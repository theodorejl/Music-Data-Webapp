"""Three recommendation engines built on your history and the public Deezer API
(api.deezer.com, no cookie involved). Everything already in your history is left out.

1. Neighbours (artist graph): Deezer's related artists of your favourite artists, scored by how
   much you listen to each seed and how close the neighbour is; one track per new artist.
2. Genres (taste profile): what is charting now in each of your genres, shared out in proportion
   to the place each genre takes in your listening.
3. Moment (context): the radio of the artists you play at this time of day (night, morning,
   afternoon, evening), so the suggestions fit the moment you open the page.

The engines only return ids, titles and artwork: previews are fetched when you press play,
because Deezer's preview links expire after about 15 minutes.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import pandas as pd

from core.deezer_public import DeezerPublicClient

log = logging.getLogger(__name__)

ENGINES = ("neighbours", "genres", "moment")
MOMENTS = (("night", 0, 6), ("morning", 6, 12), ("afternoon", 12, 18), ("evening", 18, 24))


@dataclass(frozen=True)
class Seed:
    artist_id: int
    name: str
    genre: str | None
    minutes: float
    picture: str | None


@dataclass
class Profile:
    """What the engines need from your history (small and hashable enough to cache)."""
    seeds: list[Seed]
    genres: list[tuple[str, float]]  # (genre, share of listening)
    moment: str
    moment_seeds: list[Seed]
    known_artists: frozenset[int] = field(default_factory=frozenset)
    known_tracks: frozenset[int] = field(default_factory=frozenset)


def moment_of(hour: int) -> str:
    return next(name for name, h0, h1 in MOMENTS if h0 <= hour < h1)


def _seeds(df: pd.DataFrame, n: int) -> list[Seed]:
    if df.empty:
        return []
    g = (df.dropna(subset=["artist_id"]).groupby("artist_id")
         .agg(artist=("artist_name", "first"), minutes=("minutes", "sum"), picture=("artist_picture", "first"),
              genre=("genre", lambda s: s.dropna().mode().iloc[0] if s.notna().any() else None))
         .sort_values("minutes", ascending=False).head(n))
    return [Seed(int(k), str(r["artist"]), r["genre"], float(r["minutes"]),
                 r["picture"] if isinstance(r["picture"], str) else None) for k, r in g.iterrows()]


def build_profile(window: pd.DataFrame, history: pd.DataFrame, hour: int, n_seeds: int = 10) -> Profile:
    """window: the plays the recommendations are based on; history: every play (to exclude)."""
    moment = moment_of(hour)
    h0, h1 = next((a, b) for name, a, b in MOMENTS if name == moment)
    local_hour = window["played_local"].dt.hour if not window.empty else pd.Series(dtype=int)
    in_moment = window[(local_hour >= h0) & (local_hour < h1)] if not window.empty else window
    genres = window.dropna(subset=["genre"]).groupby("genre")["minutes"].sum().sort_values(ascending=False)
    total = float(genres.sum()) or 1.0
    return Profile(
        seeds=_seeds(window, n_seeds),
        genres=[(str(g), float(v) / total) for g, v in genres.head(5).items()],
        moment=moment,
        moment_seeds=_seeds(in_moment if not in_moment.empty else window, 3),
        known_artists=frozenset(int(a) for a in history["artist_id"].dropna().unique()),
        known_tracks=frozenset(int(t) for t in history["track_id"].dropna().unique()),
    )


def _rec(engine: str, track: dict, reason: str, genre: str | None, seed: Seed | None, score: float) -> dict:
    album = track.get("album") or {}
    artist = track.get("artist") or {}
    return {
        "engine": engine, "track_id": int(track["id"]), "title": track.get("title_short") or track.get("title") or "?",
        "artist_id": int(artist.get("id") or 0), "artist_name": artist.get("name") or "?",
        "artist_picture": artist.get("picture_medium"), "album_title": album.get("title") or "",
        "cover": album.get("cover_medium") or album.get("cover"), "cover_big": album.get("cover_big"),
        "link": track.get("link") or f"https://www.deezer.com/track/{track['id']}",
        "reason": reason, "genre": genre, "seed_artist_id": seed.artist_id if seed else None,
        "seed_name": seed.name if seed else None, "score": float(score),
    }


def _fetch_all(client: DeezerPublicClient, paths: list[str], workers: int = 6) -> list[dict | None]:
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(client.get, paths))


def neighbours(client: DeezerPublicClient, p: Profile, n: int, taken: set[int]) -> list[dict]:
    """Engine 1: related artists of your favourites, weighted by your listening."""
    if not p.seeds:
        return []
    total = sum(s.minutes for s in p.seeds) or 1.0
    related = _fetch_all(client, [f"artist/{s.artist_id}/related?limit=25" for s in p.seeds])
    score: dict[int, float] = defaultdict(float)
    because: dict[int, list[Seed]] = defaultdict(list)
    for seed, data in zip(p.seeds, related):
        for rank, a in enumerate((data or {}).get("data", [])):
            aid = int(a["id"])
            if aid in p.known_artists:
                continue
            score[aid] += (seed.minutes / total) / (1 + rank / 4)
            because[aid].append(seed)
    best = sorted(score, key=score.get, reverse=True)[: n * 2]
    tops = _fetch_all(client, [f"artist/{aid}/top?limit=5" for aid in best])
    out = []
    for aid, data in zip(best, tops):
        track = next((x for x in (data or {}).get("data", []) if int(x["id"]) not in p.known_tracks
                      and int(x["id"]) not in taken), None)
        if not track:
            continue
        seeds = sorted(because[aid], key=lambda s: -s.minutes)
        reason = " & ".join(s.name for s in seeds[:2])
        out.append(_rec("neighbours", track, reason, seeds[0].genre, seeds[0], score[aid]))
        taken.add(int(track["id"]))
        if len(out) >= n:
            break
    return out


def genres(client: DeezerPublicClient, p: Profile, n: int, taken: set[int]) -> list[dict]:
    """Engine 2: charting tracks in each of your genres, in proportion to your listening."""
    if not p.genres:
        return []
    catalogue = {g["name"].casefold(): int(g["id"]) for g in ((client.get("genre") or {}).get("data", []))}
    wanted = [(g, share, catalogue.get(g.casefold())) for g, share in p.genres]
    wanted = [w for w in wanted if w[2]]
    if not wanted:
        return []
    charts = _fetch_all(client, [f"chart/{gid}/tracks?limit=100" for _, _, gid in wanted])
    shares = sum(s for _, s, _ in wanted) or 1.0
    by_genre_seed = {s.genre: s for s in reversed(p.seeds) if s.genre}
    out = []
    for (genre, share, _), data in zip(wanted, charts):
        quota = max(1, round(n * share / shares))
        picked, artists = 0, set()
        for pos, track in enumerate((data or {}).get("data", [])):
            tid, aid = int(track["id"]), int((track.get("artist") or {}).get("id") or 0)
            if tid in p.known_tracks or tid in taken or aid in p.known_artists or aid in artists:
                continue
            out.append(_rec("genres", track, genre, genre, by_genre_seed.get(genre), share * (1 - pos / 120)))
            taken.add(tid)
            artists.add(aid)
            picked += 1
            if picked >= quota:
                break
    return sorted(out, key=lambda r: -r["score"])[:n]


def moment(client: DeezerPublicClient, p: Profile, n: int, taken: set[int]) -> list[dict]:
    """Engine 3: the radio of what you play at this moment of the day; new artists first."""
    if not p.moment_seeds:
        return []
    radios = _fetch_all(client, [f"artist/{s.artist_id}/radio?limit=60" for s in p.moment_seeds])
    pools = []
    for seed, data in zip(p.moment_seeds, radios):
        tracks = [x for x in (data or {}).get("data", []) if int(x["id"]) not in p.known_tracks]
        new = [x for x in tracks if int((x.get("artist") or {}).get("id") or 0) not in p.known_artists]
        pools.append((seed, new + [x for x in tracks if x not in new]))
    out, artists = [], set()
    # round-robin across the seeds, one artist at most once
    for depth in range(60):
        for seed, pool in pools:
            if depth < len(pool) and len(out) < n:
                track = pool[depth]
                tid, aid = int(track["id"]), int((track.get("artist") or {}).get("id") or 0)
                if tid in taken or aid in artists:
                    continue
                out.append(_rec("moment", track, seed.name, seed.genre, seed, 1 - depth / 60))
                taken.add(tid)
                artists.add(aid)
        if len(out) >= n:
            break
    return out


def recommend(p: Profile, per_engine: int = 12, client: DeezerPublicClient | None = None) -> pd.DataFrame:
    """All three engines, without duplicates across them."""
    client = client or DeezerPublicClient(timeout=10)
    taken: set[int] = set()
    rows = []
    for engine in (neighbours, genres, moment):
        try:
            rows += engine(client, p, per_engine, taken)
        except Exception as exc:  # one engine failing must not hide the others
            log.warning("recommendation engine %s failed: %s", engine.__name__, exc)
    cols = ["engine", "track_id", "title", "artist_id", "artist_name", "artist_picture", "album_title", "cover",
            "cover_big", "link", "reason", "genre", "seed_artist_id", "seed_name", "score"]
    return pd.DataFrame(rows, columns=cols)
