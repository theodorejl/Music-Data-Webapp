"""Daily / weekly / monthly / yearly recap.

The URL can be shared as is: ?d=2026-10-28, ?w=2026-10-26 (Monday), ?y=2026&m=10 or ?y=2026,
plus &lang=fr|en.
"""

from datetime import timedelta
from html import escape

import pandas as pd
import streamlit as st

from app.components import charts, data, theme, ui, viz
from app.i18n import fmt_date, fmt_duration, fmt_int, fmt_month, fmt_plays, get_lang, t
from core import stats

MODES = ["day", "week", "month", "year"]

f = data.get_filters()
tz = data.timezone_name()
everything = stats.filter_frame(data.all_plays(), min_seconds=f.min_seconds)
st.title(t("wrapped.title"))
if everything.empty:
    ui.empty_state()
    st.stop()

local = everything["played_local"]
days = sorted(set(local.dt.date), reverse=True)
weeks = sorted({d - timedelta(days=d.weekday()) for d in days}, reverse=True)
months = sorted({(d.year, d.month) for d in days}, reverse=True)
years = sorted({y for y, _ in months}, reverse=True)

qp = st.query_params
default_mode = "day" if qp.get("d") else "week" if qp.get("w") else "month" if qp.get("m") else "year" if qp.get("y") else "week"
c1, c2 = st.columns([3, 2])
mode = c1.segmented_control(t("wrapped.mode"), MODES, default=default_mode, required=True,
                            format_func=lambda m: t(f"wrapped.{m}"), key="wr_mode")


def _parse_date(value):
    try:
        return pd.Timestamp(value).date()
    except (TypeError, ValueError):
        return None


keep = {"day": {"d"}, "week": {"w"}, "month": {"y", "m"}, "year": {"y"}}[mode]
for key in ("d", "w", "m", "y"):  # keep only the parameters of the current mode
    if key in qp and key not in keep:
        del qp[key]

if mode == "day":
    wanted = _parse_date(qp.get("d"))
    day = c2.selectbox(t("wrapped.pick_day"), days, index=days.index(wanted) if wanted in days else 0,
                       format_func=fmt_date, key="wr_day")
    start = pd.Timestamp(day).tz_localize(tz)
    end = pd.Timestamp(day + timedelta(days=1)).tz_localize(tz)
    period_name = fmt_date(day)
    qp.update({"d": day.isoformat(), "lang": get_lang()})
elif mode == "week":
    wanted = _parse_date(qp.get("w"))
    monday = c2.selectbox(t("wrapped.pick_week"), weeks, index=weeks.index(wanted) if wanted in weeks else 0,
                          format_func=lambda d: t("wrapped.week_of", date=fmt_date(d)), key="wr_week")
    start = pd.Timestamp(monday).tz_localize(tz)
    end = pd.Timestamp(monday + timedelta(days=7)).tz_localize(tz)
    period_name = t("wrapped.week_period", date=fmt_date(monday))
    qp.update({"w": monday.isoformat(), "lang": get_lang()})
elif mode == "month":
    wanted = (int(qp.get("y", 0) or 0), int(qp.get("m", 0) or 0))
    year, month = c2.selectbox(t("wrapped.month"), months, index=months.index(wanted) if wanted in months else 0,
                               format_func=lambda ym: fmt_month(pd.Timestamp(year=ym[0], month=ym[1], day=1)),
                               key="wr_month")
    start = pd.Timestamp(year=year, month=month, day=1, tz=tz)
    end = start + pd.offsets.MonthBegin(1)
    period_name = fmt_month(start)
    qp.update({"y": str(year), "m": str(month), "lang": get_lang()})
else:
    wanted_y = int(qp.get("y", 0) or 0)
    year = c2.selectbox(t("wrapped.year"), years, index=years.index(wanted_y) if wanted_y in years else 0,
                        key="wr_year")
    start = pd.Timestamp(year=year, month=1, day=1, tz=tz)
    end = pd.Timestamp(year=year + 1, month=1, day=1, tz=tz)
    period_name = str(year)
    qp.update({"y": str(year), "lang": get_lang()})

df = stats.filter_frame(everything, start, end)
if df.empty:
    ui.empty_state()
    st.stop()

