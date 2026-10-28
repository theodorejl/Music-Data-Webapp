from html import escape

import streamlit as st

from app.components import charts, data, detail, ui
from app.i18n import fmt_date, fmt_duration, fmt_int, t
from core import stats

f = data.get_filters()
everything = stats.filter_frame(data.all_plays(), min_seconds=f.min_seconds)
if everything.empty:
    ui.header(t("nav.artist"))
    ui.empty_state()
    st.stop()

artist_id = detail.pick_entity("artist", everything, "artist_id", lambda r: r["artist_name"])
mine = everything[everything["artist_id"] == artist_id]
in_period = stats.filter_frame(mine, f.start, f.end)
info = mine.iloc[0]

c_img, c_txt = st.columns([1, 3], gap="large", vertical_alignment="center")
with c_img:
    if isinstance(info["artist_picture_xl"], str):
        st.image(info["artist_picture_xl"], width="stretch")
with c_txt:
    st.title(info["artist_name"])
    genres = detail.tags_line(data.raw_data().tags, "artist", artist_id)
    top_genre = mine["genre"].dropna().mode()
    st.markdown(f"<div class='ds-sub'>{escape(t('detail.genre_line', genre=top_genre.iloc[0] if not top_genre.empty else '–'))}</div>",
                unsafe_allow_html=True)
    if genres:
        st.caption(t("detail.mb_tags", tags=genres))
    st.caption(t("detail.first_play", date=fmt_date(mine["played_local"].min().date())))

ui.kpi_row([
    (t("detail.plays_all_time"), fmt_int(len(mine)), None),
    (t("detail.plays_period", period=f.label.lower()), fmt_int(len(in_period)), None),
    (t("common.listening_time"), fmt_duration(mine["minutes"].sum()), t("common.estimated_help")),
    (t("common.tracks"), fmt_int(mine["track_id"].nunique()), None),
])

st.subheader(t("detail.listening_curve"))
charts.show(charts.bar_timeline(stats.timeline(mine, "M"), "plays", "M", t("common.plays"), height=220), key="ar_curve")

left, right = st.columns(2, gap="large")
with left:
    st.subheader(t("detail.favorite_tracks"))
    tracks = stats.top(mine, "track", "plays", 10)
    ui.ranked_table(tracks, "track", key=f"ar_tracks_{artist_id}")
with right:
    st.subheader(t("detail.favorite_albums"))
    albums = stats.top(mine, "album", "plays", 6)
    ui.cover_grid(albums, "album", ui.value_formatter("plays"), columns=3, key="ar_albums")

if not tracks.empty:
    st.subheader(t("detail.preview_title"))
    detail.preview_player(int(tracks.iloc[0]["key"]), tracks.iloc[0]["label"])
detail.back_links()
