"""Report run identity only while the local Prodigy HTTP application responds."""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import URLError
from urllib.request import urlopen


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        ready = self.path == "/livez"
        if self.path == "/readyz":
            try:
                with urlopen("http://127.0.0.1:8080/", timeout=2) as response:
                    ready = response.status == 200
            except (URLError, TimeoutError, OSError):
                ready = False
        result = {"ready": ready, "annotation_run_id": os.environ["KEDROGY_ANNOTATION_RUN_ID"],
                  "dataset_key": os.environ["KEDROGY_ANNOTATION_DATASET"]}
        content = json.dumps(result).encode()
        self.send_response(200 if ready else 503)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, *_args):
        """Health probes must not log request content."""


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8081), HealthHandler).serve_forever()
