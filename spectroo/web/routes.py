import os
import json
import logging
import tempfile
import time
from datetime import datetime, timezone
from typing import Optional
import numpy as np

from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from pydantic import BaseModel

from spectroo.core.exceptions import CameraNotFoundError, CalibrationError
from spectroo.camera.source import PiCameraFrameSource
from spectroo.dsp.pipeline import average_frames, run_pipeline, to_greyscale
from spectroo.dsp.peaks import find_spectrum_peaks
from spectroo.core.calibration import PolynomialCalibration, apply_calibration, fit_calibration
from spectroo.core.models import HistoryRecord, Peak, CalibrationPoint
from spectroo.core.config import write_calibration_to_config
from spectroo.storage.db import save_record as save_spectrum, get_record, get_all_records, delete_record, set_pinned_status
from spectroo.storage.export import export_csv, export_json
from spectroo.system.temp import get_cpu_temp_c, is_cpu_temp_warning
from spectroo.system.shutdown import request_shutdown, request_reboot

logger = logging.getLogger("spectroo.web.routes")

router = APIRouter()


class CaptureRequest(BaseModel):
    exposure_us: Optional[int] = None


class SaveRequest(BaseModel):
    label: str = ""


class ExposureRequest(BaseModel):
    exposure_us: int


class BaselineRequest(BaseModel):
    enabled: bool


class DarkToggleRequest(BaseModel):
    enabled: bool


class SmoothingToggleRequest(BaseModel):
    enabled: bool


class CalibrationPointRequest(BaseModel):
    pixel_index: int
    wavelength_nm: float


class CalibrationSaveRequest(BaseModel):
    label: Optional[str] = "Untitled"



@router.get("/", response_class=HTMLResponse)
def get_root():
    static_file_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if os.path.exists(static_file_path):
        with open(static_file_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), status_code=200)
    return HTMLResponse(content="<h1>Spectroo</h1><p>Static files not yet built.</p>", status_code=200)


@router.get("/api/status")
def get_status(request: Request):
    config = request.app.state.config
    live_active = request.app.state.live_active
    calibrated = False
    cal_section = config.get("calibration", {})
    if cal_section and cal_section.get("coefficients"):
        calibrated = True

    dark_loaded = False
    dark_path = config.get("storage", {}).get("dark_frame_path", "")
    if dark_path and os.path.exists(dark_path):
        dark_loaded = True

    temp = get_cpu_temp_c()
    return {
        "live_active": live_active,
        "calibrated": calibrated,
        "dark_loaded": dark_loaded,
        "dark_subtraction_enabled": config.get("dsp", {}).get("dark_subtraction_enabled", True),
        "savgol_enabled": config.get("dsp", {}).get("savgol_enabled", True),
        "cpu_temp": temp,
        "cpu_temp_warn": is_cpu_temp_warning(temp),
        "baseline_enabled": config.get("dsp", {}).get("baseline_enabled", True),
        "wavelength_range_nm": config.get("hardware", {}).get("wavelength_range_nm", [400, 700])
    }


