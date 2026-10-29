"""From an Instagram account to a playlist: the music an account posts, found in the text of its
posts and in the sound of its videos, checked on Deezer, dated, linked to its post, and kept per
account.

Where the posts come from: the official Instagram Graph API ("Business Discovery"). Through your
own professional Instagram account it reads the public posts of any other professional account
(creator or business): captions, dates, links, and the video of each post or carousel slide. It
does not give the comments of other accounts' posts. Settings: IG_USER_ID and IG_ACCESS_TOKEN (see
the README). The token travels in a header, never in a URL, and never appears in a message or log.

How music is found in a post:
1. Text: every line of the caption (and of the comments, for a source that can read them) is read
   for "Artist - Title", "Title by Artist", Artist « Title », "« Title » de Artist", "Artist: … /
   Track: …", numbered tracklists and timestamps. Each candidate is checked on the public Deezer
   API: a track (both orders tried), else an album, kept only when artist and title both match
   closely. Text that is not music ("link in bio - out now") finds nothing and is dropped.
2. Sound: when a recognition service is configured (AUDD_API_TOKEN, AudD's official API), each
   video of the post (each slide of a carousel) is identified from its audio.

Each account's results live in data/instagram/<account>.json. A new run walks the posts from the
newest; the posts already read cost nothing, so it only reads what is new (and, once recognition is
turned on, the sound of videos it had only read the text of). `estimate()` predicts the posts to
read and the time; `run()` reports progress through a `Progress` object another thread can read.
"""

from __future__ import annotations

import json
import logging
import math
import re
import tempfile
import threading
import time
import unicodedata
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import quote

import requests

from core.config import ROOT, get_setting
from core.deezer_public import DeezerPublicClient

log = logging.getLogger(__name__)

GRAPH = "https://graph.facebook.com/v25.0"
AUDD = "https://api.audd.io/"
MIN_TRACKS, MAX_TRACKS = 10, 300
MAX_POSTS = 1500
PAGE = 25  # posts per request to Instagram
WORKERS = 4  # posts read at the same time
MAX_CANDIDATES = 30  # per post: enough for a long tracklist
SIMILAR = 0.72  # artist and title must both be at least this close to Deezer's
COLUMNS = ["key", "kind", "track_id", "title", "artist_name", "album_title", "cover", "link", "duration", "source",
           "line", "post_id", "post_link", "post_at"]
USERNAME = re.compile(r"^[A-Za-z0-9._]{1,30}$")


# --- settings and errors ------------------------------------------------------------------------------

class InstagramError(Exception):
    """kind: setup (no token), token (invalid or expired), account (your own Instagram account
    cannot be reached with the token: instagram_basic missing, or its Page not chosen),
    not_found (no such professional account), rate (hourly limit), network, invalid (bad name)."""

    def __init__(self, kind: str):
        super().__init__(kind)
        self.kind = kind


class RecognitionError(Exception):
    """kind: token (refused) or quota (no requests left)."""

    def __init__(self, kind: str):
        super().__init__(kind)
        self.kind = kind


def username_of(text: str | None) -> str | None:
    """'@name', 'name' or a profile link -> 'name'; None when it cannot be an Instagram account."""
    text = (text or "").strip()
    m = re.search(r"instagram\.com/([^/?#\s]+)", text)
    name = (m.group(1) if m else text).strip().lstrip("@").strip("/").lower()
    return name if USERNAME.match(name) and not name.startswith(".") and ".." not in name else None


def configured() -> dict[str, bool]:
    return {"instagram": bool(get_setting("IG_USER_ID") and get_setting("IG_ACCESS_TOKEN")),
            "audio": bool(get_setting("AUDD_API_TOKEN"))}


# --- posts ----------------------------------------------------------------------------------------------

@dataclass
class Post:
    id: str
    permalink: str
    taken_at: str  # ISO 8601, UTC
    caption: str = ""
    kind: str = "IMAGE"  # IMAGE, VIDEO or CAROUSEL_ALBUM
    videos: list[str] = field(default_factory=list)  # every video of the post, carousel slides included
    comments: list[str] = field(default_factory=list)  # only for a source that can read them


