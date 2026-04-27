import pytest
from pydantic import ValidationError

from app.core.app_config import AppConfig, Icinga2SourceConfig, NodepingSourceConfig

VALID_CONFIG = {
    "pull_interval": 10,
    "sources": [
        {
            "name": "icinga-prod",
            "type": "icinga2",
            "url": "https://icinga.example.com:5665",
            "username": "root",
            "password": "secret",
            "verify_ssl": False,
        },
        {
            "name": "nodeping-main",
            "type": "nodeping",
            "api_key": "abc123",
        },
    ],
    "sections": [
        {
            "name": "Backups",
            "description": "Backup checks",
            "filters": [
                {"source": "icinga-prod", "name_pattern": "backup*"},
            ],
        },
        {
            "name": "Uptime",
            "filters": [
                {"source": "nodeping-main"},
            ],
        },
    ],
}


def test_valid_config_parses() -> None:
    config = AppConfig.model_validate(VALID_CONFIG)
    assert config.pull_interval == 10
    assert len(config.sources) == 2
    assert len(config.sections) == 2


def test_source_discriminator() -> None:
    config = AppConfig.model_validate(VALID_CONFIG)
    assert isinstance(config.sources[0], Icinga2SourceConfig)
    assert isinstance(config.sources[1], NodepingSourceConfig)


def test_icinga2_defaults() -> None:
    config = AppConfig.model_validate(VALID_CONFIG)
    icinga = config.sources[0]
    assert isinstance(icinga, Icinga2SourceConfig)
    assert icinga.verify_ssl is False


def test_filter_default_pattern() -> None:
    config = AppConfig.model_validate(VALID_CONFIG)
    uptime_filter = config.sections[1].filters[0]
    assert uptime_filter.name_pattern == "*"


def test_unknown_source_type_raises() -> None:
    bad = {**VALID_CONFIG, "sources": [{"name": "x", "type": "prometheus"}]}
    with pytest.raises(ValidationError):
        AppConfig.model_validate(bad)


def test_filter_references_undefined_source_raises() -> None:
    bad = {
        **VALID_CONFIG,
        "sections": [
            {
                "name": "Bad",
                "filters": [{"source": "nonexistent"}],
            }
        ],
    }
    with pytest.raises(ValidationError):
        AppConfig.model_validate(bad)


def test_missing_icinga2_required_field_raises() -> None:
    bad = {
        **VALID_CONFIG,
        "sources": [{"name": "x", "type": "icinga2", "username": "root", "password": "x"}],
    }
    with pytest.raises(ValidationError):
        AppConfig.model_validate(bad)


def test_pull_interval_default() -> None:
    minimal = {
        "sources": [{"name": "np", "type": "nodeping", "api_key": "x"}],
        "sections": [],
    }
    config = AppConfig.model_validate(minimal)
    assert config.pull_interval == 10


def test_catchall_section_requires_no_filters() -> None:
    config = AppConfig.model_validate({
        "sources": [{"name": "np", "type": "nodeping", "api_key": "x"}],
        "sections": [{"name": "All", "catchall": True}],
    })
    assert config.sections[0].catchall is True
    assert config.sections[0].filters == []


def test_non_catchall_section_without_filters_raises() -> None:
    with pytest.raises(ValidationError):
        AppConfig.model_validate({
            "sources": [{"name": "np", "type": "nodeping", "api_key": "x"}],
            "sections": [{"name": "Empty"}],
        })
