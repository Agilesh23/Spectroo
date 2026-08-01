from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
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


async def log_stream_generator(log_path: str):
    import shutil
    import subprocess
    import os

    has_journalctl = False
    if shutil.which("journalctl"):
        try:
            res = await asyncio.create_subprocess_exec(
                "journalctl", "-u", "spectroo.service", "-n", "1",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            await res.wait()
            if res.returncode == 0:
                has_journalctl = True
        except Exception:
            pass

    if has_journalctl:
        proc = await asyncio.create_subprocess_exec(
            "journalctl", "-u", "spectroo.service", "-f", "-n", "100",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
        )
        try:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                yield line.decode("utf-8", errors="ignore")
        finally:
            try:
                proc.terminate()
                await proc.wait()
            except Exception:
                pass
    else:
        expanded_path = log_path
        os.makedirs(os.path.dirname(expanded_path), exist_ok=True)
        if not os.path.exists(expanded_path):
            with open(expanded_path, "w", encoding="utf-8") as f:
                f.write("")

        try:
            with open(expanded_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                for line in lines[-100:]:
                    yield line
        except Exception:
            pass

        try:
            with open(expanded_path, "r", encoding="utf-8") as f:
                f.seek(0, os.SEEK_END)
                while True:
                    line = f.readline()
                    if not line:
                        await asyncio.sleep(0.1)
                        continue
                    yield line
        except Exception:
            pass


@router.websocket("/ws/logs")
async def logs_stream(websocket: WebSocket):
    # Check dev mode BEFORE calling accept()
    if not getattr(websocket.app.state, "dev", False):
        raise HTTPException(status_code=403, detail="Developer mode is not enabled")

    await websocket.accept()
    import os as _os
    _project_root = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    log_path = _os.path.join(_project_root, "logs", "spectroo.log")
    
    try:
        async for line in log_stream_generator(log_path):
            await websocket.send_json({"log": line.strip()})
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"error": str(e)})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
