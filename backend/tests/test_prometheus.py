import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.app_config import PrometheusSourceConfig
from app.services.backends.prometheus import PrometheusBackend, _map_severity

CONFIG = PrometheusSourceConfig(
    name="prom-prod",
    type="prometheus",
    alertmanager_url="https://alertmanager.example.com",
)

ACTIVE_ALERT = {
    "fingerprint": "abc123",
    "startsAt": "2024-01-01T10:00:00.000Z",
    "updatedAt": "2024-01-01T10:05:00.000Z",
    "generatorURL": "http://prometheus:9090/graph",
    "labels": {"alertname": "HighCPU", "severity": "critical", "instance": "server1:9100", "job": "node"},
    "annotations": {"description": "CPU above 90%", "summary": "High CPU"},
    "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
}

SILENCED_ALERT = {
    "fingerprint": "def456",
    "startsAt": "2024-01-01T09:00:00.000Z",
    "updatedAt": "2024-01-01T09:01:00.000Z",
    "generatorURL": "http://prometheus:9090/graph",
    "labels": {"alertname": "DiskFull", "severity": "warning", "instance": "server2:9100", "job": "node"},
    "annotations": {"summary": "Disk almost full"},
    "status": {"state": "suppressed", "silencedBy": ["silence-uuid-1"], "inhibitedBy": []},
}

INHIBITED_ALERT = {
    "fingerprint": "ghi789",
    "startsAt": "2024-01-01T08:00:00.000Z",
    "updatedAt": "2024-01-01T08:01:00.000Z",
    "generatorURL": "http://prometheus:9090/graph",
    "labels": {"alertname": "ServiceDown", "severity": "critical", "instance": "server3:9100", "job": "node"},
    "annotations": {"summary": "Service is down"},
    "status": {"state": "suppressed", "silencedBy": [], "inhibitedBy": ["abc123"]},
}

SILENCE = {
    "id": "silence-uuid-1",
    "comment": "Planned maintenance",
    "createdBy": "admin@example.com",
    "startsAt": "2024-01-01T09:00:00.000Z",
    "endsAt": "2024-01-01T11:00:00.000Z",
    "matchers": [{"name": "alertname", "value": "DiskFull", "isRegex": False, "isEqual": True}],
    "status": {"state": "active"},
}


def _mock_client(alerts: list, silences: list) -> AsyncMock:
    def _resp(data):
        r = MagicMock()
        r.json.return_value = data
        r.raise_for_status = MagicMock()
        return r

    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.get = AsyncMock(side_effect=lambda path, **_: _resp(alerts if "alerts" in path else silences))
    client.post = AsyncMock(return_value=_resp({"silenceID": "new-silence-uuid"}))
    client.delete = AsyncMock(return_value=_resp({}))
    return client


# --- severity mapping ---

def test_map_severity_critical() -> None:
    assert _map_severity("critical") == "critical"
    assert _map_severity("page") == "critical"


def test_map_severity_warning() -> None:
    assert _map_severity("warning") == "warning"
    assert _map_severity("warn") == "warning"


def test_map_severity_unknown() -> None:
    assert _map_severity("info") == "unknown"
    assert _map_severity("") == "unknown"


# --- fetch_checks ---

async def test_fetch_checks_active_alert() -> None:
    with patch("app.services.backends.prometheus.httpx.AsyncClient",
               return_value=_mock_client([ACTIVE_ALERT], [])):
        results = await PrometheusBackend(CONFIG).fetch_checks()
    assert len(results) == 1
    r = results[0]
    assert r.id == "abc123"
    assert r.name == "HighCPU"
    assert r.host == "server1:9100"
    assert r.status == "critical"
    assert r.output == "CPU above 90%"
    assert r.since == "2024-01-01T10:00:00.000Z"
    assert r.last_checked == "2024-01-01T10:05:00.000Z"
    assert r.in_downtime is False
    assert r.acknowledged is False
    assert r.source == "prom-prod"


async def test_fetch_checks_silenced_alert_is_in_downtime() -> None:
    with patch("app.services.backends.prometheus.httpx.AsyncClient",
               return_value=_mock_client([SILENCED_ALERT], [SILENCE])):
        results = await PrometheusBackend(CONFIG).fetch_checks()
    r = results[0]
    assert r.in_downtime is True
    assert r.downtime_comment == "Planned maintenance"
    assert r.downtime_expiry == "2024-01-01T11:00:00.000Z"
    assert r.acknowledged is False


async def test_fetch_checks_skips_inhibited_alerts() -> None:
    with patch("app.services.backends.prometheus.httpx.AsyncClient",
               return_value=_mock_client([INHIBITED_ALERT], [])):
        results = await PrometheusBackend(CONFIG).fetch_checks()
    assert len(results) == 0


