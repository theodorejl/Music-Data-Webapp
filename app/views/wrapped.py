"""Recaps: a day, a week, a month or a year told as a set of poster panels.

The URL can be shared as is: ?d=2026-10-28, ?w=2026-10-26 (Monday), ?y=2026&m=10 or ?y=2026,
plus &lang=fr|en.
"""

from datetime import timedelta
from html import escape

import pandas as pd
import streamlit as st

from app.components import charts, data, theme, ui, viz
from app.i18n import fmt_date, fmt_duration, fmt_int, fmt_month, fmt_pct, fmt_plays, get_lang, t
from core import stats

MODES = ["day", "week", "month", "year"]

f = data.get_filters()
tz = data.timezone_name()
everything = stats.filter_frame(data.all_plays(), min_seconds=f.min_seconds)
if everything.empty:
    theme.hero("butter", t("rail.wrapped"), escape(t("common.no_data")))
    st.stop()

local = everything["played_local"]
days = sorted(set(local.dt.date), reverse=True)
weeks = sorted({d - timedelta(days=d.weekday()) for d in days}, reverse=True)
months = sorted({(d.year, d.month) for d in days}, reverse=True)
years = sorted({y for y, _ in months}, reverse=True)

qp = st.query_params
default_mode = "day" if qp.get("d") else "week" if qp.get("w") else "month" if qp.get("m") else "year" if qp.get("y") else "week"


def _parse_date(value):
    try:
        return pd.Timestamp(value).date()
    except (TypeError, ValueError):
        return None


# The header holds the controls; its sentence and its figure are filled once the period is known.
with st.container(key="hero-butter"):
    left, right = st.columns([1.15, 1], gap="large", vertical_alignment="center")
    with left:
        st.html(f"<div class='ds-kicker'><i></i>{escape(t('wrapped.kicker'))}</div><h1 class='ds-hero-title'>{escape(t('rail.wrapped'))}</h1>")
        lead_slot = st.empty()
        mode = st.segmented_control(t("wrapped.mode"), MODES, default=default_mode, required=True,
                                    format_func=lambda m: t(f"wrapped.{m}"), key="wr_mode", label_visibility="collapsed")
        keep = {"day": {"d"}, "week": {"w"}, "month": {"y", "m"}, "year": {"y"}}[mode]
        for key in ("d", "w", "m", "y"):  # keep only the parameters of the current mode
            if key in qp and key not in keep:
                del qp[key]
        if mode == "day":
            wanted = _parse_date(qp.get("d"))
            day = st.selectbox(t("wrapped.pick_day"), days, index=days.index(wanted) if wanted in days else 0,
                               format_func=fmt_date, key="wr_day", width=320, label_visibility="collapsed")
            start = pd.Timestamp(day).tz_localize(tz)
            end = pd.Timestamp(day + timedelta(days=1)).tz_localize(tz)
            period_name = fmt_date(day)
            qp.update({"d": day.isoformat(), "lang": get_lang()})
        elif mode == "week":
            wanted = _parse_date(qp.get("w"))
            monday = st.selectbox(t("wrapped.pick_week"), weeks, index=weeks.index(wanted) if wanted in weeks else 0,
                                  format_func=lambda d: t("wrapped.week_of", date=fmt_date(d)), key="wr_week", width=320,
                                  label_visibility="collapsed")
            start = pd.Timestamp(monday).tz_localize(tz)
            end = pd.Timestamp(monday + timedelta(days=7)).tz_localize(tz)
            period_name = t("wrapped.week_period", date=fmt_date(monday))
            qp.update({"w": monday.isoformat(), "lang": get_lang()})
        elif mode == "month":
            wanted = (int(qp.get("y", 0) or 0), int(qp.get("m", 0) or 0))
            year, month = st.selectbox(t("wrapped.month"), months, index=months.index(wanted) if wanted in months else 0,
                                       format_func=lambda ym: fmt_month(pd.Timestamp(year=ym[0], month=ym[1], day=1)),
                                       key="wr_month", width=320, label_visibility="collapsed")
            start = pd.Timestamp(year=year, month=month, day=1, tz=tz)
            end = start + pd.offsets.MonthBegin(1)
            period_name = fmt_month(start)
            qp.update({"y": str(year), "m": str(month), "lang": get_lang()})
        else:
            wanted_y = int(qp.get("y", 0) or 0)
            year = st.selectbox(t("wrapped.year"), years, index=years.index(wanted_y) if wanted_y in years else 0,
                                key="wr_year", width=320, label_visibility="collapsed")
            start = pd.Timestamp(year=year, month=1, day=1, tz=tz)
            end = pd.Timestamp(year=year + 1, month=1, day=1, tz=tz)
            period_name = str(year)
            qp.update({"y": str(year), "lang": get_lang()})
    art_slot = right.empty()

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

lead_slot.html(f"<p class='ds-hero-lead'>{escape(t('wrapped.your_period', period=period_name))} — "
               + t("wrapped.finding_html", artist=f"<b>{escape(str(top_artist['label']))}</b>",
                   time=f"<b>{escape(fmt_duration(top_artist['minutes']))}</b>") + "</p>")
