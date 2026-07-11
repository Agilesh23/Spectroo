import pytest
import httpx
import tempfile
import os
from pathlib import Path
from spectroo.web.app import create_app

pytestmark = pytest.mark.asyncio

# Create a temporary database file path
_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_db_name = _db.name
_db.close()

MINIMAL_CONFIG = {
    "camera": {"exposure_us": 50000, "n_frames": 4},
    "dsp": {"baseline_enabled": True},
    "storage": {"dark_frame_path": "dark_frame.npy"},
    "history": {"db_path": _db_name, "max_entries": 500},
    "calibration": {},
}


@pytest.fixture
def app(tmp_path):
    # Create a temporary config.toml file for testing
    temp_config = tmp_path / "config.toml"
    temp_config.write_text("[calibration]\ncoefficients = []\ndegree = 3\nn_points = 0\n", encoding="utf-8")
    
    # Fresh app instance
    application = create_app(MINIMAL_CONFIG, config_path=str(temp_config))
    application.state.live_active = False
    application.state.current_frame = None
    application.state.current_peaks = None
    application.state.current_exposure = None

    # Ensure a fresh/empty database for each test
    if os.path.exists(_db_name):
        try:
            os.remove(_db_name)
        except Exception:
            pass

    yield application

    # Cleanup database if still exists
    if os.path.exists(_db_name):
        try:
            os.remove(_db_name)
        except Exception:
            pass


def get_client(app):
    """Factory to create an AsyncClient with compatibility for newer httpx versions."""
    try:
        from httpx import ASGITransport
        return httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    except ImportError:
        return httpx.AsyncClient(app=app, base_url="http://test")


# 1. test_get_root_returns_200
async def test_get_root_returns_200(app):
    async with get_client(app) as client:
        response = await client.get("/")
        assert response.status_code == 200


# 2. test_status_endpoint
async def test_status_endpoint(app):
    async with get_client(app) as client:
        response = await client.get("/api/status")
        assert response.status_code == 200
        assert "live_active" in response.json()


# 3. test_status_not_live_initially
async def test_status_not_live_initially(app):
    async with get_client(app) as client:
        response = await client.get("/api/status")
        assert response.status_code == 200
        assert response.json()["live_active"] is False


# 4. test_live_start_sets_flag
async def test_live_start_sets_flag(app):
    async with get_client(app) as client:
        response_start = await client.post("/api/live/start")
        assert response_start.status_code == 200

        response_status = await client.get("/api/status")
        assert response_status.status_code == 200
        assert response_status.json()["live_active"] is True


# 5. test_live_stop_clears_flag
async def test_live_stop_clears_flag(app):
    async with get_client(app) as client:
        # Start
        await client.post("/api/live/start")
        # Stop
        response_stop = await client.post("/api/live/stop")
        assert response_stop.status_code == 200

        # Check
        response_status = await client.get("/api/status")
        assert response_status.json()["live_active"] is False


# 6. test_capture_without_camera_returns_503
async def test_capture_without_camera_returns_503(app):
    async with get_client(app) as client:
        response = await client.post("/api/capture", json={})
        assert response.status_code == 503


# 7. test_capture_blocked_during_live
async def test_capture_blocked_during_live(app):
    async with get_client(app) as client:
        # Start live
        await client.post("/api/live/start")
        # Try capture
        response = await client.post("/api/capture", json={})
        assert response.status_code == 409



# 9. test_save_without_frame_returns_400
async def test_save_without_frame_returns_400(app):
    async with get_client(app) as client:
        response = await client.post("/api/save", json={"label": "test"})
        assert response.status_code == 400


# 10. test_exposure_clamp
async def test_exposure_clamp(app):
    async with get_client(app) as client:
        # Low clamp
        response_low = await client.post("/api/exposure", json={"exposure_us": 0})
        assert response_low.status_code == 200
        assert response_low.json()["exposure_us"] == 110

        # High clamp
        response_high = await client.post("/api/exposure", json={"exposure_us": 9999999})
        assert response_high.status_code == 200
        assert response_high.json()["exposure_us"] == 3066979


