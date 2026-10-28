"""Whole-project hot reload, done in the script's own thread.

Streamlit's file watcher drops changed modules from sys.modules from another thread, which
can happen in the middle of an import ("KeyError: 'app.components.ui'") and leaves the page
broken; it also reloads only the changed files, so other modules keep stale copies.
It is switched off (server.fileWatcherType = "none"). Without it Streamlit also keeps the
compiled code of every page forever, so that cache is cleared here too. Instead:
- refresh_modules(), at the top of every run of Home.py, drops every module of this project
  when any source file changed, so the run imports one consistent version of the code;
- watch(), a 2-second fragment placed first on the page, notices an edit and reruns the app,
  and keeps running even when a half-finished edit made the page fail, so the next save
  repairs it without a relaunch.
"""

from __future__ import annotations

import importlib
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_PACKAGES = ("app", "core")
_STAMP = "_deezer_stats_source_stamp"  # kept on the sys module, which is never reloaded


def _stamp() -> tuple[float, int]:
    files = [p for pkg in _PACKAGES for p in (ROOT / pkg).rglob("*") if p.suffix in (".py", ".json", ".css", ".svg")]
    return max((p.stat().st_mtime for p in files), default=0.0), len(files)


def _wait_until_stable(stamp: tuple[float, int], quiet: float = 0.8, limit: float = 6.0) -> tuple[float, int]:
    """An edit often touches several files in a row: wait until nothing has changed for
    `quiet` seconds, so the run never imports a half-edited project."""
    deadline = time.monotonic() + limit
    while time.monotonic() < deadline:
        time.sleep(quiet)
        now = _stamp()
        if now == stamp:
            break
        stamp = now
    return stamp


def _clear_page_code() -> None:
    """Streamlit caches each page's compiled code until its own (disabled) watcher reports a
    change: without this, edited pages would keep running their old code."""
    try:
        from streamlit.runtime import Runtime

        if Runtime.exists():
            Runtime.instance()._script_cache.clear()
    except Exception:  # private API: never let the dev helper break the app
        pass


def refresh_modules() -> bool:
    """Drop this project's modules when the code changed. Returns True when it did."""
    stamp = _stamp()
    previous = getattr(sys, _STAMP, None)
    if previous is not None and previous != stamp:
        stamp = _wait_until_stable(stamp)
    setattr(sys, _STAMP, stamp)
    if previous is None or previous == stamp:
        return False
    for name in list(sys.modules):
        if name in _PACKAGES or name.startswith(tuple(f"{p}." for p in _PACKAGES)):
            if name != __name__:
                del sys.modules[name]
    importlib.invalidate_caches()
    _clear_page_code()
    return True


def watch(every: float = 2.0) -> None:
    """Rerun the whole app when the code changes (no Streamlit file watcher involved)."""
    import streamlit as st

    seen = getattr(sys, _STAMP, None)

    @st.fragment(run_every=every)
    def _code_watch() -> None:
        if seen is not None and _stamp() != seen:
            _clear_page_code()  # so the rerun compiles Home.py and the pages afresh
            st.rerun(scope="app")

    _code_watch()
