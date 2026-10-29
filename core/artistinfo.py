"""What music databases say about each artist of your library: its genres and its labels.

Each source is asked once per artist, the artists that matter most first (most listened, then
most present in your playlists and favourite albums). Every source is an official API:

- Wikidata (no key): artists linked to their Deezer id (property P2722), so a namesake can never
  be taken for them. Genres, labels, and the MusicBrainz and Discogs ids. 300 artists a request.
- MusicBrainz (no key, 1 request a second): found through its link to the Deezer artist page,
  else through the ISRC of one of the artist's tracks (both exact). Curated genres and tags, and
  the Discogs id.
- Discogs (no key, 25 requests a minute; 60 with DISCOGS_TOKEN): the styles, genres and labels
  of the artist's most collected releases, by its Discogs id; with a token, by name as well.
- Last.fm (LASTFM_API_KEY, about 4 requests a second): the tags millions of listeners gave the
  artist, by MusicBrainz id when known, else by name. The widest coverage, niche artists included.

Genres go to `tags` (entity_type "artist", source = the database), labels to `tags` with
entity_type "artist_label"; identifiers and the dates each source was asked to `artist_info`.
The labels of the artist's Deezer albums are read from the albums themselves.
"""

from __future__ import annotations

import logging
import queue
import re
import threading
import time
from collections import Counter
from collections.abc import Callable

import requests
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.config import get_setting, redact
from core.db import insert_ignore
from core.models import Album, ArtistInfo, ArtistRelated, Artist, FavoriteAlbum, Play, PlaylistTrack, Tag, Track, utcnow

log = logging.getLogger(__name__)

AGENT = "DatAtlaSonore/1.0 (personal music statistics; https://github.com/theodorejl/Music-Data-Webapp)"
SOURCES = ("wikidata", "musicbrainz", "discogs", "lastfm")
NO_LABEL = {"not on label", "self-released", "[no label]", "none", "unknown", "independent"}


class SourceError(Exception):
    """A source that cannot be used now (bad key, blocked): the run goes on without it."""


class _Pace:
    """At most one request every `gap` seconds (shared by threads)."""

    def __init__(self, gap: float):
        self.gap, self.last, self.lock = gap, 0.0, threading.Lock()

    def wait(self) -> None:
        with self.lock:
            delay = self.gap - (time.monotonic() - self.last)
            if delay > 0:
                time.sleep(delay)
            self.last = time.monotonic()


SPOTIFY_ARTIST = re.compile(r"open\.spotify\.com/artist/([0-9A-Za-z]{22})")


def _store_spotify(session: Session, artist_id: int, ids: list[str], source: str) -> int:
    """Keep the Spotify artist ids (22 characters) a source gave for an artist; how many were kept."""
    ids = [i for i in dict.fromkeys(ids) if re.fullmatch(r"[0-9A-Za-z]{22}", i)]
    insert_ignore(session, Tag, [{"entity_type": "artist_spotify", "entity_id": artist_id, "tag": i, "count": None,
                                  "source": source} for i in ids], ["entity_type", "entity_id", "tag", "source"])
    return len(ids)


def _spotify_in(relations: list[dict]) -> list[str]:
    found = (SPOTIFY_ARTIST.search((r.get("url") or {}).get("resource", "")) for r in relations or [])
    return [m.group(1) for m in found if m]


def _clean_tag(tag: str) -> str:
    return re.sub(r"\s+", " ", str(tag)).strip()[:200]


# --- the sources --------------------------------------------------------------------------------------------

