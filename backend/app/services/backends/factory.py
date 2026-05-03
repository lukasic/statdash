from app.core.app_config import Icinga2SourceConfig, NodepingSourceConfig, PrometheusSourceConfig, SourceConfig, UptimeKumaSourceConfig
from app.services.backends.base import BaseBackend
from app.services.backends.icinga2 import Icinga2Backend
from app.services.backends.nodeping import NodepingBackend
from app.services.backends.prometheus import PrometheusBackend
from app.services.backends.uptimekuma import UptimeKumaBackend


def create_backend(config: SourceConfig) -> BaseBackend:
    if isinstance(config, Icinga2SourceConfig):
        return Icinga2Backend(config)
    if isinstance(config, NodepingSourceConfig):
        return NodepingBackend(config)
    if isinstance(config, UptimeKumaSourceConfig):
        return UptimeKumaBackend(config)
    if isinstance(config, PrometheusSourceConfig):
        return PrometheusBackend(config)
    raise ValueError(f"No backend implementation for source type: {config.type}")
