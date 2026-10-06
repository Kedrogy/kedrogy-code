"""Create a disposable PostgreSQL fixture without copying working application data."""

import json
import os
import secrets
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "kedrogy-revisions-pg"
NAMESPACE = "kedrogy-check-20260925"
ENV_FILE = ROOT / ".local/revisions-env.json"


def main():
    import psycopg
    password = secrets.token_urlsafe(40)
    env = {"PGHOST": "127.0.0.1", "PGPORT": "55433", "PGDATABASE": "revisions", "PGUSER": "fixture", "PGPASSWORD": password,
           "KEDROGY_TEST_DATABASE": "disposable", "DJANGO_SETTINGS_MODULE": "mysite.test_postgres_settings",
           "DJANGO_SECRET_KEY": secrets.token_urlsafe(60), "KEDROGY_NAMESPACE": NAMESPACE,
           "KEDROGY_ML_IMAGE": "approved:1"}
    if ENV_FILE.exists():
        raise RuntimeError("A revisions fixture already exists. Inspect it before reuse.")
    ENV_FILE.parent.mkdir(exist_ok=True)
    ENV_FILE.write_text(json.dumps(env))
    ENV_FILE.chmod(0o600)
    os.environ.update(env)
    child_env = dict(os.environ, POSTGRES_PASSWORD=password)
    subprocess.run(["docker", "run", "-d", "--name", NAME, "--network", "k3d-kedrogy", "-p", "127.0.0.1:55433:5432",
                    "-e", "POSTGRES_PASSWORD", "-e", "POSTGRES_USER=fixture", "-e", "POSTGRES_DB=revisions", "postgres:18"], check=True, env=child_env)
    deadline = time.monotonic() + 60
    while True:
        try:
            conn = psycopg.connect(connect_timeout=2)
            break
        except psycopg.Error:
            if time.monotonic() > deadline:
                raise TimeoutError("Disposable database did not start.") from None
            time.sleep(1)
    with conn:
        conn.execute("CREATE TABLE dataset (id serial PRIMARY KEY, name text UNIQUE NOT NULL, session boolean NOT NULL DEFAULT false)")
        conn.execute("CREATE TABLE example (id serial PRIMARY KEY, content bytea NOT NULL)")
        conn.execute("CREATE TABLE link (dataset_id int REFERENCES dataset(id), example_id int REFERENCES example(id))")
        conn.execute("INSERT INTO dataset(name) VALUES ('revision-fixture')")
        for index in range(24):
            label = "positive" if index % 2 else "negative"
            row = {"text": "good product" if index % 2 else "bad product", "label": label, "answer": "accept" if index % 5 else "reject"}
            identifier = conn.execute("INSERT INTO example(content) VALUES (%s) RETURNING id", (json.dumps(row).encode(),)).fetchone()[0]
            conn.execute("INSERT INTO link VALUES (1, %s)", (identifier,))
    env |= {"READER_" + key: value for key, value in env.items() if key.startswith("PG")}
    ENV_FILE.write_text(json.dumps(env))
    print("Disposable PostgreSQL fixture created; no working data copied.")


if __name__ == "__main__":
    main()