@router.post("/api/capture")
def post_capture(body: CaptureRequest, request: Request):
    logger.info("User action: Web API capture requested")
    config = request.app.state.config

    if request.app.state.live_active:
        raise HTTPException(status_code=409, detail="Live mode active — stop live before single capture")

    exposure_us = body.exposure_us
    if exposure_us is None:
        exposure_us = config.get("camera", {}).get("exposure_us", 200000)

    res = tuple(config.get("camera", {}).get("resolution", (2592, 200)))

    try:
        source = PiCameraFrameSource(resolution=res, exposure_us=exposure_us)
    except CameraNotFoundError as e:
        raise HTTPException(status_code=503, detail="Camera not available") from e

    try:
        n_frames = config.get("camera", {}).get("n_frames", 4)
        get_frame = getattr(source, "get_frame", None) or getattr(source, "capture_frame")
        frames = [get_frame() for _ in range(n_frames)]

        averaged = average_frames(frames)

        optics = config.get("optics", {})
        dsp_cfg = config.get("dsp", {})
        peaks_cfg = config.get("peaks", {})

        from spectroo.dsp.corrections import load_dark_frame, load_flat_field
        dark_path = config.get("storage", {}).get("dark_frame_path", "")
        flat_path = config.get("storage", {}).get("flat_field_path", "")
        dark_frame_1d = load_dark_frame(dark_path)
        response_flat = load_flat_field(flat_path)

        cal_coefs = config.get("calibration", {}).get("coefficients")
        calibration = None
        if cal_coefs:
            calibration = PolynomialCalibration(coefficients=cal_coefs, degree=len(cal_coefs) - 1, rms_nm=0.0)

        spec = run_pipeline(
            [averaged],
            optics=optics,
            dsp_cfg=dsp_cfg,
            peaks_cfg=peaks_cfg,
            exposure_us=exposure_us,
            dark_frame_1d=dark_frame_1d,
            response_flat=response_flat,
            calibration=calibration
        )

        intensities = spec.intensity
        if cal_coefs:
            wavelengths = apply_calibration(calibration, np.arange(len(intensities)))
        else:
            wavelengths = np.arange(len(intensities))

        peaks_list = find_spectrum_peaks(
            intensities,
            wavelengths,
            prominence_pct=peaks_cfg.get("prominence_pct", 0.10),
            prominence_min=peaks_cfg.get("prominence_min", 0.01),
            min_distance_px=peaks_cfg.get("min_distance_px", 20)
        )
        peaks = [p.pixel_index for p in peaks_list]

        request.app.state.current_frame = {
            "wavelengths": wavelengths.tolist(),
            "intensities": intensities.tolist(),
            "peaks": peaks
        }
        # Keep track of peaks and exposure in state for saving later
        request.app.state.current_peaks = peaks_list
        request.app.state.current_exposure = exposure_us

        # Automatically save single captures to history
        db_path = config.get("history", {}).get("db_path", "data/spectroo.db")
        from spectroo.storage.db import init_db
        try:
            init_db(db_path)
        except Exception:
            pass

        record = HistoryRecord(
            id=None,
            timestamp=datetime.now(timezone.utc).isoformat(),
            exposure_us=exposure_us,
            pixel_indices=list(range(len(intensities))),
            intensity=intensities.tolist(),
            wavelengths=wavelengths.tolist(),
            peaks=peaks_list,
            png_path="",
            calibration_rms_at_capture=None
        )
        save_spectrum(db_path, record, max_entries=20)

    finally:
        source.close()

    return JSONResponse(content=request.app.state.current_frame)


@router.get("/api/current_frame")
def get_current_frame(request: Request):
    frame = request.app.state.current_frame
    if frame is None:
        return JSONResponse(content={"intensities": [], "wavelengths": [], "peaks": []})
    return JSONResponse(content=frame)


@router.post("/api/live/start")
def post_live_start(request: Request):
    logger.info("User action: Web API live start requested")

    request.app.state.live_active = True
    return {"status": "live started"}


@router.post("/api/live/stop")
def post_live_stop(request: Request):
    logger.info("User action: Web API live stop requested")
    request.app.state.live_active = False
    return {"status": "live stopped"}


@router.post("/api/save")
def post_save(body: SaveRequest, request: Request):
    logger.info("User action: Web API save spectrum requested")
    config = request.app.state.config
    current_frame = request.app.state.current_frame

    if current_frame is None:
        raise HTTPException(status_code=400, detail="No frame data available to save")

    db_path = config.get("history", {}).get("db_path", "data/spectroo.db")
    max_entries = config.get("history", {}).get("max_entries", 500)

    from spectroo.storage.db import init_db
    try:
        init_db(db_path)
    except Exception:
        pass

    exposure_us = getattr(request.app.state, "current_exposure", None)
    if exposure_us is None:
        exposure_us = config.get("camera", {}).get("exposure_us", 200000)

    # Reconstruct or reuse Peak objects
    peaks_list = getattr(request.app.state, "current_peaks", None)
    if peaks_list is None:
        peaks_list = []
        intensities = current_frame["intensities"]
        wavelengths = current_frame["wavelengths"]
        for idx in current_frame["peaks"]:
            wl = wavelengths[idx] if wavelengths is not None else None
            peaks_list.append(Peak(
                pixel_index=int(idx),
                wavelength_nm=wl,
                intensity=float(intensities[idx]),
                prominence=0.0
            ))

    record = HistoryRecord(
        id=None,
        timestamp=datetime.now(timezone.utc).isoformat(),
        exposure_us=exposure_us,
        pixel_indices=list(range(len(current_frame["intensities"]))),
        intensity=current_frame["intensities"],
        wavelengths=current_frame["wavelengths"],
        peaks=peaks_list,
        png_path="",
        calibration_rms_at_capture=None
    )

    record_id = save_spectrum(db_path, record, max_entries=max_entries)
    return {"saved": True, "record_id": record_id}