class Wikidata:
    URL = "https://query.wikidata.org/sparql"

    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": AGENT, "Accept": "application/sparql-results+json"})

    def lookup(self, deezer_ids: list[int]) -> dict[int, dict]:
        """{deezer id: {qid, mbid, discogs, genres, labels, spotify}} for the artists Wikidata links to Deezer."""
        values = " ".join(f'"{int(i)}"' for i in deezer_ids)
        query = f"""SELECT ?dz ?item (SAMPLE(?mb) AS ?mbid) (SAMPLE(?dg) AS ?discogs)
          (GROUP_CONCAT(DISTINCT ?sp; separator="|") AS ?spotify)
          (GROUP_CONCAT(DISTINCT ?gl; separator="|") AS ?genres) (GROUP_CONCAT(DISTINCT ?ll; separator="|") AS ?labels) WHERE {{
          VALUES ?dz {{ {values} }} ?item wdt:P2722 ?dz .
          OPTIONAL {{ ?item wdt:P434 ?mb }} OPTIONAL {{ ?item wdt:P1953 ?dg }} OPTIONAL {{ ?item wdt:P1902 ?sp }}
          OPTIONAL {{ ?item wdt:P136 ?g . ?g rdfs:label ?gl FILTER(lang(?gl) = "en") }}
          OPTIONAL {{ ?item wdt:P264 ?l . ?l rdfs:label ?ll FILTER(lang(?ll) = "en") }}
        }} GROUP BY ?dz ?item"""
        for attempt in range(3):
            try:
                resp = self.session.post(self.URL, data={"query": query}, timeout=90)
            except requests.RequestException:
                time.sleep(5 * (attempt + 1))
                continue
            if resp.status_code == 429:
                time.sleep(float(resp.headers.get("Retry-After") or 30))
                continue
            if resp.status_code != 200:
                raise SourceError(f"wikidata HTTP {resp.status_code}")
            out = {}
            for b in resp.json()["results"]["bindings"]:
                get = lambda k: b.get(k, {}).get("value")  # noqa: E731
                discogs = get("discogs")
                out[int(get("dz"))] = {"qid": get("item").rsplit("/", 1)[-1], "mbid": get("mbid"),
                                       "discogs": int(discogs) if discogs and discogs.isdigit() else None,
                                       "genres": [g for g in (get("genres") or "").split("|") if g],
                                       "labels": [lb for lb in (get("labels") or "").split("|") if lb],
                                       "spotify": [x for x in (get("spotify") or "").split("|") if x]}
            return out
        raise SourceError("wikidata unreachable")


class MusicBrainz:
    URL = "https://musicbrainz.org/ws/2"

    def __init__(self, session: requests.Session | None = None, contact: str | None = None):
        self.session = session or requests.Session()
        contact = contact or get_setting("MUSICBRAINZ_CONTACT", "personal project")
        self.session.headers.update({"User-Agent": f"{AGENT} ( {contact} )", "Accept": "application/json"})
        self.pace = _Pace(1.05)

    def _get(self, path: str, params: dict) -> dict | None:
        for attempt in range(3):
            self.pace.wait()
            try:
                resp = self.session.get(f"{self.URL}/{path}", params={**params, "fmt": "json"}, timeout=20)
            except requests.RequestException:
                time.sleep(2 * (attempt + 1))
                continue
            if resp.status_code == 404:
                return None
            if resp.status_code in (429, 503):
                time.sleep(3 * (attempt + 1))
                continue
            return resp.json() if resp.status_code == 200 else None
        return None

    def by_deezer(self, deezer_id: int) -> str | None:
        d = self._get("url", {"resource": f"https://www.deezer.com/artist/{deezer_id}", "inc": "artist-rels"})
        ids = [r["artist"]["id"] for r in (d or {}).get("relations", []) if r.get("artist")]
        return ids[0] if ids else None

    def by_isrc(self, isrc: str, name: str) -> str | None:
        """The artist credited first on the recordings with this ISRC, if its name matches."""
        from core.instamusic import similar

        d = self._get(f"isrc/{isrc}", {"inc": "artist-credits"})
        for rec in (d or {}).get("recordings", []):
            for credit in rec.get("artist-credit", [])[:2]:
                a = credit.get("artist") or {}
                if similar(a.get("name"), name) >= .85:
                    return a.get("id")
        return None

    def artist(self, mbid: str) -> dict | None:
        return self._get(f"artist/{mbid}", {"inc": "genres tags url-rels"})


