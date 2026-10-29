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

    tree = genretree.tree()
    where = genretree.position()
    subs, mains = tree["sub"], tree["main"]
    ng = len(tree["genres"])

    by_artist = plays.dropna(subset=["artist_id"]).groupby("artist_id").agg(pl=("play_id", "count"), mn=("minutes", "sum"))
    played = {int(a): (int(r.pl), float(r.mn)) for a, r in by_artist.iterrows()}
    pt = playlist_tracks.dropna(subset=["artist_id"])
    in_lists = {int(a): int(n) for a, n in pt.groupby("artist_id")["track_id"].nunique().items()}
    fav = {int(a): int(n) for a, n in favorites.dropna(subset=["artist_id"]).groupby("artist_id")["album_id"].nunique().items()}
    ids = sorted(set(played) | set(in_lists) | set(fav))

    links = pd.concat([plays[["artist_id", "album_id"]], pt[["artist_id", "album_id"]],
                       favorites[["artist_id", "album_id"]]], ignore_index=True).dropna().drop_duplicates()
    links = links.astype({"artist_id": "int64", "album_id": "int64"})
    albums_of: dict[int, list[int]] = defaultdict(list)
    for a, al in zip(links["artist_id"], links["album_id"]):
        albums_of[int(a)].append(int(al))

    # every vote about every artist
    votes: dict[int, list[tuple[str, str, float]]] = defaultdict(list)
    if tags is not None and not tags.empty:
        art = tags[tags["entity_type"] == "artist"]
        tops = art.groupby(["entity_id", "source"])["count"].max().to_dict()
        for a, tag, count, source in zip(art["entity_id"], art["tag"], art["count"], art["source"]):
            votes[int(a)].append((tag, source, _strength(source, count, tops.get((a, source)) or 1)))
        alb = tags[tags["entity_type"] == "album"]
        album_tags: dict[int, list] = defaultdict(list)
        for al, tag, count in zip(alb["entity_id"], alb["tag"], alb["count"]):
            album_tags[int(al)].append((tag, count))
        for a, als in albums_of.items():
            for al in als:
                for tag, count in album_tags.get(al, []):
                    votes[a].append((tag, "album", _strength("album", count, 1)))
    genres_of_album = albums.set_index("id")["deezer_genres"].to_dict() if not albums.empty else {}
    for a, als in albums_of.items():
        for al in als:
            names = genres_of_album.get(al)
            if isinstance(names, list):
                for n in names:
                    if isinstance(n, str) and n.strip():
                        votes[a].append((n, "deezer_top" if n.strip().lower() in DEEZER_TOP else "deezer", 1.0))
    if "genre" in plays:  # the genre the plays carry, for played albums not read yet
        for a, g in plays.dropna(subset=["artist_id", "genre"]).drop_duplicates("artist_id")[["artist_id", "genre"]].itertuples(index=False):
            if not votes.get(int(a)):
                votes[int(a)].append((g, "deezer_top" if str(g).lower() in DEEZER_TOP else "deezer", 1.0))

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
    area = genretree.ASPECT * .92 / math.pi  # the atlas, in the units of y

    out, missing = [], 0
    for a in ids:
        d = placed.get(a)
        if d is None:
            missing += 1
            continue
        lv, m = d["level"], d["main"]
        if lv == GENRE:
            x, y, si = where[d["genre"]]
            sigma = .0028
        elif lv == SUB:
            si = d["sub"]
            x, y = subs[si]["x"], subs[si]["y"]
            sigma = min(.05, max(.006, .45 * math.sqrt(subs[si]["n"] / ng * area)))
        else:
            si = None
            x, y = mains[m]["x"], mains[m]["y"]
            sigma = min(.08, max(.01, .4 * math.sqrt(mains[m]["n"] / ng * area)))
        r = sigma * math.sqrt(-2 * math.log(max(1e-6, _hash(a, 11))))
        t = 2 * math.pi * _hash(a, 13)
        pl, mn = played.get(a, (0, 0.0))
        lt, fa = in_lists.get(a, 0), fav.get(a, 0)
        pic = pics.get(a) or ""
        mpic = PICTURE.match(pic) if isinstance(pic, str) else None
        out.append({"id": a, "n": names.get(a) or f"#{a}", "p": mpic.group(1) if mpic else (pic or ""),
                    "x": round(min(1, max(0, x + r * math.cos(t) / genretree.ASPECT)), 5),
                    "y": round(min(1, max(0, y + r * math.sin(t))), 5),
                    "m": m, "s": si if si is not None else -1, "g": d["genre"] or "", "lv": lv,
                    "pl": pl, "mn": round(mn), "lt": lt, "fa": fa,
                    "w": round(1.2 * math.log1p(mn) + .45 * math.log1p(lt) + .8 * fa + .25, 3),
                    "lb": str(label.get(a) or ""), "tg": ", ".join(d["words"][:4]), "sr": ", ".join(d["sources"])})
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
    keys = ("id", "n", "p", "x", "y", "m", "s", "g", "lv", "pl", "mn", "lt", "fa", "w", "lb", "tg", "sr")
    return {k: [p[k] for p in points] for k in keys}
