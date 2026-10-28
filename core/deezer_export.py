"""Import the listening history from Deezer's personal-data export (GDPR request).

Deezer's live history only keeps the last 100 plays; the personal-data export
(Account > Privacy > "My personal data") is the only source for older plays. It is
an .xlsx workbook; its listening-history sheet has columns such as
"Song Title", "Artist", "ISRC", "Album Title", "Listening Time", "Date".
The exact layout is not documented, so columns are matched by name (EN/FR).

Each row is mapped to a Deezer track id (by ISRC, else by artist + title search),
then stored as a play with its real listening time. Rows that duplicate a play
already collected by the sync (same track within a few minutes) are skipped.
"""

from __future__ import annotations

import bisect
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import insert_ignore
from core.deezer_public import DeezerPublicClient
from core.models import Album, Artist, Play, Track, TrackArtist, utcnow
from core.sync import recompute_estimates

log = logging.getLogger(__name__)

COLUMNS = {
    "title": ["song title", "track title", "titre du morceau", "titre", "title", "song", "track"],
    "artist": ["artist", "artiste", "artist name"],
    "isrc": ["isrc"],
    "album": ["album title", "titre de l'album", "album"],
    "listened": ["listening time", "temps d'écoute", "durée d'écoute", "duration", "durée"],
    "date": ["date", "listening date", "date d'écoute", "timestamp"],
}
DUPLICATE_WINDOW = timedelta(minutes=3)


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9' ]+", " ", text.lower()).strip()


def find_history_sheet(path: Path) -> tuple[str, dict[str, str], pd.DataFrame]:
    """(sheet name, {field: column}, data) for the sheet that looks like a listening history."""
    book = pd.read_excel(path, sheet_name=None)
    best = None
    for name, df in book.items():
        mapping = match_columns(df.columns)
        score = len(mapping) + (2 if "listen" in name.lower() or "ecoute" in _norm(name) else 0)
        if {"title", "date"} <= set(mapping) and (best is None or score > best[0]):
            best = (score, name, mapping, df)
    if best is None:
        sheets = ", ".join(f"{n} {list(df.columns)[:8]}" for n, df in book.items())
        raise ValueError(f"No listening-history sheet found. Sheets: {sheets}")
    return best[1], best[2], best[3]


def match_columns(columns) -> dict[str, str]:
    norm = {_norm(c): c for c in columns}
    mapping = {}
    for field_, names in COLUMNS.items():
        for wanted in names:  # exact name first, then "contains"
            hit = norm.get(_norm(wanted)) or next((c for n, c in norm.items() if _norm(wanted) in n), None)
            if hit is not None and hit not in mapping.values():
                mapping[field_] = hit
                break
    return mapping


@dataclass
class ExportRow:
    played_at: datetime  # naive UTC
    title: str
    artist: str | None
    album: str | None
    isrc: str | None
    listened: int | None
    raw: dict = field(default_factory=dict)


def parse_rows(df: pd.DataFrame, mapping: dict[str, str], tz: str = "UTC") -> list[ExportRow]:
    dates = pd.to_datetime(df[mapping["date"]], errors="coerce")
    if dates.dt.tz is None:
        dates = dates.dt.tz_localize(tz, ambiguous="NaT", nonexistent="shift_forward")
    dates = dates.dt.tz_convert("UTC").dt.tz_localize(None)
    rows = []
    for i, d in enumerate(dates):
        if pd.isna(d):
            continue
        rec = df.iloc[i]
        get = lambda f: (None if f not in mapping or pd.isna(rec[mapping[f]]) else rec[mapping[f]])  # noqa: E731
        listened = get("listened")
        try:
            listened = int(float(listened)) if listened is not None else None
        except (TypeError, ValueError):
            listened = None
        title = get("title")
        if not title:
            continue
        rows.append(ExportRow(
            played_at=d.to_pydatetime().replace(microsecond=0), title=str(title),
            artist=str(get("artist")) if get("artist") is not None else None,
            album=str(get("album")) if get("album") is not None else None,
            isrc=str(get("isrc")).strip().upper() if get("isrc") else None, listened=listened,
            raw={str(k): (None if pd.isna(v) else str(v)) for k, v in rec.items()},
        ))
    return rows


