"""Excel workbooks: listening history and library (favorite albums, playlists).

Same output for the files kept in "Exports Excel/" by the sync script and for the
download buttons of the app. Each sheet is a real Excel table (sort and filter on
every column, banding that survives sorting), with one column per field, a
title, a pastel colour per sheet, no gridlines and proper number/date formats.
"""

from __future__ import annotations

import io
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path

import pandas as pd
from sqlalchemy.engine import Engine

from core import stats

log = logging.getLogger(__name__)

HISTORY_FILE = "Historique des écoutes.xlsx"
LIBRARY_FILE = "Bibliothèque - albums et playlists.xlsx"

FONT = "Aptos"
INK, MUTED = "262626", "8C8C8C"
# (built-in table style giving pastel row bands, header fill, header text, tab colour)
PALETTES = [
    ("TableStyleLight2", "C9DAF0", "1F3864", "9DB9E3"),  # blue
    ("TableStyleLight4", "D9E7C3", "38521B", "B5D08E"),  # sage green
    ("TableStyleLight5", "DCD3EB", "3F2C68", "B9A8D8"),  # lavender
    ("TableStyleLight7", "FADCC4", "7A3E0C", "F4B98C"),  # peach
    ("TableStyleLight6", "C4E3EC", "1B4F5C", "8FCADB"),  # aqua
    ("TableStyleLight3", "F2D9D8", "6E2B2A", "E5AFAD"),  # rose
]

LABELS = {
    "fr": {
        "sheet_plays": "Écoutes", "sheet_tracks": "Titres", "sheet_albums": "Albums",
        "sheet_artists": "Artistes", "sheet_days": "Par jour", "sheet_fav": "Albums favoris",
        "sheet_playlists": "Playlists", "sheet_pl_tracks": "Titres des playlists",
        "title_plays": "Historique de mes écoutes", "title_tracks": "Mes titres les plus écoutés",
        "title_albums": "Mes albums les plus écoutés", "title_artists": "Mes artistes les plus écoutés",
        "title_days": "Mes écoutes jour par jour", "title_fav": "Mes albums favoris",
        "title_playlists": "Mes playlists", "title_pl_tracks": "Tous les titres de mes playlists",
        "info": "{n} lignes · mis à jour le {date} à {time} · trie et filtre avec les flèches des en-têtes",
        "date": "Date", "time": "Heure", "weekday": "Jour", "month": "Mois", "year": "Année",
        "date_utc": "Date et heure UTC", "track": "Titre", "artist": "Artiste",
        "album": "Album", "genre": "Genre", "listened": "Écouté (s)", "estimated": "Durée estimée",
        "plays": "Écoutes", "minutes": "Minutes", "first": "Première écoute", "last": "Dernière écoute",
        "day": "Jour", "release": "Date de sortie", "release_year": "Année de sortie", "label": "Label",
        "added": "Ajouté le", "playlist": "Playlist", "creator": "Créée par", "own": "Ma playlist",
        "nb_tracks": "Titres", "duration": "Durée (min)", "artists": "Artistes",
        "played_tracks": "Titres écoutés", "played_share": "Part écoutée", "position": "Position",
        "track_id": "ID titre", "album_id": "ID album", "playlist_id": "ID playlist", "yes": "Oui", "no": "Non",
        "weekdays": ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"],
        "date_fmt": "dd/mm/yyyy", "datetime_fmt": "dd/mm/yyyy hh:mm",
    },
    "en": {
        "sheet_plays": "Plays", "sheet_tracks": "Tracks", "sheet_albums": "Albums",
        "sheet_artists": "Artists", "sheet_days": "Per day", "sheet_fav": "Favorite albums",
        "sheet_playlists": "Playlists", "sheet_pl_tracks": "Playlist tracks",
        "title_plays": "My listening history", "title_tracks": "My most played tracks",
        "title_albums": "My most played albums", "title_artists": "My most played artists",
        "title_days": "My plays day by day", "title_fav": "My favorite albums",
        "title_playlists": "My playlists", "title_pl_tracks": "Every track of my playlists",
        "info": "{n} rows · updated on {date} at {time} · sort and filter with the header arrows",
        "date": "Date", "time": "Time", "weekday": "Weekday", "month": "Month", "year": "Year",
        "date_utc": "UTC date and time", "track": "Track", "artist": "Artist",
        "album": "Album", "genre": "Genre", "listened": "Listened (s)", "estimated": "Estimated duration",
        "plays": "Plays", "minutes": "Minutes", "first": "First play", "last": "Last play",
        "day": "Day", "release": "Release date", "release_year": "Release year", "label": "Label",
        "added": "Added on", "playlist": "Playlist", "creator": "Created by", "own": "My playlist",
        "nb_tracks": "Tracks", "duration": "Duration (min)", "artists": "Artists",
        "played_tracks": "Tracks played", "played_share": "Share played", "position": "Position",
        "track_id": "Track ID", "album_id": "Album ID", "playlist_id": "Playlist ID", "yes": "Yes", "no": "No",
        "weekdays": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
        "date_fmt": "yyyy-mm-dd", "datetime_fmt": "yyyy-mm-dd hh:mm",
    },
}


