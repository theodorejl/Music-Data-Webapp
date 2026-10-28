"""Rhythms (was Evolution + Habits): when do I listen, how it changes over time, who leads
period after period, which genres rise and fall, what I skip. Each chart has its own chips."""

from html import escape

import streamlit as st

from app.components import charts, data, theme, ui
from app.i18n import fmt_date, fmt_duration, fmt_int, fmt_pct, fmt_seconds, t, tl
from core import stats

f = data.get_filters()
df = data.filtered_plays()

if df.empty:
    theme.hero("lime", t("rail.rhythms"), escape(t("common.no_data")), f.label, controls=data.period_control)
    st.stop()


def freq_for(frame) -> str:
    span = (frame["played_local"].max() - frame["played_local"].min()).days if not frame.empty else 0
    return "D" if span <= 14 else ("W" if span <= 120 else "M")


local = df["played_local"]
by_hour = df.groupby(local.dt.hour)["minutes"].sum()
by_weekday = df.groupby(local.dt.weekday)["minutes"].sum()
s = stats.streaks(df)
lead = t("rhythms.lead", day=f"<b>{escape(tl('weekdays')[int(by_weekday.idxmax())].lower())}</b>",
         hour=f"<b>{int(by_hour.idxmax())} h</b>", streak=f"<b>{fmt_int(s['current'])}</b>",
         best=f"<b>{fmt_int(s['longest'])}</b>")
theme.hero("lime", t("rail.rhythms"), lead, f.label, controls=data.period_control,
           art=ui.art_clock(by_hour, t("rhythms.clock_cap")))

ui.stat_tiles([
    (t("habits.current_streak"), f"{fmt_int(s['current'])}|{t('rhythms.days_unit')}", t("rhythms.streak_cap"), "lime", None),
    (t("habits.longest_streak"), f"{fmt_int(s['longest'])}|{t('rhythms.days_unit')}",
     f"{fmt_date(s['longest_start'])} → {fmt_date(s['longest_end'])}" if s["longest_start"] else None, "teal", None),
    (t("habits.avg_listen"), fmt_seconds(df["listened_seconds"].mean()), t("common.estimated_short"), "sky", None),
    (t("rhythms.skip_rate"), fmt_pct(stats.skip_rate(df)), t("rhythms.skip_rate_cap"), "rose", None),
])

# --- over time ---------------------------------------------------------------------------------
theme.section(t("rhythms.time_section"), t("rhythms.time_note"))
left, right = st.columns([1.35, 1], gap="medium")
with left:
    with theme.panel("butter", "per-period"):
        slot = st.container()
        sc = data.scope_bar("rh_bars")
        with st.container(key="scope-rh_bars_opts"):
            a, b = st.columns(2)
            freq = a.segmented_control(t("evolution.granularity"), ["D", "W", "M"], default="W", required=True,
                                       format_func=lambda x: t(f"evolution.freq_{x}"), key="ev_freq", label_visibility="collapsed")
            metric = b.segmented_control(t("tops.metric"), ["minutes", "plays"], default="minutes", required=True,
                                         format_func=lambda m: t(f"common.{m}"), key="ev_metric", label_visibility="collapsed")
        with slot:
            label = t(f"common.{metric}")
            theme.head(t("evolution.per_period", metric=label), sc.label, t("rhythms.bars_note"))
            if sc.df.empty:
                ui.empty_state()
            else:
                covers = stats.top_cover_by(sc.df, stats.period_of(sc.df, freq))
                charts.show(charts.bar_timeline(stats.timeline(sc.df, freq), metric, freq, label, height=320, covers=covers),
                            key="ev_bar")
with right:
    with theme.panel("lilac", "cumulative"):
        slot = st.container()
        sc = data.scope_bar("rh_cum")
        with slot:
            fq = freq_for(sc.df)
            theme.head(t("evolution.cumulative"), sc.label)
            if sc.df.empty:
                ui.empty_state()
            else:
                charts.show(charts.flow(stats.cumulative(sc.df, fq), "minutes", fq, t("common.minutes"), "lilac", height=360),
                            key="ev_cum")

other = t("common.other")
theme.gap()
left, right = st.columns([1, 1], gap="medium")
with left:
    with theme.panel("sky", "bump"):
        slot = st.container()
        sc = data.scope_bar("rh_bump", ["artist", "album", "track", "genre"])
        with slot:
            fq = freq_for(sc.df)
            theme.head(t("rhythms.bump_title", what=t(f"scope.{sc.dim}").lower()), t(f"evolution.freq_{fq}"), t("rhythms.bump_note"))
            ranks = stats.ranks_over_time(sc.df, sc.dim, fq, 6, "minutes", depth=10)
            if ranks.empty or ranks["period"].nunique() < 2:
                ui.empty_state(t("rhythms.too_short"))
            else:
                charts.show(charts.bump(ranks, fq, height=420), key="rh_bump")
