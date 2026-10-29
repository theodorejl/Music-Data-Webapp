"""Build app/assets/everynoise_artists.json.gz: the genres each artist is listed under on Every Noise.

Every Noise at Once (everynoise.com, Glenn McDonald) has one page per genre, listing its artists by
popularity. This downloads them all (about 6,300 pages, politely paced) into data/everynoise/, then
builds the index (see core/everynoise.py). The crawl is resumable: a cached page is never fetched again,
and a 404 is cached as an empty file.

    python -m scripts.build_everynoise_index [--pause 1.0]
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import requests

from core import everynoise
from core.config import ROOT

BASE = "https://everynoise.com/"
CACHE = ROOT / "data" / "everynoise"
MIN_ARTISTS = 100_000  # fewer means the site changed or the crawl is incomplete


def fetch(name: str) -> str:
    """A page of the site; an empty string for a 404."""
    r = requests.get(BASE + name, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
    if r.status_code == 404:
        return ""
    r.raise_for_status()
    return r.text


def cached(name: str, cache: Path, pause: float, get=fetch, file: str | None = None) -> str:
    """Read a page from the cache (as `file`, default its name), downloading it first when missing."""
    path = cache / (file or name)
    if not path.exists():
        text = get(name)
        path.write_text(text, encoding="utf-8")
        time.sleep(pause)
    return path.read_text(encoding="utf-8")


def crawl(cache: Path = CACHE, pause: float = 1.0, get=fetch, limit: int | None = None) -> dict:
    """Download (or read from the cache) the genre pages and return the index data."""
    cache.mkdir(parents=True, exist_ok=True)
    links = everynoise.genre_links(cached("engenremap.html", cache, pause, get, file="_main.html"))
    if not links:
        raise SystemExit("no genre found on the main page: the layout has changed")
    names = list(links)[:limit]
    pages = {}
    for i, genre in enumerate(names, 1):
        pages[genre] = everynoise.parse_genre_page(cached(links[genre], cache, pause, get))
        if i % 100 == 0:
            print(f"{i}/{len(names)} genre pages")
    return everynoise.build_index(pages)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--pause", type=float, default=1.0, help="seconds between downloads")
    ap.add_argument("--cache", type=Path, default=CACHE, help="folder of the downloaded pages")
    ap.add_argument("--limit", type=int, help="only the first N genres (testing)")
    ap.add_argument("--out", type=Path, default=everynoise.ASSET, help="index file to write")
    args = ap.parse_args()
    index = crawl(args.cache, args.pause, limit=args.limit)
    everynoise.save(index, args.out)
    print(f"{len(index['artists'])} artists in {len(index['genres'])} genres, {args.out.stat().st_size / 1e6:.1f} MB")
    if args.limit is None and len(index["artists"]) < MIN_ARTISTS:
        raise SystemExit(f"only {len(index['artists'])} artists (expected at least {MIN_ARTISTS}): not trusting this index")


if __name__ == "__main__":
    main()