# 11. test_export_current_success
async def test_export_current_success(app):
    app.state.current_frame = {
        "wavelengths": [400.0, 500.0, 600.0],
        "intensities": [10.0, 20.0, 30.0],
        "peaks": [1]
    }
    app.state.current_exposure = 200000
    from spectroo.core.models import Peak
    app.state.current_peaks = [Peak(pixel_index=1, wavelength_nm=500.0, intensity=20.0, prominence=0.0)]

    async with get_client(app) as client:
        # JSON
        response = await client.get("/api/export/current?format=json")
        assert response.status_code == 200
        assert "application/json" in response.headers["content-type"]
        data = response.json()
        assert data["exposure_us"] == 200000
        assert data["intensity"] == [10.0, 20.0, 30.0]
        assert data["peaks"][0]["pixel_index"] == 1

        # CSV
        response_csv = await client.get("/api/export/current?format=csv")
        assert response_csv.status_code == 200
        assert "text/csv" in response_csv.headers["content-type"]
        assert "pixel_index,intensity,wavelength_nm" in response_csv.text


# 12. test_export_current_no_frame_returns_400
async def test_export_current_no_frame_returns_400(app):
    app.state.current_frame = None
    async with get_client(app) as client:
        response = await client.get("/api/export/current")
        assert response.status_code == 400


async def test_integrate_current_success(app):
    app.state.current_frame = {
        "wavelengths": [0.0, 1.0, 2.0],
        "intensities": [0.0, 1.0, 2.0],
        "peaks": []
    }
    async with get_client(app) as client:
        response = await client.post("/api/analyze/integrate", json={"range_min": 0.0, "range_max": 2.0})
        assert response.status_code == 200
        data = response.json()
        assert data["area"] == pytest.approx(2.0)
        assert data["range_min"] == pytest.approx(0.0)
        assert data["range_max"] == pytest.approx(2.0)


async def test_integrate_current_clamps_outside_range(app):
    app.state.current_frame = {
        "wavelengths": [0.0, 1.0, 2.0],
        "intensities": [0.0, 1.0, 2.0],
        "peaks": []
    }
    async with get_client(app) as client:
        response = await client.post("/api/analyze/integrate", json={"range_min": -1.0, "range_max": 3.0})
        assert response.status_code == 200
        data = response.json()
        assert data["area"] == pytest.approx(2.0)
        assert data["range_min"] == pytest.approx(0.0)
        assert data["range_max"] == pytest.approx(2.0)


async def test_integrate_current_rejects_inverted_range(app):
    app.state.current_frame = {
        "wavelengths": [0.0, 1.0, 2.0],
        "intensities": [0.0, 1.0, 2.0],
        "peaks": []
    }
    async with get_client(app) as client:
        response = await client.post("/api/analyze/integrate", json={"range_min": 2.0, "range_max": 1.0})
        assert response.status_code == 400
        assert response.json()["detail"] == "range_min must be less than range_max"


# 13. test_baseline_toggle
async def test_baseline_toggle(app):
    async with get_client(app) as client:
        # Toggle False
        response = await client.post("/api/baseline", json={"enabled": False})
        assert response.status_code == 200
        assert response.json()["baseline_enabled"] is False
        assert app.state.config["dsp"]["baseline_enabled"] is False

        # Toggle True
        response = await client.post("/api/baseline", json={"enabled": True})
        assert response.status_code == 200
        assert response.json()["baseline_enabled"] is True
        assert app.state.config["dsp"]["baseline_enabled"] is True




# 19. test_shutdown_endpoint
@pytest.mark.asyncio
async def test_shutdown_endpoint(app):
    from unittest.mock import patch
    async with get_client(app) as client:
        with patch("spectroo.web.routes.request_shutdown") as mock_sd:
            response = await client.post("/api/shutdown")
        assert response.status_code == 200
        assert response.json() == {"ok": True}
        mock_sd.assert_called_once()


async def test_shutdown_menu_requires_confirmation_and_sets_status_message():
    index_html = Path("spectroo/web/static/index.html").read_text(encoding="utf-8")
    assert 'id="menu-shutdown"' in index_html
    assert 'confirm("Are you sure you want to shut down the system? Unsaved data will be lost.")' in index_html
    assert "fetch('/api/shutdown', { method: 'POST' })" in index_html
    assert 'id="action-status"' in index_html
    assert "actionStatus.innerText = 'Shutting down...';" in index_html


# 20. test_restart_pipeline_idle
@pytest.mark.asyncio
async def test_restart_pipeline_idle(app):
    async with get_client(app) as client:
        response = await client.post("/api/restart")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert app.state.live_active is False
    assert app.state.current_frame is None
    assert app.state.ws_client_connected is False




