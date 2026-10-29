"""Reliable artist-genre model: evidence on the genre tree.

Every source turns what it says about an artist into mass on the tree (main genre, sub-genre, genre of
the map). Reliability weights are applied later; here the mass is the raw strength of the vote.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

import numpy as np

from core import atlas, genretree

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
