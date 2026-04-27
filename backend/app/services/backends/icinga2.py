import asyncio
from datetime import datetime, timedelta, timezone
from typing import Literal

import httpx

from app.core.app_config import Icinga2SourceConfig
from app.services.backends.base import BaseBackend, CheckResult, render_url

_STATE_MAP: dict[int, Literal["warning", "critical", "unknown"]] = {
    1: "warning",
    2: "critical",
}


class Icinga2Backend(BaseBackend):
    def __init__(self, config: Icinga2SourceConfig) -> None:
        self._config = config

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            verify=self._config.verify_ssl,
            auth=(self._config.username, self._config.password),
            headers={"Accept": "application/json"},
            timeout=30.0,
        )

    def _build_filter(self) -> str:
        base = "service.state!=0"
        if self._config.filter:
            return f"{base}&&{self._config.filter}"
        return base

    async def fetch_checks(self) -> list[CheckResult]:
        async with self._client() as client:
            services_resp, comments_resp, downtimes_resp = await asyncio.gather(
                client.post(
                    f"{self._config.url}/v1/objects/services",
                    headers={"X-HTTP-Method-Override": "GET"},
                    json={"filter": self._build_filter()},
                ),
                client.post(
                    f"{self._config.url}/v1/objects/comments",
                    headers={"X-HTTP-Method-Override": "GET"},
                    json={},
                ),
                client.post(
                    f"{self._config.url}/v1/objects/downtimes",
                    headers={"X-HTTP-Method-Override": "GET"},
                    json={},
                ),
            )
            services_resp.raise_for_status()
            comments_resp.raise_for_status()
            downtimes_resp.raise_for_status()

        # ack comments: entry_type 4 = acknowledgement
        ack_comments: dict[str, str] = {}
        for item in comments_resp.json().get("results", []):
            attrs = item.get("attrs", {})
            if attrs.get("entry_type") != 4:
                continue
            svc = attrs.get("service_name", "")
            if not svc:
                continue
            ack_comments[f"{attrs.get('host_name', '')}!{svc}"] = attrs.get("text", "")

        # downtime comments + expiry
        downtime_info: dict[str, tuple[str, str | None]] = {}
        for item in downtimes_resp.json().get("results", []):
            attrs = item.get("attrs", {})
            svc = attrs.get("service_name", "")
            if not svc:
                continue
            key = f"{attrs.get('host_name', '')}!{svc}"
            downtime_info[key] = (
                attrs.get("comment", ""),
                _unix_to_iso(attrs.get("end_time")),
            )

        results = []
        for item in services_resp.json().get("results", []):
            attrs = item.get("attrs", {})
            state = int(attrs.get("state", 0))
            if state == 0:
                continue
            host = attrs.get("host_name", "")
            svc_name = attrs.get("name", "")
            key = f"{host}!{svc_name}"
            name = attrs.get("display_name") or svc_name
            output = (attrs.get("last_check_result") or {}).get("output", "")
            since = _unix_to_iso(attrs.get("last_state_change"))
            last_checked = _unix_to_iso(attrs.get("last_check"))
            acknowledged = int(attrs.get("acknowledgement", 0)) > 0
            in_downtime = int(attrs.get("downtime_depth", 0)) > 0

            ack_comment = ack_comments.get(key) if acknowledged else None
            ack_expiry_raw = attrs.get("acknowledgement_expiry") or 0
            ack_expiry = _unix_to_iso(ack_expiry_raw) if ack_expiry_raw > 0 else None

            dt = downtime_info.get(key) if in_downtime else None
            downtime_comment = dt[0] if dt else None
            downtime_expiry = dt[1] if dt else None

            url = render_url(self._config.url_template, host_name=host, check_name=svc_name)
            results.append(
                CheckResult(
                    source=self._config.name,
                    id=key,
                    name=name,
                    host=host,
                    status=_STATE_MAP.get(state, "unknown"),
                    output=output,
                    since=since,
                    last_checked=last_checked,
                    acknowledged=acknowledged,
                    in_downtime=in_downtime,
                    ack_comment=ack_comment,
                    ack_expiry=ack_expiry,
                    downtime_comment=downtime_comment,
                    downtime_expiry=downtime_expiry,
                    url=url,
                )
            )
        return results

    async def recheck(self, host: str, service: str) -> None:
        async with self._client() as client:
            response = await client.post(
                f"{self._config.url}/v1/actions/reschedule-check",
                json={
                    "type": "Service",
                    "filter": _service_filter(host, service),
                    "force_check": True,
                },
            )
            response.raise_for_status()

    async def acknowledge(
        self,
        host: str,
        service: str,
        author: str,
        comment: str,
        expiry_at: datetime | None = None,
        sticky: bool = False,
        notify: bool = True,
    ) -> None:
        body: dict = {
            "type": "Service",
            "filter": _service_filter(host, service),
            "author": author,
            "comment": comment,
            "sticky": sticky,
            "notify": notify,
            "persistent": False,
        }
        if expiry_at is not None:
            body["expiry"] = expiry_at.timestamp()
        async with self._client() as client:
            response = await client.post(
                f"{self._config.url}/v1/actions/acknowledge-problem",
                json=body,
            )
            response.raise_for_status()

    async def remove_ack(self, host: str, service: str) -> None:
        async with self._client() as client:
            response = await client.post(
                f"{self._config.url}/v1/actions/remove-acknowledgement",
                json={
                    "type": "Service",
                    "filter": _service_filter(host, service),
                },
            )
            response.raise_for_status()

    async def remove_downtime(self, host: str, service: str) -> None:
        async with self._client() as client:
            response = await client.post(
                f"{self._config.url}/v1/actions/remove-downtime",
                json={
                    "type": "Service",
                    "filter": _service_filter(host, service),
                },
            )
            response.raise_for_status()

    async def schedule_downtime(
        self,
        host: str,
        service: str,
        author: str,
        comment: str,
        duration_seconds: int,
    ) -> None:
        now = datetime.now(timezone.utc)
        end = now + timedelta(seconds=duration_seconds)
        async with self._client() as client:
            response = await client.post(
                f"{self._config.url}/v1/actions/schedule-downtime",
                json={
                    "type": "Service",
                    "filter": _service_filter(host, service),
                    "author": author,
                    "comment": comment,
                    "start_time": now.timestamp(),
                    "end_time": end.timestamp(),
                    "duration": duration_seconds,
                    "fixed": True,
                },
            )
            response.raise_for_status()


def _service_filter(host: str, service: str) -> str:
    return f'host.name=="{host}"&&service.name=="{service}"'


def _unix_to_iso(ts: float | None) -> str | None:
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