@router.get("/api/export/current")
def get_export_current(request: Request, background_tasks: BackgroundTasks, format: str = "json"):
    logger.info("User action: Web API export current requested (format: %s)", format)
    config = request.app.state.config
    current_frame = request.app.state.current_frame

    if current_frame is None:
        raise HTTPException(status_code=400, detail="No frame data available to export")

    exposure_us = getattr(request.app.state, "current_exposure", None)
    if exposure_us is None:
        exposure_us = config.get("camera", {}).get("exposure_us", 200000)

    # Reconstruct or reuse Peak objects
    peaks_list = getattr(request.app.state, "current_peaks", None)
    if peaks_list is None:
        peaks_list = []
        intensities = current_frame["intensities"]
        wavelengths = current_frame["wavelengths"]
        for idx in current_frame["peaks"]:
            wl = wavelengths[idx] if wavelengths is not None else None
            peaks_list.append(Peak(
                pixel_index=int(idx),
                wavelength_nm=wl,
                intensity=float(intensities[idx]),
                prominence=0.0
            ))

    record = HistoryRecord(
        id=None,
        timestamp=datetime.now(timezone.utc).isoformat(),
        exposure_us=exposure_us,
        pixel_indices=list(range(len(current_frame["intensities"]))),
        intensity=current_frame["intensities"],
        wavelengths=current_frame["wavelengths"],
        peaks=peaks_list,
        png_path="",
        calibration_rms_at_capture=None
    )

    suffix = ".csv" if format == "csv" else ".json"
    fd, temp_path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)

    try:
        if format == "csv":
            export_csv(record, temp_path)
            media_type = "text/csv"
            filename = "spectrum_current.csv"
        else:
            export_json(record, temp_path)
            media_type = "application/json"
            filename = "spectrum_current.json"

        background_tasks.add_task(os.remove, temp_path)
        return FileResponse(temp_path, media_type=media_type, filename=filename)
    except Exception as e:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/api/export/{record_id}")
def get_export_record(record_id: int, request: Request, background_tasks: BackgroundTasks, format: str = "json"):
    logger.info("User action: Web API export record %d requested (format: %s)", record_id, format)
    config = request.app.state.config
    db_path = config.get("history", {}).get("db_path", "data/spectroo.db")
    record = get_record(db_path, record_id)

    if record is None:
        raise HTTPException(status_code=404, detail="Record not found")

    suffix = ".csv" if format == "csv" else ".json"
    fd, temp_path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)

    try:
        if format == "csv":
            export_csv(record, temp_path)
            media_type = "text/csv"
            filename = f"spectrum_{record_id}.csv"
        else:
            export_json(record, temp_path)
            media_type = "application/json"
            filename = f"spectrum_{record_id}.json"

        background_tasks.add_task(os.remove, temp_path)
        return FileResponse(temp_path, media_type=media_type, filename=filename)
    except Exception as e:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/api/exposure")
def post_exposure(body: ExposureRequest, request: Request):
    logger.info("User action: Web API exposure changed to %d us", body.exposure_us)
    config = request.app.state.config

    clamped_value = max(110, min(3066979, body.exposure_us))
    config.setdefault("camera", {})["exposure_us"] = clamped_value

    return {"exposure_us": clamped_value}


@router.post("/api/baseline")
def post_baseline(body: BaselineRequest, request: Request):
    logger.info("User action: Web API baseline correction toggled to %s", body.enabled)
    config = request.app.state.config
    config.setdefault("dsp", {})["baseline_enabled"] = body.enabled
    return {"baseline_enabled": body.enabled}


@router.post("/api/shutdown")
async def shutdown():
    logger.info("User action: Web API shutdown requested")
    request_shutdown()
    return {"ok": True}


@router.post("/api/reboot")
async def reboot():
    logger.info("User action: Web API reboot requested")
    request_reboot()
    return {"ok": True}


@router.post("/api/restart")
async def restart_pipeline(request: Request):
    logger.info("User action: Web API restart pipeline requested")
    request.app.state.live_active = False
    request.app.state.ws_client_connected = False
    request.app.state.current_frame = None
    return {"ok": True}


