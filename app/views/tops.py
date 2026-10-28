"""Charts (tops): the podium, the leaders with their genre colour, albums as a mosaic of covers,
tracks, the genre → artist rings, then full sortable tables with exports."""

from html import escape

import pandas as pd
import streamlit as st

from app.components import charts, data, theme, ui
from app.i18n import fmt_duration, fmt_int, t
from core import stats

f = data.get_filters()
df = data.filtered_plays()

if df.empty:
    theme.hero("coral", t("rail.tops"), escape(t("common.no_data")), f.label, controls=data.period_control)
    st.stop()

metric = st.session_state.get("tops_metric", "plays")
fmt = ui.value_formatter(metric)
artists = stats.top(df, "artist", metric, 12)
albums = stats.top(df, "album", metric, 24)
tracks = stats.top(df, "track", metric, 12)
first = artists.iloc[0]
lead = t("tops.hero_lead", artist=f"<b>{escape(str(first['label']))}</b>", value=f"<b>{escape(fmt(first))}</b>",
         album=f"<b>{escape(str(albums.iloc[0]['label']))}</b>" if not albums.empty else "–",
         track=f"<b>{escape(str(tracks.iloc[0]['label']))}</b>" if not tracks.empty else "–")


def controls() -> None:
    data.period_control()
    st.segmented_control(t("tops.metric"), ["plays", "minutes"], default="plays", required=True,
                         format_func=lambda m: t(f"tops.by_{m}"), key="tops_metric", label_visibility="collapsed")


theme.hero("coral", t("rail.tops"), lead, f.label, controls=controls, art=ui.art_fan(albums["image"].tolist()))

genre_of = data.artist_genres()


def genre_colors(keys) -> list[str]:
    genres = [genre_of.get(int(k)) for k in keys]
    cmap = charts.category_colors([g for g in genres if g])
    return [cmap.get(g, charts.OTHER) for g in genres]


# --- artists ----------------------------------------------------------------------------------
theme.section(t("common.artists"), t("tops.artists_note"))
left, right = st.columns([1.1, 1], gap="medium")
with left:
    with theme.panel("butter", "podium"):
        theme.head(t("tops.podium"), f.label)
        ui.podium(artists, fmt, "artist", key="pod_ar", round_art=True)
with right:
    with theme.panel("coral", "artists"):
        theme.head(t("tops.next"), t(f"tops.by_{metric}"))
        rest = artists.iloc[3:12]
        ui.rank_list(rest, fmt, metric, colors=genre_colors(rest["key"]), round_art=True, limit=9, start=4)

# --- albums -----------------------------------------------------------------------------------
theme.section(t("common.albums"), t("tops.albums_note"))
with theme.panel("sky", "mosaic"):
    theme.head(t("tops.mosaic_title"), f.label)
    ui.mosaic(albums, metric, fmt, ratio=2.4, limit=24)

# --- tracks -----------------------------------------------------------------------------------
theme.section(t("common.tracks"))
with theme.panel("lilac", "tracks"):
    theme.head(t("tops.tracks_title"), t(f"tops.by_{metric}"))
    a, b = st.columns(2, gap="large")
    track_colors = [theme.PALETTE[(i + 2) % len(theme.PALETTE)] for i in range(12)]
    with a:
        ui.rank_list(tracks.iloc[:6], fmt, metric, colors=track_colors[:6], limit=6)
    with b:
        ui.rank_list(tracks.iloc[6:12], fmt, metric, colors=track_colors[6:12], limit=6, start=7)

# --- genres -----------------------------------------------------------------------------------
theme.section(t("common.genres"), t("tops.genres_note"))
with_genre = df.dropna(subset=["genre"])
if with_genre.empty:
    ui.empty_state(t("tops.no_genre"))
else:
    left, right = st.columns([1.25, 1], gap="medium")
    with left:
        with theme.panel("teal", "sunburst"):
            theme.head(t("tops.sunburst_title"), t("tops.sunburst_meta"))
            ga = with_genre.groupby(["genre", "artist_name"])["minutes"].sum().reset_index()
            keep = ga.sort_values("minutes", ascending=False).groupby("genre").head(8)
            top_genres = with_genre.groupby("genre")["minutes"].sum().nlargest(7).index
            keep = keep[keep["genre"].isin(top_genres)].rename(columns={"artist_name": "artist"})
            charts.show(charts.sunburst(keep, height=470), key="tops_sun")
    with right:
        with theme.panel("rose", "genres"):
            theme.head(t("tops.genre_bars"), t(f"tops.by_{metric}"))
            g = stats.top(df, "genre", metric, 10)
            cmap = charts.category_colors(g["label"].tolist())
            values = g["minutes"].round(0) if metric == "minutes" else g["plays"]
            charts.show(charts.hbar(g["label"], values, t(f"common.{metric}").lower(),
                                    colors=[cmap[x] for x in g["label"]]), key="tops_gbar")
            unknown = int(df["genre"].isna().sum())
            if unknown:
                st.caption(t("tops.unknown_genre", n=unknown))

# --- full tables ------------------------------------------------------------------------------
theme.section(t("tops.tables_title"), t("tops.tables_note"))
with theme.white("tables"):
    scoped, period_label = data.scoped_plays("tops")
    n = st.selectbox(t("tops.count"), [20, 50, 100, 0], key="tops_n", width=200,
                     format_func=lambda x: t("tops.count_all") if x == 0 else str(x))
    tabs = st.tabs([t("common.artists"), t("common.albums"), t("common.tracks"), t("common.genres")])
    for tab, dim in zip(tabs, stats.DIMENSIONS):
        with tab:
            items = stats.top(scoped, dim, metric, n or len(scoped))
            if items.empty:
                ui.empty_state(t("tops.no_genre") if dim == "genre" else None)
                continue
            ui.ranked_table(items, None if dim == "genre" else dim, key=f"tl_{dim}_{metric}_{n}")
            export = pd.DataFrame({
                "#": items["rank"], t("common.name"): items["label"],
                **({t("common.artist"): items["sublabel"]} if dim in ("album", "track") else {}),
                t("common.plays"): items["plays"], t("common.minutes"): items["minutes"].round(1),
            })
            tab_name = {"artist": t("common.artists"), "album": t("common.albums"), "track": t("common.tracks"),
                        "genre": t("common.genres")}[dim]
            c_xl, c_csv, _ = st.columns([1, 1, 2])
            with c_xl:
                ui.excel_download(export, f"top_{dim}_{metric}.xlsx", tab_name, f"{t('rail.tops')} — {tab_name} ({period_label})",
                                  key=f"xl_{dim}", formats={"#": "int", t("common.plays"): "int", t("common.minutes"): "dec"})
            with c_csv:
                ui.csv_download(export, f"top_{dim}_{metric}.csv", key=f"dl_{dim}")
    st.caption(t("common.click_row") + " · " + t("tops.total", n=fmt_int(len(scoped)), time=fmt_duration(scoped["minutes"].sum())))
ui.estimated_note(df)
