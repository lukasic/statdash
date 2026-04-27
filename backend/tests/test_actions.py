from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.core.app_config import AppConfig, Icinga2SourceConfig, NodepingSourceConfig, SectionConfig, FilterConfig
import app.api.actions as actions_module

ICINGA_SOURCE = Icinga2SourceConfig(
    name="icinga-prod",
    type="icinga2",
    url="https://icinga.example.com:5665",
    username="root",
    password="secret",
    verify_ssl=False,
)

NODEPING_SOURCE = NodepingSourceConfig(
    name="np",
    type="nodeping",
    api_key="key",
)

CONFIG = AppConfig(
    pull_interval=10,
    sources=[ICINGA_SOURCE, NODEPING_SOURCE],
    sections=[SectionConfig(name="All", catchall=True)],
)


async def _login(client: AsyncClient) -> None:
    await client.post("/api/auth/register", json={"email": "u@example.com", "password": "password123"})
    await client.post("/api/auth/jwt/login", data={"username": "u@example.com", "password": "password123"})


async def test_recheck_requires_auth(client: AsyncClient) -> None:
    response = await client.post("/api/actions/recheck", json={"source": "icinga-prod", "check_id": "h!s"})
    assert response.status_code == 401


async def test_recheck_calls_backend(client: AsyncClient) -> None:
    await _login(client)
    with patch.object(actions_module, "get_app_config", return_value=CONFIG):
        with patch("app.api.actions.Icinga2Backend") as MockBackend:
            instance = AsyncMock()
            MockBackend.return_value = instance
            response = await client.post(
                "/api/actions/recheck",
                json={"source": "icinga-prod", "check_id": "server01!check_disk"},
            )
    assert response.status_code == 204
    MockBackend.assert_called_once_with(ICINGA_SOURCE)
    instance.recheck.assert_awaited_once_with("server01", "check_disk")


async def test_recheck_unknown_source_returns_404(client: AsyncClient) -> None:
    await _login(client)
    with patch.object(actions_module, "get_app_config", return_value=CONFIG):
        response = await client.post(
            "/api/actions/recheck",
            json={"source": "does-not-exist", "check_id": "h!s"},
        )
    assert response.status_code == 404


async def test_recheck_non_icinga_source_returns_404(client: AsyncClient) -> None:
    await _login(client)
    with patch.object(actions_module, "get_app_config", return_value=CONFIG):
        response = await client.post(
            "/api/actions/recheck",
            json={"source": "np", "check_id": "check-123"},
        )
    assert response.status_code == 404


async def test_recheck_invalid_check_id_returns_422(client: AsyncClient) -> None:
    await _login(client)
    with patch.object(actions_module, "get_app_config", return_value=CONFIG):
        response = await client.post(
            "/api/actions/recheck",
            json={"source": "icinga-prod", "check_id": "no-exclamation-mark"},
        )
    assert response.status_code == 422


async def test_recheck_check_id_with_multiple_exclamations(client: AsyncClient) -> None:
    """check_id splits only on first ! so service names with ! are handled correctly."""
    await _login(client)
    with patch.object(actions_module, "get_app_config", return_value=CONFIG):
        with patch("app.api.actions.Icinga2Backend") as MockBackend:
            instance = AsyncMock()
            MockBackend.return_value = instance
            await client.post(
                "/api/actions/recheck",
                json={"source": "icinga-prod", "check_id": "host!svc!extra"},
            )
    instance.recheck.assert_awaited_once_with("host", "svc!extra")


async def test_remove_ack_requires_auth(client: AsyncClient) -> None:
    response = await client.post("/api/actions/remove-ack", json={"source": "icinga-prod", "check_id": "h!s"})
    assert response.status_code == 401


async def test_remove_ack_calls_backend(client: AsyncClient) -> None:
    await _login(client)
    with patch.object(actions_module, "get_app_config", return_value=CONFIG):
        with patch("app.api.actions.Icinga2Backend") as MockBackend:
            instance = AsyncMock()
            MockBackend.return_value = instance
            response = await client.post(
                "/api/actions/remove-ack",
                json={"source": "icinga-prod", "check_id": "server01!check_disk"},
            )
    assert response.status_code == 204
    instance.remove_ack.assert_awaited_once_with("server01", "check_disk")


