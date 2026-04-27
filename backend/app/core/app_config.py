from pathlib import Path
from typing import Annotated, Literal, Union

import yaml
from pydantic import BaseModel, Field, model_validator

from app.core.config import settings


class Icinga2SourceConfig(BaseModel):
    name: str
    type: Literal["icinga2"]
    url: str
    username: str
    password: str
    verify_ssl: bool = True
    filter: str | None = None
    url_template: str | None = None


class NodepingSourceConfig(BaseModel):
    name: str
    type: Literal["nodeping"]
    api_key: str
    url_template: str | None = None


SourceConfig = Annotated[
    Union[Icinga2SourceConfig, NodepingSourceConfig],
    Field(discriminator="type"),
]


class FilterConfig(BaseModel):
    source: str
    name_pattern: str = "*"


class SectionConfig(BaseModel):
    name: str
    description: str = ""
    filters: list[FilterConfig] = []
    catchall: bool = False

    @model_validator(mode="after")
    def validate_has_filters_or_catchall(self) -> "SectionConfig":
        if not self.catchall and not self.filters:
            raise ValueError(f"Section '{self.name}' must have filters or catchall: true")
        return self


class AppConfig(BaseModel):
    pull_interval: int = 10
    sources: list[SourceConfig]
    sections: list[SectionConfig]

    @model_validator(mode="after")
    def validate_filter_sources(self) -> "AppConfig":
        known = {s.name for s in self.sources}
        for section in self.sections:
            for f in section.filters:
                if f.source not in known:
                    raise ValueError(
                        f"Section '{section.name}': unknown source '{f.source}'"
                    )
        return self


def load_app_config() -> AppConfig:
    path = Path(settings.config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path.resolve()}")
    with open(path) as f:
        raw = yaml.safe_load(f)
    return AppConfig.model_validate(raw)


_cache: AppConfig | None = None


def get_app_config() -> AppConfig:
    global _cache
    if _cache is None:
        _cache = load_app_config()
    return _cache
