"""Client for the public, unauthenticated API (api.deezer.com).

Used for metadata, covers and 30 s previews. Limit: ~50 requests / 5 seconds.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque

import requests

log = logging.getLogger(__name__)

API = "https://api.deezer.com"


class RateLimiter:
    """Sliding window: at most `max_calls` per `period` seconds."""

    def __init__(self, max_calls: int, period: float):
        self.max_calls, self.period = max_calls, period
        self._calls: deque[float] = deque()
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            while self._calls and now - self._calls[0] > self.period:
                self._calls.popleft()
            if len(self._calls) >= self.max_calls:
                time.sleep(self.period - (now - self._calls[0]) + 0.05)
            self._calls.append(time.monotonic())


class DeezerPublicClient:
    def __init__(self, timeout: float = 15.0):
        self._session = requests.Session()
        self._session.headers["User-Agent"] = "DeezerStats/1.0"
        self._limiter = RateLimiter(45, 5.0)  # a little below the official 50/5s
        self._timeout = timeout

    def get(self, path: str, retries: int = 4) -> dict | None:
        """GET /path. Returns None when the object does not exist."""
        delay = 2.0
        for _ in range(retries):
            self._limiter.wait()
            try:
                resp = self._session.get(f"{API}/{path.lstrip('/')}", timeout=self._timeout)
            except requests.RequestException as exc:
                log.warning("api.deezer.com network error on %s: %s", path, exc)
                time.sleep(delay)
                delay *= 2
                continue
            if resp.status_code >= 500 or resp.status_code == 429:
                time.sleep(delay)
                delay *= 2
                continue
            try:
                data = resp.json()
            except ValueError:
                log.warning("api.deezer.com non-JSON answer on %s", path)
                return None
            error = data.get("error") if isinstance(data, dict) else None
            if error:
                code = error.get("code") if isinstance(error, dict) else None
                if code == 4:  # Quota limit exceeded
                    time.sleep(5)
                    continue
                if code == 800:  # no data
                    return None
                log.warning("api.deezer.com error on %s: %s", path, error)
                return None
            return data
        log.warning("api.deezer.com: giving up on %s", path)
        return None

    def track(self, track_id: int) -> dict | None:
        return self.get(f"track/{track_id}")

    def album(self, album_id: int) -> dict | None:
        return self.get(f"album/{album_id}")

    def artist(self, artist_id: int) -> dict | None:
        return self.get(f"artist/{artist_id}")


def cover_url(md5: str | None, size: int = 250) -> str | None:
    """Build a cover URL from the image hash returned by the internal API."""
    if not md5:
        return None
    return f"https://cdn-images.dzcdn.net/images/cover/{md5}/{size}x{size}-000000-80-0-0.jpg"


def artist_picture_url(md5: str | None, size: int = 250) -> str | None:
    if not md5:
        return None
    return f"https://cdn-images.dzcdn.net/images/artist/{md5}/{size}x{size}-000000-80-0-0.jpg"


def fetch_preview_url(track_id: int) -> str | None:
    """Fresh 30 s preview URL (preview URLs are signed and expire)."""
    data = DeezerPublicClient(timeout=8).get(f"track/{track_id}", retries=2)
    return (data or {}).get("preview") or None
