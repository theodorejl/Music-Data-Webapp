"""Cached, read-only data access for the app + global sidebar filters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from app.i18n import fmt_date, t
from core import stats
from core.config import get_setting, get_settings
from core.db import get_engine, init_db

STATS_TTL = 120  # seconds


def _engine():
    # Creating missing tables on an empty database is harmless; the app never
    # writes data (except the admin page).
    settings = get_settings()
    if settings.data_url and not get_setting("DATABASE_URL"):
        # Hosted app: a read-only copy of the database published on the repo's data branch,
        # refreshed every 10 minutes.
        import tempfile
        from pathlib import Path

        from core.cloud_db import download_copy

        path = download_copy(settings.data_url, Path(tempfile.gettempdir()) / "deezer-stats")
        return get_engine(f"sqlite:///{path}")
    return init_db(get_engine(settings.database_url))


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


def current_filters() -> Filters:
    """The period chosen in the page header, kept across pages (plain session keys, so it
    survives pages that do not show the period chips)."""
    tz = timezone_name()
    period = st.session_state.get("period", "month")
    custom = st.session_state.get("period_dates")
    if period == "custom" and not custom:
        today = pd.Timestamp.now(tz=tz).date()
        custom = (today - timedelta(days=30), today)
    start, end = period_bounds(period, tz, custom)
    return Filters(period, start, end, 0)


def _sync_period() -> None:
    st.session_state["period"] = st.session_state["f_period_w"]


def _sync_dates() -> None:
    value = st.session_state.get("f_dates_w")
    if isinstance(value, (tuple, list)) and value:
        st.session_state["period_dates"] = (value[0], value[-1])


def period_control() -> None:
    """Period chips for the page header (plus a date range for "custom")."""
    st.session_state["f_period_w"] = st.session_state.get("period", "month")
    st.segmented_control(t("filters.period"), PERIODS, key="f_period_w", on_change=_sync_period, required=True,
                         format_func=lambda p: t(f"period.{p}"), label_visibility="collapsed")
    if st.session_state.get("period") == "custom":
        f = current_filters()
        st.session_state["f_dates_w"] = (f.start.date(), (f.end - timedelta(days=1)).date())
        st.date_input(t("filters.dates"), key="f_dates_w", on_change=_sync_dates, format="DD/MM/YYYY",
                      label_visibility="collapsed", width=280)


def get_filters() -> Filters:
    return st.session_state.get("filters") or current_filters()


def period_pills(key: str, short: bool = False, default: str | None = None) -> tuple[pd.Timestamp | None, pd.Timestamp | None, str]:
    """Period buttons shown with a table or under a chart. Defaults to the page period (or to
    `default` on pages without one); returns (start, end, label) for that block only."""
    f = get_filters()
    options = TABLE_PERIODS if f.period in TABLE_PERIODS else ["page"] + TABLE_PERIODS
    default = default or (f.period if f.period in TABLE_PERIODS else "page")
    names = "period_short" if short else "period"
    choice = st.segmented_control(t("filters.table_period"), options, default=default, required=True,
                                  key=f"tp_{key}_{f.period}", label_visibility="collapsed", width="content",
                                  format_func=lambda p: f.label if p == "page" else t(f"{names}.{p}"))
    if choice == "page":
        return f.start, f.end, f.label
    start, end = period_bounds(choice, timezone_name())
    return start, end, t(f"period.{choice}")


@dataclass
class Scope:
    df: pd.DataFrame
    dim: str | None
    start: pd.Timestamp | None
    end: pd.Timestamp | None
    label: str


def scope_bar(key: str, dims: list[str] | None = None, default: str | None = None, periods: bool = True,
              base: pd.DataFrame | None = None) -> Scope:
    """Chips under a chart: its own time range (the page's by default) and what it counts
    (artists, albums, tracks, genres). Draw the chart in a container created before this call."""
    f = get_filters()
    start, end, label, dim = f.start, f.end, f.label, None
    # One flowing row: the chips sit side by side and only wrap when the panel is narrow.
    with st.container(key=f"scope-{key}", horizontal=True, horizontal_alignment="distribute",
                      vertical_alignment="center", gap="small"):
        if periods:
            start, end, label = period_pills(key, short=True)
        if dims:
            dim = st.segmented_control(t("scope.what"), dims, default=default or dims[0], required=True,
                                       key=f"dim_{key}", format_func=lambda d: t(f"scope.{d}"),
                                       label_visibility="collapsed", width="content")
    frame = base if base is not None else all_plays()
    return Scope(stats.filter_frame(frame, start, end), dim, start, end, label)


def scoped_plays(key: str) -> tuple[pd.DataFrame, str]:
    """Plays restricted by the period buttons of one table."""
    start, end, label = period_pills(key)
    return stats.filter_frame(all_plays(), start, end), label


def scope_frame(df: pd.DataFrame, key: str, col: str, short: bool = False, default: str | None = None) -> pd.DataFrame:
    """Any frame restricted by period buttons on a datetime column (tz-aware or local naive)."""
    start, end, _ = period_pills(key, short=short, default=default)
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


@st.cache_data(ttl=STATS_TTL, show_spinner=False)
def genre_order() -> list[str]:
    """Genres by listening time over the whole history: fixes each genre's colour."""
    plays = all_plays()
    if plays.empty:
        return []
    return list(plays.dropna(subset=["genre"]).groupby("genre")["minutes"].sum().sort_values(ascending=False).index)


@st.cache_data(ttl=STATS_TTL, show_spinner=False)
def artist_genres() -> dict[int, str]:
    """Main genre of each artist (most played genre among their plays)."""
    plays = all_plays().dropna(subset=["genre", "artist_id"])
    if plays.empty:
        return {}
    g = plays.groupby(["artist_id", "genre"])["minutes"].sum().reset_index().sort_values("minutes", ascending=False)
    return {int(k): v for k, v in g.drop_duplicates("artist_id").set_index("artist_id")["genre"].items()}


@st.cache_data(ttl=6 * 3600, show_spinner=False, max_entries=8)
def recommendations(key: tuple, _profile) -> pd.DataFrame:
    """The three engines' picks, kept six hours for the same seeds (key), then refreshed."""
    from core.recommend import recommend

    return recommend(_profile, 12)


@st.cache_data(ttl=STATS_TTL, show_spinner=False)
def search_index() -> list[tuple[str, str]]:
    """(target, label) for the search box: artists, then albums, then tracks, most played first."""
    plays = all_plays()
    out: list[tuple[str, str]] = []
    if plays.empty:
        return out
    for kind, key, label, sub in (("artist", "artist_id", "artist_name", None),
                                  ("album", "album_id", "album_title", "artist_name"),
                                  ("track", "track_id", "track_title", "artist_name")):
        d = plays.dropna(subset=[key])
        g = d.groupby(key).agg(n=("play_id", "count"), label=(label, "first"),
                               **({"sub": (sub, "first")} if sub else {})).sort_values("n", ascending=False)
        for k, r in g.iterrows():
            text = f"{r['label']} — {r['sub']}" if sub and isinstance(r.get("sub"), str) else str(r["label"])
            out.append((f"{kind}:{int(k)}", f"{t('search.' + kind)} · {text}"))
    return out


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
