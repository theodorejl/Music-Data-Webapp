"""The map of sound: about 6,300 genres placed by Every Noise at Once (see
scripts/build_genre_map.py), and where your music sits on it.

- `match(tag)` turns a MusicBrainz tag or a Deezer genre into a genre of the map.
- `artist_genres()` gives each artist its genres (MusicBrainz tags of the artist, then of its
  albums, then its Deezer genre), weighted.
- `territory()` sums them over your listening: the genres you live in, and how much.
- `frontier()` finds the genres around your territory that you do not listen to yet: the
  "adjacent possible" where real discoveries are, nearer or further depending on the boldness.

Coordinates are in pixels of the original map (1500 wide, 22648 tall), so distances stay true
to how far two sounds are; the page scales them to the screen.
"""

from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd

ASSET = Path(__file__).resolve().parents[1] / "app" / "assets" / "genre_map.json"
WIDTH, HEIGHT = 1500.0, 22648.0

# MusicBrainz tags that name the same thing as a genre of the map under another spelling.
SYNONYMS = {
    "electronic": "electronica", "dance": "dance pop", "idm": "intelligent dance music", "french house": "filter house",
    "french touch": "new french touch", "french electro": "new french touch", "lo-fi hip hop": "lo-fi beats",
    "lofi hip hop": "lo-fi beats", "alternative/indie rock": "indie rock", "indie dance": "indietronica",
    "indie electronic": "indietronica", "progressive pop": "art pop", "modern classical": "neo-classical",
    "contemporary classical": "contemporary classical", "melodic house": "deep house", "left-field house": "deep house",
    "jackin house": "chicago house", "latin": "latin pop", "dance and electronica": "electronica", "film score": "soundtrack",
    "alternative": "alternative rock", "hiphop": "hip hop", "rnb": "r&b", "electropop": "electropop", "chillout": "chillout",
    "chill out": "chillout", "chill": "chillwave", "nu-disco": "nu disco", "drum & bass": "drum and bass", "dnb": "drum and bass",
    "synthpop": "synthpop", "singer-songwriter": "singer-songwriter", "soundtrack": "soundtrack", "trip-hop": "trip hop",
}
# Deezer's broad genres, anchored on the map where that family is centred.
DEEZER = {
    "pop": "pop", "rap/hip hop": "hip hop", "rock": "rock", "dance": "dance pop", "r&b": "r&b", "alternative": "alternative rock",
    "electro": "electronica", "folk": "folk", "reggae": "reggae", "jazz": "jazz", "classical": "classical",
    "films/games": "soundtrack", "metal": "metal", "soul & funk": "soul", "african music": "afropop", "asian music": "k-pop",
    "blues": "blues", "brazilian music": "mpb", "indian music": "filmi", "kids": "children's music", "latin music": "latin pop",
    "country": "country", "chanson française": "chanson", "variété française": "variete francaise", "techno/house": "house",
}
BROAD_NAMES = set(DEEZER.values()) | {"electronica", "electronic", "edm", "electro", "dance", "indie", "alternative rock",
                                      "pop", "rock", "hip hop", "rap", "classical", "jazz", "soul", "funk", "folk"}
IGNORED = {"french", "british", "european", "france", "english", "american", "usa", "uk", "german", "instrumental",
           "seen live", "male vocalists", "female vocalists", "club", "music", "favorites", "favourite"}


@dataclass(frozen=True)
class Genre:
    name: str
    color: str
    x: float  # pixels, 0..1500
    y: float  # pixels, 0..22648
    rank: int  # 1 = most popular genre
    size: int  # label size on Every Noise (100..160)


def _key(text: str) -> str:
    text = text.lower().replace("&", " and ").replace("'", "")
    return re.sub(r"[^a-z0-9]+", "", text.replace(" and ", "n"))


@lru_cache(maxsize=1)
def genres() -> tuple[Genre, ...]:
    data = json.loads(ASSET.read_text(encoding="utf-8"))
    return tuple(Genre(n, c, x * WIDTH, y * HEIGHT, r, s) for n, c, x, y, r, s in data["genres"])


