"""Reliable artist-genre model: evidence on the genre tree.

Every source turns what it says about an artist into mass on the tree (main genre, sub-genre, genre of
the map). Reliability weights are applied later; here the mass is the raw strength of the vote.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np
import pandas as pd

from core import atlas, genretree
from core.everynoise import Index

W0 = {**atlas.WEIGHT, "everynoise": 3.0, "everynoise_name": 1.5, "artist_model": 2.0}
N_MAIN = 22
HOMONYM_MIN, HOMONYM_GAP = 0.6, 0.2


@dataclass
class Evidence:
    main: np.ndarray = field(default_factory=lambda: np.zeros(N_MAIN))
    sub: dict[int, float] = field(default_factory=dict)
    genre: dict[str, float] = field(default_factory=dict)
    words: Counter = field(default_factory=Counter)

    @property
    def mass(self) -> float:
        return float(self.main.sum())

    def add(self, main: int, mass: float, sub: int | None = None, genre: str | None = None, word: str | None = None) -> None:
        self.main[main] += mass
        if sub is not None:
            self.sub[sub] = self.sub.get(sub, 0.0) + mass
        if genre is not None:
            self.genre[genre] = self.genre.get(genre, 0.0) + mass
        if word:
            self.words[word] += mass


def word_evidence(votes: list[tuple[str, str, float]]) -> dict[str, Evidence]:
    """Per source, the mass of its (word, source, strength) votes, with the rules of atlas.decide()."""
    subs = genretree.tree()["sub"]
    out: dict[str, Evidence] = {}
    for word, source, strength in votes:
        genre, sub, broad = atlas.meaning(word)
        if sub is None:
            continue
        ev = out.setdefault(source, Evidence())
        keep_genre = genre if not broad and not source.startswith("deezer") else None
        ev.add(subs[sub]["main"], strength, None if broad else sub, keep_genre, word.strip())
    return out


def everynoise_evidence(genres: list[tuple[str, int]]) -> Evidence:
    """Every Noise genres of an artist; a genre weighs 1 / (1 + rank / 50) by the artist's rank in it."""
    subs = genretree.tree()["sub"]
    where = genretree.position()
    ev = Evidence()
    for name, rank in genres:
        if name not in where:
            continue
        sub = where[name][2]
        ev.add(subs[sub]["main"], 1.0 / (1.0 + max(0, rank) / 50.0), sub, name, name)
    return ev


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    return float(a @ b / (na * nb)) if na and nb else 0.0


def match_everynoise(index, spotify_of: dict[int, list[str]], names: dict[int, str],
                     context: dict[int, np.ndarray]) -> dict[int, tuple[str, str]]:
    """artist -> ("everynoise" | "everynoise_name", Spotify id). The id first; an artist with known ids
    is never matched by name; a name shared by several artists needs genres that fit the context."""
    out: dict[int, tuple[str, str]] = {}
    for a, name in names.items():
        ids = spotify_of.get(a) or []
        if ids:
            known = next((s for s in ids if index.genres_of(s)), None)
            if known:
                out[a] = ("everynoise", known)
            continue
        cands = index.ids_named(name)
        if len(cands) == 1:
            out[a] = ("everynoise_name", cands[0])
        elif len(cands) > 1:
            ctx = context.get(a)
            if ctx is None or not np.any(ctx):
                continue
            scored = sorted(((_cosine(everynoise_evidence(index.genres_of(s)).main, ctx), s) for s in cands), reverse=True)
            best, runner = scored[0], scored[1][0]
            if best[0] >= HOMONYM_MIN and best[0] - runner >= HOMONYM_GAP:
                out[a] = ("everynoise_name", best[1])
    return out


PRIOR_N, PRIOR_ACC = 10, 0.7
W_MIN, W_MAX, EPS = 0.2, 3.0, 1e-3


