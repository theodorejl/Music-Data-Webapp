"""Genres and labels of the artists from the music databases, and the vote that places them."""

import time
from collections import Counter

import pandas as pd
import pytest
from sqlalchemy.orm import Session

from core import artistinfo as ai
from core import atlas, genretree
from core.models import Album, Artist, ArtistInfo, ArtistRelated, PlaylistTrack, Tag, Track


class Response:
    def __init__(self, body, status=200, headers=None):
        self.body, self.status_code, self.headers = body, status, headers or {}

    def json(self):
        return self.body


class Session_:
    def __init__(self, answer):
        self.answer, self.headers, self.calls = answer, {}, []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        return self.answer(url, params or {})

    def post(self, url, data=None, timeout=None):
        self.calls.append((url, data))
        return self.answer(url, data or {})


def test_wikidata_reads_genres_labels_and_ids_by_deezer_id():
    body = {"results": {"bindings": [{"dz": {"value": "27"}, "item": {"value": "http://www.wikidata.org/entity/Q185828"},
                                      "mbid": {"value": "056e4f3e"}, "discogs": {"value": "1289"},
                                      "genres": {"value": "French house|nu-disco"}, "labels": {"value": "Virgin Records"},
                                      "spotify": {"value": "4tZwfgrHOc3mvqYlEYSvVi"}}]}}
    wd = ai.Wikidata(session=Session_(lambda url, p: Response(body)))
    assert wd.lookup([27, 28]) == {27: {"qid": "Q185828", "mbid": "056e4f3e", "discogs": 1289,
                                        "genres": ["French house", "nu-disco"], "labels": ["Virgin Records"],
                                        "spotify": ["4tZwfgrHOc3mvqYlEYSvVi"]}}


def test_lastfm_tags_by_mbid_then_by_name_and_a_refused_key_stops_it():
    def answer(url, p):
        if "mbid" in p:
            return Response({"error": 6, "message": "not found"})
        return Response({"toptags": {"tag": [{"name": "jazz-funk", "count": 100}, {"name": "rare", "count": 2}]}})
    lf = ai.Lastfm("KEY", session=Session_(answer))
    lf.pace.gap = 0
    assert lf.top_tags("Wally Badarou", "mbid-1") == [("jazz-funk", 100)]
    bad = ai.Lastfm("BAD", session=Session_(lambda url, p: Response({"error": 10})))
    bad.pace.gap = 0
    with pytest.raises(ai.SourceError):
        bad.top_tags("x")


def test_discogs_reads_the_most_collected_releases():
    def answer(url, p):
        if url.endswith("/releases") and "artists/" in url:
            return Response({"releases": [{"id": 1, "type": "release", "role": "Main", "stats": {"community": {"in_collection": 5}}},
                                          {"id": 2, "type": "master", "main_release": 20, "role": "Main",
                                           "stats": {"community": {"in_collection": 900}}},
                                          {"id": 3, "type": "release", "role": "Remix"}]})
        rid = url.rsplit("/", 1)[-1]
        return Response({"20": {"styles": ["Jazz-Funk", "Synth-pop"], "genres": ["Jazz"], "labels": [{"name": "Island"}]},
                         "1": {"styles": ["Jazz-Funk"], "genres": ["Electronic"], "labels": [{"name": "Not On Label"}]}}[rid])
    dg = ai.Discogs(token="", session=Session_(answer))
    dg.pace.gap = 0
    got = dg.by_id(123)
    assert got["styles"] == Counter({"Jazz-Funk": 2, "Synth-pop": 1}) and got["labels"]["Island"] == 1


class FakeWikidata:
    def lookup(self, ids):
        return {1: {"qid": "Q1", "mbid": None, "discogs": 77, "genres": ["synth-pop"], "labels": ["Kitsuné"]}}


class FakeSpotifyWikidata:
    def __init__(self):
        self.calls = []

    def lookup(self, ids):
        self.calls.append(list(ids))
        return {a: {"qid": f"Q{a}", "mbid": None, "discogs": None, "genres": [], "labels": [],
                    "spotify": ["4tZwfgrHOc3mvqYlEYSvVi"]} for a in ids}


class FakeMusicBrainz:
    def __init__(self):
        self.asked = []

    def by_deezer(self, deezer_id):
        return "mbid-1"

    def artist(self, mbid):
        self.asked.append(mbid)
        return {"genres": [], "tags": [], "relations": [
            {"url": {"resource": "https://open.spotify.com/artist/0GG2cWaonE4JPrjcCCQ1EG"}}]}


