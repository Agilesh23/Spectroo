"""REST routes for developer mode actions."""
import os
import time
from typing import Optional
import numpy as np
from pydantic import BaseModel
from fastapi import APIRouter, Request, HTTPException, Depends, status, Query, Header

from spectroo.camera.source import PiCameraFrameSource
from spectroo.core.exceptions import CameraNotFoundError, CalibrationError
from spectroo.core.models import CalibrationPoint
from spectroo.core.calibration import fit_calibration
from spectroo.dsp.pipeline import average_frames, to_greyscale, apply_tilt_correction
from spectroo.dsp.collapse import extract_band, apply_flip

router = APIRouter()


def _close_preview_source(request: Request):
    source = getattr(request.app.state, "dev_preview_source", None)
    if source is not None:
        try:
            source.close()
        except Exception:
            pass
        request.app.state.dev_preview_source = None


def verify_dev_password(
    request: Request,
    x_dev_password: Optional[str] = Header(None, alias="X-Dev-Password"),
    password: Optional[str] = Query(None)
):
    expected = request.app.state.config.get("web", {}).get("dev_password", "changeme")
    provided = x_dev_password or password
    if not provided or provided != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid developer password"
        )


@router.get("/api/dev/auth")
def verify_dev_auth(password: str = Depends(verify_dev_password)):
    return {"ok": True}


@router.post("/api/dev/preview/start")
def post_dev_preview_start(request: Request):
    if request.app.state.live_active:
        raise HTTPException(status_code=409, detail="Stop live mode first")
    source = getattr(request.app.state, "dev_preview_source", None)
    if source is None:
        config = request.app.state.config
        res = tuple(config.get("camera", {}).get("resolution", (2592, 200)))
        try:
            source = PiCameraFrameSource(resolution=res)
            request.app.state.dev_preview_source = source
        except CameraNotFoundError as e:
            raise HTTPException(status_code=503, detail="Camera not available") from e
    return {"ok": True}


@router.get("/api/dev/preview")
def get_dev_preview(request: Request, password: str = Depends(verify_dev_password)):
    if request.app.state.live_active:
        _close_preview_source(request)
        raise HTTPException(status_code=409, detail="Stop live mode before capturing camera preview")

    # Update poll time
    request.app.state.dev_preview_last_poll = time.time()

    # Get or create preview camera source
    source = getattr(request.app.state, "dev_preview_source", None)
    if source is None:
        config = request.app.state.config
        res = tuple(config.get("camera", {}).get("resolution", (2592, 200)))
        try:
            source = PiCameraFrameSource(resolution=res)
            request.app.state.dev_preview_source = source
        except CameraNotFoundError as e:
            raise HTTPException(status_code=503, detail="Camera not available") from e

    config = request.app.state.config
    # Update exposure dynamically if configured
    if hasattr(source, "set_exposure_us"):
        source.set_exposure_us(config.get("camera", {}).get("exposure_us", 200000))

    try:
        frame = source.get_frame() if hasattr(source, "get_frame") else source.capture_frame()
        if frame is None:
            raise HTTPException(status_code=500, detail="Failed to capture frame")

        optics = config.get("optics", {})
        tilt_angle = optics.get("tilt_angle_deg", 0.0)

        # Apply same 2D processing as QDialog does: rotate RGB frame directly
        if abs(tilt_angle) > 1e-5:
            import scipy.ndimage
            if frame.ndim == 3:
                tilted = scipy.ndimage.rotate(frame, angle=tilt_angle, reshape=False, order=1, axes=(0, 1))
            else:
                tilted = apply_tilt_correction(frame, tilt_angle)
        else:
            tilted = frame

        if tilted.ndim == 2:
            tilted = np.stack([tilted, tilted, tilted], axis=-1)

        # Normalize to 0-255 range for image data drawing on client side
        min_val = tilted.min()
        max_val = tilted.max()
        range_val = max(max_val - min_val, 1)
        norm = ((tilted - min_val) / range_val * 255).astype(np.uint8)

        h, w, c = norm.shape
        return {
            "width": w,
            "height": h,
            "channels": 3,
            "data": norm.flatten().tolist()
        }
    except Exception as e:
        _close_preview_source(request)
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/api/dev/preview/stop")
def post_dev_preview_stop(request: Request):
    _close_preview_source(request)
    return {"status": "success", "message": "Preview camera source closed"}


