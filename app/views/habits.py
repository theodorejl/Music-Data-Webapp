import streamlit as st

from app.components import charts, data, theme, ui
from app.i18n import fmt_date, fmt_int, fmt_pct, fmt_seconds, t, tl
from core import stats

f = data.get_filters()
df = data.filtered_plays()
ui.header(t("habits.title"), f.label, lead=t("habits.lead"), dot="butter")

if df.empty:
    ui.empty_state()
    st.stop()

threshold = st.slider(t("habits.skip_threshold"), 5, 90, 30, step=5, format="%d s", key="hb_thr",
                      help=t("habits.skip_threshold_help"))
# Skips are measured on all plays of the period, ignoring the global minimum-duration filter
# (otherwise the filter would hide the very skips we want to count).
all_period = stats.filter_frame(data.all_plays(), f.start, f.end, 0)
s = stats.streaks(df)
ui.kpi_row([
    (t("habits.current_streak"), t("habits.days", n=fmt_int(s["current"])), None),
    (t("habits.longest_streak"), t("habits.days", n=fmt_int(s["longest"])),
     f"{fmt_date(s['longest_start'])} → {fmt_date(s['longest_end'])}" if s["longest_start"] else None),
    (t("habits.avg_listen"), fmt_seconds(df["listened_seconds"].mean()), t("common.estimated_help")),
    (t("habits.skip_rate"), fmt_pct(stats.skip_rate(all_period, threshold)), t("habits.skip_rate_help", s=threshold)),
])

theme.section(t("habits.heatmap"))
metric = st.segmented_control(t("tops.metric"), ["plays", "minutes"], default="plays", required=True,
                              format_func=lambda m: t(f"common.{m}"), key="hb_metric", label_visibility="collapsed")
charts.show(charts.heatmap_chart(stats.heatmap(df, metric), t(f"common.{metric}")), key="hb_heat")

left, right = st.columns(2, gap="large")
with left:
    theme.section(t("habits.by_weekday"))
    wd = df.groupby(df["played_local"].dt.weekday)["minutes"].sum().reindex(range(7), fill_value=0)
    charts.show(charts.hbar(tl("weekdays"), wd.round(0).tolist(), t("common.minutes")), key="hb_wd")
with right:
    theme.section(t("habits.most_skipped"))
    ms = stats.most_skipped(all_period, threshold, 10)
    if ms.empty:
        ui.empty_state(t("habits.no_skips"))
    else:
        st.dataframe(
            {
                "": ms["cover"].tolist(),
                t("common.track"): ms["track_title"].tolist(),
                t("common.artist"): ms["artist_name"].tolist(),
                t("habits.skips"): ms["skips"].tolist(),
                t("habits.skip_share"): [fmt_pct(x) for x in ms["skip_rate"]],
            },
            hide_index=True, column_config={"": st.column_config.ImageColumn("", width="small")},
        )
ui.estimated_note(df)
