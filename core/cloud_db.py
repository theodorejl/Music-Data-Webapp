"""The SQLite database stored in the GitHub repository, on its own branch.

The branch `data` holds a single file, `deezer_stats.db.gz`, in a single commit that is
replaced (force-pushed) at every publish: the repository never grows with history,
and `main` stays code only.

- GitHub Actions: pull -> sync -> publish, every 30 minutes.
- Your computer ("Lancer l'app", "Actualiser"): pull (keeping rows that exist only
  locally, such as admin corrections) -> sync -> publish.
- Streamlit Cloud: downloads the file read-only from raw.githubusercontent.com.
"""

from __future__ import annotations

import gzip
import logging
import os
import sqlite3
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

log = logging.getLogger(__name__)

BRANCH = "data"
FILE = "deezer_stats.db.gz"


def _git(repo: Path, *args: str, input_: bytes | None = None, env: dict | None = None) -> str:
    res = subprocess.run(["git", *args], cwd=repo, input=input_, capture_output=True,
                         env={**os.environ, **(env or {})}, timeout=180)
    if res.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[:2])} failed: {res.stderr.decode(errors='replace').strip()[:300]}")
    return res.stdout.decode().strip()


def _snapshot(db_path: Path, dest: Path) -> None:
    """Consistent copy of a live SQLite database (WAL included)."""
    src = sqlite3.connect(db_path)
    try:
        out = sqlite3.connect(dest)
        with out:
            src.backup(out)
        out.close()
    finally:
        src.close()


def pack(db_path: Path) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "snapshot.db"
        _snapshot(db_path, copy)
        con = sqlite3.connect(copy)
        con.execute("VACUUM")
        con.close()
        return gzip.compress(copy.read_bytes(), compresslevel=9, mtime=0)


def unpack(data: bytes, dest: Path) -> None:
    dest.write_bytes(gzip.decompress(data))


def fetch_remote(repo: Path, remote: str = "origin") -> bytes | None:
    """The published file, or None when the data branch does not exist yet."""
    if not _git(repo, "ls-remote", "--heads", remote, BRANCH):
        return None
    _git(repo, "fetch", "--depth", "1", remote, f"+refs/heads/{BRANCH}:refs/remotes/{remote}/{BRANCH}")
    res = subprocess.run(["git", "show", f"{remote}/{BRANCH}:{FILE}"], cwd=repo, capture_output=True, timeout=120)
    return res.stdout if res.returncode == 0 else None


# Tables that are snapshots of Deezer (replaced as a whole by the published copy).
SNAPSHOT_TABLES = ("favorite_albums", "playlists", "playlist_tracks", "sync_state", "artist_genre")


def merge_into(published: Path, local: Path, local_wins: bool = False) -> None:
    """Merge the published database into the local one, in place (safe while the app has it
    open): published rows win, rows that exist only locally (admin corrections, plays from a
    refresh not yet published) are kept, snapshot tables are replaced.
    With local_wins (catching up just before a publish), only the rows we lack are added.
    A table the published copy lacks (published by older code) is left as it is locally."""
    from sqlalchemy import create_engine, delete, inspect, select
    from sqlalchemy.dialects.sqlite import insert

    from core.db import init_db
    from scripts.migrate_sqlite_to_postgres import TABLES

    src = create_engine(f"sqlite:///{published}")
    dst = init_db(create_engine(f"sqlite:///{local}", connect_args={"timeout": 30}))
    try:
        with src.connect() as s_in, dst.begin() as s_out:
            published_tables = set(inspect(s_in).get_table_names())
            for model, conflict, skip in TABLES:
                table = model.__table__
                cols = [c.name for c in table.columns if c.name not in skip]
                if table.name not in published_tables or (local_wins and table.name in SNAPSHOT_TABLES):
                    continue
                rows = [dict(r._mapping) for r in s_in.execute(select(*[table.c[c] for c in cols]))]
                if table.name in SNAPSHOT_TABLES:
                    s_out.execute(delete(table))
                for i in range(0, len(rows), 400):
                    stmt = insert(table).values(rows[i:i + 400])
                    update = {} if local_wins else {c: stmt.excluded[c] for c in cols if c not in conflict}
                    stmt = (stmt.on_conflict_do_update(index_elements=conflict, set_=update) if update
                            else stmt.on_conflict_do_nothing(index_elements=conflict))
                    s_out.execute(stmt)
    finally:
        src.dispose()
        dst.dispose()


