import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.app_config import Icinga2SourceConfig
from app.services.backends.icinga2 import Icinga2Backend, _service_filter

CONFIG = Icinga2SourceConfig(
    name="icinga-prod",
    type="icinga2",
    url="https://icinga.example.com:5665",
    username="root",
    password="secret",
    verify_ssl=False,
)

SERVICES_RESPONSE = {
    "results": [
        {
            "attrs": {
                "name": "check_disk",
                "display_name": "Disk Usage",
                "host_name": "server01",
                "state": 1,
                "last_state_change": 1745000000.0,
                "last_check": 1745000060.0,
                "last_check_result": {"output": "DISK WARNING - free space: / 1234 MB (12%)"},
            }
        },
        {
            "attrs": {
                "name": "check_load",
                "display_name": "Load Average",
                "host_name": "server02",
                "state": 2,
                "last_check_result": {"output": "CRITICAL - load average: 14.5"},
            }
        },
        {
            "attrs": {
                "name": "check_users",
                "display_name": "Users",
                "host_name": "server01",
                "state": 3,
                "last_check_result": {"output": "UNKNOWN"},
            }
        },
        {
            "attrs": {
                "name": "check_ping",
                "display_name": "Ping",
                "host_name": "server01",
                "state": 0,
                "last_check_result": {"output": "OK"},
            }
        },
    ]
}


_EMPTY = {"results": []}


def _mock_client(
    services: dict,
    comments: dict | None = None,
    downtimes: dict | None = None,
) -> AsyncMock:
    data = {
        "/services": services,
        "/comments": comments if comments is not None else _EMPTY,
        "/downtimes": downtimes if downtimes is not None else _EMPTY,
    }

    def _respond(url: str, **_kwargs: object) -> MagicMock:
        for pattern, payload in data.items():
            if pattern in url:
                resp = MagicMock()
                resp.json.return_value = payload
                resp.raise_for_status = MagicMock()
                return resp
        # action endpoints and other URLs → generic OK response
        resp = MagicMock()
        resp.json.return_value = {}
        resp.raise_for_status = MagicMock()
        return resp

    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.get = AsyncMock()
    client.post = AsyncMock(side_effect=_respond)
    return client


def _services_post_call(mock_client: AsyncMock) -> object:
    return next(
        c for c in mock_client.post.call_args_list if "/services" in c.args[0]
    )


async def test_fetch_checks_skips_ok() -> None:
    with patch.object(Icinga2Backend, "_client", return_value=_mock_client(SERVICES_RESPONSE)):
        results = await Icinga2Backend(CONFIG).fetch_checks()
    assert not any(r.id == "server01!check_ping" for r in results)


async def test_fetch_checks_warning() -> None:
    with patch.object(Icinga2Backend, "_client", return_value=_mock_client(SERVICES_RESPONSE)):
        results = await Icinga2Backend(CONFIG).fetch_checks()
    disk = next(r for r in results if r.id == "server01!check_disk")
    assert disk.status == "warning"
    assert disk.name == "Disk Usage"
    assert disk.host == "server01"
    assert disk.source == "icinga-prod"
    assert "DISK WARNING" in disk.output
    assert disk.since is not None
    assert "2025" in disk.since or "2026" in disk.since  # sanity check on ISO format
    assert disk.last_checked is not None
    assert "2025" in disk.last_checked or "2026" in disk.last_checked


async def test_fetch_checks_no_last_check_gives_none_last_checked() -> None:
    with patch.object(Icinga2Backend, "_client", return_value=_mock_client(SERVICES_RESPONSE)):
        results = await Icinga2Backend(CONFIG).fetch_checks()
    load = next(r for r in results if r.id == "server02!check_load")
    assert load.last_checked is None


async def test_fetch_checks_no_state_change_gives_none_since() -> None:
    data = {"results": [{"attrs": {"name": "svc", "host_name": "h", "state": 2}}]}
    with patch.object(Icinga2Backend, "_client", return_value=_mock_client(data)):
        results = await Icinga2Backend(CONFIG).fetch_checks()
    assert results[0].since is None


async def test_fetch_checks_critical() -> None:
    with patch.object(Icinga2Backend, "_client", return_value=_mock_client(SERVICES_RESPONSE)):
        results = await Icinga2Backend(CONFIG).fetch_checks()
    load = next(r for r in results if r.id == "server02!check_load")
    assert load.status == "critical"


async def test_fetch_checks_unknown() -> None:
    with patch.object(Icinga2Backend, "_client", return_value=_mock_client(SERVICES_RESPONSE)):
        results = await Icinga2Backend(CONFIG).fetch_checks()
    users = next(r for r in results if r.id == "server01!check_users")
    assert users.status == "unknown"


