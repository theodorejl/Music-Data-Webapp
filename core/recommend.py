"""Discovery engine: three modes that only suggest artists you do not know yet, built on your
history, your Deezer library and the public Deezer API (api.deezer.com, no cookie involved).

"Known" means: any artist or track in your history, your favourite albums or your playlists
(compared by id and by name, since an artist can have several Deezer ids). Known artists are
never suggested; each suggested artist appears once.

1. Neighbours (artist graph): Deezer's related artists of your favourite artists. An artist
   related to several of yours ranks higher (consensus); bold walks one more step away. A cap
   per starting artist keeps the batch varied.
2. Sub-genres (map of sound): your precise sub-genres and the ones around them on the Every Noise
   map (see core/soundmap.py); tracks come from Deezer playlists named after each sub-genre.
3. Moment (context): the radio of the artists you play at this time of day.

Boldness sets how far it goes: familiar favours well-known tracks close to home, balanced the
middle, bold lesser-known artists further away (popularity: Deezer's track rank and artist fans).

Each mode makes 10 to 200 suggestions. `estimate()` predicts the requests and time; `run()`
reports progress through a `Progress` object another thread can read. Every suggestion carries
its sub-genre and an anchor on the map. Previews are fetched when you press play, because
Deezer's preview links expire after about 15 minutes.
"""

from __future__ import annotations

import logging
import math
import re
import threading
import time
import unicodedata
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from urllib.parse import quote

import pandas as pd

from core import soundmap
from core.deezer_public import DeezerPublicClient

log = logging.getLogger(__name__)

ENGINES = ("neighbours", "subgenres", "moment")
BOLDNESS = ("familiar", "balanced", "bold")
MOMENTS = (("night", 0, 6), ("morning", 6, 12), ("afternoon", 12, 18), ("evening", 18, 24))
MIN_TRACKS, MAX_TRACKS = 10, 200
CALLS_PER_SECOND = 9.5  # measured past the first burst: Deezer allows about 50 requests per 5 s
COLUMNS = ["engine", "track_id", "title", "artist_id", "artist_name", "artist_picture", "album_title", "cover",
           "cover_big", "link", "duration", "rank", "reason", "genre", "subgenre", "frontier", "anchor_x", "anchor_y",
           "seed_artist_id", "seed_name", "score"]


def name_key(name: str | None) -> str:
    """Artist names compared loosely: case, accents and punctuation ignored."""
    text = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", text)


def _plain(text: str | None) -> str:
    return unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower()


@dataclass(frozen=True)
class Seed:
    artist_id: int
    name: str
    genre: str | None  # Deezer genre
    minutes: float
    picture: str | None
    subgenre: str | None = None  # main genre on the map of sound
    x: float | None = None
    y: float | None = None


@dataclass
class Profile:
    """What the modes need from your history and library."""
    seeds: list[Seed]
    genres: list[tuple[str, float]]  # Deezer genres and their share of listening
    home: list[tuple[str, float]]  # sub-genres of the map and their share (your territory)
    moment: str
    moment_seeds: list[Seed]
    known_artists: frozenset[int] = field(default_factory=frozenset)
    known_names: frozenset[str] = field(default_factory=frozenset)
    known_tracks: frozenset[int] = field(default_factory=frozenset)

    def is_known(self, artist: dict | None) -> bool:
        artist = artist or {}
        return int(artist.get("id") or 0) in self.known_artists or name_key(artist.get("name")) in self.known_names


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


# --- profile ----------------------------------------------------------------------------------------

def moment_of(hour: int) -> str:
    return next(name for name, h0, h1 in MOMENTS if h0 <= hour < h1)


def _seeds(df: pd.DataFrame, n: int, placed: dict) -> list[Seed]:
    if df.empty:
        return []
    g = (df.dropna(subset=["artist_id"]).groupby("artist_id")
         .agg(artist=("artist_name", "first"), minutes=("minutes", "sum"), picture=("artist_picture", "first"),
              genre=("genre", lambda s: s.dropna().mode().iloc[0] if s.notna().any() else None))
         .sort_values("minutes", ascending=False).head(n))
    out = []
    for k, r in g.iterrows():
        genres_of = placed.get(int(k)) or []
        main = genres_of[0][0] if genres_of else None
        out.append(Seed(int(k), str(r["artist"]), r["genre"], float(r["minutes"]),
                        r["picture"] if isinstance(r["picture"], str) else None,
                        main.name if main else None, main.x if main else None, main.y if main else None))
    return out