@pytest.mark.asyncio
async def test_current_frame_empty(app):
    async with get_client(app) as client:
        response = await client.get("/api/current_frame")
    assert response.status_code == 200
    data = response.json()
    assert data["intensities"] == []
    assert data["wavelengths"] == []
    assert data["peaks"] == []


@pytest.mark.asyncio
async def test_current_frame_with_data(app):
    app.state.current_frame = {
        "intensities": [1.0, 2.0, 3.0],
        "wavelengths": [400.0, 450.0, 500.0],
        "peaks": [1]
    }
    async with get_client(app) as client:
        response = await client.get("/api/current_frame")
    assert response.status_code == 200
    data = response.json()
    assert data["intensities"] == [1.0, 2.0, 3.0]
    assert data["peaks"] == [1]


@pytest.mark.asyncio
async def test_dark_capture_without_camera_returns_503(app):
    async with get_client(app) as client:
        response = await client.post("/api/dark/capture")
        assert response.status_code == 503


@pytest.mark.asyncio
async def test_dark_capture_success(app, tmp_path):
    from unittest.mock import patch
    from spectroo.camera.source import MockFrameSource
    # Update config dark_frame_path to use a temp file
    dark_file = tmp_path / "dark_frame.npy"
    app.state.config["storage"]["dark_frame_path"] = str(dark_file)

    async with get_client(app) as client:
        with patch("spectroo.web.routes.PiCameraFrameSource", return_value=MockFrameSource()):
            response = await client.post("/api/dark/capture")
        assert response.status_code == 200
        assert response.json()["status"] == "Dark frame captured and saved successfully"
        assert os.path.exists(dark_file)


@pytest.mark.asyncio
async def test_dark_toggle(app):
    async with get_client(app) as client:
        # Toggle False
        response = await client.post("/api/dark/toggle", json={"enabled": False})
        assert response.status_code == 200
        assert response.json()["dark_subtraction_enabled"] is False
        assert app.state.config["dsp"]["dark_subtraction_enabled"] is False

        # Toggle True
        response = await client.post("/api/dark/toggle", json={"enabled": True})
        assert response.status_code == 200
        assert response.json()["dark_subtraction_enabled"] is True
        assert app.state.config["dsp"]["dark_subtraction_enabled"] is True


@pytest.mark.asyncio
async def test_smoothing_toggle(app):
    async with get_client(app) as client:
        # Toggle False
        response = await client.post("/api/smoothing/toggle", json={"enabled": False})
        assert response.status_code == 200
        assert response.json()["savgol_enabled"] is False
        assert app.state.config["dsp"]["savgol_enabled"] is False

        # Toggle True
        response = await client.post("/api/smoothing/toggle", json={"enabled": True})
        assert response.status_code == 200
        assert response.json()["savgol_enabled"] is True
        assert app.state.config["dsp"]["savgol_enabled"] is True


@pytest.mark.asyncio
async def test_normalize_toggle(app):
    async with get_client(app) as client:
        # Toggle True
        response = await client.post("/api/normalize/toggle", json={"enabled": True})
        assert response.status_code == 200
        assert response.json()["normalize_enabled"] is True
        assert app.state.config["dsp"]["normalize_enabled"] is True

        # Toggle False
        response = await client.post("/api/normalize/toggle", json={"enabled": False})
        assert response.status_code == 200
        assert response.json()["normalize_enabled"] is False
        assert app.state.config["dsp"]["normalize_enabled"] is False


@pytest.mark.asyncio
async def test_normalize_in_status(app):
    async with get_client(app) as client:
        # Default should be False
        response = await client.get("/api/status")
        assert response.status_code == 200
        assert response.json()["normalize_enabled"] is False

        # Enable and verify status reflects it
        await client.post("/api/normalize/toggle", json={"enabled": True})
        response = await client.get("/api/status")
        assert response.status_code == 200
        assert response.json()["normalize_enabled"] is True