@lru_cache(maxsize=1)
def _index() -> dict[str, Genre]:
    return {_key(g.name): g for g in genres()}


def by_name(name: str) -> Genre | None:
    return _index().get(_key(name))


def match(tag: str | None) -> Genre | None:
    """A genre of the map for a MusicBrainz tag or a Deezer genre, or None."""
    if not isinstance(tag, str) or not tag.strip():
        return None
    t = tag.strip().lower()
    if t in IGNORED:
        return None
    for candidate in (DEEZER.get(t), SYNONYMS.get(t), t, t.replace("-", " "), t.replace(" music", "")):
        if candidate:
            g = by_name(candidate)
            if g:
                return g
    return None


def distance(a: Genre, b: Genre) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def artist_genres(plays: pd.DataFrame, tags: pd.DataFrame | None) -> dict[int, list[tuple[Genre, float]]]:
    """For each artist in `plays`: its genres of the map with weights summing to 1."""
    out: dict[int, dict[str, float]] = defaultdict(dict)
    found: dict[str, Genre] = {}

    def add(aid: int, g: Genre | None, w: float) -> None:
        if g:
            found[g.name] = g
            out[aid][g.name] = out[aid].get(g.name, 0.0) + w

    if tags is not None and not tags.empty:
        art = tags[tags["entity_type"] == "artist"]
        for r in art.itertuples(index=False):
            add(int(r.entity_id), match(r.tag), float(r.count) if pd.notna(r.count) and r.count else 1.0)
        album_of = plays.dropna(subset=["album_id", "artist_id"]).drop_duplicates("album_id").set_index("album_id")["artist_id"]
        alb = tags[tags["entity_type"] == "album"]
        for r in alb.itertuples(index=False):
            aid = album_of.get(r.entity_id)
            if aid is not None and not out.get(int(aid)):
                add(int(aid), match(r.tag), 0.5 * (float(r.count) if pd.notna(r.count) and r.count else 1.0))
    deezer = plays.dropna(subset=["artist_id", "genre"]).groupby("artist_id")["genre"].agg(lambda s: s.mode().iloc[0])
    for aid, genre in deezer.items():
        if not out.get(int(aid)):
            add(int(aid), match(genre), 1.0)
    result = {}
    for aid, weights in out.items():
        total = sum(weights.values()) or 1.0
        best = sorted(weights.items(), key=lambda kv: -kv[1])[:6]
        result[aid] = [(found[name], w / total) for name, w in best]
    return result


def territory(plays: pd.DataFrame, by_artist: dict[int, list[tuple[Genre, float]]]) -> list[tuple[Genre, float]]:
    """Your genres of the map, weighted by listening time (sum to 1), strongest first."""
    minutes = plays.dropna(subset=["artist_id"]).groupby("artist_id")["minutes"].sum()
    acc: dict[str, float] = defaultdict(float)
    found: dict[str, Genre] = {}
    for aid, m in minutes.items():
        for g, w in by_artist.get(int(aid), []):
            acc[g.name] += float(m) * w
            found[g.name] = g
    total = sum(acc.values()) or 1.0
    return [(found[n], v / total) for n, v in sorted(acc.items(), key=lambda kv: -kv[1])]