def reliability(ev: dict[int, dict[str, Evidence]], prior: dict[str, float] = W0, rounds: int = 20) -> dict[tuple[str, int], float]:
    """Weight of (source, main genre): how often the source's top main genre is also the top of the other
    sources, weighted by their own weights (one-coin Dawid-Skene log-odds), with a prior of 10 artists at 70 %."""
    sources = sorted({s for row in ev.values() for s in row})
    if not sources:  # nothing known yet (a first sync): every source keeps its starting weight
        return {}
    start = {s: prior.get(s, 1.0) for s in sources}
    index = {s: i for i, s in enumerate(sources)}
    base = np.array([start[s] for s in sources])[:, None]
    scale = np.log(PRIOR_ACC / (1 - PRIOR_ACC))
    # Normalised main vectors per artist, computed once.
    obs = []
    for row in ev.values():
        items = [(index[s], e.main / e.main.sum()) for s, e in row.items() if e.main.sum() > 0]
        if len(items) > 1:
            obs.append((np.array([i for i, _ in items]), np.stack([v for _, v in items])))
    w = np.repeat(base, N_MAIN, axis=1)
    for _ in range(rounds):
        n = np.zeros_like(w); agree = np.zeros_like(w)
        for idx, vecs in obs:
            weighted = w[idx] * vecs
            others = weighted.sum(axis=0) - weighted
            tops = vecs.argmax(axis=1)
            ok = others.any(axis=1)
            hit = others.argmax(axis=1) == tops
            np.add.at(n, (idx[ok], tops[ok]), 1)
            np.add.at(agree, (idx[ok], tops[ok]), hit[ok])
        acc = (agree + PRIOR_N * PRIOR_ACC) / (n + PRIOR_N)
        new = base * np.clip(np.log(acc / (1 - acc)) / scale, W_MIN, W_MAX)
        done = np.abs(new - w).max() < EPS
        w = new
        if done:
            break
    return {(s, m): float(w[index[s], m]) for s in sources for m in range(N_MAIN)}


# --- Neighbours, propagation, decision ----------------------------------------------------------------

RELATED_RANK = 5.0                                    # a related link weighs 1 / (1 + rank / 5)
PLAYLIST_W, PLAYLIST_FULL, PLAYLIST_MAX, PLAYLIST_K = 0.3, 3, 300, 30
LAST_RESORT_W = 0.1                                   # big playlists, only for artists nothing else links
ROUNDS, TOL, PULL_MAX = 10, 1e-4, 3.0
WEAK_MASS, NEIGHBOURS_SHARE = 1.0, 0.6
CHUNK = 50_000                                        # edges gathered at once (memory bound)
FAMILY = {"mb_genre": "MusicBrainz", "mb_tag": "MusicBrainz", "album": "MusicBrainz",
          "discogs": "Discogs", "discogs_genre": "Discogs", "deezer": "Deezer", "deezer_top": "Deezer"}
SHOWN = {**atlas.SOURCE_NAME, "everynoise": "Every Noise", "everynoise_name": "Every Noise"}
EXTERNAL = "everynoise_name"                          # how an artist outside the library is known


@dataclass
class Decision:
    main: int
    sub: int
    genre: str
    confidence: str                                   # sure | likely | neighbours
    words: list[str]
    sources: list[str]


