import asyncio
import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Awaitable, Callable

import redis.asyncio as redis

from app.core.app_config import AppConfig, SourceConfig
from app.services.backends.base import BaseBackend, CheckResult
from app.services.backends.factory import create_backend

logger = logging.getLogger(__name__)

CHECKS_KEY = "statdash:checks:{}"
STATUS_KEY = "statdash:status:{}"


class Poller:
    def __init__(
        self,
        config: AppConfig,
        cache: redis.Redis,
        backend_factory: Callable[[SourceConfig], BaseBackend] | None = None,
        on_update: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._config = config
        self._cache = cache
        self._factory = backend_factory or create_backend
        self._on_update = on_update
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        for source in self._config.sources:
            task = asyncio.create_task(
                self._poll_loop(source),
                name=f"poll:{source.name}",
            )
            self._tasks.append(task)

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _poll_loop(self, source: SourceConfig) -> None:
        backend = self._factory(source)
        while True:
            await self._poll_once(source.name, backend)
            await asyncio.sleep(self._config.pull_interval)

    async def _poll_once(self, source_name: str, backend: BaseBackend) -> None:
        try:
            checks = await backend.fetch_checks()
            await self._store(source_name, checks)
        except Exception:
            logger.exception("Poll failed for source '%s'", source_name)
            await self._invalidate(source_name)
        finally:
            if self._on_update:
                await self._on_update()

    async def _store(self, source_name: str, checks: list[CheckResult]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await self._cache.set(
            CHECKS_KEY.format(source_name),
            json.dumps([asdict(c) for c in checks]),
        )
        await self._cache.set(
            STATUS_KEY.format(source_name),
            json.dumps({"available": True, "last_updated": now}),
        )

    async def _invalidate(self, source_name: str) -> None:
        await self._cache.delete(CHECKS_KEY.format(source_name))
        await self._cache.set(
            STATUS_KEY.format(source_name),
            json.dumps({"available": False, "last_updated": None}),
        )
