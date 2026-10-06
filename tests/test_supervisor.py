"""Verify the local worker supervisor stops its actual child process group."""

import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


class SupervisorTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "posix", "Process groups require POSIX.")
    def test_shutdown_reaps_worker_and_descendant(self):
        root = Path(__file__).resolve().parents[1]
        python = root / "mysite/.venv/bin/python"
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "pids"
            child = "import os,time,subprocess,sys; from pathlib import Path; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); Path(sys.argv[1]).write_text(f'{os.getpid()} {p.pid}'); time.sleep(60)"
            supervisor = subprocess.Popen([str(python), "-c",
                "import sys; from scripts.run_local import supervise; supervise(sys.argv[1:])",
                sys.executable, "-c", child, str(marker)], cwd=root)
            try:
                deadline = time.monotonic() + 10
                while not marker.exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue(marker.exists(), "The test worker never started.")
                pids = [int(value) for value in marker.read_text().split()]
                supervisor.send_signal(signal.SIGTERM)
                self.assertEqual(supervisor.wait(timeout=10), 0)
                for pid in pids:
                    deadline = time.monotonic() + 5
                    while time.monotonic() < deadline:
                        try:
                            os.kill(pid, 0)
                        except ProcessLookupError:
                            break
                        time.sleep(0.02)
                    else:
                        self.fail("A supervised process survived shutdown.")
            finally:
                if supervisor.poll() is None:
                    supervisor.kill()
                    supervisor.wait(timeout=5)
                if marker.exists():
                    for value in marker.read_text().split():
                        try:
                            os.kill(int(value), signal.SIGKILL)
                        except ProcessLookupError:
                            pass
