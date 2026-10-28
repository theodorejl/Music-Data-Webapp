"""Rhythms (was Evolution + Habits): when do I listen, how it changes over time, who leads
month after month, which genres rise and fall, what I skip."""

from html import escape

import streamlit as st

from app.components import charts, data, theme, ui
from app.i18n import fmt_date, fmt_int, fmt_pct, fmt_seconds, t, tl
from core import stats

f = data.get_filters()
df = data.filtered_plays()

if df.empty:
    theme.hero("lime", t("rail.rhythms"), escape(t("common.no_data")), f.label, controls=data.period_control)
    st.stop()

local = df["played_local"]
by_hour = df.groupby(local.dt.hour)["minutes"].sum()
by_weekday = df.groupby(local.dt.weekday)["minutes"].sum()
s = stats.streaks(df)
lead = t("rhythms.lead", day=f"<b>{escape(tl('weekdays')[int(by_weekday.idxmax())].lower())}</b>",
         hour=f"<b>{int(by_hour.idxmax())} h</b>", streak=f"<b>{fmt_int(s['current'])}</b>",
         best=f"<b>{fmt_int(s['longest'])}</b>")
theme.hero("lime", t("rail.rhythms"), lead, f.label, controls=data.period_control,
           art=ui.art_clock(by_hour, t("rhythms.clock_cap")))

# --- key figures ------------------------------------------------------------------------------
all_period = stats.filter_frame(data.all_plays(), f.start, f.end, 0)
threshold = int(st.session_state.get("hb_thr", 30))
ui.stat_tiles([
    (t("habits.current_streak"), f"{fmt_int(s['current'])}|{t('rhythms.days_unit')}", t("rhythms.streak_cap"), "lime", None),
    (t("habits.longest_streak"), f"{fmt_int(s['longest'])}|{t('rhythms.days_unit')}",
     f"{fmt_date(s['longest_start'])} → {fmt_date(s['longest_end'])}" if s["longest_start"] else None, "teal", None),
    (t("habits.avg_listen"), fmt_seconds(df["listened_seconds"].mean()), t("common.estimated_short"), "sky", None),
    (t("habits.skip_rate"), fmt_pct(stats.skip_rate(all_period, threshold)), t("habits.skip_rate_short", s=threshold), "rose", None),
])

# --- over time ---------------------------------------------------------------------------------
theme.section(t("rhythms.time_section"), t("rhythms.time_note"))
c1, c2 = st.columns([1, 1])
freq = c1.segmented_control(t("evolution.granularity"), ["D", "W", "M"], default="W", required=True,
                            format_func=lambda x: t(f"evolution.freq_{x}"), key="ev_freq", label_visibility="collapsed")
metric = c2.segmented_control(t("tops.metric"), ["minutes", "plays"], default="minutes", required=True,
                              format_func=lambda m: t(f"common.{m}"), key="ev_metric", label_visibility="collapsed")
label = t(f"common.{metric}")
left, right = st.columns([1.35, 1], gap="medium")
with left:
    with theme.panel("butter", "per-period"):
        theme.head(t("evolution.per_period", metric=label), f.label, t("rhythms.bars_note"))
        charts.show(charts.bar_timeline(stats.timeline(df, freq), metric, freq, label, height=300), key="ev_bar")
with right:
    with theme.panel("lilac", "cumulative"):
        theme.head(t("evolution.cumulative"), f.label)
        charts.show(charts.flow(stats.cumulative(df, freq), metric, freq, label, "lilac", height=330), key="ev_cum")

span = (local.max() - local.min()).days
rank_freq = "D" if span <= 14 else ("W" if span <= 120 else "M")
other = t("common.other")
theme.gap()
left, right = st.columns([1, 1], gap="medium")
with left:
    with theme.panel("sky", "bump"):
        theme.head(t("rhythms.bump_title"), t(f"evolution.freq_{rank_freq}"), t("rhythms.bump_note"))
        ranks = stats.ranks_over_time(df, "artist", rank_freq, 6, "minutes", depth=10)
        if ranks["period"].nunique() < 2:
            ui.empty_state(t("rhythms.too_short"))
        else:
            charts.show(charts.bump(ranks, rank_freq, height=400), key="rh_bump")
with right:
    with theme.panel("rose", "stream"):
        theme.head(t("evolution.genre_share"), t(f"evolution.freq_{rank_freq}"), t("rhythms.stream_note"))
        g = stats.share_over_time(df, "genre", rank_freq if rank_freq != "D" else "W", 6, "minutes", other)
        if g.empty or g["period"].nunique() < 2:
            ui.empty_state(t("tops.no_genre") if g.empty else t("rhythms.too_short"))
        else:
            charts.show(charts.stream(g, rank_freq if rank_freq != "D" else "W", other, height=400, normalized=True), key="rh_stream")

# --- the week and the day -----------------------------------------------------------------------
theme.section(t("rhythms.week_section"), t("rhythms.week_note"))
left, right = st.columns([1, 1.15], gap="medium")
with left:
    with theme.panel("coral", "ridges"):
        theme.head(t("rhythms.ridge_title"), t("rhythms.ridge_meta"))
        charts.show(charts.ridgeline(df, height=430), key="rh_ridge")
with right:
    with theme.panel("teal", "matrix"):
        theme.head(t("habits.heatmap"), t("rhythms.matrix_meta"), t("rhythms.matrix_note"))
        hm_metric = st.segmented_control(t("tops.metric"), ["plays", "minutes"], default="plays", required=True,
                                         format_func=lambda m: t(f"common.{m}"), key="hb_metric", label_visibility="collapsed")
        charts.show(charts.dot_matrix(stats.heatmap(df, hm_metric), t(f"common.{hm_metric}").lower(), height=340), key="hb_heat")

theme.gap()
with theme.panel("lime", "calendar"):
    theme.head(t("habits.calendar"), t("habits.calendar_kicker"))
    everything = data.all_plays()
    daily = everything.groupby(everything["played_local"].dt.date)["minutes"].sum()
    charts.show(charts.calendar(daily, t("common.minutes")), key="hb_cal")

# --- skips -------------------------------------------------------------------------------------
theme.section(t("rhythms.skip_section"), t("habits.skip_threshold_help"))
with theme.white("skips"):
    st.slider(t("habits.skip_threshold"), 5, 90, 30, step=5, format="%d s", key="hb_thr", width=360)
    skip_scope, _ = data.scoped_plays("hb_skip")
    ms = stats.most_skipped(skip_scope, threshold, 12)
    if ms.empty:
        ui.empty_state(t("habits.no_skips"))
    else:
        st.dataframe(
            {
                "": ms["cover"].tolist(),
                t("common.track"): ms["track_title"].tolist(),
                t("common.artist"): ms["artist_name"].tolist(),
                t("habits.skips"): ms["skips"].tolist(),
                t("habits.skip_share"): (ms["skip_rate"] * 100).round(0).tolist(),
            },
            hide_index=True,
            column_config={"": st.column_config.ImageColumn("", width="small"),
                           t("habits.skips"): st.column_config.NumberColumn(alignment="right"),
                           t("habits.skip_share"): st.column_config.ProgressColumn(t("habits.skip_share"), format="%d %%",
                                                                                     min_value=0, max_value=100, color="#e8558e")},
        )
ui.estimated_note(df)