class Discogs:
    URL = "https://api.discogs.com"

    def __init__(self, token: str | None = None, session: requests.Session | None = None):
        self.token = token if token is not None else get_setting("DISCOGS_TOKEN")
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = AGENT
        if self.token:
            self.session.headers["Authorization"] = f"Discogs token={self.token}"
        self.pace = _Pace(1.05 if self.token else 2.45)

    def _get(self, path: str, params: dict | None = None) -> dict | None:
        for attempt in range(4):
            self.pace.wait()
            try:
                resp = self.session.get(f"{self.URL}/{path}", params=params or {}, timeout=20)
            except requests.RequestException:
                time.sleep(3 * (attempt + 1))
                continue
            if resp.status_code == 429:
                time.sleep(20 * (attempt + 1))
                continue
            if resp.status_code == 401:
                raise SourceError("discogs token refused")
            if resp.status_code == 404:
                return None
            if resp.status_code != 200:
                time.sleep(3)
                continue
            return resp.json()
        return None

    def _release(self, item: dict) -> dict | None:
        rid = item.get("main_release") if item.get("type") == "master" else item.get("id")
        return self._get(f"releases/{rid}") if rid else None

    def by_id(self, discogs_id: int, releases: int = 2) -> dict:
        """Styles, genres and labels of the artist's most collected releases (as main artist)."""
        listing = self._get(f"artists/{discogs_id}/releases", {"sort": "year", "sort_order": "desc", "per_page": 100}) or {}
        items = [r for r in listing.get("releases", []) if r.get("role") == "Main"] or listing.get("releases", [])
        items.sort(key=lambda r: -(((r.get("stats") or {}).get("community") or {}).get("in_collection") or 0))
        styles, genres, labels = Counter(), Counter(), Counter()
        for item in items[:releases]:
            d = self._release(item) or {}
            styles.update(d.get("styles") or [])
            genres.update(d.get("genres") or [])
            labels.update(lb.get("name") for lb in d.get("labels") or [] if lb.get("name"))
        return {"styles": styles, "genres": genres, "labels": labels}

    def by_name(self, name: str) -> dict:
        """With a token: the styles, genres and labels of the releases found under that artist name."""
        from core.instamusic import similar

        d = self._get("database/search", {"artist": name, "type": "release", "per_page": 50}) or {}
        styles, genres, labels = Counter(), Counter(), Counter()
        for r in d.get("results", []):
            if similar(str(r.get("title", "")).split(" - ")[0], name) < .85:
                continue
            styles.update(r.get("style") or [])
            genres.update(r.get("genre") or [])
            labels.update((r.get("label") or [])[:1])
        return {"styles": styles, "genres": genres, "labels": labels}


class Lastfm:
    URL = "https://ws.audioscrobbler.com/2.0/"

    def __init__(self, key: str | None = None, session: requests.Session | None = None):
        self.key = key or get_setting("LASTFM_API_KEY")
        if not self.key:
            raise SourceError("no Last.fm key")
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = AGENT
        self.pace = _Pace(0.26)

    def top_tags(self, name: str, mbid: str | None = None) -> list[tuple[str, int]]:
        for by in ([{"mbid": mbid}] if mbid else []) + [{"artist": name}]:
            for attempt in range(3):
                self.pace.wait()
                try:
                    resp = self.session.get(self.URL, params={"method": "artist.gettoptags", "api_key": self.key,
                                                              "format": "json", "autocorrect": 1, **by}, timeout=20)
                    body = resp.json()
                except (requests.RequestException, ValueError):
                    time.sleep(2 * (attempt + 1))
                    continue
                error = body.get("error")
                if error in (10, 26):
                    raise SourceError("Last.fm key refused")
                if error == 29:
                    time.sleep(10)
                    continue
                if error:
                    break  # not found that way: try the next way
                tags = (body.get("toptags") or {}).get("tag") or []
                return [(t["name"], int(t.get("count") or 0)) for t in tags if int(t.get("count") or 0) >= 5][:12]
        return []


# --- which artists, in which order ------------------------------------------------------------------------------