class GraphSource:
    """Official Instagram Graph API, Business Discovery."""

    reads_comments = False
    fields = "id,caption,media_type,media_url,permalink,timestamp,children{media_type,media_url}"

    def __init__(self, user_id: str | None = None, token: str | None = None, session: requests.Session | None = None,
                 timeout: float = 25.0):
        self.user_id = user_id or get_setting("IG_USER_ID")
        token = token or get_setting("IG_ACCESS_TOKEN")
        if not self.user_id or not token or not str(self.user_id).isdigit():
            raise InstagramError("setup")
        self.session = session or requests.Session()
        self.session.headers["Authorization"] = f"Bearer {token}"
        self.timeout = timeout

    def _get(self, fields: str) -> dict:
        for attempt in range(3):
            try:
                resp = self.session.get(f"{GRAPH}/{self.user_id}", params={"fields": fields}, timeout=self.timeout)
            except requests.RequestException:
                # the exception text could quote the request: only its kind is logged
                log.warning("Instagram: network error (attempt %d)", attempt + 1)
                time.sleep(2 * (attempt + 1))
                continue
            try:
                body = resp.json()
            except ValueError:
                body = {}
            error = body.get("error") if isinstance(body, dict) else None
            if not error and resp.ok:
                return body
            code, sub = (error or {}).get("code"), (error or {}).get("error_subcode")
            log.warning("Instagram: error code=%s subcode=%s status=%s", code, sub, resp.status_code)
            if code in (190, 102, 2500) or resp.status_code == 401:
                raise InstagramError("token")
            if code == 100 and sub == 33:  # every request is made on your own account: it is the one out of reach
                raise InstagramError("account")
            if code in (4, 17, 32, 613) or resp.status_code == 429:
                raise InstagramError("rate")
            if code in (10, 200) or (isinstance(code, int) and 200 <= code < 300):
                raise InstagramError("setup")
            if code in (100, 110) or resp.status_code in (400, 404):
                raise InstagramError("not_found")
            if resp.status_code >= 500:
                time.sleep(2 * (attempt + 1))
                continue
            raise InstagramError("network")
        raise InstagramError("network")

    def profile(self, username: str) -> dict:
        if not USERNAME.match(username):
            raise InstagramError("invalid")
        d = self._get(f"business_discovery.username({username})"
                      "{username,name,profile_picture_url,followers_count,media_count,biography}")
        b = d.get("business_discovery") or {}
        if not b:
            raise InstagramError("not_found")
        return {"username": b.get("username", username), "name": b.get("name") or username,
                "picture": b.get("profile_picture_url") or "", "followers": b.get("followers_count"),
                "media_count": b.get("media_count"), "bio": b.get("biography") or ""}

    def posts(self, username: str, limit: int) -> Iterator[list[Post]]:
        """The posts, newest first, one page at a time."""
        if not USERNAME.match(username):
            raise InstagramError("invalid")
        after, seen = None, 0
        while seen < limit:
            media = f"media.limit({min(PAGE, limit - seen)})" + (f".after({after})" if after else "")
            d = self._get(f"business_discovery.username({username}){{{media}{{{self.fields}}}}}")
            m = (d.get("business_discovery") or {}).get("media") or {}
            page = [self._post(item) for item in m.get("data", [])]
            if not page:
                return
            seen += len(page)
            yield page
            paging = m.get("paging") or {}
            after = (paging.get("cursors") or {}).get("after")
            if not after or not paging.get("next"):
                return

    @staticmethod
    def _post(item: dict) -> Post:
        kids = (item.get("children") or {}).get("data") or []
        videos = [c["media_url"] for c in kids if c.get("media_type") == "VIDEO" and c.get("media_url")]
        if item.get("media_type") == "VIDEO" and item.get("media_url"):
            videos.insert(0, item["media_url"])
        stamp = item.get("timestamp") or ""
        try:
            at = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%S%z").astimezone(timezone.utc).isoformat()
        except ValueError:
            at = stamp
        return Post(id=str(item.get("id")), permalink=item.get("permalink") or "", taken_at=at,
                    caption=item.get("caption") or "", kind=item.get("media_type") or "IMAGE", videos=videos)


# --- text: what looks like a track ---------------------------------------------------------------------

