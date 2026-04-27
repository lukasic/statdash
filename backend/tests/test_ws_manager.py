import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from starlette.websockets import WebSocketState

from app.services.ws_manager import WebSocketManager


def _make_ws(connected: bool = True) -> MagicMock:
    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.client_state = WebSocketState.CONNECTED if connected else WebSocketState.DISCONNECTED
    return ws


async def test_connect_accepts_and_registers() -> None:
    manager = WebSocketManager()
    ws = _make_ws()
    await manager.connect(ws)
    ws.accept.assert_called_once()
    assert manager.connection_count == 1


async def test_disconnect_removes_client() -> None:
    manager = WebSocketManager()
    ws = _make_ws()
    await manager.connect(ws)
    manager.disconnect(ws)
    assert manager.connection_count == 0


async def test_broadcast_sends_to_all_connected() -> None:
    manager = WebSocketManager()
    ws1, ws2 = _make_ws(), _make_ws()
    await manager.connect(ws1)
    await manager.connect(ws2)

    await manager.broadcast({"sections": [], "sources": []})

    ws1.send_json.assert_called_once()
    ws2.send_json.assert_called_once()


async def test_broadcast_skips_disconnected() -> None:
    manager = WebSocketManager()
    ws = _make_ws(connected=False)
    await manager.connect(ws)

    await manager.broadcast({"sections": [], "sources": []})

    ws.send_json.assert_not_called()
    assert manager.connection_count == 0


async def test_broadcast_removes_failed_connection() -> None:
    manager = WebSocketManager()
    ws = _make_ws()
    ws.send_json = AsyncMock(side_effect=RuntimeError("broken pipe"))
    await manager.connect(ws)

    await manager.broadcast({"sections": [], "sources": []})

    assert manager.connection_count == 0


async def test_disconnect_nonexistent_is_safe() -> None:
    manager = WebSocketManager()
    ws = _make_ws()
    manager.disconnect(ws)
    assert manager.connection_count == 0
