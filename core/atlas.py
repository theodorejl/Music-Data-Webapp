"""Your artists on the atlas of genres (core/genretree.py): every artist with at least one thing
in your music (a play, a track in a playlist, a favourite album) becomes one point.

Where an artist goes depends on what is known about its genre, from the most precise:
1. MusicBrainz tags of the artist (then of its albums): a precise genre ("dub techno"), so the
   point sits on that genre;
2. the Deezer genres of its albums: a sub-genre at best ("Techno/House", "Indie Rock"), so the
   point is spread over that sub-genre's district; a broad one ("Electro", "Pop"), so it is
   spread over the whole main genre;
3. otherwise the main genre most common among the artists sharing its playlists.
Artists about whom nothing is known are left out (and counted).

Each point weighs your listening time and its place in your library, which is what makes the
density of the map show where your music lives.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict

import numpy as np
import pandas as pd

from core import genretree, soundmap

PICTURE = re.compile(r"^https://cdn-images\.dzcdn\.net/images/artist/([0-9a-f]{32})/250x250-000000-80-0-0\.jpg$")
GENRE, SUB, MAIN = 0, 1, 2  # how precise a placement is
# Deezer's first-level genres ("Electro", "Pop"…); the others ("Techno/House", "Indie Rock"…) are sub-genres.
DEEZER_TOP = set(soundmap.DEEZER) - {"techno/house"}


def _hash(i: int, salt: int) -> float:
    h = (int(i) * 2654435761 + salt * 40503) & 0xFFFFFFFF
    h ^= h >> 15
    h = (h * 2246822519) & 0xFFFFFFFF
    h ^= h >> 13
    return h / 4294967296


def _deezer_choice(lists: list[list[str]]) -> tuple[soundmap.Genre | None, bool]:
    """The genre of the map that best names a set of Deezer album genre lists: the most specific
    entry of each list (the broad family comes first in Deezer's lists), the most common one."""
    votes: Counter = Counter()
    for names in lists:
        names = [n for n in names if isinstance(n, str) and n.strip()]
        if not names:
            continue
        specific = [n for n in names if n.strip().lower() not in DEEZER_TOP]
        votes[(specific or names)[-1].strip()] += 1
    for name, _ in votes.most_common():
        g = soundmap.match(name)
        if g:
            low = name.lower()
            return g, low in DEEZER_TOP or (low not in soundmap.DEEZER and g.name in soundmap.BROAD_NAMES)
    return None, False


def place(artists: pd.DataFrame, plays: pd.DataFrame, tags: pd.DataFrame | None, albums: pd.DataFrame,
          playlist_tracks: pd.DataFrame, favorites: pd.DataFrame) -> tuple[list[dict], int]:
    """(points, how many artists could not be placed). A point: id, n (name), p (picture id or
    url), x, y (0..1), m (main genre), s (sub-genre), g (precise genre or ""), lv (precision),
    pl (plays), mn (minutes), lt (tracks in playlists), fa (favourite albums), w (weight)."""
    tree = genretree.tree()
    where = genretree.position()
    subs, mains = tree["sub"], tree["main"]
    genres_of_sub: dict[int, list[str]] = defaultdict(list)
    genres_of_main: dict[int, list[str]] = defaultdict(list)
    for name, si, _, _ in tree["genres"]:
        genres_of_sub[si].append(name)
        genres_of_main[subs[si]["main"]].append(name)

    by_artist = plays.dropna(subset=["artist_id"]).groupby("artist_id").agg(pl=("play_id", "count"), mn=("minutes", "sum"))
    played = {int(a): (int(r.pl), float(r.mn)) for a, r in by_artist.iterrows()}
    pt = playlist_tracks.dropna(subset=["artist_id"])
    in_lists = {int(a): int(n) for a, n in pt.groupby("artist_id")["track_id"].nunique().items()}
    fav = {int(a): int(n) for a, n in favorites.dropna(subset=["artist_id"]).groupby("artist_id")["album_id"].nunique().items()}
    ids = sorted(set(played) | set(in_lists) | set(fav))

    # 1. MusicBrainz tags (artist, then album) and the Deezer genres the plays carry
    precise = soundmap.artist_genres(plays, tags)
    # 2. Deezer genres of every album linked to the artist
    album_genres = albums.set_index("id")["deezer_genres"].to_dict() if not albums.empty else {}
    links = pd.concat([plays[["artist_id", "album_id"]], pt[["artist_id", "album_id"]],
                       favorites[["artist_id", "album_id"]]], ignore_index=True).dropna().drop_duplicates()
    lists_of: dict[int, list[list[str]]] = defaultdict(list)
    for a, al in zip(links["artist_id"].astype(int), links["album_id"].astype(int)):
        g = album_genres.get(al)
        if isinstance(g, list) and g:
            lists_of[a].append(g)

    level: dict[int, tuple[int, str]] = {}  # artist -> (precision, genre name)
    for a in ids:
        tagged = precise.get(a)
        if tagged and not soundmap.is_broad(tagged[0][0]):
            level[a] = (GENRE, tagged[0][0].name)
            continue
        g, broad = _deezer_choice(lists_of.get(a, []))
        if g is None and tagged:
            g, broad = tagged[0][0], soundmap.is_broad(tagged[0][0])
        if g is not None and g.name in where:
            level[a] = (MAIN if broad else SUB, g.name)

    # 3. the main genre of the artists sharing its playlists
    main_of = {a: subs[where[name][2]]["main"] for a, (_, name) in level.items()}
    if not pt.empty and "playlist_id" in pt:
        pairs = pt[["playlist_id", "artist_id"]].drop_duplicates()
        pairs = pairs.assign(main=pairs["artist_id"].astype(int).map(main_of))
        mix = pairs.dropna(subset=["main"]).groupby(["playlist_id", "main"]).size()
        share = (mix / mix.groupby(level=0).transform("sum")).rename("share").reset_index()
        unknown = pairs[pairs["main"].isna()][["playlist_id", "artist_id"]]
        guess = unknown.merge(share, on="playlist_id").groupby(["artist_id", "main"])["share"].sum().reset_index()
        guess = guess.sort_values("share", ascending=False).drop_duplicates("artist_id")
        for a, m in zip(guess["artist_id"].astype(int), guess["main"].astype(int)):
            names = genres_of_main[m]
            level[a] = (MAIN, names[int(_hash(a, 7) * len(names))])

    names = artists.set_index("id")["name"].to_dict() if not artists.empty else {}
    pics = artists.set_index("id")["picture_medium"].to_dict() if not artists.empty else {}
    out, missing = [], 0
    for a in ids:
        if a not in level:
            missing += 1
            continue
        lv, gname = level[a]
        x, y, si = where[gname]
        if lv == SUB:  # spread over the district of that sub-genre
            pool = genres_of_sub[si]
            x, y, si = where[pool[int(_hash(a, 3) * len(pool))]]
        elif lv == MAIN:  # spread over the whole main genre
            pool = genres_of_main[subs[si]["main"]]
            x, y, si = where[pool[int(_hash(a, 5) * len(pool))]]
        sigma = .0028 if lv == GENRE else .0042
        r = sigma * math.sqrt(-2 * math.log(max(1e-6, _hash(a, 11))))
        t = 2 * math.pi * _hash(a, 13)
        pl, mn = played.get(a, (0, 0.0))
        lt, fa = in_lists.get(a, 0), fav.get(a, 0)
        pic = pics.get(a) or ""
        m = PICTURE.match(pic) if isinstance(pic, str) else None
        out.append({"id": a, "n": names.get(a) or f"#{a}", "p": m.group(1) if m else (pic or ""),
                    "x": round(min(1, max(0, x + r * math.cos(t) / genretree.ASPECT)), 5),
                    "y": round(min(1, max(0, y + r * math.sin(t))), 5),
                    "m": subs[si]["main"], "s": si, "g": gname if lv == GENRE else "", "lv": lv,
                    "pl": pl, "mn": round(mn), "lt": lt, "fa": fa,
                    "w": round(1.2 * math.log1p(mn) + .45 * math.log1p(lt) + .8 * fa + .25, 3)})
    return out, missing


def anchor(subgenre: str | None, x_px: float | None = None, y_px: float | None = None) -> tuple[float, float] | None:
    """Where a recommendation goes on the atlas: on its sub-genre, else on the genre of the map
    closest to its old anchor (Every Noise pixels)."""
    where = genretree.position()
    if subgenre and subgenre in where:
        return where[subgenre][0], where[subgenre][1]
    if x_px is None or y_px is None or (isinstance(x_px, float) and np.isnan(x_px)):
        return None
    best = min(soundmap.genres(), key=lambda g: (g.x - x_px) ** 2 + (g.y - y_px) ** 2)
    p = where.get(best.name)
    return (p[0], p[1]) if p else None


def columns(points: list[dict]) -> dict[str, list]:
    """The points as columns (much lighter in the page than one object per artist)."""
    keys = ("id", "n", "p", "x", "y", "m", "s", "g", "lv", "pl", "mn", "lt", "fa", "w")
    return {k: [p[k] for p in points] for k in keys}
