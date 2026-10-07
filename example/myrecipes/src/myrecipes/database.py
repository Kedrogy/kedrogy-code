"""Prodigy adapter for a pre-provisioned PostgreSQL schema without runtime DDL."""

from peewee import PostgresqlDatabase
from prodigy.components.db import Database
from prodigy.util import get_config


class ExistingSchemaDatabase(PostgresqlDatabase):
    """Verify tables instead of Prodigy's unconditional CREATE IF NOT EXISTS."""

    def create_tables(self, models, **options):
        missing = [model._meta.table_name for model in models if not model.table_exists()]
        if missing:
            raise RuntimeError("Initialize Prodigy schema with the setup role first. Missing tables: " + ", ".join(missing))


def connect_existing() -> Database:
    """Open the configured schema using only the annotation role's DML rights."""
    options = dict(get_config().get("db_settings", {}).get("kedrogy_postgresql", {}))
    if not options.get("dbname"):
        raise ValueError("Configure db_settings.kedrogy_postgresql.dbname in PRODIGY_CONFIG.")
    name = options.pop("dbname")
    return Database(ExistingSchemaDatabase(name, **options), "postgresql", "Kedrogy PostgreSQL")
