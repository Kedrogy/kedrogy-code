"""Verify real kubectl tunnel cleanup after a prediction transport failure."""

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch


def main():
    env = json.loads(Path(".local/reliability-env.json").read_text())
    if env.get("KEDROGY_NAMESPACE") != "kedrogy-check-20260924":
        raise ValueError("Disposable fixtures only.")
    os.environ.update(env)
    import django

    django.setup()
    from django.conf import settings
    from kedrogy.kubernetes import OperationError, command
    from kedrogy.prediction import predict

    settings.KEDROGY_NAMESPACE = env["KEDROGY_NAMESPACE"]
    service = {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {"name": "serve-svc-9999"},
        "spec": {
            "selector": {"app.kubernetes.io/name": "mysite"},
            "ports": [{"port": 8888, "targetPort": 8000}],
        },
    }
    command(["create", "-f", "-"], document=service)
    processes = []
    real_popen = subprocess.Popen

    def observe(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        processes.append(process)
        return process

    try:
        # The fixture backend is deliberately not an inference HTTP service.
        with patch("kedrogy.kubernetes.subprocess.Popen", side_effect=observe):
            try:
                predict(9999, "Synthetic transport check")
            except OperationError as error:
                if error.code != "PREDICTION_UNAVAILABLE":
                    raise
            else:
                raise RuntimeError("The invalid inference endpoint should fail.")
        if len(processes) != 1 or processes[0].poll() is None:
            raise RuntimeError("The real tunnel process was not reaped.")
        if not processes[0].stdout.closed or not processes[0].stderr.closed:
            raise RuntimeError("The tunnel left output pipes open.")
        report = {
            "transport_error": "PREDICTION_UNAVAILABLE",
            "real_port_forward_reaped": True,
            "pipes_closed": True,
        }
        Path("reports/2026-09-24-implementation/tunnel-runtime.json").write_text(
            json.dumps(report, indent=2) + "\n"
        )
        print(json.dumps(report))
    finally:
        command(["delete", "service/serve-svc-9999", "--wait=false"])


if __name__ == "__main__":
    main()
