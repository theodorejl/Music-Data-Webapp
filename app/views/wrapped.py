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
theme.page_header(t("wrapped.title"), kicker=t("wrapped.kicker"), dot="peach")
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

theme.hero(period_name, t("wrapped.your_period", period=period_name), [
    (t("common.listening_time"), fmt_duration(k["minutes"])),
    (t("common.plays"), fmt_int(k["plays"])),
    (t("common.artists"), fmt_int(k["artists"])),
    (t("wrapped.new_artists"), fmt_int(new_artists)),
], palette=("#F7CDB8", "#D7C8F2", "#C9D0F7", "#F6E2A8"))

c_img, c_txt = st.columns([1, 2], gap="large", vertical_alignment="center")
with c_img:
    if isinstance(top_artist["image"], str):
        st.image(top_artist["image"].replace("250x250", "500x500"), width="stretch")
with c_txt:
    st.caption(t("wrapped.top_artist"))
    st.markdown(f"<div class='ds-hero-num' style='font-size:clamp(2.2rem,1.4rem + 2.4vw,3.6rem)'>"
                f"{escape(str(top_artist['label']))}</div>", unsafe_allow_html=True)
    st.markdown(t("wrapped.top_artist_detail", time=fmt_duration(top_artist["minutes"]),
                  plays=fmt_int(top_artist["plays"])))
    facts = []
    if not top_genre.empty:
        facts.append(t("wrapped.top_genre", genre=top_genre.iloc[0]["label"]))
    if busiest and mode != "day":
        facts.append(t("wrapped.busiest_day", date=fmt_date(busiest[0]), time=fmt_duration(busiest[1])))
    facts.append(t("wrapped.fav_hour", hour=fav_hour))
    for fact in facts:
        st.markdown(f"- {fact}")

left, right = st.columns(2, gap="large")
with left:
    theme.section(t("wrapped.top_tracks"))
    tracks = stats.top(df, "track", "plays", 5)
    for row in tracks.itertuples():
        a, b = st.columns([1, 5], vertical_alignment="center")
        if isinstance(row.image, str):
            a.image(row.image, width="stretch")
        b.markdown(f"**{row.rank}. {row.label}**  \n{row.sublabel} · {fmt_plays(row.plays)}")
with right:
    theme.section(t("wrapped.top_albums"))
    ui.cover_grid(stats.top(df, "album", "plays", 6), "album", ui.value_formatter("plays"), columns=3, key="wr_al")

theme.section(t("wrapped.rhythm"))
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
    charts.show(charts.bar_timeline(tl, "minutes", freq, t("common.minutes"), height=220), key="wr_tl")
theme.section(t("explore.fingerprint_title"), t("explore.fingerprint_kicker"))
svg = viz.fingerprint_svg(df, t("explore.fingerprint_title"), period_name)
st.markdown(svg, unsafe_allow_html=True)
st.download_button(t("explore.download_svg"), svg.encode("utf-8"), file_name="empreinte_sonore.svg",
                   mime="image/svg+xml", icon=":material/download:", key="wr_fp_dl")
st.caption(t("wrapped.share_hint"))
