import streamlit as st

from app.components import charts, data, theme, ui
from app.i18n import fmt_datetime_short, fmt_duration, fmt_int, fmt_seconds, t
from core import stats

f = data.get_filters()
df = data.filtered_plays()

if df.empty:
    theme.page_header(t("overview.title"), kicker=f.label)
    ui.empty_state(t("overview.empty"))
    st.stop()

k = stats.kpis(df)
theme.hero(t("overview.hero_title"), f.label, [
    (t("common.plays"), fmt_int(k["plays"])),
    (t("common.listening_time"), fmt_duration(k["minutes"])),
    (t("common.artists"), fmt_int(k["artists"])),
    (t("common.tracks"), fmt_int(k["tracks"])),
])
ui.estimated_note(df)

freq = "D" if f.period in ("today", "7d", "30d") else ("W" if f.period in ("year", "custom") else "M")
theme.section(t("overview.activity"), t("overview.activity_kicker"))
charts.show(charts.bar_timeline(stats.timeline(df, freq), "minutes", freq, t("common.minutes"), height=260), key="ov_tl")

left, right = st.columns([5, 4], gap="large")
with left:
    theme.section(t("overview.top_artists"), t("overview.by_plays"))
    ui.cover_grid(stats.top(df, "artist", "plays", 6), "artist", ui.value_formatter("plays"), columns=3, key="ov_ar")
with right:
    theme.section(t("overview.top_tracks"), t("overview.by_plays"))
    tracks = stats.top(df, "track", "plays", 8)
    charts.show(charts.hbar([f"{a} — {b}" if len(a) < 28 else a for a, b in zip(tracks["label"], tracks["sublabel"])],
                            tracks["plays"], t("common.plays")), key="ov_tr")

theme.section(t("overview.recent"), t("overview.recent_kicker"))
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
c1, c2 = st.columns(2)
c1.page_link(ui.PAGES["history"], label=t("overview.see_history"), icon=":material/arrow_forward:")
c2.page_link(ui.PAGES["explore"], label=t("overview.see_explore"), icon=":material/blur_on:")