# Words that make a genre regional ("finnish dance pop"): left out unless you already listen there.
REGIONS = set("""musica japanese german russian italian swedish canadian australian brazilian polish indonesian finnish french
spanish chinese dutch irish korean norwegian turkish british south danish belgian musique mexican thai greek czech
ukrainian swiss pinoy indian lagu scottish american nz portuguese icelandic taiwan israeli hungarian austrian argentine
romanian persian malaysian muzica west nordic bulgarian lithuanian north vietnamese balkan slovak southern colombian
arab texas boston singaporean folclore estonian czsk peruvian croatian native african belarusian latvian slovenian
macedonian memphis kentucky pakistani chilean albanian welsh magyar malayalam marathi serbian kenyan telugu baltic
georgian puerto tamil pittsburgh egyptian melbourne turkce nashville ghanaian quebec kurdish san viet austin euskal igbo
tibetan faroese luxembourgian punjabi desi miami florida philly venezuelan birmingham arkansas minneapolis alabama
canzone atlanta virginia kazakh portland sinhala jewish azeri hong palestinian kannada cuban cape ugandan mongolian
armenian galician afrikaans rwandan east tennessee nyc cancion moldovan bolivian ecuadorian uruguayo uruguayan
paraguayan nigerian ivorian congolese senegalese malian cameroonian zambian zimbabwean tanzanian ethiopian somali
sudanese moroccan algerian tunisian lebanese syrian iraqi saudi emirati kuwaiti yemeni omani qatari bahraini
afghan nepali bangladeshi bengali hindi urdu gujarati odia assamese burmese khmer lao filipino cebuano hawaiian
maori samoan tongan fijian aussie oklahoma ohio michigan wisconsin iowa kansas missouri louisiana mississippi georgia
carolina ontario alberta vancouver toronto montreal seattle denver dallas houston phoenix vegas brooklyn bronx
jersey baltimore dc bay oakland la socal norcal sacramento chico hamburg berlin munich vienna zurich basel geneva
lyon marseille bordeaux paris belgrade sofia warsaw krakow prague budapest bucharest athens istanbul cairo tehran
dubai mumbai delhi chennai kolkata karachi lahore dhaka bangkok jakarta manila hanoi saigon taipei seoul tokyo
osaka beijing shanghai shenzhen cantonese mandopop yugoslav xitsonga zulu xhosa swahili yoruba hausa tagalog basque
breton sami inuit quechua aymara manx czech slovak greek thai lao dutch welsh okc nola atl dmv socal cristao cristiano
grupero dangdut shabad qawwali bhajan kirtan gamelan andaluz tico favela""".split())
# Style words that merely look like nationalities ("christian", "urban", "lo-fi").
NOT_REGIONS = {"christian", "urban", "suburban", "pagan", "lo-fi", "hi-fi", "sci-fi", "kawaii", "mini", "taxi", "spoken", "outsider",
               "sertanejo", "italo", "afro", "latin", "celtic", "nordic", "balkan", "baltic", "andean", "caribbean",
               "medieval", "renaissance", "victorian", "baroque", "persian", "arabesque"}
STYLE_PLACES = {"detroit", "chicago", "uk", "new", "acid", "italo", "balearic", "ibiza", "goa", "berlin"}


def _is_region(t: str) -> bool:
    if t in STYLE_PLACES or t in NOT_REGIONS:
        return False
    return t in REGIONS or (len(t) > 4 and t.endswith(("ian", "ese", "ish", "an", "i", "ean", "ois", "ville", "ano", "ana",
                                                       "eiro", "eira", "ense", "ais", "aise", "ien", "ienne", "ese", "ijo")))


# boldness: how far from home the frontier reaches (map pixels) and how obscure a genre may be
REACH = {"familiar": (450.0, 1500), "balanced": (950.0, 3500), "bold": (1500.0, 6300)}
BROAD = 60  # the 60 most popular genres (pop, rock, rap...) are too broad to anchor a search


def is_broad(g: Genre) -> bool:
    """Umbrella genres: the most popular ones and the anchors of Deezer's own genres
    (electronica, dance pop, alternative rock, classical, jazz...). Their surroundings on the
    map mean nothing; precise sub-genres (deep house, dub techno...) are what guide discovery."""
    return g.rank <= BROAD or g.name in BROAD_NAMES


GENERIC_HEADS = {"indie", "rock", "pop", "rap", "punk", "metal", "folk", "hardcore", "jazz", "blues", "country", "r&b", "soul",
                 "reggae", "emo", "ska", "gospel", "worship", "drill", "trap", "singer-songwriter", "hip"}


@lru_cache(maxsize=1)
def _word_counts() -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for g in genres():
        for w in set(_words(g.name)):
            counts[w] += 1
    return counts


