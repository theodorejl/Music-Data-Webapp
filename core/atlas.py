"""Your artists on the atlas of genres (core/genretree.py): every artist with at least one thing
in your music (a play, a track in a playlist, a favourite album) becomes one point.

The genre of an artist is a vote between everything known about it (core/artistinfo.py): the
genres of MusicBrainz and Wikidata, the styles of Discogs, the tags of Last.fm listeners, the
MusicBrainz tags of its albums, and the Deezer genres of its albums. Each source weighs what it
is worth (curated genres more than free tags, Deezer's broad "Pop" or "Electro" least), and each
word is read on the tree of genres: an exact genre of the map ("nu-disco"), else a sub-genre
("jazz-funk" is fusion), else nothing (a country, a decade, "seen live").

The main genre with the most votes wins, then its sub-genre with the most votes, then a precise
genre if one clearly stands out. The point goes:
- on that genre when it is known (GENRE);
- else in a small cloud around the name of its sub-genre (SUB);
- else in a cloud around the name of its main genre (MAIN), which is also where an artist goes
  when only the artists sharing its playlists say something about it.
Never on a precise genre that nothing pointed to. Artists about whom nothing is known are left out
(and counted).

Each point weighs your listening time and its place in your library, which is what makes the
density of the map show where your music lives. It also carries the label that released most of
its Deezer albums, the words that placed it and the sources they came from.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from functools import lru_cache

import numpy as np
import pandas as pd

from core import genretree, soundmap

PICTURE = re.compile(r"^https://cdn-images\.dzcdn\.net/images/artist/([0-9a-f]{32})/250x250-000000-80-0-0\.jpg$")
COVER = re.compile(r"^https://cdn-images\.dzcdn\.net/images/cover/([0-9a-f]{32})/250x250-000000-80-0-0\.jpg$")
GENRE, SUB, MAIN = 0, 1, 2  # how precise a placement is
# Deezer's first-level genres ("Electro", "Pop"…); the others ("Techno/House", "Indie Rock"…) are sub-genres.
DEEZER_TOP = set(soundmap.DEEZER) - {"techno/house"}
WEIGHT = {"mb_genre": 3.0, "wikidata": 2.5, "discogs": 2.5, "lastfm": 2.2, "mb_tag": 1.0, "album": .8,
          "discogs_genre": .7, "deezer": 1.2, "deezer_top": .5}
SOURCE_NAME = {"mb_genre": "MusicBrainz", "mb_tag": "MusicBrainz", "album": "MusicBrainz", "wikidata": "Wikidata",
               "discogs": "Discogs", "discogs_genre": "Discogs", "lastfm": "Last.fm", "deezer": "Deezer", "deezer_top": "Deezer"}
# Genres of the map that name a whole main genre, not one of its sub-genres.
MAIN_WORDS = {"pop", "rock", "electronica", "electro", "edm", "dance pop", "hip hop", "rap", "jazz", "classical", "metal",
              "punk", "folk", "country", "r&b", "soul", "funk", "blues", "reggae", "indie", "alternative rock",
              "latin pop", "soundtrack", "world", "afropop", "mpb", "k-pop", "filmi", "children's music", "chanson"}
# Words listeners use that say nothing about the genre.
NOT_GENRES = {"seen live", "favorites", "favourites", "favorite", "awesome", "beautiful", "love", "cool", "chill", "sexy",
              "female vocalists", "male vocalists", "female vocalist", "male vocalist", "female", "male", "vocal",
              "instrumental", "singer", "band", "dj", "producer", "composer", "musician", "artist", "group", "duo",
              "spotify", "under 2000 listeners", "all", "music", "genre", "albums i own", "my music", "check out",
              "francais", "francaise", "french", "english", "american", "british", "uk", "usa", "german", "paris",
              "london", "berlin", "new york", "canadian", "australian", "seen", "live", "remix", "remixes", "cover",
              "covers", "soundtrack composer", "classic", "oldies", "good", "best", "amazing", "mellow", "fun"}


def _hash(i: int, salt: int) -> float:
    h = (int(i) * 2654435761 + salt * 40503) & 0xFFFFFFFF
    h ^= h >> 15
    h = (h * 2246822519) & 0xFFFFFFFF
    h ^= h >> 13
    return h / 4294967296


@lru_cache(maxsize=1)
def _sub_index() -> dict[str, int]:
    return {s["key"]: i for i, s in enumerate(genretree.tree()["sub"])}


@lru_cache(maxsize=50000)
def meaning(tag: str) -> tuple[str | None, int | None, bool]:
    """(genre of the map or None, sub-genre index or None, broad) for any genre word."""
    from core.soundmap import _is_region

    t = re.sub(r"\s+", " ", str(tag).strip().lower())
    if not t or t in NOT_GENRES or re.fullmatch(r"(?:\d0|\d{4}|'\d0)s?|\d+|.*\b(?:century|decade)\b.*", t) or _is_region(t):
        return None, None, False
    where = genretree.position()
    g = soundmap.match(t)
    if g and g.name in where:
        return g.name, where[g.name][2], g.name in MAIN_WORDS or t in DEEZER_TOP
    key = genretree.by_rules(t)  # a genre word the map does not have: its sub-genre at least
    return (None, _sub_index().get(key), key in genretree.GENERIC) if key else (None, None, False)


def _strength(source: str, count, top: float) -> float:
    """How much one word weighs inside its source: Last.fm counts are 0..100, Discogs counts how
    many releases carry the style, MusicBrainz counts votes."""
    if count is None or (isinstance(count, float) and math.isnan(count)):
        return 1.0
    if source == "lastfm":
        return max(.05, float(count) / 100)
    if source in ("discogs", "discogs_genre"):
        return float(count) / max(1.0, top)
    if source in ("mb_genre", "mb_tag", "album"):
        return min(1.0, .4 + .2 * float(count))
    return 1.0


def decide(votes: list[tuple[str, str, float]]) -> dict | None:
    """From (word, source, strength) to {level, genre, sub, main, words, sources}, or None."""
    subs = genretree.tree()["sub"]
    main_score: Counter = Counter()
    sub_score: Counter = Counter()
    genre_score: Counter = Counter()
    words: dict[int, Counter] = defaultdict(Counter)
    sources: dict[int, set] = defaultdict(set)
    for word, source, strength in votes:
        genre, sub, broad = meaning(word)
        if sub is None:
            continue
        w = WEIGHT.get(source, 1.0) * strength
        m = subs[sub]["main"]
        main_score[m] += w
        words[m][word.strip()] += w
        sources[m].add(SOURCE_NAME.get(source, source))
        if not broad:
            sub_score[sub] += w
            if genre and not source.startswith("deezer"):  # Deezer's genres only ever say the sub-genre
                genre_score[(sub, genre)] += w
    if not main_score:
        return None
    main = max(main_score, key=lambda m: (main_score[m], -m))
    in_main = {s: v for s, v in sub_score.items() if subs[s]["main"] == main}
    out = {"main": main, "sub": None, "genre": None, "level": MAIN,
           "words": [w for w, _ in words[main].most_common(4)], "sources": sorted(sources[main])}
    if in_main:
        sub = max(in_main, key=lambda s: (in_main[s], -s))
        out.update(sub=sub, level=SUB)
        best = max(((g, v) for (s, g), v in genre_score.items() if s == sub), key=lambda gv: gv[1], default=None)
        if best and best[1] >= .3 * in_main[sub]:
            out.update(genre=best[0], level=GENRE)
    return out


def place(artists: pd.DataFrame, plays: pd.DataFrame, tags: pd.DataFrame | None, albums: pd.DataFrame,
          playlist_tracks: pd.DataFrame, favorites: pd.DataFrame) -> tuple[list[dict], int]:
    """(points, how many artists could not be placed). A point: id, n (name), p (picture id or
    url), x, y (0..1), m (main genre), s (sub-genre or -1), g (precise genre or ""), lv (precision),
    pl (plays), mn (minutes), lt (tracks in playlists), fa (favourite albums), w (weight),
    lb (label), tg (the words that placed it), sr (their sources)."""
    from core.artistinfo import labels_of

    by_artist = plays.dropna(subset=["artist_id"]).groupby("artist_id").agg(pl=("play_id", "count"), mn=("minutes", "sum"))
    played = {int(a): (int(r.pl), float(r.mn)) for a, r in by_artist.iterrows()}
    pt = playlist_tracks.dropna(subset=["artist_id"])
    in_lists = {int(a): int(n) for a, n in pt.groupby("artist_id")["track_id"].nunique().items()}
    fav = {int(a): int(n) for a, n in favorites.dropna(subset=["artist_id"]).groupby("artist_id")["album_id"].nunique().items()}
    ids = sorted(set(played) | set(in_lists) | set(fav))

    links, albums_of = _links(plays, pt, favorites)
    votes = _artist_votes(plays, tags, albums, albums_of)

    placed = {a: d for a in ids if (d := decide(votes.get(a, [])))}

    # nothing known: the main genre of the artists sharing its playlists
    if not pt.empty and "playlist_id" in pt:
        pairs = pt[["playlist_id", "artist_id"]].drop_duplicates()
        pairs = pairs.assign(main=pairs["artist_id"].astype(int).map({a: d["main"] for a, d in placed.items()}))
        mix = pairs.dropna(subset=["main"]).groupby(["playlist_id", "main"]).size()
        if not mix.empty:
            share = (mix / mix.groupby(level=0).transform("sum")).rename("share").reset_index()
            unknown = pairs[pairs["main"].isna()][["playlist_id", "artist_id"]]
            guess = unknown.merge(share, on="playlist_id").groupby(["artist_id", "main"])["share"].sum().reset_index()
            guess = guess.sort_values("share", ascending=False).drop_duplicates("artist_id")
            for a, m in zip(guess["artist_id"].astype(int), guess["main"].astype(int)):
                placed[a] = {"main": m, "sub": None, "genre": None, "level": MAIN, "words": [], "sources": ["playlists"]}

    label = labels_of(albums, links) if not albums.empty and "label" in albums else {}
    if tags is not None and not tags.empty:
        lab = tags[tags["entity_type"] == "artist_label"]
        for a, lb in zip(lab["entity_id"], lab["tag"]):
            label.setdefault(int(a), lb)
    names = artists.set_index("id")["name"].to_dict() if not artists.empty else {}
    pics = artists.set_index("id")["picture_medium"].to_dict() if not artists.empty else {}

    out, missing = [], 0
    for a in ids:
        d = placed.get(a)
        if d is None:
            missing += 1
            continue
        lv, m = d["level"], d["main"]
        x, y, si = _spot(d, a)
        pl, mn = played.get(a, (0, 0.0))
        lt, fa = in_lists.get(a, 0), fav.get(a, 0)
        pic = pics.get(a) or ""
        mpic = PICTURE.match(pic) if isinstance(pic, str) else None
        out.append({"id": a, "n": names.get(a) or f"#{a}", "p": mpic.group(1) if mpic else (pic or ""),
                    "x": x, "y": y, "m": m, "s": si, "g": d["genre"] or "", "lv": lv,
                    "pl": pl, "mn": round(mn), "lt": lt, "fa": fa,
                    "w": round(1.2 * math.log1p(mn) + .45 * math.log1p(lt) + .8 * fa + .25, 3),
                    "lb": str(label.get(a) or ""), "tg": ", ".join(d["words"][:4]), "sr": ", ".join(d["sources"])})
    return out, missing


def _links(plays: pd.DataFrame, pt: pd.DataFrame, favorites: pd.DataFrame) -> tuple[pd.DataFrame, dict[int, list[int]]]:
    """Every (artist, album) pair of your music, and the albums of each artist."""
    links = pd.concat([plays[["artist_id", "album_id"]], pt[["artist_id", "album_id"]],
                       favorites[["artist_id", "album_id"]]], ignore_index=True).dropna().drop_duplicates()
    links = links.astype({"artist_id": "int64", "album_id": "int64"})
    albums_of: dict[int, list[int]] = defaultdict(list)
    for a, al in zip(links["artist_id"], links["album_id"]):
        albums_of[int(a)].append(int(al))
    return links, albums_of


def _album_votes(albums: pd.DataFrame, tags: pd.DataFrame | None) -> dict[int, list[tuple[str, str, float]]]:
    """What the album itself says: its Deezer genres and its MusicBrainz tags."""
    votes: dict[int, list[tuple[str, str, float]]] = defaultdict(list)
    if tags is not None and not tags.empty:
        alb = tags[tags["entity_type"] == "album"]
        for al, tag, count in zip(alb["entity_id"], alb["tag"], alb["count"]):
            votes[int(al)].append((tag, "album", _strength("album", count, 1)))
    if not albums.empty:
        for al, names in zip(albums["id"], albums["deezer_genres"]):
            if isinstance(names, list):
                for n in names:
                    if isinstance(n, str) and n.strip():
                        votes[int(al)].append((n, "deezer_top" if n.strip().lower() in DEEZER_TOP else "deezer", 1.0))
    return votes


def _artist_votes(plays: pd.DataFrame, tags: pd.DataFrame | None, albums: pd.DataFrame,
                  albums_of: dict[int, list[int]]) -> dict[int, list[tuple[str, str, float]]]:
    """Every vote about every artist: its own tags, then what its albums say."""
    votes: dict[int, list[tuple[str, str, float]]] = defaultdict(list)
    if tags is not None and not tags.empty:
        art = tags[tags["entity_type"] == "artist"]
        tops = art.groupby(["entity_id", "source"])["count"].max().to_dict()
        for a, tag, count, source in zip(art["entity_id"], art["tag"], art["count"], art["source"]):
            votes[int(a)].append((tag, source, _strength(source, count, tops.get((a, source)) or 1)))
    of_album = _album_votes(albums, tags)
    for a, als in albums_of.items():
        for al in als:
            votes[a].extend(of_album.get(al, []))
    if "genre" in plays:  # the genre the plays carry, for played albums not read yet
        for a, g in plays.dropna(subset=["artist_id", "genre"]).drop_duplicates("artist_id")[["artist_id", "genre"]].itertuples(index=False):
            if not votes.get(int(a)):
                votes[int(a)].append((g, "deezer_top" if str(g).lower() in DEEZER_TOP else "deezer", 1.0))
    return votes


def _spot(d: dict, key: int) -> tuple[float, float, int]:
    """(x, y, sub-genre or -1) of a decided point: on its genre, else in a cloud around the name
    of its sub-genre or main genre; the same place every time for the same key."""
    tree = genretree.tree()
    subs, mains, ng = tree["sub"], tree["main"], len(tree["genres"])
    area = genretree.ASPECT * .92 / math.pi  # the atlas, in the units of y
    if d["level"] == GENRE:
        x, y, si = genretree.position()[d["genre"]]
        sigma = .0028
    elif d["level"] == SUB:
        si = d["sub"]
        x, y = subs[si]["x"], subs[si]["y"]
        sigma = min(.05, max(.006, .45 * math.sqrt(subs[si]["n"] / ng * area)))
    else:
        si = -1
        x, y = mains[d["main"]]["x"], mains[d["main"]]["y"]
        sigma = min(.08, max(.01, .4 * math.sqrt(mains[d["main"]]["n"] / ng * area)))
    r = sigma * math.sqrt(-2 * math.log(max(1e-6, _hash(key, 11))))
    t = 2 * math.pi * _hash(key, 13)
    px, py = x + r * math.cos(t) / genretree.ASPECT, y + r * math.sin(t)
    # never outside its territory: back towards its middle (territories are convex, so the way in is straight)
    poly = mains[d["main"]]["poly"] if si == -1 else subs[si]["poly"]
    cx, cy = (mains[d["main"]]["x"], mains[d["main"]]["y"]) if si == -1 else (subs[si]["x"], subs[si]["y"])
    for _ in range(14):
        if _inside(px, py, poly):
            break
        px, py = cx + (px - cx) * .7, cy + (py - cy) * .7
    return round(px, 5), round(py, 5), si


def _inside(x: float, y: float, poly: list) -> bool:
    hit = False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            hit = not hit
    return hit


def place_albums(artists: pd.DataFrame, plays: pd.DataFrame, tags: pd.DataFrame | None, albums: pd.DataFrame,
                 playlist_tracks: pd.DataFrame, favorites: pd.DataFrame) -> list[dict]:
    """Your favourite and listened albums on the atlas, placed by what the album says first
    (Deezer genres, MusicBrainz tags), then by what its artist's votes say (counted half). A
    point: id, n (title), a (artist), ai (artist id), p (cover id or url), x, y, m, s, g, lv,
    lb (label), fa (1 if favourite)."""
    pt = playlist_tracks.dropna(subset=["artist_id"])
    _, albums_of = _links(plays, pt, favorites)
    by_artist = _artist_votes(plays, tags, albums, albums_of)
    own = _album_votes(albums, tags)
    info = albums.set_index("id") if not albums.empty else pd.DataFrame()
    played = set(plays.dropna(subset=["album_id"])["album_id"].astype(int))
    favs = set(favorites.dropna(subset=["album_id"])["album_id"].astype(int))
    artist_of = {int(al): int(a) for al, a in plays.dropna(subset=["album_id", "artist_id"])[["album_id", "artist_id"]].values}
    artist_of.update({int(al): int(a) for al, a in favorites.dropna(subset=["album_id", "artist_id"])[["album_id", "artist_id"]].values})
    names = artists.set_index("id")["name"].to_dict() if not artists.empty else {}
    out = []
    for al in sorted(played | favs):
        row = info.loc[al] if al in info.index else None
        a = artist_of.get(al)
        if row is not None and pd.notna(row.get("artist_id")):
            a = int(row["artist_id"])
        d = decide(own.get(al, []) + [(w, src, s * .5) for w, src, s in by_artist.get(a, [])]) if a is not None else decide(own.get(al, []))
        if d is None:
            continue
        x, y, si = _spot(d, al)
        cover = (row.get("cover_medium") if row is not None else None) or ""
        m = COVER.match(cover) if isinstance(cover, str) else None
        label = row.get("label") if row is not None else None
        out.append({"id": int(al), "n": str((row.get("title") if row is not None else None) or f"#{al}"),
                    "a": str(names.get(a) or ""), "ai": int(a) if a is not None else 0,
                    "p": m.group(1) if m else (cover or ""), "x": x, "y": y, "m": d["main"], "s": si,
                    "g": d["genre"] or "", "lv": d["level"], "lb": str(label) if isinstance(label, str) else "",
                    "fa": int(al in favs), "tg": ", ".join(d["words"][:4]), "sr": ", ".join(d["sources"])})
    return out


def top_share(ids, minutes: dict, pct: float, all_history: bool) -> list:
    """The `pct` % most listened of `ids` (never none when there are some). Outside « all the
    history », only what was listened in the period counts; within it, what was never listened
    comes last."""
    cands = list(ids) if all_history else [i for i in ids if minutes.get(i, 0) > 0]
    cands.sort(key=lambda i: (-minutes.get(i, 0), i))
    return cands[:max(1, math.ceil(len(cands) * pct / 100))] if cands else []


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
    """The points as columns (much lighter in the page than one object per point): artists or
    albums, every point having the same fields."""
    return {k: [p[k] for p in points] for k in points[0]} if points else {}