def library_artists(session: Session) -> list[int]:
    """Every artist with a play, a track in a playlist or a favourite album: the most listened
    first, then the most present in the library."""
    listened = dict(session.execute(select(Track.artist_id, func.sum(Play.listened_seconds))
                                    .join(Play, Play.track_id == Track.id).where(Track.artist_id.is_not(None))
                                    .group_by(Track.artist_id)).all())
    in_lists = dict(session.execute(select(Track.artist_id, func.count()).join(PlaylistTrack, PlaylistTrack.track_id == Track.id)
                                    .where(Track.artist_id.is_not(None)).group_by(Track.artist_id)).all())
    favs = dict(session.execute(select(Album.artist_id, func.count()).join(FavoriteAlbum, FavoriteAlbum.album_id == Album.id)
                                .where(Album.artist_id.is_not(None)).group_by(Album.artist_id)).all())
    ids = set(listened) | set(in_lists) | set(favs)
    return sorted((int(a) for a in ids), key=lambda a: (-(listened.get(a) or 0), -(in_lists.get(a, 0) + 5 * favs.get(a, 0)), a))


# --- the run -----------------------------------------------------------------------------------------------------

def enrich(session: Session, deadline: float, wikidata: Wikidata | None = None, musicbrainz: MusicBrainz | None = None,
           discogs: Discogs | None = None, lastfm: Lastfm | None = None, public=None,
           progress: Callable[[str, int], None] | None = None) -> dict[str, int]:
    """Ask every source about the artists it has not been asked about yet, until the deadline.
    Returns how many artists each source answered for."""
    order = library_artists(session)
    infos = {i.artist_id: i for i in session.scalars(select(ArtistInfo)).all()}
    names = dict(session.execute(select(Artist.id, Artist.name)).all())
    done: Counter = Counter()

    def info(a: int) -> ArtistInfo:
        if a not in infos:
            infos[a] = ArtistInfo(artist_id=a, checked={})
            session.add(infos[a])
        return infos[a]

    def asked(a: int, source: str) -> bool:
        return source in ((infos.get(a).checked or {}) if a in infos else {})

    def mark(a: int, source: str) -> None:
        i = info(a)
        i.checked = {**(i.checked or {}), source: utcnow().isoformat()}

    def store(a: int, rows: list[tuple[str, int | None, str]], kind: str = "artist") -> None:
        insert_ignore(session, Tag, [{"entity_type": kind, "entity_id": a, "tag": _clean_tag(t), "count": c, "source": s}
                                     for t, c, s in rows if t and str(t).strip()], ["entity_type", "entity_id", "tag", "source"])

    # 1. Wikidata, many artists at once
    if wikidata is not None:
        todo = [a for a in order if not asked(a, "wikidata")]
        for k in range(0, len(todo), 300):
            if time.monotonic() > deadline:
                break
            batch = todo[k:k + 300]
            try:
                found = wikidata.lookup(batch)
            except SourceError as exc:
                log.warning("Artist info: %s", exc)
                break
            for a in batch:
                w = found.get(a)
                if w:
                    i = info(a)
                    i.wikidata, i.mbid = w["qid"], i.mbid or w["mbid"]
                    i.discogs_id = i.discogs_id or w["discogs"]
                    store(a, [(g, None, "wikidata") for g in w["genres"]])
                    store(a, [(lb, None, "wikidata") for lb in w["labels"]], "artist_label")
                    done["wikidata"] += 1
                    if _store_spotify(session, a, w.get("spotify") or [], "wikidata"):
                        mark(a, "spotify_wd")
                mark(a, "wikidata")
            session.commit()
            if progress:
                progress("wikidata", done["wikidata"])

    # 2. the others, each at its own pace, in threads; answers are written here
    results: queue.Queue = queue.Queue()

    def run(source: str, items: list[int], ask: Callable[[int], object]) -> None:
        for a in items:
            if time.monotonic() > deadline:
                break
            try:
                results.put((source, a, ask(a)))
            except SourceError as exc:
                log.warning("Artist info: %s", exc)
                break
            except Exception as exc:  # one artist must not stop the source
                log.warning("Artist info: %s failed for %s: %s", source, a, redact(exc))
                results.put((source, a, None))
        results.put((source, None, None))

    # what the threads need, read now (the session belongs to this thread)
    mbid_of = {a: i.mbid for a, i in infos.items() if i.mbid}
    discogs_of = {a: i.discogs_id for a, i in infos.items() if i.discogs_id}
    isrc_of = dict(session.execute(select(Track.artist_id, func.max(Track.isrc)).where(Track.isrc.is_not(None))
                                   .group_by(Track.artist_id)).all())
    track_of = dict(session.execute(select(Track.artist_id, func.min(Track.id)).where(Track.artist_id.is_not(None))
                                    .group_by(Track.artist_id)).all())
    workers = []
    if musicbrainz is not None:
        def ask_mb(a: int):
            mbid = mbid_of.get(a) or musicbrainz.by_deezer(a)
            if not mbid:
                isrc = isrc_of.get(a)
                if not isrc and public is not None and track_of.get(a):
                    isrc = (public.track(track_of[a]) or {}).get("isrc")
                mbid = musicbrainz.by_isrc(isrc, names.get(a) or "") if isrc else None
            return {"mbid": mbid, "artist": musicbrainz.artist(mbid) if mbid else None}
        workers.append(("musicbrainz", [a for a in order if not asked(a, "musicbrainz")], ask_mb))
    if discogs is not None:
        def ask_discogs(a: int):
            return discogs.by_id(discogs_of[a]) if a in discogs_of else discogs.by_name(names.get(a) or "")
        workers.append(("discogs", [a for a in order if not asked(a, "discogs") and (a in discogs_of or discogs.token)],
                        ask_discogs))
    if lastfm is not None:
        workers.append(("lastfm", [a for a in order if not asked(a, "lastfm")],
                        lambda a: lastfm.top_tags(names.get(a) or "", mbid_of.get(a))))

    threads = [threading.Thread(target=run, args=w, daemon=True) for w in workers]
    for t in threads:
        t.start()
    running, written = len(threads), 0
    while running:
        try:
            source, a, answer = results.get(timeout=max(1.0, deadline - time.monotonic() + 30))
        except queue.Empty:
            break
        if a is None:
            running -= 1
            continue
        if source == "musicbrainz" and answer:
            art = answer.get("artist") or {}
            if answer.get("mbid"):
                info(a).mbid = answer["mbid"]
            rows = [(g["name"], g.get("count"), "mb_genre") for g in art.get("genres") or []]
            rows += [(t["name"], t.get("count"), "mb_tag") for t in art.get("tags") or []]
            store(a, rows)
            for rel in art.get("relations") or []:
                m = re.search(r"discogs\.com/artist/(\d+)", (rel.get("url") or {}).get("resource", ""))
                if m:
                    info(a).discogs_id = info(a).discogs_id or int(m.group(1))
            if _store_spotify(session, a, _spotify_in(art.get("relations")), "musicbrainz"):
                mark(a, "spotify_mb")
            done["musicbrainz"] += bool(rows)
        elif source == "discogs" and answer:
            store(a, [(s, n, "discogs") for s, n in answer["styles"].items()] +
                  [(g, n, "discogs_genre") for g, n in answer["genres"].items()])
            store(a, [(lb, n, "discogs") for lb, n in answer["labels"].items() if lb.lower() not in NO_LABEL], "artist_label")
            done["discogs"] += bool(answer["styles"] or answer["genres"])
        elif source == "lastfm" and answer:
            store(a, [(t, n, "lastfm") for t, n in answer])
            done["lastfm"] += 1
        mark(a, source)
        written += 1
        if written % 20 == 0:
            session.commit()
            if progress:
                progress(source, done[source])
    session.commit()
    return dict(done)