@pytest.mark.asyncio
async def test_calibration_endpoints(app, tmp_path):
    state_file = tmp_path / "calibration_state.json"
    app.state.config["storage"]["calibration_state_path"] = str(state_file)
    
    async with get_client(app) as client:
        # 1. GET empty state
        response = await client.get("/api/calibration/state")
        assert response.status_code == 200
        assert response.json() == {"points": [], "fit_result": None, "fit_points": None}

        # 2. POST add point 1
        response = await client.post("/api/calibration/point", json={"pixel_index": 100, "wavelength_nm": 450.0})
        assert response.status_code == 200
        assert response.json() == [{"pixel": 100, "wavelength": 450.0}]

        # Add point 2
        response = await client.post("/api/calibration/point", json={"pixel_index": 200, "wavelength_nm": 550.0})
        assert response.status_code == 200
        assert len(response.json()) == 2

        # 3. DELETE point with invalid index (out of range)
        response = await client.delete("/api/calibration/point/5")
        assert response.status_code == 404

        # DELETE point with valid index
        response = await client.delete("/api/calibration/point/0")
        assert response.status_code == 200
        assert response.json() == [{"pixel": 200, "wavelength": 550.0}]

        # 4. POST undo
        response = await client.post("/api/calibration/undo")
        assert response.status_code == 200
        assert response.json() == []

        # POST undo on empty list
        response = await client.post("/api/calibration/undo")
        assert response.status_code == 200
        assert response.json() == []

        # 5. POST fit with <2 points (should fail with 400)
        await client.post("/api/calibration/point", json={"pixel_index": 100, "wavelength_nm": 450.0})
        response = await client.post("/api/calibration/fit")
        assert response.status_code == 400
        assert "Fewer than 2" in response.json()["detail"]

        # POST fit with duplicate pixels causing fitting error
        await client.post("/api/calibration/point", json={"pixel_index": 100, "wavelength_nm": 550.0})
        response = await client.post("/api/calibration/fit")
        assert response.status_code == 400

        # Clear state
        await client.post("/api/calibration/clear")
        
        # Add 3 valid points for fit
        await client.post("/api/calibration/point", json={"pixel_index": 100, "wavelength_nm": 400.0})
        await client.post("/api/calibration/point", json={"pixel_index": 200, "wavelength_nm": 500.0})
        await client.post("/api/calibration/point", json={"pixel_index": 300, "wavelength_nm": 600.0})

        # POST fit success
        response = await client.post("/api/calibration/fit")
        assert response.status_code == 200
        data = response.json()
        assert "coefficients" in data
        assert data["degree"] == 2
        assert "rms_nm" in data

        # 6. POST apply (success)
        response = await client.post("/api/calibration/apply")
        assert response.status_code == 200
        assert response.json() == {"status": "Calibration applied successfully"}
        assert len(app.state.config["calibration"]["coefficients"]) == 3

        # Add a point to make fit stale
        await client.post("/api/calibration/point", json={"pixel_index": 400, "wavelength_nm": 700.0})
        
        # POST apply with stale points (should fail with 400)
        response = await client.post("/api/calibration/apply")
        assert response.status_code == 400
        assert "stale" in response.json()["detail"]

        # 7. POST clear
        response = await client.post("/api/calibration/clear")
        assert response.status_code == 200
        assert response.json() == {"status": "Calibration cleared"}
        assert app.state.config["calibration"]["coefficients"] == []

        # POST apply without fitting first (should fail with 400)
        response = await client.post("/api/calibration/apply")
        assert response.status_code == 400
        assert "No fit" in response.json()["detail"]


