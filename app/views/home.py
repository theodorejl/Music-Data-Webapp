"""Home: what did I listen to in this period, and what dominates it?
A mosaic of colour panels; under each chart, chips choose its own time range and what it counts."""

from html import escape

import streamlit as st

from app.components import charts, data, theme, ui
from app.i18n import fmt_date, fmt_duration, fmt_int, fmt_pct, fmt_plays, fmt_seconds, t
from core import stats

f = data.get_filters()
df = data.filtered_plays()

if df.empty:
    theme.hero("sky", t("home.title"), escape(t("overview.empty")), f.label, controls=data.period_control)
    st.stop()


def freq_for(frame) -> str:
    span = (frame["played_local"].max() - frame["played_local"].min()).days if not frame.empty else 0
    return "D" if span <= 45 else ("W" if span <= 400 else "M")


k = stats.kpis(df)
leader = stats.top(df, "artist", "minutes", 1).iloc[0]
busiest = stats.busiest_day(df)
freq = freq_for(df)
timeline = stats.timeline(df, freq)

lead = t("home.lead", time=f"<b>{escape(fmt_duration(k['minutes']))}</b>",
         share=f"<b>{fmt_pct(leader['minutes'] / k['minutes']) if k['minutes'] else '–'}</b>",
         artist=f"<b>{escape(str(leader['label']))}</b>",
         day=f"<b>{escape(fmt_date(busiest[0]))}</b>" if busiest else "–",
         day_time=escape(fmt_duration(busiest[1])) if busiest else "–")
