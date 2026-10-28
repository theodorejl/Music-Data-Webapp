"""Discoveries: artists, albums and tracks played for the first time, shown as their covers on a
timeline, how much of the listening went to them, and how the collection grows."""

from html import escape

import streamlit as st

from app.components import charts, data, theme, ui
from app.i18n import fmt_datetime_short, fmt_duration, fmt_int, fmt_pct, t
from core import stats

f = data.get_filters()

# "New" means first play ever, so first plays are computed on the whole history,
# then restricted to the chosen period.
everything = stats.filter_frame(data.all_plays(), min_seconds=f.min_seconds)
if everything.empty:
    theme.hero("rose", t("rail.discoveries"), escape(t("common.no_data")), f.label, controls=data.period_control)
    st.stop()

firsts = {dim: stats.first_listens(everything, dim) for dim in ("artist", "album", "track")}
KEY = {"artist": "artist_id", "album": "album_id", "track": "track_id"}


def in_range(frame, start, end):
    out = frame
    if start is not None:
        out = out[out["first_played"] >= start]
    if end is not None:
        out = out[out["first_played"] < end]
    return out


def fresh_minutes(dim: str, start, end) -> tuple[float, float]:
    """Minutes spent in the range on things discovered in that range, and all minutes."""
    plays = stats.filter_frame(everything, start, end)
    new_keys = set(in_range(firsts[dim], start, end)["key"])
    return float(plays[plays[KEY[dim]].isin(new_keys)]["minutes"].sum()), float(plays["minutes"].sum())


new = {dim: in_range(frame, f.start, f.end) for dim, frame in firsts.items()}
fresh, total = fresh_minutes("artist", f.start, f.end)
star = new["artist"].sort_values("plays", ascending=False).head(1)
lead = t("discoveries.hero_lead", artists=f"<b>{fmt_int(len(new['artist']))}</b>", albums=f"<b>{fmt_int(len(new['album']))}</b>",
         share=f"<b>{fmt_pct(fresh / total) if total else '–'}</b>")
if not star.empty:
    lead += " " + t("discoveries.hero_star", artist=f"<b>{escape(str(star.iloc[0]['label']))}</b>",
                    plays=fmt_int(int(star.iloc[0]["plays"])))
faces = new["artist"].sort_values("plays", ascending=False)["image"].tolist()
theme.hero("rose", t("rail.discoveries"), lead, f.label, controls=data.period_control, art=ui.art_faces(faces))

ui.stat_tiles([
    (t("discoveries.new_artists"), fmt_int(len(new["artist"])), t("discoveries.since_note"), "rose", None),
    (t("discoveries.new_albums"), fmt_int(len(new["album"])), None, "sky", None),
    (t("discoveries.new_tracks"), fmt_int(len(new["track"])), None, "lime", None),
    (t("discoveries.fresh_share"), fmt_pct(fresh / total) if total else "–",
     t("discoveries.fresh_share_cap", time=fmt_duration(fresh)), "butter", None),
])

theme.section(t("discoveries.swarm_section"), t("discoveries.timeline_note"))
with theme.panel("lilac", "timeline"):
    slot = st.container()
    sc = data.scope_bar("disc_tl", ["artist", "album", "track"])
    with slot:
        found = in_range(firsts[sc.dim], sc.start, sc.end)
        theme.head(t("discoveries.timeline_title", n=fmt_int(len(found)), what=t(f"scope.{sc.dim}").lower()), sc.label)
        if found.empty:
            ui.empty_state(t("discoveries.none"))
        else:
            ui.cover_timeline(found, "first_played", lambda r: t("discoveries.plays_since_n", n=fmt_int(r.plays)),
                              per_col=6, round_art=sc.dim == "artist")

theme.gap()
left, right = st.columns([1, 1], gap="medium")
with left:
    with theme.panel("teal", "growth"):
        theme.head(t("discoveries.growth_title"), t("period.all"), t("discoveries.growth_note"))
        per_month = stats.discoveries_per_month(everything)
        charts.show(charts.cumulative_lines(per_month, [("new_artists", t("common.artists"), "teal"),
                                                        ("new_albums", t("common.albums"), "sky")], height=340), key="disc_growth")
with right:
    with theme.panel("coral", "split"):
        slot = st.container()
        sc = data.scope_bar("disc_split", ["artist", "album", "track"])
        with slot:
            new_min, all_min = fresh_minutes(sc.dim, sc.start, sc.end)
            theme.head(t("discoveries.split_title"), sc.label, t("discoveries.split_note"))
            parts = [(t("discoveries.fresh"), new_min), (t("discoveries.known"), max(0.0, all_min - new_min))]
            ui.waffle(parts, {t("discoveries.fresh"): "#e8558e", t("discoveries.known"): "#1e9fd8"})
            stars = in_range(firsts[sc.dim], sc.start, sc.end).sort_values("plays", ascending=False).head(4)
            if not stars.empty:
                theme.gap()
                ui.rank_list(stars, lambda r: t("discoveries.plays_since_n", n=fmt_int(r.plays)), "plays",
                             colors=["#e8558e", "#ff6f4d", "#8b6cf0", "#1e9fd8"], round_art=sc.dim == "artist", limit=4)

theme.section(t("discoveries.lists_title"))
with theme.white("lists"):
    tab_ar, tab_al, tab_tr = st.tabs([t("discoveries.new_artists"), t("discoveries.new_albums"), t("discoveries.new_tracks")])
    for tab, dim in ((tab_ar, "artist"), (tab_al, "album"), (tab_tr, "track")):
        with tab:
            frame = data.scope_frame(firsts[dim], f"disc_{dim}", "first_played")
            if frame.empty:
                ui.empty_state(t("discoveries.none"))
                continue
            event = st.dataframe(
                {
                    "": frame["image"].tolist(),
                    t("common.name"): frame["label"].tolist(),
                    **({t("common.artist"): frame["sublabel"].tolist()} if dim != "artist" else {}),
                    t("discoveries.first_play"): [fmt_datetime_short(x) for x in frame["first_played"]],
                    t("discoveries.plays_since"): frame["plays"].tolist(),
                },
                hide_index=True, key=f"disc_{dim}", on_select="rerun", selection_mode="single-row",
                column_config={"": st.column_config.ImageColumn("", width="small"),
                               t("discoveries.plays_since"): st.column_config.ProgressColumn(
                                   t("discoveries.plays_since"), format="%d", min_value=0,
                                   max_value=int(frame["plays"].max() or 1), color="#e8558e")},
            )
            if event.selection.rows:
                ui.open_detail(dim, frame.iloc[event.selection.rows[0]]["key"])
            st.caption(t("common.click_row"))