class FakeLastfm:
    def top_tags(self, name, mbid=None):
        return [("jazz-funk", 100), ("80s", 60)] if name == "Wally" else []


class FakeDiscogs:
    token = ""

    def by_id(self, did):
        return {"styles": Counter({"Nu-Disco": 2}), "genres": Counter({"Electronic": 2}), "labels": Counter({"Kitsuné": 2})}


def test_enrich_asks_each_source_once_and_stores_what_it_says(engine):
    with Session(engine) as s:
        s.add_all([Artist(id=1, name="Parcels"), Artist(id=2, name="Wally")])
        s.add_all([Track(id=10, title="t", artist_id=1), Track(id=20, title="t", artist_id=2)])
        s.add_all([PlaylistTrack(playlist_id=1, position=0, track_id=10), PlaylistTrack(playlist_id=1, position=1, track_id=20)])
        s.commit()
        done = ai.enrich(s, time.monotonic() + 30, wikidata=FakeWikidata(), discogs=FakeDiscogs(), lastfm=FakeLastfm())
        assert done == {"wikidata": 1, "discogs": 1, "lastfm": 1}
        tags = {(t.entity_type, t.entity_id, t.tag, t.source) for t in s.query(Tag)}
        assert ("artist", 1, "synth-pop", "wikidata") in tags and ("artist", 1, "Nu-Disco", "discogs") in tags
        assert ("artist_label", 1, "Kitsuné", "wikidata") in tags and ("artist", 2, "jazz-funk", "lastfm") in tags
        info = s.get(ArtistInfo, 1)
        assert info.discogs_id == 77 and {"wikidata", "discogs", "lastfm"} <= set(info.checked)
        assert ai.enrich(s, time.monotonic() + 30, wikidata=FakeWikidata(), discogs=FakeDiscogs(), lastfm=FakeLastfm()) == {}


def test_enrich_stores_spotify_ids_from_wikidata_and_musicbrainz(engine):
    class Wd(FakeWikidata):
        def lookup(self, ids):
            return {1: {**super().lookup(ids)[1], "spotify": ["4tZwfgrHOc3mvqYlEYSvVi"]}}

    with Session(engine) as s:
        s.add_all([Artist(id=1, name="Parcels"), Track(id=10, title="t", artist_id=1)])
        s.add(PlaylistTrack(playlist_id=1, position=0, track_id=10))
        s.commit()
        ai.enrich(s, time.monotonic() + 30, wikidata=Wd(), musicbrainz=FakeMusicBrainz())
        tags = {(t.entity_type, t.entity_id, t.tag, t.source) for t in s.query(Tag) if t.entity_type == "artist_spotify"}
        assert tags == {("artist_spotify", 1, "4tZwfgrHOc3mvqYlEYSvVi", "wikidata"),
                        ("artist_spotify", 1, "0GG2cWaonE4JPrjcCCQ1EG", "musicbrainz")}
        assert {"spotify_wd", "spotify_mb"} <= set(s.get(ArtistInfo, 1).checked)


def test_spotify_backfill_asks_only_artists_not_asked_yet(engine):
    with Session(engine) as s:
        s.add_all([Artist(id=1, name="Parcels"), Track(id=10, title="t", artist_id=1)])
        s.add(PlaylistTrack(playlist_id=1, position=0, track_id=10))
        s.add(ArtistInfo(artist_id=1, mbid="mbid-1", checked={"wikidata": "2026-01-01"}))
        s.commit()
        wd, mb = FakeSpotifyWikidata(), FakeMusicBrainz()
        done = ai.enrich_spotify_ids(s, time.monotonic() + 30, wd, mb)
        assert wd.calls == [[1]] and mb.asked == ["mbid-1"] and done == {"wikidata": 1, "musicbrainz": 1}
        ids = {(t.tag, t.source) for t in s.query(Tag) if t.entity_type == "artist_spotify"}
        assert ids == {("4tZwfgrHOc3mvqYlEYSvVi", "wikidata"), ("0GG2cWaonE4JPrjcCCQ1EG", "musicbrainz")}
        assert ai.enrich_spotify_ids(s, time.monotonic() + 30, wd, mb) == {}
        assert wd.calls == [[1]] and mb.asked == ["mbid-1"]


