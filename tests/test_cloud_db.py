import subprocess
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.cloud_db import BRANCH, fetch_remote, publish, pull
from core.db import get_engine, init_db
from core.deezer_gw import parse_history
from core.models import Alias, ArtistGenre, ArtistRelated, Play
from core.sync import run_sync


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


class Src:
    def __init__(self, records):
        self.records = records

    def fetch_recent(self):
        return self.records


def test_publish_and_pull_round_trip(tmp_path, history_response):
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "--bare", "-q", str(remote))
    repo_a, repo_b = tmp_path / "a", tmp_path / "b"
    for repo in (repo_a, repo_b):
        repo.mkdir()
        git(repo, "init", "-q")
        git(repo, "remote", "add", "origin", str(remote))

    # Machine A (GitHub Actions) collects and publishes.
    db_a = tmp_path / "a.db"
    run_sync(init_db(get_engine(f"sqlite:///{db_a}")), Src(parse_history(history_response)), enrich=False)
    assert fetch_remote(repo_a) is None
    with Session(get_engine(f"sqlite:///{db_a}")) as s:
        s.add(ArtistRelated(artist_id=1, related_id=2, rank=0, related_name="Rel"))
        s.add(ArtistGenre(artist_id=1, main=0, sub=0, genre="house", confidence="sure", words=[], sources=[]))
        s.commit()
    publish(db_a, repo_a)
    publish(db_a, repo_a)  # republishing keeps a single commit on the data branch
    assert git(remote, "rev-list", "--count", BRANCH) == "1"

    # Machine B (your computer) has a local correction, then pulls.
    db_b = tmp_path / "b.db"
    eng_b = init_db(get_engine(f"sqlite:///{db_b}"))
    with Session(eng_b) as s:
        s.add(Alias(kind="rename_genre", source_key="Dance", target="Électro"))
        s.add(ArtistGenre(artist_id=99, main=0, sub=0, genre="techno", confidence="likely", words=[], sources=[]))
        s.commit()
    assert pull(db_b, repo_b).startswith("pulled")
    with Session(eng_b) as s:  # the app's open engine keeps working after the pull
        assert s.scalar(select(func.count()).select_from(Play)) == 6       # published plays arrived
        assert s.scalar(select(func.count()).select_from(Alias)) == 1      # local correction kept
        assert s.scalar(select(func.count()).select_from(ArtistRelated)) == 1  # related artists arrived
        assert [g.artist_id for g in s.scalars(select(ArtistGenre))] == [1]   # decisions: the published ones


def _published_plays(repo, tmp_path) -> int:
    copy = tmp_path / "published_copy.db"
    copy.write_bytes(__import__("gzip").decompress(fetch_remote(repo)))
    with Session(get_engine(f"sqlite:///{copy}")) as s:
        return s.scalar(select(func.count()).select_from(Play))


def test_two_machines_publishing_at_once_lose_nothing(tmp_path, history_response):
    """GitHub Actions and your computer both publish: the second one must not overwrite the first."""
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "--bare", "-q", str(remote))
    repo_a, repo_b = tmp_path / "a", tmp_path / "b"
    for repo in (repo_a, repo_b):
        repo.mkdir()
        git(repo, "init", "-q")
        git(repo, "remote", "add", "origin", str(remote))
    records = parse_history(history_response)
    db_a, db_b = tmp_path / "a.db", tmp_path / "b.db"

    eng_a = init_db(get_engine(f"sqlite:///{db_a}"))
    run_sync(eng_a, Src(records[:3]), enrich=False)
    publish(db_a, repo_a)
    pull(db_b, repo_b)                                    # both start from the same published copy

    run_sync(eng_a, Src(records[3:5]), enrich=False)      # GitHub collects two plays and publishes
    publish(db_a, repo_a)
    run_sync(init_db(get_engine(f"sqlite:///{db_b}")), Src(records[5:]), enrich=False)  # your computer, one other
    publish(db_b, repo_b)                                 # published since its pull: merge, then publish

    assert _published_plays(repo_a, tmp_path) == 6       # nobody's plays were overwritten
    assert git(remote, "rev-list", "--count", BRANCH) == "1"


def test_a_real_failure_still_says_the_push_failed(tmp_path, history_response):
    import pytest
    repo = tmp_path / "a"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "remote", "add", "origin", str(tmp_path / "nowhere.git"))
    db = tmp_path / "a.db"
    run_sync(init_db(get_engine(f"sqlite:///{db}")), Src(parse_history(history_response)), enrich=False)
    with pytest.raises(RuntimeError, match="git push"):
        publish(db, repo)
