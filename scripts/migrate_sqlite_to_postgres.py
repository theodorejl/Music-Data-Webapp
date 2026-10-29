"""Copy the local SQLite database into Postgres (Neon). Safe to run several times:
rows that already exist are skipped (no duplicates).

Usage:
    python -m scripts.migrate_sqlite_to_postgres --target "postgresql://user:pass@host/db?sslmode=require"
    (--source defaults to the local SQLite file data/deezer_stats.db)
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

from core.config import DEFAULT_SQLITE, redact
from core.db import get_engine, init_db, insert_ignore
from core.models import (Alias, Album, Artist, ArtistGenre, ArtistRelated, FavoriteAlbum, Play, Playlist, PlaylistTrack, SyncRun,
                         SyncState, Tag, Track, TrackArtist)
from sqlalchemy.orm import Session

# (model, conflict columns, columns to skip because they are auto ids)
TABLES = [
    (Artist, ["id"], []),
    (Album, ["id"], []),
    (Track, ["id"], []),
    (TrackArtist, ["track_id", "artist_id"], []),
    (Play, ["track_id", "played_at"], ["id"]),
    (Tag, ["entity_type", "entity_id", "tag", "source"], ["id"]),
    (Alias, ["kind", "source_key"], ["id"]),
    (SyncRun, ["started_at"], ["id"]),
    (FavoriteAlbum, ["album_id"], []),
    (Playlist, ["id"], []),
    (PlaylistTrack, ["playlist_id", "position"], []),
    (SyncState, ["key"], []),
    (ArtistRelated, ["artist_id", "related_id"], []),
    (ArtistGenre, ["artist_id"], []),
]


def migrate(source_url: str, target_url: str, quiet: bool = False) -> dict[str, tuple[int, int]]:
    src = get_engine(source_url)
    dst = init_db(get_engine(target_url))
    report = {}
    with Session(src) as s_in, Session(dst) as s_out:
        for model, conflict, skip in TABLES:
            cols = [c.name for c in model.__table__.columns if c.name not in skip]
            rows = [dict(r._mapping) for r in s_in.execute(select(*[model.__table__.c[c] for c in cols]))]
            before = s_out.query(model).count()
            insert_ignore(s_out, model, rows, conflict)
            s_out.commit()
            after = s_out.query(model).count()
            report[model.__tablename__] = (len(rows), after - before)
            if not quiet:
                print(f"{model.__tablename__:14} read {len(rows):7}  inserted {after - before:7}")
    return report


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", default=DEFAULT_SQLITE)
    p.add_argument("--target", required=True, help="Postgres URL (Neon connection string)")
    args = p.parse_args()
    if not args.target.startswith(("postgres://", "postgresql")):
        print("--target must be a postgresql:// URL")
        return 1
    try:
        migrate(args.source, args.target)
    except Exception as exc:
        print("Migration failed:", redact(exc))
        return 1
    print("Done. You can run this script again safely.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
