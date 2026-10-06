"""Bounded subprocess execution and Kubernetes access without shell commands."""

import json
import logging
import os
import re
import selectors
import signal
import subprocess
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

from django.conf import settings

logger = logging.getLogger(__name__)
OUTPUT_LIMIT = 64 * 1024


class OperationError(RuntimeError):
    """A public, credential-free operation failure."""

    def __init__(self, code: str, message: str, *, returncode: int | None = None):
        self.code = code
        self.returncode = returncode
        super().__init__(message)

    def public(self) -> dict:
        return {"code": self.code, "message": str(self)}


@dataclass(frozen=True)
class CommandResult:
    """Private command output; never serialize directly into task metadata."""

    stdout: str = field(repr=False)
    stderr: str = field(repr=False)
    returncode: int
    duration: float
    truncated: bool = False


def redact(value: str) -> str:
    """Filter known credentials and common credential-bearing representations."""
    secrets = [
        value for key, value in os.environ.items()
        if value and any(part in key.upper() for part in ("PASSWORD", "SECRET", "TOKEN", "UV_INDEX_"))
    ]
    for secret in sorted(secrets, key=len, reverse=True):
        value = value.replace(secret, "[redacted]")
    value = re.sub(r"(?i)\b[a-z][a-z0-9+.-]*://[^\s/]+:[^\s@]+@", "[redacted]@", value)
    value = re.sub(r"(?i)((?:password|token|secret|authorization)\s*[=:]\s*)[^\s,}]+",
                   r"\1[redacted]", value)
    return value


def stop_process(process: subprocess.Popen) -> None:
    """Reap the child and terminate its process group, including inherited pipes."""
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            pass
        if sig == signal.SIGTERM:
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                continue
        # A child can have exited while one of its descendants still owns a pipe.
    process.wait(timeout=5)


def _failure(returncode: int, stderr: str) -> OperationError:
    text = stderr.lower()
    if "forbidden" in text or "unauthorized" in text:
        return OperationError("CLUSTER_ACCESS_DENIED", "Kubernetes access was denied. Refresh the controller credentials or check RBAC.", returncode=returncode)
    if any(word in text for word in ("connection refused", "unable to connect", "i/o timeout")):
        return OperationError("CLUSTER_UNAVAILABLE", "The Kubernetes API is unavailable.", returncode=returncode)
    if "notfound" in text or "not found" in text:
        return OperationError("RESOURCE_NOT_FOUND", "The Kubernetes resource was not found.", returncode=returncode)
    if "alreadyexists" in text:
        return OperationError("RESOURCE_EXISTS", "The Kubernetes resource already exists.", returncode=returncode)
    return OperationError("COMMAND_FAILED", f"Kubernetes operation failed (exit {returncode}).", returncode=returncode)


def execute(argv: list[str], *, input_text: str | None = None, timeout: float = 30,
            limit: int = OUTPUT_LIMIT, strict_output: bool = False) -> CommandResult:
    """Drain both pipes with bounded memory and always reap a timed-out child."""
    start = time.monotonic()
    tails = {"stdout": bytearray(), "stderr": bytearray()}
    totals = {"stdout": 0, "stderr": 0}
    # An unlinked temporary stdin avoids deadlock when the child emits before reading.
    with tempfile.TemporaryFile() as stdin, selectors.DefaultSelector() as selector:
        stdin.write((input_text or "").encode())
        stdin.seek(0)
        try:
            process = subprocess.Popen(argv, stdin=stdin, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, start_new_session=True)
        except OSError:
            raise OperationError("PROCESS_START_FAILED", "Cannot start the operation. Check the executable and configuration.") from None
        try:
            for name in tails:
                stream = getattr(process, name)
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, name)
            while selector.get_map() or process.poll() is None:
                remaining = timeout - (time.monotonic() - start)
                if remaining <= 0:
                    raise OperationError("OPERATION_TIMEOUT", "The operation exceeded its time limit.")
                for key, _ in selector.select(min(remaining, 0.2)):
                    chunk = os.read(key.fd, 8192)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    name = key.data
                    totals[name] += len(chunk)
                    tails[name].extend(chunk)
                    del tails[name][:-limit]
                    if strict_output and totals[name] > limit:
                        raise OperationError("OUTPUT_LIMIT", "The operation returned more data than allowed.")
            result = CommandResult(
                stdout=tails["stdout"].decode(errors="replace"),
                stderr=tails["stderr"].decode(errors="replace"),
                returncode=process.wait(), duration=time.monotonic() - start,
                truncated=any(count > limit for count in totals.values()),
            )
            if result.returncode:
                # Arbitrary stderr can contain rejected manifests. Log classification only.
                error = _failure(result.returncode, result.stderr)
                logger.warning("Operation failed code=%s exit=%s duration=%.3f",
                               error.code, result.returncode, result.duration)
                raise error
            return result
        finally:
            stop_process(process)
            process.stdout.close()
            process.stderr.close()


def command(args: list[str], *, namespace: str | None = None, document: dict | None = None,
            timeout: float = 30, json_output: bool = False) -> str | dict:
    """Run kubectl against a named namespace and parse bounded JSON when requested."""
    result = execute(
        ["kubectl", "--namespace", namespace or settings.KEDROGY_NAMESPACE, *args],
        input_text=json.dumps(document) if document is not None else None,
        timeout=timeout, limit=2 * 1024 * 1024 if json_output else OUTPUT_LIMIT,
        strict_output=json_output,
    )
    if not json_output:
        return result.stdout.strip()
    try:
        return json.loads(result.stdout)
    except (ValueError, TypeError):
        raise OperationError("INVALID_CLUSTER_RESPONSE", "Kubernetes returned an invalid response.") from None


@contextmanager
def service_tunnel(resource: str, port: int, *, path: str = "", timeout: float = 15, namespace: str | None = None):
    """Reserve an OS-selected loopback port and close the tunnel on every exit."""
    argv = ["kubectl", "--namespace", namespace or settings.KEDROGY_NAMESPACE, "port-forward",
            "--address=127.0.0.1", resource, f":{port}"]
    try:
        process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True)
    except OSError:
        raise OperationError("PROCESS_START_FAILED", "Cannot start the prediction tunnel.") from None
    try:
        deadline = time.monotonic() + timeout
        output = bytearray()
        with selectors.DefaultSelector() as selector:
            for stream in (process.stdout, process.stderr):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ)
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise OperationError("TUNNEL_FAILED", "The prediction tunnel could not start.")
                for key, _ in selector.select(min(0.2, max(0, deadline - time.monotonic()))):
                    chunk = os.read(key.fd, 8192)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    output.extend(chunk)
                    del output[:-OUTPUT_LIMIT]
                    match = re.search(rb"Forwarding from 127\.0\.0\.1:(\d+)", output)
                    if match:
                        yield f"http://127.0.0.1:{int(match[1])}{path}"
                        return
            raise OperationError("TUNNEL_TIMEOUT", "The prediction tunnel did not become ready in time.")
    finally:
        stop_process(process)
        process.stdout.close()
        process.stderr.close()


@contextmanager
def port_forward(model_id: int, *, timeout: float = 15, namespace: str | None = None):
    with service_tunnel(f"service/serve-svc-{model_id}", 8888, path="/predict", timeout=timeout, namespace=namespace) as url:
        yield url
