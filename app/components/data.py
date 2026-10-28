"""Cached, read-only data access for the app + global sidebar filters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from app.i18n import fmt_date, t
from core import stats
from core.config import get_settings
from core.db import get_engine, init_db

STATS_TTL = 120  # seconds


def _engine():
    # Creating missing tables on an empty database is harmless; the app never
    # writes data (except the admin page).
    return init_db(get_engine(get_settings().database_url))


def timezone_name() -> str:
    return get_settings().timezone


@st.cache_data(ttl=STATS_TTL, show_spinner=False)
def raw_data() -> stats.RawData:
    return stats.load_raw(_engine())


@st.cache_data(ttl=STATS_TTL, show_spinner=False)
def all_plays() -> pd.DataFrame:
    """Every visible play, aliases applied, in the display timezone."""
    return stats.assemble(raw_data(), timezone_name())


@st.cache_data(ttl=STATS_TTL, show_spinner=False)
def sync_runs() -> pd.DataFrame:
    return stats.load_sync_runs(_engine())


@st.cache_data(ttl=600, show_spinner=False)
def preview_url(track_id: int) -> str | None:
    """Fresh 30 s preview URL from the public API (URLs expire)."""
    from core.deezer_public import fetch_preview_url

    try:
        return fetch_preview_url(int(track_id))
    except Exception:
        return None


def clear_caches() -> None:
    st.cache_data.clear()


# --- global filters -------------------------------------------------------------

PERIODS = ["today", "week", "month", "year", "all", "custom"]
TABLE_PERIODS = ["today", "week", "month", "year", "all"]


@dataclass
class Filters:
    period: str
    start: pd.Timestamp | None  # tz-aware, inclusive
    end: pd.Timestamp | None  # tz-aware, exclusive
    min_seconds: int

    @property
    def label(self) -> str:
        if self.period == "custom" and self.start is not None and self.end is not None:
            return f"{fmt_date(self.start.date(), short=True)} – {fmt_date((self.end - timedelta(days=1)).date(), short=True)}"
        return t(f"period.{self.period}")


def period_bounds(period: str, tz: str, custom: tuple[date, date] | None = None):
    now = pd.Timestamp.now(tz=tz)
    today = now.normalize()
    tomorrow = today + pd.Timedelta(days=1)
    if period == "today":
        return today, tomorrow
    if period == "week":  # since Monday
        return today - pd.Timedelta(days=today.weekday()), tomorrow
    if period == "month":
        return pd.Timestamp(year=now.year, month=now.month, day=1, tz=tz), tomorrow
    if period in ("7d", "30d"):  # kept for old links
        return today - pd.Timedelta(days=6 if period == "7d" else 29), tomorrow
    if period == "year":
        return pd.Timestamp(year=now.year, month=1, day=1, tz=tz), tomorrow
    if period == "custom" and custom:
        start = pd.Timestamp(custom[0]).tz_localize(tz)
        end = pd.Timestamp(custom[-1]).tz_localize(tz) + pd.Timedelta(days=1)
        return start, end
    return None, None


def sidebar_filters() -> Filters:
    tz = timezone_name()
    with st.sidebar:
        st.markdown(f"**{t('filters.title')}**")
        period = st.selectbox(t("filters.period"), PERIODS, index=PERIODS.index("month"), key="f_period",
                              format_func=lambda p: t(f"period.{p}"))
        custom = None
        if period == "custom":
            today = pd.Timestamp.now(tz=tz).date()
            value = st.date_input(t("filters.dates"), value=(today - timedelta(days=30), today), key="f_dates",
                                  format="DD/MM/YYYY")
            if isinstance(value, (tuple, list)) and len(value) == 2:
                custom = (value[0], value[1])
            elif isinstance(value, (tuple, list)) and len(value) == 1:
                custom = (value[0], value[0])
    start, end = period_bounds(period, tz, custom)
    return Filters(period, start, end, 0)


def get_filters() -> Filters:
    return st.session_state["filters"]


def period_pills(key: str) -> tuple[pd.Timestamp | None, pd.Timestamp | None, str]:
    """Period buttons shown above a data table. Defaults to the page period;
    returns (start, end, label) for that table only."""
    f = get_filters()
    options = TABLE_PERIODS if f.period in TABLE_PERIODS else ["page"] + TABLE_PERIODS
    default = f.period if f.period in TABLE_PERIODS else "page"
    choice = st.segmented_control(t("filters.table_period"), options, default=default, required=True,
                                  key=f"tp_{key}_{f.period}", label_visibility="collapsed",
                                  format_func=lambda p: f.label if p == "page" else t(f"period.{p}"))
    if choice == "page":
        return f.start, f.end, f.label
    start, end = period_bounds(choice, timezone_name())
    return start, end, t(f"period.{choice}")


def scoped_plays(key: str) -> tuple[pd.DataFrame, str]:
    """Plays restricted by the period buttons of one table."""
    start, end, label = period_pills(key)
    return stats.filter_frame(all_plays(), start, end), label


def scope_frame(df: pd.DataFrame, key: str, col: str) -> pd.DataFrame:
    """Any frame restricted by period buttons on a datetime column (tz-aware or local naive)."""
    start, end, _ = period_pills(key)
    if start is None and end is None:
        return df
    values = pd.to_datetime(df[col], errors="coerce")
    if getattr(values.dt, "tz", None) is None:
        start, end = (x.tz_localize(None) if x is not None else None for x in (start, end))
    mask = pd.Series(True, index=df.index)
    if start is not None:
        mask &= values >= start
    if end is not None:
        mask &= values < end
    return df[mask]


def filtered_plays() -> pd.DataFrame:
    f = get_filters()
    return stats.filter_frame(all_plays(), f.start, f.end, f.min_seconds)


# --- library (favorite albums & playlists) ----------------------------------------

@st.cache_data(ttl=STATS_TTL, show_spinner=False)
def library() -> stats.LibraryData:
    return stats.load_library(_engine())


@st.cache_data(ttl=STATS_TTL, show_spinner=False)
def favorite_albums() -> pd.DataFrame:
    raw = raw_data()
    genres = stats.album_genres(raw.albums, raw.tags, raw.aliases)
    return stats.favorite_albums_view(library(), all_plays(), genres)


@st.cache_data(ttl=STATS_TTL, show_spinner=False)
def playlists() -> pd.DataFrame:
    return stats.playlists_view(library(), all_plays())


@st.cache_data(ttl=STATS_TTL, show_spinner=False)
def playlist_tracks() -> pd.DataFrame:
    return stats.playlist_tracks_view(library(), all_plays())


@st.cache_data(ttl=3600, show_spinner=False, max_entries=8)
def library_xlsx(lang: str) -> bytes:
    from core.excel import library_sheets, to_xlsx

    return to_xlsx(library_sheets(favorite_albums(), playlists(), playlist_tracks(), lang), lang)


@st.cache_data(ttl=3600, show_spinner=False, max_entries=8)
def history_xlsx(lang: str, play_ids: tuple[int, ...]) -> bytes:
    from core.excel import history_sheets, to_xlsx

    plays = all_plays()
    return to_xlsx(history_sheets(plays[plays["play_id"].isin(play_ids)], lang), lang)


@st.cache_data(ttl=3600, show_spinner=False, max_entries=4)
def album_poster(albums: tuple[tuple[str, str, str, str, str], ...], title: str | None) -> bytes:
    """albums: (title, artist, release text, cover 250px, cover 500px)."""
    from core.poster import album_poster_pdf

    return album_poster_pdf([{"title": a, "artist": b, "release": c, "cover_url": d, "cover_url_big": e}
                             for a, b, c, d, e in albums], title)