def graph(related: pd.DataFrame, playlist_tracks: pd.DataFrame,
          index: Index | None) -> tuple[list[tuple[int, int, float]], dict[int, Evidence]]:
    """Edges (a, b, weight) between Deezer artists, each pair once with a < b, and the Every Noise evidence
    of the related artists that Every Noise knows by a unique name (homonyms and unknown names: skipped).
    A related link weighs 1 / (1 + rank / 5), the best of both directions. Shared playlists of at most
    300 tracks weigh 0.3 x min(1, shared / 3); each artist picks its 30 most shared, and a pair stays
    when either end picked it. A pair linked both ways adds the two weights."""
    parts = []
    rel = related.dropna(subset=["artist_id", "related_id"])
    if not rel.empty:
        a, b = rel["artist_id"].to_numpy("int64"), rel["related_id"].to_numpy("int64")
        w = 1.0 / (1.0 + rel["rank"].to_numpy(float) / RELATED_RANK)
        df = pd.DataFrame({"a": np.minimum(a, b), "b": np.maximum(a, b), "w": w})
        parts.append(df[df["a"] != df["b"]].groupby(["a", "b"], as_index=False)["w"].max())
    parts.append(_playlist_edges(playlist_tracks))
    parts = [p for p in parts if not p.empty]
    linked = set().union(*(set(p["a"]) | set(p["b"]) for p in parts)) if parts else set()
    parts.append(_last_resort_edges(playlist_tracks, linked))
    parts = [p for p in parts if not p.empty]
    edges = pd.concat(parts).groupby(["a", "b"], as_index=False)["w"].sum() if parts else None
    out = [] if edges is None else [(int(a), int(b), float(w)) for a, b, w in edges.itertuples(index=False)]
    external: dict[int, Evidence] = {}
    if index is not None and not rel.empty:
        for rid, name in rel.drop_duplicates("related_id")[["related_id", "related_name"]].itertuples(index=False):
            sids = index.ids_named(name) if isinstance(name, str) else []
            if len(sids) == 1:
                e = everynoise_evidence(index.genres_of(sids[0]))
                if e.mass > 0:
                    external[int(rid)] = e
    return out, external


def _playlist_edges(pt: pd.DataFrame) -> pd.DataFrame:
    """(a, b, w) for artists sharing playlists, a < b, after each artist picks its 30 most shared."""
    size = pt.groupby("playlist_id")["playlist_id"].transform("size")
    pa = pt.loc[size <= PLAYLIST_MAX, ["playlist_id", "artist_id"]].dropna().drop_duplicates()
    pa = pa.astype({"artist_id": "int64"})
    pairs = pa.merge(pa, on="playlist_id")
    pairs = pairs[pairs["artist_id_x"] < pairs["artist_id_y"]]
    shared = pairs.groupby(["artist_id_x", "artist_id_y"]).size().reset_index(name="n")
    x, y, n = shared["artist_id_x"].to_numpy(), shared["artist_id_y"].to_numpy(), shared["n"].to_numpy()
    both = pd.DataFrame({"a": np.r_[x, y], "b": np.r_[y, x], "n": np.r_[n, n]})
    picked = both.sort_values(["a", "n", "b"], ascending=[True, False, True]).groupby("a").head(PLAYLIST_K)
    lo, hi = np.minimum(picked["a"], picked["b"]), np.maximum(picked["a"], picked["b"])
    kept = pd.DataFrame({"a": lo, "b": hi, "n": picked["n"]}).drop_duplicates(["a", "b"])
    return pd.DataFrame({"a": kept["a"], "b": kept["b"], "w": PLAYLIST_W * np.minimum(1.0, kept["n"] / PLAYLIST_FULL)})


def _last_resort_edges(pt: pd.DataFrame, linked: set) -> pd.DataFrame:
    """For an artist of your playlists that nothing else links (no related artist, no playlist of at most
    300 tracks shared), the artists of the bigger playlists it is in, weakly: 0.1 x min(1, shared / 3),
    its 30 most shared. Better a likely genre than a cloud in the middle of nowhere."""
    pa = pt[["playlist_id", "artist_id"]].dropna().drop_duplicates().astype({"artist_id": "int64"})
    alone = pa[~pa["artist_id"].isin(linked)]
    if alone.empty:
        return pd.DataFrame(columns=["a", "b", "w"])
    pairs = alone.merge(pa, on="playlist_id")
    pairs = pairs[pairs["artist_id_x"] != pairs["artist_id_y"]]
    shared = pairs.groupby(["artist_id_x", "artist_id_y"]).size().reset_index(name="n")
    picked = shared.sort_values(["artist_id_x", "n", "artist_id_y"], ascending=[True, False, True]).groupby("artist_id_x").head(PLAYLIST_K)
    lo = np.minimum(picked["artist_id_x"], picked["artist_id_y"])
    hi = np.maximum(picked["artist_id_x"], picked["artist_id_y"])
    w = LAST_RESORT_W * np.minimum(1.0, picked["n"].to_numpy() / PLAYLIST_FULL)
    return pd.DataFrame({"a": lo, "b": hi, "w": w}).groupby(["a", "b"], as_index=False)["w"].max()


