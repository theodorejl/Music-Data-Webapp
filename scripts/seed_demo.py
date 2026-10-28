"""Fill a demo database with realistic fake plays (no Deezer cookie needed).

Usage:
    python -m scripts.seed_demo                    # creates data/demo.db
    python -m scripts.seed_demo --db sqlite:///data/other.db --days 400

Then: DATABASE_URL=sqlite:///data/demo.db streamlit run app/Home.py
"""

from __future__ import annotations

import argparse
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete

from core.db import get_engine, init_db, session_scope
from core.models import Alias, Album, Artist, Base, Play, SyncRun, Tag, Track, TrackArtist
from core.sync import estimate_listened

GENRES = ["Electro", "Pop", "Rock", "Jazz", "Rap/Hip Hop", "Classique", "Soul & Funk", "Alternative"]
SYLLABLES = ["lu", "na", "ver", "mo", "sol", "kai", "ra", "tel", "ori", "zen", "pha", "bel", "dor", "mi", "sa"]
WORDS = ["Night", "Blue", "Echo", "Garden", "Signal", "River", "Paper", "Gold", "Static", "Velvet",
         "Neon", "Silent", "Orbit", "Coral", "Winter", "Ember", "Glass", "Atlas", "Shadow", "Bloom"]


def _name(rng: random.Random, n: int = 2) -> str:
    return "".join(rng.choice(SYLLABLES) for _ in range(n)).capitalize()


def _title(rng: random.Random) -> str:
    return " ".join(rng.sample(WORDS, rng.choice([1, 2, 2, 3])))


def _img(kind: str, i: int, size: int) -> str:
    return f"https://picsum.photos/seed/{kind}{i}/{size}/{size}"


def seed(db_url: str, days: int = 420, seed_value: int = 7) -> int:
    rng = random.Random(seed_value)
    engine = init_db(get_engine(db_url))
    with session_scope(engine) as s:
        for table in reversed(Base.metadata.sorted_tables):
            s.execute(delete(table))

        artists, albums, tracks = [], [], []
        track_weights = []
        for a in range(1, 41):
            aid = 9_000_000 + a
            genre = rng.choice(GENRES)
            name = _name(rng, rng.choice([2, 3])) + (f" {_name(rng)}" if rng.random() < 0.4 else "")
            popularity = rng.paretovariate(1.2)
            artists.append(Artist(id=aid, name=name, picture_small=_img("ar", a, 56),
                                  picture_medium=_img("ar", a, 250), picture_big=_img("ar", a, 500),
                                  picture_xl=_img("ar", a, 1000), fetched_at=datetime(2025, 1, 1),
                                  mb_checked_at=datetime(2025, 1, 1)))
            s.add(Tag(entity_type="artist", entity_id=aid, tag=genre.lower(), count=rng.randint(1, 9), source="mb_genre"))
            for b in range(rng.randint(1, 3)):
                alid = aid * 10 + b
                albums.append(Album(
                    id=alid, title=_title(rng), artist_id=aid,
                    release_date=f"{rng.randint(1995, 2026)}-{rng.randint(1, 12):02d}-01",
                    label=f"{_name(rng)} Records", record_type="album",
                    cover_small=_img("al", alid, 56), cover_medium=_img("al", alid, 250),
                    cover_big=_img("al", alid, 500), cover_xl=_img("al", alid, 1000),
                    deezer_genres=[genre] if rng.random() < 0.85 else [],
                    fetched_at=datetime(2025, 1, 1), mb_checked_at=datetime(2025, 1, 1)))
                for t in range(rng.randint(6, 12)):
                    tid = alid * 100 + t
                    tracks.append(Track(id=tid, title=_title(rng), duration=rng.randint(130, 330),
                                        isrc=None, album_id=alid, artist_id=aid, explicit=False,
                                        fetched_at=datetime(2025, 1, 1), mb_checked_at=datetime(2025, 1, 1)))
                    track_weights.append(popularity * rng.paretovariate(1.5))
                    s.add(TrackArtist(track_id=tid, artist_id=aid, role="main", position=0))
        s.add_all(artists + albums + tracks)
        s.flush()

        # Artists "discovered" over time: each artist becomes available at some date.
        now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
        start = now - timedelta(days=days)
        unlock = {a.id: start + timedelta(days=rng.uniform(0, days * 0.9)) for a in artists}
        for a in rng.sample(artists, 12):
            unlock[a.id] = start

        plays = []
        day = start
        while day < now:
            weekend = day.weekday() >= 5
            n_sessions = rng.choice([0, 1, 1, 2, 2, 3] + ([3, 4] if weekend else []))
            for _ in range(n_sessions):
                hour = rng.choices(range(24), weights=[1, .5, .2, .1, .1, .2, 1, 3, 4, 3, 2, 2,
                                                       3, 3, 2, 2, 3, 4, 5, 6, 6, 5, 3, 2])[0]
                t = day.replace(hour=hour, minute=rng.randint(0, 59), second=rng.randint(0, 59))
                available = [i for i, tr in enumerate(tracks) if unlock[tr.artist_id] <= t]
                if not available:
                    continue
                weights = [track_weights[i] for i in available]
                for _ in range(rng.randint(3, 18)):
                    tr = tracks[rng.choices(available, weights=weights)[0]]
                    if t >= now:
                        break
                    skipped = rng.random() < 0.14
                    listened = rng.randint(3, 29) if skipped else tr.duration
                    plays.append((tr.id, t, tr.duration))
                    t += timedelta(seconds=listened + rng.randint(0, 4))
            day += timedelta(days=1)

        plays.sort(key=lambda p: p[1])
        estimates = estimate_listened([(p[1], p[2]) for p in plays])
        s.add_all([Play(track_id=tid, played_at=ts, listened_seconds=est, duration_is_estimated=True,
                        source="demo", raw_json={"SNG_ID": str(tid), "TS": int(ts.replace(tzinfo=timezone.utc).timestamp())})
                   for (tid, ts, _), est in zip(plays, estimates)])

        # A few sync runs, one of them with a gap warning.
        for i in range(48):
            st = now - timedelta(minutes=30 * i + 2)
            s.add(SyncRun(started_at=st, finished_at=st + timedelta(seconds=20), fetched=100,
                          inserted=rng.randint(0, 8), status="ok", duration_s=20.0))
        gs, ge = now - timedelta(days=40, hours=5), now - timedelta(days=40)
        s.add(SyncRun(started_at=now - timedelta(days=40), finished_at=now - timedelta(days=40), fetched=100,
                      inserted=100, status="ok", gap_start=gs, gap_end=ge,
                      gap_warning=f"possible gap between {gs:%Y-%m-%d %H:%M} and {ge:%Y-%m-%d %H:%M} UTC"))
        s.add(Alias(kind="rename_genre", source_key="Alternative", target="Rock"))
    print(f"Demo database ready: {len(plays)} plays, {len(tracks)} tracks, {len(artists)} artists -> {db_url}")
    return len(plays)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", default="sqlite:///data/demo.db")
    p.add_argument("--days", type=int, default=420)
    args = p.parse_args()
    seed(args.db, args.days)


if __name__ == "__main__":
    main()
