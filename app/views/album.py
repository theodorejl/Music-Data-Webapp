from html import escape

import pandas as pd
import streamlit as st

from app.components import charts, data, detail, theme, ui
from app.i18n import fmt_date, fmt_duration, fmt_int, t
from core import stats

f = data.get_filters()
everything = stats.filter_frame(data.all_plays(), min_seconds=f.min_seconds)
if everything.empty:
    ui.header(t("nav.album"))
    ui.empty_state()
    st.stop()

album_id = detail.pick_entity("album", everything, "album_id",
                              lambda r: f"{r['album_title']} — {r['artist_name']}")
mine = everything[everything["album_id"] == album_id]
info = mine.iloc[0]
raw = data.raw_data()
meta = raw.albums[raw.albums["id"] == album_id]
meta = meta.iloc[0] if not meta.empty else None

c_img, c_txt = st.columns([1, 2], gap="large", vertical_alignment="center")
with c_img:
    if isinstance(info["cover_xl"], str):
        st.image(info["cover_xl"], width="stretch")
with c_txt:
    st.title(info["album_title"])
    if st.button(info["artist_name"], type="tertiary", icon=":material/person:"):
        ui.open_detail("artist", info["artist_id"])
    facts = []
    if meta is not None:
        released = pd.to_datetime(meta["release_date"], errors="coerce")  # Deezer may send "0000-00-00"
        if pd.notna(released):
            facts.append(t("detail.released", date=fmt_date(released.date())))
        if isinstance(meta["label"], str):
            facts.append(meta["label"])
    if isinstance(info["genre"], str):
        facts.append(info["genre"])
    st.markdown(f"<div class='ds-sub'>{escape(' · '.join(facts))}</div>", unsafe_allow_html=True)
    mb = detail.tags_line(raw.tags, "album", album_id)
    if mb:
        st.caption(t("detail.mb_tags", tags=mb))
    st.caption(t("detail.first_play", date=fmt_date(mine["played_local"].min().date())))
    ui.kpi_row([
        (t("common.plays"), fmt_int(len(mine)), None),
        (t("common.listening_time"), fmt_duration(mine["minutes"].sum()), t("common.estimated_help")),
    ])

theme.section(t("detail.album_tracks"))
t_start, t_end, _ = data.period_pills("al_tracks")
tracks = stats.top(stats.filter_frame(mine, t_start, t_end), "track", "plays", 100)
ui.ranked_table(tracks, "track", key=f"al_tracks_{album_id}")

theme.section(t("detail.listening_curve"))
charts.show(charts.bar_timeline(stats.timeline(mine, "M"), "plays", "M", t("common.plays"), height=220), key="al_curve")

if not tracks.empty:
    theme.section(t("detail.preview_title"))
    detail.preview_player(int(tracks.iloc[0]["key"]), tracks.iloc[0]["label"])
detail.back_links()