@lru_cache(maxsize=1)
def _shape() -> tuple[np.ndarray, np.ndarray, list[str], dict[str, int], dict[int, int], np.ndarray]:
    """Main of each sub, sub of each genre (popularity order), genre names and indices, the most popular
    genre of each sub and the sub of the most popular genre of each main."""
    t = genretree.tree()
    sub_main = np.array([s["main"] for s in t["sub"]])
    names = [g[0] for g in t["genres"]]
    genre_sub = np.array([g[1] for g in t["genres"]])
    top_genre: dict[int, int] = {}
    top_sub: dict[int, int] = {}
    for i, s in enumerate(genre_sub):
        top_genre.setdefault(int(s), i)
        top_sub.setdefault(int(sub_main[s]), int(s))
    top_subs = np.array([top_sub[m] for m in range(N_MAIN)])
    return sub_main, genre_sub, names, {n: i for i, n in enumerate(names)}, top_genre, top_subs


@lru_cache(maxsize=50000)
def _word_main(word: str) -> int | None:
    where = genretree.position()
    sub = where[word][2] if word in where else atlas.meaning(word)[1]
    return None if sub is None else int(_shape()[0][sub])


def _weigh(weights: dict[tuple[str, int], float]):
    cache: dict[str, np.ndarray] = {}

    def of(source: str) -> np.ndarray:
        if source not in cache:
            cache[source] = np.array([weights.get((source, m), W0.get(source, 1.0)) for m in range(N_MAIN)])
        return cache[source]
    return of


def _own(rows: list[dict[str, Evidence]], weight) -> tuple[np.ndarray, np.ndarray, list[dict[int, float]]]:
    """Reliability-weighted own evidence of each node: main (n, 22), sub (n, 162) and genre masses; each
    source counts by its weight on the main genre, its mass scaled down to 1 when larger."""
    sub_main, genre_sub, _, gid, _, _ = _shape()
    em, es = np.zeros((len(rows), N_MAIN)), np.zeros((len(rows), len(sub_main)))
    eg: list[dict[int, float]] = []
    for i, row in enumerate(rows):
        g: dict[int, float] = {}
        for source, e in row.items():
            w = weight(source) / max(1.0, e.mass)
            em[i] += w * e.main
            for s, x in e.sub.items():
                es[i, s] += w[sub_main[s]] * x
            for name, x in e.genre.items():
                k = gid.get(name)
                if k is not None:
                    g[k] = g.get(k, 0.0) + w[sub_main[genre_sub[k]]] * x
        eg.append(g)
    return em, es, eg


def _normalise(x: np.ndarray) -> np.ndarray:
    s = x.sum(axis=1, keepdims=True)
    return np.divide(x, s, out=np.zeros_like(x), where=s > 0)