def enrich_spotify_ids(session: Session, deadline: float, wikidata: Wikidata | None = None,
                       musicbrainz: MusicBrainz | None = None,
                       progress: Callable[[str, int], None] | None = None) -> dict[str, int]:
    """Backfill the Spotify artist ids: Wikidata for the artists it already answered about, then
    MusicBrainz for the artists with a MusicBrainz id. Each artist is asked once per source.
    Returns how many artists each source gave an id for."""
    order = library_artists(session)
    infos = {i.artist_id: i for i in session.scalars(select(ArtistInfo)).all()}
    done: Counter = Counter()

    def asked(a: int, source: str) -> bool:
        return a in infos and source in (infos[a].checked or {})

    def mark(a: int, source: str) -> None:
        infos[a].checked = {**(infos[a].checked or {}), source: utcnow().isoformat()}

    if wikidata is not None:
        todo = [a for a in order if asked(a, "wikidata") and not asked(a, "spotify_wd")]
        for k in range(0, len(todo), 300):
            if time.monotonic() > deadline:
                break
            batch = todo[k:k + 300]
            try:
                found = wikidata.lookup(batch)
            except SourceError as exc:
                log.warning("Artist info: %s", exc)
                break
            for a in batch:
                done["wikidata"] += bool(_store_spotify(session, a, (found.get(a) or {}).get("spotify") or [], "wikidata"))
                mark(a, "spotify_wd")
            session.commit()
            if progress:
                progress("wikidata", done["wikidata"])

    if musicbrainz is not None:
        todo = [a for a in order if a in infos and infos[a].mbid and not asked(a, "spotify_mb")]
        for n, a in enumerate(todo, 1):
            if time.monotonic() > deadline:
                break
            try:
                art = musicbrainz.artist(infos[a].mbid) or {}
            except Exception as exc:  # one artist must not stop the source
                log.warning("Artist info: musicbrainz failed for %s: %s", a, redact(exc))
                continue
            done["musicbrainz"] += bool(_store_spotify(session, a, _spotify_in(art.get("relations")), "musicbrainz"))
            mark(a, "spotify_mb")
            if n % 20 == 0:
                session.commit()
                if progress:
                    progress("musicbrainz", done["musicbrainz"])
        session.commit()
    return {k: v for k, v in done.items() if v}


