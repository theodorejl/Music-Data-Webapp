"""Sidebar "refresh" button: fetches the latest Deezer plays on demand.

The sync runs in a separate process (scripts.sync), so the web app itself never
handles the Deezer cookie. The button only appears where the cookie is configured
(your computer), not on the public site, whose collection runs on GitHub Actions.
"""

from __future__ import annotations

import re
import subprocess
import sys
import time
from html import escape

import streamlit as st

from app.components import data, theme
from app.i18n import t
from core.config import ROOT, get_setting, redact

MIN_ANIMATION = 2.6  # seconds: long enough to enjoy the loader, short enough not to annoy

LOADER = """
<style>
.ds-load{position:relative;overflow:hidden;display:flex;align-items:center;gap:14px;padding:8px 18px 8px 8px;
  border-radius:999px;background:linear-gradient(120deg,#c4e9f9,#ddd2ff 45%,#ffd0bd);min-height:56px}
.ds-load .ds-mark{width:42px;height:42px;animation:ds-spin 2.4s linear infinite}
.ds-body{flex:1;min-width:0}
.ds-eq{display:none}
.ds-eq i{width:4px;height:100%;border-radius:2px;transform-origin:bottom;animation:ds-eq .8s ease-in-out infinite alternate}
.ds-eq i:nth-child(1){background:#6C7FE8;animation-delay:-.1s}.ds-eq i:nth-child(2){background:#9B7FD9;animation-delay:-.5s}
.ds-eq i:nth-child(3){background:#E07FA8;animation-delay:-.3s}.ds-eq i:nth-child(4){background:#EE8E66;animation-delay:-.7s}
.ds-eq i:nth-child(5){background:#D9A93A;animation-delay:-.2s}.ds-eq i:nth-child(6){background:#3FB58E;animation-delay:-.6s}
.ds-steps{position:relative;height:18px;font-size:14px;font-weight:500;color:#1f1f1f}
.ds-steps span{position:absolute;left:0;top:0;white-space:nowrap;opacity:0;animation:ds-step 4.2s infinite}
.ds-steps span:nth-child(2){animation-delay:1.4s}.ds-steps span:nth-child(3){animation-delay:2.8s}
.ds-sweep{position:absolute;left:0;right:0;bottom:0;height:3px;
  background:linear-gradient(90deg,transparent,#8b6cf0,#e8558e,#ff6f4d,transparent);background-size:50% 100%;
  background-repeat:no-repeat;animation:ds-sweep 1.3s cubic-bezier(.65,0,.35,1) infinite}
@keyframes ds-spin{to{transform:rotate(360deg)}}
@keyframes ds-eq{from{transform:scaleY(.25)}to{transform:scaleY(1)}}
@keyframes ds-step{0%{opacity:0;transform:translateY(8px)}8%,30%{opacity:1;transform:none}38%,100%{opacity:0;transform:translateY(-8px)}}
@keyframes ds-sweep{from{background-position:-60% 0}to{background-position:160% 0}}
@media (prefers-reduced-motion: reduce){.ds-load .ds-mark,.ds-eq i,.ds-sweep{animation:none}
  .ds-steps span{animation:none}.ds-steps span:first-child{opacity:1}}
</style>
<div class="ds-load"><div class="ds-vinyl"></div><div class="ds-body">
<div class="ds-eq"><i></i><i></i><i></i><i></i><i></i><i></i></div>
<div class="ds-steps"><span>STEP1</span><span>STEP2</span><span>STEP3</span></div></div>
<div class="ds-sweep"></div></div>
"""


def available() -> bool:
    """Only where the Deezer cookie is configured (never on the public site)."""
    return bool(get_setting("DEEZER_ARL"))


def _run_sync() -> tuple[bool, int, str]:
    """(ok, new plays, error message). Library, Excel and long enrichment are left to the
    regular background sync so the button stays quick."""
    run = lambda *args: subprocess.run([sys.executable, "-m", *args], cwd=ROOT,  # noqa: E731
                                       capture_output=True, text=True, timeout=180)
    try:
        pulled = run("scripts.cloud_db", "pull").returncode == 0  # plays collected by GitHub, local corrections kept
        res = run("scripts.sync", "--no-library", "--no-excel", "--enrich-budget", "20")
        # Publish for the hosted site and the next GitHub run, but never without the published
        # copy merged in first: that would replace it with ours and lose its plays.
        if res.returncode == 0 and pulled:
            run("scripts.cloud_db", "push")
    except subprocess.TimeoutExpired:
        return False, 0, t("refresh.timeout")
    match = re.search(r"(\d+) new stored", res.stdout)
    if res.returncode == 0:
        return True, int(match.group(1)) if match else 0, ""
    errors = [line.split(": ", 1)[-1] for line in (res.stderr + res.stdout).splitlines() if " ERROR " in line]
    if any("COOKIE" in e for e in errors):
        return False, 0, t("refresh.cookie")
    return False, 0, redact(errors[-1] if errors else t("refresh.failed"))[:200]


def refresh_button() -> None:
    if not available():
        return
    slot = st.empty()
    if slot.button(t("refresh.button"), icon=":material/sync:", key="refresh_btn", type="primary", width="stretch",
                   help=t("refresh.help")):
        steps = [escape(t(f"refresh.step{i}")) for i in (1, 2, 3)]
        html = LOADER.replace('<div class="ds-vinyl"></div>', theme.mark_img(42))
        for i, step in enumerate(steps, start=1):
            html = html.replace(f"STEP{i}", step)
        slot.html(html)
        started = time.monotonic()
        ok, new, error = _run_sync()
        time.sleep(max(0.0, MIN_ANIMATION - (time.monotonic() - started)))
        st.session_state["refresh_result"] = (ok, new, error)
        data.clear_caches()
        st.rerun()

    result = st.session_state.pop("refresh_result", None)
    if result:
        ok, new, error = result
        if not ok:
            st.toast(error, icon="⚠️")
        elif new == 0:
            st.toast(t("refresh.up_to_date"), icon="✅")
        else:
            st.toast(t("refresh.new", n=new) if new > 1 else t("refresh.new_one"), icon="🎧")