def build_profile(window: pd.DataFrame, history: pd.DataFrame, hour: int, tags: pd.DataFrame | None = None,
                  library: pd.DataFrame | None = None, n_seeds: int = 40) -> Profile:
    """window: the plays to start from; history: every play; tags: MusicBrainz tags;
    library: artists and tracks of your favourite albums and playlists (artist_id, artist_name, track_id)."""
    placed = soundmap.artist_genres(history, tags)
    moment = moment_of(hour)
    h0, h1 = next((a, b) for name, a, b in MOMENTS if name == moment)
    local_hour = window["played_local"].dt.hour if not window.empty else pd.Series(dtype=int)
    in_moment = window[(local_hour >= h0) & (local_hour < h1)] if not window.empty else window
    genres = window.dropna(subset=["genre"]).groupby("genre")["minutes"].sum().sort_values(ascending=False)
    total = float(genres.sum()) or 1.0
    known_artists = set(int(a) for a in history["artist_id"].dropna().unique())
    known_names = {name_key(n) for n in history["artist_name"].dropna().unique()}
    known_tracks = set(int(t) for t in history["track_id"].dropna().unique())
    if library is not None and not library.empty:
        known_artists |= set(int(a) for a in library["artist_id"].dropna().unique())
        known_names |= {name_key(n) for n in library["artist_name"].dropna().unique()}
        if "track_id" in library:
            known_tracks |= set(int(t) for t in library["track_id"].dropna().unique())
    known_names.discard("")
    return Profile(
        seeds=_seeds(window, n_seeds, placed),
        genres=[(str(g), float(v) / total) for g, v in genres.head(8).items()],
        home=[(g.name, w) for g, w in soundmap.territory(window, placed)[:60]],
        moment=moment,
        moment_seeds=_seeds(in_moment if not in_moment.empty else window, 10, placed),
        known_artists=frozenset(known_artists), known_names=frozenset(known_names),
        known_tracks=frozenset(known_tracks),
    )


# --- size and time of a batch ---------------------------------------------------------------------

def _neighbour_seeds(p: Profile, n: int) -> int:
    return min(len(p.seeds), max(8, math.ceil(n / 7)))


def _moment_seeds(p: Profile, n: int) -> int:
    return min(len(p.moment_seeds), max(3, math.ceil(n / 25)))


def _subgenre_count(n: int) -> int:
    return max(6, min(30, math.ceil(n / 7)))


def estimate(mode: str, n: int, p: Profile, boldness: str = "balanced") -> tuple[int, float]:
    """(requests to Deezer, seconds) for `n` suggestions in `mode`."""
    if mode == "neighbours":
        seeds = _neighbour_seeds(p, n)
        hops = math.ceil(n / 12) if boldness == "bold" or n > seeds * 9 else 0
        calls = seeds + hops + math.ceil(n * 1.2)
    elif mode == "subgenres":
        calls = round(_subgenre_count(n) * 2.6)
    else:
        calls = _moment_seeds(p, n)
    seconds = 0.6 + (calls * 0.04 if calls <= 30 else calls / CALLS_PER_SECOND)
    return calls, round(seconds, 1)


# --- shared helpers -----------------------------------------------------------------------------------

def _fetch_all(client, paths: list[str], workers: int = 6) -> list[dict | None]:
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(client.get, paths))


def _taste(pct: float, boldness: str) -> float:
    """How welcome a popularity level is (pct: 0 = least popular of the pool, 1 = most)."""
    if boldness == "familiar":
        return 0.45 + 0.55 * pct
    if boldness == "bold":
        return 1.0 - 0.85 * pct
    return 1.0 - 0.9 * abs(pct - 0.45)


