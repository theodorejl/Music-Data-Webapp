"""Home: what did I listen to in this period, and what dominates it?
A mosaic of colour panels: the headline in the sky header, then key figures, leaders,
genres, the flow of time, the clock of the day, the last day in covers, recent plays."""

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

k = stats.kpis(df)
artists = stats.top(df, "artist", "minutes", 8)
busiest = stats.busiest_day(df)
span_days = (df["played_local"].max() - df["played_local"].min()).days
freq = "D" if span_days <= 45 else ("W" if span_days <= 400 else "M")
timeline = stats.timeline(df, freq)
leader = artists.iloc[0]

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

# --- leaders and genres -------------------------------------------------------------------------
genre_of = data.artist_genres()
left, right = st.columns([1.25, 1], gap="medium")
with left:
    with theme.panel("rose", "artists"):
        theme.head(t("overview.top_artists"), t("overview.by_minutes"))
        cmap = charts.category_colors([genre_of.get(int(a)) for a in artists["key"] if genre_of.get(int(a))])
        colors = [cmap.get(genre_of.get(int(a)), charts.OTHER) for a in artists["key"]]
        ui.rank_list(artists, lambda r: fmt_duration(r.minutes), "minutes", colors=colors, round_art=True, limit=7)
        st.caption(t("home.bar_colour_note"))
with right:
    with theme.panel("lilac", "genres"):
        genres = stats.top(df, "genre", "minutes", 6)
        theme.head(t("overview.genres_title"), t("overview.genres_meta"))
        if genres.empty:
            ui.empty_state(t("tops.no_genre"))
        else:
            other = t("common.other")
            rest = df["minutes"].sum() - genres["minutes"].sum()
            labels = genres["label"].tolist() + ([other] if rest > 1 else [])
            values = genres["minutes"].tolist() + ([rest] if rest > 1 else [])
            charts.show(charts.donut(labels, values, fmt_int(len(df["genre"].dropna().unique())), t("home.genres_center"),
                                     height=330, other_label=other), key="home_donut")
            cmap = charts.category_colors(labels, other)
            ui.legend([(lab, cmap[lab]) for lab in labels])

theme.gap()
left, right = st.columns([1.6, 1], gap="medium")
with left:
    with theme.panel("lime", "flow"):
        theme.head(t("overview.time_title"), f.label)
        theme.figure(escape(fmt_duration(k["minutes"])), t("overview.time_sub", plays=fmt_int(k["plays"]), artists=fmt_int(k["artists"]),
                                                             tracks=fmt_int(k["tracks"]), avg=fmt_seconds(k["avg_seconds"])))
        charts.show(charts.flow(timeline, "minutes", freq, t("common.minutes"), "lime", height=270,
                                avg_label=t("home.average"), peak_label=t("home.record")), key="home_flow")
with right:
    with theme.panel("butter", "clock"):
        theme.head(t("home.clock_title"), t("home.clock_meta"))
        by_hour = df.groupby(df["played_local"].dt.hour)["minutes"].sum()
        charts.show(charts.radial_clock(by_hour, "minutes", height=360), key="home_clock")

theme.gap()
last_day = df["played_local"].max().date()
day = df[df["played_local"].dt.date == last_day]
with theme.panel("teal", "day"):
    theme.head(t("overview.day_title"), fmt_date(last_day),
               t("overview.day_sub", plays=fmt_plays(len(day)), time=fmt_duration(day["minutes"].sum()),
                 first=day["played_local"].min().strftime("%H:%M"), last=day["played_local"].max().strftime("%H:%M")))
    ui.day_in_covers(day)

theme.gap()
left, right = st.columns([1, 1.5], gap="medium")
with left:
    with theme.panel("sky", "recent"):
        theme.head(t("overview.recent"), t("overview.recent_kicker"))
        ui.short_rows(df, limit=7)
        st.page_link(ui.PAGES["history"], label=t("overview.see_history"), icon=":material/arrow_forward:")
with right:
    with theme.panel("coral", "albums"):
        theme.head(t("home.albums_title"), t("home.albums_meta"))
        ui.mosaic(stats.top(df, "album", "minutes", 18), "minutes", lambda r: fmt_duration(r.minutes), ratio=1.55)
        st.page_link(ui.PAGES["tops"], label=t("overview.see_tops"), icon=":material/arrow_forward:")

ui.estimated_note(df)
