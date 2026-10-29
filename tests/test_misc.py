import json
import re
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core import config
from core.deezer_gw import parse_history
from core.models import Play
from core.sync import run_sync

ROOT = Path(__file__).resolve().parents[1]


def _flat(d, prefix=""):
    out = set()
    for k, v in d.items():
        out |= _flat(v, f"{prefix}{k}.") if isinstance(v, dict) else {f"{prefix}{k}"}
    return out


def test_translations_have_same_keys_and_cover_code():
    fr = _flat(json.loads((ROOT / "app/i18n/fr.json").read_text()))
    en = _flat(json.loads((ROOT / "app/i18n/en.json").read_text()))
    assert fr == en
    used = set()
    for path in (ROOT / "app").rglob("*.py"):
        used |= set(re.findall(r'\bt\("([a-z_]+\.[a-zA-Z0-9_.]+)"', path.read_text()))
    missing = used - fr
    assert not missing, missing


def test_redact_hides_arl(monkeypatch):
    monkeypatch.setenv("DEEZER_ARL", "supersecretarlvalue123")
    assert "supersecret" not in config.redact("cookie=supersecretarlvalue123; bad")


def test_database_url_normalization():
    assert config.normalize_database_url("postgres://u:p@h/db").startswith("postgresql+psycopg://")
    assert config.normalize_database_url("postgresql://u:p@h/db?sslmode=require").startswith("postgresql+psycopg://")
    url = config.normalize_database_url("sqlite:///data/x.db")
    assert url.startswith("sqlite:////") and url.endswith("data/x.db")


class _Src:
    def __init__(self, r):
        self.r = r

    def fetch_recent(self):
        return self.r


def test_migration_is_rerunnable(tmp_path, history_response):
    from core.db import get_engine, init_db
    from scripts.migrate_sqlite_to_postgres import migrate

    src_url, dst_url = f"sqlite:///{tmp_path / 'a.db'}", f"sqlite:///{tmp_path / 'b.db'}"
    run_sync(init_db(get_engine(src_url)), _Src(parse_history(history_response)), enrich=False, window=100)
    migrate(src_url, dst_url)
    report = migrate(src_url, dst_url)
    assert report["plays"] == (6, 0)
    with Session(get_engine(dst_url)) as s:
        assert s.scalar(select(func.count()).select_from(Play)) == 6


def test_language_falls_back_when_the_browser_sends_nothing(monkeypatch):
    import streamlit as st

    from app import i18n

    monkeypatch.setattr(st, "session_state", {"lang": None})
    assert i18n.get_lang() == i18n.DEFAULT_LANG and i18n.t("rail.home") == "Accueil"
    monkeypatch.setattr(st, "session_state", {"lang": "en"})
    assert i18n.t("rail.home") == "Home"
