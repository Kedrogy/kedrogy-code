"""Create a separate synthetic Prodigy database for deployment route testing."""

import json
import os
import subprocess
from pathlib import Path

from scripts.publish_local_secrets import apply_secret

env = json.loads(Path(".local/reliability-env.json").read_text())
if env.get("KEDROGY_TEST_DATABASE") != "disposable":
    raise ValueError("Disposable fixtures only.")
os.environ.update(env)
import psycopg

with psycopg.connect(autocommit=True) as conn:
    conn.execute("CREATE DATABASE prodigy_fixture")
pg = {key: value for key, value in env.items() if key.startswith("PG")} | {
    "PGDATABASE": "prodigy_fixture"
}
p = Path(".local/prodigy-fixture-env.json")
p.write_text(json.dumps(pg))
p.chmod(0o600)
# Use the installed Prodigy ORM to initialize exactly its current schema.
code = """import os
from prodigy.components.db import Database
from peewee import PostgresqlDatabase
Database(PostgresqlDatabase(os.environ['PGDATABASE'],user=os.environ['PGUSER'],password=os.environ['PGPASSWORD'],host=os.environ['PGHOST'],port=int(os.environ['PGPORT'])), 'postgresql', 'Synthetic fixture')
"""
subprocess.run(
    ["example/.venv/bin/python", "-c", code],
    env=os.environ | pg,
    check=True,
    timeout=120,
)
with psycopg.connect(
    dbname=pg["PGDATABASE"],
    user=pg["PGUSER"],
    password=pg["PGPASSWORD"],
    host=pg["PGHOST"],
    port=pg["PGPORT"],
) as conn:
    conn.execute("CREATE TABLE all_data (id text PRIMARY KEY, text text, source text)")
    conn.execute(
        "INSERT INTO all_data VALUES ('1','A good synthetic product','fixture'),('2','A bad synthetic product','fixture')"
    )
ip = subprocess.check_output(
    [
        "docker",
        "inspect",
        "kedrogy-reliability-pg",
        "--format",
        "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
    ],
    text=True,
).strip()
os.environ["KUBECONFIG"] = str(Path.home() / ".kube/config")
apply_secret(
    "kedrogy-db-annotation-fixture",
    pg | {"PGHOST": ip, "PGPORT": "5432"},
    env["KEDROGY_NAMESPACE"],
)
os.environ["KUBECONFIG"] = env["KUBECONFIG"]
import django

django.setup()
from django.conf import settings
from kedrogy.kubernetes import command
from kedrogy.launch_config import LaunchConfig
from kedrogy.manifests import annotation

settings.KEDROGY_NAMESPACE = env["KEDROGY_NAMESPACE"]
cfg = LaunchConfig(
    image=env["KEDROGY_ML_IMAGE"],
    working_dir="/app/mykedro",
    pipeline="load_examples",
    dataset_name="route-fixture",
    table_name="all_data",
    id_field="id",
    recipe_args=(
        "myrecipes.textcat.custom-model",
        "route-fixture",
        "./data/00_examples/examples.jsonl",
        "-l",
        "positive,negative",
    ),
)
docs = annotation(cfg, 999)
for container in docs[1]["spec"]["template"]["spec"]["initContainers"]:
    for value in container.get("env", []):
        ref = value.get("valueFrom", {}).get("secretKeyRef")
        if ref:
            ref["name"] = "kedrogy-db-annotation-fixture"
command(
    ["apply", "-f", "-"], document={"apiVersion": "v1", "kind": "List", "items": docs}
)
print("Isolated annotation deployment created; credentials withheld.")
