"""Monthly / yearly recap. The URL (?y=2026&m=10&lang=fr) can be shared as is."""

from html import escape

import pandas as pd
import streamlit as st

from app.components import charts, data, ui
from app.i18n import fmt_date, fmt_duration, fmt_int, fmt_month, get_lang, t
from core import stats

f = data.get_filters()
everything = stats.filter_frame(data.all_plays(), min_seconds=f.min_seconds)
ui.header(t("wrapped.title"))
if everything.empty:
    ui.empty_state()
    st.stop()

local = everything["played_local"]
months = sorted({(d.year, d.month) for d in local}, reverse=True)
years = sorted({y for y, _ in months}, reverse=True)

qp = st.query_params
default_mode = "month" if qp.get("m") else ("year" if qp.get("y") else "month")
c1, c2 = st.columns([1, 2])
mode = c1.segmented_control(t("wrapped.mode"), ["month", "year"], default=default_mode, required=True,
                            format_func=lambda m: t(f"wrapped.{m}"), key="wr_mode")
if mode == "month":
    wanted = (int(qp.get("y", 0) or 0), int(qp.get("m", 0) or 0))
    idx = months.index(wanted) if wanted in months else 0
    year, month = c2.selectbox(t("wrapped.month"), months, index=idx, key="wr_month",
                               format_func=lambda ym: fmt_month(pd.Timestamp(year=ym[0], month=ym[1], day=1)))
    start = pd.Timestamp(year=year, month=month, day=1, tz=data.timezone_name())
    end = start + pd.offsets.MonthBegin(1)
    period_name = fmt_month(start)
    qp.update({"y": str(year), "m": str(month), "lang": get_lang()})
else:
    wanted_y = int(qp.get("y", 0) or 0)
    year = c2.selectbox(t("wrapped.year"), years, index=years.index(wanted_y) if wanted_y in years else 0, key="wr_year")
    start = pd.Timestamp(year=year, month=1, day=1, tz=data.timezone_name())
    end = pd.Timestamp(year=year + 1, month=1, day=1, tz=data.timezone_name())
    period_name = str(year)
    if "m" in qp:
        del qp["m"]
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

st.markdown(
    f"""<div class="ds-wrapped">
<div class="ds-muted">{escape(t('wrapped.your_period', period=period_name))}</div>
<div class="ds-hero">{escape(fmt_duration(k['minutes']))}</div>
<div class="ds-sub" style="margin-top:.4rem">{escape(t('wrapped.summary', plays=fmt_int(k['plays']),
    artists=fmt_int(k['artists']), new=fmt_int(new_artists)))}</div>
</div>""",
    unsafe_allow_html=True,
)

c_img, c_txt = st.columns([1, 2], gap="large", vertical_alignment="center")
with c_img:
    if isinstance(top_artist["image"], str):
        st.image(top_artist["image"].replace("250x250", "500x500"), width="stretch")
with c_txt:
    st.caption(t("wrapped.top_artist"))
    st.markdown(f"<div class='ds-hero' style='font-size:2.4rem'>{escape(str(top_artist['label']))}</div>",
                unsafe_allow_html=True)
    st.markdown(t("wrapped.top_artist_detail", time=fmt_duration(top_artist["minutes"]),
                  plays=fmt_int(top_artist["plays"])))
    facts = []
    if not top_genre.empty:
        facts.append(t("wrapped.top_genre", genre=top_genre.iloc[0]["label"]))
    if busiest:
        facts.append(t("wrapped.busiest_day", date=fmt_date(busiest[0]), time=fmt_duration(busiest[1])))
    facts.append(t("wrapped.fav_hour", hour=fav_hour))
    for fact in facts:
        st.markdown(f"- {fact}")

left, right = st.columns(2, gap="large")
with left:
    st.subheader(t("wrapped.top_tracks"))
    tracks = stats.top(df, "track", "plays", 5)
    for row in tracks.itertuples():
        a, b = st.columns([1, 5], vertical_alignment="center")
        if isinstance(row.image, str):
            a.image(row.image, width="stretch")
        b.markdown(f"**{row.rank}. {row.label}**  \n{row.sublabel} · {fmt_int(row.plays)} {t('common.plays_short')}")
with right:
    st.subheader(t("wrapped.top_albums"))
    ui.cover_grid(stats.top(df, "album", "plays", 6), "album", ui.value_formatter("plays"), columns=3, key="wr_al")

freq = "D" if mode == "month" else "M"
st.subheader(t("wrapped.rhythm"))
charts.show(charts.bar_timeline(stats.timeline(df, freq), "minutes", freq, t("common.minutes"), height=220), key="wr_tl")
st.caption(t("wrapped.share_hint"))