def fetch_related(session: Session, public, deadline: float,
                  progress: Callable[[str, int], None] | None = None) -> int:
    """Store the artists Deezer lists as related to each artist of the library (rank 0 is the
    closest). Each artist is asked once. Returns how many artists were answered."""
    infos = {i.artist_id: i for i in session.scalars(select(ArtistInfo)).all()}
    done = 0
    for a in library_artists(session):
        if "deezer_related" in ((infos[a].checked or {}) if a in infos else {}):
            continue
        if time.monotonic() > deadline:
            break
        try:
            related = public.related(a)
        except Exception as exc:  # one artist must not stop the pass
            log.warning("Artist info: deezer related failed for %s: %s", a, redact(exc))
            continue
        rows, seen = [], set()
        for rank, r in enumerate(related):
            rid = r.get("id")
            if not isinstance(rid, int) or rid == a or rid in seen:
                continue
            seen.add(rid)
            rows.append({"artist_id": a, "related_id": rid, "rank": rank,
                         "related_name": (r.get("name") or "")[:300] or None})
        insert_ignore(session, ArtistRelated, rows, ["artist_id", "related_id"])
        if a not in infos:
            infos[a] = ArtistInfo(artist_id=a, checked={})
            session.add(infos[a])
        infos[a].checked = {**(infos[a].checked or {}), "deezer_related": utcnow().isoformat()}
        done += 1
        if done % 50 == 0:
            session.commit()
            if progress:
                progress("related", done)
    session.commit()
    return done


def labels_of(albums, links) -> dict[int, str]:
    """The label that released most of an artist's Deezer albums (albums: id, label;
    links: artist_id, album_id)."""
    label = {int(a): str(lb).strip() for a, lb in zip(albums["id"], albums["label"])
             if isinstance(lb, str) and lb.strip() and lb.strip().lower() not in NO_LABEL}
    votes: dict[int, Counter] = {}
    for a, al in zip(links["artist_id"], links["album_id"]):
        lb = label.get(int(al))
        if lb:
            votes.setdefault(int(a), Counter())[lb] += 1
    return {a: c.most_common(1)[0][0] for a, c in votes.items()}


def sources_from_settings() -> dict:
    """The sources that can be used with the settings at hand (Last.fm needs LASTFM_API_KEY)."""
    out = {"wikidata": Wikidata(), "musicbrainz": MusicBrainz(), "discogs": Discogs()}
    try:
        out["lastfm"] = Lastfm()
    except SourceError:
        pass
    return out


def enrich_from_settings(session: Session, public, deadline: float) -> int:
    """For the sync: one pass over every source available, until the deadline."""
    sources = sources_from_settings()
    total = sum(enrich(session, deadline, public=public, **sources).values())
    total += sum(enrich_spotify_ids(session, deadline, sources.get("wikidata"), sources.get("musicbrainz")).values())
    return total + fetch_related(session, public, deadline)