async def test_fetch_checks_returns_three_problems() -> None:
    with patch.object(Icinga2Backend, "_client", return_value=_mock_client(SERVICES_RESPONSE)):
        results = await Icinga2Backend(CONFIG).fetch_checks()
    assert len(results) == 3


async def test_fetch_checks_missing_last_check_result() -> None:
    data = {"results": [{"attrs": {"name": "svc", "host_name": "h", "state": 2}}]}
    with patch.object(Icinga2Backend, "_client", return_value=_mock_client(data)):
        results = await Icinga2Backend(CONFIG).fetch_checks()
    assert results[0].output == ""


async def test_recheck_sends_correct_payload() -> None:
    mock_client = _mock_client({})
    with patch.object(Icinga2Backend, "_client", return_value=mock_client):
        await Icinga2Backend(CONFIG).recheck("server01", "check_disk")
    payload = mock_client.post.call_args.kwargs["json"]
    assert payload["type"] == "Service"
    assert 'host.name=="server01"' in payload["filter"]
    assert 'service.name=="check_disk"' in payload["filter"]
    assert payload["force_check"] is True


async def test_acknowledge_sends_correct_payload() -> None:
    mock_client = _mock_client({})
    with patch.object(Icinga2Backend, "_client", return_value=mock_client):
        await Icinga2Backend(CONFIG).acknowledge(
            host="server01",
            service="check_disk",
            author="admin",
            comment="Looking into it",
            sticky=True,
        )
    payload = mock_client.post.call_args.kwargs["json"]
    assert payload["author"] == "admin"
    assert payload["comment"] == "Looking into it"
    assert payload["sticky"] is True
    assert payload["notify"] is True


async def test_schedule_downtime_sends_correct_payload() -> None:
    mock_client = _mock_client({})
    with patch.object(Icinga2Backend, "_client", return_value=mock_client):
        await Icinga2Backend(CONFIG).schedule_downtime(
            host="server01",
            service="check_disk",
            author="admin",
            comment="Planned maintenance",
            duration_seconds=3600,
        )
    payload = mock_client.post.call_args.kwargs["json"]
    assert payload["duration"] == 3600
    assert payload["fixed"] is True
    assert payload["end_time"] > payload["start_time"]


async def test_fetch_checks_http_error_propagates() -> None:
    response = MagicMock()
    response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Unauthorized", request=MagicMock(), response=MagicMock()
    )
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.post = AsyncMock(return_value=response)

    with patch.object(Icinga2Backend, "_client", return_value=client):
        with pytest.raises(httpx.HTTPStatusError):
            await Icinga2Backend(CONFIG).fetch_checks()


def test_service_filter_format() -> None:
    f = _service_filter("server01", "check_disk")
    assert f == 'host.name=="server01"&&service.name=="check_disk"'


async def test_fetch_checks_appends_custom_filter() -> None:
    config = Icinga2SourceConfig(
        **{**CONFIG.model_dump(), "filter": '"Managed by STA Admins" in host.groups'},
    )
    mock_client = _mock_client(SERVICES_RESPONSE)
    with patch.object(Icinga2Backend, "_client", return_value=mock_client):
        await Icinga2Backend(config).fetch_checks()
    sent_filter = _services_post_call(mock_client).kwargs["json"]["filter"]
    assert sent_filter.startswith("service.state!=0&&")
    assert '"Managed by STA Admins" in host.groups' in sent_filter


async def test_fetch_checks_no_custom_filter() -> None:
    mock_client = _mock_client(SERVICES_RESPONSE)
    with patch.object(Icinga2Backend, "_client", return_value=mock_client):
        await Icinga2Backend(CONFIG).fetch_checks()
    sent_filter = _services_post_call(mock_client).kwargs["json"]["filter"]
    assert sent_filter == "service.state!=0"


async def test_fetch_checks_uses_method_override_header() -> None:
    mock_client = _mock_client(SERVICES_RESPONSE)
    with patch.object(Icinga2Backend, "_client", return_value=mock_client):
        await Icinga2Backend(CONFIG).fetch_checks()
    headers = _services_post_call(mock_client).kwargs["headers"]
    assert headers.get("X-HTTP-Method-Override") == "GET"


async def test_fetch_checks_acknowledged_flag() -> None:
    data = {"results": [{"attrs": {
        "name": "svc", "host_name": "h", "state": 1,
        "acknowledgement": 1, "downtime_depth": 0,
    }}]}
    with patch.object(Icinga2Backend, "_client", return_value=_mock_client(data)):
        results = await Icinga2Backend(CONFIG).fetch_checks()
    assert results[0].acknowledged is True
    assert results[0].in_downtime is False


