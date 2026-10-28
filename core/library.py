"""Favorite albums and playlists of the Deezer profile.

Refreshed by the sync script at most every LIBRARY_REFRESH_HOURS. Playlist tracks
are reloaded only when a playlist is new, its track count changed, or its tracks
are older than PLAYLIST_MAX_AGE; work is time-boxed and resumes on the next run.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from core.config import redact
from core.db import init_db, insert_ignore
from core.deezer_gw import DeezerGatewayClient, parse_song_metadata
from core.deezer_public import cover_url
from core.models import Album, Artist, FavoriteAlbum, Playlist, PlaylistTrack, SyncState, utcnow
from core.sync import _upsert_minimal_metadata

log = logging.getLogger(__name__)

LIBRARY_REFRESH_HOURS = 6
PLAYLIST_MAX_AGE = timedelta(days=7)


def _dt(value) -> datetime | None:
    try:
        return datetime.strptime(str(value)[:19], "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return None


def _int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _release_date(value) -> str | None:
    value = str(value or "")[:10]
    return value if len(value) == 10 and not value.startswith("0000") else None


def playlist_picture_url(md5: str | None, picture_type: str | None, size: int = 250) -> str | None:
    if not md5:
        return None
    kind = picture_type or "playlist"
    return f"https://cdn-images.dzcdn.net/images/{kind}/{md5}/{size}x{size}-000000-80-0-0.jpg"


def store_favorite_albums(session: Session, items: list[dict], profile_id: int | None) -> int:
    artists, albums, favorites = {}, {}, []
    for it in items:
        alb_id, art_id = _int(it.get("ALB_ID")), _int(it.get("ART_ID"))
        if not alb_id:
            continue
        if art_id:
            artists[art_id] = {"id": art_id, "name": it.get("ART_NAME") or f"#{art_id}",
                               "picture_small": None, "picture_medium": None, "picture_big": None, "picture_xl": None}
        pic = it.get("ALB_PICTURE")
        albums[alb_id] = {
            "id": alb_id, "title": it.get("ALB_TITLE") or f"#{alb_id}", "artist_id": art_id,
            "release_date": _release_date(it.get("PHYSICAL_RELEASE_DATE")),
            "cover_small": cover_url(pic, 56), "cover_medium": cover_url(pic, 250),
            "cover_big": cover_url(pic, 500), "cover_xl": cover_url(pic, 1000),
        }
        favorites.append({"album_id": alb_id, "profile_id": profile_id,
                          "added_at": _dt(it.get("DATE_FAVORITE")), "raw_json": it})
    insert_ignore(session, Artist, list(artists.values()), ["id"])
    insert_ignore(session, Album, list(albums.values()), ["id"])
    # Albums created earlier from a play may lack the release date.
    for alb in albums.values():
        if alb["release_date"]:
            session.execute(update(Album).where(Album.id == alb["id"], Album.release_date.is_(None))
                            .values(release_date=alb["release_date"]))
    session.execute(delete(FavoriteAlbum))  # snapshot: albums removed from favorites disappear
    insert_ignore(session, FavoriteAlbum, favorites, ["album_id"])
    return len(favorites)


def store_playlist_list(session: Session, items: list[dict], profile_id: int | None,
                        profile_name: str | None = None) -> list[int]:
    """Upsert playlists; return ids whose tracks must be (re)loaded."""
    existing = {p.id: p for p in session.scalars(select(Playlist)).all()}
    seen, to_fetch = set(), []
    now = utcnow()
    for it in items:
        pid = _int(it.get("PLAYLIST_ID"))
        if not pid:
            continue
        seen.add(pid)
        creator = _int(it.get("PARENT_USER_ID"))
        is_own = creator is not None and creator == profile_id
        values = dict(
            profile_id=profile_id, title=it.get("TITLE") or f"#{pid}", creator_id=creator,
            # Deezer leaves the creator name empty on the profile's own playlists.
            creator_name=it.get("PARENT_USERNAME") or (profile_name if is_own else None), is_own=is_own, nb_songs=_int(it.get("NB_SONG")),
            picture=playlist_picture_url(it.get("PLAYLIST_PICTURE"), it.get("PICTURE_TYPE")),
            added_at=_dt(it.get("DATE_ADD") if is_own else (it.get("DATE_FAVORITE") or it.get("DATE_ADD"))),
            raw_json=it,
        )
        old = existing.get(pid)
        if old is None:
            session.add(Playlist(id=pid, **values))
            to_fetch.append(pid)
            continue
        changed = old.nb_songs != values["nb_songs"]
        for key, value in values.items():
            setattr(old, key, value)
        if changed or old.tracks_fetched_at is None or now - old.tracks_fetched_at > PLAYLIST_MAX_AGE:
            to_fetch.append(pid)
    gone = set(existing) - seen
    if gone:
        session.execute(delete(PlaylistTrack).where(PlaylistTrack.playlist_id.in_(gone)))
        session.execute(delete(Playlist).where(Playlist.id.in_(gone)))
    return to_fetch


def store_playlist_tracks(session: Session, playlist_id: int, info: dict, songs: list[dict]) -> int:
    records, rows = [], []
    for pos, song in enumerate(songs):
        try:
            rec = parse_song_metadata(song)
        except Exception:
            continue
        records.append(rec)
        rows.append({"playlist_id": playlist_id, "position": pos, "track_id": rec.track_id,
                     "added_at": _dt(song.get("DATE_ADD"))})
    _upsert_minimal_metadata(session, records)
    session.execute(delete(PlaylistTrack).where(PlaylistTrack.playlist_id == playlist_id))
    insert_ignore(session, PlaylistTrack, rows, ["playlist_id", "position"])
    pl = session.get(Playlist, playlist_id)
    if pl is not None:
        pl.tracks_fetched_at = utcnow()
        pl.checksum = info.get("CHECKSUM") or pl.checksum
        pl.duration = _int(info.get("DURATION")) or pl.duration
        pl.modified_at = _dt(info.get("DATE_MOD")) or pl.modified_at
        pl.nb_songs = len(rows)
    return len(rows)


def _get_state(session: Session, key: str) -> str | None:
    row = session.get(SyncState, key)
    return row.value if row else None


def _set_state(session: Session, key: str, value: str) -> None:
    row = session.get(SyncState, key)
    if row:
        row.value = value
    else:
        session.add(SyncState(key=key, value=value))


def refresh_library(engine: Engine, client: DeezerGatewayClient, force: bool = False,
                    budget_seconds: float = 120) -> dict:
    """Best effort: never raises (the history sync must not depend on it)."""
    init_db(engine)
    Session_ = sessionmaker(bind=engine, expire_on_commit=False)
    report = {"albums": 0, "playlists": 0, "playlists_loaded": 0, "skipped": False}
    deadline = time.monotonic() + budget_seconds
    try:
        with Session_() as session:
            last = _dt(_get_state(session, "library_refreshed_at"))
            pending = session.scalar(select(Playlist.id).where(Playlist.tracks_fetched_at.is_(None)).limit(1))
            if not force and last and utcnow() - last < timedelta(hours=LIBRARY_REFRESH_HOURS) and pending is None:
                report["skipped"] = True
                return report

            client.ensure_profile()
            report["albums"] = store_favorite_albums(session, client.get_favorite_albums(), client.user_id)
            to_fetch = store_playlist_list(session, client.get_playlists(), client.user_id, client.profile_name)
            report["playlists"] = session.query(Playlist).count()
            session.commit()

            # Never-loaded playlists first, then the oldest ones.
            order = {p.id: p.tracks_fetched_at or datetime.min for p in session.scalars(select(Playlist)).all()}
            for pid in sorted(to_fetch, key=lambda i: order.get(i, datetime.min)):
                if time.monotonic() > deadline:
                    log.info("Library: time budget reached, remaining playlists next run")
                    break
                try:
                    info, songs = client.get_playlist(pid)
                    store_playlist_tracks(session, pid, info, songs)
                    session.commit()
                    report["playlists_loaded"] += 1
                except Exception as exc:
                    session.rollback()
                    log.warning("Playlist %s not loaded: %s", pid, redact(exc))
            else:
                _set_state(session, "library_refreshed_at", utcnow().strftime("%Y-%m-%d %H:%M:%S"))
                session.commit()
    except Exception as exc:
        log.warning("Library refresh failed (will retry next run): %s", redact(exc))
    log.info("Library: %s", report)
    return report
