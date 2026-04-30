from datetime import datetime, timezone

import httpx

from app.core.app_config import NodepingSourceConfig
from app.services.backends.base import BaseBackend, CheckResult, render_url


class NodepingBackend(BaseBackend):
    BASE_URL = "https://api.nodeping.com/api/1"

    def __init__(self, config: NodepingSourceConfig) -> None:
        self._config = config

    async def fetch_checks(self) -> list[CheckResult]:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/checks",
                params={"token": self._config.api_key},
                timeout=30.0,
            )
            response.raise_for_status()
            data: dict = response.json()

        results = []
        for check_id, check in data.items():
            if not isinstance(check, dict):
                continue
            state = check.get("state", 1)
            if state == 1:
                continue
            # firstdown is milliseconds since epoch; False when check is passing
            firstdown = check.get("firstdown")
            since = (
                datetime.fromtimestamp(firstdown / 1000, tz=timezone.utc).isoformat()
                if firstdown and firstdown is not False
                else None
            )
            label = check.get("label", check_id)
            url = render_url(self._config.url_template, check_id=check_id, check_name=label)
            results.append(
                CheckResult(
                    source=self._config.name,
                    id=check_id,
                    name=label,
                    host=check.get("parameters", {}).get("target", ""),
                    status="critical" if state == 0 else "unknown",
                    output=_describe(check),
                    since=since,
                    url=url,
                )
            )
        return results

    async def create_downtime(
        self,
        check_ids: list[str],
        duration_minutes: int,
        label: str,
    ) -> None:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.BASE_URL}/maintenance",
                json={
                    "token": self._config.api_key,
                    "label": label,
                    "enabled": True,
                    "duration": duration_minutes,
                    "checklist": check_ids,
                },
                timeout=30.0,
            )
            response.raise_for_status()


def _describe(check: dict) -> str:
    check_type = check.get("type", "")
    state = check.get("state", "")
    return f"{check_type} check is down (state={state})"
