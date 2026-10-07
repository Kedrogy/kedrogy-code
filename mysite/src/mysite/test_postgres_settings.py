"""Integration tests against an explicitly disposable PostgreSQL instance."""

import os

from django.core.exceptions import ImproperlyConfigured

from .test_settings import *

if os.environ.get("KEDROGY_TEST_DATABASE") != "disposable":
    raise ImproperlyConfigured("PostgreSQL integration settings require a disposable database.")
DATABASES = {"default": {"ENGINE": "django.db.backends.postgresql",
    "HOST": os.environ["PGHOST"], "PORT": os.environ["PGPORT"],
    "NAME": os.environ["PGDATABASE"], "USER": os.environ["PGUSER"], "PASSWORD": os.environ["PGPASSWORD"]}}
TASKS = {"default": {"BACKEND": "django_tasks.backends.database.DatabaseBackend"}}