def _directed(edges, node: dict[int, int], n_lib: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(to, from, weight) arrays toward library artists, sorted by `to`: each pair once (the strongest if
    given twice), both ways between library artists; unknown artists are dropped."""
    empty = (np.zeros(0, np.int64), np.zeros(0, np.int64), np.zeros(0))
    if not edges:
        return empty
    df = pd.DataFrame(edges, columns=["a", "b", "w"])
    i, j = df["a"].map(node), df["b"].map(node)
    ok = i.notna() & j.notna() & (df["w"] > 0)
    i, j, w = i[ok].to_numpy("int64"), j[ok].to_numpy("int64"), df["w"][ok].to_numpy(float)
    lo, hi = np.minimum(i, j), np.maximum(i, j)
    keep = (lo != hi) & (lo < n_lib)                  # library artists come first: lo is one of them
    df = pd.DataFrame({"lo": lo[keep], "hi": hi[keep], "w": w[keep]}).groupby(["lo", "hi"], as_index=False)["w"].max()
    lo, hi, w = df["lo"].to_numpy(), df["hi"].to_numpy(), df["w"].to_numpy()
    back = hi < n_lib
    to, frm, w = np.r_[lo, hi[back]], np.r_[hi, lo[back]], np.r_[w, w[back]]
    order = np.argsort(to, kind="stable")
    return to[order], frm[order], w[order]


def _pull(P: np.ndarray, to: np.ndarray, frm: np.ndarray, w: np.ndarray, n: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """For each of n artists: sum of w x neighbour P, and sum of w over neighbours with main / sub mass.
    `to` is sorted, so each block of edges is summed with reduceat."""
    num = np.zeros((n, P.shape[1]))
    for k in range(0, len(to), CHUNK):
        t, f, x = to[k:k + CHUNK], frm[k:k + CHUNK], w[k:k + CHUNK]
        start = np.flatnonzero(np.r_[True, t[1:] != t[:-1]])
        num[t[start]] += np.add.reduceat(P[f] * x[:, None], start, axis=0)
    has_main, has_sub = P[:, :N_MAIN].sum(axis=1) > 0, P[:, N_MAIN:].sum(axis=1) > 0
    return (num, np.bincount(to, weights=w * has_main[frm], minlength=n),
            np.bincount(to, weights=w * has_sub[frm], minlength=n))


def _expand(rows: np.ndarray, indptr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(position in rows, entry) for every CSR entry of the given rows."""
    cnt = indptr[rows + 1] - indptr[rows]
    return np.repeat(np.arange(len(rows)), cnt), np.repeat(indptr[rows] - np.cumsum(cnt) + cnt, cnt) + np.arange(cnt.sum())


def _genres(eg: list[dict[int, float]], n_lib: int, sub: np.ndarray, to, frm, w) -> dict[int, int]:
    """Library artist -> its genre in its sub: the strongest of its own genres there; without any, the
    strongest there among its neighbours' own genres, weighted by w."""
    cnt = np.array([len(g) for g in eg], dtype=np.int64)
    indptr = np.r_[0, np.cumsum(cnt)]
    gk = np.fromiter((k for g in eg for k in g), np.int64, int(indptr[-1]))
    gv = np.fromiter((v for g in eg for v in g.values()), float, int(indptr[-1]))
    own_at, own_e = _expand(np.arange(n_lib), indptr)
    edge_at, edge_e = _expand(frm, indptr)
    own = _best(own_at, gk[own_e], gv[own_e], sub)
    return {**_best(to[edge_at], gk[edge_e], gv[edge_e] * w[edge_at], sub), **own}


def _best(who: np.ndarray, g: np.ndarray, v: np.ndarray, sub: np.ndarray) -> dict[int, int]:
    """Artist -> the genre of its sub with the largest total mass; ties go to the more popular genre."""
    genre_sub = _shape()[1]
    ok = (genre_sub[g] == sub[who]) & (v > 0)
    who, g, v = who[ok], g[ok], v[ok]
    if not len(who):
        return {}
    keys, inv = np.unique(who * len(genre_sub) + g, return_inverse=True)
    total = np.bincount(inv, weights=v)
    who, g = keys // len(genre_sub), keys % len(genre_sub)
    order = np.lexsort((g, -total, who))
    first = order[np.r_[True, who[order][1:] != who[order][:-1]]]
    return {int(a): int(b) for a, b in zip(who[first], g[first])}


def _sure(row: dict[str, Evidence], sub: int) -> bool:
    """Two source families (MusicBrainz counted once) whose top sub is this one, or Every Noise by id."""
    fam: dict[str, Counter] = {}
    for source, e in row.items():
        for s, x in e.sub.items():
            fam.setdefault(FAMILY.get(source, source), Counter())[s] += x
    agree = {f for f, c in fam.items() if max(c, key=lambda s: (c[s], -s)) == sub}
    return len(agree) >= 2 or "everynoise" in agree


def _support(row: dict[str, Evidence], main: int, weight) -> tuple[list[str], list[str]]:
    """The 4 strongest words of the chosen main from the sources that put it first, and their names."""
    score: Counter = Counter()
    shown = set()
    for source, e in row.items():
        if e.mass <= 0 or int(np.argmax(e.main)) != main:
            continue
        shown.add(SHOWN.get(source, source))
        for word, x in e.words.items():
            if _word_main(word) == main:
                score[word] += x * weight(source)[main]
    words, seen = [], set()
    for word, _ in sorted(score.items(), key=lambda kv: (-kv[1], kv[0])):
        if word.lower() not in seen and len(words) < 4:
            seen.add(word.lower())
            words.append(word)
    return words, sorted(shown)


def classify(ids: list[int], ev: dict[int, dict[str, Evidence]], weights: dict[tuple[str, int], float],
             edges: list[tuple[int, int, float]], external: dict[int, Evidence]) -> dict[int, Decision]:
    """The genre of each library artist with evidence or neighbours: own evidence plus the neighbours'
    distributions, pulled less as the own mass grows; weak own evidence yields to clear neighbours; then
    down the tree (main, sub in it, genre in it). Artists with neither are left out."""
    lib = list(dict.fromkeys(int(a) for a in ids))
    if not lib:
        return {}
    inside = set(lib)
    ext = [int(a) for a in external if int(a) not in inside]
    node = {a: i for i, a in enumerate(lib + ext)}
    n_lib = len(lib)
    weight = _weigh(weights)
    em, es, eg = _own([ev.get(a, {}) for a in lib] + [{EXTERNAL: external[a]} for a in ext], weight)
    mass = em[:n_lib].sum(axis=1)
    P = np.hstack([_normalise(em), _normalise(es)])
    to, frm, w = _directed(edges, node, n_lib)
    outside = frm >= n_lib                             # neighbours outside the library: fixed, summed once
    fixed = _pull(P[n_lib:], to[outside], frm[outside] - n_lib, w[outside], n_lib)
    inner = to[~outside], frm[~outside], w[~outside]
    lam = 1.0 / (1.0 + mass)
    own_top = em[:n_lib].argmax(axis=1)
    Pl, fired = P[:n_lib], np.zeros(n_lib, bool)
    for _ in range(ROUNDS):
        num, dm, ds = (a + b for a, b in zip(_pull(Pl, *inner, n_lib), fixed))
        N = np.hstack([np.divide(num[:, :N_MAIN], dm[:, None], out=np.zeros((n_lib, N_MAIN)), where=dm[:, None] > 0),
                       np.divide(num[:, N_MAIN:], ds[:, None], out=np.zeros((n_lib, es.shape[1])), where=ds[:, None] > 0)])
        new = np.hstack([_normalise(em[:n_lib] + (lam * np.minimum(PULL_MAX, dm))[:, None] * N[:, :N_MAIN]),
                         _normalise(es[:n_lib] + (lam * np.minimum(PULL_MAX, ds))[:, None] * N[:, N_MAIN:])])
        nm = N[:, :N_MAIN]
        fired = (mass < WEAK_MASS) & (nm.max(axis=1) > NEIGHBOURS_SHARE) & (nm.argmax(axis=1) != own_top)
        new[fired] = N[fired]
        delta = float(np.abs(new - Pl).max())
        Pl = new
        if delta < TOL:
            break
    sub_main, _, names, _, top_genre, top_sub = _shape()
    decided = Pl[:, :N_MAIN].sum(axis=1) > 0
    main = Pl[:, :N_MAIN].argmax(axis=1)
    in_main = np.where(sub_main[None, :] == main[:, None], Pl[:, N_MAIN:], 0.0)
    sub = np.where(in_main.max(axis=1) > 0, in_main.argmax(axis=1), top_sub[main])
    sub = np.where(decided, sub, -1)
    genre = _genres(eg, n_lib, sub, to, frm, w)
    out: dict[int, Decision] = {}
    for k in np.flatnonzero(decided):
        a, m, s = lib[k], int(main[k]), int(sub[k])
        g = names[genre.get(int(k), top_genre[s])]
        row = ev.get(a, {})
        if mass[k] == 0 or fired[k]:
            out[a] = Decision(m, s, g, "neighbours", [], ["Deezer"])
            continue
        words, sources = _support(row, m, weight)
        sources = sources or ["Deezer"]                # pulled to this main by its Deezer neighbours
        out[a] = Decision(m, s, g, "sure" if _sure(row, s) else "likely", words, sources)
    return out


# --- Stored at each sync ------------------------------------------------------------------------------

def inputs(engine) -> dict:
    """Everything the model reads from the database: the library artists (played, in playlists or in
    favourite albums), their evidence (Every Noise included), the neighbour graph and the playlists."""
    from sqlalchemy import select

    from core import everynoise, stats
    from core.models import ArtistRelated

    raw, lib = stats.load_raw(engine), stats.load_library(engine)
    plays = stats.assemble(raw, "UTC")
    pt, fav = lib.playlist_tracks.dropna(subset=["artist_id"]), lib.favorites
    ids = sorted({int(a) for frame in (plays, pt, fav) if "artist_id" in frame for a in frame["artist_id"].dropna()})
    _, albums_of = atlas._links(plays, pt, fav)
    votes = atlas._artist_votes(plays, raw.tags, raw.albums, albums_of)
    ev = {a: e for a in ids if (e := word_evidence(votes.get(a, [])))}

    related = stats._read(engine, select(ArtistRelated.artist_id, ArtistRelated.related_id, ArtistRelated.rank,
                                         ArtistRelated.related_name))
    index = everynoise.load()
    edges, external = graph(related, pt, index)
    if index is not None:
        tags = raw.tags[raw.tags["entity_type"] == "artist_spotify"]
        spotify_of: dict[int, list[str]] = {}
        for a, sid in zip(tags["entity_id"], tags["tag"]):
            spotify_of.setdefault(int(a), []).append(str(sid))
        in_library = set(ids)
        names = {int(a): n for a, n in zip(raw.artists["id"], raw.artists["name"]) if int(a) in in_library and isinstance(n, str)}
        # what a name shared by several Every Noise artists must fit: the artist's own genres, else its neighbours'
        context: dict[int, np.ndarray] = {a: sum(_unit(e.main) for e in row.values()) for a, row in ev.items()}
        for a, rid in zip(related["artist_id"], related["related_id"]):
            if int(a) not in ev and int(rid) in external:
                context[int(a)] = context.get(int(a), 0) + _unit(external[int(rid)].main)
        for a, (key, sid) in match_everynoise(index, spotify_of, names, context).items():
            e = everynoise_evidence(index.genres_of(sid))
            if e.mass > 0:
                ev.setdefault(a, {})[key] = e
    return {"ids": ids, "ev": ev, "edges": edges, "external": external, "playlist_tracks": pt,
            "names": {int(a): n for a, n in zip(raw.artists["id"], raw.artists["name"])}}


def run(engine) -> dict:
    """Decide the genre of every artist of the library from everything the database knows, and replace the
    table artist_genre. Returns a summary."""
    from sqlalchemy import delete
    from sqlalchemy.orm import Session

    from core.models import ArtistGenre, utcnow

    data = inputs(engine)
    ids, ev = data["ids"], data["ev"]
    weights = reliability(ev)
    decisions = classify(ids, ev, weights, data["edges"], data["external"])
    now = utcnow()
    with Session(engine) as s:
        s.execute(delete(ArtistGenre))
        s.add_all(ArtistGenre(artist_id=a, main=d.main, sub=d.sub, genre=d.genre, confidence=d.confidence,
                              words=d.words, sources=d.sources, updated=now) for a, d in decisions.items())
        s.commit()
    count = Counter(d.confidence for d in decisions.values())
    return {"artists": len(decisions), "sure": count["sure"], "likely": count["likely"],
            "neighbours": count["neighbours"], "missing": len(ids) - len(decisions),
            "weights": {f"{s}:{m}": round(w, 3) for (s, m), w in sorted(weights.items())
                        if abs(w - W0.get(s, 1.0)) > 1e-6}}


def _unit(x: np.ndarray) -> np.ndarray:
    s = x.sum()
    return x / s if s > 0 else x


# --- Evaluation -------------------------------------------------------------------------------------------

def reference(ev: dict[int, dict[str, Evidence]]) -> dict[int, int]:
    """Artists whose sub-genre is sure: two source families (MusicBrainz counted once) agree on it, or
    Every Noise knows the artist by its Spotify id. Artist -> that sub-genre."""
    out: dict[int, int] = {}
    for a, row in ev.items():
        fam: dict[str, Counter] = {}
        for source, e in row.items():
            for sub, x in e.sub.items():
                fam.setdefault(FAMILY.get(source, source), Counter())[sub] += x
        tops = Counter(max(c, key=lambda k: (c[k], -k)) for c in fam.values() if c)
        if "everynoise" in fam:
            out[a] = max(fam["everynoise"], key=lambda k: (fam["everynoise"][k], -k))
        elif tops and tops.most_common(1)[0][1] >= 2:
            out[a] = tops.most_common(1)[0][0]
    return out


def evaluate(ev: dict[int, dict[str, Evidence]], weights: dict[tuple[str, int], float], edges, external: dict[int, Evidence],
             ids: list[int] | None = None, playlist_tracks: pd.DataFrame | None = None, folds: int = 5) -> dict:
    """How often the model finds the sure genre of the reference artists again:
    - cold: their own evidence hidden (a fifth of them at a time), only their neighbours left, against the
      old way (the main genre of the artists sharing their playlists);
    - single: one source of theirs kept at random (seed 0), to see one source's errors corrected."""
    ids = list(ev) if ids is None else ids
    ref = reference(ev)
    sub_main = _shape()[0]
    if not ref:
        return {"reference": 0}
    hits: Counter = Counter()
    for k in range(folds):
        hidden = {a for a in ref if a % folds == k}
        if not hidden:
            continue
        cold = classify(ids, {a: r for a, r in ev.items() if a not in hidden}, weights, edges, external)
        old = _playlist_guess(ev, hidden, playlist_tracks)
        for a in hidden:
            d = cold.get(a)
            hits["cold_main"] += bool(d and d.main == sub_main[ref[a]])
            hits["cold_sub"] += bool(d and d.sub == ref[a])
            hits["cold_main_old"] += old.get(a) == sub_main[ref[a]]
    rng = np.random.default_rng(0)
    single = dict(ev)
    for a in ref:
        keep = sorted(ev[a])[int(rng.integers(len(ev[a])))]
        single[a] = {keep: ev[a][keep]}
    got = classify(ids, single, weights, edges, external)
    for a in ref:
        d = got.get(a)
        hits["single_main"] += bool(d and d.main == sub_main[ref[a]])
        hits["single_sub"] += bool(d and d.sub == ref[a])
    n = len(ref)
    return {"reference": n, **{k: round(hits[k] / n, 3) for k in
                               ("cold_main", "cold_sub", "cold_main_old", "single_main", "single_sub")}}


def _playlist_guess(ev: dict[int, dict[str, Evidence]], hidden: set, pt: pd.DataFrame | None) -> dict[int, int]:
    """The old way (atlas.place): an artist takes the main genre most shared by the artists of its playlists."""
    if pt is None or pt.empty:
        return {}
    known = {a: int(np.argmax(sum(e.main for e in row.values()))) for a, row in ev.items() if a not in hidden and row}
    pairs = pt.dropna(subset=["artist_id"])[["playlist_id", "artist_id"]].drop_duplicates()
    pairs = pairs.assign(artist_id=pairs["artist_id"].astype(int))
    pairs = pairs.assign(main=pairs["artist_id"].map(known))
    mix = pairs.dropna(subset=["main"]).groupby(["playlist_id", "main"]).size()
    if mix.empty:
        return {}
    share = (mix / mix.groupby(level=0).transform("sum")).rename("share").reset_index()
    asked = pairs[pairs["artist_id"].isin(hidden)][["playlist_id", "artist_id"]]
    guess = asked.merge(share, on="playlist_id").groupby(["artist_id", "main"])["share"].sum().reset_index()
    guess = guess.sort_values("share", ascending=False).drop_duplicates("artist_id")
    return {int(a): int(m) for a, m in zip(guess["artist_id"], guess["main"])}
