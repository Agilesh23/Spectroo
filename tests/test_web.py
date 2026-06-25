import pytest
import httpx
import tempfile
import os
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


# 14. test_dev_auth_required
async def test_dev_auth_required(app):
    async with get_client(app) as client:
        # No password
        response = await client.get("/api/dev/preview")
        assert response.status_code == 401

        # Wrong password
        response = await client.get("/api/dev/preview?password=wrong")
        assert response.status_code == 401

        # Correct password via query param
        response = await client.get("/api/dev/preview?password=changeme")
        assert response.status_code == 503  # falls to camera not available

        # Correct password via header
        response = await client.get("/api/dev/preview", headers={"X-Dev-Password": "changeme"})
        assert response.status_code == 503


# 15. test_dev_endpoints_live_conflict
async def test_dev_endpoints_live_conflict(app):
    app.state.live_active = True
    async with get_client(app) as client:
        # Preview
        response = await client.get("/api/dev/preview?password=changeme")
        assert response.status_code == 409
        assert "Stop live mode" in response.json()["detail"]

        # Dark
        response = await client.post("/api/dev/dark?password=changeme")
        assert response.status_code == 409
        assert "Stop live mode" in response.json()["detail"]

        # Flat
        response = await client.post("/api/dev/flat?password=changeme")
        assert response.status_code == 409
        assert "Stop live mode" in response.json()["detail"]


# 16. test_dev_endpoints_no_camera_503
async def test_dev_endpoints_no_camera_503(app):
    app.state.live_active = False
    async with get_client(app) as client:
        # Dark
        response = await client.post("/api/dev/dark?password=changeme")
        assert response.status_code == 503

        # Flat
        response = await client.post("/api/dev/flat?password=changeme")
        assert response.status_code == 503


# 17. test_dev_calibrate_success
async def test_dev_calibrate_success(app):
    payload = {
        "pairs": [
            {"pixel": 100, "wavelength": 400.0},
            {"pixel": 500, "wavelength": 500.0},
            {"pixel": 900, "wavelength": 600.0}
        ]
    }
    async with get_client(app) as client:
        response = await client.post("/api/dev/calibrate?password=changeme", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert len(data["coefficients"]) == 3
        assert "rms_nm" in data
        assert "residuals_nm" in data
        assert len(data["residuals_nm"]) == 3
        assert isinstance(data["residuals_nm"][0], float)
        
        # Verify and print exact values
        rms_nm = data["rms_nm"]
        residuals = data["residuals_nm"]
        rms_calc = (sum(r**2 for r in residuals) / len(residuals))**0.5
        print(f"\n[VERIFICATION] rms_nm={rms_nm}")
        print(f"[VERIFICATION] residuals_nm={residuals}")
        print(f"[VERIFICATION] sqrt(mean(residuals**2))={rms_calc}")
        assert abs(rms_nm - rms_calc) < 1e-12
        
        assert app.state.config["calibration"]["coefficients"] == data["coefficients"]


# 18. test_dev_calibrate_insufficient_points
async def test_dev_calibrate_insufficient_points(app):
    payload = {
        "pairs": [
            {"pixel": 100, "wavelength": 400.0}
        ]
    }
    async with get_client(app) as client:
        response = await client.post("/api/dev/calibrate?password=changeme", json=payload)
        assert response.status_code == 400
        assert "Fewer than 2 calibration points" in response.json()["detail"]


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


# 21. test_restart_pipeline_closes_dev_preview
@pytest.mark.asyncio
async def test_restart_pipeline_closes_dev_preview(app):
    from unittest.mock import MagicMock
    mock_source = MagicMock()
    app.state.dev_preview_source = mock_source
    async with get_client(app) as client:
        response = await client.post("/api/restart")
    assert response.status_code == 200
    mock_source.close.assert_called_once()
    assert app.state.dev_preview_source is None


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
async def test_dev_calibrate_returns_residuals(app):
    from unittest.mock import patch, MagicMock
    mock_calib = MagicMock()
    mock_calib.coefficients = [1.0, 0.0]
    mock_calib.degree = 1
    mock_calib.rms_nm = 0.5
    with patch("spectroo.web.routes_dev.fit_calibration",
               return_value=mock_calib):
        async with get_client(app) as client:
            response = await client.post(
                "/api/dev/calibrate",
                json={"pairs": [
                    {"pixel": 100, "wavelength": 450.0},
                    {"pixel": 500, "wavelength": 550.0}
                ]},
                params={"password": "changeme"}
            )
    assert response.status_code == 200
    data = response.json()
    assert "residuals_nm" in data
    assert "rms_nm" in data
    assert len(data["residuals_nm"]) == 2






