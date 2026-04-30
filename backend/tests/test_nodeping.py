import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.app_config import NodepingSourceConfig
from app.services.backends.nodeping import NodepingBackend

CONFIG = NodepingSourceConfig(name="nodeping-main", type="nodeping", api_key="test-key")

CHECKS_RESPONSE = {
    "check-ok": {
        "_id": "check-ok",
        "label": "Up Service",
        "type": "HTTP",
        "state": 1,
        "parameters": {"target": "https://up.example.com"},
    },
    "check-down": {
        "_id": "check-down",
        "label": "Down Service",
        "type": "HTTP",
        "state": 0,
        "firstdown": 1745000000000,  # milliseconds
        "parameters": {"target": "https://down.example.com"},
    },
    "check-unknown": {
        "_id": "check-unknown",
        "label": "Unknown Service",
        "type": "HTTP",
        "state": -1,
        "parameters": {"target": "https://unknown.example.com"},
    },
}


def _mock_client(json_data: dict) -> AsyncMock:
    response = MagicMock()
    response.json.return_value = json_data
    response.raise_for_status = MagicMock()

    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.get = AsyncMock(return_value=response)
    client.post = AsyncMock(return_value=response)
    return client


async def test_fetch_checks_skips_up() -> None:
    with patch("app.services.backends.nodeping.httpx.AsyncClient", return_value=_mock_client(CHECKS_RESPONSE)):
        results = await NodepingBackend(CONFIG).fetch_checks()
    assert not any(r.id == "check-ok" for r in results)


async def test_fetch_checks_critical() -> None:
    with patch("app.services.backends.nodeping.httpx.AsyncClient", return_value=_mock_client(CHECKS_RESPONSE)):
        results = await NodepingBackend(CONFIG).fetch_checks()
    down = next(r for r in results if r.id == "check-down")
    assert down.status == "critical"
    assert down.name == "Down Service"
    assert down.host == "https://down.example.com"
    assert down.source == "nodeping-main"
    assert down.since is not None
    # firstdown 1745000000000 ms = 1745000000 s
    assert "2025" in down.since  # sanity-check the ms→s conversion


async def test_fetch_checks_no_firstdown_gives_none_since() -> None:
    data = {"check-x": {"_id": "check-x", "label": "X", "type": "HTTP", "state": 0,
                         "parameters": {"target": "https://x.com"}}}
    with patch("app.services.backends.nodeping.httpx.AsyncClient", return_value=_mock_client(data)):
        results = await NodepingBackend(CONFIG).fetch_checks()
    assert results[0].since is None


async def test_fetch_checks_firstdown_false_gives_none_since() -> None:
    data = {"check-x": {"_id": "check-x", "label": "X", "type": "HTTP", "state": 0,
                         "firstdown": False,
                         "parameters": {"target": "https://x.com"}}}
    with patch("app.services.backends.nodeping.httpx.AsyncClient", return_value=_mock_client(data)):
        results = await NodepingBackend(CONFIG).fetch_checks()
    assert results[0].since is None


async def test_fetch_checks_unknown() -> None:
    with patch("app.services.backends.nodeping.httpx.AsyncClient", return_value=_mock_client(CHECKS_RESPONSE)):
        results = await NodepingBackend(CONFIG).fetch_checks()
    unknown = next(r for r in results if r.id == "check-unknown")
    assert unknown.status == "unknown"


async def test_fetch_checks_sends_api_key() -> None:
    mock_client = _mock_client(CHECKS_RESPONSE)
    with patch("app.services.backends.nodeping.httpx.AsyncClient", return_value=mock_client):
        await NodepingBackend(CONFIG).fetch_checks()
    assert mock_client.get.call_args.kwargs["params"]["token"] == "test-key"


async def test_fetch_checks_ignores_non_dict_entries() -> None:
    data = {**CHECKS_RESPONSE, "some-metadata-key": "string-value"}
    with patch("app.services.backends.nodeping.httpx.AsyncClient", return_value=_mock_client(data)):
        results = await NodepingBackend(CONFIG).fetch_checks()
    assert all(isinstance(r.id, str) for r in results)


async def test_fetch_checks_missing_parameters() -> None:
    data = {"check-x": {"_id": "check-x", "label": "X", "type": "HTTP", "state": 0}}
    with patch("app.services.backends.nodeping.httpx.AsyncClient", return_value=_mock_client(data)):
        results = await NodepingBackend(CONFIG).fetch_checks()
    assert results[0].host == ""


async def test_create_downtime_payload() -> None:
    mock_client = _mock_client({})
    with patch("app.services.backends.nodeping.httpx.AsyncClient", return_value=mock_client):
        await NodepingBackend(CONFIG).create_downtime(
            check_ids=["check-down", "check-unknown"],
            duration_minutes=60,
            label="Planned maintenance",
        )
    payload = mock_client.post.call_args.kwargs["json"]
    assert payload["token"] == "test-key"
    assert payload["duration"] == 60
    assert payload["enabled"] is True
    assert "check-down" in payload["checklist"]


async def test_fetch_checks_http_error_propagates() -> None:
    response = MagicMock()
    response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Server error", request=MagicMock(), response=MagicMock()
    )
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.get = AsyncMock(return_value=response)

    with patch("app.services.backends.nodeping.httpx.AsyncClient", return_value=client):
        with pytest.raises(httpx.HTTPStatusError):
            await NodepingBackend(CONFIG).fetch_checks()
