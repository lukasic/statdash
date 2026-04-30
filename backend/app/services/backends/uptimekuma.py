import re

import httpx

from app.core.app_config import UptimeKumaSourceConfig
from app.services.backends.base import BaseBackend, CheckResult, render_url

# monitor_status values: 0=DOWN, 1=UP, 2=PENDING, 3=MAINTENANCE
_STATUS_MAP = {0: "critical", 2: "unknown"}

_METRIC_RE = re.compile(r'^(\w+)\{([^}]*)\}\s+([\d.eE+\-]+)')
_LABEL_RE = re.compile(r'(\w+)="([^"]*)"')


def _parse_metrics(text: str) -> list[tuple[str, dict[str, str], float]]:
    results = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = _METRIC_RE.match(line)
        if not m:
            continue
        labels = dict(_LABEL_RE.findall(m.group(2)))
        try:
            value = float(m.group(3))
        except ValueError:
            continue
        results.append((m.group(1), labels, value))
    return results


class UptimeKumaBackend(BaseBackend):
    def __init__(self, config: UptimeKumaSourceConfig) -> None:
        self._config = config

    def _client(self) -> httpx.AsyncClient:
        # Uptime Kuma v2: HTTP Basic auth with empty username, API key as password
        return httpx.AsyncClient(
            base_url=self._config.url.rstrip("/"),
            auth=("", self._config.api_key),
            timeout=30.0,
        )

    async def fetch_checks(self) -> list[CheckResult]:
        async with self._client() as client:
            response = await client.get("/metrics")
            response.raise_for_status()

        results = []
        for metric_name, labels, value in _parse_metrics(response.text):
            if metric_name != "monitor_status":
                continue
            status_code = int(value)
            if status_code not in _STATUS_MAP:
                continue

            name = labels.get("monitor_name", "")
            host = labels.get("monitor_url") or labels.get("monitor_hostname") or ""
            url = render_url(self._config.url_template, check_id=name, check_name=name)

            results.append(CheckResult(
                source=self._config.name,
                id=name,
                name=name,
                host=host,
                status=_STATUS_MAP[status_code],
                output="Monitor is down" if status_code == 0 else "Monitor is pending",
                url=url,
            ))
        return results
