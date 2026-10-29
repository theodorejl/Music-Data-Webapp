"""Build app/assets/genre_map.json from Every Noise at Once (everynoise.com, Glenn McDonald).

Every Noise places about 6,300 genres on one map: down is more organic, up is more mechanical
and electric; left is denser and more atmospheric, right is spikier and bouncier; the colour
blends further acoustic traits. Genres are listed by popularity (item1 = the most popular).

    python -m scripts.build_genre_map            # downloads the page
    python -m scripts.build_genre_map page.html  # or reads a saved copy

The JSON keeps, for each genre: name, colour, x and y in 0..1, popularity rank, label size.
"""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

import requests

URL = "https://everynoise.com/engenremap.html"
OUT = Path(__file__).resolve().parents[1] / "app" / "assets" / "genre_map.json"
ITEM = re.compile(r'<div id=item(\d+) [^>]*?style="color: (#[0-9a-f]{6}); top: (\d+)px; left: (\d+)px; '
                  r'font-size: (\d+)%"[^>]*?>([^<]+)<')


def parse(page: str) -> list[list]:
    raw = [(int(i), c, int(top), int(left), int(size), html.unescape(name).strip())
           for i, c, top, left, size, name in ITEM.findall(page)]
    if len(raw) < 1000:
        raise ValueError(f"only {len(raw)} genres found: the page layout has changed")
    max_top = max(r[2] for r in raw) or 1
    max_left = max(r[3] for r in raw) or 1
    return [[name, color, round(left / max_left, 5), round(top / max_top, 5), rank, size]
            for rank, color, top, left, size, name in sorted(raw)]


def main(argv: list[str]) -> int:
    page = Path(argv[1]).read_text(encoding="utf-8") if len(argv) > 1 else \
        requests.get(URL, timeout=90, headers={"User-Agent": "Mozilla/5.0"}).text
    genres = parse(page)
    OUT.write_text(json.dumps({
        "source": "Every Noise at Once, everynoise.com (Glenn McDonald)",
        "axes": "x: denser and more atmospheric (0) to spikier and bouncier (1); "
                "y: more mechanical and electric (0) to more organic (1)",
        "fields": ["name", "color", "x", "y", "rank", "size"],
        "genres": genres,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(genres)} genres written to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
