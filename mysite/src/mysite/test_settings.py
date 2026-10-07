"""Isolated Django tests: no startup network calls, real tasks, or cluster access."""

import os

for key, value in {"DJANGO_SECRET_KEY": "test-only-not-a-deployment-secret",
                   "KEDROGY_ML_IMAGE": "approved:1", "PGDATABASE": "unused", "PGUSER": "unused", "PGPASSWORD": "unused",
                   "PGHOST": "localhost", "PGPORT": "5432"}.items():
    os.environ.setdefault(key, value)

from .settings_local import *

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
TASKS = {"default": {"BACKEND": "django_tasks.backends.dummy.DummyBackend"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
KEDROGY_ML_IMAGE = "approved.invalid/ml@sha256:" + "a" * 64
KEDROGY_ML_IMAGE_ALIASES = {"approved:1"}
KEDROGY_SOURCES = {"all_data": {"schema": "public", "table": "all_data", "id_fields": ["id"]}}

ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
