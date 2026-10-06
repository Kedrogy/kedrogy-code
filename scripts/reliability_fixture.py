"""Prepare synthetic PostgreSQL/Kubernetes fixtures without reading working data."""

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAMESPACE = "kedrogy-check-20260924"
ML_TAG = "kedrogy-registry.localhost:5500/mykedro:reliability-20260924"


def setup():
    """Create only isolated fixture resources and credentials."""
    import psycopg

    from scripts.publish_local_secrets import apply_secret
    from scripts.refresh_kubeconfig import refresh

    env = json.loads((ROOT / ".local/reliability-env.json").read_text())
    if (
        env.get("KEDROGY_TEST_DATABASE") != "disposable"
        or env["PGDATABASE"] != "reliability"
    ):
        raise ValueError("Only the disposable reliability database is permitted.")
    os.environ.update(env)
    os.environ["KUBECONFIG"] = str(Path.home() / ".kube/config")
    subprocess.run(["kubectl", "create", "namespace", NAMESPACE], check=True)
    subprocess.run(
        ["kubectl", "-n", NAMESPACE, "apply", "-f", "infra/rbac.json"], check=True
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
    digest = subprocess.check_output(
        ["docker", "image", "inspect", ML_TAG, "--format", "{{.Id}}"], text=True
    ).strip()
    image = "kedrogy-registry:5000/mykedro@" + digest
    cluster_db = {key: value for key, value in env.items() if key.startswith("PG")} | {
        "PGHOST": ip,
        "PGPORT": "5432",
    }
    # Fixture credentials are generated for this disposable database, never copied from the application.
    for kind in ["app", "migrator", "reader"]:
        apply_secret("kedrogy-db-" + kind, cluster_db, NAMESPACE)
    import secrets

    apply_secret(
        "kedrogy-app-config",
        {"DJANGO_SECRET_KEY": secrets.token_urlsafe(64), "KEDROGY_ML_IMAGE": image},
        NAMESPACE,
    )
    os.environ["DJANGO_SETTINGS_MODULE"] = "mysite.test_postgres_settings"
    import django

    django.setup()
    from django.core.management import call_command

    call_command("migrate", verbosity=0)
    with psycopg.connect() as conn:
        conn.execute("CREATE TABLE dataset (id serial PRIMARY KEY, name text)")
        conn.execute("CREATE TABLE example (id serial PRIMARY KEY, content bytea)")
        conn.execute("CREATE TABLE link (dataset_id int, example_id int)")
        conn.execute("INSERT INTO dataset(name) VALUES ('reliability-fixture')")
        for index in range(24):
            label = "positive" if index % 2 else "negative"
            value = {
                "text": "good product" if label == "positive" else "bad product",
                "label": label,
                "answer": "accept" if index % 5 else "reject",
            }
            record = conn.execute(
                "INSERT INTO example(content) VALUES (%s) RETURNING id",
                (json.dumps(value).encode(),),
            ).fetchone()[0]
            conn.execute("INSERT INTO link VALUES (1, %s)", (record,))
    scoped = ROOT / ".local/reliability-kubeconfig.json"
    refresh(
        admin_config=Path.home() / ".kube/config", output=scoped, namespace=NAMESPACE
    )
    env |= {
        "KUBECONFIG": str(scoped),
        "KEDROGY_NAMESPACE": NAMESPACE,
        "KEDROGY_ML_IMAGE": image,
        "DJANGO_SETTINGS_MODULE": "mysite.test_postgres_settings",
    }
    path = ROOT / ".local/reliability-env.json"
    path.write_text(json.dumps(env))
    path.chmod(0o600)
    print("Synthetic fixture ready; no working records copied.")


if __name__ == "__main__":
    setup()
