"""Check the isolated TLS deployment using its ephemeral test CA."""

import json
import subprocess
import tempfile
from pathlib import Path

checks = []


def request(
    path, *, host="app.kedrogy.test", method="GET", expected=200, headers=None, tls=True
):
    with tempfile.TemporaryDirectory() as folder:
        body = Path(folder) / "body"
        response_headers = Path(folder) / "headers"
        args = [
            "curl",
            "--silent",
            "--show-error",
            "--max-time",
            "15",
            "-X",
            method,
            "-D",
            str(response_headers),
            "-o",
            str(body),
            "-w",
            "%{http_code}",
        ]
        if tls:
            args += [
                "--cacert",
                ".local/tls-check/tls.crt",
                "--resolve",
                f"{host}:8443:127.0.0.1",
                f"https://{host}:8443{path}",
            ]
        else:
            args += ["-H", f"Host: {host}", f"http://127.0.0.1:18002{path}"]
        for header in headers or []:
            args += ["-H", header]
        result = subprocess.check_output(args, text=True)
        if int(result) != expected:
            raise RuntimeError(
                f"{method} {host}{path}: expected {expected}, received {result}"
            )
        content = body.read_text(errors="replace")
        if "Traceback (most recent call last)" in content:
            raise RuntimeError("Traceback leaked into HTTP response.")
        checks.append(
            {
                "path": path,
                "host": host,
                "method": method,
                "status": int(result),
                "tls": tls,
            }
        )
        return content, response_headers.read_text()


html, _ = request("/")
if "root" not in html:
    raise RuntimeError("Frontend was not served.")
import re

asset = re.search(r'src="(/assets/[^\"]+)"', html)
if not asset:
    raise RuntimeError("Frontend asset missing.")
request(asset.group(1))
request("/static/admin/css/base.css")
request("/health/")
request("/api/models/")
body, _ = request("/api/does-not-exist/", expected=404)
if not json.loads(body).get("error"):
    raise RuntimeError("API error is not JSON.")
request("/train_model/2/", method="HEAD", expected=405)
request("/train_model/2/", method="POST", expected=403)
request("/legacy/")
request("/admin/login/")
request("/", host="label.kedrogy.test")
request("/api/models/", tls=False, headers=["X-Forwarded-Proto: https"], expected=301)
body, _ = request("/api/models/", host="unapproved.invalid", tls=False, expected=400)
if not json.loads(body).get("request_id"):
    raise RuntimeError("API boundary omitted request ID.")
# The ingress must redirect cleartext requests before they reach the application.
status = subprocess.check_output(
    [
        "curl",
        "--silent",
        "--max-time",
        "15",
        "-o",
        "/dev/null",
        "-w",
        "%{http_code}",
        "-H",
        "Host: app.kedrogy.test",
        "http://127.0.0.1:8081/",
    ],
    text=True,
)
if status not in {"301", "308"}:
    raise RuntimeError("Ingress did not redirect HTTP.")
checks.append({"check": "ingress HTTP redirect", "status": int(status)})
output = Path("reports/2026-09-24-implementation/http-runtime.json")
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(checks, indent=2) + "\n")
print(f"{len(checks)} real HTTP/TLS checks passed.")
