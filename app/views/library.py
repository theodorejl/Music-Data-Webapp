"""Favorite albums and playlists: analysis, Excel export and A3 album poster."""

import math

import pandas as pd
import streamlit as st

from app.components import charts, data, theme, ui
from app.i18n import fmt_date, fmt_duration, fmt_int, fmt_pct, get_lang, t
from core.poster import best_layout

ui.header(t("library.title"), t("library.kicker"), lead=t("library.subtitle"), dot="mint")

fav = data.favorite_albums()
pls = data.playlists()
if fav.empty and pls.empty:
    ui.empty_state(t("library.empty"))
    st.stop()

tab_albums, tab_playlists, tab_export = st.tabs([t("library.tab_albums"), t("library.tab_playlists"),
                                                 t("library.tab_export")])

SORTS = {
    "added": ("added_at", False), "release": ("release_date", False), "artist": ("artist_name", True),
    "title": ("title", True), "plays": ("plays", False),
}


def sorted_favorites(order: str) -> pd.DataFrame:
    col, asc = SORTS[order]
    return fav.sort_values([col, "title"], ascending=[asc, True], na_position="last").reset_index(drop=True)


def release_text(value) -> str:
    d = pd.to_datetime(value, errors="coerce")
    return fmt_date(d.date()) if pd.notna(d) else "–"


# --- favorite albums -------------------------------------------------------------------

