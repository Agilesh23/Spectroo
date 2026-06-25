import os
import tempfile
import time
from datetime import datetime, timezone
from typing import Optional
import numpy as np

from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from pydantic import BaseModel

from spectroo.core.exceptions import CameraNotFoundError
from spectroo.camera.source import PiCameraFrameSource
from spectroo.dsp.pipeline import average_frames, run_pipeline
from spectroo.dsp.peaks import find_spectrum_peaks
from spectroo.core.calibration import PolynomialCalibration, apply_calibration
from spectroo.core.models import HistoryRecord, Peak
from spectroo.storage.db import save_record as save_spectrum, get_record, list_records
from spectroo.storage.export import export_csv, export_json
from spectroo.system.temp import get_cpu_temp_c, is_cpu_temp_warning
from spectroo.system.shutdown import request_shutdown

router = APIRouter()


class CaptureRequest(BaseModel):
    exposure_us: Optional[int] = None


class SaveRequest(BaseModel):
    label: str = ""


class ExposureRequest(BaseModel):
    exposure_us: int


class BaselineRequest(BaseModel):
    enabled: bool


def get_history(config: dict) -> list[HistoryRecord]:
    """Helper to retrieve history list from config db_path."""
    db_path = config.get("history", {}).get("db_path", "data/spectroo.db")
    from spectroo.storage.db import init_db
    try:
        init_db(db_path)
    except Exception:
        pass
    return list_records(db_path)


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

    # Check idle timeout for preview source (30s)
    source = getattr(request.app.state, "dev_preview_source", None)
    if source is not None:
        last_poll = getattr(request.app.state, "dev_preview_last_poll", 0.0)
        if time.time() - last_poll > 30.0:
            try:
                source.close()
            except Exception:
                pass
            request.app.state.dev_preview_source = None

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
        "cpu_temp": temp,
        "cpu_temp_warn": is_cpu_temp_warning(temp),
        "baseline_enabled": config.get("dsp", {}).get("baseline_enabled", True)
    }


@router.post("/api/capture")
def post_capture(body: CaptureRequest, request: Request):
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

    finally:
        source.close()

    return JSONResponse(content=request.app.state.current_frame)


@router.post("/api/live/start")
def post_live_start(request: Request):
    # Release preview camera if active to prevent collision
    source = getattr(request.app.state, "dev_preview_source", None)
    if source is not None:
        try:
            source.close()
        except Exception:
            pass
        request.app.state.dev_preview_source = None

    request.app.state.live_active = True
    return {"status": "live started"}


@router.post("/api/live/stop")
def post_live_stop(request: Request):
    request.app.state.live_active = False
    return {"status": "live stopped"}


@router.post("/api/save")
def post_save(body: SaveRequest, request: Request):
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
    config = request.app.state.config

    clamped_value = max(110, min(3066979, body.exposure_us))
    config.setdefault("camera", {})["exposure_us"] = clamped_value

    return {"exposure_us": clamped_value}


@router.post("/api/baseline")
def post_baseline(body: BaselineRequest, request: Request):
    config = request.app.state.config
    config.setdefault("dsp", {})["baseline_enabled"] = body.enabled
    return {"baseline_enabled": body.enabled}


@router.post("/api/shutdown")
async def shutdown():
    request_shutdown()
    return {"ok": True}


@router.post("/api/restart")
async def restart_pipeline(request: Request):
    request.app.state.live_active = False
    request.app.state.ws_client_connected = False
    request.app.state.current_frame = None
    source = getattr(request.app.state, "dev_preview_source", None)
    if source is not None:
        try:
            source.close()
        except Exception:
            pass
        request.app.state.dev_preview_source = None
    return {"ok": True}

