"""Instagram account -> playlist, with a fake Instagram, a fake Deezer and a fake recognizer."""

from urllib.parse import parse_qs, unquote, urlparse

import pytest

from core import instamusic as im

CATALOGUE = [  # Deezer tracks the fake API knows
    {"id": 1, "title": "Maria También", "title_short": "Maria También", "duration": 200, "rank": 500,
     "artist": {"id": 10, "name": "Khruangbin"}, "album": {"id": 100, "title": "Con Todo El Mundo", "cover_medium": "c1"}},
    {"id": 2, "title": "Nautilus", "title_short": "Nautilus", "duration": 300, "rank": 400,
     "artist": {"id": 20, "name": "Bob James"}, "album": {"id": 200, "title": "One", "cover_medium": "c2"}},
    {"id": 3, "title": "Says", "title_short": "Says", "duration": 500, "rank": 300,
     "artist": {"id": 30, "name": "Nils Frahm"}, "album": {"id": 300, "title": "Spaces", "cover_medium": "c3"}},
    {"id": 4, "title": "Water No Get Enemy", "title_short": "Water No Get Enemy", "duration": 600, "rank": 200,
     "artist": {"id": 40, "name": "Fela Kuti"}, "album": {"id": 400, "title": "Expensive Shit", "cover_medium": "c4"}},
]


class FakeDeezer:
    def __init__(self):
        self.calls = []

    def get(self, path):
        self.calls.append(path)
        if path.startswith("track/"):
            return next((t for t in CATALOGUE if t["id"] == int(path.split("/")[1])), None)
        if path.startswith("search?") or path.startswith("search/album?"):
            q = unquote(parse_qs(urlparse(path).query)["q"][0]).lower()
            if path.startswith("search/album"):
                return {"data": []}
            return {"data": [t for t in CATALOGUE if t["artist"]["name"].lower().split()[0] in q
                             and t["title"].lower().split()[0] in q]}
        return None


class FakeSource:
    reads_comments = False

    def __init__(self, posts):
        self._posts, self.pages = posts, 0

    def profile(self, username):
        return {"username": username, "name": "Delicious", "picture": "", "followers": 1000, "media_count": len(self._posts)}

    def posts(self, username, limit):
        for i in range(0, min(limit, len(self._posts)), 2):  # pages of 2
            self.pages += 1
            yield self._posts[i:i + 2]


class FakeRecognizer:
    def __init__(self, answers, quota_after=None):
        self.answers, self.heard, self.quota_after = answers, [], quota_after

    def identify(self, url):
        if self.quota_after is not None and len(self.heard) >= self.quota_after:
            raise im.RecognitionError("quota")
        self.heard.append(url)
        return self.answers.get(url)


def post(i, caption="", videos=()):
    return im.Post(id=str(i), permalink=f"https://www.instagram.com/p/P{i}/", taken_at=f"2026-10-{30 - i:02d}T12:00:00+00:00",
                   caption=caption, kind="CAROUSEL_ALBUM" if len(videos) > 1 else ("VIDEO" if videos else "IMAGE"),
                   videos=list(videos))


POSTS = [post(1, "🎶 Khruangbin – Maria También\n#vinyl"),
         post(2, "Today's pick: “Nautilus” by Bob James (CTI, 1974)"),
         post(3, "New video out now - link in bio ✨", videos=["v3"]),
         post(4, "Carrousel du jour 💿", videos=["v4a", "v4b"]),
         post(5, "@nilsfrahm - Says\nKhruangbin - Maria También")]


def test_account_names():
    assert im.username_of("@Nabi_La_Fille") == "nabi_la_fille"
    assert im.username_of("https://www.instagram.com/maslowunknown/?hl=fr") == "maslowunknown"
    assert im.username_of("delicieusemusique") == "delicieusemusique"
    assert im.username_of("not a name") is None and im.username_of("a){b}") is None and im.username_of("") is None


