"""Shared helpers for the artist / album / track detail pages."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app.components import data, ui
from app.i18n import t


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
    selected = st.selectbox(t(f"detail.choose_{kind}"), options, index=index,
                            format_func=lambda k: label_fn(first.loc[k]), key=f"pick_{kind}_{wanted}")
    if str(selected) != st.query_params.get("id"):
        st.query_params["id"] = str(selected)
    return selected


def preview_player(track_id: int, title: str) -> None:
    url = data.preview_url(track_id)
    if url:
        st.caption(f"▶ {t('detail.preview')} — {title}")
        st.audio(url, format="audio/mpeg")
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
    st.page_link(ui.PAGES["tops"], label=t("detail.back_tops"), icon=":material/arrow_back:")
