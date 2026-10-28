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
# --- the podium and what follows -----------------------------------------------------------------
theme.section(t("tops.podium_section"), t("tops.artists_note"))
with theme.panel("butter", "podium"):
    slot = st.container()
    sc = data.scope_bar("tops_pod", ["artist", "album", "track", "genre"])
    with slot:
        items = ui.ranking(sc.df, sc.dim, metric, 12)
        if items.empty:
            ui.empty_state()
        else:
            round_art = sc.dim == "artist"
            left, right = st.columns([1.1, 1], gap="large")
            with left:
                theme.head(t("tops.podium_of", what=t(f"scope.{sc.dim}").lower()), sc.label)
                ui.podium(items, fmt, None if sc.dim == "genre" else sc.dim, key=f"pod_{sc.dim}", round_art=round_art)
            with right:
                theme.head(t("tops.next"), t(f"tops.by_{metric}"))
                rest = items.iloc[3:12]
                ui.rank_list(rest, fmt, metric, colors=ui.item_colors(rest, sc.dim, sc.df), round_art=round_art, limit=9, start=4,
                             scale_max=float(items[metric].max()))

# --- mosaic -----------------------------------------------------------------------------------
theme.section(t("tops.mosaic_section"), t("tops.albums_note"))
with theme.panel("sky", "mosaic"):
    slot = st.container()
    sc = data.scope_bar("tops_mosaic", ["album", "artist", "track"])
    with slot:
        theme.head(t("home.mosaic_title", what=t(f"scope.{sc.dim}").lower()), sc.label)
        ui.mosaic(stats.top(sc.df, sc.dim, metric, 24), metric, fmt, ratio=2.4, limit=24)

# --- two columns of a ranking ---------------------------------------------------------------------
theme.section(t("tops.list_section"))
with theme.panel("lilac", "tracks"):
    slot = st.container()
    sc = data.scope_bar("tops_list", ["track", "album", "artist", "genre"])
    with slot:
        theme.head(t("tops.list_title", what=t(f"scope.{sc.dim}").lower()), sc.label)
        items = ui.ranking(sc.df, sc.dim, metric, 12)
        if items.empty:
            ui.empty_state()
        else:
            colors = ui.item_colors(items, sc.dim, sc.df)
            top_value = float(items[metric].max())
            a, b = st.columns(2, gap="large")
            with a:
                ui.rank_list(items.iloc[:6], fmt, metric, colors=colors[:6], limit=6, round_art=sc.dim == "artist")
            with b:
                ui.rank_list(items.iloc[6:12], fmt, metric, colors=colors[6:12], limit=6, start=7,
                             round_art=sc.dim == "artist", scale_max=top_value)

# --- genres -----------------------------------------------------------------------------------
theme.section(t("common.genres"), t("tops.genres_note"))
left, right = st.columns([1.25, 1], gap="medium")
with left:
    with theme.panel("teal", "sunburst"):
        slot = st.container()
        sc = data.scope_bar("tops_sun")
        with slot:
            theme.head(t("tops.sunburst_title"), sc.label, t("tops.sunburst_meta"))
            with_genre = sc.df.dropna(subset=["genre"])
            if with_genre.empty:
                ui.empty_state(t("tops.no_genre"))
            else:
                ga = with_genre.groupby(["genre", "artist_name"])["minutes"].sum().reset_index()
                keep = ga.sort_values("minutes", ascending=False).groupby("genre").head(8)
                top_genres = with_genre.groupby("genre")["minutes"].sum().nlargest(7).index
                keep = keep[keep["genre"].isin(top_genres)].rename(columns={"artist_name": "artist"})
                charts.show(charts.sunburst(keep, height=470), key="tops_sun")
with right:
    with theme.panel("rose", "genres"):
        slot = st.container()
        sc = data.scope_bar("tops_genres")
        with slot:
            theme.head(t("tops.genre_bars"), sc.label, t("tops.genre_covers_note"))
            g = ui.ranking(sc.df, "genre", metric, 8)
            if g.empty:
                ui.empty_state(t("tops.no_genre"))
            else:
                ui.rank_list(g, fmt, metric, colors=ui.item_colors(g, "genre", sc.df), limit=8)
                unknown = int(sc.df["genre"].isna().sum())
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