with right:
    with theme.panel("rose", "stream"):
        slot = st.container()
        sc = data.scope_bar("rh_stream", ["genre", "artist", "album"])
        with slot:
            fq = freq_for(sc.df)
            fq = fq if fq != "D" else "W"
            theme.head(t("rhythms.stream_title", what=t(f"scope.{sc.dim}").lower()), t(f"evolution.freq_{fq}"), t("rhythms.stream_note"))
            g = stats.share_over_time(sc.df, sc.dim, fq, 6, "minutes", other)
            if g.empty or g["period"].nunique() < 2:
                ui.empty_state(t("tops.no_genre") if g.empty else t("rhythms.too_short"))
            else:
                charts.show(charts.stream(g, fq, other, height=420, normalized=True), key="rh_stream")

# --- the week and the day -----------------------------------------------------------------------
theme.section(t("rhythms.week_section"), t("rhythms.week_note"))
with theme.panel("teal", "week"):
    slot = st.container()
    sc = data.scope_bar("rh_week")
    with slot:
        theme.head(t("rhythms.week_covers_title"), sc.label, t("rhythms.week_covers_note"))
        hm_metric = st.segmented_control(t("tops.metric"), ["plays", "minutes"], default="plays", required=True,
                                         format_func=lambda m: t(f"common.{m}"), key="hb_metric", label_visibility="collapsed")
        fmt_value = (lambda v: fmt_duration(v)) if hm_metric == "minutes" else (lambda v: t("common.n_plays", n=fmt_int(v)))
        if sc.df.empty:
            ui.empty_state()
        else:
            ui.week_covers(stats.week_matrix(sc.df, hm_metric), fmt_value)

theme.gap()
left, right = st.columns([1, 1], gap="medium")
with left:
    with theme.panel("coral", "ridges"):
        slot = st.container()
        sc = data.scope_bar("rh_ridge")
        with slot:
            theme.head(t("rhythms.ridge_title"), sc.label, t("rhythms.ridge_meta"))
            charts.show(charts.ridgeline(sc.df, height=430), key="rh_ridge")
with right:
    with theme.panel("butter", "moments"):
        slot = st.container()
        sc = data.scope_bar("rh_moments")
        with slot:
            theme.head(t("rhythms.moments_title"), sc.label)
            charts.show(charts.radial_clock(sc.df.groupby(sc.df["played_local"].dt.hour)["minutes"].sum(), "minutes", height=260),
                        key="rh_clock")
            ui.moments(stats.moments(sc.df))

theme.gap()
with theme.panel("lime", "calendar"):
    theme.head(t("habits.calendar"), t("habits.calendar_kicker"))
    everything = data.all_plays()
    daily = everything.groupby(everything["played_local"].dt.date)["minutes"].sum()
    charts.show(charts.calendar(daily, t("common.minutes")), key="hb_cal")

# --- skips -------------------------------------------------------------------------------------
theme.section(t("rhythms.skip_section"), t("rhythms.skip_note"))
with theme.panel("rose", "skips"):
    slot = st.container()
    sc = data.scope_bar("rh_skips")
    with slot:
        ms = stats.most_skipped(sc.df, 12)
        theme.head(t("habits.most_skipped"), sc.label,
                   t("rhythms.skips_summary", n=fmt_int(int(stats.skipped(sc.df).sum())) if not sc.df.empty else "0",
                     share=fmt_pct(stats.skip_rate(sc.df))))
        if ms.empty:
            ui.empty_state(t("habits.no_skips"))
        else:
            items = ms.rename(columns={"track_title": "label", "artist_name": "sublabel", "cover": "image"})
            a, b = st.columns(2, gap="large")
            fmt_skip = lambda r: t("rhythms.skips_of", skips=fmt_int(r.skips), plays=fmt_int(r.plays))  # noqa: E731
            with a:
                ui.rank_list(items.iloc[:6], fmt_skip, "skips", colors=["#e8558e"] * 6, limit=6)
            with b:
                ui.rank_list(items.iloc[6:12], fmt_skip, "skips", colors=["#e8558e"] * 6, limit=6, start=7,
                             scale_max=float(items["skips"].max()))
ui.estimated_note(df)
