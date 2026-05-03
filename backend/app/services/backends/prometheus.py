import asyncio
from datetime import datetime, timedelta, timezone
from typing import Literal

import httpx

from app.core.app_config import PrometheusSourceConfig
from app.services.backends.base import BaseBackend, CheckResult, render_url

_SEVERITY_MAP: dict[str, Literal["warning", "critical", "unknown"]] = {
    "critical": "critical",
    "page": "critical",
    "warning": "warning",
    "warn": "warning",
}


def _map_severity(severity: str) -> Literal["warning", "critical", "unknown"]:
    return _SEVERITY_MAP.get(severity.lower(), "unknown")


class PrometheusBackend(BaseBackend):
    def __init__(self, config: PrometheusSourceConfig) -> None:
        self._config = config

    def _client(self) -> httpx.AsyncClient:
        auth = (self._config.username, self._config.password) if self._config.username else None
        return httpx.AsyncClient(
            base_url=self._config.alertmanager_url.rstrip("/"),
            auth=auth,
            verify=self._config.verify_ssl,
            timeout=30.0,
        )

    async def fetch_checks(self) -> list[CheckResult]:
        async with self._client() as client:
            alerts_resp, silences_resp = await asyncio.gather(
                client.get("/api/v2/alerts"),
                client.get("/api/v2/silences"),
            )
            alerts_resp.raise_for_status()
            silences_resp.raise_for_status()
            alerts: list[dict] = alerts_resp.json()
            silences: dict[str, dict] = {s["id"]: s for s in silences_resp.json()}

        results = []
        for alert in alerts:
            state: str = alert["status"]["state"]
            silenced_by: list[str] = alert["status"]["silencedBy"]

            # Skip inhibited-only suppressed alerts
            if state == "suppressed" and not silenced_by:
                continue

            in_downtime = bool(silenced_by)
            downtime_comment: str | None = None
            downtime_expiry: str | None = None
            if silenced_by:
                silence = silences.get(silenced_by[0])
                if silence:
                    downtime_comment = silence.get("comment")
                    downtime_expiry = silence.get("endsAt")

            labels: dict[str, str] = alert["labels"]
            annotations: dict[str, str] = alert["annotations"]

            name = labels.get("alertname", "")
            host = labels.get(self._config.host_label) or labels.get("job") or ""
            status = _map_severity(labels.get("severity", ""))
            output = annotations.get("description") or annotations.get("summary") or ""
            url = alert.get("generatorURL") or render_url(
                self._config.url_template, check_id=alert["fingerprint"], check_name=name,
            )

            results.append(CheckResult(
                source=self._config.name,
                id=alert["fingerprint"],
                name=name,
                host=host,
                status=status,
                output=output,
                since=alert.get("startsAt"),
                last_checked=alert.get("updatedAt"),
                acknowledged=False,
                in_downtime=in_downtime,
                downtime_comment=downtime_comment,
                downtime_expiry=downtime_expiry,
                url=url,
            ))
        return results

    async def create_silence(self, fingerprint: str, author: str, comment: str, ends_at: datetime) -> None:
        async with self._client() as client:
            alerts_resp = await client.get("/api/v2/alerts")
            alerts_resp.raise_for_status()
            alerts: list[dict] = alerts_resp.json()

        alert = next((a for a in alerts if a["fingerprint"] == fingerprint), None)
        if alert is None:
            raise ValueError(f"Alert {fingerprint} not found — it may have already resolved")

        matchers = [
            {"name": k, "value": v, "isRegex": False, "isEqual": True}
            for k, v in alert["labels"].items()
        ]
        now = datetime.now(timezone.utc)

        async with self._client() as client:
            resp = await client.post(
                "/api/v2/silences",
                json={
                    "matchers": matchers,
                    "startsAt": now.isoformat(),
                    "endsAt": ends_at.isoformat(),
                    "comment": comment,
                    "createdBy": author,
                },
            )
            resp.raise_for_status()

    async def remove_silence(self, fingerprint: str) -> None:
        async with self._client() as client:
            alerts_resp, silences_resp = await asyncio.gather(
                client.get("/api/v2/alerts"),
                client.get("/api/v2/silences"),
            )
            alerts_resp.raise_for_status()
            silences_resp.raise_for_status()
            alerts: list[dict] = alerts_resp.json()
            silences_by_id: dict[str, dict] = {s["id"]: s for s in silences_resp.json()}

        alert = next((a for a in alerts if a["fingerprint"] == fingerprint), None)
        if alert is None:
            return

        silence_ids: list[str] = alert["status"]["silencedBy"]
        if not silence_ids:
            return

        # Expire each silence by re-POSTing with endsAt 1 s in the future.
        # DELETE is often blocked by proxies; POST is universally allowed.
        # Alertmanager rejects endsAt <= now, so we use now + 1 s.
        now = (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()
        payloads = [
            {**silences_by_id[sid], "endsAt": now}
            for sid in silence_ids
            if sid in silences_by_id
        ]
        if not payloads:
            return

        async with self._client() as client:
            responses = await asyncio.gather(*[
                client.post("/api/v2/silences", json=payload)
                for payload in payloads
            ])
        for resp in responses:
            resp.raise_for_status()