def _percentiles(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    pct = [0.0] * len(values)
    for pos, i in enumerate(order):
        pct[i] = pos / max(1, len(values) - 1)
    return pct


def _by_taste(pool: list[dict], boldness: str) -> list[dict]:
    pct = _percentiles([float(x.get("rank") or 0) for x in pool])
    order = sorted(range(len(pool)), key=lambda i: -_taste(pct[i], boldness))
    return [pool[i] for i in order]


def _rec(engine: str, track: dict, reason: str, genre: str | None, seed: Seed | None, score: float,
         subgenre: str | None = None, frontier: bool = False, anchor: tuple | None = None) -> dict:
    album = track.get("album") or {}
    artist = track.get("artist") or {}
    if anchor is None and seed is not None and seed.x is not None:
        anchor = (seed.x, seed.y)
    return {
        "engine": engine, "track_id": int(track["id"]), "title": track.get("title_short") or track.get("title") or "?",
        "artist_id": int(artist.get("id") or 0), "artist_name": artist.get("name") or "?",
        "artist_picture": artist.get("picture_medium"), "album_title": album.get("title") or "",
        "cover": album.get("cover_medium") or album.get("cover"), "cover_big": album.get("cover_big"),
        "link": track.get("link") or f"https://www.deezer.com/track/{track['id']}",
        "duration": int(track.get("duration") or 0), "rank": int(track.get("rank") or 0),
        "reason": reason, "genre": genre, "subgenre": subgenre or (seed.subgenre if seed else None), "frontier": frontier,
        "anchor_x": anchor[0] if anchor else None, "anchor_y": anchor[1] if anchor else None,
        "seed_artist_id": seed.artist_id if seed else None, "seed_name": seed.name if seed else None, "score": float(score),
    }


class _Picker:
    """Keeps a batch free of known music and of repeated tracks or artists."""

    def __init__(self, p: Profile):
        self.p, self.tracks, self.artists, self.names = p, set(), set(), set()

    def ok(self, track: dict) -> bool:
        artist = track.get("artist") or {}
        aid, key = int(artist.get("id") or 0), name_key(artist.get("name"))
        return (int(track["id"]) not in self.p.known_tracks and int(track["id"]) not in self.tracks
                and not self.p.is_known(artist) and aid not in self.artists and key not in self.names)

    def take(self, track: dict) -> None:
        artist = track.get("artist") or {}
        self.tracks.add(int(track["id"]))
        self.artists.add(int(artist.get("id") or 0))
        self.names.add(name_key(artist.get("name")))


# --- 1. neighbours ----------------------------------------------------------------------------------

def neighbours(client, p: Profile, n: int, boldness: str, progress: Progress | None = None) -> list[dict]:
    seeds = p.seeds[:_neighbour_seeds(p, n)]
    if not seeds:
        return []
    total = sum(s.minutes for s in seeds) or 1.0
    if progress:
        progress.plan(len(seeds), "graph", ", ".join(s.name for s in seeds[:3]))
    related = _fetch_all(client, [f"artist/{s.artist_id}/related?limit=20" for s in seeds])
    score: dict[int, float] = defaultdict(float)
    votes: dict[int, int] = defaultdict(int)
    because: dict[int, list[Seed]] = defaultdict(list)
    info: dict[int, dict] = {}
    first_hop = 0.6 if boldness == "bold" else 1.0
    for seed, data in zip(seeds, related):
        for rank, a in enumerate((data or {}).get("data", [])):
            aid = int(a["id"])
            if p.is_known(a):
                continue
            score[aid] += first_hop * (seed.minutes / total) / (1 + rank / 4)
            votes[aid] += 1
            because[aid].append(seed)
            info[aid] = a
    # one more step away: always when bold, otherwise only when the first step is too small
    if boldness == "bold" or len(score) < n * 1.3:
        hops = sorted(score, key=lambda a: score[a] * (1 + 0.3 * (votes[a] - 1)), reverse=True)[: math.ceil(n / 12)]
        if hops and progress:
            progress.plan(len(hops), "graph2", ", ".join(info[h]["name"] for h in hops[:3]))
        second = _fetch_all(client, [f"artist/{aid}/related?limit=20" for aid in hops])
        weight = 0.95 if boldness == "bold" else 0.45
        for hop, data in zip(hops, second):
            for rank, a in enumerate((data or {}).get("data", [])):
                aid = int(a["id"])
                if p.is_known(a) or aid in hops:
                    continue
                score[aid] += score[hop] * weight / (1 + rank / 4)
                votes[aid] = max(votes[aid], 1)
                because[aid] = because[aid] or because[hop]
                info[aid] = a
    # consensus, popularity taste (fans), and a cap per starting artist for variety
    ids = list(score)
    fans = _percentiles([float(info[a].get("nb_fan") or 0) for a in ids])
    final = {a: score[a] * (1 + 0.35 * (votes[a] - 1)) * _taste(f, boldness) for a, f in zip(ids, fans)}
    cap = max(3, math.ceil(n / max(3, len(seeds) * 0.6)))
    per_seed: dict[int, int] = defaultdict(int)
    best = []
    for aid in sorted(final, key=final.get, reverse=True):
        lead = sorted(because[aid], key=lambda s: -s.minutes)[0]
        if per_seed[lead.artist_id] >= cap:
            continue
        per_seed[lead.artist_id] += 1
        best.append(aid)
        if len(best) >= math.ceil(n * 1.2):
            break
    if progress:
        progress.plan(len(best), "tracks", "")
    picker = _Picker(p)
    found = [0]

    def top_of(aid: int):
        data = client.get(f"artist/{aid}/top?limit=5")
        if progress and any(picker.ok(x) for x in (data or {}).get("data", [])):
            found[0] += 1
            progress.found = min(n, found[0])
        return data

    with ThreadPoolExecutor(max_workers=6) as pool:
        tops = list(pool.map(top_of, best))
    out = []
    for aid, data in zip(best, tops):
        tracks = [x for x in (data or {}).get("data", []) if picker.ok(x)]
        if not tracks:
            continue
        # familiar: the artist's best-known track; bold: a lesser-known one among the top three
        track = min(tracks[:3], key=lambda x: x.get("rank") or 0) if boldness == "bold" else tracks[0]
        seeds_of = sorted(because[aid], key=lambda s: -s.minutes)
        reason = " & ".join(s.name for s in seeds_of[:2])
        out.append(_rec("neighbours", track, reason, seeds_of[0].genre, seeds_of[0], final[aid]))
        picker.take(track)
        if len(out) >= n:
            break
    if progress:
        progress.found = len(out)
    return out


# --- 2. sub-genres ------------------------------------------------------------------------------------

SHARE_HOME = {"familiar": 0.6, "balanced": 0.3, "bold": 0.1}


def targets(p: Profile, n: int, boldness: str) -> list[tuple[soundmap.Genre, float, bool, str | None]]:
    """(genre, weight, is_frontier, the home genre it grows from) to explore."""
    count = _subgenre_count(n)
    home = [(soundmap.by_name(name), w) for name, w in p.home]
    home = [(g, w) for g, w in home if g]
    precise = [(g, w) for g, w in home if not soundmap.is_broad(g)] or home
    n_home = max(1, round(count * SHARE_HOME.get(boldness, 0.3))) if precise else 0
    out = [(g, w, False, None) for g, w in precise[:n_home]]
    home_total = sum(w for _, w, _, _ in out) or 1.0
    share_home = SHARE_HOME.get(boldness, 0.3) if out else 0.0
    out = [(g, share_home * w / home_total, f, h) for g, w, f, h in out]
    frontier = soundmap.frontier(home, boldness, count - len(out))
    total_f = sum(s for _, s, _ in frontier) or 1.0
    out += [(g, (1 - share_home) * s / total_f, True, h.name) for g, s, h in frontier]
    total = sum(w for _, w, _, _ in out) or 1.0
    return [(g, w / total, f, h) for g, w, f, h in out]


def _words(text: str) -> set[str]:
    return {w for w in re.split(r"[^a-z0-9&]+", _plain(text)) if len(w) > 1}


def subgenres(client, p: Profile, n: int, boldness: str, progress: Progress | None = None) -> list[dict]:
    goals = targets(p, n, boldness)
    if not goals:
        return []
    if progress:
        progress.plan(len(goals), "search", ", ".join(g.name for g, *_ in goals[:3]))
    found = _fetch_all(client, [f"search/playlist?q={quote(g.name)}&limit=10" for g, *_ in goals])
    # the playlists that name the sub-genre best (Deezer's own editors first), two per sub-genre
    chosen: list[tuple[int, int]] = []
    for i, ((g, *_), data) in enumerate(zip(goals, found)):
        want = _words(g.name)
        lists = []
        for pl in (data or {}).get("data", []):
            got = _words(pl.get("title") or "")
            overlap = len(want & got) / max(1, len(want))
            editorial = "deezer" in name_key((pl.get("user") or {}).get("name"))
            lists.append((overlap + (0.3 if editorial else 0), int(pl.get("nb_tracks") or 0), int(pl["id"])))
        lists.sort(reverse=True)
        keep = [pl for pl in lists if pl[0] >= 0.5][:2] or lists[:1]
        chosen += [(i, pl[2]) for pl in keep]
    if progress:
        progress.plan(len(chosen), "playlists", "")
    tracks = _fetch_all(client, [f"playlist/{pid}/tracks?limit=100" for _, pid in chosen])
    pools: dict[int, list[dict]] = defaultdict(list)
    for (i, _), data in zip(chosen, tracks):
        pools[i] += (data or {}).get("data", [])
    by_genre_seed = {s.subgenre: s for s in reversed(p.seeds) if s.subgenre}
    picker, out = _Picker(p), []
    for pass_ in (0, 1):  # each sub-genre's share first, then fill up from the richest pools
        for i, (g, w, is_frontier, home_name) in enumerate(goals):
            quota = max(1, round(n * w)) if pass_ == 0 else n
            taken = sum(1 for r in out if r["subgenre"] == g.name)
            for x in _by_taste([x for x in pools.get(i, []) if picker.ok(x)], boldness):
                if len(out) >= n or taken >= quota:
                    break
                if not picker.ok(x):
                    continue
                seed = by_genre_seed.get(home_name if is_frontier else g.name)
                reason = f"{home_name} → {g.name}" if is_frontier else g.name
                out.append(_rec("subgenres", x, reason, None, seed, w, subgenre=g.name, frontier=is_frontier,
                                anchor=(g.x, g.y)))
                picker.take(x)
                taken += 1
        if progress:
            progress.found = len(out)
    return out


# --- 3. moment ----------------------------------------------------------------------------------------

def moment(client, p: Profile, n: int, boldness: str, progress: Progress | None = None) -> list[dict]:
    seeds = p.moment_seeds[:_moment_seeds(p, n)]
    if not seeds:
        return []
    if progress:
        progress.plan(len(seeds), "radio", ", ".join(s.name for s in seeds[:3]))
    radios = _fetch_all(client, [f"artist/{s.artist_id}/radio?limit=100" for s in seeds])
    picker = _Picker(p)
    pools = [(seed, _by_taste([x for x in (data or {}).get("data", []) if picker.ok(x)], boldness))
             for seed, data in zip(seeds, radios)]
    out = []
    for depth in range(100):  # round-robin across the starting artists
        for seed, pool in pools:
            if depth < len(pool) and len(out) < n and picker.ok(pool[depth]):
                out.append(_rec("moment", pool[depth], seed.name, seed.genre, seed, 1 - depth / 100))
                picker.take(pool[depth])
        if len(out) >= n:
            break
    if progress:
        progress.found = len(out)
    return out


MODES = {"neighbours": neighbours, "subgenres": subgenres, "moment": moment}


def run(mode: str, p: Profile, n: int, progress: Progress | None = None, client: DeezerPublicClient | None = None,
        boldness: str = "balanced") -> pd.DataFrame:
    """One mode, `n` suggestions (10 to 200)."""
    n = max(MIN_TRACKS, min(MAX_TRACKS, int(n)))
    counting = _Counting(client or DeezerPublicClient(timeout=10), progress)
    try:
        rows = MODES[mode](counting, p, n, boldness if boldness in BOLDNESS else "balanced", progress)
    finally:
        if progress:
            progress.finished = True
    return pd.DataFrame(rows, columns=COLUMNS)