def _local_scene(name: str, allowed: set[str]) -> bool:
    """"sheffield indie", "kc indie": a rare first word before a generic head is a place."""
    words = _words(name)
    if len(words) < 2 or words[0] in allowed:
        return False
    head = words[-1] if words[-1] != "hop" else "hip"
    return head in GENERIC_HEADS and _word_counts().get(words[0], 0) < 4


def _words(name: str) -> list[str]:
    return [t for t in re.split(r"[\s/]+", name.lower()) if t]


def _tokens(name: str) -> set[str]:
    return {t for t in _words(name) if not _is_region(t)}


def _regions(name: str) -> set[str]:
    return {t for t in _words(name) if _is_region(t)}


def frontier(home: list[tuple[Genre, float]], boldness: str, count: int) -> list[tuple[Genre, float, Genre]]:
    """Genres you do not listen to yet, around your territory: (genre, score, the home genre it
    grows from), best first. A genre counts when it is a relative of a home genre (shares a
    word: house, techno, jazz...) and/or lies close to it on the map; familiar stays with
    relatives nearby, bold goes further, to cousins and strangers. Broad home genres (pop,
    electronica) pull less than precise ones, and regional variants are left out unless you
    already listen to that region. At most three genres per family, for variety."""
    reach, max_rank = REACH.get(boldness, REACH["balanced"])
    own = {g.name for g, _ in home}
    allowed = set().union(*(_regions(g.name) for g, _ in home)) if home else set()
    home_words = set().union(*(_words(g.name) for g, _ in home)) if home else set()
    # precise genres anchor the search; broad ones (pop, electronica...) only when nothing else
    precise = [(g, w) for g, w in home[:40] if not is_broad(g)]
    anchors = precise if len(precise) >= 3 else home[:30]
    total = sum(w for _, w in anchors) or 1.0
    anchors = [(g, w / total, _tokens(g.name), not is_broad(g)) for g, w in anchors]
    best: dict[str, tuple[float, Genre]] = {}
    for g in genres():
        if g.name in own or g.rank > max_rank or (_regions(g.name) - allowed) or _local_scene(g.name, home_words):
            continue
        tg = _tokens(g.name)
        if not tg:
            continue
        for h, w, th, fine in anchors:
            d = distance(g, h) if fine else reach * 2  # a broad genre's surroundings mean nothing
            if not fine and not (tg & th):
                continue
            if fine and d > reach * 1.4:
                continue
            close = max(0.0, 1 - d / reach)
            kin = len(tg & th) / len(tg | th) if th else 0.0
            if boldness == "familiar":
                if not kin:
                    continue
                sim = 0.65 * kin + 0.35 * close
            elif boldness == "balanced":
                if not kin and close < 0.7:
                    continue
                sim = 0.5 * kin + 0.5 * close
            else:  # bold: further, but still within earshot of home
                if close < 0.25 and not kin:
                    continue
                sim = 0.4 * kin + 0.6 * max(0.0, 1 - 1.6 * abs(d / reach - 0.5)) if fine else 0.4 * kin
            score = w * sim
            if score > best.get(g.name, (0.0, None))[0]:
                best[g.name] = (score, h)
    by = {g.name: g for g in genres()}
    # variety: at most three genres per family, and each home genre opens its own paths
    per_home = max(2, math.ceil(count / max(1, min(len(anchors), 6))))
    out, families, homes = [], defaultdict(int), defaultdict(int)
    for name, (score, h) in sorted(best.items(), key=lambda kv: -kv[1][0]):
        family = name.split()[-1]
        if families[family] >= 3 or homes[h.name] >= per_home:
            continue
        families[family] += 1
        homes[h.name] += 1
        out.append((by[name], score, h))
        if len(out) >= count:
            break
    return out


def place(genres_of: list[tuple[Genre, float]] | None) -> tuple[float, float] | None:
    """Where an artist sits: on its main genre (a mix of distant genres would land nowhere)."""
    if not genres_of:
        return None
    g = genres_of[0][0]
    return g.x, g.y


# --- regions of the map ------------------------------------------------------------------------------

ASPECT = 1.6  # the map is drawn 1.6 times wider than tall; regions are cut in that same space