async def test_fetch_checks_in_downtime_flag() -> None:
    data = {"results": [{"attrs": {
        "name": "svc", "host_name": "h", "state": 1,
        "acknowledgement": 0, "downtime_depth": 2,
    }}]}
    with patch.object(Icinga2Backend, "_client", return_value=_mock_client(data)):
        results = await Icinga2Backend(CONFIG).fetch_checks()
    assert results[0].in_downtime is True
    assert results[0].acknowledged is False


async def test_fetch_checks_defaults_not_acknowledged_not_in_downtime() -> None:
    with patch.object(Icinga2Backend, "_client", return_value=_mock_client(SERVICES_RESPONSE)):
        results = await Icinga2Backend(CONFIG).fetch_checks()
    assert all(not r.acknowledged for r in results)
    assert all(not r.in_downtime for r in results)


async def test_fetch_checks_ack_comment_populated() -> None:
    services = {"results": [{"attrs": {
        "name": "check_disk", "host_name": "server01", "state": 1,
        "acknowledgement": 1,
    }}]}
    comments = {"results": [{"attrs": {
        "entry_type": 4,
        "host_name": "server01", "service_name": "check_disk",
        "text": "Looking into it",
    }}]}
    with patch.object(Icinga2Backend, "_client", return_value=_mock_client(services, comments=comments)):
        results = await Icinga2Backend(CONFIG).fetch_checks()
    assert results[0].ack_comment == "Looking into it"


async def test_fetch_checks_ack_comment_none_when_not_acknowledged() -> None:
    services = {"results": [{"attrs": {
        "name": "check_disk", "host_name": "server01", "state": 1,
        "acknowledgement": 0,
    }}]}
    comments = {"results": [{"attrs": {
        "entry_type": 4,
        "host_name": "server01", "service_name": "check_disk",
        "text": "Some comment",
    }}]}
    with patch.object(Icinga2Backend, "_client", return_value=_mock_client(services, comments=comments)):
        results = await Icinga2Backend(CONFIG).fetch_checks()
    assert results[0].ack_comment is None


async def test_fetch_checks_ack_expiry_populated() -> None:
    services = {"results": [{"attrs": {
        "name": "svc", "host_name": "h", "state": 1,
        "acknowledgement": 1,
        "acknowledgement_expiry": 1745100000.0,
    }}]}
    with patch.object(Icinga2Backend, "_client", return_value=_mock_client(services)):
        results = await Icinga2Backend(CONFIG).fetch_checks()
    assert results[0].ack_expiry is not None
    assert "2025" in results[0].ack_expiry or "2026" in results[0].ack_expiry


async def test_fetch_checks_ack_expiry_none_when_zero() -> None:
    services = {"results": [{"attrs": {
        "name": "svc", "host_name": "h", "state": 1,
        "acknowledgement": 1,
        "acknowledgement_expiry": 0,
    }}]}
    with patch.object(Icinga2Backend, "_client", return_value=_mock_client(services)):
        results = await Icinga2Backend(CONFIG).fetch_checks()
    assert results[0].ack_expiry is None


async def test_fetch_checks_downtime_comment_and_expiry() -> None:
    services = {"results": [{"attrs": {
        "name": "check_disk", "host_name": "server01", "state": 1,
        "downtime_depth": 1,
    }}]}
    downtimes = {"results": [{"attrs": {
        "host_name": "server01", "service_name": "check_disk",
        "comment": "Planned maintenance window",
        "end_time": 1745100000.0,
    }}]}
    with patch.object(Icinga2Backend, "_client", return_value=_mock_client(services, downtimes=downtimes)):
        results = await Icinga2Backend(CONFIG).fetch_checks()
    assert results[0].downtime_comment == "Planned maintenance window"
    assert results[0].downtime_expiry is not None


async def test_fetch_checks_non_ack_comments_ignored() -> None:
    services = {"results": [{"attrs": {
        "name": "svc", "host_name": "h", "state": 1, "acknowledgement": 1,
    }}]}
    comments = {"results": [{"attrs": {
        "entry_type": 1,  # user comment, not acknowledgement
        "host_name": "h", "service_name": "svc", "text": "User comment",
    }}]}
    with patch.object(Icinga2Backend, "_client", return_value=_mock_client(services, comments=comments)):
        results = await Icinga2Backend(CONFIG).fetch_checks()
    assert results[0].ack_comment is None
