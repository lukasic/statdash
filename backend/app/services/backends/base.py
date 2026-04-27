from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

from jinja2 import Environment, Undefined

_jinja_env = Environment(undefined=Undefined)


def render_url(template: str | None, **variables: str) -> str | None:
    if not template:
        return None
    try:
        return _jinja_env.from_string(template).render(**variables)
    except Exception:
        return None


@dataclass
class CheckResult:
    source: str
    id: str
    name: str
    host: str
    status: Literal["warning", "critical", "unknown"]
    output: str
    since: str | None = None          # ISO 8601 UTC — when the problem started
    last_checked: str | None = None   # ISO 8601 UTC — when the check last ran
    acknowledged: bool = False
    in_downtime: bool = False
    ack_comment: str | None = None
    ack_expiry: str | None = None      # ISO 8601 UTC
    downtime_comment: str | None = None
    downtime_expiry: str | None = None  # ISO 8601 UTC
    url: str | None = None


class BaseBackend(ABC):
    @abstractmethod
    async def fetch_checks(self) -> list[CheckResult]:
        ...