@dataclass(frozen=True)
class Candidate:
    artist: str
    title: str
    line: str


_BULLET = re.compile(r"^\s*(?:\(?\d{1,2}:\d{2}(?::\d{2})?\)?\s*[-–—]?\s*|#?\d{1,3}\s*[.)\]:/-]\s*|[A-H]\d{1,2}\s*[.):-]?\s+|"
                     r"[•·▪◦‣▶►▸➤→»*+-]\s*)+")
_PREFIX = re.compile(r"^\s*(?:now playing|np|track(?:\s*id)?|song|tune|music|sound|titre|morceau|chanson|musique|son|"
                     r"on the (?:deck|turntable|platter)|today'?s? (?:pick|record|selection|song|track)|record of the day|"
                     r"song of the day|disque du jour|son du jour|pépite du jour|ce soir|cover|pressage|selection|sélection)"
                     r"\s*[:：|-]\s*", re.I)
_TAIL = re.compile(r"\s*(?:[(\[][^()\[\]]*(?:\d{4}|records?|recordings|label|lp|ep|vinyl|reissue|pressing|edition|"
                   r"remaster(?:ed)?|music|disques|discos|7\"|12\"|45|33)[^()\[\]]*[)\]]|,\s*\d{4}|\s\d{4}$)\s*$", re.I)
_SPLIT = re.compile(r"\s+[-–—―~|]\s+|\s*[–—―]\s*")
_QUOTE_AFTER = re.compile(r"^(?P<artist>[^\"“”«»‘’]{2,60}?)\s*[,:–—-]?\s*[\"“«‘'](?P<title>[^\"“”«»‘’]{2,80})[\"”»’']")
_QUOTE_BEFORE = re.compile(r"[\"“«‘](?P<title>[^\"“”«»‘’]{1,80})[\"”»’]\s*,?\s+(?:by|de|par|from|of|von|di)\s+"
                           r"(?P<artist>[^,.;!?\n#@()]{2,60})", re.I)
_BY = re.compile(r"^(?P<title>[^,;!?]{1,80}?)\s+(?:by|par)\s+(?P<artist>[^,;!?#]{2,60})$", re.I)
_LABELLED = re.compile(r"^\s*(?P<k>artist|artiste|artistes|band|groupe|title|titre|track|song|morceau|album)\s*[:：]\s*(?P<v>.+)$",
                       re.I | re.M)
_NOT_MUSIC = re.compile(r"link in (?:the )?bio|lien en bio|lien dans la bio|out now|available (?:now|on|at)|dispo (?:sur|en)|"
                        r"pre-?order|pré-?commande|tickets? (?:on|now|here)|billets? (?:en|dispo)|giveaway|concours|"
                        r"follow (?:us|me|for|@)|abonne[- ]toi|subscribe|thank you (?:all|so much|for)|merci (?:à|a|pour|beaucoup)|"
                        r"swipe|tag a friend|\bdm\b|www\.|https?://|\.com\b", re.I)
_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍⃣]")
_EMOJI_RUN = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍⃣]+")


def _until_emoji(line: str) -> str:
    """Drop what follows an emoji once the line already names a track ("Artist - Title 🔁 again"),
    but keep going past an emoji in the middle of a name ("Air 🇫🇷 - La femme d'argent")."""
    pieces = [x for x in _EMOJI_RUN.split(line) if x.strip()]
    for k in range(1, len(pieces)):
        head = " ".join(pieces[:k]).strip()
        parts = _SPLIT.split(_BULLET.sub("", head), maxsplit=1)
        if (len(parts) == 2 and parts[0].strip() and parts[1].strip()) or re.search(r"[\"“«‘'].+[\"”»’']", head) \
                or re.search(r"\s(?:by|par|de)\s", head):
            return head
    return " ".join(pieces)


def _clean(part: str) -> str:
    part = re.sub(r"#\w+", "", part)
    part = re.sub(r"@([\w.]+)", lambda m: m.group(1).replace("_", " ").replace(".", " "), part)
    part = _EMOJI.sub("", part)
    part = re.sub(r"\s*[(\[][^()\[\]]*\b(?:19|20)\d{2}\b[^()\[\]]*[)\]].*$", "", part)  # "(Label, 1976)" and what follows
    for _ in range(2):
        part = _TAIL.sub("", part.strip())
    return part.strip(" \t\"'“”«»‘’*_,;:.-–—|/").strip()