def test_candidates_read_the_usual_ways_of_naming_a_track():
    pairs = lambda text: [(c.artist, c.title) for c in im.candidates(text)]  # noqa: E731
    assert pairs("1. Air - La femme d'argent\n2) Phoenix — 1901\n00:00 Larry Heard - Can You Feel It") == [
        ("Air", "La femme d'argent"), ("Phoenix", "1901"), ("Larry Heard", "Can You Feel It")]
    assert pairs("Jean-Michel Jarre - Oxygène, Pt. 4 (Disques Dreyfus, 1976) quel disque") == [("Jean-Michel Jarre", "Oxygène, Pt. 4")]
    assert pairs("Ce soir : « La Javanaise » de Serge Gainsbourg") == [("Serge Gainsbourg", "La Javanaise")]
    assert pairs("Mulatu Astatke 'Yègellé Tezeta' 🇪🇹") == [("Mulatu Astatke", "Yègellé Tezeta")]
    assert pairs("Khruangbin - Maria También 🔁 encore elle\nAir 🇫🇷 - La femme d'argent") == [
        ("Khruangbin", "Maria También"), ("Air", "La femme d'argent")]
    assert pairs("Artist: Fela Kuti\nTrack: Water No Get Enemy") == [("Fela Kuti", "Water No Get Enemy")]
    assert pairs("New video out now - link in bio\n#house #vinyl\nFollow the Leader - Eric B. & Rakim") == [
        ("Follow the Leader", "Eric B. & Rakim")]  # the other way round is tried on Deezer


def test_similarity_ignores_case_accents_versions_and_spaces():
    assert im.similar("nilsfrahm", "Nils Frahm") > 0.9
    assert im.similar("Oxygene pt 4", "Oxygène, Pt. 4 (Remastered)") == 1.0
    assert im.similar("Daft Punk", "Air") < 0.5


def test_match_checks_both_names_and_both_orders():
    client = FakeDeezer()
    hit = im.match(client, im.Candidate("Nautilus", "Bob James", ""))  # "Title - Artist"
    assert hit["track_id"] == 2 and hit["artist_name"] == "Bob James" and hit["key"] == "track:2"
    assert im.match(client, im.Candidate("Bob James", "Some Other Song", "")) is None


def test_run_reads_new_posts_only_and_keeps_the_playlist_by_date(tmp_path):
    client, source = FakeDeezer(), FakeSource(POSTS)
    state = im.run("delicieusemusique", 10, source=source, client=client, state=im.load("delicieusemusique", tmp_path))
    assert "error" not in state and len(state["posts"]) == 5 and state["profile"]["name"] == "Delicious"
    pl = im.playlist(state)
    assert list(pl["track_id"]) == [1, 2, 3]  # newest post first; Khruangbin is named twice, kept once
    first = pl.iloc[0]
    assert first["post_link"] == "https://www.instagram.com/p/P1/" and first["posts"] == 2 and first["source"] == "caption"
    im.save(state, tmp_path)
    again = im.run("delicieusemusique", 10, source=FakeSource(POSTS), client=(c2 := FakeDeezer()),
                   state=im.load("delicieusemusique", tmp_path))
    assert c2.calls == [] and len(im.playlist(again)) == 3  # everything came from memory
    assert im.accounts(tmp_path)[0]["tracks"] == 3


def test_run_walks_no_further_than_it_may(tmp_path):
    many = [post(i, "Khruangbin – Maria También" if i % 2 else "Bob James - Nautilus") for i in range(1, 25)]
    source = FakeSource(many)
    state = im.run("x", 10, source=source, client=FakeDeezer(), state=im.load("x", tmp_path))
    assert len(state["posts"]) == 24  # only two tracks exist: it reads everything it may, then stops


def test_sound_of_videos_and_carousels_and_a_quota_that_runs_out(tmp_path):
    rec = FakeRecognizer({"v4a": {"artist": "Fela Kuti", "title": "Water No Get Enemy", "deezer_id": 4},
                          "v4b": {"artist": "Nils Frahm", "title": "Says", "deezer_id": None}})
    state = im.run("acc", 10, source=FakeSource(POSTS), client=FakeDeezer(), recognizer=rec, audio=True,
                   state=im.load("acc", tmp_path))
    heard = im.playlist(state)
    assert set(heard[heard["source"] == "audio"]["track_id"]) == {4, 3}
    assert state["posts"]["4"]["audio"] and state["posts"]["3"]["audio"]
    rec2 = FakeRecognizer({}, quota_after=1)
    state2 = im.run("acc2", 10, source=FakeSource(POSTS), client=FakeDeezer(), recognizer=rec2, audio=True,
                    state=im.load("acc2", tmp_path))
    assert state2["error"] == "audio_quota" and not state2["posts"]["4"].get("audio")  # retried on the next run