@pytest.mark.asyncio
async def test_calibration_snapshot_endpoints(app, tmp_path):
    import asyncio
    calibrations_dir = tmp_path / "calibrations"
    
    # Write the calibrations_dir to the test's config.toml on disk so it persists across reloads!
    config_path = app.state.config_path
    with open(config_path, "r", encoding="utf-8") as f:
        config_text = f.read()
        
    escaped_dir = str(calibrations_dir).replace('\\', '\\\\')
    config_text += f'\n\n[storage]\ncalibrations_dir = "{escaped_dir}"\n'
    
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(config_text)
        
    # Reload config in memory once
    from spectroo.core.config import load_config
    app.state.config.clear()
    app.state.config.update(load_config(config_path))
    
    # 1. Clear calibration in config so it is empty
    app.state.config.setdefault("calibration", {})["coefficients"] = []
    
    async with get_client(app) as client:
        # Save with no active calibration (should fail with 400)
        response = await client.post("/api/calibration/save", json={"label": "Test Cal"})
        assert response.status_code == 400
        assert "No active calibration" in response.json()["detail"]
        
        # Verify list is empty
        response = await client.get("/api/calibration/list")
        assert response.status_code == 200
        assert response.json() == []

        # Make active calibration in memory
        app.state.config["calibration"]["coefficients"] = [1.0, 2.0, 3.0]
        app.state.config["calibration"]["degree"] = 2
        app.state.config["calibration"]["n_points"] = 3
        
        # Save success
        response = await client.post("/api/calibration/save", json={"label": "First Calibration"})
        assert response.status_code == 200
        data = response.json()
        assert "filename" in data
        assert data["data"]["label"] == "First Calibration"
        assert data["data"]["coefficients"] == [1.0, 2.0, 3.0]
        first_filename = data["filename"]

        # Sleep briefly to ensure distinct timestamps
        await asyncio.sleep(1.1)

        # Save a second one
        response = await client.post("/api/calibration/save", json={"label": "Second Calibration"})
        assert response.status_code == 200
        second_filename = response.json()["filename"]

        # List (entries, newest-first ordering)
        response = await client.get("/api/calibration/list")
        assert response.status_code == 200
        records = response.json()
        assert len(records) == 2
        assert records[0]["filename"] == second_filename
        assert records[0]["label"] == "Second Calibration"
        assert records[1]["filename"] == first_filename
        assert records[1]["label"] == "First Calibration"

        # Load success (confirms config.toml updated)
        app.state.config["calibration"]["coefficients"] = []
        response = await client.post(f"/api/calibration/load/{first_filename}")
        assert response.status_code == 200
        assert response.json() == {"status": "Calibration loaded successfully"}
        assert app.state.config["calibration"]["coefficients"] == [1.0, 2.0, 3.0]

        # Load with invalid/traversal filename (400)
        response = await client.post("/api/calibration/load/subdir/file.json")
        assert response.status_code == 400
        assert "Invalid snapshot filename" in response.json()["detail"]

        response = await client.post("/api/calibration/load/%2e%2e%2ftraversal.json")
        assert response.status_code == 400
        assert "Invalid snapshot filename" in response.json()["detail"]

        # Load with nonexistent filename (404)
        response = await client.post("/api/calibration/load/nonexistent.json")
        assert response.status_code == 404
        assert "Calibration snapshot not found" in response.json()["detail"]

        # Load with malformed JSON content (400)
        malformed_file = calibrations_dir / "malformed.json"
        with open(malformed_file, "w", encoding="utf-8") as f:
            f.write("invalid json {")
        response = await client.post("/api/calibration/load/malformed.json")
        assert response.status_code == 400
        assert "Malformed JSON" in response.json()["detail"]


@pytest.mark.asyncio
async def test_fit_residuals_perfect_linear(app, tmp_path):
    """A perfect 2-point linear fit should return residuals of length 2, all ~0."""
    state_file = tmp_path / "calibration_state.json"
    app.state.config["storage"]["calibration_state_path"] = str(state_file)

    async with get_client(app) as client:
        await client.post("/api/calibration/point", json={"pixel_index": 100, "wavelength_nm": 400.0})
        await client.post("/api/calibration/point", json={"pixel_index": 200, "wavelength_nm": 500.0})

        response = await client.post("/api/calibration/fit")
        assert response.status_code == 200
        data = response.json()

        # residuals key exists and has correct length
        assert "residuals" in data
        assert len(data["residuals"]) == 2

        # Perfect linear fit through 2 points → residuals ≈ 0
        for r in data["residuals"]:
            assert abs(r) < 1e-6


@pytest.mark.asyncio
async def test_fit_residuals_offset_point(app, tmp_path):
    """5 points (4 collinear + 1 offset): degree-3 fit cannot interpolate all 5, so the offset point has a nonzero residual."""
    state_file = tmp_path / "calibration_state.json"
    app.state.config["storage"]["calibration_state_path"] = str(state_file)

    async with get_client(app) as client:
        # 4 perfectly collinear points: wavelength = 2*pixel + 200
        await client.post("/api/calibration/point", json={"pixel_index": 100, "wavelength_nm": 400.0})
        await client.post("/api/calibration/point", json={"pixel_index": 200, "wavelength_nm": 600.0})
        await client.post("/api/calibration/point", json={"pixel_index": 300, "wavelength_nm": 800.0})
        await client.post("/api/calibration/point", json={"pixel_index": 400, "wavelength_nm": 1000.0})
        # 5th point deliberately offset by +50 nm from the line
        await client.post("/api/calibration/point", json={"pixel_index": 500, "wavelength_nm": 1250.0})

        response = await client.post("/api/calibration/fit")
        assert response.status_code == 200
        data = response.json()

        assert "residuals" in data
        assert len(data["residuals"]) == 5

        # With 5 points and degree min(4, 3) = 3, the polynomial cannot
        # pass through all 5 points exactly. The 5th point is offset
        # from the linear trend, so at least one residual should be nonzero.
        max_residual = max(abs(r) for r in data["residuals"])
        assert max_residual > 0.01