def _plausible(artist: str, title: str) -> bool:
    if not (1 <= len(title) <= 90 and 2 <= len(artist) <= 70):
        return False
    if len(artist.split()) > 8 or len(title.split()) > 14:
        return False
    return title.lower() not in {"id", "unknown", "?", "tba", "tbc"} and artist.lower() not in {"id", "unknown", "va", "v.a."}


def candidates(text: str | None) -> list[Candidate]:
    """Every (artist, title) a text seems to name, in reading order, without duplicates."""
    out: list[Candidate] = []
    seen: set[tuple[str, str]] = set()

    def add(artist: str, title: str, line: str) -> None:
        artist, title = _clean(artist), _clean(title)
        key = (artist.lower(), title.lower())
        if _plausible(artist, title) and key not in seen:
            seen.add(key)
            out.append(Candidate(artist, title, line.strip()[:200]))

    text = text or ""
    labelled = {m.group("k").lower(): m.group("v").strip() for m in _LABELLED.finditer(text)}
    artist = next((labelled[k] for k in ("artist", "artiste", "artistes", "band", "groupe") if k in labelled), None)
    title = next((labelled[k] for k in ("track", "title", "titre", "song", "morceau", "album") if k in labelled), None)
    if artist and title:
        add(artist, title, f"{artist} — {title}")
    for raw in re.split(r"[\n\r]+|\s+[•·]\s+", text):
        line = _PREFIX.sub("", _BULLET.sub("", _until_emoji(raw)).strip()).strip()
        if len(line) < 4 or _LABELLED.match(line) or _NOT_MUSIC.search(line):
            continue
        if re.fullmatch(r"(?:[#@][\w.]+\s*)+", line):
            continue
        found = False
        for m in _QUOTE_BEFORE.finditer(line):
            add(m.group("artist"), m.group("title"), raw)
            found = True
        if not found and (m := _QUOTE_AFTER.match(line)) and not _SPLIT.search(m.group("artist")):
            add(m.group("artist"), m.group("title"), raw)
            found = True
        if not found and len(line) <= 160:
            parts = [p for p in _SPLIT.split(line) if p.strip()]
            if len(parts) >= 2:
                add(parts[0], parts[1], raw)
                found = True
        if not found and len(line) <= 120 and (m := _BY.match(line)):
            add(m.group("artist"), m.group("title"), raw)
        if len(out) >= MAX_CANDIDATES:
            break
    return out


# --- Deezer: is it really a track? ----------------------------------------------------------------------

def _norm(text: str | None) -> str:
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"\s*[(\[].*?[)\]]", " ", text)
    text = re.sub(r"\b(?:feat|ft|featuring|with)\b.*$", " ", text)
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    return re.sub(r"^the\s+", "", text)


def similar(a: str | None, b: str | None) -> float:
    """0..1: how close two names are, ignoring case, accents, punctuation, versions and 'feat.'."""
    x, y = _norm(a), _norm(b)
    if not x or not y:
        return 0.0
    if x == y:
        return 1.0
    cx, cy = x.replace(" ", ""), y.replace(" ", "")
    score = max(SequenceMatcher(None, x, y).ratio(), SequenceMatcher(None, cx, cy).ratio())
    short, long_ = sorted((cx, cy), key=len)
    if len(short) >= 4 and short in long_:
        score = max(score, 0.9)
    return score


def _row(kind: str, track: dict, album: dict | None = None) -> dict:
    album = album or track.get("album") or {}
    artist = (album if kind == "album" else track).get("artist") or track.get("artist") or {}
    return {"key": f"{kind}:{album.get('id') if kind == 'album' else track.get('id')}", "kind": kind,
            "track_id": int(track["id"]), "title": album.get("title") if kind == "album" else track.get("title"),
            "artist_name": artist.get("name"), "album_title": album.get("title") or "",
            "cover": album.get("cover_medium") or album.get("cover") or "",
            "link": (album if kind == "album" else track).get("link") or f"https://www.deezer.com/track/{track['id']}",
            "duration": int(track.get("duration") or 0)}


