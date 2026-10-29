"""Decide the genre of every artist of your library and store it (table artist_genre; see
core/genremodel.py). The sync does it after each enrichment; this runs it on demand.

    python -m scripts.classify_genres
"""

from __future__ import annotations

from core import genremodel
from core.db import get_engine, init_db


def main() -> int:
    summary = genremodel.run(init_db(get_engine()))
    print(f"artists decided: {summary['artists']}  (sure {summary['sure']}, likely {summary['likely']}, "
          f"from their neighbours {summary['neighbours']}; nothing known: {summary['missing']})")
    print("reliability that moved from its starting weight (source:main genre):")
    for key, w in sorted(summary["weights"].items(), key=lambda kv: kv[1]):
        print(f"  {key:24} {w}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
