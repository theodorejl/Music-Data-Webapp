"""For you: a studio to generate discoveries, then their map and their table.

The studio explains the three modes and lets you pick one, choose how many tracks to discover
(10 to 200, with the expected loading time) and generate them. Each mode keeps its last results
(in the session and on disk) until it is generated again.
"""

import threading
import time
from html import escape

import pandas as pd
import streamlit as st

from app.components import charts, data, interactive, studio, theme, ui
from app.i18n import fmt_int, t
from core import recommend

MODES = recommend.ENGINES
f = data.get_filters()
window = data.filtered_plays()
everything = data.all_plays()
tz = data.timezone_name()
now = pd.Timestamp.now(tz=tz)

mode = st.session_state.setdefault("reco_mode", "neighbours")
base = window if not window.empty else everything
profile = recommend.build_profile(base, everything, now.hour)
moment_name = t(f"moments.{profile.moment}").lower()


def ago(iso: str) -> str:
    minutes = max(0, int((now - pd.Timestamp(iso)).total_seconds() // 60))
    if minutes < 1:
        return t("reco.ago_now")
    if minutes < 60:
        return t("reco.ago_min", n=minutes)
    if minutes < 48 * 60:
        return t("reco.ago_h", n=minutes // 60)
    return t("reco.ago_d", n=minutes // 1440)


def status_of(m: str) -> str:
    saved = data.saved_recommendations(m)
    if not saved:
        return t("reco.status_none")
    return t("reco.status", n=fmt_int(len(saved["df"])), ago=ago(saved["meta"]["at"]))


def generate(m: str, n: int, slot) -> None:
    """Run a mode in a worker thread and redraw the loading bar until it is done."""
    calls, seconds = recommend.estimate(m, n, profile)
    progress = recommend.Progress(calls, n)
    box: dict = {}

    def work():
        try:
            box["df"] = recommend.run(m, profile, n, progress)
        except Exception as exc:  # shown below instead of crashing the page
            box["error"] = exc

    worker = threading.Thread(target=work, daemon=True)
    worker.start()
    steps = {k: t(f"reco.step_{k}") for k in ("start", "graph", "graph2", "tracks", "catalogue", "charts", "radio")}
    labels = {"eta": t("reco.eta"), "eta_wait": t("reco.eta_wait"), "done": t("reco.eta_done"),
              "found": t("reco.found"), "calls": t("reco.calls")}
    while worker.is_alive():
        frac, el = progress.fraction, progress.elapsed
        eta = max(0.0, seconds - el) if frac < 0.2 else el * (1 - frac) / max(frac, 1e-3)
        step = steps.get(progress.step, "").format(detail=progress.detail or "…")
        slot.html(studio.progress_html(m, frac, el, eta, step, progress.found, n, progress.done, progress.planned, labels))
        time.sleep(0.12)
    worker.join()
    if "error" in box or box.get("df") is None or box["df"].empty:
        slot.error(t("reco.unavailable"))
        return
    df = box["df"]
    slot.html(studio.progress_html(m, 1.0, progress.elapsed, 0, t("reco.step_done", n=fmt_int(len(df))), len(df), n,
                                   progress.done, progress.planned, labels, done=True))
    used = {int(a) for a in df["seed_artist_id"].dropna()}
    seeds = [{"id": s.artist_id, "name": s.name, "genre": s.genre, "minutes": s.minutes, "img": s.picture}
             for s in {s.artist_id: s for s in profile.seeds + profile.moment_seeds}.values() if s.artist_id in used]
    data.save_recommendations(m, df, {"at": now.isoformat(), "n": n, "period": f.label, "moment": profile.moment,
                                      "seconds": round(progress.elapsed, 1), "seeds": seeds})
    time.sleep(0.6)
    st.rerun()


# --- the studio: three modes, how many tracks, generate ------------------------------------------------
with st.container(key="hero-ocean"):
    st.html(f"<div class='ds-kicker'><i></i>{escape(t('reco.kicker'))}</div>"
            f"<h1 class='ds-hero-title'>{escape(t('rail.foryou'))}</h1>"
            f"<p class='ds-hero-lead' style='max-width:80ch'>{t('reco.studio_lead', artists=', '.join(f'<b>{escape(s.name)}</b>' for s in profile.seeds[:3]) or '–')}</p>")
    cols = st.columns(3, gap="medium")
    for col, m in zip(cols, MODES):
        with col, st.container(key=f"mode-{m}"):
            theme.html(studio.mode_card(m, t(f"reco.engine_{m}"), t(f"reco.tag_{m}"), t(f"reco.how_{m}", moment=moment_name),
                                        status_of(m), m == mode))
            if st.button(t("reco.chosen") if m == mode else t("reco.choose"), key=f"pick_{m}", width="stretch",
                         type="secondary", disabled=m == mode, icon=":material/check:" if m == mode else None):
                st.session_state["reco_mode"] = m
                st.rerun()
    color = studio.MODE_COLORS[mode][0]
    st.html(f"<style>.st-key-hero-ocean{{--mc:{color}}}"
            f".st-key-mode-{mode}{{background:#17171c !important;border-color:{color} !important;"
            f"box-shadow:0 0 0 3px {color}55,0 24px 44px -26px {color} !important}}"
            f".st-key-mode-{mode} button{{background:transparent !important;border-color:{color} !important;opacity:1 !important}}"
            f".st-key-mode-{mode} button p,.st-key-mode-{mode} button span{{color:#fff !important}}</style>")

    theme.gap()
    left, mid, right = st.columns([2.2, 1, 1.2], gap="large", vertical_alignment="center")
    with left:
        st.html(f"<div class='rs-label'>{escape(t('reco.how_many'))}</div>")
        n = st.slider(t("reco.how_many"), recommend.MIN_TRACKS, recommend.MAX_TRACKS, 40, step=10, key="reco_n",
                      label_visibility="collapsed")
        st.html(f"<div class='rs-label'>{escape(t('reco.based_on'))}</div>")
        data.period_control()
    calls, seconds = recommend.estimate(mode, n, profile)
    with mid:
        st.html(f"<div class='rs-est'><b class='num'>≈ {seconds:.0f} s</b>"
                f"<span>{escape(t('reco.estimate', n=fmt_int(n), calls=fmt_int(calls)))}</span></div>")
    with right:
        saved = data.saved_recommendations(mode)
        go = st.button(t("reco.regenerate" if saved else "reco.generate", n=fmt_int(n), mode=t(f"reco.engine_{mode}")),
                       key="reco_go", type="primary", width="stretch", icon=":material/auto_awesome:")
        st.caption(t("reco.keep_note"))
    progress_slot = st.empty()
    if go:
        if base.empty:
            progress_slot.info(t("reco.empty"))
        else:
            generate(mode, n, progress_slot)

saved = data.saved_recommendations(mode)
mode_name = t(f"reco.engine_{mode}")

if not saved:
    with theme.panel("mist", "reco-empty"):
        st.html(f"<div class='rs-empty'>{studio.mode_art(mode)}<b>{escape(t('reco.empty_title', mode=mode_name))}</b>"
                f"<span>{escape(t('reco.empty_hint'))}</span></div>")
    st.stop()

recs, meta = saved["df"], saved["meta"]
meta_line = t("reco.meta", n=fmt_int(len(recs)), ago=ago(meta["at"]), period=meta.get("period", "–"))

# --- the map ------------------------------------------------------------------------------------------
theme.section(t("reco.map_section"), t("reco.map_note_mode", mode=mode_name))
names = list(dict.fromkeys([g for g, _ in profile.genres] + list(recs["genre"].dropna())))
names = [g for g in names if (recs["genre"] == g).any() or any(s["genre"] == g for s in meta["seeds"])][:6]
other = t("common.other")
genre_colors = charts.category_colors(names)
needs_other = recs["genre"].isna().any() or (~recs["genre"].isin(names)).any() or any(s["genre"] not in names for s in meta["seeds"])
genres = [(g, genre_colors[g]) for g in names] + ([(other, "#c4c9d0")] if needs_other else [])
map_labels = {"you": t("reco.map_you"), "neighbours": t("reco.engine_neighbours"), "genres": t("reco.engine_genres"),
              "moment": t("reco.engine_moment"), "hint": t("reco.map_hint"), "play": t("reco.play"), "pause": t("reco.pause"),
              "no_preview": t("reco.no_preview"), "loading": t("reco.loading_short"),
              "because": {e: t(f"reco.because_{e}") for e in MODES}}
with theme.panel("night", "reco-map"):
    theme.head(t("reco.map_title_mode", mode=mode_name), meta_line)
    interactive.rec_map(
        [{**s, "genre": s["genre"] if s["genre"] in names else other} for s in meta["seeds"]],
        [{"track_id": r.track_id, "title": r.title, "artist": r.artist_name, "engine": r.engine,
          "genre": r.genre if r.genre in names else other, "seed": r.seed_artist_id, "img": r.cover, "reason": r.reason}
         for r in recs.itertuples(index=False)],
        genres, map_labels, height=700 if len(recs) > 80 else 640)

# --- the table ----------------------------------------------------------------------------------------
theme.section(t("reco.table_section"), t("reco.table_note"))
with theme.white("reco-table"):
    interactive.rec_table(recs, {"title": t("common.track"), "artist": t("common.artist"), "album": t("common.album"),
                                 "why": t("reco.why"), "genre": t("common.genre"), "time": t("reco.length"),
                                 "search": t("reco.table_search"), "count": t("reco.table_count"),
                                 "because": t(f"reco.because_{mode}"), "open": "Deezer", "no_preview": t("reco.no_preview"),
                                 "play": t("reco.play")},
                          studio.MODE_COLORS[mode][0], {**genre_colors, other: "#c4c9d0"})
    export = pd.DataFrame({
        "#": range(1, len(recs) + 1), t("common.track"): recs["title"], t("common.artist"): recs["artist_name"],
        t("common.album"): recs["album_title"], t("reco.why"): recs["reason"], t("common.genre"): recs["genre"],
        "Deezer": recs["link"],
    })
    ui.excel_download(export, f"decouvertes_{mode}.xlsx", mode_name, f"{t('rail.foryou')} — {mode_name}", key="reco_xl",
                      formats={"#": "int"})
st.caption(t("reco.footnote"))