def _best(items: list[dict], artist: str, title: str, field: str) -> dict | None:
    best, score = None, 0.0
    for it in items or []:
        a = similar(artist, (it.get("artist") or {}).get("name"))
        t = max(similar(title, it.get(field)), similar(title, it.get("title")))
        if a >= SIMILAR and t >= SIMILAR and a + t > score:
            best, score = it, a + t
    return best


def _q(**fields: str) -> str:
    """An advanced Deezer search, e.g. artist:"Air" track:"Playground Love"."""
    return quote(" ".join(f'{k}:"{v.replace(chr(34), " ")}"' for k, v in fields.items()))


def match(client, cand: Candidate) -> dict | None:
    """The Deezer track (else album) a candidate names, or None. Tries artist/title, then the
    other way round (some captions say "Title - Artist"), then a plain search, then the albums."""
    tries = [(cand.artist, cand.title), (cand.title, cand.artist)]
    for artist, title in tries:
        hit = _best((client.get(f"search?q={_q(artist=artist, track=title)}&limit=10") or {}).get("data"),
                    artist, title, "title_short")
        if hit:
            return _row("track", hit)
    loose = (client.get(f"search?q={quote(cand.artist + ' ' + cand.title)}&limit=15") or {}).get("data")
    for artist, title in tries:
        hit = _best(loose, artist, title, "title_short")
        if hit:
            return _row("track", hit)
    hit = _best((client.get(f"search/album?q={_q(artist=cand.artist, album=cand.title)}&limit=8") or {}).get("data"),
                cand.artist, cand.title, "title")
    if hit:
        tracks = (client.get(f"album/{hit['id']}/tracks?limit=60") or {}).get("data") or []
        if tracks:  # its most popular track plays as the album's preview
            return _row("album", max(tracks, key=lambda x: x.get("rank") or 0), hit)
    return None


# --- sound: what is playing in a video -------------------------------------------------------------------

class AuddRecognizer:
    """AudD's official recognition API: reads the video from its link, answers artist and title
    (and the Deezer id when it knows it)."""

    def __init__(self, token: str | None = None, session: requests.Session | None = None, timeout: float = 60.0):
        self.token = token or get_setting("AUDD_API_TOKEN")
        if not self.token:
            raise RecognitionError("token")
        self.session = session or requests.Session()
        self.timeout = timeout

    def identify(self, media_url: str) -> dict | None:
        try:
            resp = self.session.post(AUDD, data={"api_token": self.token, "url": media_url, "return": "deezer"},
                                     timeout=self.timeout)
            body = resp.json()
        except (requests.RequestException, ValueError):
            log.warning("AudD: no answer")
            return None
        if body.get("status") != "success":
            code = (body.get("error") or {}).get("error_code")
            log.warning("AudD: error code=%s", code)
            if code == 900:
                raise RecognitionError("token")
            if code in (901, 902):
                raise RecognitionError("quota")
            return None
        res = body.get("result") or {}
        if not res.get("artist") or not res.get("title"):
            return None
        return {"artist": res["artist"], "title": res["title"], "deezer_id": (res.get("deezer") or {}).get("id")}


# --- progress, estimate, memory ---------------------------------------------------------------------------

class Progress:
    """Shared between the worker (writes) and the page (reads)."""

    def __init__(self, posts_planned: int, target: int):
        self.posts_planned = max(1, posts_planned)
        self.target = target
        self.posts_done = 0
        self.found = 0
        self.calls = 0
        self.step = "profile"
        self.detail = ""
        self.started = time.monotonic()
        self.finished = False
        self._lock = threading.Lock()

    def tick(self) -> None:
        with self._lock:
            self.calls += 1

    def post_done(self, total_found: int) -> None:
        with self._lock:
            self.posts_done += 1
            self.found = total_found

    @property
    def fraction(self) -> float:
        if self.finished:
            return 1.0
        return min(0.98, max(self.posts_done / self.posts_planned, self.found / max(1, self.target)))

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started


class _Counting:
    def __init__(self, client, progress: Progress | None):
        self.client, self.progress = client, progress

    def get(self, path: str):
        try:
            return self.client.get(path)
        finally:
            if self.progress:
                self.progress.tick()


