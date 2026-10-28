import streamlit as st

from app.components import charts, data, detail, theme, ui
from app.i18n import fmt_date, fmt_datetime_short, fmt_duration, fmt_int, fmt_pct, fmt_seconds, t
from core import stats

f = data.get_filters()
everything = stats.filter_frame(data.all_plays(), min_seconds=f.min_seconds)
if everything.empty:
    ui.header(t("nav.track"))
    ui.empty_state()
    st.stop()

track_id = detail.pick_entity("track", everything, "track_id",
                              lambda r: f"{r['track_title']} — {r['artist_name']}")
mine = everything[everything["track_id"] == track_id]
info = mine.iloc[0]

c_img, c_txt = st.columns([1, 2], gap="large", vertical_alignment="center")
with c_img:
    if isinstance(info["cover_xl"], str):
        st.image(info["cover_xl"], width="stretch")
with c_txt:
    st.title(info["track_title"])
    b1, b2 = st.columns(2)
    if b1.button(info["artist_name"], type="tertiary", icon=":material/person:"):
        ui.open_detail("artist", info["artist_id"])
    if b2.button(info["album_title"], type="tertiary", icon=":material/album:"):
        ui.open_detail("album", info["album_id"])
    st.caption(t("detail.first_play", date=fmt_date(mine["played_local"].min().date())))
    detail.preview_player(int(track_id), info["track_title"])

ui.kpi_row([
    (t("common.plays"), fmt_int(len(mine)), None),
    (t("common.listening_time"), fmt_duration(mine["minutes"].sum()), t("common.estimated_help")),
    (t("habits.avg_listen"), fmt_seconds(mine["listened_seconds"].mean()), None),
    (t("habits.skip_rate"), fmt_pct(stats.skip_rate(mine, 30)), t("habits.skip_rate_help", s=30)),
])

theme.section(t("detail.listening_curve"))
charts.show(charts.bar_timeline(stats.timeline(mine, "M"), "plays", "M", t("common.plays"), height=220), key="tr_curve")

theme.section(t("detail.all_plays"))
st.dataframe(
    {
        t("common.time"): [fmt_datetime_short(x) for x in mine["played_local"]],
        t("common.listened"): [fmt_seconds(s) + ("*" if e else "") for s, e in
                               zip(mine["listened_seconds"], mine["duration_is_estimated"])],
    },
    hide_index=True,
)
ui.estimated_note(mine)
detail.back_links()
