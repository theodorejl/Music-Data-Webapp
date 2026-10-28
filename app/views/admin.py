"""Metadata corrections. The ONLY page that writes to the database.

Corrections are stored as aliases and applied when stats are computed; raw data
is never modified.
"""

import hmac

import pandas as pd
import streamlit as st
from sqlalchemy import delete

from app.components import data, ui
from app.i18n import fmt_datetime_short, t
from core.config import get_settings
from core.db import get_engine, session_scope
from core.models import Alias, play_key
from core.stats import search_history

ui.header(t("admin.title"), t("admin.kicker"), lead=t("admin.subtitle"), dot="butter")

password = get_settings().admin_password
if not password:
    st.warning(t("admin.no_password"))
    st.stop()

if not st.session_state.get("admin_ok"):
    with st.form("login"):
        typed = st.text_input(t("admin.password"), type="password")
        if st.form_submit_button(t("admin.login")):
            if hmac.compare_digest(typed.encode(), password.encode()):
                st.session_state["admin_ok"] = True
                st.rerun()
            else:
                st.error(t("admin.wrong_password"))
    st.stop()


def save_alias(kind: str, source_key: str, target: str) -> None:
    with session_scope(get_engine()) as s:
        existing = s.query(Alias).filter_by(kind=kind, source_key=source_key).one_or_none()
        if existing:
            existing.target = target
        else:
            s.add(Alias(kind=kind, source_key=source_key, target=target))
    data.clear_caches()
    st.toast(t("admin.saved"), icon="✅")


raw = data.raw_data()
artists = raw.artists.sort_values("name")
albums = raw.albums.merge(raw.artists[["id", "name"]].rename(columns={"id": "artist_id", "name": "artist"}),
                          on="artist_id", how="left").sort_values("title")
artist_label = dict(zip(artists["id"], artists["name"]))
album_label = {r.id: f"{r.title} — {r.artist if isinstance(r.artist, str) else '?'}" for r in albums.itertuples()}

tab_ar, tab_al, tab_g, tab_hide, tab_list = st.tabs([
    t("admin.merge_artists"), t("admin.merge_albums"), t("admin.genres"), t("admin.hide_play"), t("admin.existing"),
])

with tab_ar:
    st.caption(t("admin.merge_artists_help"))
    with st.form("merge_artist", clear_on_submit=True):
        src = st.selectbox(t("admin.merge_this"), artists["id"], format_func=lambda i: f"{artist_label[i]} (#{i})", index=None)
        dst = st.selectbox(t("admin.into_this"), artists["id"], format_func=lambda i: f"{artist_label[i]} (#{i})", index=None)
        if st.form_submit_button(t("admin.merge")) and src and dst:
            if src == dst:
                st.error(t("admin.same"))
            else:
                save_alias("merge_artist", str(src), str(dst))

with tab_al:
    st.caption(t("admin.merge_albums_help"))
    with st.form("merge_album", clear_on_submit=True):
        src = st.selectbox(t("admin.merge_this"), albums["id"], format_func=lambda i: f"{album_label[i]} (#{i})", index=None)
        dst = st.selectbox(t("admin.into_this"), albums["id"], format_func=lambda i: f"{album_label[i]} (#{i})", index=None)
        if st.form_submit_button(t("admin.merge")) and src and dst:
            if src == dst:
                st.error(t("admin.same"))
            else:
                save_alias("merge_album", str(src), str(dst))

with tab_g:
    known_genres = sorted(set(data.all_plays()["genre"].dropna()))
    st.markdown(f"**{t('admin.force_genre')}**")
    with st.form("album_genre", clear_on_submit=True):
        alb = st.selectbox(t("common.album"), albums["id"], format_func=lambda i: album_label[i], index=None)
        genre = st.text_input(t("common.genre"), placeholder=", ".join(known_genres[:5]))
        if st.form_submit_button(t("admin.save")) and alb and genre.strip():
            save_alias("album_genre", str(alb), genre.strip())
    st.markdown(f"**{t('admin.rename_genre')}**")
    with st.form("rename_genre", clear_on_submit=True):
        old = st.selectbox(t("admin.genre_from"), known_genres, index=None)
        new = st.text_input(t("admin.genre_to"))
        if st.form_submit_button(t("admin.save")) and old and new.strip() and old != new.strip():
            save_alias("rename_genre", old, new.strip())

with tab_hide:
    st.caption(t("admin.hide_help"))
    plays = data.all_plays()
    q = st.text_input(t("history.search"), key="adm_q")
    candidates = search_history(plays, q.strip()).head(200)
    options = {int(r.play_id): f"{fmt_datetime_short(r.played_local)} — {r.track_title} — {r.artist_name}"
               for r in candidates.itertuples()}
    with st.form("hide_play", clear_on_submit=True):
        pid = st.selectbox(t("admin.play"), list(options), format_func=lambda i: options[i], index=None)
        if st.form_submit_button(t("admin.hide")) and pid:
            row = plays[plays["play_id"] == pid].iloc[0]
            save_alias("hide_play", play_key(int(row["track_id"]), row["played_at"].to_pydatetime()), "")

with tab_list:
    aliases = raw.aliases
    if aliases.empty:
        ui.empty_state(t("admin.none"))
    else:
        def describe(r) -> str:
            if r.kind == "merge_artist":
                return f"{artist_label.get(int(r.source_key), r.source_key)} → {artist_label.get(int(r.target), r.target)}"
            if r.kind == "merge_album":
                return f"{album_label.get(int(r.source_key), r.source_key)} → {album_label.get(int(r.target), r.target)}"
            if r.kind == "album_genre":
                return f"{album_label.get(int(r.source_key), r.source_key)} → {r.target}"
            if r.kind == "rename_genre":
                return f"{r.source_key} → {r.target}"
            return r.source_key

        view = pd.DataFrame({
            "id": aliases["id"],
            t("admin.kind"): [t(f"admin.kind_{k}") for k in aliases["kind"]],
            t("admin.correction"): [describe(r) for r in aliases.itertuples()],
        })
        st.dataframe(view, hide_index=True, column_config={"id": None})
        with st.form("delete_alias"):
            to_delete = st.multiselect(t("admin.delete_which"), view["id"].tolist(),
                                       format_func=lambda i: view.loc[view["id"] == i, t("admin.correction")].iloc[0])
            if st.form_submit_button(t("admin.delete"), type="primary") and to_delete:
                with session_scope(get_engine()) as s:
                    s.execute(delete(Alias).where(Alias.id.in_([int(i) for i in to_delete])))
                data.clear_caches()
                st.rerun()

if st.button(t("admin.logout"), type="tertiary"):
    st.session_state["admin_ok"] = False
    st.rerun()