SECONDS_PAGE = 1.6  # one request to Instagram (25 posts)
SECONDS_TEXT = 0.6  # the Deezer checks of one post, posts read 4 at a time
SECONDS_VIDEO = 1.8  # one recognition (about 6 s), 4 at a time


def _rates(state: dict | None, audio: bool) -> tuple[float, float]:
    """Tracks per post and videos per post: measured on this account when known, else typical."""
    posts = (state or {}).get("posts") or {}
    if len(posts) >= 12:
        per_post = len({r["key"] for r in state.get("tracks", [])}) / len(posts)
        videos = sum(p.get("videos", 0) for p in posts.values()) / len(posts)
        if audio and not all(p.get("audio") for p in posts.values()):
            per_post += 0.6 * videos  # the sound of their videos has not been heard yet
        return max(0.15, per_post), videos
    return (1.2 if audio else 0.8), 0.8


def estimate(n: int, state: dict | None = None, media_count: int | None = None, audio: bool = False) -> dict:
    """Posts to read (how many are new) and seconds, for `n` tracks."""
    n = max(MIN_TRACKS, min(MAX_TRACKS, int(n)))
    per_post, videos = _rates(state, audio)
    posts = min(MAX_POSTS, math.ceil(n / per_post), media_count or MAX_POSTS)
    done = (state or {}).get("posts") or {}
    ready = sum(1 for p in done.values() if p.get("audio") or not audio or not p.get("videos"))
    new = max(0, posts - ready)
    seconds = 2 + math.ceil(posts / PAGE) * SECONDS_PAGE + new * SECONDS_TEXT + (new * videos * SECONDS_VIDEO if audio else 0)
    return {"posts": posts, "new": new, "seconds": seconds}


def _store_dir() -> Path | None:
    for base in (ROOT / "data" / "instagram", Path(tempfile.gettempdir()) / "datatlasonore-instagram"):
        try:
            base.mkdir(parents=True, exist_ok=True)
            return base
        except OSError:
            continue
    return None


def load(username: str, folder: Path | None = None) -> dict:
    folder = folder or _store_dir()
    path = folder / f"{username}.json" if folder and USERNAME.match(username) else None
    if path and path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
    return {"username": username, "profile": {}, "posts": {}, "tracks": [], "runs": []}


