"""One-command dev environment (R0.4, modeled on openhanako's dev-web.js).

Starts the full two-process stack against a throwaway data directory:

    .venv\\Scripts\\python.exe scripts/dev.py --frontend   # backend + vite
    .venv\\Scripts\\python.exe scripts/dev.py              # backend only

Isolation guarantees:
- BOBODAN_HOME points at ~/.bobodan-dev so provider catalogs, preferences
  and usage ledgers never touch the real profile (--fresh wipes it).
- The backend port is pre-picked as a free ephemeral port and, once
  /api/health answers, the handshake file
  ~/.bobodan-dev/server-info.json ({port, pid, started_at}) is written for
  external tools (tests, scripts) to discover the stack.
- Vite's /api proxy target is injected through BOBODAN_API_URL.
- Either process exiting tears the other one down (Ctrl+C included), so no
  orphaned servers linger to confuse the next run.
"""

from __future__ import annotations

import argparse
import atexit
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INFO_FILE_NAME = "server-info.json"

_PROCESSES: list[subprocess.Popen] = []


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _health_ok(port: int, timeout_s: float = 60.0) -> bool:
    deadline = time.time() + timeout_s
    url = f"http://127.0.0.1:{port}/api/health"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return True
        except OSError:
            pass
        if poll_processes() is not None:
            return False
        time.sleep(0.2)
    return False


def poll_processes() -> int | None:
    """Return the exit code of the first dead child, or None while all live."""
    for proc in _PROCESSES:
        code = proc.poll()
        if code is not None:
            return code
    return None


def _teardown() -> None:
    for proc in _PROCESSES:
        if proc.poll() is None:
            proc.terminate()
    for proc in _PROCESSES:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Bobodan dev stack (isolated data dir)")
    parser.add_argument("--frontend", action="store_true", help="Also start the Vite dev server")
    parser.add_argument("--fresh", action="store_true", help="Wipe ~/.bobodan-dev before starting")
    args = parser.parse_args()

    dev_home = Path.home() / ".bobodan-dev"
    if args.fresh and dev_home.exists():
        shutil.rmtree(dev_home)
    dev_home.mkdir(parents=True, exist_ok=True)

    port = _pick_free_port()
    env = os.environ.copy()
    env["BOBODAN_HOME"] = str(dev_home)

    backend = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "web.backend.app:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=REPO_ROOT,
        env=env,
    )
    _PROCESSES.append(backend)
    atexit.register(_teardown)

    print(f"[dev] waiting for backend on port {port}…")
    if not _health_ok(port):
        code = poll_processes()
        print(f"[dev] backend never became healthy (exit={code})", file=sys.stderr)
        return 1

    info = {"port": port, "pid": backend.pid, "started_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    (dev_home / INFO_FILE_NAME).write_text(json.dumps(info, indent=2), encoding="utf-8")
    print(f"[dev] backend ready on http://127.0.0.1:{port} (data: {dev_home})")

    if args.frontend:
        frontend_env = env.copy()
        frontend_env["BOBODAN_API_URL"] = f"http://127.0.0.1:{port}"
        frontend = subprocess.Popen(
            ["npm", "run", "dev"],
            cwd=REPO_ROOT / "web" / "frontend",
            env=frontend_env,
            shell=os.name == "nt",  # npm is a .cmd shim on Windows
        )
        _PROCESSES.append(frontend)
        print("[dev] vite starting on http://127.0.0.1:5173 (Ctrl+C stops both)")

    try:
        while True:
            code = poll_processes()
            if code is not None:
                print(f"[dev] a child exited with code {code}; tearing down")
                return code or 0
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[dev] stopping…")
        return 0
    finally:
        _teardown()


if __name__ == "__main__":
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, signal.default_int_handler)
    raise SystemExit(main())
