#!/usr/bin/env python3
"""Launch backend (uvicorn --reload) + frontend (npm run dev) in one terminal.

This project uses fixed ports — backend 8765, frontend 3015 — so it never
collides with other apps running locally. Streams both processes' output
prefixed with [BACK] / [FRONT]. Ctrl+C stops both.

Usage:
    python3 scripts/dev.py
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = REPO_ROOT / "frontend"

BACKEND_PORT = 8765
FRONTEND_PORT = 3015

# ANSI colors — no-op if not a TTY
_TTY = sys.stdout.isatty()
def _color(code: str, text: str) -> str:
    return f"\x1b[{code}m{text}\x1b[0m" if _TTY else text

PREFIX_BACK = _color("36", "[BACK ]")   # cyan
PREFIX_FRONT = _color("35", "[FRONT]")  # magenta
PREFIX_DEV = _color("33", "[DEV  ]")    # yellow


def _stream(stream, prefix: str) -> None:
    """Pipe lines from a child process stream to stdout with a prefix."""
    try:
        for raw in iter(stream.readline, b""):
            try:
                line = raw.decode("utf-8", errors="replace").rstrip("\n")
            except Exception:
                line = repr(raw)
            print(f"{prefix} {line}", flush=True)
    except Exception:
        pass


def _spawn(cmd: list[str], cwd: Path, prefix: str, env: dict[str, str] | None = None) -> subprocess.Popen:
    print(f"{PREFIX_DEV} starting: {' '.join(cmd)}  (cwd={cwd})", flush=True)
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=0,
        env={**os.environ, **(env or {})},
        # New process group so we can SIGTERM the whole tree (npm spawns next-server)
        start_new_session=True,
    )
    threading.Thread(target=_stream, args=(proc.stdout, prefix), daemon=True).start()
    return proc


def _terminate(proc: subprocess.Popen, label: str) -> None:
    if proc.poll() is not None:
        return
    print(f"{PREFIX_DEV} stopping {label} (pid={proc.pid})…", flush=True)
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        print(f"{PREFIX_DEV} {label} did not exit — sending SIGKILL", flush=True)
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass


def main() -> int:
    if not FRONTEND_DIR.exists():
        print(f"{PREFIX_DEV} frontend dir missing: {FRONTEND_DIR}", file=sys.stderr)
        return 1

    backend_url = f"http://localhost:{BACKEND_PORT}"
    backend_cmd = [sys.executable, "-m", "uvicorn", "backend.main:app", "--reload", "--port", str(BACKEND_PORT)]
    frontend_cmd = ["npm", "run", "dev", "--", "--port", str(FRONTEND_PORT)]

    backend = _spawn(backend_cmd, REPO_ROOT, PREFIX_BACK)
    # Pass BACKEND_URL so the Next.js proxy uses our uvicorn even if .env.local drifts.
    frontend = _spawn(frontend_cmd, FRONTEND_DIR, PREFIX_FRONT, env={"BACKEND_URL": backend_url})

    print(
        f"{PREFIX_DEV} backend → {backend_url}   "
        f"frontend → http://localhost:{FRONTEND_PORT}   "
        f"(Ctrl+C to stop)",
        flush=True,
    )

    try:
        while True:
            for label, proc in (("backend", backend), ("frontend", frontend)):
                rc = proc.poll()
                if rc is not None:
                    print(
                        f"{PREFIX_DEV} {label} exited (code={rc}) — shutting down the other",
                        flush=True,
                    )
                    _terminate(backend if label == "frontend" else frontend, "the other")
                    return rc or 1
            time.sleep(0.5)
    except KeyboardInterrupt:
        print(f"\n{PREFIX_DEV} Ctrl+C received — shutting down both", flush=True)
    finally:
        _terminate(frontend, "frontend")
        _terminate(backend, "backend")

    return 0


if __name__ == "__main__":
    sys.exit(main())
