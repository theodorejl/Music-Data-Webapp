"""For you: a studio to generate real discoveries, then their map of sound and their table.

The studio explains the three modes and lets you pick one, set the boldness, choose how many
tracks to discover (10 to 200, with the expected loading time) and generate them. Each mode keeps
its last results (in the session and on disk) until it is generated again. Artists already in
your history or your Deezer library are never suggested.
"""

import threading
import time
from html import escape

import pandas as pd
import streamlit as st

from app.components import data, interactive, studio, theme, ui
from app.i18n import fmt_int, get_lang, t
from core import atlas, recommend, soundmap

MODES = recommend.ENGINES
f = data.get_filters()
window = data.filtered_plays()
everything = data.all_plays()
tz = data.timezone_name()
now = pd.Timestamp.now(tz=tz)

mode = st.session_state.get("reco_mode", "neighbours")
if mode not in MODES:
    mode = st.session_state["reco_mode"] = "neighbours"
base = window if not window.empty else everything


@st.cache_data(ttl=600, show_spinner=False)
def _library_frame() -> pd.DataFrame:
    lib = data.library()
    parts = [lib.favorites[["artist_id", "artist_name"]]] if not lib.favorites.empty else []
    if not lib.playlist_tracks.empty:
        parts.append(lib.playlist_tracks[["artist_id", "artist_name", "track_id"]])
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=["artist_id", "artist_name", "track_id"])


profile = recommend.build_profile(base, everything, now.hour, data.raw_data().tags, _library_frame())
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


def saved_for(m: str) -> dict | None:
    saved = data.saved_recommendations(m)
    # results made before the map of sound lack their sub-genre: treat them as not generated
    return saved if saved and "subgenre" in saved["df"].columns else None


def status_of(m: str) -> str:
    saved = saved_for(m)
    if not saved:
        return t("reco.status_none")
    return t("reco.status", n=fmt_int(len(saved["df"])), ago=ago(saved["meta"]["at"]))


def map_seed(s: recommend.Seed) -> dict:
    return {"id": s.artist_id, "name": s.name, "img": s.picture, "subgenre": s.subgenre,
            "x": s.x / soundmap.WIDTH, "y": s.y / soundmap.HEIGHT, "minutes": s.minutes}


def generate(m: str, n: int, boldness: str, slot) -> None:
    """Run a mode in a worker thread and redraw the loading bar until it is done."""
    calls, seconds = recommend.estimate(m, n, profile, boldness)
    progress = recommend.Progress(calls, n)
    box: dict = {}

    def work():
        try:
            box["df"] = recommend.run(m, profile, n, progress, boldness=boldness)
        except Exception as exc:  # shown below instead of crashing the page
            box["error"] = exc

    worker = threading.Thread(target=work, daemon=True)
    worker.start()
    steps = {k: t(f"reco.step_{k}") for k in ("start", "graph", "graph2", "tracks", "search", "playlists", "radio")}
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
    pool = {s.artist_id: s for s in profile.seeds + profile.moment_seeds if s.x is not None}
    used = {int(a) for a in df["seed_artist_id"].dropna()}
    seeds = [map_seed(s) for s in list(pool.values())[:24]] + [map_seed(pool[a]) for a in used
                                                                 if a in pool and a not in [s.artist_id for s in list(pool.values())[:24]]]
    data.save_recommendations(m, df, {"at": now.isoformat(), "n": n, "period": f.label, "moment": profile.moment,
                                      "boldness": boldness, "seconds": round(progress.elapsed, 1), "seeds": seeds,
                                      "home": profile.home[:40]})
    time.sleep(0.6)
    st.rerun()


# --- the studio: three modes, boldness, how many tracks, generate -----------------------------------
with st.container(key="hero-ocean"):
    st.html(f"<div class='ds-kicker'><i></i>{escape(t('reco.kicker'))}</div>"
            f"<h1 class='ds-hero-title'>{escape(t('rail.foryou'))}</h1>"
            f"<p class='ds-hero-lead' style='max-width:84ch'>{t('reco.studio_lead', artists=', '.join(f'<b>{escape(s.name)}</b>' for s in profile.seeds[:3]) or '–', known=f'<b>{fmt_int(len(profile.known_artists))}</b>')}</p>")
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
        st.html(f"<div class='rs-label'>{escape(t('reco.boldness'))}</div>")
        boldness = st.segmented_control(t("reco.boldness"), list(recommend.BOLDNESS), default="balanced", required=True,
                                        key="reco_bold", format_func=lambda b: t(f"reco.bold_{b}"),
                                        label_visibility="collapsed")
        st.caption(t(f"reco.bold_{boldness}_help"))
        st.html(f"<div class='rs-label'>{escape(t('reco.based_on'))}</div>")
        data.period_control()
    calls, seconds = recommend.estimate(mode, n, profile, boldness)
    with mid:
        st.html(f"<div class='rs-est'><b class='num'>≈ {seconds:.0f} s</b>"
                f"<span>{escape(t('reco.estimate', n=fmt_int(n), calls=fmt_int(calls)))}</span></div>")
    with right:
        saved = saved_for(mode)
        go = st.button(t("reco.regenerate" if saved else "reco.generate", n=fmt_int(n), mode=t(f"reco.engine_{mode}")),
                       key="reco_go", type="primary", width="stretch", icon=":material/auto_awesome:")
        st.caption(t("reco.keep_note"))
    progress_slot = st.empty()
    if go:
        if base.empty:
            progress_slot.info(t("reco.empty"))
        else:
            generate(mode, n, boldness, progress_slot)

