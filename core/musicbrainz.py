"""MusicBrainz genre/tag enrichment. Strictly 1 request per second.

Flow for a track: ISRC -> recording id -> recording (genres, tags, release groups,
artist credits) -> release group (genres, tags) -> artist (genres, tags).
Album and artist lookups happen once per Deezer album/artist.
"""

from __future__ import annotations

import logging
import time

import requests

from core.config import get_settings

log = logging.getLogger(__name__)

API = "https://musicbrainz.org/ws/2"


class MusicBrainzClient:
    def __init__(self, contact: str | None = None, timeout: float = 15.0):
        contact = contact or get_settings().musicbrainz_contact
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": f"DeezerStats/1.0 ( {contact} )",
            "Accept": "application/json",
        })
        self._timeout = timeout
        self._last_call = 0.0

    def _get(self, path: str, params: dict | None = None) -> dict | None:
        params = {**(params or {}), "fmt": "json"}
        for attempt in range(3):
            wait = 1.05 - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()
            try:
                resp = self._session.get(f"{API}/{path}", params=params, timeout=self._timeout)
            except requests.RequestException as exc:
                log.warning("MusicBrainz network error on %s: %s", path, exc)
                time.sleep(2 * (attempt + 1))
                continue
            if resp.status_code == 404:
                return None
            if resp.status_code in (429, 503):
                time.sleep(3 * (attempt + 1))
                continue
            if resp.status_code != 200:
                log.warning("MusicBrainz HTTP %s on %s", resp.status_code, path)
                return None
            try:
                return resp.json()
            except ValueError:
                return None
        return None

    def recording_id_by_isrc(self, isrc: str) -> str | None:
        data = self._get(f"isrc/{isrc}")
        recs = (data or {}).get("recordings") or []
        return recs[0]["id"] if recs else None

    def recording(self, mbid: str) -> dict | None:
        return self._get(f"recording/{mbid}", {"inc": "genres tags artist-credits releases release-groups"})

    def release_group(self, mbid: str) -> dict | None:
        return self._get(f"release-group/{mbid}", {"inc": "genres tags"})

    def artist(self, mbid: str) -> dict | None:
        return self._get(f"artist/{mbid}", {"inc": "genres tags"})


def extract_tags(obj: dict | None) -> list[tuple[str, int | None, str]]:
    """[(tag, votes, source)] from a MusicBrainz entity (genres + free tags)."""
    out = []
    for g in (obj or {}).get("genres") or []:
        out.append((g["name"], g.get("count"), "mb_genre"))
    for t in (obj or {}).get("tags") or []:
        out.append((t["name"], t.get("count"), "mb_tag"))
    return out


def pick_release_group(recording: dict, album_title: str | None) -> dict | None:
    """The release group matching the Deezer album title, else the first one."""
    groups = []
    for rel in recording.get("releases") or []:
        rg = rel.get("release-group")
        if rg:
            groups.append((rel.get("title") or "", rg))
    if not groups:
        return None
    if album_title:
        wanted = album_title.casefold().strip()
        for title, rg in groups:
            if title.casefold().strip() == wanted or (rg.get("title") or "").casefold().strip() == wanted:
                return rg
    return groups[0][1]