with tab_albums:
    if fav.empty:
        ui.empty_state(t("library.no_albums"))
    else:
        listened = int((fav["plays"] > 0).sum())
        years = fav["release_year"].dropna()
        ui.kpi_row([
            (t("library.fav_albums"), fmt_int(len(fav)), None),
            (t("common.artists"), fmt_int(fav["artist_id"].nunique()), None),
            (t("library.median_year"), str(int(years.median())) if len(years) else "–", None),
            (t("library.listened_share"), fmt_pct(listened / len(fav)), t("library.listened_share_help")),
        ])

        left, right = st.columns(2, gap="large")
        with left:
            theme.section(t("library.by_decade"))
            dec = (years // 10 * 10).astype(int).value_counts().sort_index()
            charts.show(charts.bar_categories([f"{d}s" for d in dec.index], dec.tolist(), t("library.albums")),
                        key="lib_dec")
        with right:
            theme.section(t("library.top_artists"))
            top_art = fav.groupby("artist_name").size().sort_values(ascending=False).head(10)
            charts.show(charts.hbar(top_art.index.tolist(), top_art.tolist(), t("library.albums")), key="lib_art")
        left, right = st.columns(2, gap="large")
        with left:
            theme.section(t("library.genres"))
            g = fav["genre"].dropna().value_counts().head(10)
            if g.empty:
                ui.empty_state(t("tops.no_genre"))
            else:
                charts.show(charts.hbar(g.index.tolist(), g.tolist(), t("library.albums")), key="lib_genre")
        with right:
            theme.section(t("library.added_per_month"))
            added = pd.to_datetime(fav["added_at"], errors="coerce").dropna()
            if added.empty:
                ui.empty_state()
            else:
                per_month = added.dt.to_period("M").dt.to_timestamp().value_counts().sort_index()
                full = pd.date_range(per_month.index.min(), per_month.index.max(), freq="MS")
                per_month = per_month.reindex(full, fill_value=0)
                tl = pd.DataFrame({"period": per_month.index, "albums": per_month.values})
                charts.show(charts.bar_timeline(tl, "albums", "M", t("library.albums"), height=300), key="lib_added")

        theme.section(t("library.all_favorites"))
        c1, c2, c3 = st.columns([2, 2, 2])
        order = c1.selectbox(t("library.sort"), list(SORTS), format_func=lambda s: t(f"library.sort_{s}"),
                             key="lib_sort")
        view = c2.segmented_control(t("tops.view"), ["list", "grid"], default="list", required=True,
                                    format_func=lambda v: t(f"tops.view_{v}"), key="lib_view")
        query = c3.text_input(t("history.search"), key="lib_q", placeholder=t("library.search_placeholder"))
        shown = data.scope_frame(sorted_favorites(order), "lib_fav", "added_at")
        if query.strip():
            q = query.strip().casefold()
            shown = shown[shown["title"].str.casefold().str.contains(q, regex=False)
                          | shown["artist_name"].str.casefold().str.contains(q, regex=False)]
        if view == "list":
            event = st.dataframe(
                pd.DataFrame({
                    "cover": shown["cover_medium"], "title": shown["title"], "artist": shown["artist_name"],
                    "release": [release_text(v) for v in shown["release_date"]],
                    "genre": shown["genre"].fillna("–"),
                    "added": [fmt_date(v.date()) if pd.notna(v) else "–" for v in pd.to_datetime(shown["added_at"])],
                    "plays": shown["plays"],
                }),
                hide_index=True, key="lib_table", on_select="rerun", selection_mode="single-row", height=520,
                column_config={
                    "cover": st.column_config.ImageColumn("", width="small"),
                    "title": st.column_config.TextColumn(t("common.album"), width="medium"),
                    "artist": st.column_config.TextColumn(t("common.artist"), width="medium"),
                    "release": st.column_config.TextColumn(t("library.release")),
                    "genre": st.column_config.TextColumn(t("common.genre")),
                    "added": st.column_config.TextColumn(t("library.added")),
                    "plays": st.column_config.NumberColumn(t("library.plays_history")),
                },
            )
            if event.selection.rows:
                ui.open_detail("album", shown.iloc[event.selection.rows[0]]["album_id"])
            st.caption(t("common.click_row"))
        else:
            per_page = 48
            pages = max(1, math.ceil(len(shown) / per_page))
            page = st.number_input(t("history.page", total=pages), 1, pages, 1, key="lib_grid_page") if pages > 1 else 1
            chunk = shown.iloc[(page - 1) * per_page: page * per_page]
            grid = pd.DataFrame({
                "rank": range((page - 1) * per_page + 1, (page - 1) * per_page + 1 + len(chunk)),
                "key": chunk["album_id"].values, "label": chunk["title"].values,
                "sublabel": chunk["artist_name"].values, "image": chunk["cover_medium"].values,
                "plays": chunk["plays"].values, "minutes": chunk["minutes"].values,
                "release": [release_text(v) for v in chunk["release_date"]],
            })
            ui.cover_grid(grid, "album", lambda row: row.release, columns=8, key="lib_grid")

# --- playlists ---------------------------------------------------------------------------

with tab_playlists:
    if pls.empty:
        ui.empty_state(t("library.no_playlists"))
    else:
        tracks_all = data.playlist_tracks()
        ui.kpi_row([
            (t("library.playlists"), fmt_int(len(pls)), None),
            (t("library.own"), fmt_int(int(pls["is_own"].sum())), None),
            (t("library.favorited"), fmt_int(int((~pls["is_own"].astype(bool)).sum())), None),
            (t("library.unique_tracks"), fmt_int(tracks_all["track_id"].nunique()), None),
        ])
        kind = st.segmented_control(t("library.show"), ["all", "own", "fav"], default="all", required=True,
                                    format_func=lambda k: t(f"library.show_{k}"), key="pl_kind")
        shown = pls if kind == "all" else pls[pls["is_own"].astype(bool) == (kind == "own")]
        shown = data.scope_frame(shown, "pl_list", "added_at")

        left, right = st.columns(2, gap="large")
        with left:
            theme.section(t("library.most_played_playlists"))
            top_pl = shown.sort_values("plays", ascending=False).head(10)
            charts.show(charts.hbar(top_pl["title"].tolist(), top_pl["plays"].tolist(), t("common.plays")),
                        key="pl_top")
        with right:
            theme.section(t("library.artists_in_playlists"))
            in_shown = tracks_all[tracks_all["playlist_id"].isin(shown["id"])]
            arts = in_shown.dropna(subset=["artist_name"]).groupby("artist_name").size()
            arts = arts.sort_values(ascending=False).head(10)
            charts.show(charts.hbar(arts.index.tolist(), arts.tolist(), t("library.tracks")), key="pl_art")

        theme.section(t("library.all_playlists"))
        event = st.dataframe(
            pd.DataFrame({
                "picture": shown["picture"], "title": shown["title"], "creator": shown["creator_name"].fillna("–"),
                "tracks": shown["tracks"], "duration": [fmt_duration((d or 0) / 60) for d in shown["duration"].fillna(0)],
                "played": [fmt_pct(x) for x in shown["played_share"]], "plays": shown["plays"],
            }),
            hide_index=True, key="pl_table", on_select="rerun", selection_mode="single-row", height=420,
            column_config={
                "picture": st.column_config.ImageColumn("", width="small"),
                "title": st.column_config.TextColumn(t("library.playlist")),
                "creator": st.column_config.TextColumn(t("library.creator")),
                "tracks": st.column_config.NumberColumn(t("library.tracks")),
                "duration": st.column_config.TextColumn(t("library.duration")),
                "played": st.column_config.TextColumn(t("library.played_share"), help=t("library.played_share_help")),
                "plays": st.column_config.NumberColumn(t("library.plays_history")),
            },
        )
        st.caption(t("library.pick_playlist"))
        if event.selection.rows:
            pl = shown.iloc[event.selection.rows[0]]
            theme.section(pl["title"])
            pt = tracks_all[tracks_all["playlist_id"] == pl["id"]]
            ui.kpi_row([
                (t("library.tracks"), fmt_int(len(pt)), None),
                (t("common.artists"), fmt_int(pt["artist_id"].nunique()), None),
                (t("library.played_share"), fmt_pct(pl["played_share"]), None),
                (t("library.plays_history"), fmt_int(pl["plays"]), None),
            ])
            st.dataframe(
                pd.DataFrame({
                    "cover": pt["cover"], "title": pt["track_title"], "artist": pt["artist_name"],
                    "album": pt["album_title"], "plays": pt["plays"],
                }),
                hide_index=True, height=420,
                column_config={
                    "cover": st.column_config.ImageColumn("", width="small"),
                    "title": st.column_config.TextColumn(t("common.track")),
                    "artist": st.column_config.TextColumn(t("common.artist")),
                    "album": st.column_config.TextColumn(t("common.album")),
                    "plays": st.column_config.NumberColumn(t("library.plays_history")),
                },
            )

# --- exports: Excel and A3 poster -------------------------------------------------------

with tab_export:
    theme.section(t("library.excel_title"))
    st.caption(t("library.excel_help"))
    st.download_button(t("library.excel_button"), data.library_xlsx(get_lang()),
                       file_name="bibliotheque_deezer.xlsx" if get_lang() == "fr" else "deezer_library.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       icon=":material/table_view:", key="lib_xlsx")

    st.divider()
    theme.section(t("library.poster_title"))
    st.caption(t("library.poster_help"))
    if fav.empty:
        ui.empty_state(t("library.no_albums"))
    else:
        c1, c2 = st.columns(2)
        order = c1.selectbox(t("library.sort"), list(SORTS), format_func=lambda s: t(f"library.sort_{s}"),
                             key="poster_sort", index=1)
        title = c2.text_input(t("library.poster_heading"), value="", placeholder=t("library.poster_heading_ph"),
                              key="poster_title")
        chosen = sorted_favorites(order)
        layout = best_layout(len(chosen), title_h=40 if title else 0)
        st.caption(t("library.poster_layout", n=len(chosen), cols=layout.cols, rows=layout.rows,
                     size=f"{layout.cover / 72 * 25.4:.0f}"))
        if st.button(t("library.poster_generate"), type="primary", icon=":material/picture_as_pdf:"):
            albums = tuple(
                (r.title, r.artist_name, release_text(r.release_date), r.cover_medium or "", r.cover_big or "")
                for r in chosen.itertuples()
            )
            with st.spinner(t("library.poster_wait")):
                st.session_state["poster_pdf"] = data.album_poster(albums, title.strip() or None)
        if st.session_state.get("poster_pdf"):
            st.download_button(t("library.poster_download"), st.session_state["poster_pdf"],
                               file_name="albums_favoris_A3.pdf", mime="application/pdf",
                               icon=":material/download:", key="poster_dl")
