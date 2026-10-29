"""Index of Every Noise at Once artists: which genres each Spotify artist is listed under.

Built by scripts/build_everynoise_index.py from the genre pages of everynoise.com (Glenn McDonald)
and stored as app/assets/everynoise_artists.json.gz. On a genre page the artists are listed by
popularity, so the position in the page is the rank of the artist in that genre.
"""

from __future__ import annotations

import gzip
import html
import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from core.config import ROOT

ASSET = ROOT / "app" / "assets" / "everynoise_artists.json.gz"
SOURCE = "Every Noise at Once, everynoise.com (Glenn McDonald)"

# One line per entry: <div id=itemN ...>name<a class=navlink href="...">
ITEM = re.compile(r'<div id=item(\d+) [^>]*?>([^<]*)<a class=navlink href="([^"]*)"')
ARTIST_ID = re.compile(r"artistprofile\.html\?id=([0-9A-Za-z]{22})")
GENRE_HREF = re.compile(r"engenremap-[^\"/]+\.html$")


def norm_name(name: str) -> str:
    """Compare-friendly name: accents stripped, lowercase, letters and digits only."""
    ascii_ = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", ascii_.lower())


def genre_links(main_html: str) -> dict[str, str]:
    """Genre name -> page file name (engenremap-....html) from the main map."""
    return {html.unescape(name).strip(): href for _, name, href in ITEM.findall(main_html)
            if GENRE_HREF.match(href)}


def parse_genre_page(page: str) -> list[tuple[str, str, int]]:
    """(Spotify artist id, name, rank from 1) for each artist of a genre page."""
    rows = []
    for rank, name, href in ITEM.findall(page):
        m = ARTIST_ID.search(href)
        if m:
            rows.append((m.group(1), html.unescape(name).strip(), int(rank)))
    return rows


def build_index(pages: dict[str, list[tuple[str, str, int]]]) -> dict:
    """Merge genre pages into {"source", "genres", "artists": {id: [name, [[genre_idx, rank], ...]]}}."""
    genres = list(pages)
    artists: dict[str, list] = {}
    for gi, rows in enumerate(pages.values()):
        for sid, name, rank in rows:
            artists.setdefault(sid, [name, []])[1].append([gi, rank])
    return {"source": SOURCE, "genres": genres, "artists": artists}


def save(index: dict, path: Path = ASSET) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(index, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    with open(path, "wb") as f, gzip.GzipFile(fileobj=f, mode="wb", mtime=0) as gz:  # mtime=0: reproducible bytes
        gz.write(raw)


class Index:
    def __init__(self, data: dict):
        self.genres: list[str] = data["genres"]
        self.artists: dict[str, list] = data["artists"]
        self._by_name: dict[str, list[str]] = {}
        for sid, (name, _) in self.artists.items():
            self._by_name.setdefault(norm_name(name), []).append(sid)

    def genres_of(self, sid: str) -> list[tuple[str, int]]:
        """(genre, rank) pairs of an artist; empty when unknown."""
        entry = self.artists.get(sid)
        return [(self.genres[g], r) for g, r in entry[1]] if entry else []

    def ids_named(self, name: str) -> list[str]:
        return list(self._by_name.get(norm_name(name), []))

    def name_of(self, sid: str) -> str:
        entry = self.artists.get(sid)
        return entry[0] if entry else ""

    def __len__(self) -> int:
        return len(self.artists)


@lru_cache(maxsize=None)
def _load(path: Path) -> Index | None:
    if not path.exists():
        return None
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return Index(json.load(f))


def load(path: Path = ASSET) -> Index | None:
    """The index, or None when the file is missing. Cached per path."""
    return _load(Path(path))
