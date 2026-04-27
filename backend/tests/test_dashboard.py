import json
from dataclasses import asdict
from unittest.mock import AsyncMock

from app.core.app_config import AppConfig, FilterConfig, NodepingSourceConfig, SectionConfig
from app.services.backends.base import CheckResult
from app.services.dashboard import get_dashboard_data
from app.services.poller import CHECKS_KEY, STATUS_KEY

SOURCE = NodepingSourceConfig(name="np", type="nodeping", api_key="key")

CONFIG = AppConfig(
    pull_interval=10,
    sources=[SOURCE],
    sections=[
        SectionConfig(
            name="Uptime",
            description="External checks",
            filters=[FilterConfig(source="np", name_pattern="*")],
        ),
        SectionConfig(
            name="Backups",
            description="Backup checks",
            filters=[FilterConfig(source="np", name_pattern="backup*")],
        ),
    ],
)

CHECKS = [
    CheckResult(source="np", id="c1", name="My Site", host="https://a.com", status="critical", output="down"),
    CheckResult(source="np", id="c2", name="backup-db", host="https://b.com", status="warning", output="slow"),
    CheckResult(source="np", id="c3", name="check-other", host="https://c.com", status="unknown", output="?"),
]


def _make_cache(checks: list[CheckResult] | None = None, available: bool = True) -> AsyncMock:
    cache = AsyncMock()

    async def get(key: str):
        if key == STATUS_KEY.format("np"):
            return json.dumps({"available": available, "last_updated": "2026-01-01T00:00:00+00:00"})
        if key == CHECKS_KEY.format("np") and checks is not None:
            return json.dumps([asdict(c) for c in checks])
        return None

    cache.get = get
    return cache


async def test_sections_contain_matching_checks() -> None:
    data = await get_dashboard_data(CONFIG, _make_cache(CHECKS))
    uptime = next(s for s in data["sections"] if s["name"] == "Uptime")
    assert len(uptime["checks"]) == 3


async def test_section_filter_by_pattern() -> None:
    data = await get_dashboard_data(CONFIG, _make_cache(CHECKS))
    backups = next(s for s in data["sections"] if s["name"] == "Backups")
    assert len(backups["checks"]) == 1
    assert backups["checks"][0]["name"] == "backup-db"


async def test_no_duplicate_checks_in_section() -> None:
    config = AppConfig(
        pull_interval=10,
        sources=[SOURCE],
        sections=[
            SectionConfig(
                name="All",
                filters=[
                    FilterConfig(source="np", name_pattern="*"),
                    FilterConfig(source="np", name_pattern="backup*"),
                ],
            )
        ],
    )
    data = await get_dashboard_data(config, _make_cache(CHECKS))
    assert len(data["sections"][0]["checks"]) == 3


async def test_source_unavailable_reflected() -> None:
    data = await get_dashboard_data(CONFIG, _make_cache(available=False))
    source = next(s for s in data["sources"] if s["name"] == "np")
    assert source["available"] is False


async def test_empty_cache_returns_empty_sections() -> None:
    data = await get_dashboard_data(CONFIG, _make_cache(checks=None))
    assert all(len(s["checks"]) == 0 for s in data["sections"])


async def test_catchall_shows_unmatched_checks() -> None:
    config = AppConfig(
        pull_interval=10,
        sources=[SOURCE],
        sections=[
            SectionConfig(name="Backups", filters=[FilterConfig(source="np", name_pattern="backup*")]),
            SectionConfig(name="All", catchall=True),
        ],
    )
    data = await get_dashboard_data(config, _make_cache(CHECKS))
    catchall = next(s for s in data["sections"] if s["name"] == "All")
    ids = {c["id"] for c in catchall["checks"]}
    assert "c2" not in ids  # backup-db matched by Backups section
    assert "c1" in ids
    assert "c3" in ids


async def test_catchall_empty_when_all_checks_matched() -> None:
    config = AppConfig(
        pull_interval=10,
        sources=[SOURCE],
        sections=[
            SectionConfig(name="Everything", filters=[FilterConfig(source="np", name_pattern="*")]),
            SectionConfig(name="Rest", catchall=True),
        ],
    )
    data = await get_dashboard_data(config, _make_cache(CHECKS))
    catchall = next(s for s in data["sections"] if s["name"] == "Rest")
    assert catchall["checks"] == []


async def test_catchall_shows_all_when_no_other_sections() -> None:
    config = AppConfig(
        pull_interval=10,
        sources=[SOURCE],
        sections=[SectionConfig(name="All", catchall=True)],
    )
    data = await get_dashboard_data(config, _make_cache(CHECKS))
    assert len(data["sections"][0]["checks"]) == 3


async def test_checks_sorted_by_status_priority() -> None:
    checks = [
        CheckResult(source="np", id="u", name="Unknown", host="h", status="unknown", output=""),
        CheckResult(source="np", id="w", name="Warning", host="h", status="warning", output=""),
        CheckResult(source="np", id="c", name="Critical", host="h", status="critical", output=""),
    ]
    config = AppConfig(
        pull_interval=10,
        sources=[SOURCE],
        sections=[SectionConfig(name="All", filters=[FilterConfig(source="np", name_pattern="*")])],
    )
    data = await get_dashboard_data(config, _make_cache(checks))
    statuses = [ch["status"] for ch in data["sections"][0]["checks"]]
    assert statuses == ["critical", "warning", "unknown"]


async def test_checks_sorted_newer_since_first_within_same_status() -> None:
    checks = [
        CheckResult(source="np", id="old", name="Old", host="h", status="critical", output="",
                    since="2025-01-01T00:00:00+00:00"),
        CheckResult(source="np", id="new", name="New", host="h", status="critical", output="",
                    since="2025-06-01T00:00:00+00:00"),
    ]
    config = AppConfig(
        pull_interval=10,
        sources=[SOURCE],
        sections=[SectionConfig(name="All", filters=[FilterConfig(source="np", name_pattern="*")])],
    )
    data = await get_dashboard_data(config, _make_cache(checks))
    ids = [ch["id"] for ch in data["sections"][0]["checks"]]
    assert ids == ["new", "old"]


async def test_checks_without_since_go_last_within_status() -> None:
    checks = [
        CheckResult(source="np", id="no-since", name="NoSince", host="h", status="critical", output=""),
        CheckResult(source="np", id="has-since", name="HasSince", host="h", status="critical", output="",
                    since="2025-01-01T00:00:00+00:00"),
    ]
    config = AppConfig(
        pull_interval=10,
        sources=[SOURCE],
        sections=[SectionConfig(name="All", filters=[FilterConfig(source="np", name_pattern="*")])],
    )
    data = await get_dashboard_data(config, _make_cache(checks))
    ids = [ch["id"] for ch in data["sections"][0]["checks"]]
    assert ids == ["has-since", "no-since"]
