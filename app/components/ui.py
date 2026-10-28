"""Reusable UI blocks: header, KPI tiles, cover grid, ranked lists, status."""

from __future__ import annotations

from html import escape

import pandas as pd
import streamlit as st

from app.i18n import fmt_datetime_short, fmt_duration, fmt_int, fmt_plays, t

# Pages registry, filled by Home.py so components can link to detail pages.
PAGES: dict[str, st.Page] = {}

CSS = """
<style>
.block-container {padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1200px;}
h1 {font-weight: 650; letter-spacing: -0.02em;}
h2, h3 {font-weight: 600; letter-spacing: -0.01em;}
[data-testid="stMetricValue"] {font-size: 1.7rem; font-weight: 600;}
[data-testid="stMetricLabel"] p {color: #52514e;}
.ds-sub {color: #52514e; margin-top: -0.6rem; margin-bottom: 1.2rem;}
.ds-muted {color: #898781; font-size: 0.85rem;}
.ds-card-title {font-weight: 600; line-height: 1.2; margin: 0.35rem 0 0 0; font-size: 0.92rem;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;}
.ds-card-sub {color: #52514e; font-size: 0.8rem; margin: 0;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;}
.ds-rank {color: #898781; font-size: 0.8rem;}
[data-testid="stImage"] img {border-radius: 6px;}
.ds-hero {font-size: 3rem; font-weight: 700; letter-spacing: -0.03em; line-height: 1;}
.ds-wrapped {background: #f4f8fd; border-radius: 16px; padding: 1.6rem 1.8rem; margin-bottom: 1rem;}
@media (max-width: 640px) {
  [data-testid="stImage"] img {max-width: 180px;}
  .ds-hero {font-size: 2.2rem;}
}
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def header(title: str, subtitle: str | None = None) -> None:
    st.title(title)
    if subtitle:
        st.markdown(f"<div class='ds-sub'>{escape(subtitle)}</div>", unsafe_allow_html=True)


def kpi_row(items: list[tuple[str, str, str | None]]) -> None:
    """items: [(label, value, help)]. Wraps to 2 per row on narrow screens."""
    cols = st.columns(len(items))
    for col, (label, value, help_) in zip(cols, items):
        col.metric(label, value, help=help_, border=True)


def empty_state(message: str | None = None) -> None:
    st.info(message or t("common.no_data"))


def estimated_note(df: pd.DataFrame) -> None:
    if not df.empty and df["duration_is_estimated"].any():
        st.caption("ⓘ " + t("common.estimated_note"))


def open_detail(kind: str, key) -> None:
    page = PAGES.get(kind)
    if page is not None and key is not None and not pd.isna(key):
        st.switch_page(page, query_params={"id": str(int(key))})


def cover_grid(items: pd.DataFrame, kind: str | None, value_fmt, columns: int = 5, key: str = "grid") -> None:
    """Grid of covers from a `stats.top()` frame. Clicking a title opens the detail page."""
    rows = list(items.itertuples(index=False))
    for start in range(0, len(rows), columns):
        cols = st.columns(columns)
        for col, row in zip(cols, rows[start:start + columns]):
            with col:
                if isinstance(row.image, str) and row.image:
                    st.image(row.image, width="stretch")
                label = str(row.label)
                if kind and st.button(f"{row.rank}. {label}", key=f"{key}_{kind}_{row.key}",
                                      type="tertiary", help=t("common.open_page")):
                    open_detail(kind, row.key)
                elif not kind:
                    st.markdown(f"<p class='ds-card-title'>{row.rank}. {escape(label)}</p>", unsafe_allow_html=True)
                sub = escape(row.sublabel) if isinstance(row.sublabel, str) else ""
                st.markdown(f"<p class='ds-card-sub'>{sub}{' · ' if sub else ''}{value_fmt(row)}</p>",
                            unsafe_allow_html=True)


def ranked_table(items: pd.DataFrame, kind: str | None, key: str) -> None:
    """List view of a `stats.top()` frame; selecting a row opens the detail page."""
    view = pd.DataFrame({
        "rank": items["rank"],
        "image": items["image"],
        "label": items["label"],
        "sublabel": items["sublabel"],
        "plays": items["plays"],
        "minutes": items["minutes"].round(0),
    })
    has_image = view["image"].notna().any()
    has_sub = view["sublabel"].notna().any()
    order = ["rank"] + (["image"] if has_image else []) + ["label"] + (["sublabel"] if has_sub else []) + ["plays", "minutes"]
    event = st.dataframe(
        view, hide_index=True, column_order=order, key=key,
        on_select="rerun" if kind else "ignore", selection_mode="single-row",
        column_config={
            "rank": st.column_config.NumberColumn("#", width="small"),
            "image": st.column_config.ImageColumn("", width="small"),
            "label": st.column_config.TextColumn(t("common.name")),
            "sublabel": st.column_config.TextColumn(t("common.artist")),
            "plays": st.column_config.NumberColumn(t("common.plays"), format="localized"),
            "minutes": st.column_config.NumberColumn(t("common.minutes"), format="localized"),
        },
    )
    if kind:
        selected = getattr(getattr(event, "selection", None), "rows", []) or []
        if selected:
            open_detail(kind, items.iloc[selected[0]]["key"])


def value_formatter(metric: str):
    if metric == "minutes":
        return lambda row: fmt_duration(row.minutes)
    return lambda row: fmt_plays(row.plays)


def sync_status(runs: pd.DataFrame, total_plays: int, tz: str) -> None:
    """Small sidebar block: last successful sync, number of plays, possible gaps."""
    with st.sidebar:
        st.divider()
        ok = runs[runs["status"] == "ok"] if not runs.empty else runs
        if ok.empty:
            st.caption(t("status.never"))
        else:
            last = pd.Timestamp(ok["finished_at"].max() or ok["started_at"].max()).tz_localize("UTC").tz_convert(tz)
            st.caption(t("status.last_sync", when=fmt_datetime_short(last)))
        st.caption(t("status.total_plays", n=fmt_int(total_plays)))
        if not runs.empty and runs.iloc[0]["status"] == "error":
            st.caption("⚠️ " + t("status.last_failed"))
        gaps = runs[runs["gap_warning"].notna()] if not runs.empty else runs
        if not gaps.empty:
            with st.expander(t("status.gaps", n=len(gaps))):
                for g in gaps.itertuples():
                    s = pd.Timestamp(g.gap_start).tz_localize("UTC").tz_convert(tz)
                    e = pd.Timestamp(g.gap_end).tz_localize("UTC").tz_convert(tz)
                    st.caption(t("status.gap_between", start=fmt_datetime_short(s), end=fmt_datetime_short(e)))


def csv_download(df: pd.DataFrame, filename: str, key: str) -> None:
    st.download_button(t("common.download_csv"), df.to_csv(index=False).encode("utf-8"),
                       file_name=filename, mime="text/csv", key=key, icon=":material/download:")


def export_plays(df: pd.DataFrame) -> pd.DataFrame:
    """Plays in a flat, readable shape for CSV export."""
    return pd.DataFrame({
        "played_at_local": df["played_local"].dt.strftime("%Y-%m-%d %H:%M:%S"),
        "played_at_utc": df["played_at"].dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "track": df["track_title"], "artist": df["artist_name"], "album": df["album_title"],
        "genre": df["genre"], "listened_seconds": df["listened_seconds"].astype(int),
        "duration_is_estimated": df["duration_is_estimated"], "track_id": df["track_id"],
    })
