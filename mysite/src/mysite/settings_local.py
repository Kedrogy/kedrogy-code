"""Local HTTP profile; no user login is introduced."""

from .settings_base import *
from .settings_base import os

DEBUG = os.environ.get("DJANGO_DEBUG", "false").lower() == "true"
ALLOWED_HOSTS = [host.strip() for host in os.environ.get(
    "DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1"
).split(",") if host.strip()]
CORS_ALLOWED_ORIGINS = [origin.strip() for origin in os.environ.get(
    "DJANGO_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
).split(",") if origin.strip()]
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in os.environ.get(
    "DJANGO_CSRF_ORIGINS", ",".join(CORS_ALLOWED_ORIGINS)
).split(",") if origin.strip()]
