import subprocess
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.cloud_db import BRANCH, fetch_remote, publish, pull
from core.db import get_engine, init_db
from core.deezer_gw import parse_history
from core.models import Alias, Play
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
    publish(db_a, repo_a)
    publish(db_a, repo_a)  # republishing keeps a single commit on the data branch
    assert git(remote, "rev-list", "--count", BRANCH) == "1"

    # Machine B (your computer) has a local correction, then pulls.
    db_b = tmp_path / "b.db"
    eng_b = init_db(get_engine(f"sqlite:///{db_b}"))
    with Session(eng_b) as s:
        s.add(Alias(kind="rename_genre", source_key="Dance", target="Électro"))
        s.commit()
    assert pull(db_b, repo_b).startswith("pulled")
    with Session(eng_b) as s:  # the app's open engine keeps working after the pull
        assert s.scalar(select(func.count()).select_from(Play)) == 6       # published plays arrived
        assert s.scalar(select(func.count()).select_from(Alias)) == 1      # local correction kept