def save(state: dict, folder: Path | None = None) -> None:
    folder = folder or _store_dir()
    if folder and USERNAME.match(state.get("username", "")):
        try:
            (folder / f"{state['username']}.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        except OSError:
            log.warning("Instagram: could not save the results")


def forget(username: str, folder: Path | None = None) -> None:
    folder = folder or _store_dir()
    if folder and USERNAME.match(username):
        (folder / f"{username}.json").unlink(missing_ok=True)


def accounts(folder: Path | None = None) -> list[dict]:
    """The accounts already read, most recent first."""
    folder = folder or _store_dir()
    out = []
    for path in (folder.glob("*.json") if folder else []):
        try:
            s = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        out.append({"username": s.get("username", path.stem), "name": (s.get("profile") or {}).get("name") or path.stem,
                    "picture": (s.get("profile") or {}).get("picture") or "", "posts": len(s.get("posts") or {}),
                    "tracks": len({r["key"] for r in s.get("tracks") or []}), "updated": s.get("updated") or ""})
    return sorted(out, key=lambda a: a["updated"], reverse=True)


def playlist(state: dict):
    """One row per track (or album): its most recent post, newest first, with how many posts named it."""
    import pandas as pd

    rows = pd.DataFrame(state.get("tracks") or [], columns=COLUMNS)
    if rows.empty:
        return rows.assign(posts=pd.Series(dtype=int))
    rows = rows.sort_values("post_at", ascending=False)
    counts = rows.groupby("key")["post_id"].nunique()
    out = rows.drop_duplicates("key").copy()
    out["posts"] = out["key"].map(counts).astype(int)
    return out.reset_index(drop=True)


# --- the run -----------------------------------------------------------------------------------------------

def _read(post: Post, client, recognizer, audio: bool, known: dict | None) -> tuple[list[dict], dict, str | None]:
    """The tracks of one post, its memory entry, and a recognition problem if there was one."""
    rows, keys, problem = [], set(), None
    entry = dict(known or {})

    def keep(row: dict | None, source: str, line: str) -> None:
        if row and row["key"] not in keys:
            keys.add(row["key"])
            rows.append({**row, "source": source, "line": line, "post_id": post.id, "post_link": post.permalink,
                         "post_at": post.taken_at})

    if not entry.get("text"):
        texts = [("caption", post.caption)] + [("comment", c) for c in post.comments]
        for source, text in texts:
            for cand in candidates(text):
                keep(match(client, cand), source, cand.line)
        entry["text"] = True
    if audio and post.videos and not entry.get("audio") and recognizer is not None:
        for url in post.videos:
            try:
                heard = recognizer.identify(url)
            except RecognitionError as exc:
                problem = exc.kind
                break
            if not heard:
                continue
            row = None
            if heard.get("deezer_id"):
                track = client.get(f"track/{heard['deezer_id']}")
                row = _row("track", track) if track and track.get("id") else None
            keep(row or match(client, Candidate(heard["artist"], heard["title"], "")), "audio",
                 f"{heard['artist']} — {heard['title']}")
        else:
            entry["audio"] = True
    entry.update({"at": post.taken_at, "link": post.permalink, "videos": len(post.videos), "kind": post.kind,
                  "excerpt": (post.caption or "")[:280]})
    return rows, entry, problem


def run(username: str, n: int, source=None, recognizer=None, client=None, progress: Progress | None = None,
        audio: bool = False, state: dict | None = None) -> dict:
    """Read the account's posts from the newest until `n` tracks are found (or the posts run out),
    reusing what is in memory. Returns the account's state (also on failure: what was read is kept,
    and the error is in state['error'])."""
    n = max(MIN_TRACKS, min(MAX_TRACKS, int(n)))
    state = state if state is not None else load(username)
    state.pop("error", None)
    started = time.monotonic()
    client = _Counting(client or DeezerPublicClient(timeout=12), progress)
    audio = audio and recognizer is not None
    try:
        source = source or GraphSource()
        state["profile"] = source.profile(username)
        plan = estimate(n, state, state["profile"].get("media_count"), audio)
        limit = min(MAX_POSTS, max(plan["posts"] * 3, 60), state["profile"].get("media_count") or MAX_POSTS)
        if progress:
            progress.posts_planned = max(1, plan["posts"])
            progress.step = "posts"
        keys_of: dict[str, set[str]] = {}
        for r in state["tracks"]:
            keys_of.setdefault(r["post_id"], set()).add(r["key"])
        here: set[str] = set()  # the tracks of the posts walked in this run
        with ThreadPoolExecutor(WORKERS) as pool:
            for page in source.posts(username, limit):
                todo = [p for p in page if not (state["posts"].get(p.id, {}).get("text")
                                                and (not audio or not p.videos or state["posts"][p.id].get("audio")))]
                if progress:
                    progress.step = "audio" if audio and any(p.videos for p in todo) else ("text" if todo else "memory")
                    progress.detail = page[-1].taken_at[:10]
                read = dict(zip([p.id for p in todo], pool.map(
                    lambda p: _read(p, client, recognizer, audio, state["posts"].get(p.id)), todo)))
                for post in page:
                    if post.id in read:
                        rows, entry, problem = read[post.id]
                        state["posts"][post.id] = entry
                        state["tracks"] += rows
                        keys_of.setdefault(post.id, set()).update(r["key"] for r in rows)
                        if problem:  # no recognition left: carry on with the text only
                            state["error"] = f"audio_{problem}"
                            audio = False
                    here |= keys_of.get(post.id, set())
                    if progress:
                        progress.post_done(len(here))
                    if len(here) >= n:
                        break
                if len(here) >= n:
                    break
    except InstagramError as exc:
        state["error"] = exc.kind
    finally:
        if progress:
            progress.finished = True
    state["updated"] = datetime.now(timezone.utc).isoformat()
    state.setdefault("runs", []).append({"at": state["updated"], "n": n, "audio": audio,
                                         "seconds": round(time.monotonic() - started, 1),
                                         "tracks": len({r["key"] for r in state["tracks"]})})
    state["runs"] = state["runs"][-20:]
    return state
