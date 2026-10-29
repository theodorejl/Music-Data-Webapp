"""Ask the music databases about every artist of your library: genres and labels (see
core/artistinfo.py). Resumes where it stopped; the sync also does a little of it every hour.

    python -m scripts.enrich_artists                # for up to 60 minutes
    python -m scripts.enrich_artists --minutes 240

Add LASTFM_API_KEY (and optionally DISCOGS_TOKEN) to .env for the widest and fastest coverage.
"""

from __future__ import annotations

import argparse
import logging
import time

from sqlalchemy.orm import sessionmaker

from core.artistinfo import enrich, sources_from_settings
from core.db import get_engine, init_db
from core.deezer_public import DeezerPublicClient


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--minutes", type=float, default=60)
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(message)s")
    engine = init_db(get_engine())
    deadline = time.monotonic() + args.minutes * 60
    sources = sources_from_settings()
    print("sources:", ", ".join(sources), flush=True)
    total: dict[str, int] = {}
    last = [0.0]

    def progress(source: str, n: int) -> None:
        if time.monotonic() - last[0] > 60:
            last[0] = time.monotonic()
            print(time.strftime("%H:%M"), source, n, flush=True)

    while time.monotonic() < deadline:  # rounds: ids found by one source feed the next round of another
        with sessionmaker(bind=engine, expire_on_commit=False)() as session:
            done = enrich(session, deadline, public=DeezerPublicClient(timeout=12), progress=progress, **sources)
        for k, v in done.items():
            total[k] = total.get(k, 0) + v
        print(time.strftime("%H:%M"), "round:", done, flush=True)
        if not any(done.values()):
            break
    print("answers per source:", total, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