saved = saved_for(mode)
mode_name = t(f"reco.engine_{mode}")

if not saved:
    with theme.panel("mist", "reco-empty"):
        st.html(f"<div class='rs-empty'>{studio.mode_art(mode)}<b>{escape(t('reco.empty_title', mode=mode_name))}</b>"
                f"<span>{escape(t('reco.empty_hint'))}</span></div>")
    st.stop()

recs, meta = saved["df"], saved["meta"]
meta_line = t("reco.meta", n=fmt_int(len(recs)), ago=ago(meta["at"]), period=meta.get("period", "–"),
              boldness=t(f"reco.bold_{meta.get('boldness', 'balanced')}").lower())

# --- the map of sound ---------------------------------------------------------------------------------
theme.section(t("reco.map_section"), t(f"reco.map_note_{'paths' if mode == 'subgenres' else 'seeds'}", mode=mode_name))


@st.cache_data(ttl=600, show_spinner=False)
def _atlas(n_plays: int, n_library: int, n_tags: int) -> tuple[dict, int]:
    """Every artist of your music on the atlas of genres (see core/atlas.py); computed again
    whenever plays, library or genre information grow."""
    raw, lib = data.raw_data(), data.library()
    points, missing = atlas.place(raw.artists, everything, raw.tags, raw.albums, lib.playlist_tracks, lib.favorites)
    return atlas.columns(points), missing


lib_size = len(data.library().playlist_tracks)
artists, missing = _atlas(len(everything), lib_size, len(data.raw_data().tags))
points = []
for r in recs.itertuples(index=False):
    spot = atlas.anchor(r.subgenre if isinstance(r.subgenre, str) else None, r.anchor_x, r.anchor_y)
    if spot:
        points.append({"title": r.title, "artist": r.artist_name, "img": r.cover, "track_id": int(r.track_id),
                       "reason": r.reason, "subgenre": r.subgenre if isinstance(r.subgenre, str) else "",
                       "x": spot[0], "y": spot[1]})
paths = sorted({(r.reason.split(" → ")[0], r.subgenre) for r in recs.itertuples(index=False)
                if mode == "subgenres" and r.frontier and " → " in str(r.reason)})
with theme.panel("ocean", "reco-map"):
    theme.head(t("reco.map_title_mode", mode=mode_name), meta_line)
    interactive.sound_map(
        artists, points, paths,
        {"density": t("reco.map_density"), "artists": t("reco.map_artists"), "found": t("reco.map_found", mode=mode_name),
         "zones": t("reco.map_zones"), "search": t("reco.map_search"), "fit": t("reco.map_fit"), "whole": t("reco.map_whole"),
         "hint": t("reco.map_hint"), "play": t("reco.play"), "pause": t("reco.pause"), "no_preview": t("reco.no_preview"),
         "because": t(f"reco.because_{mode}"), "count": t("reco.map_count"), "plays": t("reco.map_plays"),
         "minutes": t("reco.map_minutes"), "lists": t("reco.map_lists"), "favs": t("reco.map_favs"), "open": t("reco.map_open"),
         "lv0": t("reco.map_lv0"), "lv1": t("reco.map_lv1"), "lv2": t("reco.map_lv2"), "zone": t("reco.map_zone"),
         "zoom_in": t("reco.map_zoom_in"), "genre": t("common.genre"), "artist": t("common.artist"),
         "label": t("reco.map_label"), "words": t("reco.map_words")},
        studio.MODE_COLORS[mode][0], get_lang(), height=820)
    st.caption(t("reco.map_credit", n=fmt_int(len(artists["id"])), missing=fmt_int(missing)))

# --- the table ----------------------------------------------------------------------------------------
theme.section(t("reco.table_section"), t("reco.table_note"))
genre_colors = {}
for name in recs["subgenre"].dropna().unique():
    g = soundmap.by_name(name)
    if g:
        genre_colors[name] = g.color
with theme.white("reco-table"):
    table = recs.assign(genre=recs["subgenre"].fillna(recs["genre"]))
    interactive.rec_table(table, {"title": t("common.track"), "artist": t("common.artist"), "album": t("common.album"),
                                  "why": t("reco.why"), "genre": t("reco.subgenre"), "time": t("reco.length"),
                                  "search": t("reco.table_search"), "count": t("reco.table_count"),
                                  "because": t(f"reco.because_{mode}"), "open": "Deezer", "no_preview": t("reco.no_preview"),
                                  "play": t("reco.play")},
                          studio.MODE_COLORS[mode][0], genre_colors)
    export = pd.DataFrame({
        "#": range(1, len(recs) + 1), t("common.track"): recs["title"], t("common.artist"): recs["artist_name"],
        t("common.album"): recs["album_title"], t("reco.subgenre"): table["genre"], t("reco.why"): recs["reason"],
        "Deezer": recs["link"],
    })
    ui.excel_download(export, f"decouvertes_{mode}.xlsx", mode_name, f"{t('rail.foryou')} — {mode_name}", key="reco_xl",
                      formats={"#": "int"})
st.caption(t("reco.footnote"))
