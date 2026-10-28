"""Fetch history -> dedupe -> store -> enrich.

Collection never depends on enrichment: enrichment errors are logged and
swallowed, and it resumes on the next run (rows carry fetched_at/mb_checked_at).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from core.config import get_settings, redact
from core.db import init_db, insert_ignore
from core.deezer_gw import HistorySource, PlayRecord
from core.deezer_public import DeezerPublicClient, artist_picture_url, cover_url
from core.models import Album, Artist, FavoriteAlbum, Play, SyncRun, Tag, Track, TrackArtist, utcnow
from core.musicbrainz import MusicBrainzClient, extract_tags, pick_release_group

log = logging.getLogger(__name__)


@dataclass
class SyncResult:
    fetched: int
    inserted: int
    gap_start: datetime | None = None
    gap_end: datetime | None = None

    @property
    def gap_warning(self) -> str | None:
        if self.gap_start and self.gap_end:
            return f"possible gap between {self.gap_start:%Y-%m-%d %H:%M} and {self.gap_end:%Y-%m-%d %H:%M} UTC"
        return None


# --- duration estimation (pure) ----------------------------------------------

def estimate_listened(rows: list[tuple[datetime, int | None]]) -> list[int | None]:
    """rows: (played_at, track_duration) sorted by played_at ascending.

    Estimated listened time = min(track duration, next play start - this play start).
    The last play (no next play yet) gets the full track duration.
    """
    out: list[int | None] = []
    for i, (played_at, duration) in enumerate(rows):
        gap = None
        if i + 1 < len(rows):
            gap = int((rows[i + 1][0] - played_at).total_seconds())
        if duration is None:
            out.append(gap if gap is not None and gap < 900 else None)
        elif gap is None:
            out.append(int(duration))
        else:
            out.append(max(0, min(int(duration), gap)))
    return out


def recompute_estimates(session: Session, since: datetime) -> int:
    """Re-estimate durations of plays from `since` (and the play just before)."""
    rows = session.execute(
        select(Play.id, Play.played_at, Play.listened_seconds, Play.duration_is_estimated, Track.duration)
        .join(Track, Track.id == Play.track_id, isouter=True)
        .where(Play.played_at >= since - timedelta(days=1))
        .order_by(Play.played_at, Play.id)
    ).all()
    if not rows:
        return 0
    estimates = estimate_listened([(r.played_at, r.duration) for r in rows])
    changed = 0
    for r, est in zip(rows, estimates):
        if r.duration_is_estimated and r.listened_seconds != est:
            session.execute(update(Play).where(Play.id == r.id).values(listened_seconds=est))
            changed += 1
    return changed


# --- storage -------------------------------------------------------------------

def _upsert_minimal_metadata(session: Session, records: list[PlayRecord]) -> None:
    """Create bare track/album/artist rows from the history payload so the app
    can show something before enrichment. Existing rows are never overwritten."""
    tracks, albums, artists, links = {}, {}, {}, {}
    for r in records:
        tracks[r.track_id] = {
            "id": r.track_id, "title": r.title or f"#{r.track_id}", "version": r.version,
            "duration": r.duration, "isrc": r.isrc, "album_id": r.album_id,
            "artist_id": r.artist_id, "explicit": r.explicit,
        }
        if r.album_id:
            albums[r.album_id] = {
                "id": r.album_id, "title": r.album_title or f"#{r.album_id}", "artist_id": r.artist_id,
                "cover_small": cover_url(r.album_picture, 56), "cover_medium": cover_url(r.album_picture, 250),
                "cover_big": cover_url(r.album_picture, 500), "cover_xl": cover_url(r.album_picture, 1000),
            }
        artist_list = r.artists or (
            [{"id": r.artist_id, "name": r.artist_name, "role": "main", "picture": None}] if r.artist_id else []
        )
        for pos, a in enumerate(artist_list):
            if not a.get("id"):
                continue
            pic = a.get("picture")
            artists.setdefault(a["id"], {
                "id": a["id"], "name": a.get("name") or f"#{a['id']}",
                "picture_small": artist_picture_url(pic, 56), "picture_medium": artist_picture_url(pic, 250),
                "picture_big": artist_picture_url(pic, 500), "picture_xl": artist_picture_url(pic, 1000),
            })
            links[(r.track_id, a["id"])] = {
                "track_id": r.track_id, "artist_id": a["id"], "role": a.get("role", "main"), "position": pos,
            }
    insert_ignore(session, Artist, list(artists.values()), ["id"])
    insert_ignore(session, Album, list(albums.values()), ["id"])
    insert_ignore(session, Track, list(tracks.values()), ["id"])
    insert_ignore(session, TrackArtist, list(links.values()), ["track_id", "artist_id"])


def store_plays(session: Session, records: list[PlayRecord], window: int) -> SyncResult:
    """Insert new plays (dedup on track_id + played_at) and detect possible gaps."""
    result = SyncResult(fetched=len(records), inserted=0)
    if not records:
        return result

    last_stored = session.scalar(select(Play.played_at).order_by(Play.played_at.desc()).limit(1))
    oldest_fetched = min(r.played_at for r in records)
    newest_fetched = max(r.played_at for r in records)

    _upsert_minimal_metadata(session, records)

    existing = set(session.execute(
        select(Play.track_id, Play.played_at).where(
            and_(Play.played_at >= oldest_fetched, Play.played_at <= newest_fetched)
        )
    ).all())
    new_rows, seen = [], set()
    for r in records:
        key = (r.track_id, r.played_at)
        if key in existing or key in seen:
            continue
        seen.add(key)
        new_rows.append({
            "track_id": r.track_id, "played_at": r.played_at,
            "listened_seconds": r.listened_seconds,
            "duration_is_estimated": r.listened_seconds is None,
            "source": r.source, "raw_json": r.raw, "inserted_at": utcnow(),
        })
    insert_ignore(session, Play, new_rows, ["track_id", "played_at"])
    result.inserted = len(new_rows)

    # The window is full and does not reach back to what we already have:
    # plays in between may have been lost.
    if last_stored is not None and len(records) >= window and oldest_fetched > last_stored:
        result.gap_start, result.gap_end = last_stored, oldest_fetched
        log.warning("Possible gap: %s", result.gap_warning)

    if new_rows:
        recompute_estimates(session, min(r["played_at"] for r in new_rows))
    return result


# --- enrichment ------------------------------------------------------------------

def _clean_public(data: dict) -> dict:
    return {k: v for k, v in data.items() if k not in ("available_countries", "track_token", "md5_image")}


def enrich_public(session: Session, client: DeezerPublicClient, deadline: float) -> int:
    """Fill tracks/albums/artists from api.deezer.com (each object fetched once)."""
    done = 0
    now = utcnow
    # Only what the stats need: played tracks, their albums/artists, and favorite albums.
    # (Tracks that only appear in playlists keep the metadata given by the playlist.)
    played = select(Play.track_id).distinct()
    played_albums = select(Track.album_id).where(Track.id.in_(played))
    played_artists = select(Track.artist_id).where(Track.id.in_(played))
    favorite_albums = select(FavoriteAlbum.album_id)
    favorite_artists = select(Album.artist_id).where(Album.id.in_(favorite_albums))
    for track in session.scalars(select(Track).where(Track.fetched_at.is_(None), Track.id.in_(played))
                                 .limit(500)).all():
        if time.monotonic() > deadline:
            return done
        data = client.track(track.id)
        if data:
            track.title = data.get("title_short") or data.get("title") or track.title
            track.version = (data.get("title_version") or "").strip() or track.version
            track.duration = data.get("duration") or track.duration
            track.isrc = data.get("isrc") or track.isrc
            track.preview_url = data.get("preview") or None
            track.explicit = bool(data.get("explicit_lyrics"))
            track.album_id = (data.get("album") or {}).get("id") or track.album_id
            track.artist_id = (data.get("artist") or {}).get("id") or track.artist_id
            track.raw_json = _clean_public(data)
            contributors = data.get("contributors") or ([data["artist"]] if data.get("artist") else [])
            artist_rows, link_rows = [], []
            for pos, c in enumerate(contributors):
                artist_rows.append({
                    "id": c["id"], "name": c.get("name") or f"#{c['id']}",
                    "picture_small": c.get("picture_small"), "picture_medium": c.get("picture_medium"),
                    "picture_big": c.get("picture_big"), "picture_xl": c.get("picture_xl"),
                })
                link_rows.append({"track_id": track.id, "artist_id": c["id"],
                                  "role": "main" if pos == 0 else "featuring", "position": pos})
            insert_ignore(session, Artist, artist_rows, ["id"])
            session.query(TrackArtist).filter(TrackArtist.track_id == track.id).delete()
            insert_ignore(session, TrackArtist, link_rows, ["track_id", "artist_id"])
            album = (data.get("album") or {})
            if album.get("id"):
                insert_ignore(session, Album, [{
                    "id": album["id"], "title": album.get("title") or "?", "artist_id": track.artist_id,
                    "cover_small": album.get("cover_small"), "cover_medium": album.get("cover_medium"),
                    "cover_big": album.get("cover_big"), "cover_xl": album.get("cover_xl"),
                }], ["id"])
        track.fetched_at = now()
        session.commit()
        done += 1

    for album in session.scalars(select(Album).where(
            Album.fetched_at.is_(None), Album.id.in_(played_albums) | Album.id.in_(favorite_albums)).limit(500)).all():
        if time.monotonic() > deadline:
            return done
        data = client.album(album.id)
        if data:
            album.title = data.get("title") or album.title
            album.release_date = data.get("release_date")
            album.label = data.get("label")
            album.record_type = data.get("record_type")
            album.artist_id = (data.get("artist") or {}).get("id") or album.artist_id
            for size in ("small", "medium", "big", "xl"):
                setattr(album, f"cover_{size}", data.get(f"cover_{size}") or getattr(album, f"cover_{size}"))
            album.deezer_genres = [g["name"] for g in (data.get("genres") or {}).get("data", [])]
        album.fetched_at = now()
        session.commit()
        done += 1

    for artist in session.scalars(select(Artist).where(
            Artist.fetched_at.is_(None), Artist.id.in_(played_artists) | Artist.id.in_(favorite_artists)).limit(500)).all():
        if time.monotonic() > deadline:
            return done
        data = client.artist(artist.id)
        if data:
            artist.name = data.get("name") or artist.name
            for size in ("small", "medium", "big", "xl"):
                setattr(artist, f"picture_{size}", data.get(f"picture_{size}") or getattr(artist, f"picture_{size}"))
        artist.fetched_at = now()
        session.commit()
        done += 1
    return done


def _store_tags(session: Session, entity_type: str, entity_id: int, tags) -> None:
    rows = [{"entity_type": entity_type, "entity_id": entity_id, "tag": t[:200], "count": c, "source": s}
            for t, c, s in tags]
    insert_ignore(session, Tag, rows, ["entity_type", "entity_id", "tag", "source"])


def enrich_musicbrainz(session: Session, client: MusicBrainzClient, deadline: float) -> int:
    done = 0
    tracks = session.scalars(
        select(Track).where(Track.mb_checked_at.is_(None), Track.id.in_(select(Play.track_id).distinct()))
        .order_by(Track.id).limit(300)
    ).all()
    for track in tracks:
        if time.monotonic() > deadline:
            break
        try:
            rec_id = client.recording_id_by_isrc(track.isrc) if track.isrc else None
            recording = client.recording(rec_id) if rec_id else None
            if recording:
                _store_tags(session, "track", track.id, extract_tags(recording))
                album = session.get(Album, track.album_id) if track.album_id else None
                if album and album.mb_checked_at is None:
                    rg = pick_release_group(recording, album.title)
                    if rg and rg.get("id"):
                        _store_tags(session, "album", album.id, extract_tags(client.release_group(rg["id"])))
                    album.mb_checked_at = utcnow()
                artist = session.get(Artist, track.artist_id) if track.artist_id else None
                credits = recording.get("artist-credit") or []
                if artist and artist.mb_checked_at is None and credits:
                    mb_artist = client.artist(credits[0]["artist"]["id"])
                    _store_tags(session, "artist", artist.id, extract_tags(mb_artist))
                    artist.mb_checked_at = utcnow()
            track.mb_checked_at = utcnow()
            session.commit()
            done += 1
        except Exception as exc:
            session.rollback()
            log.warning("MusicBrainz enrichment failed for track %s: %s", track.id, redact(exc))
    return done


def run_enrichment(engine: Engine, budget_seconds: float = 120,
                   public: DeezerPublicClient | None = None, mb: MusicBrainzClient | None = None) -> None:
    """Best effort; never raises."""
    deadline = time.monotonic() + budget_seconds
    Session_ = sessionmaker(bind=engine, expire_on_commit=False)
    for name, fn, client_factory, given in (
        ("public", enrich_public, DeezerPublicClient, public),
        ("musicbrainz", enrich_musicbrainz, MusicBrainzClient, mb),
    ):
        try:
            with Session_() as session:
                n = fn(session, given or client_factory(), deadline)
                session.commit()
            log.info("Enrichment %s: %d objects processed", name, n)
        except Exception as exc:
            log.warning("Enrichment %s failed (will resume next run): %s", name, redact(exc))


# --- orchestration -----------------------------------------------------------------

def run_sync(engine: Engine, source: HistorySource, enrich: bool = True,
             enrich_budget: float = 120, window: int | None = None) -> SyncResult:
    """Run one sync. Raises if fetching/storing fails (so CI jobs fail visibly)."""
    init_db(engine)
    window = window or get_settings().history_window
    Session_ = sessionmaker(bind=engine, expire_on_commit=False)
    started = datetime.now(timezone.utc).replace(tzinfo=None)
    t0 = time.monotonic()
    with Session_() as session:
        run = SyncRun(started_at=started, status="running")
        session.add(run)
        session.commit()
        run_id = run.id

    try:
        records = source.fetch_recent()
        with Session_() as session:
            result = store_plays(session, records, window)
            session.commit()
    except Exception as exc:
        with Session_() as session:
            run = session.get(SyncRun, run_id)
            run.status, run.error = "error", redact(f"{type(exc).__name__}: {exc}")[:2000]
            run.finished_at, run.duration_s = utcnow(), time.monotonic() - t0
            session.commit()
        raise

    with Session_() as session:
        run = session.get(SyncRun, run_id)
        run.fetched, run.inserted, run.status = result.fetched, result.inserted, "ok"
        run.gap_warning, run.gap_start, run.gap_end = result.gap_warning, result.gap_start, result.gap_end
        run.finished_at, run.duration_s = utcnow(), time.monotonic() - t0
        session.commit()
    log.info("Fetched %d plays, inserted %d new", result.fetched, result.inserted)

    if enrich:
        run_enrichment(engine, enrich_budget)
    return result
