"""Test supervisor SIGTERM using only an inert child; no working services touched."""

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path


root = Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix="kedrogy-supervisor-audit-") as directory:
    pidfile = Path(directory) / "child.pid"
    wrapper = f"""
import sys, subprocess
sys.path.insert(0, {str(root / 'scripts')!r})
import run_local
run_local.dotenv_values = lambda *args: {{}}
original_run = subprocess.run
def inert_worker(*args, **kwargs):
    return original_run([sys.executable, '-c', {f'import os, time; from pathlib import Path; Path({str(pidfile)!r}).write_text(str(os.getpid())); time.sleep(30)'!r}], check=False)
run_local.subprocess.run = inert_worker
sys.argv = ['run_local.py', 'worker']
run_local.main()
"""
    parent = subprocess.Popen([sys.executable, "-c", wrapper], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    child = None
    try:
        deadline = time.monotonic()+5
        while not pidfile.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        if not pidfile.exists():
            raise RuntimeError("Synthetic child did not start.")
        child = int(pidfile.read_text())
        parent.terminate()
        parent.wait(timeout=5)
        os.kill(child, 0)
        print(json.dumps({"supervisor_exit": parent.returncode, "child_survived_sigterm": True, "scope": "synthetic child only"}))
    finally:
        try:
            os.killpg(parent.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        parent.wait(timeout=5)
