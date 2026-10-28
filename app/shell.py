"""The app around the pages: language, navigation, sidebar, background.

Kept out of Home.py so that Home.py itself never changes: an edit that breaks this file
(or any page) is shown on screen and fixed by the next save, without relaunching anything.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from app.components import data, refresh, theme, ui
from app.i18n import DEFAULT_LANG, LANGS, t

# Not named "pages/": that folder name switches Streamlit to its legacy multipage mode.
VIEWS = Path(__file__).parent / "views"


def run() -> None:
    ui.inject_css()
    theme.brand()

    # Language first: page titles depend on it. Kept in the URL (?lang=en) so links can be shared.
    if "lang" not in st.session_state:
        st.session_state["lang"] = st.query_params.get("lang", DEFAULT_LANG) if st.query_params.get("lang") in LANGS else DEFAULT_LANG
    with st.sidebar:
        st.segmented_control(t("filters.language"), list(LANGS), key="lang", format_func=lambda c: LANGS[c],
                             required=True, label_visibility="collapsed")

    P = VIEWS
    pages = {
        "overview": st.Page(P / "overview.py", title=t("nav.overview"), icon=":material/dashboard:", default=True),
        "tops": st.Page(P / "tops.py", title=t("nav.tops"), icon=":material/leaderboard:", url_path="tops"),
        "evolution": st.Page(P / "evolution.py", title=t("nav.evolution"), icon=":material/show_chart:", url_path="evolution"),
        "habits": st.Page(P / "habits.py", title=t("nav.habits"), icon=":material/schedule:", url_path="habits"),
        "discoveries": st.Page(P / "discoveries.py", title=t("nav.discoveries"), icon=":material/explore:", url_path="discoveries"),
        "explore": st.Page(P / "explore.py", title=t("nav.explore"), icon=":material/blur_on:", url_path="explore"),
        "wrapped": st.Page(P / "wrapped.py", title=t("nav.wrapped"), icon=":material/auto_awesome:", url_path="wrapped"),
        "library": st.Page(P / "library.py", title=t("nav.library"), icon=":material/library_music:", url_path="library"),
        "history": st.Page(P / "history.py", title=t("nav.history"), icon=":material/history:", url_path="history"),
        "artist": st.Page(P / "artist.py", title=t("nav.artist"), icon=":material/person:", url_path="artist"),
        "album": st.Page(P / "album.py", title=t("nav.album"), icon=":material/album:", url_path="album"),
        "track": st.Page(P / "track.py", title=t("nav.track"), icon=":material/music_note:", url_path="track"),
        "admin": st.Page(P / "admin.py", title=t("nav.admin"), icon=":material/build:", url_path="admin"),
    }
    ui.PAGES.update(pages)

    nav = st.navigation({
        t("nav.section_stats"): [pages[k] for k in ("overview", "explore", "tops", "evolution", "habits", "discoveries", "wrapped")],
        t("nav.section_library"): [pages[k] for k in ("library", "history", "artist", "album", "track")],
        t("nav.section_settings"): [pages["admin"]],
    }, expanded=True)

    theme.background(nav.url_path)
    refresh.refresh_button()
    st.session_state["filters"] = data.sidebar_filters()
    try:
        ui.sync_status(data.sync_runs(), len(data.all_plays()), data.timezone_name())
    except Exception as exc:  # e.g. database unreachable: show it instead of crashing every page
        st.error(t("common.db_error", error=type(exc).__name__))
        st.stop()

    nav.run()