hours = int(k["minutes"] // 60)
art_slot.markdown("<div class='ds-art'>" + ui.art_giant(fmt_int(hours) if hours else fmt_int(round(k["minutes"])),
                                                         "h" if hours else "min", t("wrapped.giant_cap", plays=fmt_plays(k["plays"])))
                  + "</div>", unsafe_allow_html=True)

ui.stat_tiles([
    (t("common.listening_time"), fmt_duration(k["minutes"]), t("common.estimated_short"), "coral", None),
    (t("common.plays"), fmt_int(k["plays"]), None, "sky", None),
    (t("common.artists"), fmt_int(k["artists"]), None, "lilac", None),
    (t("wrapped.new_artists"), fmt_int(new_artists), t("wrapped.new_artists_cap"), "lime", None),
])
theme.gap()

c_art, c_tracks, c_albums = st.columns([1, 1.1, 1.1], gap="medium")
with c_art:
    with theme.panel("coral", "wr-artist"):
        theme.head(t("wrapped.top_artist"), period_name)
        if isinstance(top_artist["image"], str):
            st.image(top_artist["image"].replace("250x250", "500x500"), width="stretch")
        st.html(f"<div class='ds-figure' style='font-size:40px'>{escape(str(top_artist['label']))}</div>"
                f"<p class='ds-figure-sub'>{escape(t('wrapped.top_artist_detail', time=fmt_duration(top_artist['minutes']), plays=fmt_int(top_artist['plays'])))}</p>")
with c_tracks:
    with theme.panel("sky", "wr-tracks"):
        theme.head(t("wrapped.top_tracks"), t("overview.by_plays"))
        ui.rank_list(stats.top(df, "track", "plays", 8), lambda r: fmt_plays(r.plays), "plays", limit=8)
with c_albums:
    with theme.panel("lilac", "wr-albums"):
        theme.head(t("wrapped.top_albums"), t("overview.by_plays"))
        albums = stats.top(df, "album", "plays", 8)
        ui.rank_list(albums, lambda r: fmt_plays(r.plays), "plays", colors=theme.PALETTE[2:] + theme.PALETTE[:2], limit=8)

theme.gap()
left, right = st.columns([1.5, 1], gap="medium")
with left:
    with theme.panel("lime", "wr-rhythm"):
        theme.head(t("wrapped.rhythm"), period_name)
        if mode == "day":
            per_hour = df.groupby(df["played_local"].dt.hour)["minutes"].sum().reindex(range(24), fill_value=0)
            charts.show(charts.bars([f"{h} h" for h in per_hour.index], per_hour.round(0).tolist(), "minutes", height=280,
                                    colors=[charts.hour_color(h + 0.5) for h in per_hour.index]), key="wr_tl")
        else:
            freq = "M" if mode == "year" else "D"
            tl_ = stats.timeline(df, freq)
            if mode == "week":  # always show the 7 days, even silent ones
                full = pd.date_range(start.tz_localize(None), periods=7, freq="D")
                tl_ = tl_.set_index("period").reindex(full, fill_value=0).rename_axis("period").reset_index()
            charts.show(charts.bar_timeline(tl_, "minutes", freq, t("common.minutes"), height=280), key="wr_tl")
with right:
    with theme.panel("teal", "wr-facts"):
        theme.head(t("wrapped.facts"), period_name)
        facts = []
        if not top_genre.empty:
            facts.append((t("wrapped.fact_genre"), str(top_genre.iloc[0]["label"]),
                          fmt_pct(float(top_genre.iloc[0]["minutes"]) / k["minutes"]) if k["minutes"] else ""))
        if busiest and mode != "day":
            facts.append((t("wrapped.fact_day"), fmt_date(busiest[0]), fmt_duration(busiest[1])))
        facts.append((t("wrapped.fact_hour"), f"{fav_hour} h", t("wrapped.fact_hour_cap")))
        facts.append((t("wrapped.fact_tracks"), fmt_int(k["tracks"]), t("wrapped.fact_tracks_cap", albums=fmt_int(k["albums"]))))
        st.html("".join(f"<div style='padding:12px 0;border-top:1px solid rgba(255,255,255,.7)'><div class='ds-meta'>{escape(a)}</div>"
                        f"<div class='ds-figure' style='font-size:34px;margin:4px 0 0'>{escape(b)}</div>"
                        f"<div class='ds-figure-sub' style='margin:2px 0 0'>{escape(c)}</div></div>" for a, b, c in facts))

theme.gap()
with theme.panel("rose", "wr-print"):
    theme.head(t("explore.fingerprint_title"), t("explore.fingerprint_kicker"))
    svg = viz.fingerprint_svg(df, t("explore.fingerprint_title"), period_name)
    left, right = st.columns([1.4, 1], gap="large", vertical_alignment="center")
    with left:
        theme.html(svg)
    with right:
        st.html(f"<p class='ds-hero-lead'>{escape(t('explore.fingerprint_story'))}</p>")
        st.download_button(t("explore.download_svg"), svg.encode("utf-8"), file_name="empreinte_sonore.svg",
                           mime="image/svg+xml", icon=":material/download:", key="wr_fp_dl", type="primary")
st.caption(t("wrapped.share_hint"))
