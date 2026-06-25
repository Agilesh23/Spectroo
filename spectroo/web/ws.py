from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
import numpy as np
from spectroo.camera.source import PiCameraFrameSource
from spectroo.core.exceptions import CameraNotFoundError
from spectroo.dsp.pipeline import run_pipeline
from spectroo.core.calibration import apply_calibration, PolynomialCalibration
from spectroo.dsp.peaks import find_spectrum_peaks
from spectroo.system.temp import get_cpu_temp_c, is_cpu_temp_warning

router = APIRouter()

@router.websocket("/ws/live")
async def live_stream(websocket: WebSocket):
    await websocket.accept()
    
    if websocket.app.state.ws_client_connected:
        await websocket.send_json({"error": "device busy"})
        await websocket.close()
        return
        
    websocket.app.state.ws_client_connected = True
    websocket.app.state.live_active = True
    source = None
    try:
        config = websocket.app.state.config
        res = tuple(config.get("camera", {}).get("resolution", [2592, 200]))
        exp = config.get("camera", {}).get("exposure_us", 200000)
        source = PiCameraFrameSource(resolution=res, exposure_us=exp)
    except CameraNotFoundError:
        await websocket.send_json({"error": "camera not available"})
        websocket.app.state.live_active = False
        websocket.app.state.ws_client_connected = False
        await websocket.close()
        return
    except Exception as e:
        await websocket.send_json({"error": str(e)})
        websocket.app.state.live_active = False
        websocket.app.state.ws_client_connected = False
        await websocket.close()
        return

    try:
        loop = asyncio.get_running_loop()
        frame_fn = source.get_frame if hasattr(source, "get_frame") else source.capture_frame
        
        while websocket.app.state.live_active:
            config = websocket.app.state.config
            # Check exposure update from config dynamically
            source.set_exposure_us(config.get("camera", {}).get("exposure_us", 200000))
            
            frame = await loop.run_in_executor(None, frame_fn)
            
            optics = config.get("optics", {})
            dsp_cfg = config.get("dsp", {})
            peaks_cfg = config.get("peaks", {})
            exposure_us = config.get("camera", {}).get("exposure_us", 200000)

            # Load dark frame and flat-field if path exists
            from spectroo.dsp.corrections import load_dark_frame, load_flat_field
            dark_path = config.get("storage", {}).get("dark_frame_path", "")
            flat_path = config.get("storage", {}).get("flat_field_path", "")
            dark_frame_1d = load_dark_frame(dark_path)
            response_flat = load_flat_field(flat_path)

            spec = run_pipeline(
                [frame],
                optics,
                dsp_cfg,
                peaks_cfg,
                exposure_us,
                dark_frame_1d=dark_frame_1d,
                response_flat=response_flat
            )
            intensities = spec.intensity
            
            cal_coefs = config.get("calibration", {}).get("coefficients", None)
            if cal_coefs:
                cal = PolynomialCalibration(coefficients=cal_coefs, degree=len(cal_coefs)-1, rms_nm=0.0)
                wavelengths = apply_calibration(cal, np.arange(len(intensities)))
            else:
                wavelengths = np.arange(len(intensities))

            peaks_list = find_spectrum_peaks(
                intensities,
                wavelengths,
                peaks_cfg.get("prominence_pct", 0.10),
                peaks_cfg.get("prominence_min", 0.01),
                peaks_cfg.get("min_distance_px", 20)
            )
            peaks = [p.pixel_index for p in peaks_list]

            temp = get_cpu_temp_c()
            websocket.app.state.current_frame = {
                "wavelengths": wavelengths.tolist(),
                "intensities": intensities.tolist(),
                "peaks": peaks,
                "cpu_temp": temp,
                "cpu_temp_warn": is_cpu_temp_warning(temp)
            }

            await websocket.send_json(websocket.app.state.current_frame)
            await asyncio.sleep(0.05)
            
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"error": str(e)})
        except Exception:
            pass
    finally:
        websocket.app.state.live_active = False
        websocket.app.state.ws_client_connected = False
        if source is not None:
            try:
                source.close()
            except Exception:
                pass
        try:
            await websocket.close()
        except Exception:
            pass
