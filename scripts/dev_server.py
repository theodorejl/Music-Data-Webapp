"""Keep the app running whatever changes: supervises `streamlit run app/Home.py`.

- Code (app/, core/): reloaded in place by app/devreload.py, no restart.
- Settings (.streamlit/config.toml, .env): the app is restarted on its own.
- Libraries (requirements.txt): installed, then the app is restarted.
- A crash: the app is restarted (with a growing pause if it keeps crashing).
The browser reconnects by itself after a restart.

Usage: python -m scripts.dev_server [--port 8501]
"""

from __future__ import annotations

import argparse
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESTART_ON = [ROOT / ".streamlit" / "config.toml", ROOT / ".env"]
REQUIREMENTS = ROOT / "requirements.txt"


def _mtimes(paths: list[Path]) -> dict[Path, float]:
    return {p: (p.stat().st_mtime if p.exists() else 0.0) for p in paths}


def _start(port: int) -> subprocess.Popen:
    cmd = [sys.executable, "-m", "streamlit", "run", "app/Home.py", "--server.port", str(port),
           "--server.headless", "true"]
    return subprocess.Popen(cmd, cwd=ROOT)


def _stop(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8501)
    args = parser.parse_args()

    proc = _start(args.port)
    stopping = False

    def on_signal(*_):
        nonlocal stopping
        stopping = True
        _stop(proc)
        sys.exit(0)

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    watched = _mtimes(RESTART_ON + [REQUIREMENTS])
    pause = 2.0
    while not stopping:
        time.sleep(1.0)
        now = _mtimes(RESTART_ON + [REQUIREMENTS])
        if now != watched:
            time.sleep(1.5)  # let the edit finish
            now = _mtimes(RESTART_ON + [REQUIREMENTS])
            if now[REQUIREMENTS] != watched[REQUIREMENTS]:
                print("[dev_server] requirements.txt changed: installing…", flush=True)
                subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", str(REQUIREMENTS)], cwd=ROOT)
            print("[dev_server] settings changed: restarting the app…", flush=True)
            watched = now
            _stop(proc)
            proc = _start(args.port)
            pause = 2.0
        elif proc.poll() is not None:
            print(f"[dev_server] the app stopped (code {proc.returncode}): restarting in {pause:.0f} s…", flush=True)
            time.sleep(pause)
            pause = min(pause * 2, 60.0)
            proc = _start(args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
