"""The app around the pages: a Material navigation rail, a top bar with search and refresh,
the living background, then the page itself.

Kept out of Home.py so that Home.py itself never changes: an edit that breaks this file
(or any page) is shown on screen and fixed by the next save, without relaunching anything.
"""

from __future__ import annotations

from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

from app.components import data, refresh, theme, ui
from app.i18n import DEFAULT_LANG, LANGS, fmt_datetime_short, fmt_int, t

# Not named "pages/": that folder name switches Streamlit to its legacy multipage mode.
VIEWS = Path(__file__).parent / "views"

# (name, file, icon) in rail order; detail pages are reached by search and clicks only.
RAIL = [
    ("home", "home.py", ":material/home:"),
    ("tops", "tops.py", ":material/trophy:"),
    ("rhythms", "rhythms.py", ":material/graphic_eq:"),
    ("discoveries", "discoveries.py", ":material/explore:"),
    ("explore", "explore.py", ":material/blur_on:"),
    ("wrapped", "wrapped.py", ":material/auto_awesome:"),
    ("library", "library.py", ":material/library_music:"),
    ("history", "history.py", ":material/history:"),
    ("admin", "admin.py", ":material/tune:"),
]
HIDDEN = [("artist", "artist.py"), ("album", "album.py"), ("track", "track.py")]


def _language() -> None:
    if "lang" not in st.session_state:
        wanted = st.query_params.get("lang")
        st.session_state["lang"] = wanted if wanted in LANGS else DEFAULT_LANG


def _pages() -> dict[str, st.Page]:
    pages = {}
    for name, file, icon in RAIL:
        pages[name] = st.Page(VIEWS / file, title=t(f"rail.{name}"), icon=icon, default=name == "home",
                              url_path=None if name == "home" else name)
    for name, file in HIDDEN:
        pages[name] = st.Page(VIEWS / file, title=t(f"nav.{name}"), url_path=name, visibility="hidden")
    # aliases kept so older links and components keep working
    pages["overview"] = pages["home"]
    pages["evolution"] = pages["habits"] = pages["rhythms"]
    return pages


def _rail(pages: dict[str, st.Page], current: str) -> None:
    family = theme.PAGE_FAMILY.get(current, "sky")
    active = theme.FAMILIES[family]["light"]
    with st.sidebar:
        for name, _, icon in RAIL:
            with st.container(key=f"rail-{name}"):
                st.page_link(pages[name], label=t(f"rail.{name}"), icon=icon)
        st.html(f"<style>.st-key-rail-{current or 'home'} [data-testid='stPageLink'] a > span:first-child"
                f"{{background:{active} !important;color:#1f1f1f !important}}"
                f".st-key-rail-{current or 'home'} [data-testid='stPageLink'] a p{{color:#1f1f1f !important;font-weight:700 !important}}</style>")
        st.segmented_control(t("filters.language"), list(LANGS), key="lang", format_func=lambda c: c.upper(),
                             required=True, label_visibility="collapsed")
        _sync_foot()


def _sync_foot() -> None:
    runs = data.sync_runs()
    ok = runs[runs["status"] == "ok"] if not runs.empty else runs
    failed = not runs.empty and runs.iloc[0]["status"] == "error"
    if ok.empty:
        when = t("status.never")
    else:
        last = pd.Timestamp(ok["finished_at"].max() or ok["started_at"].max()).tz_localize("UTC").tz_convert(data.timezone_name())
        when = fmt_datetime_short(last)
    gaps = int(runs["gap_warning"].notna().sum()) if not runs.empty else 0
    lines = [f"<i class='{'off' if failed else ''}'></i>{escape(when)}",
             escape(t("status.plays_short", n=fmt_int(len(data.all_plays()))))]
    if gaps:
        lines.append(f"<span style='color:#7d1a43'>{escape(t('status.gaps_short', n=gaps))}</span>")
    st.html(f"<div class='ds-rail-foot' title='{escape(t('status.title'))}'>{'<br>'.join(lines)}</div>")


def _go(target: str, pages: dict[str, st.Page]) -> None:
    kind, _, key = target.partition(":")
    if kind in pages and key:
        st.switch_page(pages[kind], query_params={"id": key})


def _remember_search() -> None:
    st.session_state["goto"] = st.session_state.get("search_box")
    st.session_state["search_box"] = None


def _top_bar(pages: dict[str, st.Page]) -> None:
    with st.container(key="topbar"):
        brand, search, action = st.columns([1.05, 3.2, 1.1], gap="large", vertical_alignment="center")
        with brand:
            st.html(theme.brand_html())
        with search:
            index = data.search_index()
            labels = dict(index)
            st.selectbox(t("search.label"), [k for k, _ in index], index=None, key="search_box",
                         placeholder=t("search.placeholder"), format_func=lambda k: labels.get(k, k),
                         on_change=_remember_search, label_visibility="collapsed")
        with action:
            refresh.refresh_button()
    target = st.session_state.pop("goto", None)
    if target:
        _go(target, pages)


def run() -> None:
    theme.inject()
    theme.brand()
    _language()

    pages = _pages()
    ui.PAGES.update(pages)
    nav = st.navigation([pages[name] for name, _, _ in RAIL] + [pages[name] for name, _ in HIDDEN], position="hidden")
    current = nav.url_path or "home"
    st.session_state["page"] = current

    st.session_state["filters"] = data.current_filters()
    try:
        _rail(pages, current)
        _top_bar(pages)
    except Exception as exc:  # e.g. database unreachable: show it instead of crashing every page
        st.error(t("common.db_error", error=type(exc).__name__))
        st.stop()
    theme.background(current)
    nav.run()
