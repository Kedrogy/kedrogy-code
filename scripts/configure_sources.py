"""Install managed sources and scoped grants without changing any password.

Run using a database administrator connection. --apply is required for writes.
The old all_data table is retained with its exact contents and made read-only.
"""

import argparse
import json
import uuid
from pathlib import Path

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]


def install(connection):
    roles = {kind: f"kedrogy_{kind}" for kind in ("migrator", "ingest", "reader", "app")}
    existing = {row[0] for row in connection.execute("SELECT rolname FROM pg_roles")}
    if not set(roles.values()) <= existing:
        raise ValueError("Provision the project roles first. Source setup does not create or rotate credentials.")
    connection.execute((ROOT / "infra/source_schema.sql").read_text())
    connection.execute("ALTER SCHEMA kedrogy_source OWNER TO kedrogy_migrator")
    connection.execute("REVOKE ALL ON SCHEMA kedrogy_source FROM PUBLIC, kedrogy_ingest, kedrogy_reader, kedrogy_app")
    connection.execute("GRANT USAGE ON SCHEMA kedrogy_source TO kedrogy_ingest, kedrogy_reader")
    for table in ("collection", "record", "import_receipt"):
        name = sql.Identifier("kedrogy_source", table)
        connection.execute(sql.SQL("ALTER TABLE {} OWNER TO kedrogy_migrator").format(name))
        connection.execute(sql.SQL("REVOKE ALL ON {} FROM PUBLIC, kedrogy_ingest, kedrogy_reader, kedrogy_app").format(name))
        connection.execute(sql.SQL("GRANT SELECT ON {} TO kedrogy_ingest, kedrogy_reader").format(name))
    connection.execute("GRANT INSERT ON kedrogy_source.record, kedrogy_source.import_receipt TO kedrogy_ingest")
    connection.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC, kedrogy_ingest")
    connection.execute(sql.SQL("GRANT TEMPORARY ON DATABASE {} TO kedrogy_ingest").format(sql.Identifier(connection.info.dbname)))
    if connection.execute("SELECT to_regclass('public.all_data')").fetchone()[0]:
        connection.execute("ALTER TABLE public.all_data OWNER TO kedrogy_migrator")
        connection.execute("REVOKE ALL ON public.all_data FROM PUBLIC, kedrogy_ingest, kedrogy_app, kedrogy_reader")
        connection.execute("GRANT SELECT ON public.all_data TO kedrogy_reader")
    # An inherited owner role would bypass ordinary privilege revocations.
    for role in ("kedrogy_ingest", "kedrogy_reader", "kedrogy_app"):
        if connection.execute("SELECT pg_has_role(%s, 'kedrogy_migrator', 'MEMBER')", (role,)).fetchone()[0]:
            raise ValueError("Runtime roles must not inherit the schema owner role. Source setup was rolled back.")


def create_source(connection, key, policy):
    if not isinstance(key, str) or not 1 <= len(key) <= 128 or any(ord(c) < 33 for c in key):
        raise ValueError("Use a nonempty source namespace of at most 128 characters without whitespace or controls.")
    old = connection.execute("SELECT id, identity_policy FROM kedrogy_source.collection WHERE source_key=%s", (key,)).fetchone()
    if old:
        if old[1] != policy:
            raise ValueError("A registered source's identity policy cannot change.")
        return old[0]
    identifier = uuid.uuid4()
    connection.execute("INSERT INTO kedrogy_source.collection (id,source_key,identity_policy) VALUES (%s,%s,%s)", (identifier, key, policy))
    return identifier


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--create-source")
    parser.add_argument("--identity-policy", choices=("upstream-id-v1", "content-addressed-v1"), default="upstream-id-v1")
    args = parser.parse_args()
    if not args.apply:
        print(json.dumps({"dry_run": True, "schema": "kedrogy_source", "legacy_table": "all_data (retained, read-only)",
                          "source": args.create_source, "identity_policy": args.identity_policy, "password_changes": False}))
        return
    with psycopg.connect() as connection:
        install(connection)
        identifier = create_source(connection, args.create_source, args.identity_policy) if args.create_source else None
    print(json.dumps({"installed": True, "source_id": str(identifier) if identifier else None, "password_changes": False}))


if __name__ == "__main__":
    main()
