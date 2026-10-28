"""Journal: every play, searchable, with exports."""

import math
from html import escape

import streamlit as st

from app.components import data, theme, ui
from app.i18n import fmt_datetime_short, fmt_duration, fmt_int, fmt_seconds, get_lang, t
from core import stats

PAGE_SIZE = 50

f = data.get_filters()
df = stats.filter_frame(data.all_plays(), f.start, f.end)
last = data.all_plays().head(1)
lead = t("history.hero_lead", n=f"<b>{fmt_int(len(df))}</b>", time=f"<b>{escape(fmt_duration(df['minutes'].sum()))}</b>")
if not last.empty:
    r = last.iloc[0]
    lead += " " + t("history.hero_last", track=f"<b>{escape(str(r['track_title']))}</b>", artist=escape(str(r["artist_name"])),
                    when=escape(fmt_datetime_short(r["played_local"])))
theme.hero("mist", t("rail.history"), lead, f.label, controls=data.period_control,
           art=ui.art_giant(fmt_int(len(df)), "", t("history.giant_cap")))

if df.empty:
    ui.empty_state()
    st.stop()

with theme.white("journal"):
    c1, c2, c3 = st.columns([3, 1.2, 1], vertical_alignment="bottom")
    query = c1.text_input(t("history.search"), placeholder=t("history.search_placeholder"), key="hist_q")
    found = stats.search_history(df, query.strip())
    pages = max(1, math.ceil(len(found) / PAGE_SIZE))
    c2.html(f"<p class='ds-meta' style='margin:0 0 12px'>{escape(t('history.count', n=fmt_int(len(found))))}</p>")
    page = c3.number_input(t("history.page", total=pages), min_value=1, max_value=pages, value=1, step=1,
                           key=f"hist_page_{query}_{f.period}")

    chunk = found.iloc[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]
    event = st.dataframe(
        {
            t("common.time"): [fmt_datetime_short(x) for x in chunk["played_local"]],
            "": chunk["cover"].tolist(),
            t("common.track"): chunk["track_title"].tolist(),
            t("common.artist"): chunk["artist_name"].tolist(),
            t("common.album"): chunk["album_title"].tolist(),
            t("common.genre"): chunk["genre"].fillna("–").tolist(),
            t("common.listened"): [fmt_seconds(s) + ("*" if e else "") for s, e in
                                   zip(chunk["listened_seconds"], chunk["duration_is_estimated"])],
        },
        hide_index=True, height=min(38 + 35 * len(chunk), 1800), key="hist_table",
        on_select="rerun", selection_mode="single-row",
        column_config={"": st.column_config.ImageColumn("", width="small"),
                       t("common.listened"): st.column_config.TextColumn(alignment="right")},
    )
    if event.selection.rows:
        ui.open_detail("track", chunk.iloc[event.selection.rows[0]]["track_id"])
    st.caption(t("common.click_row") + " · " + t("history.star_note"))

    c1, c2, _ = st.columns([1, 1, 2])
    with c1:
        ui.csv_download(ui.export_plays(found), "deezer_plays.csv", key="hist_dl")
    with c2:
        st.download_button(t("common.download_excel"), data.history_xlsx(get_lang(), tuple(int(i) for i in found["play_id"])),
                           file_name="historique_deezer.xlsx" if get_lang() == "fr" else "deezer_history.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           icon=":material/table_view:", key="hist_xlsx")
