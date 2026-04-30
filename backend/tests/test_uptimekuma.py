import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.app_config import UptimeKumaSourceConfig
from app.services.backends.uptimekuma import UptimeKumaBackend, _parse_metrics

CONFIG = UptimeKumaSourceConfig(
    name="kuma-main",
    type="uptimekuma",
    url="https://status.example.com",
    api_key="uk2_testkey",
)

METRICS_TEXT = """\
# HELP monitor_status Monitor Status
# TYPE monitor_status gauge
monitor_status{monitor_name="Up Service",monitor_type="http",monitor_url="https://up.example.com",monitor_hostname=""} 1
monitor_status{monitor_name="Down Service",monitor_type="http",monitor_url="https://down.example.com",monitor_hostname=""} 0
monitor_status{monitor_name="Pending Service",monitor_type="http",monitor_url="https://pending.example.com",monitor_hostname=""} 2
monitor_status{monitor_name="Maintenance Service",monitor_type="http",monitor_url="https://maint.example.com",monitor_hostname=""} 3
monitor_status{monitor_name="TCP Monitor",monitor_type="tcp",monitor_url="",monitor_hostname="server.example.com"} 0
# HELP monitor_response_time Monitor Response Time
# TYPE monitor_response_time gauge
monitor_response_time{monitor_name="Up Service",monitor_type="http",monitor_url="https://up.example.com",monitor_hostname=""} 148
"""


def _mock_client(text: str) -> AsyncMock:
    response = MagicMock()
    response.text = text
    response.raise_for_status = MagicMock()

    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.get = AsyncMock(return_value=response)
    return client


# --- parser unit tests ---

def test_parse_metrics_skips_comments() -> None:
    parsed = _parse_metrics("# HELP foo Bar\n# TYPE foo gauge\nfoo{a=\"b\"} 1\n")
    assert len(parsed) == 1
    assert parsed[0][0] == "foo"


def test_parse_metrics_extracts_labels() -> None:
    parsed = _parse_metrics('monitor_status{monitor_name="My Monitor",monitor_type="http"} 0\n')
    assert parsed[0][1]["monitor_name"] == "My Monitor"
    assert parsed[0][1]["monitor_type"] == "http"


def test_parse_metrics_extracts_value() -> None:
    parsed = _parse_metrics('monitor_status{monitor_name="X"} 0\n')
    assert parsed[0][2] == 0.0


def test_parse_metrics_skips_lines_without_labels() -> None:
    # Lines without {} are not monitor_status lines we care about
    parsed = _parse_metrics("some_metric 42\n")
    assert len(parsed) == 0


# --- backend integration tests ---

async def test_fetch_checks_skips_up() -> None:
    with patch("app.services.backends.uptimekuma.httpx.AsyncClient", return_value=_mock_client(METRICS_TEXT)):
        results = await UptimeKumaBackend(CONFIG).fetch_checks()
    assert not any(r.name == "Up Service" for r in results)


async def test_fetch_checks_skips_maintenance() -> None:
    with patch("app.services.backends.uptimekuma.httpx.AsyncClient", return_value=_mock_client(METRICS_TEXT)):
        results = await UptimeKumaBackend(CONFIG).fetch_checks()
    assert not any(r.name == "Maintenance Service" for r in results)


async def test_fetch_checks_down_is_critical() -> None:
    with patch("app.services.backends.uptimekuma.httpx.AsyncClient", return_value=_mock_client(METRICS_TEXT)):
        results = await UptimeKumaBackend(CONFIG).fetch_checks()
    down = next(r for r in results if r.name == "Down Service")
    assert down.status == "critical"
    assert down.id == "Down Service"
    assert down.host == "https://down.example.com"
    assert down.source == "kuma-main"


async def test_fetch_checks_pending_is_unknown() -> None:
    with patch("app.services.backends.uptimekuma.httpx.AsyncClient", return_value=_mock_client(METRICS_TEXT)):
        results = await UptimeKumaBackend(CONFIG).fetch_checks()
    pending = next(r for r in results if r.name == "Pending Service")
    assert pending.status == "unknown"


async def test_fetch_checks_tcp_uses_hostname() -> None:
    with patch("app.services.backends.uptimekuma.httpx.AsyncClient", return_value=_mock_client(METRICS_TEXT)):
        results = await UptimeKumaBackend(CONFIG).fetch_checks()
    tcp = next(r for r in results if r.name == "TCP Monitor")
    assert tcp.host == "server.example.com"


async def test_fetch_checks_response_time_lines_ignored() -> None:
    with patch("app.services.backends.uptimekuma.httpx.AsyncClient", return_value=_mock_client(METRICS_TEXT)):
        results = await UptimeKumaBackend(CONFIG).fetch_checks()
    # response_time lines must not produce extra entries
    names = [r.name for r in results]
    assert names.count("Up Service") == 0


async def test_fetch_checks_uses_basic_auth() -> None:
    mock_client_cls = MagicMock(return_value=_mock_client(METRICS_TEXT))
    with patch("app.services.backends.uptimekuma.httpx.AsyncClient", mock_client_cls):
        await UptimeKumaBackend(CONFIG).fetch_checks()
    _, kwargs = mock_client_cls.call_args
    assert kwargs.get("auth") == ("", "uk2_testkey")


async def test_fetch_checks_http_error_propagates() -> None:
    response = MagicMock()
    response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Unauthorized", request=MagicMock(), response=MagicMock()
    )
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.get = AsyncMock(return_value=response)

    with patch("app.services.backends.uptimekuma.httpx.AsyncClient", return_value=client):
        with pytest.raises(httpx.HTTPStatusError):
            await UptimeKumaBackend(CONFIG).fetch_checks()
