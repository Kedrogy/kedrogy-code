"""Check actual network isolation in the disposable deployment fixture."""

import json
import subprocess
import uuid
from pathlib import Path

NAMESPACE = "kedrogy-check-20260924"


def kubectl(*args, document=None):
    return subprocess.check_output(
        ["kubectl", "-n", NAMESPACE, *args],
        input=json.dumps(document) if document else None,
        text=True,
        timeout=60,
    )


def main():
    backend = json.loads(kubectl("get", "service/mysite-svc", "-o", "json"))
    web = json.loads(kubectl("get", "service/kedrogy-web", "-o", "json"))
    pods = json.loads(
        kubectl("get", "pods", "-l", "app.kubernetes.io/name=mysite", "-o", "json")
    )["items"]
    ready = [
        pod
        for pod in pods
        if not pod["metadata"].get("deletionTimestamp")
        and any(
            condition["type"] == "Ready" and condition["status"] == "True"
            for condition in pod["status"].get("conditions", [])
        )
    ]
    if len(ready) != 1:
        raise RuntimeError("The fixture backend must be healthy before probing.")
    targets = [
        (backend["spec"]["clusterIP"], 8000),
        (ready[0]["status"]["podIP"], 8000),
        (web["spec"]["clusterIP"], 8080),
    ]
    # Allow the network controller to attach rules to the new probe Pod.
    code = """import errno,json,socket,time
time.sleep(10)
targets=TARGETS
results=[]
for host,port in targets:
    try:
        connection=socket.create_connection((host,port),timeout=4)
    except OSError as error:
        if not isinstance(error,TimeoutError) and error.errno not in {errno.EHOSTUNREACH,errno.ENETUNREACH,errno.ECONNREFUSED}:
            raise
        results.append({'host':host,'port':port,'blocked':True})
    else:
        connection.close()
        results.append({'host':host,'port':port,'blocked':False})
print(json.dumps(results),flush=True)
raise SystemExit(0 if all(result['blocked'] for result in results) else 1)
""".replace("TARGETS", repr(targets))
    image = json.loads(
        Path("reports/2026-09-24-implementation/release-images.json").read_text()
    )["backend"]
    name = "direct-denied-" + uuid.uuid4().hex[:8]
    job = {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {"name": name, "namespace": NAMESPACE},
        "spec": {
            "backoffLimit": 0,
            "activeDeadlineSeconds": 90,
            "template": {
                "spec": {
                    "restartPolicy": "Never",
                    "automountServiceAccountToken": False,
                    "containers": [
                        {
                            "name": "probe",
                            "image": image,
                            "command": ["/app/.venv/bin/python", "-c", code],
                        }
                    ],
                }
            },
        },
    }
    kubectl("create", "-f", "-", document=job)
    try:
        kubectl("wait", "--for=condition=complete", f"job/{name}", "--timeout=50s")
    finally:
        output = kubectl("logs", f"job/{name}")
        print(output, end="")
    results = json.loads(output)
    if not all(result["blocked"] for result in results):
        raise RuntimeError("Network policy enforcement failed.")
    report = {
        "namespace": NAMESPACE,
        "checks": results,
        "note": "An initial probe passed through after Docker restarted. The local node was restarted before this repeat. HTTPS route checks must also pass to prove the service is healthy.",
    }
    Path("reports/2026-09-24-implementation/network-runtime.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
