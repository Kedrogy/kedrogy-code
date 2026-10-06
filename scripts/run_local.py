"""Run one local service with private environment files and scoped Kubernetes access."""

import argparse
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path

from dotenv import dotenv_values


def supervise(argv):
    """Restart a crashed worker, but reap its entire process group on shutdown."""
    stopping = threading.Event()
    child = None

    def stop(signum, frame):
        stopping.set()

    previous = {sig: signal.signal(sig, stop) for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        while not stopping.is_set():
            child = subprocess.Popen(argv, start_new_session=True)
            while child.poll() is None and not stopping.wait(0.2):
                pass
            if stopping.is_set():
                break
            if child.returncode == 0:
                return
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            print("Queue worker exited; restarting in five seconds.", flush=True)
            stopping.wait(5)
    finally:
        if child is not None:
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait(timeout=5)
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('service', choices=('api', 'worker', 'training', 'serving', 'operations'))
    parser.add_argument('--port', type=int, default=8002)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    os.environ.update({key: value for key, value in dotenv_values(root / '.env').items() if value is not None})
    os.environ['DJANGO_SETTINGS_MODULE'] = 'mysite.settings_local'
    os.environ['KUBECONFIG'] = str(root / '.local/kubeconfig.json')
    if args.service == 'api':
        import uvicorn
        uvicorn.run('mysite.asgi:application', host='127.0.0.1', port=args.port, proxy_headers=False)
    else:
        from django.core.management import execute_from_command_line
        commands = {'worker': ['db_worker', '--no-reload'], 'training': ['reconcile_training', '--watch'],
                    'serving': ['reconcile_serving', '--watch'], 'operations': ['reconcile_operations', '--watch']}
        if args.service == "worker":
            # A crashed database worker is restarted; historical tasks are never requeued here.
            supervise([sys.executable, "-m", "django", *commands["worker"]])
            return
        execute_from_command_line(['django', *commands[args.service]])


if __name__ == '__main__':
    main()