async def test_fetch_checks_uses_generator_url() -> None:
    with patch("app.services.backends.prometheus.httpx.AsyncClient",
               return_value=_mock_client([ACTIVE_ALERT], [])):
        results = await PrometheusBackend(CONFIG).fetch_checks()
    assert results[0].url == "http://prometheus:9090/graph"


async def test_fetch_checks_host_label_fallback_to_job() -> None:
    cfg = PrometheusSourceConfig(
        name="prom", type="prometheus",
        alertmanager_url="https://am.example.com",
        host_label="node",
    )
    alert = {**ACTIVE_ALERT, "labels": {"alertname": "X", "severity": "warning", "job": "myjob"}}
    with patch("app.services.backends.prometheus.httpx.AsyncClient",
               return_value=_mock_client([alert], [])):
        results = await PrometheusBackend(cfg).fetch_checks()
    assert results[0].host == "myjob"


async def test_fetch_checks_unknown_severity() -> None:
    alert = {**ACTIVE_ALERT, "labels": {**ACTIVE_ALERT["labels"], "severity": "info"}}
    with patch("app.services.backends.prometheus.httpx.AsyncClient",
               return_value=_mock_client([alert], [])):
        results = await PrometheusBackend(CONFIG).fetch_checks()
    assert results[0].status == "unknown"


async def test_fetch_checks_annotation_summary_fallback() -> None:
    alert = {**ACTIVE_ALERT, "annotations": {"summary": "Summary only"}}
    with patch("app.services.backends.prometheus.httpx.AsyncClient",
               return_value=_mock_client([alert], [])):
        results = await PrometheusBackend(CONFIG).fetch_checks()
    assert results[0].output == "Summary only"


# --- create_silence ---

async def test_create_silence_posts_correct_payload() -> None:
    from datetime import datetime, timezone
    ends_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    mock_client = _mock_client([ACTIVE_ALERT], [])

    with patch("app.services.backends.prometheus.httpx.AsyncClient", return_value=mock_client):
        await PrometheusBackend(CONFIG).create_silence(
            fingerprint="abc123", author="admin@example.com",
            comment="Maintenance", ends_at=ends_at,
        )

    payload = mock_client.post.call_args.kwargs["json"]
    assert payload["comment"] == "Maintenance"
    assert payload["createdBy"] == "admin@example.com"
    matchers = {m["name"]: m["value"] for m in payload["matchers"]}
    assert matchers["alertname"] == "HighCPU"
    assert matchers["instance"] == "server1:9100"


async def test_create_silence_raises_if_alert_not_found() -> None:
    from datetime import datetime, timezone
    ends_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    with patch("app.services.backends.prometheus.httpx.AsyncClient",
               return_value=_mock_client([], [])):
        with pytest.raises(ValueError, match="not found"):
            await PrometheusBackend(CONFIG).create_silence(
                fingerprint="nonexistent", author="admin@example.com",
                comment="x", ends_at=ends_at,
            )


# --- remove_silence ---

async def test_remove_silence_expires_all_silence_ids() -> None:
    silence_2 = {**SILENCE, "id": "sid-2"}
    alert_with_two_silences = {
        **SILENCED_ALERT,
        "status": {"state": "suppressed", "silencedBy": ["silence-uuid-1", "sid-2"], "inhibitedBy": []},
    }
    mock_client = _mock_client([alert_with_two_silences], [SILENCE, silence_2])

    with patch("app.services.backends.prometheus.httpx.AsyncClient", return_value=mock_client):
        await PrometheusBackend(CONFIG).remove_silence("def456")

    # Expiration uses POST, not DELETE
    mock_client.delete.assert_not_called()
    assert mock_client.post.call_count == 2
    posted_ids = {call.kwargs["json"]["id"] for call in mock_client.post.call_args_list}
    assert "silence-uuid-1" in posted_ids
    assert "sid-2" in posted_ids


async def test_remove_silence_noop_if_alert_not_found() -> None:
    mock_client = _mock_client([], [])
    with patch("app.services.backends.prometheus.httpx.AsyncClient", return_value=mock_client):
        await PrometheusBackend(CONFIG).remove_silence("nonexistent")
    mock_client.post.assert_not_called()


async def test_remove_silence_raises_on_post_error() -> None:
    err_response = MagicMock()
    err_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Forbidden", request=MagicMock(), response=MagicMock()
    )
    mock_client = _mock_client([SILENCED_ALERT], [SILENCE])
    mock_client.post = AsyncMock(return_value=err_response)

    with patch("app.services.backends.prometheus.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(httpx.HTTPStatusError):
            await PrometheusBackend(CONFIG).remove_silence("def456")


async def test_fetch_checks_http_error_propagates() -> None:
    response = MagicMock()
    response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Unauthorized", request=MagicMock(), response=MagicMock()
    )
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.get = AsyncMock(return_value=response)

    with patch("app.services.backends.prometheus.httpx.AsyncClient", return_value=client):
        with pytest.raises(httpx.HTTPStatusError):
            await PrometheusBackend(CONFIG).fetch_checks()
