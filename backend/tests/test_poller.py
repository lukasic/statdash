import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.app_config import AppConfig, NodepingSourceConfig
from app.services.backends.base import BaseBackend, CheckResult
from app.services.poller import CHECKS_KEY, STATUS_KEY, Poller

SOURCE = NodepingSourceConfig(name="np", type="nodeping", api_key="key")

CONFIG = AppConfig(
    pull_interval=10,
    sources=[SOURCE],
    sections=[],
)

CHECKS = [
    CheckResult(
        source="np",
        id="c1",
        name="My Site",
        host="https://example.com",
        status="critical",
        output="HTTP check is down (state=0)",
    )
]


@pytest.fixture
def cache() -> AsyncMock:
    mock = AsyncMock()
    mock.set = AsyncMock()
    mock.get = AsyncMock(return_value=None)
    mock.delete = AsyncMock()
    return mock


@pytest.fixture
def ok_backend() -> BaseBackend:
    backend = MagicMock(spec=BaseBackend)
    backend.fetch_checks = AsyncMock(return_value=CHECKS)
    return backend


@pytest.fixture
def failing_backend() -> BaseBackend:
    backend = MagicMock(spec=BaseBackend)
    backend.fetch_checks = AsyncMock(side_effect=Exception("Connection refused"))
    return backend


async def test_poll_once_stores_checks(cache: AsyncMock, ok_backend: BaseBackend) -> None:
    poller = Poller(CONFIG, cache, backend_factory=lambda _: ok_backend)
    await poller._poll_once("np", ok_backend)

    stored = json.loads(cache.set.call_args_list[0].args[1])
    assert stored[0]["id"] == "c1"
    assert stored[0]["status"] == "critical"


async def test_poll_once_sets_available_status(cache: AsyncMock, ok_backend: BaseBackend) -> None:
    poller = Poller(CONFIG, cache, backend_factory=lambda _: ok_backend)
    await poller._poll_once("np", ok_backend)

    status_call = next(
        call for call in cache.set.call_args_list
        if STATUS_KEY.format("np") in call.args[0]
    )
    status = json.loads(status_call.args[1])
    assert status["available"] is True
    assert status["last_updated"] is not None


async def test_poll_once_on_error_deletes_checks(cache: AsyncMock, failing_backend: BaseBackend) -> None:
    poller = Poller(CONFIG, cache, backend_factory=lambda _: failing_backend)
    await poller._poll_once("np", failing_backend)

    cache.delete.assert_called_once_with(CHECKS_KEY.format("np"))


async def test_poll_once_on_error_marks_unavailable(cache: AsyncMock, failing_backend: BaseBackend) -> None:
    poller = Poller(CONFIG, cache, backend_factory=lambda _: failing_backend)
    await poller._poll_once("np", failing_backend)

    status = json.loads(cache.set.call_args.args[1])
    assert status["available"] is False
    assert status["last_updated"] is None


async def test_start_creates_task_per_source(cache: AsyncMock, ok_backend: BaseBackend) -> None:
    poller = Poller(CONFIG, cache, backend_factory=lambda _: ok_backend)
    await poller.start()
    assert len(poller._tasks) == 1
    await poller.stop()


async def test_stop_cancels_tasks(cache: AsyncMock, ok_backend: BaseBackend) -> None:
    poller = Poller(CONFIG, cache, backend_factory=lambda _: ok_backend)
    await poller.start()
    await poller.stop()
    assert all(t.cancelled() or t.done() for t in poller._tasks)


async def test_on_update_called_after_successful_poll(cache: AsyncMock, ok_backend: BaseBackend) -> None:
    on_update = AsyncMock()
    poller = Poller(CONFIG, cache, backend_factory=lambda _: ok_backend, on_update=on_update)
    await poller._poll_once("np", ok_backend)
    on_update.assert_called_once()


async def test_on_update_called_after_failed_poll(cache: AsyncMock, failing_backend: BaseBackend) -> None:
    on_update = AsyncMock()
    poller = Poller(CONFIG, cache, backend_factory=lambda _: failing_backend, on_update=on_update)
    await poller._poll_once("np", failing_backend)
    on_update.assert_called_once()
