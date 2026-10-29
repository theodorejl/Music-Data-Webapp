"""Three recommendation modes built on your history and the public Deezer API
(api.deezer.com, no cookie involved). Everything already in your history is left out.

1. Neighbours (artist graph): Deezer's related artists of your favourite artists, scored by how
   much you listen to each seed and how close the neighbour is; one track per new artist. For
   large batches the graph is walked one step further (neighbours of the best neighbours).
2. Genres (taste profile): what is charting now in each of your genres (up to 300 tracks per
   genre), shared out in proportion to the place each genre takes in your listening.
3. Moment (context): the radio of the artists you play at this time of day (night, morning,
   afternoon, evening), new artists first.

Each mode can produce 10 to 200 tracks. `estimate()` predicts the number of requests and the time
it takes (the public API allows about 50 requests per 5 seconds); `run()` reports its progress
through a `Progress` object that another thread can read while it works.

The modes only return ids, titles and artwork: previews are fetched when you press play,
because Deezer's preview links expire after about 15 minutes.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import pandas as pd

from core.deezer_public import DeezerPublicClient

log = logging.getLogger(__name__)

ENGINES = ("neighbours", "genres", "moment")
MOMENTS = (("night", 0, 6), ("morning", 6, 12), ("afternoon", 12, 18), ("evening", 18, 24))
MIN_TRACKS, MAX_TRACKS = 10, 200
CALLS_PER_SECOND = 9.5  # measured past the first burst: Deezer allows about 50 requests per 5 s
COLUMNS = ["engine", "track_id", "title", "artist_id", "artist_name", "artist_picture", "album_title", "cover",
           "cover_big", "link", "duration", "reason", "genre", "seed_artist_id", "seed_name", "score"]


@dataclass(frozen=True)
class Seed:
    artist_id: int
    name: str
    genre: str | None
    minutes: float
    picture: str | None


@dataclass
class Profile:
    """What the modes need from your history."""
    seeds: list[Seed]
    genres: list[tuple[str, float]]  # (genre, share of listening)
    moment: str
    moment_seeds: list[Seed]
    known_artists: frozenset[int] = field(default_factory=frozenset)
    known_tracks: frozenset[int] = field(default_factory=frozenset)


class Progress:
    """Shared between the worker (writes) and the page (reads): requests done and planned,
    tracks found, current step."""

    def __init__(self, expected_calls: int, target: int):
        self.expected = max(1, expected_calls)
        self.target = target
        self.done = 0
        self.planned = 0
        self.found = 0
        self.step = "start"
        self.detail = ""
        self.started = time.monotonic()
        self.finished = False
        self._lock = threading.Lock()

    def plan(self, calls: int, step: str, detail: str = "") -> None:
        with self._lock:
            self.planned += calls
            self.step, self.detail = step, detail

    def tick(self) -> None:
        with self._lock:
            self.done += 1

    @property
    def fraction(self) -> float:
        if self.finished:
            return 1.0
        return min(0.98, self.done / max(self.expected, self.planned, 1))

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started


class _Counting:
    """Wraps the client so every request moves the progress bar."""

    def __init__(self, client: DeezerPublicClient, progress: Progress | None):
        self.client, self.progress = client, progress

    def get(self, path: str):
        try:
            return self.client.get(path)
        finally:
            if self.progress:
                self.progress.tick()


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


def build_profile(window: pd.DataFrame, history: pd.DataFrame, hour: int, n_seeds: int = 40) -> Profile:
    """window: the plays the recommendations are based on; history: every play (to exclude)."""
    moment = moment_of(hour)
    h0, h1 = next((a, b) for name, a, b in MOMENTS if name == moment)
    local_hour = window["played_local"].dt.hour if not window.empty else pd.Series(dtype=int)
    in_moment = window[(local_hour >= h0) & (local_hour < h1)] if not window.empty else window
    genres = window.dropna(subset=["genre"]).groupby("genre")["minutes"].sum().sort_values(ascending=False)
    total = float(genres.sum()) or 1.0
    return Profile(
        seeds=_seeds(window, n_seeds),
        genres=[(str(g), float(v) / total) for g, v in genres.head(8).items()],
        moment=moment,
        moment_seeds=_seeds(in_moment if not in_moment.empty else window, 10),
        known_artists=frozenset(int(a) for a in history["artist_id"].dropna().unique()),
        known_tracks=frozenset(int(t) for t in history["track_id"].dropna().unique()),
    )


# --- how big each mode's batch is, and how long it takes ------------------------------------------

def _neighbour_seeds(p: Profile, n: int) -> int:
    return min(len(p.seeds), max(8, math.ceil(n / 7)))


def _moment_seeds(p: Profile, n: int) -> int:
    return min(len(p.moment_seeds), max(3, math.ceil(n / 30)))


def estimate(mode: str, n: int, p: Profile) -> tuple[int, float]:
    """(requests to Deezer, seconds) for `n` tracks in `mode`."""
    if mode == "neighbours":
        seeds = _neighbour_seeds(p, n)
        calls = seeds + math.ceil(n * 1.12) + (math.ceil(n / 14) if n > seeds * 9 else 0)
    elif mode == "genres":
        calls = 1 + min(len(p.genres), 8)
    else:
        calls = _moment_seeds(p, n)
    # a first burst of ~30 requests goes through at once, then the API's rate limit sets the pace
    seconds = 0.6 + (calls * 0.04 if calls <= 30 else calls / CALLS_PER_SECOND)
    if mode == "genres":
        seconds += 0.45 * (calls - 1)  # each chart answer holds 300 tracks
    return calls, round(seconds, 1)


# --- the modes -------------------------------------------------------------------------------------

def _rec(engine: str, track: dict, reason: str, genre: str | None, seed: Seed | None, score: float) -> dict:
    album = track.get("album") or {}
    artist = track.get("artist") or {}
    return {
        "engine": engine, "track_id": int(track["id"]), "title": track.get("title_short") or track.get("title") or "?",
        "artist_id": int(artist.get("id") or 0), "artist_name": artist.get("name") or "?",
        "artist_picture": artist.get("picture_medium"), "album_title": album.get("title") or "",
        "cover": album.get("cover_medium") or album.get("cover"), "cover_big": album.get("cover_big"),
        "link": track.get("link") or f"https://www.deezer.com/track/{track['id']}",
        "duration": int(track.get("duration") or 0),
        "reason": reason, "genre": genre, "seed_artist_id": seed.artist_id if seed else None,
        "seed_name": seed.name if seed else None, "score": float(score),
    }


def _fetch_all(client, paths: list[str], workers: int = 6) -> list[dict | None]:
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(client.get, paths))


def _new_track(data: dict | None, p: Profile, taken: set[int]):
    """The first track that is new and whose main artist is new too (a hit can be a featuring)."""
    for x in (data or {}).get("data", []):
        tid, aid = int(x["id"]), int((x.get("artist") or {}).get("id") or 0)
        if tid not in p.known_tracks and tid not in taken and aid not in p.known_artists:
            return x
    return None


def neighbours(client, p: Profile, n: int, taken: set[int], progress: Progress | None = None) -> list[dict]:
    """Related artists of your favourites, weighted by your listening; one track per new artist."""
    seeds = p.seeds[:_neighbour_seeds(p, n)]
    if not seeds:
        return []
    total = sum(s.minutes for s in seeds) or 1.0
    if progress:
        progress.plan(len(seeds), "graph", ", ".join(s.name for s in seeds[:3]))
    related = _fetch_all(client, [f"artist/{s.artist_id}/related?limit=20" for s in seeds])
    score: dict[int, float] = defaultdict(float)
    because: dict[int, list[Seed]] = defaultdict(list)
    for seed, data in zip(seeds, related):
        for rank, a in enumerate((data or {}).get("data", [])):
            aid = int(a["id"])
            if aid in p.known_artists:
                continue
            score[aid] += (seed.minutes / total) / (1 + rank / 4)
            because[aid].append(seed)
    # not enough new artists for a big batch: walk one step further from the best neighbours
    if len(score) < n * 1.15:
        hops = sorted(score, key=score.get, reverse=True)[: math.ceil(n / 14)]
        if hops and progress:
            progress.plan(len(hops), "graph2", "")
        second = _fetch_all(client, [f"artist/{aid}/related?limit=20" for aid in hops])
        for hop, data in zip(hops, second):
            for rank, a in enumerate((data or {}).get("data", [])):
                aid = int(a["id"])
                if aid in p.known_artists or aid in hops:
                    continue
                score[aid] += score[hop] * 0.45 / (1 + rank / 4)
                because[aid] = because[aid] or because[hop]
    best = sorted(score, key=score.get, reverse=True)[: math.ceil(n * 1.12)]
    if progress:
        progress.plan(len(best), "tracks", "")
    seen = [0]

    def top_of(aid: int):
        data = client.get(f"artist/{aid}/top?limit=5")
        if progress and _new_track(data, p, taken) is not None:  # live count, made exact below
            seen[0] += 1
            progress.found = min(n, seen[0])
        return data

    with ThreadPoolExecutor(max_workers=6) as pool:
        tops = list(pool.map(top_of, best))
    out = []
    for aid, data in zip(best, tops):
        track = _new_track(data, p, taken)
        if not track:
            continue
        seeds_of = sorted(because[aid], key=lambda s: -s.minutes)
        reason = " & ".join(s.name for s in seeds_of[:2])
        out.append(_rec("neighbours", track, reason, seeds_of[0].genre, seeds_of[0], score[aid]))
        taken.add(int(track["id"]))
        if progress:
            progress.found = len(out)
        if len(out) >= n:
            break
    return out


def genres(client, p: Profile, n: int, taken: set[int], progress: Progress | None = None) -> list[dict]:
    """Charting tracks in each of your genres, in proportion to your listening."""
    if not p.genres:
        return []
    if progress:
        progress.plan(1, "catalogue", "")
    catalogue = {g["name"].casefold(): int(g["id"]) for g in ((client.get("genre") or {}).get("data", []))}
    wanted = [(g, share, catalogue.get(g.casefold())) for g, share in p.genres]
    wanted = [w for w in wanted if w[2]]
    if not wanted:
        return []
    if progress:
        progress.plan(len(wanted), "charts", ", ".join(g for g, _, _ in wanted[:3]))
    charts = _fetch_all(client, [f"chart/{gid}/tracks?limit=300" for _, _, gid in wanted])
    shares = sum(s for _, s, _ in wanted) or 1.0
    by_genre_seed = {s.genre: s for s in reversed(p.seeds) if s.genre}
    pools = []
    for (genre, share, _), data in zip(wanted, charts):
        pool = []
        for pos, track in enumerate((data or {}).get("data", [])):
            tid, aid = int(track["id"]), int((track.get("artist") or {}).get("id") or 0)
            if tid not in p.known_tracks and aid not in p.known_artists:
                pool.append((pos, track))
        pools.append((genre, share, pool))
    out, artists = [], set()
    # each genre's quota first, then fill up from the deepest pools
    for pass_ in (0, 1):
        for genre, share, pool in pools:
            quota = max(1, round(n * share / shares)) if pass_ == 0 else n
            picked = sum(1 for r in out if r["genre"] == genre)
            for pos, track in pool:
                if len(out) >= n or (pass_ == 0 and picked >= quota):
                    break
                tid, aid = int(track["id"]), int((track.get("artist") or {}).get("id") or 0)
                if tid in taken or aid in artists:
                    continue
                out.append(_rec("genres", track, genre, genre, by_genre_seed.get(genre), share * (1 - pos / 320)))
                taken.add(tid)
                artists.add(aid)
                picked += 1
        if progress:
            progress.found = len(out)
    return sorted(out, key=lambda r: -r["score"])[:n]


def moment(client, p: Profile, n: int, taken: set[int], progress: Progress | None = None) -> list[dict]:
    """The radio of what you play at this moment of the day; new artists first."""
    seeds = p.moment_seeds[:_moment_seeds(p, n)]
    if not seeds:
        return []
    if progress:
        progress.plan(len(seeds), "radio", ", ".join(s.name for s in seeds[:3]))
    radios = _fetch_all(client, [f"artist/{s.artist_id}/radio?limit=100" for s in seeds])
    pools = []
    for seed, data in zip(seeds, radios):
        tracks = [x for x in (data or {}).get("data", []) if int(x["id"]) not in p.known_tracks]
        new = [x for x in tracks if int((x.get("artist") or {}).get("id") or 0) not in p.known_artists]
        pools.append((seed, new + [x for x in tracks if x not in new]))
    out, artists = [], set()
    for depth in range(100):  # round-robin across the seeds, each artist at most once
        for seed, pool in pools:
            if depth < len(pool) and len(out) < n:
                track = pool[depth]
                tid, aid = int(track["id"]), int((track.get("artist") or {}).get("id") or 0)
                if tid in taken or aid in artists:
                    continue
                out.append(_rec("moment", track, seed.name, seed.genre, seed, 1 - depth / 100))
                taken.add(tid)
                artists.add(aid)
        if len(out) >= n:
            break
    if progress:
        progress.found = len(out)
    return out


MODES = {"neighbours": neighbours, "genres": genres, "moment": moment}


def run(mode: str, p: Profile, n: int, progress: Progress | None = None,
        client: DeezerPublicClient | None = None) -> pd.DataFrame:
    """One mode, `n` tracks (10 to 200)."""
    n = max(MIN_TRACKS, min(MAX_TRACKS, int(n)))
    counting = _Counting(client or DeezerPublicClient(timeout=10), progress)
    try:
        rows = MODES[mode](counting, p, n, set(), progress)
    finally:
        if progress:
            progress.finished = True
    return pd.DataFrame(rows, columns=COLUMNS)


def recommend(p: Profile, per_engine: int = 12, client: DeezerPublicClient | None = None) -> pd.DataFrame:
    """All three modes at once, without duplicates across them."""
    client = client or DeezerPublicClient(timeout=10)
    taken: set[int] = set()
    rows = []
    for engine in MODES.values():
        try:
            rows += engine(client, p, per_engine, taken)
        except Exception as exc:  # one mode failing must not hide the others
            log.warning("recommendation mode %s failed: %s", engine.__name__, exc)
    return pd.DataFrame(rows, columns=COLUMNS)