@dataclass
class Sheet:
    name: str
    title: str
    df: pd.DataFrame
    formats: dict[str, str] = field(default_factory=dict)  # column -> date|datetime|time|int|dec|pct|id|text


def _naive(s) -> pd.Series:
    """Excel cannot store timezones: keep the local wall-clock time."""
    s = pd.to_datetime(pd.Series(s), errors="coerce")
    return s.dt.tz_localize(None) if getattr(s.dt, "tz", None) is not None else s


def _col(df: pd.DataFrame, name: str, default=None) -> pd.Series:
    return df[name] if name in df else pd.Series([default] * len(df), index=df.index, dtype=object)


# --- sheet builders -----------------------------------------------------------------

def history_sheets(plays: pd.DataFrame, lang: str = "fr") -> list[Sheet]:
    L = LABELS[lang]
    p = plays.sort_values("played_at", ascending=False)
    local = _naive(p["played_local"])
    sheets = [Sheet(L["sheet_plays"], L["title_plays"], pd.DataFrame({
        L["date"]: local.dt.normalize(), L["time"]: local.dt.time, L["weekday"]: local.dt.weekday.map(
            lambda i: L["weekdays"][int(i)] if pd.notna(i) else None),
        L["month"]: local.dt.strftime("%Y-%m"), L["year"]: local.dt.year,
        L["track"]: p["track_title"].values, L["artist"]: p["artist_name"].values, L["album"]: p["album_title"].values,
        L["genre"]: p["genre"].values, L["listened"]: p["listened_seconds"].astype(int).values,
        L["estimated"]: p["duration_is_estimated"].map({True: L["yes"], False: L["no"]}).values,
        L["date_utc"]: _naive(p["played_at"]).values, L["track_id"]: p["track_id"].values,
        L["album_id"]: p["album_id"].values,
    }), {L["date"]: "date", L["time"]: "time", L["year"]: "id", L["listened"]: "int",
         L["date_utc"]: "datetime", L["track_id"]: "id", L["album_id"]: "id"})]
    if p.empty:
        return sheets

    def agg(keys: list[str], cols: dict[str, str]) -> pd.DataFrame:
        g = p.groupby(keys, dropna=False).agg(plays=("play_id", "count"), minutes=("minutes", "sum"),
                                               first=("played_local", "min"), last=("played_local", "max"))
        g = g.reset_index().sort_values(["plays", "minutes"], ascending=False)
        g["first"], g["last"] = _naive(g["first"]).values, _naive(g["last"]).values
        return g.rename(columns={**cols, "plays": L["plays"], "minutes": L["minutes"],
                                 "first": L["first"], "last": L["last"]})

    agg_formats = {L["plays"]: "int", L["minutes"]: "dec", L["first"]: "datetime", L["last"]: "datetime"}
    sheets.append(Sheet(L["sheet_tracks"], L["title_tracks"], agg(
        ["track_title", "artist_name", "album_title"],
        {"track_title": L["track"], "artist_name": L["artist"], "album_title": L["album"]}), agg_formats))
    sheets.append(Sheet(L["sheet_albums"], L["title_albums"], agg(
        ["album_title", "artist_name"], {"album_title": L["album"], "artist_name": L["artist"]}), agg_formats))
    sheets.append(Sheet(L["sheet_artists"], L["title_artists"], agg(
        ["artist_name"], {"artist_name": L["artist"]}), agg_formats))
    day = local.dt.normalize()
    days = p.assign(_day=day.values).groupby("_day").agg(plays=("play_id", "count"), minutes=("minutes", "sum"))
    days = days.reset_index().sort_values("_day", ascending=False)
    sheets.append(Sheet(L["sheet_days"], L["title_days"], pd.DataFrame({
        L["day"]: days["_day"].values,
        L["weekday"]: [L["weekdays"][d.weekday()] for d in days["_day"]],
        L["plays"]: days["plays"].values, L["minutes"]: days["minutes"].values,
    }), {L["day"]: "date", L["plays"]: "int", L["minutes"]: "dec"}))
    return sheets


