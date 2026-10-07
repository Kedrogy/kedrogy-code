"""Provision project-scoped PostgreSQL roles using an administrative connection.

Run with PG* administrator variables and --output-dir pointing to private storage.
The generated files are credentials, not source files. No values are printed.
"""
import argparse
import os
import secrets
from pathlib import Path

import psycopg
from psycopg import sql

ROLES = {kind: f'kedrogy_{kind}' for kind in ('app', 'reader', 'annotator', 'ingest', 'migrator')}
ANNOTATION_TABLES = {'dataset', 'example', 'link', 'structured_input', 'structured_example', 'structured_link'}


def write_env(path: Path, values: dict[str, str]) -> None:
    """Write dotenv-compatible values with private permissions and no logging."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    os.chmod(path, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8') as file:
        for key, value in values.items():
            escaped = str(value).replace('\\', '\\\\').replace("'", "\\'")
            file.write(f"{key}='{escaped}'\n")


def provision(output_dir: Path) -> None:
    """Create roles and grants; reserve schema ownership for explicit setup."""
    if any((output_dir / f"{kind}.env").exists() for kind in ROLES):
        raise FileExistsError("Use a new private output directory; existing recovery credentials will not be overwritten.")
    common = {key: os.environ[key] for key in ('PGHOST', 'PGPORT', 'PGDATABASE')}
    credentials = {kind: common | {'PGUSER': role, 'PGPASSWORD': secrets.token_urlsafe(36)} for kind, role in ROLES.items()}
    # Write private recovery material before committing any credential changes.
    for kind, values in credentials.items():
        write_env(output_dir / f'{kind}.env', values)
    with psycopg.connect() as conn:
        database = conn.info.dbname
        for kind, role in ROLES.items():
            if not conn.execute('SELECT 1 FROM pg_roles WHERE rolname=%s', (role,)).fetchone():
                conn.execute(sql.SQL('CREATE ROLE {} LOGIN').format(sql.Identifier(role)))
            conn.execute(sql.SQL('ALTER ROLE {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}').format(
                sql.Identifier(role), sql.Literal(credentials[kind]['PGPASSWORD'])))
            conn.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO {}').format(sql.Identifier(database), sql.Identifier(role)))
            conn.execute(sql.SQL('GRANT USAGE ON SCHEMA public TO {}').format(sql.Identifier(role)))
            conn.execute(sql.SQL('ALTER ROLE {} IN DATABASE {} SET search_path = public').format(sql.Identifier(role), sql.Identifier(database)))
        conn.execute('REVOKE CREATE ON SCHEMA public FROM PUBLIC')
        for kind in ('migrator',):
            conn.execute(sql.SQL('GRANT CREATE ON SCHEMA public TO {}').format(sql.Identifier(ROLES[kind])))
        tables = [r[0] for r in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'")]
        for table in tables:
            identifier = sql.Identifier('public', table)
            if table.startswith(('django_', 'kedrogy_', 'auth_')):
                conn.execute(sql.SQL('ALTER TABLE {} OWNER TO {}').format(identifier, sql.Identifier(ROLES['migrator'])))
                conn.execute(sql.SQL('GRANT SELECT, INSERT, UPDATE, DELETE ON {} TO {}').format(identifier, sql.Identifier(ROLES['app'])))
            elif table in ANNOTATION_TABLES:
                conn.execute(sql.SQL('GRANT SELECT, INSERT, UPDATE, DELETE ON {} TO {}').format(identifier, sql.Identifier(ROLES['annotator'])))
                conn.execute(sql.SQL('GRANT SELECT ON {} TO {}').format(identifier, sql.Identifier(ROLES['reader'])))
            elif table == 'all_data':
                conn.execute(sql.SQL('ALTER TABLE {} OWNER TO {}').format(identifier, sql.Identifier(ROLES['migrator'])))
                conn.execute(sql.SQL('GRANT SELECT ON {} TO {}').format(identifier, sql.Identifier(ROLES['reader'])))
        # Sequence ownership follows ALTER TABLE for owned sequences. Grant only matching ones.
        sequences = conn.execute("""
            SELECT seq.relname, tbl.relname FROM pg_class seq
            JOIN pg_namespace ns ON ns.oid=seq.relnamespace
            JOIN pg_depend dep ON dep.objid=seq.oid AND dep.deptype IN ('a','i')
            JOIN pg_class tbl ON tbl.oid=dep.refobjid
            WHERE seq.relkind='S' AND ns.nspname='public'
        """).fetchall()
        for sequence, table in sequences:
            kind = 'annotator' if table in ANNOTATION_TABLES else 'app' if table.startswith(('django_', 'kedrogy_', 'auth_')) else None
            if kind:
                conn.execute(sql.SQL('GRANT USAGE, SELECT ON SEQUENCE {} TO {}').format(sql.Identifier('public', sequence), sql.Identifier(ROLES[kind])))
        conn.execute('ALTER DEFAULT PRIVILEGES FOR ROLE kedrogy_migrator IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO kedrogy_app')
        conn.execute('ALTER DEFAULT PRIVILEGES FOR ROLE kedrogy_migrator IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO kedrogy_app')
        from configure_sources import install
        install(conn)
    print('Provisioned five restricted roles. Credentials saved to private files; values withheld.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    provision(parser.parse_args().output_dir)
