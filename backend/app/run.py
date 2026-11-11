"""Supervise demo web/worker processes so child failures restart the container."""
import os
import signal
import subprocess
import sys
import time
from app.migrate import main as migrate


def main():
    migrate()
    children = []
    stopping = False
    def stop(*_):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        if os.getenv("RUN_CELERY_IN_WEB", "false").lower() == "true":
            children.append(subprocess.Popen([sys.executable, "-m", "celery", "-A", "app.celery_app:celery_app", "worker", "-B", "-l", "info", "--pool=solo", "--concurrency=1"]))
        children.append(subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", os.getenv("PORT", "8000"), "--no-proxy-headers"]))
        while not stopping:
            if any(child.poll() is not None for child in children):
                raise RuntimeError("A supervised service exited; restarting the container.")
            time.sleep(0.5)
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == "__main__":
    main()