SPECIAL_CASE = {"r&b": "R&B", "edm": "EDM", "idm": "IDM", "k-pop": "K-pop", "j-pop": "J-pop", "uk": "UK", "dnb": "DnB",
                "mpb": "MPB", "lo-fi": "Lo-fi", "hip hop": "Hip hop", "drum and bass": "Drum and bass"}


def display(name: str) -> str:
    """A genre or region name as a title ("deep house" -> "Deep house", "r&b" -> "R&B")."""
    if name in SPECIAL_CASE:
        return SPECIAL_CASE[name]
    return " ".join(SPECIAL_CASE.get(w, w) for w in name.split()).capitalize() if name else name


HEAD_IGNORED = {"era", "music", "standards", "group", "recitation", "classics", "covers", "instrumental", "kids", "show"}


def _head(name: str) -> str | None:
    for tail in ("hip hop", "drum and bass", "r&b", "singer-songwriter"):
        if name.endswith(tail):
            return tail
    words = [w for w in _words(name) if not _is_region(w)]
    return words[-1] if words else None


def _name_regions(of, k: int, rank, two_heads: bool) -> list[str]:
    """Large regions: their two leading genre families ("House & techno"); small regions: their
    most popular genre that is not a regional variant."""
    gs = genres()
    names, used = [], set()
    for j in range(k):
        members = [i for i in range(len(gs)) if of[i] == j]
        members.sort(key=lambda i: rank[i])
        plain = [i for i in members if not _regions(gs[i].name)] or members
        if not two_heads:
            names.append(display(gs[plain[0]].name) if plain else "")
            continue
        heads: dict[str, float] = defaultdict(float)
        for i in plain:
            h = _head(gs[i].name)
            if h and h not in IGNORED and h not in HEAD_IGNORED:
                heads[h] += 1 / math.sqrt(rank[i])
        top = [h for h, _ in sorted(heads.items(), key=lambda kv: -kv[1])]
        label = None
        for a in range(len(top)):
            for b in range(a + 1, min(len(top), a + 4)):
                pair = (top[a], top[b])
                if pair not in used:
                    label = pair
                    break
            if label:
                break
        label = label or ((top[0],) if top else (gs[plain[0]].name,))
        used.add(label)
        names.append(" & ".join(display(h) for h in label))
    return names


@lru_cache(maxsize=4)
def hierarchy(levels: tuple[int, ...] = (14, 110)) -> dict:
    """Group the genres into nested regions by where they sit on the map (k-means, fixed seed):
    a few large families, then smaller ones, each named after its most popular genre.
    Returns {"levels": [{"names": [...], "cx": [...], "cy": [...], "of": [region of each genre]}, ...]}."""
    import numpy as np

    gs = genres()
    pts = np.array([[g.x / WIDTH * ASPECT, g.y / HEIGHT] for g in gs])
    rank = np.array([g.rank for g in gs])
    out = []
    rng = np.random.default_rng(7)
    for k in levels:
        # k-means++ start, then Lloyd iterations
        centres = [pts[int(np.argmin(rank))]]
        for _ in range(1, k):
            d = np.min(((pts[:, None, :] - np.array(centres)[None, :, :]) ** 2).sum(-1), axis=1)
            centres.append(pts[rng.choice(len(pts), p=d / d.sum())])
        c = np.array(centres)
        for _ in range(40):
            of = np.argmin(((pts[:, None, :] - c[None, :, :]) ** 2).sum(-1), axis=1)
            new = np.array([pts[of == j].mean(axis=0) if (of == j).any() else c[j] for j in range(k)])
            if np.allclose(new, c):
                break
            c = new
        of = np.argmin(((pts[:, None, :] - c[None, :, :]) ** 2).sum(-1), axis=1)
        names = _name_regions(of, k, rank, two_heads=k <= 30)
        out.append({"names": names, "cx": (c[:, 0] / ASPECT).round(5).tolist(), "cy": c[:, 1].round(5).tolist(),
                    "of": of.astype(int).tolist()})
    return {"levels": out}