def test_estimate_counts_what_memory_saves():
    fresh = im.estimate(100)
    assert fresh["new"] == fresh["posts"] and fresh["seconds"] > im.estimate(10)["seconds"]
    known = {"posts": {str(i): {"text": True, "videos": 0} for i in range(200)},
             "tracks": [{"key": f"track:{i}", "post_id": str(i)} for i in range(200)]}
    assert im.estimate(100, known)["new"] == 0 and im.estimate(100, known)["seconds"] < fresh["seconds"]
    assert im.estimate(100, None, audio=True)["seconds"] > fresh["seconds"]


class FakeResponse:
    def __init__(self, body, status=200):
        self.body, self.status_code, self.ok = body, status, status < 400

    def json(self):
        return self.body


class FakeSession:
    def __init__(self, responses):
        self.responses, self.headers, self.urls = list(responses), {}, []

    def get(self, url, params=None, timeout=None):
        self.urls.append((url, params))
        return self.responses.pop(0)


def test_graph_source_pages_and_keeps_the_token_out_of_urls():
    page1 = {"business_discovery": {"media": {"data": [
        {"id": "9", "caption": "Air - Playground Love", "media_type": "CAROUSEL_ALBUM", "permalink": "https://instagram.com/p/A/",
         "timestamp": "2026-10-20T08:00:00+0000", "children": {"data": [{"media_type": "VIDEO", "media_url": "https://cdn/v.mp4"},
                                                                         {"media_type": "IMAGE", "media_url": "https://cdn/i.jpg"}]}}],
        "paging": {"cursors": {"after": "CUR"}, "next": "https://graph"}}}}
    page2 = {"business_discovery": {"media": {"data": [{"id": "8", "media_type": "IMAGE", "permalink": "p",
                                                        "timestamp": "2026-10-19T08:00:00+0000"}], "paging": {}}}}
    session = FakeSession([FakeResponse(page1), FakeResponse(page2)])
    src = im.GraphSource("17841400000000000", "SECRET-TOKEN", session=session)
    pages = list(src.posts("delicieusemusique", 50))
    assert [p.id for pg in pages for p in pg] == ["9", "8"]
    assert pages[0][0].videos == ["https://cdn/v.mp4"] and pages[0][0].taken_at.startswith("2026-10-20T08:00:00")
    assert ".after(CUR)" in session.urls[1][1]["fields"]
    assert session.headers["Authorization"] == "Bearer SECRET-TOKEN"
    assert all("SECRET" not in url + str(params) for url, params in session.urls)


@pytest.mark.parametrize("error,kind", [({"code": 190}, "token"), ({"code": 4}, "rate"), ({"code": 110}, "not_found"),
                                        ({"code": 100, "error_subcode": 33}, "account"),
                                        ({"code": 10}, "setup")])
def test_graph_errors_become_plain_reasons(error, kind):
    src = im.GraphSource("1", "SECRET", session=FakeSession([FakeResponse({"error": error}, 400)]))
    with pytest.raises(im.InstagramError) as exc:
        src.profile("someone")
    assert exc.value.kind == kind and "SECRET" not in str(exc.value)


def test_missing_settings_and_bad_names_are_refused(monkeypatch):
    monkeypatch.setattr(im, "get_setting", lambda name, default=None: None)
    with pytest.raises(im.InstagramError):
        im.GraphSource("", "")
    src = im.GraphSource("1", "t", session=FakeSession([]))
    with pytest.raises(im.InstagramError) as exc:
        src.profile("a){evil}")
    assert exc.value.kind == "invalid"
