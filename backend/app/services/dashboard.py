import fnmatch
import json
from datetime import datetime, timezone

import redis.asyncio as redis

from app.core.app_config import AppConfig
from app.services.backends.base import CheckResult
from app.services.poller import CHECKS_KEY, STATUS_KEY

_STATUS_ORDER = {"critical": 0, "warning": 1, "unknown": 2}


def _sort_key(check: dict) -> tuple[int, datetime]:
    status_rank = _STATUS_ORDER.get(check["status"], 99)
    since = check["since"]
    # Newer since = shorter duration = higher priority → sort descending by parsing as negative.
    # Checks without since go last within their status group.
    if since:
        ts = datetime.fromisoformat(since)
    else:
        ts = datetime.min.replace(tzinfo=timezone.utc)
    return (status_rank, -ts.timestamp())


async def get_dashboard_data(config: AppConfig, cache: redis.Redis) -> dict:
    sources = []
    all_checks: list[CheckResult] = []

    for source in config.sources:
        status_raw = await cache.get(STATUS_KEY.format(source.name))
        status = json.loads(status_raw) if status_raw else {"available": True, "last_updated": None}
        sources.append({
            "name": source.name,
            "type": source.type,
            "available": status["available"],
            "last_updated": status["last_updated"],
        })
        checks_raw = await cache.get(CHECKS_KEY.format(source.name))
        if checks_raw:
            for c in json.loads(checks_raw):
                all_checks.append(CheckResult(**c))

    # Collect IDs matched by all non-catchall sections so catchall can exclude them.
    globally_matched: set[str] = set()
    for section_cfg in config.sections:
        if section_cfg.catchall:
            continue
        for f in section_cfg.filters:
            for check in all_checks:
                if check.source == f.source and fnmatch.fnmatch(check.name, f.name_pattern):
                    globally_matched.add(check.id)

    sections = []
    for section_cfg in config.sections:
        if section_cfg.catchall:
            matching = [_check_to_dict(c) for c in all_checks if c.id not in globally_matched]
        else:
            seen: set[str] = set()
            matching = []
            for f in section_cfg.filters:
                for check in all_checks:
                    if (
                        check.source == f.source
                        and fnmatch.fnmatch(check.name, f.name_pattern)
                        and check.id not in seen
                    ):
                        seen.add(check.id)
                        matching.append(_check_to_dict(check))

        sections.append({
            "name": section_cfg.name,
            "description": section_cfg.description,
            "checks": sorted(matching, key=_sort_key),
        })

    return {"sections": sections, "sources": sources}


def _check_to_dict(check: CheckResult) -> dict:
    return {
        "id": check.id,
        "name": check.name,
        "host": check.host,
        "source": check.source,
        "status": check.status,
        "output": check.output,
        "since": check.since,
        "last_checked": check.last_checked,
        "acknowledged": check.acknowledged,
        "in_downtime": check.in_downtime,
        "ack_comment": check.ack_comment,
        "ack_expiry": check.ack_expiry,
        "downtime_comment": check.downtime_comment,
        "downtime_expiry": check.downtime_expiry,
        "url": check.url,
    }