k = stats.kpis(df)
firsts = stats.first_listens(everything, "artist")
new_artists = int(((firsts["first_played"] >= start) & (firsts["first_played"] < end)).sum())
top_artist = stats.top(df, "artist", "minutes", 1).iloc[0]
top_genre = stats.top(df, "genre", "minutes", 1)
busiest = stats.busiest_day(df)
fav_hour = int(df["played_local"].dt.hour.value_counts().idxmax())

st.markdown(f"<p class='ds-sub'>{escape(t('wrapped.your_period', period=period_name))} · "
            f"{escape(t('wrapped.finding', artist=str(top_artist['label']), time=fmt_duration(top_artist['minutes'])))}</p>",
            unsafe_allow_html=True)
ui.kpi_row([
    (t("common.listening_time"), fmt_duration(k["minutes"]), t("common.estimated_short")),
    (t("common.plays"), fmt_int(k["plays"]), None),
    (t("common.artists"), fmt_int(k["artists"]), None),
    (t("wrapped.new_artists"), fmt_int(new_artists), t("wrapped.new_artists_cap")),
])
st.markdown("<div class='ds-section-gap'></div>", unsafe_allow_html=True)

c_art, c_tracks, c_albums = st.columns([1, 1.15, 1.15], gap="medium")
with c_art:
    with st.container(key="card-wr-artist"):
        theme.card_head(t("wrapped.top_artist"))
        if isinstance(top_artist["image"], str):
            st.image(top_artist["image"].replace("250x250", "500x500"), width="stretch")
        st.html(f"<div class='ds-figure'>{escape(str(top_artist['label']))}</div>"
                f"<p class='ds-figure-sub'>{escape(t('wrapped.top_artist_detail', time=fmt_duration(top_artist['minutes']), plays=fmt_int(top_artist['plays'])))}</p>")
        facts = []
        if not top_genre.empty:
            facts.append(t("wrapped.top_genre_plain", genre=top_genre.iloc[0]["label"]))
        if busiest and mode != "day":
            facts.append(t("wrapped.busiest_day_plain", date=fmt_date(busiest[0]), time=fmt_duration(busiest[1])))
        facts.append(t("wrapped.fav_hour_plain", hour=fav_hour))
        st.html("<div class='ds-stamp'>" + "<br>".join(escape(x) for x in facts) + "</div>")
with c_tracks:
    with st.container(key="card-wr-tracks"):
        theme.card_head(t("wrapped.top_tracks"), meta=t("overview.by_plays"))
        ui.bar_list(stats.top(df, "track", "plays", 7), lambda r: fmt_plays(r.plays), limit=7)
with c_albums:
    with st.container(key="card-wr-albums"):
        theme.card_head(t("wrapped.top_albums"), meta=t("overview.by_plays"))
        ui.bar_list(stats.top(df, "album", "plays", 7), lambda r: fmt_plays(r.plays), limit=7)

with st.container(key="card-wr-rhythm"):
    theme.card_head(t("wrapped.rhythm"), meta=period_name)
    if mode == "day":
        per_hour = df.groupby(df["played_local"].dt.hour)["minutes"].sum().reindex(range(24), fill_value=0)
        charts.show(charts.bar_categories([f"{h}h" for h in per_hour.index], per_hour.round(0).tolist(),
                                          t("common.minutes"), height=220), key="wr_tl")
    else:
        freq = "M" if mode == "year" else "D"
        tl = stats.timeline(df, freq)
        if mode == "week":  # always show the 7 days, even silent ones
            full = pd.date_range(start.tz_localize(None), periods=7, freq="D")
            tl = tl.set_index("period").reindex(full, fill_value=0).rename_axis("period").reset_index()
        charts.show(charts.bar_timeline(tl, "minutes", freq, t("common.minutes"), height=220, highlight_last=False),
                    key="wr_tl")

with st.container(key="card-wr-print"):
    theme.card_head(t("explore.fingerprint_title"), meta=t("explore.fingerprint_kicker"))
    svg = viz.fingerprint_svg(df, t("explore.fingerprint_title"), period_name)
    st.markdown(svg, unsafe_allow_html=True)
    st.download_button(t("explore.download_svg"), svg.encode("utf-8"), file_name="empreinte_sonore.svg",
                       mime="image/svg+xml", icon=":material/download:", key="wr_fp_dl")
st.caption(t("wrapped.share_hint"))
