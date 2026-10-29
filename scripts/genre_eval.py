"""How good the genre model is on your own library (see core/genremodel.py and the design in
docs/superpowers/specs/2026-10-29-genre-classification-design.md).

    python -m scripts.genre_eval

Reference artists are those whose sub-genre is sure (two source families agree, or Every Noise knows
them by their Spotify id). The model must find it again with their own evidence hidden (as for the
artists nobody documents) and with a single source left. Then 40 artists drawn at random, to judge.
"""

from __future__ import annotations

from collections import Counter

import numpy as np

from core import atlas, genremodel, genretree, stats
from core.db import get_engine, init_db


def main() -> int:
    engine = init_db(get_engine())
    data = genremodel.inputs(engine)
    ev, ids = data["ev"], data["ids"]
    weights = genremodel.reliability(ev)
    got = genremodel.evaluate(ev, weights, data["edges"], data["external"], ids=ids, playlist_tracks=data["playlist_tracks"])
    pct = lambda k: f"{100 * got[k]:.0f} %"  # noqa: E731
    print(f"reference artists: {got['reference']}")
    if got["reference"]:
        print(f"own evidence hidden: main genre {pct('cold_main')} (playlists, the old way: {pct('cold_main_old')}), "
              f"sub-genre {pct('cold_sub')}")
        print(f"one source left:     main genre {pct('single_main')}, sub-genre {pct('single_sub')}")

    decisions = genremodel.classify(ids, ev, weights, data["edges"], data["external"])
    raw, lib = stats.load_raw(engine), stats.load_library(engine)
    old, _ = atlas.place(raw.artists, stats.assemble(raw, "UTC"), raw.tags, raw.albums, lib.playlist_tracks, lib.favorites)
    level = {atlas.GENRE: "precise genre", atlas.SUB: "sub-genre only", atlas.MAIN: "main genre only"}
    print("old placement:", dict(Counter(level[p["lv"]] for p in old)), f"(placed {len(old)})")
    print("new placement:", {"precise genre": len(decisions)}, "by", dict(Counter(d.confidence for d in decisions.values())),
          f"(nothing known: {len(ids) - len(decisions)})")

    names, tree = data["names"], genretree.tree()
    rng = np.random.default_rng(0)
    pick = rng.choice(sorted(decisions), size=min(40, len(decisions)), replace=False)
    print("\n40 artists drawn at random:")
    for a in sorted(pick, key=lambda a: str(names.get(int(a), ""))):
        d = decisions[int(a)]
        print(f"  {str(names.get(int(a), a))[:34]:34} {d.genre:28} ({tree['main'][d.main]['fr']}) [{', '.join(d.sources)}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
