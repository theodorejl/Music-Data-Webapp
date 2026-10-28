"""Track page, in the colour of the track's genre."""

from html import escape

import streamlit as st

from app.components import charts, data, detail, theme, ui
from app.i18n import fmt_date, fmt_datetime_short, fmt_duration, fmt_int, fmt_pct, fmt_seconds, t
from core import stats

f = data.get_filters()
everything = stats.filter_frame(data.all_plays(), min_seconds=f.min_seconds)
if everything.empty:
    theme.hero("rose", t("nav.track"), escape(t("common.no_data")))
    st.stop()

track_id = detail.wanted_id(everything, "track_id")
mine = everything[everything["track_id"] == track_id]
info = mine.iloc[0]
family = detail.family_for(info["genre"])
lead = (f"<b>{escape(str(info['artist_name']))}</b> · {escape(str(info['album_title']))}"
        + (f" · {escape(info['genre'])}" if isinstance(info["genre"], str) else ""))


def controls() -> None:
    detail.pick_entity("track", everything, "track_id", lambda r: f"{r['track_title']} — {r['artist_name']}")
    b1, b2 = st.columns(2)
    if b1.button(str(info["artist_name"]), type="secondary", icon=":material/person:", key="tr_to_artist"):
        ui.open_detail("artist", info["artist_id"])
    if b2.button(str(info["album_title"]), type="secondary", icon=":material/album:", key="tr_to_album"):
        ui.open_detail("album", info["album_id"])
    detail.preview_player(int(track_id), info["track_title"])


theme.hero(family, str(info["track_title"]), lead, t("nav.track"), controls=controls, art=detail.image_art(info["cover_xl"]))

ui.stat_tiles([
    (t("common.plays"), fmt_int(len(mine)), t("detail.first_play", date=fmt_date(mine["played_local"].min().date())), family, None),
    (t("common.listening_time"), fmt_duration(mine["minutes"].sum()), t("common.estimated_short"), "sky", None),
    (t("habits.avg_listen"), fmt_seconds(mine["listened_seconds"].mean()), None, "butter", None),
    (t("habits.skip_rate"), fmt_pct(stats.skip_rate(mine, 30)), t("habits.skip_rate_short", s=30), "rose", None),
])
theme.gap()

left, right = st.columns([1.4, 1], gap="medium")
with left:
    with theme.panel(family, "curve"):
        theme.head(t("detail.listening_curve"), t("period.all"))
        charts.show(charts.flow(stats.timeline(mine, "M"), "plays", "M", t("common.plays"), family, height=300,
                                avg_label=t("home.average"), peak_label=t("home.record")), key="tr_curve")
with right:
    with theme.panel("butter", "clock"):
        theme.head(t("home.clock_title"), t("home.clock_meta"))
        charts.show(charts.radial_clock(mine.groupby(mine["played_local"].dt.hour)["minutes"].sum(), "minutes", height=320),
                    key="tr_clock")

theme.section(t("detail.all_plays"))
with theme.white("plays"):
    p_start, p_end, _ = data.period_pills("tr_plays")
    plays_scope = stats.filter_frame(mine, p_start, p_end)
    st.dataframe(
        {
            t("common.time"): [fmt_datetime_short(x) for x in plays_scope["played_local"]],
            t("common.listened"): [fmt_seconds(s) + ("*" if e else "") for s, e in
                                   zip(plays_scope["listened_seconds"], plays_scope["duration_is_estimated"])],
        },
        hide_index=True,
        column_config={t("common.listened"): st.column_config.TextColumn(alignment="right")},
    )
ui.estimated_note(mine)
detail.back_links()
