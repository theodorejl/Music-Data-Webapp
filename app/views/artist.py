"""Artist page, in the colour of the artist's main genre."""

from html import escape

import streamlit as st

from app.components import charts, data, detail, theme, ui
from app.i18n import fmt_date, fmt_duration, fmt_int, fmt_plays, t
from core import stats

f = data.get_filters()
everything = stats.filter_frame(data.all_plays(), min_seconds=f.min_seconds)
if everything.empty:
    theme.hero("lilac", t("nav.artist"), escape(t("common.no_data")))
    st.stop()

artist_id = detail.wanted_id(everything, "artist_id")
mine = everything[everything["artist_id"] == artist_id]
in_period = stats.filter_frame(mine, f.start, f.end)
info = mine.iloc[0]
top_genre = mine["genre"].dropna().mode()
genre = top_genre.iloc[0] if not top_genre.empty else None
family = detail.family_for(genre)

lead = t("detail.artist_lead", genre=f"<b>{escape(genre or '–')}</b>", plays=f"<b>{fmt_int(len(mine))}</b>",
         time=f"<b>{escape(fmt_duration(mine['minutes'].sum()))}</b>", date=escape(fmt_date(mine["played_local"].min().date())))
tags = detail.tags_line(data.raw_data().tags, "artist", artist_id)


def controls() -> None:
    detail.pick_entity("artist", everything, "artist_id", lambda r: r["artist_name"])
    if tags:
        st.caption(t("detail.mb_tags", tags=tags))


theme.hero(family, str(info["artist_name"]), lead, t("nav.artist"), controls=controls,
           art=detail.image_art(info["artist_picture_xl"], round_=True))

ui.stat_tiles([
    (t("detail.plays_all_time"), fmt_int(len(mine)), None, family, None),
    (t("detail.plays_period", period=f.label.lower()), fmt_int(len(in_period)), None, "sky", None),
    (t("common.listening_time"), fmt_duration(mine["minutes"].sum()), t("common.estimated_short"), "butter", None),
    (t("common.tracks"), fmt_int(mine["track_id"].nunique()), t("home.albums", n=fmt_int(mine["album_id"].nunique())), "lime", None),
])
theme.gap()

left, right = st.columns([1.5, 1], gap="medium")
with left:
    with theme.panel(family, "curve"):
        theme.head(t("detail.listening_curve"), t("period.all"))
        charts.show(charts.flow(stats.timeline(mine, "M"), "plays", "M", t("common.plays"), family, height=320,
                                avg_label=t("home.average"), peak_label=t("home.record"),
                                covers=stats.top_cover_by(mine, stats.period_of(mine, "M"))), key="ar_curve")
with right:
    with theme.panel("butter", "clock"):
        theme.head(t("home.clock_title"), t("home.clock_meta"))
        charts.show(charts.radial_clock(mine.groupby(mine["played_local"].dt.hour)["minutes"].sum(), "minutes", height=260),
                    key="ar_clock")
        ui.moments(stats.moments(mine))

theme.gap()
left, right = st.columns([1, 1.2], gap="medium")
with left:
    with theme.panel("rose", "tracks"):
        theme.head(t("detail.favorite_tracks"), t("overview.by_plays"))
        t_start, t_end, _ = data.period_pills("ar_tracks")
        tracks = stats.top(stats.filter_frame(mine, t_start, t_end), "track", "plays", 10)
        if tracks.empty:
            ui.empty_state()
        else:
            ui.rank_list(tracks, lambda r: fmt_plays(r.plays), "plays", limit=10)
with right:
    with theme.panel("sky", "albums"):
        theme.head(t("detail.favorite_albums"), t("overview.by_plays"))
        ui.cover_grid(stats.top(mine, "album", "plays", 6), "album", ui.value_formatter("plays"), columns=3, key="ar_albums")

if not tracks.empty:
    theme.gap()
    with theme.panel("mist", "preview"):
        theme.head(t("detail.preview_title"), str(tracks.iloc[0]["label"]))
        detail.preview_player(int(tracks.iloc[0]["key"]), tracks.iloc[0]["label"])
detail.back_links()