@router.post("/api/dev/dark")
def post_dev_dark(request: Request, password: str = Depends(verify_dev_password)):
    if request.app.state.live_active:
        raise HTTPException(status_code=409, detail="Stop live mode before capturing dark frame")

    # Release preview camera if active to prevent collision
    _close_preview_source(request)

    config = request.app.state.config
    res = tuple(config.get("camera", {}).get("resolution", (2592, 200)))
    try:
        source = PiCameraFrameSource(resolution=res)
    except CameraNotFoundError as e:
        raise HTTPException(status_code=503, detail="Camera not available") from e

    try:
        frames = []
        for _ in range(4):
            frame = source.get_frame() if hasattr(source, "get_frame") else source.capture_frame()
            frames.append(frame)
            time.sleep(0.01)

        averaged = average_frames(frames)
        grey = to_greyscale(averaged)

        dark_path = config.get("storage", {}).get("dark_frame_path", "")
        if dark_path:
            parent_dir = os.path.dirname(dark_path)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
            np.save(dark_path, grey)
            return {"status": "success", "message": f"Dark frame saved successfully to: {dark_path}"}
        else:
            raise HTTPException(status_code=400, detail="Dark frame path not specified in configuration.")
    finally:
        source.close()


@router.post("/api/dev/flat")
def post_dev_flat(request: Request, password: str = Depends(verify_dev_password)):
    if request.app.state.live_active:
        raise HTTPException(status_code=409, detail="Stop live mode before capturing flat field")

    # Release preview camera if active to prevent collision
    _close_preview_source(request)

    config = request.app.state.config
    res = tuple(config.get("camera", {}).get("resolution", (2592, 200)))
    exposure_us = config.get("camera", {}).get("exposure_us", 200000)
    try:
        source = PiCameraFrameSource(resolution=res, exposure_us=exposure_us)
    except CameraNotFoundError as e:
        raise HTTPException(status_code=503, detail="Camera not available") from e

    try:
        time.sleep(0.5)  # allow camera to settle
        n_frames = config.get("camera", {}).get("frame_stack", 4)
        frames = []
        for _ in range(n_frames):
            frame = source.get_frame() if hasattr(source, "get_frame") else source.capture_frame()
            frames.append(frame)
            time.sleep(0.01)

        averaged = average_frames(frames)
        grey = to_greyscale(averaged)

        optics = config.get("optics", {})
        dsp_cfg = config.get("dsp", {})

        tilted = apply_tilt_correction(grey, optics.get("tilt_angle_deg", 0.0))
        band = extract_band(tilted, optics.get("center_y", 0), dsp_cfg.get("band_half_height", 15))
        profile = apply_flip(band, optics.get("flip_spectrum", False))

        # Subtract dark frame if it exists
        dark_path = config.get("storage", {}).get("dark_frame_path", "")
        if dark_path and os.path.exists(dark_path):
            try:
                dark_frame = np.load(dark_path)
                if dark_frame.ndim == 2:
                    dark_tilted = apply_tilt_correction(dark_frame, optics.get("tilt_angle_deg", 0.0))
                    dark_band = extract_band(dark_tilted, optics.get("center_y", 0), dsp_cfg.get("band_half_height", 15))
                    dark_frame_1d = apply_flip(dark_band, optics.get("flip_spectrum", False))
                else:
                    dark_frame_1d = dark_frame

                from spectroo.dsp.corrections import subtract_dark
                profile = subtract_dark(profile, dark_frame_1d)
            except Exception:
                pass

        # Clamp and normalize
        floor = np.mean(profile) * 0.05
        profile = np.clip(profile, floor, None)
        mean_val = np.mean(profile)
        if mean_val <= 0:
            raise HTTPException(status_code=400, detail="Cannot normalize flat-field: mean intensity is zero or negative.")
        profile = profile / mean_val

        # Save as JSON array
        flat_path = config.get("storage", {}).get("flat_field_path", "data/response_flat.json")
        if flat_path:
            parent_dir = os.path.dirname(flat_path)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
            import json
            with open(flat_path, "w") as f:
                json.dump(profile.tolist(), f)
            return {"status": "success", "message": f"Flat-field saved successfully to: {flat_path}"}
        else:
            raise HTTPException(status_code=400, detail="Flat-field path not specified in configuration.")
    finally:
        source.close()


