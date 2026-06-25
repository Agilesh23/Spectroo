import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from spectroo.web import routes, ws, routes_dev

def create_app(config: dict, config_path: str = None) -> FastAPI:
    app = FastAPI(title="Spectroo", version="3.0")
    app.state.config = config
    app.state.live_active = False
    app.state.ws_client_connected = False
    app.state.current_frame = None   # dict | None: latest frame data

    if config_path is None:
        # Default fallback to root config.toml
        config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "config.toml"))
    app.state.config_path = config_path

    app.include_router(routes.router)
    app.include_router(ws.router)
    app.include_router(routes_dev.router)

    static_dir = os.path.join(os.path.dirname(__file__), "static")
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    return app
