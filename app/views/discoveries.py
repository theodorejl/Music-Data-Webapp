import streamlit as st

from app.components import charts, data, theme, ui
from app.i18n import fmt_datetime_short, fmt_int, t
from core import stats

f = data.get_filters()
ui.header(t("discoveries.title"), f.label, lead=t("discoveries.lead"), dot="rose")

# "New" means first play ever, so first plays are computed on the whole history
# (with the minimum-duration filter), then restricted to the selected period.
everything = stats.filter_frame(data.all_plays(), min_seconds=f.min_seconds)
if everything.empty:
    ui.empty_state()
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
ui.kpi_row([
    (t("discoveries.new_artists"), fmt_int(len(new["artist"])), None),
    (t("discoveries.new_albums"), fmt_int(len(new["album"])), None),
    (t("discoveries.new_tracks"), fmt_int(len(new["track"])), None),
])
st.caption(t("discoveries.since_note"))

theme.section(t("discoveries.per_month"))
per_month = stats.discoveries_per_month(everything)
charts.show(charts.grouped_bars(per_month, "period", [("new_artists", t("common.artists")),
                                                      ("new_albums", t("common.albums"))]), key="disc_month")

tab_ar, tab_al = st.tabs([t("discoveries.new_artists"), t("discoveries.new_albums")])
for tab, dim in ((tab_ar, "artist"), (tab_al, "album")):
    with tab:
        frame = new[dim]
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
            column_config={"": st.column_config.ImageColumn("", width="small")},
        )
        if event.selection.rows:
            ui.open_detail(dim, frame.iloc[event.selection.rows[0]]["key"])
        st.caption(t("common.click_row"))