class FakeRelatedPublic:
    def __init__(self):
        self.asked = []

    def related(self, artist_id, limit=20):
        self.asked.append(artist_id)
        return [{"id": 100 + k, "name": f"Rel {k}"} for k in range(3)]


def test_related_artists_are_stored_with_their_rank_once(engine):
    with Session(engine) as s:
        s.add_all([Artist(id=1, name="Parcels"), Track(id=10, title="t", artist_id=1)])
        s.add(PlaylistTrack(playlist_id=1, position=0, track_id=10))
        s.commit()
        pub = FakeRelatedPublic()
        assert ai.fetch_related(s, pub, time.monotonic() + 30) == 1
        rows = sorted((r.related_id, r.rank, r.related_name) for r in s.query(ArtistRelated).filter_by(artist_id=1))
        assert rows == [(100, 0, "Rel 0"), (101, 1, "Rel 1"), (102, 2, "Rel 2")]
        assert "deezer_related" in s.get(ArtistInfo, 1).checked
        assert ai.fetch_related(s, pub, time.monotonic() + 30) == 0
        assert pub.asked == [1]


def test_related_without_an_answer_is_retried_not_recorded(engine):
    class Flaky(FakeRelatedPublic):
        def related(self, artist_id, limit=20):
            self.asked.append(artist_id)
            return None if artist_id == 1 else [{"id": 100, "name": "Rel"}]

    with Session(engine) as s:
        s.add_all([Artist(id=1, name="A"), Artist(id=2, name="B"),
                   Track(id=10, title="t", artist_id=1), Track(id=11, title="u", artist_id=2)])
        s.add_all([PlaylistTrack(playlist_id=1, position=0, track_id=10), PlaylistTrack(playlist_id=1, position=1, track_id=11)])
        s.commit()
        pub = Flaky()
        assert ai.fetch_related(s, pub, time.monotonic() + 30) == 1
        assert s.query(ArtistRelated).filter_by(artist_id=1).count() == 0
        assert "deezer_related" not in ((s.get(ArtistInfo, 1) and s.get(ArtistInfo, 1).checked) or {})
        assert s.query(ArtistRelated).filter_by(artist_id=2).count() == 1
        assert "deezer_related" in s.get(ArtistInfo, 2).checked
        pub.asked.clear()
        ai.fetch_related(s, pub, time.monotonic() + 30)
        assert pub.asked == [1]


def test_words_are_read_on_the_tree_and_noise_is_ignored():
    g, sub, broad = atlas.meaning("Nu-Disco")
    assert g == "nu disco" and genretree.tree()["sub"][sub]["key"] == "disco" and not broad
    assert atlas.meaning("electronic music")[2] and atlas.meaning("Pop")[2]  # a whole main genre
    for noise in ("seen live", "80s", "1984", "french", "female vocalists"):
        assert atlas.meaning(noise) == (None, None, False)
    assert genretree.tree()["sub"][atlas.meaning("jazz-funk")[1]]["key"] == "fusion"


def test_the_vote_prefers_curated_genres_and_never_invents_a_precise_one():
    keys = lambda d: (genretree.tree()["main"][d["main"]]["key"],  # noqa: E731
                      genretree.tree()["sub"][d["sub"]]["key"] if d["sub"] is not None else None, d["genre"], d["level"])
    wally = atlas.decide([("Pop", "deezer_top", 1), ("jazz-funk", "lastfm", 1), ("Jazz-Funk", "discogs", 1),
                          ("Synth-pop", "discogs", .5), ("80s", "lastfm", .6)])
    assert keys(wally)[:2] == ("jazz", "fusion") and "Discogs" in wally["sources"]
    assert keys(atlas.decide([("Pop", "deezer_top", 1)])) == ("pop", None, None, atlas.MAIN)
    assert keys(atlas.decide([("Electro", "deezer_top", 1), ("Techno/House", "deezer", 1)]))[1:] == ("house", None, atlas.SUB)
    assert atlas.decide([("seen live", "lastfm", 1)]) is None


def test_the_label_is_the_one_of_most_albums():
    albums = pd.DataFrame({"id": [1, 2, 3], "label": ["Ed Banger", "Ed Banger", "Not On Label"]})
    links = pd.DataFrame({"artist_id": [9, 9, 9], "album_id": [1, 2, 3]})
    assert ai.labels_of(albums, links) == {9: "Ed Banger"}