@pytest.mark.asyncio
async def test_compare_ratio_no_reference_returns_400(app):
    async with get_client(app) as client:
        app.state.compare_reference = None
        app.state.current_frame = {
            "wavelengths": [400.0, 500.0],
            "intensities": [10.0, 20.0],
            "peaks": []
        }
        response = await client.post("/api/compare/ratio")
        assert response.status_code == 400
        assert "No reference spectrum is set" in response.json()["detail"]


@pytest.mark.asyncio
async def test_compare_reference_from_history(app, tmp_path):
    db_file = tmp_path / "test_history.db"
    app.state.config.setdefault("history", {})["db_path"] = str(db_file)
    
    from spectroo.storage.db import init_db, save_record
    from spectroo.core.models import HistoryRecord
    init_db(str(db_file))
    
    spec = HistoryRecord(
        id=None,
        pixel_indices=[0, 1],
        intensity=[50.0, 100.0],
        wavelengths=[400.0, 500.0],
        exposure_us=20000,
        peaks=[],
        png_path="",
        calibration_rms_at_capture=0.0,
        timestamp="2026-07-11T12:00:00"
    )
    save_record(str(db_file), spec)
    
    async with get_client(app) as client:
        response = await client.post("/api/compare/reference/from-history/1")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["reference"]["intensities"] == [50.0, 100.0]
        assert data["reference"]["wavelengths"] == [400.0, 500.0]
        
        get_res = await client.get("/api/compare/reference")
        assert get_res.status_code == 200
        assert get_res.json()["reference"]["intensities"] == [50.0, 100.0]


@pytest.mark.asyncio
async def test_compare_reference_from_current(app):
    app.state.current_frame = {
        "wavelengths": [450.0, 550.0],
        "intensities": [30.0, 60.0],
        "peaks": []
    }
    async with get_client(app) as client:
        response = await client.post("/api/compare/reference/from-current")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["reference"]["intensities"] == [30.0, 60.0]
        assert data["reference"]["wavelengths"] == [450.0, 550.0]
        assert "Current Frame" in data["reference"]["label"]


@pytest.mark.asyncio
async def test_compare_ratio_success(app):
    app.state.compare_reference = {
        "wavelengths": [400.0, 500.0],
        "intensities": [10.0, 20.0],
        "label": "Ref",
        "timestamp": "2026"
    }
    app.state.current_frame = {
        "wavelengths": [400.0, 500.0],
        "intensities": [25.0, 10.0],
        "peaks": []
    }
    async with get_client(app) as client:
        response = await client.post("/api/compare/ratio")
        assert response.status_code == 200
        data = response.json()
        assert data["wavelengths"] == [400.0, 500.0]
        assert data["ratios"] == [2.5, 0.5]
        assert data["reference_label"] == "Ref"


@pytest.mark.asyncio
async def test_compare_ratio_zero_division_safety(app):
    app.state.compare_reference = {
        "wavelengths": [400.0, 500.0],
        "intensities": [0.0, 1e-7],
        "label": "Ref",
        "timestamp": "2026"
    }
    app.state.current_frame = {
        "wavelengths": [400.0, 500.0],
        "intensities": [25.0, 10.0],
        "peaks": []
    }
    async with get_client(app) as client:
        response = await client.post("/api/compare/ratio")
        assert response.status_code == 200
        data = response.json()
        assert data["ratios"] == [None, None]


@pytest.mark.asyncio
async def test_compare_ratio_mismatched_lengths_returns_400(app):
    app.state.compare_reference = {
        "wavelengths": [400.0, 500.0],
        "intensities": [10.0, 20.0],
        "label": "Ref",
        "timestamp": "2026"
    }
    app.state.current_frame = {
        "wavelengths": [400.0, 500.0, 600.0],
        "intensities": [25.0, 10.0, 5.0],
        "peaks": []
    }
    async with get_client(app) as client:
        response = await client.post("/api/compare/ratio")
        assert response.status_code == 400
        assert "Spectrum length mismatch" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_compare_reference_none(app):
    app.state.compare_reference = None
    async with get_client(app) as client:
        response = await client.get("/api/compare/reference")
        assert response.status_code == 200
        assert response.json()["reference"] is None









