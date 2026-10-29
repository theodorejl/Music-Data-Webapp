"""Database tables. All timestamps are naive datetimes in UTC."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    from datetime import timezone

    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


class Play(Base):
    __tablename__ = "plays"
    __table_args__ = (UniqueConstraint("track_id", "played_at", name="uq_play_track_time"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    track_id: Mapped[int] = mapped_column(BigInteger, index=True)
    played_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    listened_seconds: Mapped[int | None] = mapped_column(Integer)
    duration_is_estimated: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[str] = mapped_column(String(32), default="deezer_gw")
    raw_json: Mapped[dict | None] = mapped_column(JSON)
    inserted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Track(Base):
    __tablename__ = "tracks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    title: Mapped[str] = mapped_column(String(500))
    version: Mapped[str | None] = mapped_column(String(500))
    duration: Mapped[int | None] = mapped_column(Integer)
    isrc: Mapped[str | None] = mapped_column(String(32), index=True)
    album_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    artist_id: Mapped[int | None] = mapped_column(BigInteger, index=True)  # principal artist
    preview_url: Mapped[str | None] = mapped_column(Text)
    explicit: Mapped[bool | None] = mapped_column(Boolean)
    raw_json: Mapped[dict | None] = mapped_column(JSON)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime)  # public API enrichment done
    mb_checked_at: Mapped[datetime | None] = mapped_column(DateTime)  # MusicBrainz lookup done


class TrackArtist(Base):
    __tablename__ = "track_artists"

    track_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    artist_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    role: Mapped[str] = mapped_column(String(16), default="main")  # main | featuring
    position: Mapped[int] = mapped_column(Integer, default=0)


class Album(Base):
    __tablename__ = "albums"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    title: Mapped[str] = mapped_column(String(500))
    artist_id: Mapped[int | None] = mapped_column(BigInteger)
    release_date: Mapped[str | None] = mapped_column(String(10))
    label: Mapped[str | None] = mapped_column(String(300))
    record_type: Mapped[str | None] = mapped_column(String(32))
    cover_small: Mapped[str | None] = mapped_column(Text)
    cover_medium: Mapped[str | None] = mapped_column(Text)
    cover_big: Mapped[str | None] = mapped_column(Text)
    cover_xl: Mapped[str | None] = mapped_column(Text)
    deezer_genres: Mapped[list | None] = mapped_column(JSON)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime)
    mb_checked_at: Mapped[datetime | None] = mapped_column(DateTime)


class Artist(Base):
    __tablename__ = "artists"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(500))
    picture_small: Mapped[str | None] = mapped_column(Text)
    picture_medium: Mapped[str | None] = mapped_column(Text)
    picture_big: Mapped[str | None] = mapped_column(Text)
    picture_xl: Mapped[str | None] = mapped_column(Text)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime)
    mb_checked_at: Mapped[datetime | None] = mapped_column(DateTime)


class Tag(Base):
    """Genres / tags attached to a track, album or artist (Deezer ids)."""

    __tablename__ = "tags"
    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", "tag", "source", name="uq_tag"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(16))  # track | album | artist
    entity_id: Mapped[int] = mapped_column(BigInteger, index=True)
    tag: Mapped[str] = mapped_column(String(200))
    count: Mapped[int | None] = mapped_column(Integer)  # MusicBrainz votes
    source: Mapped[str] = mapped_column(String(32))  # mb_genre | mb_tag | wikidata | lastfm | discogs | discogs_genre
    # Labels of an artist are stored the same way, with entity_type "artist_label".


class ArtistInfo(Base):
    """An artist's identifiers in other music databases, and when each database was asked
    (so each one is asked once). Its genres and labels go to `tags`."""

    __tablename__ = "artist_info"

    artist_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    mbid: Mapped[str | None] = mapped_column(String(36))  # MusicBrainz
    discogs_id: Mapped[int | None] = mapped_column(BigInteger)
    wikidata: Mapped[str | None] = mapped_column(String(20))  # e.g. Q185828
    checked: Mapped[dict | None] = mapped_column(JSON)  # source -> date asked (ISO)


class Alias(Base):
    """Manual corrections, applied when computing stats (raw data untouched).

    kind           source_key                      target
    merge_artist   artist id to merge              artist id to keep
    merge_album    album id to merge               album id to keep
    album_genre    album id                        forced genre
    rename_genre   genre name                      new genre name
    hide_play      "<track_id>@<ISO played_at>"    ""
    """

    __tablename__ = "aliases"
    __table_args__ = (UniqueConstraint("kind", "source_key", name="uq_alias"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(32))
    source_key: Mapped[str] = mapped_column(String(200))
    target: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, unique=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    fetched: Mapped[int] = mapped_column(Integer, default=0)
    inserted: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="running")  # running | ok | error
    error: Mapped[str | None] = mapped_column(Text)
    gap_warning: Mapped[str | None] = mapped_column(Text)
    gap_start: Mapped[datetime | None] = mapped_column(DateTime)
    gap_end: Mapped[datetime | None] = mapped_column(DateTime)
    duration_s: Mapped[float | None] = mapped_column(Float)


class FavoriteAlbum(Base):
    """Snapshot of the profile's favorite albums (replaced at each library refresh)."""

    __tablename__ = "favorite_albums"

    album_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    profile_id: Mapped[int | None] = mapped_column(BigInteger)
    added_at: Mapped[datetime | None] = mapped_column(DateTime)
    raw_json: Mapped[dict | None] = mapped_column(JSON)


class Playlist(Base):
    """Playlists of the profile: its own and the ones it added to favorites."""

    __tablename__ = "playlists"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    profile_id: Mapped[int | None] = mapped_column(BigInteger)
    title: Mapped[str] = mapped_column(String(500))
    creator_id: Mapped[int | None] = mapped_column(BigInteger)
    creator_name: Mapped[str | None] = mapped_column(String(300))
    is_own: Mapped[bool] = mapped_column(Boolean, default=False)
    nb_songs: Mapped[int | None] = mapped_column(Integer)
    duration: Mapped[int | None] = mapped_column(Integer)  # seconds
    picture: Mapped[str | None] = mapped_column(Text)
    added_at: Mapped[datetime | None] = mapped_column(DateTime)  # favorite / creation date
    modified_at: Mapped[datetime | None] = mapped_column(DateTime)
    checksum: Mapped[str | None] = mapped_column(String(64))  # tracks reloaded when it changes
    tracks_fetched_at: Mapped[datetime | None] = mapped_column(DateTime)
    raw_json: Mapped[dict | None] = mapped_column(JSON)


class PlaylistTrack(Base):
    __tablename__ = "playlist_tracks"

    playlist_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    position: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    track_id: Mapped[int] = mapped_column(BigInteger, index=True)
    added_at: Mapped[datetime | None] = mapped_column(DateTime)


class SyncState(Base):
    """Small key/value store (e.g. last library refresh)."""

    __tablename__ = "sync_state"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text)


def play_key(track_id: int, played_at: datetime) -> str:
    """Stable identifier of a play, used by `hide_play` aliases (portable across DBs)."""
    return f"{track_id}@{played_at.replace(microsecond=0).isoformat()}"