@router.post("/api/dark/capture")
def post_dark_capture(request: Request):
    logger.info("User action: Web API dark frame capture requested")
    config = request.app.state.config

    if request.app.state.live_active:
        raise HTTPException(status_code=409, detail="Live mode active — stop live before dark capture")

    exposure_us = config.get("camera", {}).get("exposure_us", 200000)
    res = tuple(config.get("camera", {}).get("resolution", (2592, 200)))

    try:
        source = PiCameraFrameSource(resolution=res, exposure_us=exposure_us)
    except CameraNotFoundError as e:
        raise HTTPException(status_code=503, detail="Camera not available") from e

    try:
        frames = []
        for _ in range(4):
            frames.append(source.capture_frame())
            time.sleep(0.01)

        averaged = average_frames(frames)
        grey = to_greyscale(averaged)

        dark_path = config.get("storage", {}).get("dark_frame_path", "")
        if dark_path:
            os.makedirs(os.path.dirname(dark_path), exist_ok=True)
            np.save(dark_path, grey)
            logger.info(f"Dark frame saved successfully to: {dark_path}")
        else:
            raise HTTPException(status_code=500, detail="Dark frame path not specified in configuration.")
    except Exception as e:
        logger.error(f"Error during dark capture: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        source.close()

    return {"status": "Dark frame captured and saved successfully"}


@router.post("/api/dark/toggle")
def post_dark_toggle(body: DarkToggleRequest, request: Request):
    logger.info("User action: Web API dark subtraction toggled to %s", body.enabled)
    config = request.app.state.config
    config.setdefault("dsp", {})["dark_subtraction_enabled"] = body.enabled
    return {"dark_subtraction_enabled": body.enabled}


@router.post("/api/smoothing/toggle")
def post_smoothing_toggle(body: SmoothingToggleRequest, request: Request):
    logger.info("User action: Web API smoothing toggled to %s", body.enabled)
    config = request.app.state.config
    config.setdefault("dsp", {})["savgol_enabled"] = body.enabled
    return {"savgol_enabled": body.enabled}


@router.get("/logs", response_class=HTMLResponse)
def get_logs(request: Request):
    if not getattr(request.app.state, "dev", False):
        raise HTTPException(status_code=403, detail="Developer mode is not enabled")
    static_file_path = os.path.join(os.path.dirname(__file__), "static", "logs.html")
    if os.path.exists(static_file_path):
        with open(static_file_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), status_code=200)
    return HTMLResponse(content="<h1>Spectroo v3 - Logs</h1><p>Template logs.html not found.</p>", status_code=404)


