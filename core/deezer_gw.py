"""Deezer web-player ("gw-light") client, authenticated with the `arl` cookie.

Only the sync script / GitHub Actions use this module. The Streamlit app never
imports it and never sees the cookie.

Confirmed on 2026-10-28:
  * `deezer.getUserData`   -> results.USER.USER_ID and results.checkForm (api_token)
  * `user.getSongsHistory` -> results.data = list of songs, newest first, each with
    SNG_ID and TS (unix timestamp of the play start). Capped at 100 entries,
    no pagination beyond that, no "listened duration" field.
  * `deezer.pageProfile` (tab=history) returns the same items: kept as fallback.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

import requests

from core.config import get_settings, redact

log = logging.getLogger(__name__)

GW_URL = "https://www.deezer.com/ajax/gw-light.php"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)
# Fields that are useless for stats or tied to streaming rights/tokens: not stored.
_DROP_FIELDS = {"MEDIA", "RIGHTS", "TRACK_TOKEN", "TRACK_TOKEN_EXPIRE", "MD5_ORIGIN", "LOCALES"}


# --- domain objects & interface --------------------------------------------

@dataclass
class PlayRecord:
    """One play, as returned by a history source (normalized)."""

    track_id: int
    played_at: datetime  # naive UTC
    listened_seconds: int | None = None  # None = unknown, will be estimated
    source: str = "deezer_gw"
    title: str | None = None
    version: str | None = None
    duration: int | None = None
    isrc: str | None = None
    explicit: bool | None = None
    artist_id: int | None = None
    artist_name: str | None = None
    album_id: int | None = None
    album_title: str | None = None
    album_picture: str | None = None  # Deezer image hash
    artists: list[dict] = field(default_factory=list)  # [{id, name, role, picture}]
    raw: dict = field(default_factory=dict)


class HistorySource(Protocol):
    def fetch_recent(self) -> list[PlayRecord]:
        ...


class DeezerAuthError(RuntimeError):
    """The arl cookie is missing, expired or invalid."""


class DeezerAPIError(RuntimeError):
    """Unexpected answer from the internal API."""


# --- parsing (pure, unit-tested) --------------------------------------------

def clean_raw(item: dict) -> dict:
    return {k: v for k, v in item.items() if k not in _DROP_FIELDS and not k.startswith("FILESIZE")}


def _int(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def parse_history_item(item: dict, source: str = "deezer_gw") -> PlayRecord:
    if "SNG_ID" not in item or "TS" not in item:
        raise DeezerAPIError(f"history item without SNG_ID/TS: keys={sorted(item)[:20]}")
    played_at = datetime.fromtimestamp(int(item["TS"]), tz=timezone.utc).replace(tzinfo=None)
    explicit = item.get("EXPLICIT_TRACK_CONTENT", {}) or {}
    artists = []
    for i, a in enumerate(item.get("ARTISTS") or []):
        artists.append({
            "id": _int(a.get("ART_ID")),
            "name": a.get("ART_NAME"),
            "role": "main" if i == 0 else "featuring",
            "picture": a.get("ART_PICTURE"),
        })
    version = (item.get("VERSION") or "").strip() or None
    return PlayRecord(
        track_id=int(item["SNG_ID"]),
        played_at=played_at,
        # The API does not expose the time actually listened: keep None (estimated later).
        listened_seconds=None,
        source=source,
        title=item.get("SNG_TITLE"),
        version=version,
        duration=_int(item.get("DURATION")),
        isrc=item.get("ISRC") or None,
        explicit=bool(explicit.get("EXPLICIT_LYRICS_STATUS")) if explicit else None,
        artist_id=_int(item.get("ART_ID")),
        artist_name=item.get("ART_NAME"),
        album_id=_int(item.get("ALB_ID")),
        album_title=item.get("ALB_TITLE"),
        album_picture=item.get("ALB_PICTURE"),
        artists=artists,
        raw=clean_raw(item),
    )


def extract_history_items(response: dict) -> list[dict]:
    """Return the list of song dicts from a `user.getSongsHistory` or
    `deezer.pageProfile` response. Raises DeezerAPIError if the shape is unknown."""
    if not isinstance(response, dict):
        raise DeezerAPIError("response is not a JSON object")
    error = response.get("error")
    if error:
        raise DeezerAPIError(f"gateway error: {error}")
    results = response.get("results")
    if isinstance(results, dict):
        if isinstance(results.get("data"), list):
            return results["data"]
        tab = results.get("TAB", {}).get("history", {}) if isinstance(results.get("TAB"), dict) else {}
        if isinstance(tab.get("data"), list):
            return tab["data"]
    raise DeezerAPIError("unknown history response shape")


def parse_history(response: dict) -> list[PlayRecord]:
    return [parse_history_item(item) for item in extract_history_items(response)]


# --- HTTP client --------------------------------------------------------------

class DeezerGatewayClient:
    def __init__(self, arl: str | None = None, timeout: float = 20.0, max_retries: int = 4):
        arl = arl or get_settings().deezer_arl
        if not arl:
            raise DeezerAuthError(
                "DEEZER_ARL is not set. Put your arl cookie in .env (local) "
                "or in the GitHub secret DEEZER_ARL (GitHub Actions)."
            )
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
        self._session.cookies.set("arl", arl, domain=".deezer.com")
        self._timeout = timeout
        self._max_retries = max_retries
        self._api_token: str | None = None
        self.user_id: int | None = None

    def _post(self, method: str, body: dict | None = None, api_token: str = "null") -> dict:
        params = {"method": method, "input": "3", "api_version": "1.0", "api_token": api_token}
        delay = 2.0
        last_exc: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                resp = self._session.post(GW_URL, params=params, json=body or {}, timeout=self._timeout)
            except requests.RequestException as exc:
                last_exc = exc
                log.warning("Network error calling %s (attempt %d): %s", method, attempt, redact(exc))
                time.sleep(delay)
                delay *= 2
                continue
            if resp.status_code in (429, 500, 502, 503, 504):
                log.warning("HTTP %s on %s (attempt %d), backing off", resp.status_code, method, attempt)
                time.sleep(delay)
                delay *= 2
                continue
            if resp.status_code in (401, 403):
                raise DeezerAuthError(f"HTTP {resp.status_code} from Deezer: cookie refused")
            try:
                data = resp.json()
            except ValueError as exc:
                save_raw_response(method, resp.text)
                raise DeezerAPIError(f"{method}: non-JSON response (HTTP {resp.status_code})") from exc
            err = data.get("error") if isinstance(data, dict) else None
            if err and _is_rate_limit(err):
                log.warning("Deezer rate limit on %s (attempt %d): %s", method, attempt, err)
                time.sleep(delay)
                delay *= 2
                continue
            return data
        raise DeezerAPIError(f"{method}: giving up after {self._max_retries} attempts ({redact(last_exc)})")

    def login(self) -> None:
        data = self._post("deezer.getUserData")
        results = data.get("results") or {}
        user = results.get("USER") or {}
        user_id = _int(user.get("USER_ID"))
        if not user_id:  # USER_ID == 0 means "not logged in"
            raise DeezerAuthError(
                "Deezer did not accept the arl cookie (expired or invalid). "
                "Log in on deezer.com, copy the new arl cookie and update DEEZER_ARL."
            )
        self.user_id = user_id
        self._api_token = results.get("checkForm")
        log.info("Logged in to Deezer (user id %s)", user_id)

    def call(self, method: str, body: dict | None = None) -> dict:
        if self._api_token is None:
            self.login()
        data = self._post(method, body, api_token=self._api_token or "null")
        err = data.get("error") if isinstance(data, dict) else None
        if err and any(k in str(err) for k in ("VALID_TOKEN_REQUIRED", "invalid api token")):
            log.info("api_token expired, refreshing")
            self.login()
            data = self._post(method, body, api_token=self._api_token or "null")
        return data

    def get_history_raw(self, nb: int = 100) -> dict:
        """Raw history response. Tries the confirmed method first, then the fallback."""
        if self.user_id is None:
            self.login()
        attempts = [
            ("user.getSongsHistory", {"USER_ID": self.user_id, "nb": nb, "start": 0}),
            ("deezer.pageProfile", {"USER_ID": self.user_id, "tab": "history", "nb": nb}),
        ]
        errors = []
        for method, body in attempts:
            data = self.call(method, body)
            try:
                extract_history_items(data)
                return data
            except DeezerAPIError as exc:
                errors.append(f"{method}: {exc}")
                save_raw_response(method, data)
        raise DeezerAPIError("no history method worked: " + " | ".join(errors))


def _is_rate_limit(err) -> bool:
    s = str(err).upper()
    return "QUOTA" in s or "RATE" in s or "TOO MANY" in s


def save_raw_response(method: str, payload) -> Path | None:
    """Log an unexpected raw response to logs/ (secrets redacted)."""
    try:
        log_dir = get_settings().log_dir
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / f"raw_{method}_{datetime.now():%Y%m%d_%H%M%S}.json"
        text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, indent=1)
        text = redact(text)
        path.write_text(text, encoding="utf-8")
        log.warning("Unexpected response from %s saved to %s. Start: %s", method, path, text[:500])
        return path
    except Exception as exc:  # logging must never break the sync
        log.warning("Could not save raw response: %s", redact(exc))
        return None


class DeezerHistorySource:
    """HistorySource backed by the internal web-player API."""

    def __init__(self, client: DeezerGatewayClient | None = None, nb: int | None = None):
        self.client = client or DeezerGatewayClient()
        self.nb = nb or get_settings().history_window

    def fetch_recent(self) -> list[PlayRecord]:
        raw = self.client.get_history_raw(self.nb)
        try:
            return parse_history(raw)
        except DeezerAPIError:
            save_raw_response("history_parse", raw)
            raise
