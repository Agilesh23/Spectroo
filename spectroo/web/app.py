import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from spectroo.web import routes, ws

def create_app(config: dict) -> FastAPI:
    app = FastAPI(title="Spectroo", version="3.0")
    app.state.config = config
    app.state.live_active = False
    app.state.current_frame = None   # dict | None: latest frame data

    app.include_router(routes.router)
    app.include_router(ws.router)

    static_dir = os.path.join(os.path.dirname(__file__), "static")
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    return app