def library_sheets(favorites: pd.DataFrame, playlists: pd.DataFrame, playlist_tracks: pd.DataFrame,
                   lang: str = "fr") -> list[Sheet]:
    L = LABELS[lang]
    fav = favorites
    release = pd.to_datetime(_col(fav, "release_date"), errors="coerce")
    sheets = [Sheet(L["sheet_fav"], L["title_fav"], pd.DataFrame({
        L["album"]: _col(fav, "title").values, L["artist"]: _col(fav, "artist_name").values,
        L["release"]: release.values, L["release_year"]: release.dt.year.values,
        L["genre"]: _col(fav, "genre").values, L["label"]: _col(fav, "label").values,
        L["added"]: _naive(_col(fav, "added_at")).values,
        L["plays"]: _col(fav, "plays", 0).values, L["minutes"]: _col(fav, "minutes", 0.0).values,
        L["album_id"]: _col(fav, "album_id").values,
    }), {L["release"]: "date", L["release_year"]: "id", L["added"]: "date", L["plays"]: "int",
         L["minutes"]: "dec", L["album_id"]: "id"})]
    pl = playlists
    sheets.append(Sheet(L["sheet_playlists"], L["title_playlists"], pd.DataFrame({
        L["playlist"]: _col(pl, "title").values, L["creator"]: _col(pl, "creator_name").values,
        L["own"]: _col(pl, "is_own", False).map({True: L["yes"], False: L["no"]}).values,
        L["nb_tracks"]: _col(pl, "tracks", 0).values,
        L["duration"]: (pd.to_numeric(_col(pl, "duration"), errors="coerce") / 60).values,
        L["artists"]: _col(pl, "artists", 0).values, L["played_tracks"]: _col(pl, "played_tracks", 0).values,
        L["played_share"]: _col(pl, "played_share", 0.0).values, L["plays"]: _col(pl, "plays", 0).values,
        L["added"]: _naive(_col(pl, "added_at")).values, L["playlist_id"]: _col(pl, "id").values,
    }), {L["nb_tracks"]: "int", L["duration"]: "int", L["artists"]: "int", L["played_tracks"]: "int",
         L["played_share"]: "pct", L["plays"]: "int", L["added"]: "date", L["playlist_id"]: "id"}))
    titles = dict(zip(_col(pl, "id"), _col(pl, "title")))
    pt = playlist_tracks
    sheets.append(Sheet(L["sheet_pl_tracks"], L["title_pl_tracks"], pd.DataFrame({
        L["playlist"]: _col(pt, "playlist_id").map(titles).values,
        L["position"]: (pd.to_numeric(_col(pt, "position"), errors="coerce") + 1).values,
        L["track"]: _col(pt, "track_title").values, L["artist"]: _col(pt, "artist_name").values,
        L["album"]: _col(pt, "album_title").values, L["plays"]: _col(pt, "plays", 0).values,
        L["added"]: _naive(_col(pt, "added_at")).values, L["track_id"]: _col(pt, "track_id").values,
    }), {L["position"]: "int", L["plays"]: "int", L["added"]: "date", L["track_id"]: "id"}))
    return sheets


def table_sheet(df: pd.DataFrame, name: str, title: str, formats: dict[str, str] | None = None) -> Sheet:
    return Sheet(name, title, df, formats or {})


# --- workbook writer --------------------------------------------------------------------

def _cell_value(v):
    if v is None:
        return None
    if isinstance(v, float) and v != v:  # NaN
        return None
    if v is pd.NaT or (isinstance(v, pd.Timestamp) and pd.isna(v)):
        return None
    if isinstance(v, pd.Timestamp):
        return v.to_pydatetime()
    if hasattr(v, "item") and not isinstance(v, (str, bytes)):  # numpy scalar
        try:
            v = v.item()
        except (ValueError, AttributeError):
            pass
        if isinstance(v, int) and not isinstance(v, bool) and abs(v) > 10**18:  # ns timestamps
            return pd.Timestamp(v).to_pydatetime()
    return v


def _kind(series: pd.Series, declared: str | None) -> str:
    if declared:
        return declared
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"
    if pd.api.types.is_integer_dtype(series):
        return "int"
    if pd.api.types.is_float_dtype(series):
        return "dec"
    return "text"