class TrackResolver:
    """Map (ISRC | artist + title) to a Deezer track id, creating metadata rows."""

    def __init__(self, session: Session, client: DeezerPublicClient):
        self.session, self.client = session, client
        self.cache: dict[tuple, int | None] = {}
        self.by_isrc = {isrc: tid for tid, isrc in session.execute(
            select(Track.id, Track.isrc).where(Track.isrc.is_not(None))).all()}

    def resolve(self, row: ExportRow) -> int | None:
        key = ("isrc", row.isrc) if row.isrc else ("search", _norm(row.artist or ""), _norm(row.title))
        if key in self.cache:
            return self.cache[key]
        tid = self.by_isrc.get(row.isrc) if row.isrc else None
        if tid is None:
            data = self.client.get(f"track/isrc:{row.isrc}") if row.isrc else None
            if not data:
                q = f'artist:"{row.artist}" track:"{row.title}"' if row.artist else row.title
                found = (self.client.get(f"search/track?q={requests_quote(q)}&limit=1") or {}).get("data") or []
                data = self.client.track(found[0]["id"]) if found else None
            if data and data.get("id"):
                tid = int(data["id"])
                self._store(data)
        self.cache[key] = tid
        return tid

    def _store(self, data: dict) -> None:
        album, artist = data.get("album") or {}, data.get("artist") or {}
        contributors = data.get("contributors") or ([artist] if artist else [])
        insert_ignore(self.session, Artist, [{
            "id": a["id"], "name": a.get("name") or f"#{a['id']}", "picture_small": a.get("picture_small"),
            "picture_medium": a.get("picture_medium"), "picture_big": a.get("picture_big"),
            "picture_xl": a.get("picture_xl")} for a in contributors if a.get("id")], ["id"])
        if album.get("id"):
            insert_ignore(self.session, Album, [{
                "id": album["id"], "title": album.get("title") or "?", "artist_id": artist.get("id"),
                "cover_small": album.get("cover_small"), "cover_medium": album.get("cover_medium"),
                "cover_big": album.get("cover_big"), "cover_xl": album.get("cover_xl")}], ["id"])
        insert_ignore(self.session, Track, [{
            "id": int(data["id"]), "title": data.get("title_short") or data.get("title") or "?",
            "version": (data.get("title_version") or "").strip() or None, "duration": data.get("duration"),
            "isrc": data.get("isrc"), "album_id": album.get("id"), "artist_id": artist.get("id"),
            "preview_url": data.get("preview"), "explicit": bool(data.get("explicit_lyrics")),
            "fetched_at": utcnow()}], ["id"])
        insert_ignore(self.session, TrackArtist, [{
            "track_id": int(data["id"]), "artist_id": a["id"], "role": "main" if i == 0 else "featuring",
            "position": i} for i, a in enumerate(contributors) if a.get("id")], ["track_id", "artist_id"])
        if data.get("isrc"):
            self.by_isrc[data["isrc"]] = int(data["id"])


def requests_quote(q: str) -> str:
    from urllib.parse import quote

    return quote(q, safe="")


@dataclass
class ImportReport:
    rows: int = 0
    inserted: int = 0
    duplicates: int = 0
    unresolved: int = 0
    unresolved_examples: list[str] = field(default_factory=list)


def import_rows(session: Session, rows: list[ExportRow], client: DeezerPublicClient | None = None,
                dry_run: bool = False, progress=None) -> ImportReport:
    report = ImportReport(rows=len(rows))
    resolver = TrackResolver(session, client or DeezerPublicClient())
    existing: dict[int, list[datetime]] = {}
    for tid, ts in session.execute(select(Play.track_id, Play.played_at)).all():
        existing.setdefault(tid, []).append(ts)
    for v in existing.values():
        v.sort()

    new = []
    for i, row in enumerate(sorted(rows, key=lambda r: r.played_at)):
        if progress and i % 200 == 0:
            progress(i, len(rows))
        tid = resolver.resolve(row)
        if tid is None:
            report.unresolved += 1
            if len(report.unresolved_examples) < 10:
                report.unresolved_examples.append(f"{row.artist} — {row.title}")
            continue
        times = existing.setdefault(tid, [])
        j = bisect.bisect_left(times, row.played_at - DUPLICATE_WINDOW)
        if j < len(times) and times[j] <= row.played_at + DUPLICATE_WINDOW:
            report.duplicates += 1
            continue
        bisect.insort(times, row.played_at)
        new.append({"track_id": tid, "played_at": row.played_at, "listened_seconds": row.listened,
                    "duration_is_estimated": row.listened is None, "source": "deezer_export",
                    "raw_json": row.raw, "inserted_at": utcnow()})
    report.inserted = len(new)
    if not dry_run and new:
        insert_ignore(session, Play, new, ["track_id", "played_at"])
        recompute_estimates(session, min(r["played_at"] for r in new))
    return report
