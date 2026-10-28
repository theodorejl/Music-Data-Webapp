"""For you: three recommendation engines (neighbours, genres, moment), their picks on the map
of your genres next to the artists they come from, and every track playable for 30 s."""

from html import escape

import pandas as pd
import streamlit as st

from app.components import charts, data, interactive, theme, ui
from app.i18n import fmt_int, t
from core import recommend

f = data.get_filters()
window = data.filtered_plays()
everything = data.all_plays()

if "reco_nonce" not in st.session_state:
    st.session_state["reco_nonce"] = 0


def controls() -> None:
    data.period_control()
    if st.button(t("reco.refresh"), icon=":material/autorenew:", key="reco_refresh", type="secondary"):
        st.session_state["reco_nonce"] += 1
        data.recommendations.clear()
        st.rerun()


if window.empty:
    theme.hero("ocean", t("rail.foryou"), escape(t("reco.empty")), f.label, controls=controls)
    st.stop()

hour = pd.Timestamp.now(tz=data.timezone_name()).hour
profile = recommend.build_profile(window, everything, hour)
key = (tuple(s.artist_id for s in profile.seeds), tuple(g for g, _ in profile.genres), profile.moment,
       tuple(s.artist_id for s in profile.moment_seeds), len(everything), st.session_state["reco_nonce"])
with st.spinner(t("reco.loading")):
    recs = data.recommendations(key, profile)

moment_name = t(f"moments.{profile.moment}").lower()
if recs.empty:
    theme.hero("ocean", t("rail.foryou"), escape(t("reco.unavailable")), f.label, controls=controls)
    st.stop()

lead = t("reco.lead", n=f"<b>{fmt_int(len(recs))}</b>",
         artists=", ".join(f"<b>{escape(s.name)}</b>" for s in profile.seeds[:3]),
         genres=", ".join(escape(g) for g, _ in profile.genres[:2]) or "–", moment=escape(moment_name))
theme.hero("ocean", t("rail.foryou"), lead, t("reco.kicker"), controls=controls,
           art=ui.art_fan(recs.drop_duplicates("cover")["cover_big"].fillna(recs["cover"]).tolist()))

by_engine = {e: recs[recs["engine"] == e] for e in recommend.ENGINES}
ui.stat_tiles([
    (t("reco.engine_neighbours"), fmt_int(len(by_engine["neighbours"])), t("reco.tile_neighbours", n=fmt_int(len(profile.seeds))), "coral", None),
    (t("reco.engine_genres"), fmt_int(len(by_engine["genres"])),
     ", ".join(g for g, _ in profile.genres[:3]) or "–", "sky", None),
    (t("reco.engine_moment"), fmt_int(len(by_engine["moment"])), t("reco.tile_moment", moment=moment_name), "lilac", None),
])

# --- the map -------------------------------------------------------------------------------------
theme.section(t("reco.map_section"), t("reco.map_note"))
seeds = {s.artist_id: s for s in profile.seeds + profile.moment_seeds}
names = [g for g, _ in profile.genres] + [r for r in recs["genre"].dropna().unique() if r not in {g for g, _ in profile.genres}]
names = names[:6]
other = t("common.other")
needs_other = any(s.genre not in names for s in seeds.values()) or recs["genre"].isna().any() or (~recs["genre"].isin(names)).any()
colors = charts.category_colors(names)
genres = [(g, colors[g]) for g in names] + ([(other, "#c4c9d0")] if needs_other else [])
map_labels = {"you": t("reco.map_you"), "neighbours": t("reco.engine_neighbours"), "genres": t("reco.engine_genres"),
              "moment": t("reco.engine_moment"), "hint": t("reco.map_hint"), "play": t("reco.play"), "pause": t("reco.pause"),
              "no_preview": t("reco.no_preview"), "loading": t("reco.loading_short"),
              "because": {e: t(f"reco.because_{e}") for e in recommend.ENGINES}}
with theme.panel("night", "map"):
    theme.head(t("reco.map_title"), t("reco.map_meta", n=fmt_int(len(recs)), seeds=fmt_int(len(seeds))))
    interactive.rec_map(
        [{"id": s.artist_id, "name": s.name, "genre": s.genre if s.genre in names else other, "minutes": s.minutes,
          "img": s.picture} for s in seeds.values()],
        [{"track_id": r.track_id, "title": r.title, "artist": r.artist_name, "engine": r.engine,
          "genre": r.genre if r.genre in names else other, "seed": r.seed_artist_id, "img": r.cover, "reason": r.reason}
         for r in recs.itertuples(index=False)],
        genres, map_labels, height=660)

# --- one panel per engine ---------------------------------------------------------------------------
card_labels = {"open": t("reco.open"), "no_preview": t("reco.no_preview")}
for engine, family in (("neighbours", "coral"), ("genres", "sky"), ("moment", "lilac")):
    picks = by_engine[engine]
    theme.gap()
    with theme.panel(family, f"engine-{engine}"):
        theme.head(t(f"reco.engine_{engine}"), t("reco.n_tracks", n=fmt_int(len(picks))),
                   t(f"reco.how_{engine}", moment=moment_name))
        if picks.empty:
            ui.empty_state(t("reco.none"))
        else:
            interactive.rec_cards(picks, {**card_labels, "because": t(f"reco.because_{engine}")},
                                  interactive.ENGINE_COLORS[engine], columns=3)
st.caption(t("reco.footnote"))