def to_xlsx(sheets: list[Sheet], lang: str = "fr") -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.table import Table, TableStyleInfo

    L = LABELS[lang]
    number_formats = {
        "date": L["date_fmt"], "datetime": L["datetime_fmt"], "time": "hh:mm", "int": "#,##0",
        "dec": "#,##0.0", "pct": "0%", "id": "0", "text": "@",
    }
    now = datetime.now()
    wb = Workbook()
    wb.remove(wb.active)
    used_names: set[str] = set()
    for idx, sheet in enumerate(sheets):
        style, head_fill, head_ink, tab = PALETTES[idx % len(PALETTES)]
        name = re.sub(r"[\[\]\*\?/\\:]", "-", sheet.name)[:31]
        ws = wb.create_sheet(name)
        ws.sheet_properties.tabColor = tab
        ws.sheet_view.showGridLines = False
        ws.sheet_view.zoomScale = 110
        df = sheet.df.reset_index(drop=True)
        ncols = max(1, len(df.columns))

        # Title block (rows 1-2), table from row 4.
        ws["A1"] = sheet.title
        ws["A1"].font = Font(name=FONT, size=18, bold=True, color=INK)
        ws["A2"] = L["info"].format(n=f"{len(df):,}".replace(",", " " if lang == "fr" else ","),
                                     date=now.strftime("%d/%m/%Y" if lang == "fr" else "%Y-%m-%d"),
                                     time=now.strftime("%H:%M"))
        ws["A2"].font = Font(name=FONT, size=10, italic=True, color=MUTED)
        ws.row_dimensions[1].height = 30
        ws.row_dimensions[3].height = 8
        header_row = 4

        kinds = [_kind(df[c], sheet.formats.get(c)) for c in df.columns]
        thin = Side(style="thin", color=head_ink)
        for j, col in enumerate(df.columns, start=1):
            cell = ws.cell(row=header_row, column=j, value=str(col))
            cell.font = Font(name=FONT, size=11, bold=True, color=head_ink)
            cell.fill = PatternFill("solid", fgColor=head_fill)
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = Border(bottom=thin)
        ws.row_dimensions[header_row].height = 30

        body_font = Font(name=FONT, size=11, color=INK)
        align = {k: Alignment(vertical="center", horizontal="right" if k in ("int", "dec", "pct") else
                              "center" if k in ("date", "datetime", "time", "id") else "left")
                 for k in set(kinds)}
        for i, row in enumerate(df.itertuples(index=False, name=None), start=header_row + 1):
            for j, (value, kind) in enumerate(zip(row, kinds), start=1):
                v = _cell_value(value)
                if kind == "time" and isinstance(v, datetime):
                    v = v.time()
                if kind == "date" and isinstance(v, datetime):
                    v = v.date()
                if kind == "text" and v is not None and not isinstance(v, (str, int, float, bool, date, time)):
                    v = str(v)
                c = ws.cell(row=i, column=j, value=v)
                c.font = body_font
                c.number_format = number_formats[kind]
                c.alignment = align[kind]

        last_row = header_row + max(len(df), 1)
        if len(df) == 0:  # a table needs at least one data row
            ws.cell(row=last_row, column=1, value=None)
        ref = f"A{header_row}:{get_column_letter(ncols)}{last_row}"
        display = re.sub(r"\W", "_", f"T_{name}", flags=re.ASCII)
        while display in used_names:
            display += "_"
        used_names.add(display)
        table = Table(displayName=display, ref=ref)
        table.tableStyleInfo = TableStyleInfo(name=style, showRowStripes=True, showColumnStripes=False,
                                              showFirstColumn=False, showLastColumn=False)
        ws.add_table(table)
        ws.freeze_panes = ws.cell(row=header_row + 1, column=1)

        for j, (col, kind) in enumerate(zip(df.columns, kinds), start=1):
            if kind in ("date", "time", "id"):
                width = 12
            elif kind == "datetime":
                width = 17
            elif kind in ("int", "dec", "pct"):
                width = 11
            else:
                sample = df[col].head(300).dropna().astype(str).map(len)
                width = min(48, max(12, int(sample.quantile(0.9)) + 3 if len(sample) else 12))
            width = max(width, min(30, len(str(col)) + 4))
            ws.column_dimensions[get_column_letter(j)].width = width
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.stem + ".tmp.xlsx")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def write_exports(engine: Engine, out_dir: Path, tz: str, lang: str = "fr") -> list[Path]:
    """Rewrite the Excel copies of the whole history and library."""
    out_dir.mkdir(parents=True, exist_ok=True)
    raw = stats.load_raw(engine)
    plays = stats.assemble(raw, tz)
    paths = [out_dir / HISTORY_FILE, out_dir / LIBRARY_FILE]
    _atomic_write(paths[0], to_xlsx(history_sheets(plays, lang), lang))
    lib = stats.load_library(engine)
    genres = stats.album_genres(raw.albums, raw.tags, raw.aliases)
    _atomic_write(paths[1], to_xlsx(library_sheets(
        stats.favorite_albums_view(lib, plays, genres), stats.playlists_view(lib, plays),
        stats.playlist_tracks_view(lib, plays), lang), lang))
    log.info("Excel exports written to %s", out_dir)
    return paths