class CalibrationPair(BaseModel):
    pixel: int
    wavelength: float


class CalibrateRequest(BaseModel):
    pairs: list[CalibrationPair]


@router.post("/api/dev/calibrate")
def post_dev_calibrate(body: CalibrateRequest, request: Request, password: str = Depends(verify_dev_password)):
    # 1. Map to CalibrationPoint objects
    points = [
        CalibrationPoint(pixel_index=p.pixel, known_wavelength_nm=p.wavelength)
        for p in body.pairs
    ]

    # 2. Fit calibration
    try:
        calib = fit_calibration(points)
    except CalibrationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    coefs_list = calib.coefficients
    degree = calib.degree
    n_points = len(points)

    # Compute residuals: predicted wavelength minus known wavelength
    residuals_nm = [
        float(np.polyval(coefs_list, p.pixel_index) - p.known_wavelength_nm)
        for p in points
    ]

    # 3. Save to config.toml on disk and update in-memory
    config = request.app.state.config
    config_path = getattr(request.app.state, "config_path", "config.toml")

    try:
        try:
            import tomli_w
            import tomllib
            with open(config_path, "rb") as f:
                data = tomllib.load(f)
            if "calibration" not in data:
                data["calibration"] = {}
            data["calibration"]["coefficients"] = coefs_list
            data["calibration"]["degree"] = degree
            data["calibration"]["n_points"] = n_points
            with open(config_path, "wb") as f:
                tomli_w.dump(data, f)
        except ImportError:
            with open(config_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            cal_idx = -1
            for i, line in enumerate(lines):
                if line.strip().startswith("[calibration]"):
                    cal_idx = i
                    break

            coef_str = "[" + ", ".join(f"{c:.6e}" for c in coefs_list) + "]"
            new_lines_section = [
                f"coefficients = {coef_str}\n",
                f"degree = {degree}\n",
                f"n_points = {n_points}\n"
            ]

            if cal_idx != -1:
                end_idx = len(lines)
                for i in range(cal_idx + 1, len(lines)):
                    if lines[i].strip().startswith("[") and not lines[i].strip().startswith("[calibration]"):
                        end_idx = i
                        break
                section_lines = lines[cal_idx+1:end_idx]
                filtered_lines = []
                for line in section_lines:
                    is_replace = False
                    if "=" in line:
                        key = line.split("=")[0].strip()
                        if key in ["coefficients", "degree", "n_points"]:
                            is_replace = True
                    if not is_replace:
                        filtered_lines.append(line)
                filtered_lines.extend(new_lines_section)
                new_lines = lines[:cal_idx+1] + filtered_lines + lines[end_idx:]
            else:
                new_lines = lines + ["\n[calibration]\n"] + new_lines_section

            with open(config_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)

        # Update in-memory config dict
        if "calibration" not in config:
            config["calibration"] = {}
        config["calibration"]["coefficients"] = coefs_list
        config["calibration"]["degree"] = degree
        config["calibration"]["n_points"] = n_points

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save coefficients to config: {e}")

    return {
        "status": "success",
        "coefficients": coefs_list,
        "rms_nm": calib.rms_nm,
        "degree": degree,
        "residuals_nm": residuals_nm
    }
