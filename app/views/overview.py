import streamlit as st

from app.components import charts, data, ui
from app.i18n import fmt_datetime_short, fmt_duration, fmt_int, fmt_seconds, t
from core import stats

f = data.get_filters()
df = data.filtered_plays()
ui.header(t("overview.title"), f.label)

if df.empty:
    ui.empty_state(t("overview.empty"))
    st.stop()

k = stats.kpis(df)
ui.kpi_row([
    (t("common.plays"), fmt_int(k["plays"]), None),
    (t("common.listening_time"), fmt_duration(k["minutes"]), t("common.estimated_help")),
    (t("common.artists"), fmt_int(k["artists"]), None),
    (t("common.tracks"), fmt_int(k["tracks"]), None),
])
ui.estimated_note(df)

freq = "D" if f.period in ("today", "7d", "30d") else ("W" if f.period in ("year", "custom") else "M")
st.subheader(t("overview.activity"))
tl = stats.timeline(df, freq)
charts.show(charts.bar_timeline(tl, "minutes", freq, t("common.minutes"), height=240), key="ov_tl")

left, right = st.columns(2, gap="large")
with left:
    st.subheader(t("overview.top_artists"))
    ui.cover_grid(stats.top(df, "artist", "plays", 6), "artist", ui.value_formatter("plays"), columns=3, key="ov_ar")
with right:
    st.subheader(t("overview.top_tracks"))
    tracks = stats.top(df, "track", "plays", 8)
    charts.show(charts.hbar([f"{a} — {b}" if len(a) < 28 else a for a, b in zip(tracks["label"], tracks["sublabel"])],
                            tracks["plays"], t("common.plays")), key="ov_tr")

st.subheader(t("overview.recent"))
recent = df.head(15)
st.dataframe(
    {
        t("common.time"): [fmt_datetime_short(x) for x in recent["played_local"]],
        "": recent["cover"].tolist(),
        t("common.track"): recent["track_title"].tolist(),
        t("common.artist"): recent["artist_name"].tolist(),
        t("common.listened"): [fmt_seconds(s) + ("*" if e else "") for s, e in
                               zip(recent["listened_seconds"], recent["duration_is_estimated"])],
    },
    hide_index=True,
    column_config={"": st.column_config.ImageColumn("", width="small")},
)
st.page_link(ui.PAGES["history"], label=t("overview.see_history"), icon=":material/arrow_forward:")
