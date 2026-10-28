"""SQLAlchemy engine/session helpers. Works with sqlite:/// and postgresql://."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from core.config import get_settings, normalize_database_url
from core.models import Base


@lru_cache(maxsize=4)
def get_engine(url: str | None = None) -> Engine:
    url = normalize_database_url(url) if url else get_settings().database_url
    parsed = make_url(url)
    if parsed.get_backend_name() == "sqlite":
        if parsed.database and parsed.database != ":memory:":
            Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _):  # better concurrency between app and sync
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA busy_timeout=10000")
            cur.close()

    else:
        # Neon closes idle connections: pre-ping avoids "connection closed" errors.
        engine = create_engine(url, pool_pre_ping=True, pool_recycle=300)
    return engine


def init_db(engine: Engine | None = None) -> Engine:
    engine = engine or get_engine()
    Base.metadata.create_all(engine)
    return engine


@contextmanager
def session_scope(engine: Engine | None = None):
    engine = engine or get_engine()
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def insert_ignore(session: Session, model, rows: Sequence[dict], conflict_cols: Iterable[str]) -> None:
    """INSERT ... ON CONFLICT DO NOTHING, for both SQLite and Postgres."""
    if not rows:
        return
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    cols = list(conflict_cols)
    # Chunk to stay under parameter limits.
    for i in range(0, len(rows), 500):
        stmt = insert(model).values(list(rows[i:i + 500])).on_conflict_do_nothing(index_elements=cols)
        session.execute(stmt)
