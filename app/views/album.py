"""Album page, in the colour of the album's genre."""

from html import escape

import pandas as pd
import streamlit as st

from app.components import charts, data, detail, theme, ui
from app.i18n import fmt_date, fmt_duration, fmt_int, fmt_plays, t
from core import stats

f = data.get_filters()
everything = stats.filter_frame(data.all_plays(), min_seconds=f.min_seconds)
if everything.empty:
    theme.hero("coral", t("nav.album"), escape(t("common.no_data")))
    st.stop()

album_id = detail.wanted_id(everything, "album_id")
mine = everything[everything["album_id"] == album_id]
info = mine.iloc[0]
raw = data.raw_data()
meta = raw.albums[raw.albums["id"] == album_id]
meta = meta.iloc[0] if not meta.empty else None
family = detail.family_for(info["genre"])

facts = []
if meta is not None:
    released = pd.to_datetime(meta["release_date"], errors="coerce")  # Deezer may send "0000-00-00"
    if pd.notna(released):
        facts.append(t("detail.released", date=fmt_date(released.date())))
    if isinstance(meta["label"], str):
        facts.append(meta["label"])
if isinstance(info["genre"], str):
    facts.append(info["genre"])
lead = f"<b>{escape(str(info['artist_name']))}</b>" + (f" · {escape(' · '.join(facts))}" if facts else "")
tags = detail.tags_line(raw.tags, "album", album_id)


def controls() -> None:
    detail.pick_entity("album", everything, "album_id", lambda r: f"{r['album_title']} — {r['artist_name']}")
    if st.button(str(info["artist_name"]), type="secondary", icon=":material/person:", key="al_to_artist"):
        ui.open_detail("artist", info["artist_id"])
    if tags:
        st.caption(t("detail.mb_tags", tags=tags))


theme.hero(family, str(info["album_title"]), lead, t("nav.album"), controls=controls, art=detail.image_art(info["cover_xl"]))

ui.stat_tiles([
    (t("common.plays"), fmt_int(len(mine)), t("detail.first_play", date=fmt_date(mine["played_local"].min().date())), family, None),
    (t("common.listening_time"), fmt_duration(mine["minutes"].sum()), t("common.estimated_short"), "sky", None),
    (t("common.tracks"), fmt_int(mine["track_id"].nunique()), None, "lime", None),
])
theme.gap()

left, right = st.columns([1, 1.2], gap="medium")
with left:
    with theme.panel("rose", "tracks"):
        theme.head(t("detail.album_tracks"), t("overview.by_plays"))
        t_start, t_end, _ = data.period_pills("al_tracks")
        tracks = stats.top(stats.filter_frame(mine, t_start, t_end), "track", "plays", 30)
        if tracks.empty:
            ui.empty_state()
        else:
            ui.rank_list(tracks, lambda r: fmt_plays(r.plays), "plays", limit=30)
with right:
    with theme.panel(family, "curve"):
        theme.head(t("detail.listening_curve"), t("period.all"))
        charts.show(charts.flow(stats.timeline(mine, "M"), "plays", "M", t("common.plays"), family, height=300,
                                avg_label=t("home.average"), peak_label=t("home.record")), key="al_curve")
    if not tracks.empty:
        theme.gap()
        with theme.panel("mist", "preview"):
            theme.head(t("detail.preview_title"), str(tracks.iloc[0]["label"]))
            detail.preview_player(int(tracks.iloc[0]["key"]), tracks.iloc[0]["label"])
detail.back_links()