hours = int(k["minutes"] // 60)
art = (ui.art_giant(fmt_int(hours) if hours else fmt_int(round(k["minutes"])), "h" if hours else "min",
                    t("home.giant_cap", plays=fmt_int(k["plays"])))
       + ui.art_line(timeline["minutes"], label_start=fmt_date(timeline["period"].iloc[0].date(), short=True),
                     label_end=fmt_date(timeline["period"].iloc[-1].date(), short=True)))
theme.hero("sky", t("home.title"), lead, f.label, art=art, controls=data.period_control)

# --- key figures ------------------------------------------------------------------------------
daily = stats.timeline(df, "D")
firsts = stats.first_listens(stats.filter_frame(data.all_plays()), "artist")
new_artists = int(((firsts["first_played"] >= f.start) & (firsts["first_played"] < f.end)).sum()) if f.start is not None else len(firsts)
ui.stat_tiles([
    (t("common.plays"), fmt_int(k["plays"]), t("home.per_day", n=fmt_int(round(k["plays"] / max(1, k["days"])))), "coral", daily["plays"]),
    (t("common.artists"), fmt_int(k["artists"]), t("home.new_artists", n=fmt_int(new_artists)), "lilac", None),
    (t("common.tracks"), fmt_int(k["tracks"]), t("home.albums", n=fmt_int(k["albums"])), "lime", None),
    (t("home.active_days"), fmt_int(k["days"]), t("home.avg_listen", time=fmt_seconds(k["avg_seconds"])), "butter", daily["minutes"]),
])
theme.gap()

# --- favourites and genres ----------------------------------------------------------------------
left, right = st.columns([1.25, 1], gap="medium")
with left:
    with theme.panel("rose", "favourites"):
        slot = st.container()
        sc = data.scope_bar("home_fav", ["artist", "album", "track", "genre"])
        with slot:
            theme.head(t("home.favourites", what=t(f"scope.{sc.dim}").lower()), sc.label)
            items = ui.ranking(sc.df, sc.dim, "minutes", 7)
            if items.empty:
                ui.empty_state()
            else:
                ui.rank_list(items, lambda r: fmt_duration(r.minutes), "minutes", colors=ui.item_colors(items, sc.dim, sc.df),
                             round_art=sc.dim == "artist", limit=7)
                st.caption(t("home.bar_colour_note"))
with right:
    with theme.panel("lilac", "genres"):
        slot = st.container()
        sc = data.scope_bar("home_genres")
        with slot:
            theme.head(t("overview.genres_title"), sc.label)
            genres = stats.top(sc.df, "genre", "minutes", 6)
            if genres.empty:
                ui.empty_state(t("tops.no_genre"))
            else:
                other = t("common.other")
                rest = sc.df["minutes"].sum() - genres["minutes"].sum()
                labels = genres["label"].tolist() + ([other] if rest > 1 else [])
                values = genres["minutes"].tolist() + ([rest] if rest > 1 else [])
                charts.show(charts.donut(labels, values, fmt_int(sc.df["genre"].dropna().nunique()), t("home.genres_center"),
                                         height=310, other_label=other), key="home_donut")
                cmap = charts.category_colors(labels, other)
                ui.legend([(lab, cmap[lab]) for lab in labels])

# --- time and the clock ---------------------------------------------------------------------------
theme.gap()
left, right = st.columns([1.6, 1], gap="medium")
with left:
    with theme.panel("lime", "flow"):
        slot = st.container()
        sc = data.scope_bar("home_flow")
        with slot:
            fq = freq_for(sc.df)
            ks = stats.kpis(sc.df)
            theme.head(t("overview.time_title"), sc.label)
            theme.figure(escape(fmt_duration(ks["minutes"])), t("overview.time_sub", plays=fmt_int(ks["plays"]),
                                                                  artists=fmt_int(ks["artists"]), tracks=fmt_int(ks["tracks"]),
                                                                  avg=fmt_seconds(ks["avg_seconds"])))
            if sc.df.empty:
                ui.empty_state()
            else:
                covers = stats.top_cover_by(sc.df, stats.period_of(sc.df, fq))
                charts.show(charts.flow(stats.timeline(sc.df, fq), "minutes", fq, t("common.minutes"), "lime", height=290,
                                        avg_label=t("home.average"), peak_label=t("home.record"), covers=covers), key="home_flow")
with right:
    with theme.panel("butter", "clock"):
        slot = st.container()
        sc = data.scope_bar("home_clock")
        with slot:
            theme.head(t("home.clock_title"), sc.label)
            charts.show(charts.radial_clock(sc.df.groupby(sc.df["played_local"].dt.hour)["minutes"].sum(), "minutes", height=300),
                        key="home_clock")
            ui.moments(stats.moments(sc.df))

# --- one day in covers ----------------------------------------------------------------------------
theme.gap()
with theme.panel("teal", "day"):
    slot = st.container()
    days = sorted(set(data.all_plays()["played_local"].dt.date), reverse=True)[:60]
    with st.container(key="scope-home_day"):
        day = st.selectbox(t("home.pick_day"), days, index=0, format_func=fmt_date, key="home_day", width=300,
                           label_visibility="collapsed")
    with slot:
        everything = data.all_plays()
        one = everything[everything["played_local"].dt.date == day]
        theme.head(t("overview.day_title"), fmt_date(day),
                   t("overview.day_sub", plays=fmt_plays(len(one)), time=fmt_duration(one["minutes"].sum()),
                     first=one["played_local"].min().strftime("%H:%M"), last=one["played_local"].max().strftime("%H:%M")))
        ui.day_in_covers(one)

# --- recent plays and the mosaic -------------------------------------------------------------------
theme.gap()
left, right = st.columns([1, 1.5], gap="medium")
with left:
    with theme.panel("sky", "recent"):
        theme.head(t("overview.recent"), t("overview.recent_kicker"))
        ui.short_rows(data.all_plays(), limit=8)
        st.page_link(ui.PAGES["history"], label=t("overview.see_history"), icon=":material/arrow_forward:")
with right:
    with theme.panel("coral", "mosaic"):
        slot = st.container()
        sc = data.scope_bar("home_mosaic", ["album", "artist", "track"])
        with slot:
            theme.head(t("home.mosaic_title", what=t(f"scope.{sc.dim}").lower()), t("home.albums_meta"))
            ui.mosaic(stats.top(sc.df, sc.dim, "minutes", 18), "minutes", lambda r: fmt_duration(r.minutes), ratio=1.55)

ui.estimated_note(df)
