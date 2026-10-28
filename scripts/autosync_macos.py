"""Background sync on macOS (launchd): runs the sync every 30 minutes, even when the
app is closed, as long as the Mac is on (a run missed during sleep happens on wake).

Usage:
    python -m scripts.autosync_macos install     # install + start
    python -m scripts.autosync_macos uninstall
    python -m scripts.autosync_macos status
"""

from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from pathlib import Path

from core.config import ROOT

LABEL = "com.deezerstats.autosync"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
LOG = ROOT / "logs" / "autosync.log"
INTERVAL = 1800  # seconds


def _domain() -> str:
    return f"gui/{os.getuid()}"


def install() -> None:
    python = ROOT / ".venv" / "bin" / "python"
    if not python.exists():
        sys.exit(f"Virtual environment not found: {python}")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    plist = {
        "Label": LABEL,
        "ProgramArguments": [str(python), "-m", "scripts.sync", "--enrich-budget", "90"],
        "WorkingDirectory": str(ROOT),
        "StartInterval": INTERVAL,
        "RunAtLoad": True,
        "ProcessType": "Background",
        "LowPriorityIO": True,
        "StandardOutPath": str(LOG),
        "StandardErrorPath": str(LOG),
        "EnvironmentVariables": {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "PYTHONUNBUFFERED": "1"},
    }
    subprocess.run(["launchctl", "bootout", _domain(), str(PLIST)], capture_output=True)
    PLIST.write_bytes(plistlib.dumps(plist))
    subprocess.run(["launchctl", "bootstrap", _domain(), str(PLIST)], check=True)
    subprocess.run(["launchctl", "kickstart", f"{_domain()}/{LABEL}"], capture_output=True)
    print(f"Installed: Deezer sync every {INTERVAL // 60} min in the background. Log: {LOG}")


def uninstall() -> None:
    subprocess.run(["launchctl", "bootout", _domain(), str(PLIST)], capture_output=True)
    PLIST.unlink(missing_ok=True)
    print("Background sync removed.")


def status() -> None:
    res = subprocess.run(["launchctl", "print", f"{_domain()}/{LABEL}"], capture_output=True, text=True)
    if res.returncode != 0:
        print("Background sync: not installed.")
        return
    keep = ("state =", "last exit code", "runs =", "run interval")
    print("\n".join(line.strip() for line in res.stdout.splitlines() if line.strip().startswith(keep)))
    if LOG.exists():
        print("--- last log lines ---")
        print("\n".join(LOG.read_text(errors="replace").splitlines()[-6:]))


if __name__ == "__main__":
    {"install": install, "uninstall": uninstall, "status": status}.get(
        sys.argv[1] if len(sys.argv) > 1 else "status", status)()
