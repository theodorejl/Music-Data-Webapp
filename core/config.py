"""Settings loading.

Lookup order for every setting: environment variables, then Streamlit secrets
(only when running inside Streamlit), then the local `.env` file. The same names
are used everywhere: DATABASE_URL, DEEZER_ARL, ADMIN_PASSWORD, ...
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SQLITE = f"sqlite:///{ROOT / 'data' / 'deezer_stats.db'}"


def _streamlit_secret(name: str) -> str | None:
    """Read a value from st.secrets without failing outside Streamlit."""
    try:
        import streamlit as st
        from streamlit.runtime import exists as runtime_exists

        if not runtime_exists():
            return None
        value = st.secrets.get(name)  # raises if no secrets file at all
        return None if value is None else str(value)
    except Exception:
        return None


@lru_cache(maxsize=1)
def _dotenv() -> dict[str, str | None]:
    path = ROOT / ".env"
    return dotenv_values(path) if path.exists() else {}


def get_setting(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value:
        return value
    value = _streamlit_secret(name)
    if value:
        return value
    value = _dotenv().get(name)
    if value:
        return value
    return default


def normalize_database_url(url: str) -> str:
    """Make relative SQLite paths absolute (relative to the project root) and
    pick the psycopg (v3) driver for Postgres URLs such as Neon's."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    if url.startswith("sqlite:///") and not url.startswith("sqlite:////"):
        rel = url[len("sqlite:///"):]
        if rel and rel != ":memory:" and not Path(rel).is_absolute():
            url = f"sqlite:///{ROOT / rel}"
    return url


@dataclass(frozen=True)
class Settings:
    database_url: str
    deezer_arl: str | None
    deezer_profile: str | None  # Family profile name or id; empty = main profile
    admin_password: str | None
    timezone: str
    history_window: int
    musicbrainz_contact: str
    log_dir: Path


def get_settings() -> Settings:
    return Settings(
        database_url=normalize_database_url(get_setting("DATABASE_URL", DEFAULT_SQLITE)),
        deezer_arl=get_setting("DEEZER_ARL"),
        deezer_profile=get_setting("DEEZER_PROFILE"),
        admin_password=get_setting("ADMIN_PASSWORD"),
        timezone=get_setting("TIMEZONE", "Europe/Zurich"),
        # Maximum number of entries returned by Deezer's history (measured: 100).
        history_window=int(get_setting("HISTORY_WINDOW", "100")),
        musicbrainz_contact=get_setting("MUSICBRAINZ_CONTACT", "personal project"),
        log_dir=Path(get_setting("LOG_DIR", str(ROOT / "logs"))),
    )


# --- secret redaction -------------------------------------------------------

def redact(text: object) -> str:
    """Remove the arl cookie (and DB password) from any text before it is logged."""
    s = str(text)
    for secret in (get_setting("DEEZER_ARL"), _db_password()):
        if secret and len(secret) >= 6:
            s = s.replace(secret, "***")
    return s


def _db_password() -> str | None:
    url = get_setting("DATABASE_URL") or ""
    try:
        from sqlalchemy.engine import make_url

        return make_url(normalize_database_url(url)).password if url else None
    except Exception:
        return None


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = ()
        return True


def setup_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler.addFilter(RedactingFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # urllib3 debug logs could contain URLs/headers; keep them quiet.
    logging.getLogger("urllib3").setLevel(logging.WARNING)
