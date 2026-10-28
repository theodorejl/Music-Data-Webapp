"""Reusable UI blocks drawn to the taste-skill app rules: title row, the divided KPI strip,
bar lists with artwork, genre tiles, short rows, the cover grid, and the collection status."""

from __future__ import annotations

from html import escape

import pandas as pd
import streamlit as st

from app.components import theme
from app.i18n import fmt_datetime_short, fmt_duration, fmt_int, fmt_plays, t

# Pages registry, filled by Home.py so components can link to detail pages.
PAGES: dict[str, st.Page] = {}


def inject_css() -> None:
    theme.inject()


def header(title: str, subtitle: str | None = None, lead: str | None = None, dot: str | None = None) -> None:
    """Title row: noun h1 and one grey line about the data (period · finding)."""
    theme.page_header(title, kicker=subtitle, lead=lead)


def kpi_row(items: list[tuple[str, str, str | None]]) -> None:
    """items: [(label, value, caption)]: one container split by 1px dividers, label over value,
    the caption (baseline, window or method) in small grey under it."""
    cells = "".join(
        f"<div class='ds-kpi'><div class='ds-kpi-label'>{escape(label)}</div>"
        f"<div class='ds-kpi-value num'>{escape(str(value))}</div>"
        + (f"<div class='ds-kpi-cap'>{escape(cap)}</div>" if cap else "") + "</div>"
        for label, value, cap in items)
    st.html(f"<div class='ds-kpis'>{cells}</div>")


def bar_list(items: pd.DataFrame, value_fmt, round_art: bool = False, limit: int = 6, metric: str = "plays") -> None:
    """A ranking where each row is artwork, a label line and a 10px bar with its value after it;
    the leader in cobalt, the rest in its pale tint (§7.9)."""
    rows = list(items.head(limit).itertuples(index=False))
    if not rows:
        return
    top = max(float(getattr(r, metric)) for r in rows) or 1
    html = []
    for i, r in enumerate(rows):
        img = (f"<img src='{escape(r.image)}' alt=''>" if isinstance(r.image, str) and r.image
               else "<div class='ds-art-empty'></div>")
        sub = f"<em>{escape(r.sublabel)}</em>" if isinstance(r.sublabel, str) and r.sublabel else ""
        width = max(4.0, 88.0 * float(getattr(r, metric)) / top)
        html.append(
            f"<div class='ds-bar-row{' round' if round_art else ''}'>{img}<div>"
            f"<div class='ds-bar-label'><span>{escape(str(r.label))}</span>{sub}</div>"
            f"<div class='ds-bar-track'><div class='ds-bar-fill{'' if i == 0 else ' dim'}' style='width:{width:.1f}%'></div>"
            f"<span class='ds-bar-value num'>{escape(value_fmt(r))}</span></div></div></div>")
    st.html(f"<div class='ds-bars'>{''.join(html)}</div>")


def genre_tiles(items: pd.DataFrame, total_minutes: float, limit: int = 6) -> None:
    """Genres as pale tiles with the dark of their own hue (the style's move)."""
    rows = list(items.head(limit).itertuples(index=False))
    if not rows:
        return
    from app.i18n import fmt_pct

    tiles = []
    for i, r in enumerate(rows):
        bg, ink = theme.tile(i)
        share = fmt_pct(float(r.minutes) / total_minutes) if total_minutes else "–"
        tiles.append(f"<div class='ds-tile' style='background:{bg};color:{ink}'><b>{escape(str(r.label))}</b>"
                     f"<span class='num'>{share} · {escape(fmt_duration(r.minutes))}</span></div>")
    st.html(f"<div class='ds-tiles'>{''.join(tiles)}</div>")


def short_rows(df: pd.DataFrame, limit: int = 5) -> None:
    """Recent plays as two-line rows with their cover; time on the right."""
    from app.i18n import fmt_seconds

    rows = []
    for r in df.head(limit).itertuples(index=False):
        img = f"<img src='{escape(r.cover)}' alt=''>" if isinstance(r.cover, str) and r.cover else "<div></div>"
        when = r.played_local.strftime("%H:%M")
        rows.append(f"<div class='ds-row'>{img}<div class='ds-row-main'><b>{escape(str(r.track_title))}</b>"
                    f"<span>{escape(str(r.artist_name))}</span></div>"
                    f"<div class='ds-row-end num'>{when}<br>{fmt_seconds(r.listened_seconds)}"
                    f"{'*' if r.duration_is_estimated else ''}</div></div>")
    st.html(f"<div class='ds-rows'>{''.join(rows)}</div>")


