from app.core.app_config import Icinga2SourceConfig, NodepingSourceConfig, SourceConfig
from app.services.backends.base import BaseBackend
from app.services.backends.icinga2 import Icinga2Backend
from app.services.backends.nodeping import NodepingBackend


def create_backend(config: SourceConfig) -> BaseBackend:
    if isinstance(config, Icinga2SourceConfig):
        return Icinga2Backend(config)
    if isinstance(config, NodepingSourceConfig):
        return NodepingBackend(config)
    raise ValueError(f"No backend implementation for source type: {config.type}")