@router.get("/api/history")
def get_history(request: Request):
    config = request.app.state.config
    db_path = config.get("history", {}).get("db_path", "data/spectroo.db")
    from spectroo.storage.db import init_db
    try:
        init_db(db_path)
    except Exception:
        pass
    records = get_all_records(db_path)
    
    serialized = []
    for r in records:
        ints = r.intensity
        sparkline = []
        if ints:
            step = max(1, len(ints) // 100)
            sparkline = ints[::step][:100]
            
        serialized.append({
            "id": r.id,
            "timestamp": r.timestamp,
            "exposure_us": r.exposure_us,
            "pinned": r.pinned,
            "peaks_count": len(r.peaks),
            "sparkline": sparkline
        })
    return serialized


@router.post("/api/history/{record_id}/restore")
def post_restore_record(record_id: int, request: Request):
    config = request.app.state.config
    db_path = config.get("history", {}).get("db_path", "data/spectroo.db")
    record = get_record(db_path, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Record not found")
        
    peaks_px = [p.pixel_index for p in record.peaks]
    request.app.state.current_frame = {
        "wavelengths": record.wavelengths,
        "intensities": record.intensity,
        "peaks": peaks_px
    }
    request.app.state.current_peaks = record.peaks
    request.app.state.current_exposure = record.exposure_us
    return request.app.state.current_frame


@router.delete("/api/history/{record_id}")
def delete_history_record(record_id: int, request: Request):
    config = request.app.state.config
    db_path = config.get("history", {}).get("db_path", "data/spectroo.db")
    try:
        delete_record(db_path, record_id)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/history/{record_id}/pin")
def pin_history_record(record_id: int, request: Request):
    config = request.app.state.config
    db_path = config.get("history", {}).get("db_path", "data/spectroo.db")
    try:
        set_pinned_status(db_path, record_id, True)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/history/{record_id}/unpin")
def unpin_history_record(record_id: int, request: Request):
    config = request.app.state.config
    db_path = config.get("history", {}).get("db_path", "data/spectroo.db")
    try:
        set_pinned_status(db_path, record_id, False)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def load_state_file(request: Request) -> dict:
    config = request.app.state.config
    config_dir = os.path.dirname(request.app.state.config_path)
    rel_path = config.get("storage", {}).get("calibration_state_path", "data/calibration_state.json")
    state_path = os.path.join(config_dir, rel_path)

    if not os.path.exists(state_path):
        return {"points": [], "fit_result": None, "fit_points": None}
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to read calibration state file: {e}")
        return {"points": [], "fit_result": None, "fit_points": None}


def save_state_file(request: Request, state: dict) -> None:
    config = request.app.state.config
    config_dir = os.path.dirname(request.app.state.config_path)
    rel_path = config.get("storage", {}).get("calibration_state_path", "data/calibration_state.json")
    state_path = os.path.join(config_dir, rel_path)

    try:
        os.makedirs(os.path.dirname(state_path), exist_ok=True)
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save calibration state: {e}")


@router.get("/api/calibration/state")
def get_calibration_state(request: Request):
    return load_state_file(request)


@router.post("/api/calibration/point")
def post_calibration_point(body: CalibrationPointRequest, request: Request):
    state = load_state_file(request)
    state.setdefault("points", []).append({
        "pixel": body.pixel_index,
        "wavelength": body.wavelength_nm
    })
    save_state_file(request, state)
    return state["points"]


@router.delete("/api/calibration/point/{index}")
def delete_calibration_point(index: int, request: Request):
    state = load_state_file(request)
    points = state.setdefault("points", [])
    if index < 0 or index >= len(points):
        raise HTTPException(status_code=404, detail="Index out of range")
    points.pop(index)
    save_state_file(request, state)
    return points


@router.post("/api/calibration/undo")
def post_calibration_undo(request: Request):
    state = load_state_file(request)
    points = state.setdefault("points", [])
    if points:
        points.pop()
        save_state_file(request, state)
    return points


@router.post("/api/calibration/fit")
def post_calibration_fit(request: Request):
    state = load_state_file(request)
    points_data = state.setdefault("points", [])
    
    if len(points_data) < 2:
        raise HTTPException(status_code=400, detail="Fewer than 2 calibration points supplied.")
        
    pts = [
        CalibrationPoint(pixel_index=p["pixel"], known_wavelength_nm=p["wavelength"])
        for p in points_data
    ]
    
    pixels = [p.pixel_index for p in pts]
    if len(pixels) != len(set(pixels)):
        raise HTTPException(status_code=400, detail="Duplicate pixel indices in calibration points.")

    try:
        result = fit_calibration(pts, degree_high=3, min_points=2)
        if np.isnan(result.coefficients).any() or np.isinf(result.coefficients).any() or np.isnan(result.rms_nm):
            raise CalibrationError("Polynomial fitting failed: singular matrix or invalid coefficients.")
    except CalibrationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Polynomial fitting failed: {e}")
        
    residuals = [
        float(np.polyval(result.coefficients, p["pixel"]) - p["wavelength"])
        for p in points_data
    ]

    fit_result_data = {
        "degree": result.degree,
        "rms_nm": result.rms_nm,
        "coefficients": result.coefficients,
        "residuals": residuals
    }
    
    state["fit_result"] = fit_result_data
    state["fit_points"] = points_data.copy()
    
    save_state_file(request, state)
    return fit_result_data


@router.post("/api/calibration/apply")
def post_calibration_apply(request: Request):
    state = load_state_file(request)
    fit_result = state.get("fit_result")
    fit_points = state.get("fit_points")
    points = state.get("points", [])
    
    if fit_result is None or fit_points is None:
        raise HTTPException(status_code=400, detail="No fit computed yet")
        
    # Check staleness
    is_stale = False
    if len(points) != len(fit_points):
        is_stale = True
    else:
        for p1, p2 in zip(points, fit_points):
            if p1.get("pixel") != p2.get("pixel") or not np.isclose(p1.get("wavelength", 0.0), p2.get("wavelength", 0.0), atol=1e-5):
                is_stale = True
                break
                
    if is_stale:
        raise HTTPException(status_code=400, detail="Fit is stale, run fit again")

    coefficients = fit_result["coefficients"]
    degree = fit_result["degree"]
    n_points = len(points)
    config_path = request.app.state.config_path
    
    try:
        write_calibration_to_config(config_path, coefficients, degree, n_points)
        from spectroo.core.config import load_config
        new_config = load_config(config_path)
        request.app.state.config.clear()
        request.app.state.config.update(new_config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"status": "Calibration applied successfully"}


@router.post("/api/calibration/clear")
def post_calibration_clear(request: Request):
    save_state_file(request, {"points": [], "fit_result": None, "fit_points": None})
    config_path = request.app.state.config_path
    
    try:
        write_calibration_to_config(config_path, [], 3, 0)
        from spectroo.core.config import load_config
        new_config = load_config(config_path)
        request.app.state.config.clear()
        request.app.state.config.update(new_config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"status": "Calibration cleared"}


@router.post("/api/calibration/save")
def post_calibration_save(body: CalibrationSaveRequest, request: Request):
    config = request.app.state.config
    calib = config.get("calibration", {})
    coefficients = calib.get("coefficients", [])
    
    if not coefficients:
        raise HTTPException(status_code=400, detail="No active calibration to save")
        
    config_dir = os.path.dirname(request.app.state.config_path)
    rel_dir = config.get("storage", {}).get("calibrations_dir", "data/calibrations")
    calibrations_dir = os.path.abspath(os.path.join(config_dir, rel_dir))
    os.makedirs(calibrations_dir, exist_ok=True)
    
    # Load rms_nm from state if available
    state = load_state_file(request)
    fit_result = state.get("fit_result")
    rms_nm = fit_result.get("rms_nm") if fit_result else None
    
    label = body.label or "Untitled"
    now_utc = datetime.now(timezone.utc)
    ts = now_utc.strftime("%Y-%m-%dT%H-%M-%S")
    filename = f"calibration_{ts}.json"
    file_path = os.path.join(calibrations_dir, filename)
    
    payload = {
        "label": label,
        "coefficients": coefficients,
        "degree": calib.get("degree", 3),
        "n_points": calib.get("n_points", 0),
        "rms_nm": rms_nm,
        "saved_at": now_utc.isoformat()
    }
    
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to write calibration snapshot to {file_path}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save calibration snapshot: {e}")
        
    return {"filename": filename, "data": payload}


@router.get("/api/calibration/list")
def get_calibration_list(request: Request):
    config = request.app.state.config
    config_dir = os.path.dirname(request.app.state.config_path)
    rel_dir = config.get("storage", {}).get("calibrations_dir", "data/calibrations")
    calibrations_dir = os.path.abspath(os.path.join(config_dir, rel_dir))
    
    if not os.path.exists(calibrations_dir):
        return []
        
    results = []
    try:
        files = os.listdir(calibrations_dir)
    except Exception as e:
        logger.error(f"Failed to list directory {calibrations_dir}: {e}")
        return []
        
    for filename in files:
        if not filename.endswith(".json"):
            continue
        file_path = os.path.join(calibrations_dir, filename)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Ensure basic fields are present
            results.append({
                "filename": filename,
                "label": data.get("label", "Untitled"),
                "saved_at": data.get("saved_at", ""),
                "rms_nm": data.get("rms_nm"),
                "n_points": data.get("n_points", 0),
                "degree": data.get("degree", 3)
            })
        except Exception as e:
            logger.error(f"Failed to parse calibration snapshot file {filename}: {e}")
            continue
            
    # Sort newest-first based on saved_at string comparison
    results.sort(key=lambda x: x["saved_at"], reverse=True)
    return results


@router.post("/api/calibration/load/{filename:path}")
def post_calibration_load(filename: str, request: Request):
    # Path-sanitize
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid snapshot filename")
        
    config = request.app.state.config
    config_dir = os.path.dirname(request.app.state.config_path)
    rel_dir = config.get("storage", {}).get("calibrations_dir", "data/calibrations")
    calibrations_dir = os.path.abspath(os.path.join(config_dir, rel_dir))
    file_path = os.path.join(calibrations_dir, filename)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Calibration snapshot not found")
        
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.error(f"Failed to parse snapshot JSON {filename}: {e}")
        raise HTTPException(status_code=400, detail="Malformed JSON content in snapshot file")
        
    coefficients = data.get("coefficients")
    degree = data.get("degree")
    n_points = data.get("n_points")
    
    if coefficients is None or degree is None or n_points is None:
        raise HTTPException(status_code=400, detail="Snapshot is missing required calibration parameters")
        
    config_path = request.app.state.config_path
    try:
        write_calibration_to_config(config_path, coefficients, degree, n_points)
        from spectroo.core.config import load_config
        new_config = load_config(config_path)
        request.app.state.config.clear()
        request.app.state.config.update(new_config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
    return {"status": "Calibration loaded successfully"}


