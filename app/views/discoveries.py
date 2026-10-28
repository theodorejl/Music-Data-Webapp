"""Discoveries: artists, albums and tracks played for the first time in the period, how much
of the listening went to them, and how the collection grows month after month."""

from html import escape

import streamlit as st

from app.components import charts, data, theme, ui
from app.i18n import fmt_datetime_short, fmt_duration, fmt_int, fmt_pct, t
from core import stats

f = data.get_filters()

# "New" means first play ever, so first plays are computed on the whole history,
# then restricted to the selected period.
everything = stats.filter_frame(data.all_plays(), min_seconds=f.min_seconds)
if everything.empty:
    theme.hero("rose", t("rail.discoveries"), escape(t("common.no_data")), f.label, controls=data.period_control)
    st.stop()

firsts = {dim: stats.first_listens(everything, dim) for dim in ("artist", "album", "track")}


def in_period(frame):
    out = frame
    if f.start is not None:
        out = out[out["first_played"] >= f.start]
    if f.end is not None:
        out = out[out["first_played"] < f.end]
    return out


new = {dim: in_period(frame) for dim, frame in firsts.items()}
df = stats.filter_frame(everything, f.start, f.end)
new_ids = set(new["artist"]["key"])
fresh_minutes = float(df[df["artist_id"].isin(new_ids)]["minutes"].sum()) if not df.empty else 0.0
total_minutes = float(df["minutes"].sum()) if not df.empty else 0.0
star = new["artist"].sort_values("plays", ascending=False).head(1)

lead = t("discoveries.hero_lead", artists=f"<b>{fmt_int(len(new['artist']))}</b>", albums=f"<b>{fmt_int(len(new['album']))}</b>",
         share=f"<b>{fmt_pct(fresh_minutes / total_minutes) if total_minutes else '–'}</b>")
if not star.empty:
    lead += " " + t("discoveries.hero_star", artist=f"<b>{escape(str(star.iloc[0]['label']))}</b>",
                    plays=fmt_int(int(star.iloc[0]["plays"])))
faces = new["artist"].sort_values("plays", ascending=False)["image"].tolist()
theme.hero("rose", t("rail.discoveries"), lead, f.label, controls=data.period_control, art=ui.art_faces(faces))

ui.stat_tiles([
    (t("discoveries.new_artists"), fmt_int(len(new["artist"])), t("discoveries.since_note"), "rose", None),
    (t("discoveries.new_albums"), fmt_int(len(new["album"])), None, "sky", None),
    (t("discoveries.new_tracks"), fmt_int(len(new["track"])), None, "lime", None),
    (t("discoveries.fresh_share"), fmt_pct(fresh_minutes / total_minutes) if total_minutes else "–",
     t("discoveries.fresh_share_cap", time=fmt_duration(fresh_minutes)), "butter", None),
])

theme.section(t("discoveries.swarm_section"), t("discoveries.swarm_note"))
with theme.panel("lilac", "swarm"):
    swarm = new["artist"] if len(new["artist"]) >= 3 else firsts["artist"]
    genre_of = data.artist_genres()
    swarm = swarm.assign(genre=[genre_of.get(int(k)) for k in swarm["key"]])
    theme.head(t("discoveries.swarm_title"), f.label if swarm is not firsts["artist"] else t("period.all"))
    other = t("common.other")
    charts.show(charts.beeswarm(swarm, t("common.plays_short"), height=380, other_label=other), key="disc_swarm")
    shown = swarm["genre"].fillna(other).value_counts().index.tolist()[:7]
    cmap = charts.category_colors(shown, other)
    ui.legend([(g, cmap[g]) for g in shown])

theme.gap()
per_month = stats.discoveries_per_month(everything)
left, right = st.columns([1, 1], gap="medium")
with left:
    with theme.panel("teal", "growth"):
        theme.head(t("discoveries.growth_title"), t("period.all"), t("discoveries.growth_note"))
        charts.show(charts.cumulative_lines(per_month, [("new_artists", t("common.artists"), "teal"),
                                                        ("new_albums", t("common.albums"), "sky")], height=330), key="disc_growth")
with right:
    with theme.panel("coral", "split"):
        theme.head(t("discoveries.split_title"), f.label, t("discoveries.split_note"))
        known = max(0.0, total_minutes - fresh_minutes)
        parts = [(t("discoveries.fresh"), fresh_minutes), (t("discoveries.known"), known)]
        ui.waffle(parts, {t("discoveries.fresh"): "#e8558e", t("discoveries.known"): "#1e9fd8"})
        theme.gap()
        charts.show(charts.grouped_bars(per_month.tail(12), "period", [("new_artists", t("common.artists")),
                                                                      ("new_albums", t("common.albums"))], height=240),
                    key="disc_month")

theme.section(t("discoveries.lists_title"))
with theme.white("lists"):
    tab_ar, tab_al = st.tabs([t("discoveries.new_artists"), t("discoveries.new_albums")])
    for tab, dim in ((tab_ar, "artist"), (tab_al, "album")):
        with tab:
            frame = data.scope_frame(firsts[dim], f"disc_{dim}", "first_played")
            if frame.empty:
                ui.empty_state(t("discoveries.none"))
                continue
            event = st.dataframe(
                {
                    "": frame["image"].tolist(),
                    t("common.name"): frame["label"].tolist(),
                    **({t("common.artist"): frame["sublabel"].tolist()} if dim == "album" else {}),
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
