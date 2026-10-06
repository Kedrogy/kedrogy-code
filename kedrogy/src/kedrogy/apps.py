"""App registration; initialization is an explicit management command."""
from django.apps import AppConfig


class DatasetNewConfig(AppConfig):
    """Register without touching PostgreSQL or Kubernetes during startup."""

    name = "kedrogy"
