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
def app():
    # Fresh app instance
    application = create_app(MINIMAL_CONFIG)
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


# 8. test_history_initially_empty
async def test_history_initially_empty(app):
    async with get_client(app) as client:
        response = await client.get("/api/history")
        assert response.status_code == 200
        assert response.json() == []


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