async def test_remove_ack_unknown_source_returns_404(client: AsyncClient) -> None:
    await _login(client)
    with patch.object(actions_module, "get_app_config", return_value=CONFIG):
        response = await client.post(
            "/api/actions/remove-ack",
            json={"source": "does-not-exist", "check_id": "h!s"},
        )
    assert response.status_code == 404


async def test_remove_downtime_requires_auth(client: AsyncClient) -> None:
    response = await client.post("/api/actions/remove-downtime", json={"source": "icinga-prod", "check_id": "h!s"})
    assert response.status_code == 401


async def test_remove_downtime_calls_backend(client: AsyncClient) -> None:
    await _login(client)
    with patch.object(actions_module, "get_app_config", return_value=CONFIG):
        with patch("app.api.actions.Icinga2Backend") as MockBackend:
            instance = AsyncMock()
            MockBackend.return_value = instance
            response = await client.post(
                "/api/actions/remove-downtime",
                json={"source": "icinga-prod", "check_id": "server01!check_disk"},
            )
    assert response.status_code == 204
    instance.remove_downtime.assert_awaited_once_with("server01", "check_disk")


async def test_remove_downtime_unknown_source_returns_404(client: AsyncClient) -> None:
    await _login(client)
    with patch.object(actions_module, "get_app_config", return_value=CONFIG):
        response = await client.post(
            "/api/actions/remove-downtime",
            json={"source": "does-not-exist", "check_id": "h!s"},
        )
    assert response.status_code == 404


async def test_acknowledge_requires_auth(client: AsyncClient) -> None:
    response = await client.post(
        "/api/actions/acknowledge",
        json={"source": "icinga-prod", "check_id": "h!s", "comment": "c"},
    )
    assert response.status_code == 401


async def test_acknowledge_calls_backend(client: AsyncClient) -> None:
    await _login(client)
    with patch.object(actions_module, "get_app_config", return_value=CONFIG):
        with patch("app.api.actions.Icinga2Backend") as MockBackend:
            instance = AsyncMock()
            MockBackend.return_value = instance
            response = await client.post(
                "/api/actions/acknowledge",
                json={
                    "source": "icinga-prod",
                    "check_id": "server01!check_disk",
                    "comment": "Working on it",
                    "expiry_at": "2026-04-28T10:00:00",
                },
            )
    assert response.status_code == 204
    call_kwargs = instance.acknowledge.call_args.kwargs
    assert call_kwargs["host"] == "server01"
    assert call_kwargs["service"] == "check_disk"
    assert call_kwargs["comment"] == "Working on it"
    assert call_kwargs["expiry_at"] is not None


async def test_acknowledge_without_expiry(client: AsyncClient) -> None:
    await _login(client)
    with patch.object(actions_module, "get_app_config", return_value=CONFIG):
        with patch("app.api.actions.Icinga2Backend") as MockBackend:
            instance = AsyncMock()
            MockBackend.return_value = instance
            response = await client.post(
                "/api/actions/acknowledge",
                json={"source": "icinga-prod", "check_id": "server01!check_disk", "comment": "No expiry"},
            )
    assert response.status_code == 204
    assert instance.acknowledge.call_args.kwargs["expiry_at"] is None


async def test_schedule_downtime_requires_auth(client: AsyncClient) -> None:
    response = await client.post(
        "/api/actions/schedule-downtime",
        json={"source": "icinga-prod", "check_id": "h!s", "comment": "c", "expiry_at": "2026-04-28T10:00:00"},
    )
    assert response.status_code == 401


async def test_schedule_downtime_calls_backend(client: AsyncClient) -> None:
    await _login(client)
    with patch.object(actions_module, "get_app_config", return_value=CONFIG):
        with patch("app.api.actions.Icinga2Backend") as MockBackend:
            instance = AsyncMock()
            MockBackend.return_value = instance
            response = await client.post(
                "/api/actions/schedule-downtime",
                json={
                    "source": "icinga-prod",
                    "check_id": "server01!check_disk",
                    "comment": "Planned maintenance",
                    "expiry_at": "2026-04-28T12:00:00",
                },
            )
    assert response.status_code == 204
    call_kwargs = instance.schedule_downtime.call_args.kwargs
    assert call_kwargs["host"] == "server01"
    assert call_kwargs["service"] == "check_disk"
    assert call_kwargs["comment"] == "Planned maintenance"
    assert call_kwargs["duration_seconds"] > 0
