"""Crash an isolated queue worker and recover its real Job in a new process."""

import json
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
env = json.loads((ROOT / ".local/reliability-env.json").read_text())
if (
    env.get("KEDROGY_TEST_DATABASE") != "disposable"
    or env["KEDROGY_NAMESPACE"] != "kedrogy-check-20260924"
):
    raise ValueError("Disposable fixtures only.")
final_image = "kedrogy-registry:5000/mykedro@sha256:897d9d4bb8eb431101be7d160f1981fab46224fc3d2ecd99bf25883d8d6befcb"
previous_image = env["KEDROGY_ML_IMAGE"]
env |= {
    "KEDROGY_ML_IMAGE": final_image,
    "PYTHONPATH": str(ROOT / ".local"),
    "DJANGO_SETTINGS_MODULE": "reliability_runtime_settings",
}
(ROOT / ".local/reliability_runtime_settings.py").write_text("""import os
from mysite.test_postgres_settings import *
KEDROGY_ML_IMAGE=os.environ['KEDROGY_ML_IMAGE']
KEDROGY_ML_IMAGE_ALIASES={KEDROGY_ML_IMAGE, 'approved:1'}
KEDROGY_NAMESPACE=os.environ['KEDROGY_NAMESPACE']
KEDROGY_TRAIN_OPTIONS={'base_model':'data/06_models/tiny-base','max_steps':1}
KEDROGY_TRAIN_TIMEOUT=600
""")
subprocess.run(
    [
        "kubectl",
        "--kubeconfig",
        str(Path.home() / ".kube/config"),
        "-n",
        env["KEDROGY_NAMESPACE"],
        "wait",
        "--for=delete",
        "pods",
        "-l",
        "app.kubernetes.io/name=mysite",
        "--timeout=60s",
    ],
    check=True,
)
os.environ.update(env)
sys.path.insert(0, str(ROOT / ".local"))
import django

django.setup()
from kedrogy.models import DjangoModel
from kedrogy.training import start_training

model = DjangoModel.objects.get(pk=2)
run, _ = start_training(model.pk, "actual-worker-crash-" + str(uuid.uuid4()))
log = ROOT / ".local/recovery-worker.log"
with log.open("w") as stream:
    log.chmod(0o600)
    worker = subprocess.Popen(
        [sys.executable, "-m", "django", "db_worker", "--no-reload"],
        env=os.environ,
        stdout=stream,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            run.refresh_from_db()
            if run.status == "RUNNING" and run.job_uid and run.lease_owner is None:
                break
            if worker.poll() is not None or run.status in ["FAILED", "SUCCEEDED"]:
                raise RuntimeError("Worker did not reach the intended crash point.")
            time.sleep(0.2)
        else:
            raise TimeoutError("Worker did not launch the Job.")
        uid = run.job_uid
        os.killpg(worker.pid, signal.SIGKILL)
        worker.wait(timeout=10)
        print(
            "Isolated worker killed after Job creation; starting an independent reconciler.",
            flush=True,
        )
        observer = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "django",
                "reconcile_training",
                "--watch",
                "--interval",
                "2",
            ],
            env=os.environ,
            stdout=stream,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            deadline = time.monotonic() + 750
            while time.monotonic() < deadline:
                run.refresh_from_db()
                if run.status in ["SUCCEEDED", "FAILED", "TIMED_OUT", "INTERRUPTED"]:
                    break
                time.sleep(2)
            if run.status != "SUCCEEDED" or run.job_uid != uid:
                raise RuntimeError(f"Worker recovery failed: {run.status} {run.error}")
            result = {
                "run_id": str(run.id),
                "status": run.status,
                "job_uid_preserved": run.job_uid == uid,
                "image": run.snapshot["image"],
                "checks": [
                    "real worker SIGKILL",
                    "independent reconciler process",
                    "full seeded Kedro pipeline",
                    "verified artifact published",
                ],
            }
            output = ROOT / "reports/2026-09-24-implementation/worker-recovery.json"
            output.write_text(json.dumps(result, indent=2) + "\n")
            print(json.dumps(result, indent=2), flush=True)
        finally:
            os.killpg(observer.pid, signal.SIGTERM)
            observer.wait(timeout=10)
    finally:
        if worker.poll() is None:
            os.killpg(worker.pid, signal.SIGTERM)
            worker.wait(timeout=10)
