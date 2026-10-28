"""Overview. Question: what did I listen to in this period, and what dominates it?
The finding sits under the title; each sum sits in the card that explains it."""

import streamlit as st

from app.components import charts, data, theme, ui
from app.i18n import fmt_date, fmt_duration, fmt_int, fmt_pct, fmt_plays, fmt_seconds, t
from core import stats

f = data.get_filters()
df = data.filtered_plays()

if df.empty:
    theme.page_header(t("overview.title"), kicker=f.label)
    ui.empty_state(t("overview.empty"))
    st.stop()

k = stats.kpis(df)
artists = stats.top(df, "artist", "minutes", 6)
busiest = stats.busiest_day(df)
finding = t("overview.finding", artist=artists.iloc[0]["label"],
            share=fmt_pct(artists.iloc[0]["minutes"] / k["minutes"]) if k["minutes"] else "–",
            day=fmt_date(busiest[0]) if busiest else "–", time=fmt_duration(busiest[1]) if busiest else "–")
theme.page_header(t("overview.title"), kicker=f.label, lead=finding)

span_days = (df["played_local"].max() - df["played_local"].min()).days
freq = "D" if span_days <= 45 else ("W" if span_days <= 400 else "M")

main, rail = st.columns([1.85, 1], gap="large")
with main:
    with st.container(key="card-time"):
        theme.card_head(t("overview.time_title"), meta=f.label, figure=fmt_duration(k["minutes"]),
                        figure_sub=t("overview.time_sub", plays=fmt_int(k["plays"]), artists=fmt_int(k["artists"]),
                                     tracks=fmt_int(k["tracks"]), avg=fmt_seconds(k["avg_seconds"])))
        charts.show(charts.bar_timeline(stats.timeline(df, freq), "minutes", freq, t("common.minutes"), height=230),
                    key="ov_tl")

    last_day = df["played_local"].max().date()
    day = df[df["played_local"].dt.date == last_day]
    with st.container(key="card-day"):
        theme.card_head(t("overview.day_title"), meta=fmt_date(last_day),
                        figure_sub=t("overview.day_sub", plays=fmt_plays(len(day)), time=fmt_duration(day["minutes"].sum()),
                                     first=day["played_local"].min().strftime("%H:%M"),
                                     last=day["played_local"].max().strftime("%H:%M")))
        ui.day_in_covers(day)

    with st.container(key="card-genres"):
        genres = stats.top(df, "genre", "minutes", 6)
        theme.card_head(t("overview.genres_title"), meta=t("overview.genres_meta"))
        if genres.empty:
            ui.empty_state(t("tops.no_genre"))
        else:
            ui.genre_tiles(genres, k["minutes"])

with rail:
    with st.container(key="card-artists"):
        theme.card_head(t("overview.top_artists"), meta=t("overview.by_minutes"))
        ui.bar_list(artists, lambda r: fmt_duration(r.minutes), round_art=True, limit=5, metric="minutes")
        st.page_link(ui.PAGES["tops"], label=t("overview.see_tops"), icon=":material/arrow_forward:")

    with st.container(key="card-recent"):
        theme.card_head(t("overview.recent"), meta=t("overview.recent_kicker"))
        ui.short_rows(df, limit=5)
        st.page_link(ui.PAGES["history"], label=t("overview.see_history"), icon=":material/arrow_forward:")

ui.estimated_note(df)
