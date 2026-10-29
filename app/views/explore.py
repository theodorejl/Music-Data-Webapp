"""Universe: the atlas of your albums or artists (the map of sound of « Pour toi », without the
discoveries), then the generative pieces — time spiral, cover orbit, listening fingerprint — each
in its own colour panel."""

import math
from html import escape

import streamlit as st

from app.components import data, interactive, theme, ui, viz
from app.i18n import fmt_int, get_lang, t, tl
from core import atlas, stats

f = data.get_filters()
df = data.filtered_plays()

if df.empty:
    theme.hero("lilac", t("rail.explore"), escape(t("common.no_data")), f.label, controls=data.period_control)
    st.stop()

k = stats.kpis(df)
lead = t("explore.hero_lead", plays=f"<b>{fmt_int(k['plays'])}</b>", artists=f"<b>{fmt_int(k['artists'])}</b>",
         genres=f"<b>{fmt_int(df['genre'].nunique())}</b>")
theme.hero("lilac", t("rail.explore"), lead, f.label, controls=data.period_control,
           art=viz.fingerprint_svg(df, "", "", size=520, framed=False))

@st.cache_data(ttl=600, show_spinner=False)
def _atlas_points(kind: str, n_plays: int, n_library: int, n_tags: int) -> list[dict]:
    """Every favourite or listened album (or every artist of your music) on the atlas of genres."""
    raw, lib = data.raw_data(), data.library()
    args = (raw.artists, data.all_plays(), raw.tags, raw.albums, lib.playlist_tracks, lib.favorites)
    return atlas.place_albums(*args) if kind == "album" else atlas.place(*args)[0]


with theme.panel("lilac", "atlas"):
    # the controls sit above the map: it fills the screen, so nobody would scroll past it to find them
    head = st.container()
    sc = data.scope_bar("ex_atlas", ["album", "artist"])
    pct = st.slider(t("explore.atlas_top"), 1, 100, 100, step=1, format="%d %%", key="ex_atlas_pct")
    with head:
        theme.head(t("explore.atlas_title"), sc.label, t("explore.atlas_help"))
    albums = sc.dim == "album"
    points = _atlas_points(sc.dim, len(data.all_plays()), len(data.library().playlist_tracks), len(data.raw_data().tags))
    key = "album_id" if albums else "artist_id"
    played = sc.df.dropna(subset=[key])
    minutes = {int(k): float(v) for k, v in played.groupby(key)["minutes"].sum().items()}
    plays = {int(k): int(v) for k, v in played.groupby(key)["play_id"].count().items()}
    everything = sc.start is None and sc.end is None  # « all the history »: the never-played ones too
    keep = set(atlas.top_share([p["id"] for p in points], minutes, pct, everything))
    shown = []
    for p in points:
        if p["id"] in keep:
            mn, fav = minutes.get(p["id"], 0.0), p.get("fa", 0)
            shown.append({**p, "mn": round(mn), "pl": plays.get(p["id"], 0),
                          "w": round(1.3 * math.log1p(mn) + .45 * math.log1p(p.get("lt", 0)) + .9 * min(1, fav) + .3, 3)})
    what = t("explore.atlas_albums" if albums else "explore.atlas_artists")
    if not shown:
        ui.empty_state()
    else:
        interactive.sound_map(
            atlas.columns(shown), [], [],
            {"density": t("explore.atlas_density"), "artists": what, "search": t("reco.map_search"), "fit": t("explore.atlas_fit"),
             "whole": t("reco.map_whole"), "hint": t("explore.atlas_hint"), "play": "", "pause": "", "no_preview": "",
             "because": "", "count": t("reco.map_count"), "plays": t("reco.map_plays"), "minutes": t("reco.map_minutes"),
             "lists": t("reco.map_lists"), "favs": t("reco.map_favs"), "open": t("reco.map_open"), "lv0": t("reco.map_lv0"),
             "lv1": t("reco.map_lv1"), "lv2": t("reco.map_lv2"), "zone": "", "zoom_in": t("reco.map_zoom_in"),
             "genre": t("common.genre"), "artist": t("common.album" if albums else "common.artist"),
             "label": t("reco.map_label"), "words": t("reco.map_words"), "fav": t("explore.atlas_fav"),
             "found": "", "zones": ""},
            theme.mid("lilac"), get_lang(), height=820, family="lilac", kind="albums" if albums else "artists")
        one = len(shown) == 1
    noun = t(f"common.{sc.dim}" if one else f"scope.{sc.dim}").lower()
    shown_txt = t("explore.atlas_shown_one" if one else "explore.atlas_shown", n=fmt_int(len(shown)), what=noun)
    st.caption(t("explore.atlas_count", shown=shown_txt, total=fmt_int(len(points))))

theme.gap()
left, right = st.columns([1, 1], gap="medium")
with left:
    with theme.panel("sky", "spiral"):
        slot = st.container()
        sc = data.scope_bar("ex_spiral")
        with slot:
            theme.head(t("explore.spiral_title"), sc.label, t("explore.spiral_help"))
            if sc.df.empty:
                ui.empty_state()
            else:
                viz.listening_spiral(sc.df.head(6000), {
                    "other": t("common.other"), "turn_day": t("explore.turn_day"), "turn_week": t("explore.turn_week"),
                    "hours": tl("explore.hours"), "days": tl("weekdays_short"), "minutes": t("explore.dot_size"),
                })
with right:
    with theme.panel("butter", "orbit"):
        slot = st.container()
        sc = data.scope_bar("ex_orbit", ["album", "artist", "track"])
        with slot:
            theme.head(t("explore.orbit_title_of", what=t(f"scope.{sc.dim}").lower()), sc.label, t("explore.orbit_help"))
            if sc.df.empty:
                ui.empty_state()
            else:
                viz.cover_orbit(stats.top(sc.df, sc.dim, "plays", 64), t("common.plays_short"))

theme.gap()
with theme.panel("rose", "fingerprint"):
    slot = st.container()
    sc = data.scope_bar("ex_print")
    with slot:
        theme.head(t("explore.fingerprint_title"), sc.label, t("explore.fingerprint_help"))
        if sc.df.empty:
            ui.empty_state()
        else:
            svg = viz.fingerprint_svg(sc.df, t("explore.fingerprint_title"), sc.label)
            left, right = st.columns([1.4, 1], gap="large", vertical_alignment="center")
            with left:
                theme.html(svg)
            with right:
                st.html(f"<p class='ds-hero-lead'>{escape(t('explore.fingerprint_story'))}</p>")
                st.download_button(t("explore.download_svg"), svg.encode("utf-8"), file_name="empreinte_sonore.svg",
                                   mime="image/svg+xml", icon=":material/download:", key="fp_dl", type="primary")
ui.estimated_note(df)
