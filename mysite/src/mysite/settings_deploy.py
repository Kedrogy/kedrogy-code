"""Explicit deployment profile behind a trusted HTTPS reverse proxy."""

import ipaddress
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured

from .settings_base import *
from .settings_base import SECRET_KEY, os, required_setting


def required_list(name: str) -> list[str]:
    """Reject missing entries without echoing deployment values."""
    values = [value.strip() for value in required_setting(name).split(",")]
    if any(not value for value in values):
        raise ImproperlyConfigured(f"Set a nonempty comma-separated {name}.")
    return values


DEBUG = False
if os.environ.get("DJANGO_DEBUG", "false").lower() != "false":
    raise ImproperlyConfigured("DJANGO_DEBUG must be false in the deployment profile.")
if len(SECRET_KEY) < 50:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must contain at least 50 random characters.")
ALLOWED_HOSTS = required_list("DJANGO_ALLOWED_HOSTS")
if any(host in {"*", "testserver", "localhost", "127.0.0.1"} or host.startswith(".")
       or "/" in host or ":" in host for host in ALLOWED_HOSTS):
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must list explicit deployment hostnames.")
CORS_ALLOWED_ORIGINS = required_list("DJANGO_CORS_ORIGINS")
CSRF_TRUSTED_ORIGINS = required_list("DJANGO_CSRF_ORIGINS")
for origin in CORS_ALLOWED_ORIGINS + CSRF_TRUSTED_ORIGINS:
    parsed = urlsplit(origin)
    if parsed.scheme != "https" or not parsed.hostname or parsed.path != "" or parsed.query or parsed.fragment or parsed.username or "*" in origin:
        raise ImproperlyConfigured("Deployment origins must be explicit HTTPS origins.")
TRUSTED_PROXY_CIDRS = required_list("DJANGO_TRUSTED_PROXY_CIDRS")
try:
    if any(ipaddress.ip_network(value).prefixlen == 0 for value in TRUSTED_PROXY_CIDRS):
        raise ValueError
except ValueError:
    raise ImproperlyConfigured("DJANGO_TRUSTED_PROXY_CIDRS must contain specific trusted networks.") from None
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SECURE_REDIRECT_EXEMPT = [r"^health/$"]
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