def pull(db_path: Path, repo: Path, remote: str = "origin") -> str:
    """Bring the published database into the local one (see merge_into)."""
    data = fetch_remote(repo, remote)
    if data is None:
        return "no published database yet"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if not db_path.exists():
        unpack(data, db_path)
        return "pulled (new local database)"
    with tempfile.TemporaryDirectory() as tmp:
        published = Path(tmp) / "published.db"
        unpack(data, published)
        merge_into(published, db_path)
    return "pulled (merged)"


def _seen(repo: Path, remote: str) -> str:
    """The data branch as this clone last saw it (its pull or its publish); '' if never."""
    res = subprocess.run(["git", "rev-parse", "--verify", "-q", f"refs/remotes/{remote}/{BRANCH}"],
                         cwd=repo, capture_output=True, text=True, timeout=30)
    return res.stdout.strip() if res.returncode == 0 else ""


def _commit(data: bytes, repo: Path, message: str) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        blob_file = Path(tmp) / FILE
        blob_file.write_bytes(data)
        blob = _git(repo, "hash-object", "-w", str(blob_file))
    tree = _git(repo, "mktree", input_=f"100644 blob {blob}\t{FILE}\n".encode())
    who = {"GIT_AUTHOR_NAME": "DatAtlaSonore", "GIT_AUTHOR_EMAIL": "deezer-stats@users.noreply.github.com",
           "GIT_COMMITTER_NAME": "DatAtlaSonore", "GIT_COMMITTER_EMAIL": "deezer-stats@users.noreply.github.com"}
    return _git(repo, "commit-tree", tree, "-m", message, env=who)


def publish(db_path: Path, repo: Path, remote: str = "origin", message: str = "Update listening database",
            attempts: int = 4) -> str:
    """Replace the one-commit data branch with the compressed database.

    GitHub Actions and your computer both publish, sometimes at the same moment. The branch is
    replaced only if nobody published since this clone last saw it; otherwise that newer copy is
    merged in first (its rows join ours, ours win), then we try again."""
    for attempt in range(attempts):
        seen, data = _seen(repo, remote), pack(db_path)
        commit = _commit(data, repo, message)
        try:
            _git(repo, "push", f"--force-with-lease=refs/heads/{BRANCH}:{seen}", remote, f"{commit}:refs/heads/{BRANCH}")
        except RuntimeError:
            try:
                newer = fetch_remote(repo, remote)
            except RuntimeError:
                newer = None
            if attempt == attempts - 1 or newer is None or _seen(repo, remote) == seen:
                raise  # nobody else published: a real failure (network, rights)
            log.info("The database was published elsewhere meanwhile; merging it before publishing again")
            with tempfile.TemporaryDirectory() as tmp:
                published = Path(tmp) / "published.db"
                unpack(newer, published)
                merge_into(published, db_path, local_wins=True)
            continue
        _git(repo, "update-ref", f"refs/remotes/{remote}/{BRANCH}", commit)
        return f"published {len(data) / 1e6:.1f} MB" + (" (merged a copy published meanwhile)" if attempt else "")
    raise RuntimeError("unreachable")


# --- read-only copy for the hosted app ---------------------------------------------------

def download_copy(url: str, dest_dir: Path, max_age: float = 600) -> Path:
    """Download the published file when the local copy is older than max_age seconds.
    Each download gets a new file name so open connections never read a half-written file."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    copies = sorted(dest_dir.glob("deezer_stats_*.db"))
    if copies and time.time() - copies[-1].stat().st_mtime < max_age:
        return copies[-1]
    try:
        with urllib.request.urlopen(f"{url}?t={int(time.time() // 60)}", timeout=60) as resp:  # noqa: S310
            data = resp.read()
        target = dest_dir / f"deezer_stats_{int(time.time())}.db"
        unpack(data, target)
        for old in copies:
            old.unlink(missing_ok=True)
        return target
    except Exception as exc:
        if copies:
            log.warning("Could not refresh the published database (%s); using the previous copy", exc)
            return copies[-1]
        raise