def day_in_covers(df: pd.DataFrame, per_hour: int = 4) -> None:
    """Signature element: one day's plays as their covers, one column per hour (0-23 h),
    stacked from the axis up (four at most, then "+n"), so the strip shows both what was
    played and when the listening was dense."""
    by_hour: dict[int, list] = {}
    for r in df.sort_values("played_local").itertuples(index=False):
        by_hour.setdefault(r.played_local.hour, []).append(r)
    cols = []
    for h in range(24):
        plays = by_hour.get(h, [])
        cells = []
        for r in plays[-per_hour:]:
            tip = escape(f"{r.played_local:%H:%M} · {r.track_title} — {r.artist_name}")
            if isinstance(r.cover, str) and r.cover:
                cells.append(f"<img src='{escape(r.cover)}' alt='{tip}' title='{tip}'>")
            else:
                cells.append(f"<i title='{tip}'></i>")
        more = f"<span class='ds-day-more num'>+{len(plays) - per_hour}</span>" if len(plays) > per_hour else ""
        label = f"<span class='ds-day-h num'>{h:02d}</span>" if h % 3 == 0 else "<span class='ds-day-h'></span>"
        cols.append(f"<div class='ds-day-col'>{more}{''.join(reversed(cells))}{label}</div>")
    st.html(f"<div class='ds-day'>{''.join(cols)}</div>")


def empty_state(message: str | None = None) -> None:
    st.info(message or t("common.no_data"))


def estimated_note(df: pd.DataFrame) -> None:
    if not df.empty and df["duration_is_estimated"].any():
        st.caption("ⓘ " + t("common.estimated_note"))


def open_detail(kind: str, key) -> None:
    page = PAGES.get(kind)
    if page is not None and key is not None and not pd.isna(key):
        st.switch_page(page, query_params={"id": str(int(key))})


def cover_grid(items: pd.DataFrame, kind: str | None, value_fmt, columns: int = 6, key: str = "grid") -> None:
    """Grid of covers from a `stats.top()` frame (peer objects, 6 across at most).
    Clicking a title opens the detail page."""
    columns = min(columns, 6)
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
                    st.markdown(f"<p class='ds-cap-title'>{row.rank}. {escape(label)}</p>", unsafe_allow_html=True)
                sub = escape(row.sublabel) if isinstance(row.sublabel, str) else ""
                st.markdown(f"<p class='ds-cap-sub'>{sub}{' · ' if sub else ''}{value_fmt(row)}</p>",
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
            "rank": st.column_config.NumberColumn("#", width="small", alignment="right"),
            "image": st.column_config.ImageColumn("", width="small"),
            "label": st.column_config.TextColumn(t("common.name")),
            "sublabel": st.column_config.TextColumn(t("common.artist")),
            "plays": st.column_config.NumberColumn(t("common.plays"), format="localized", alignment="right"),
            "minutes": st.column_config.NumberColumn(t("common.minutes"), format="localized", alignment="right"),
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
        ok = runs[runs["status"] == "ok"] if not runs.empty else runs
        lines = []
        if ok.empty:
            lines.append(escape(t("status.never")))
        else:
            last = pd.Timestamp(ok["finished_at"].max() or ok["started_at"].max()).tz_localize("UTC").tz_convert(tz)
            lines.append(escape(t("status.last_sync", when=fmt_datetime_short(last))))
        lines.append(escape(t("status.total_plays", n=fmt_int(total_plays))))
        if not runs.empty and runs.iloc[0]["status"] == "error":
            lines.append(f"<span style='color:var(--negative)'>{escape(t('status.last_failed'))}</span>")
        st.html(f"<div class='ds-side-title'>{escape(t('status.title'))}</div><div class='ds-stamp'>{'<br>'.join(lines)}</div>")
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


def excel_download(df: pd.DataFrame, filename: str, sheet: str, title: str, key: str,
                   formats: dict[str, str] | None = None) -> None:
    """Download button producing the same styled workbook as the Excel exports."""
    from app.i18n import get_lang
    from core.excel import table_sheet, to_xlsx

    st.download_button(t("common.download_excel"), to_xlsx([table_sheet(df, sheet, title, formats)], get_lang()),
                       file_name=filename, key=key, icon=":material/table_view:",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def export_plays(df: pd.DataFrame) -> pd.DataFrame:
    """Plays in a flat, readable shape for CSV export."""
    return pd.DataFrame({
        "played_at_local": df["played_local"].dt.strftime("%Y-%m-%d %H:%M:%S"),
        "played_at_utc": df["played_at"].dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "track": df["track_title"], "artist": df["artist_name"], "album": df["album_title"],
        "genre": df["genre"], "listened_seconds": df["listened_seconds"].astype(int),
        "duration_is_estimated": df["duration_is_estimated"], "track_id": df["track_id"],
    })
