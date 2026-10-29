"""Shared helpers for the artist / album / track detail pages."""

from __future__ import annotations

from html import escape

import pandas as pd
import streamlit as st

from app.components import charts, data, theme, ui
from app.i18n import t


def wanted_id(df_all: pd.DataFrame, key_col: str) -> int | None:
    """The entity in the URL (?id=), else the most played one."""
    counts = df_all.groupby(key_col).size().sort_values(ascending=False)
    if counts.empty:
        return None
    options = [int(k) for k in counts.index]
    try:
        wanted = int(st.query_params.get("id"))
    except (TypeError, ValueError):
        wanted = None
    return wanted if wanted in options else options[0]


def pick_entity(kind: str, df_all: pd.DataFrame, key_col: str, label_fn) -> int | None:
    """Selectbox of entities (most played first), synced with ?id= in the URL."""
    counts = df_all.groupby(key_col).size().sort_values(ascending=False)
    if counts.empty:
        return None
    first = df_all.drop_duplicates(key_col).set_index(key_col)
    options = [int(k) for k in counts.index]
    wanted = st.query_params.get("id")
    try:
        wanted = int(wanted) if wanted is not None else None
    except ValueError:
        wanted = None
    index = options.index(wanted) if wanted in options else 0
    selected = st.selectbox(t(f"detail.choose_{kind}"), options, index=index, width=420,
                            format_func=lambda k: label_fn(first.loc[k]), key=f"pick_{kind}_{wanted}")
    if str(selected) != st.query_params.get("id"):
        st.query_params["id"] = str(selected)
        if wanted is not None:  # the header was drawn for the previous one
            st.rerun()
    return selected


def family_for(genre) -> str:
    """The panel family of a genre's colour, so a page wears the colour of its music."""
    if not isinstance(genre, str):
        return "lilac"
    return theme.family_of_color(charts.category_colors([genre]).get(genre, "")) if genre else "lilac"


def image_art(url, round_: bool = False) -> str:
    if not isinstance(url, str) or not url:
        return ""
    radius = "50%" if round_ else "28px"
    return (f"<img src='{escape(url)}' alt='' style='display:block;width:min(100%,380px);aspect-ratio:1;object-fit:cover;"
            f"margin:0 auto;border-radius:{radius};border:6px solid rgba(255,255,255,.75);"
            f"box-shadow:0 34px 60px -34px rgba(0,0,0,.65)'>")


def preview_player(track_id: int, title: str) -> None:
    """A play button: the 30 s preview plays in the player bar at the bottom of the window."""
    if data.preview_url(track_id):
        st.html(f"<button class='ds-play' data-ds-play='{int(track_id)}' data-title='{escape(title)}'>"
                f"<i></i>{escape(t('detail.preview'))} — {escape(title)}</button>")
    else:
        st.caption(t("detail.no_preview"))


def tags_line(tags: pd.DataFrame, entity_type: str, entity_id: int, limit: int = 8) -> str | None:
    if tags is None or tags.empty:
        return None
    sel = tags[(tags["entity_type"] == entity_type) & (tags["entity_id"] == entity_id)]
    if sel.empty:
        return None
    sel = sel.sort_values("count", ascending=False, na_position="last").drop_duplicates("tag").head(limit)
    return " · ".join(f"{r.tag} ({int(r.count)})" if pd.notna(r.count) else r.tag for r in sel.itertuples())


def back_links() -> None:
    theme.gap()
    st.page_link(ui.PAGES["tops"], label=t("detail.back_tops"), icon=":material/arrow_back:")
