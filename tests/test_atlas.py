"""The tree of genres, its atlas, your artists on it, and the enrichment that places them."""

import time

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from core import atlas, genretree, soundmap
from core.models import Album, PlaylistTrack, Tag, Track
from core.sync import enrich_library_genres


def test_names_are_read_by_their_head_their_decisive_words_and_their_place():
    expect = {"deep house": "house", "dub techno": "techno", "tropical house": "edm", "trip hop": "downtempo",
              "pop punk": "poppunk", "dance pop": "dancepop", "thrash metal": "thrash", "atmospheric black metal": "black",
              "indie rock": "indierock", "bristol indie": "indiescenes", "swedish pop": "worldpop", "russian rock": "rockscenes",
              "rap francais": "frenchrap", "rap marseille": "frenchrap", "deep east coast hip hop": "boombap",
              "musica sinaloense": "mexico", "funk carioca": "funkbr", "sertanejo universitario": "sertanejo",
              "turkish folk": "mideast", "k-pop": "asianpop", "barbershop": "doowop", "celtic punk": "garagepunk",
              "jazz rap": "althiphop", "christian doom metal": "doom", "worship": "worship", "children's music": "kids"}
    got = {name: genretree.by_rules(name) for name in expect}
    assert got == expect


def test_coinages_take_the_sub_genre_of_their_neighbours():
    names = ["deep house", "chicago house", "tech house", "escape room"]
    xy = np.array([[.5, .5], [.51, .5], [.5, .51], [.505, .505]])
    assert genretree.classify(names, xy)[-1] == "house"


def test_the_stored_atlas_is_complete_ordered_and_up_to_date():
    t = genretree.tree()
    names = [g.name for g in soundmap.genres()]
    assert [g[0] for g in t["genres"]] == names  # every genre of the map, same order
    keys = [s["key"] for s in t["sub"]]
    assert all(s["n"] > 0 for s in t["sub"]) and len(set(keys)) == len(keys)
    mains = [m["key"] for m in t["main"]]
    assert {"electronic", "pop", "rock", "hiphop", "jazz", "classical", "latin", "africa"} <= set(mains)
    electronic = {s["key"] for s in t["sub"] if mains[s["main"]] == "electronic"}
    assert {"house", "techno", "trance", "dnb", "ambient"} <= electronic
    for name, si, x, y in t["genres"]:  # rebuilt after any change of the rules
        rule = genretree.by_rules(name)
        assert rule is None or rule == keys[si], (name, rule, keys[si])
        assert 0 <= x <= 1 and 0 <= y <= 1
    # each main genre is one territory: its genres sit around their own centre, not across the map
    for mi, m in enumerate(t["main"]):
        pts = np.array([[g[2], g[3]] for g in t["genres"] if t["sub"][g[1]]["main"] == mi])
        assert np.median(np.hypot(pts[:, 0] - m["x"], pts[:, 1] - m["y"])) < .2, m["key"]


def frames():
    artists = pd.DataFrame({"id": [1, 2, 3, 4, 5], "name": ["Tagged", "Deezer Sub", "Deezer Broad", "Neighbour", "Unknown"],
                            "picture_medium": ["https://cdn-images.dzcdn.net/images/artist/" + "a" * 32 +
                                               "/250x250-000000-80-0-0.jpg", "https://x/y.jpg", None, None, None]})
    plays = pd.DataFrame({"play_id": [10, 11], "artist_id": [1, 1], "album_id": [100, 100], "minutes": [4.0, 3.0],
                          "genre": [None, None]})
    tags = pd.DataFrame({"entity_type": ["artist"], "entity_id": [1], "tag": ["dub techno"], "count": [5], "source": ["mb"]})
    albums = pd.DataFrame({"id": [100, 200, 300], "artist_id": [1, 2, 3],
                           "deezer_genres": [None, ["Electro", "Techno/House"], ["Pop"]]})
    pt = pd.DataFrame({"playlist_id": [1, 1, 1, 2], "track_id": [20, 30, 40, 50], "artist_id": [2.0, 3.0, 4.0, 5.0],
                       "album_id": [200, 300, None, None]})
    fav = pd.DataFrame({"album_id": [200], "artist_id": [2]})
    return artists, plays, tags, albums, pt, fav


def test_artists_are_placed_as_precisely_as_their_genre_is_known():
    points, missing = atlas.place(*frames())
    by = {p["n"]: p for p in points}
    t = genretree.tree()
    main = lambda p: t["main"][p["m"]]["key"]  # noqa: E731
    assert by["Tagged"]["lv"] == atlas.GENRE and by["Tagged"]["g"] == "dub techno" and by["Tagged"]["p"] == "a" * 32
    assert by["Tagged"]["pl"] == 2 and by["Tagged"]["mn"] == 7
    assert by["Deezer Sub"]["lv"] == atlas.SUB and t["sub"][by["Deezer Sub"]["s"]]["key"] == "house"
    assert by["Deezer Sub"]["lt"] == 1 and by["Deezer Sub"]["fa"] == 1
    assert by["Deezer Broad"]["lv"] == atlas.MAIN and main(by["Deezer Broad"]) == "pop"
    assert by["Neighbour"]["lv"] == atlas.MAIN  # from the artists sharing its playlist
    assert "Unknown" not in by and missing == 1  # alone in its playlist, nothing known
    columns = atlas.columns(points)
    assert len(columns["id"]) == 4 and set(columns) >= {"x", "y", "w", "lv"}
    again, _ = atlas.place(*frames())
    assert again == points  # the same place every time


def test_recommendations_go_on_their_sub_genre():
    x, y, _ = genretree.position()["deep house"]
    assert atlas.anchor("deep house") == (x, y)
    g = soundmap.by_name("dub techno")
    assert atlas.anchor(None, g.x, g.y) == genretree.position()["dub techno"][:2]
    assert atlas.anchor(None) is None


class FakeDeezer:
    def __init__(self):
        self.asked = []

    def album(self, album_id):
        self.asked.append(album_id)
        return {"title": f"Album {album_id}", "genres": {"data": [{"name": "Electro"}, {"name": "Techno/House"}]}}


def test_library_genres_fetch_one_album_per_unknown_artist_most_present_first(engine):
    with Session(engine) as s:
        s.add_all([Album(id=a, title="?", artist_id=a // 10) for a in (10, 11, 20, 30)])
        s.add_all([Track(id=t, title="t", album_id=al, artist_id=ar) for t, al, ar in
                   ((1, 10, 1), (2, 10, 1), (3, 11, 1), (4, 20, 2), (5, 20, 2), (6, 20, 2), (8, 20, 2), (7, 30, 3))])
        s.add_all([PlaylistTrack(playlist_id=1, position=i, track_id=t) for i, t in enumerate((1, 2, 3, 4, 5, 6, 8, 7))])
        s.add(Tag(entity_type="artist", entity_id=3, tag="house", count=1, source="mb"))  # already placed
        s.commit()
        client = FakeDeezer()
        assert enrich_library_genres(s, client, time.monotonic() + 30) == 2
        assert client.asked == [20, 10]  # artist 2 has 4 tracks, artist 1 has 3 (two on album 10)
        assert s.get(Album, 20).deezer_genres == ["Electro", "Techno/House"]
        assert enrich_library_genres(s, FakeDeezer(), time.monotonic() + 30) == 0  # nothing left
