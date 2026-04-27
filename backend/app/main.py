from contextlib import asynccontextmanager
from typing import AsyncGenerator

import httpx
from fastapi import FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.websockets import WebSocketDisconnect

from app.api.router import api_router
from app.core.app_config import get_app_config, load_app_config
from app.core.cache import valkey
from app.core.config import settings
from app.core.database import create_db_and_tables
from app.services.dashboard import get_dashboard_data
from app.services.poller import Poller
from app.services.ws_manager import WebSocketManager

ws_manager = WebSocketManager()


async def _broadcast() -> None:
    if ws_manager.connection_count == 0:
        return
    data = await get_dashboard_data(get_app_config(), valkey)
    await ws_manager.broadcast(data)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    load_app_config()
    await create_db_and_tables()
    poller = Poller(get_app_config(), valkey, on_update=_broadcast)
    await poller.start()
    yield
    await poller.stop()


app = FastAPI(title="StatDash", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")


@app.exception_handler(httpx.HTTPStatusError)
async def httpx_status_error_handler(request: Request, exc: httpx.HTTPStatusError) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={"detail": f"Backend returned {exc.response.status_code}: {exc.response.text[:300]}"},
    )


@app.exception_handler(httpx.RequestError)
async def httpx_request_error_handler(request: Request, exc: httpx.RequestError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": f"Could not reach backend: {exc}"},
    )


@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await ws_manager.connect(websocket)
    try:
        data = await get_dashboard_data(get_app_config(), valkey)
        await websocket.send_json(data)
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(websocket)
