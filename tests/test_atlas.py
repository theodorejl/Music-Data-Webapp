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


def _inside(x, y, poly):
    hit = False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            hit = not hit
    return hit


def _convex(poly, aspect):
    pts = [(x * aspect, y) for x, y in poly]
    signs = set()
    for (ax, ay), (bx, by), (cx, cy) in zip(pts, pts[1:] + pts[:1], pts[2:] + pts[:2]):
        cross = (bx - ax) * (cy - by) - (by - ay) * (cx - bx)
        if abs(cross) > 1e-9:
            signs.add(cross > 0)
    return len(signs) == 1


def test_territories_are_straight_edged_polygons_that_hold_their_genres():
    t = genretree.tree()
    assert all(_convex(m["poly"], genretree.ASPECT) for m in t["main"])
    assert all(_convex(s["poly"], genretree.ASPECT) for s in t["sub"])
    for name, si, x, y in t["genres"]:
        sub = t["sub"][si]
        assert _inside(x, y, sub["poly"]), (name, sub["key"])
        assert _inside(x, y, t["main"][sub["main"]]["poly"]), name
    # the edge of the atlas is a rounded rectangle, not a wobbly coast
    xs, ys = [p[0] for p in t["outline"]], [p[1] for p in t["outline"]]
    assert _convex(t["outline"], genretree.ASPECT)
    assert sum(1 for x in xs if abs(x - min(xs)) < 1e-3) >= 2 and sum(1 for y in ys if abs(y - max(ys)) < 1e-3) >= 2


def test_top_share_keeps_the_most_listened_and_never_listened_ones_only_in_all_history():
    minutes = {1: 50.0, 2: 30.0, 3: 5.0}
    ids = [1, 2, 3, 4, 5]  # 4 and 5: favourites never played
    assert atlas.top_share(ids, minutes, 100, all_history=False) == [1, 2, 3]
    assert atlas.top_share(ids, minutes, 1, all_history=False) == [1]  # never nothing
    assert atlas.top_share(ids, minutes, 40, all_history=True) == [1, 2]
    assert atlas.top_share(ids, minutes, 100, all_history=True) == [1, 2, 3, 4, 5]
    assert atlas.top_share([], minutes, 50, all_history=True) == []


def test_albums_are_placed_by_their_own_genres_then_by_their_artist():
    artists, plays, tags, albums, pt, fav = frames()
    albums = pd.concat([albums, pd.DataFrame({"id": [500], "artist_id": [1], "deezer_genres": [None]})], ignore_index=True)
    albums["title"] = ["Tagged Album", "House Album", "Pop Album", "Untagged"]
    albums["label"] = ["Kompakt", "Ed Banger", None, None]
    albums["cover_medium"] = ["https://cdn-images.dzcdn.net/images/cover/" + "b" * 32 + "/250x250-000000-80-0-0.jpg", None, None, None]
    plays = pd.concat([plays, pd.DataFrame({"play_id": [12], "artist_id": [1], "album_id": [500], "minutes": [2.0], "genre": [None]})])
    points = {p["id"]: p for p in atlas.place_albums(artists, plays, tags, albums, pt, fav)}
    t = genretree.tree()
    assert set(points) == {100, 200, 500}  # listened (100, 500) or favourite (200); 300 is neither
    assert t["sub"][points[200]["s"]]["key"] == "house" and points[200]["lb"] == "Ed Banger" and points[200]["fa"] == 1
    assert points[500]["lv"] == atlas.GENRE and points[500]["g"] == "dub techno"  # from its artist's tags
    assert points[100]["p"] == "b" * 32 and points[100]["a"] == "Tagged" and points[100]["n"] == "Tagged Album"


def _touch(p, q, eps=2e-4):
    """Two straight-edged polygons share a border when a corner of one lies on an edge of the other."""
    for x, y in p:
        for (x1, y1), (x2, y2) in zip(q, q[1:] + q[:1]):
            dx, dy = x2 - x1, y2 - y1
            t = max(0, min(1, ((x - x1) * dx + (y - y1) * dy) / ((dx * dx + dy * dy) or 1)))
            if (x - x1 - t * dx) ** 2 + (y - y1 - t * dy) ** 2 < eps * eps:
                return True
    return False


def test_neighbouring_territories_never_share_a_tone():
    t = genretree.tree()
    mains = t["main"]
    assert all(0 <= m["tone"] < 4 for m in mains)
    for i, a in enumerate(mains):
        for b in mains[i + 1:]:
            if _touch(a["poly"], b["poly"]) or _touch(b["poly"], a["poly"]):
                assert a["tone"] != b["tone"], (a["key"], b["key"])
    for i, a in enumerate(t["sub"]):
        for b in t["sub"][i + 1:]:
            if a["main"] == b["main"] and (_touch(a["poly"], b["poly"]) or _touch(b["poly"], a["poly"])):
                assert a["shade"] != b["shade"], (a["key"], b["key"])


def test_columns_keep_the_fields_of_albums_too():
    cols = atlas.columns([{"id": 1, "n": "Discovery", "a": "Daft Punk", "x": .5}, {"id": 2, "n": "Homework", "a": "Daft Punk", "x": .6}])
    assert cols == {"id": [1, 2], "n": ["Discovery", "Homework"], "a": ["Daft Punk", "Daft Punk"], "x": [.5, .6]}
    assert atlas.columns([]) == {}


def test_every_point_stays_inside_its_territory():
    t = genretree.tree()
    for key in range(600):
        m = key % len(t["main"])
        x, y, _ = atlas._spot({"level": atlas.MAIN, "main": m, "sub": None, "genre": None}, key)
        assert _inside(x, y, t["main"][m]["poly"]), (t["main"][m]["key"], key)
        si = key % len(t["sub"])
        x, y, _ = atlas._spot({"level": atlas.SUB, "main": t["sub"][si]["main"], "sub": si, "genre": None}, key)
        assert _inside(x, y, t["sub"][si]["poly"]), (t["sub"][si]["key"], key)


# --- Placed from the stored decisions (core/genremodel.py) -------------------------------------------

def _decision(artist, genre):
    sub = genretree.position()[genre][2]
    return pd.DataFrame({"artist_id": [artist], "main": [genretree.tree()["sub"][sub]["main"]], "sub": [sub],
                         "genre": [genre], "confidence": ["sure"], "words": [[genre]], "sources": [["Every Noise"]]})


def test_place_uses_the_stored_decision():
    points, _ = atlas.place(*frames(), decisions=_decision(4, "nu disco"))
    p = next(p for p in points if p["n"] == "Neighbour")       # only a playlist guess before
    sub = genretree.position()["nu disco"][2]
    assert p["g"] == "nu disco" and p["lv"] == atlas.GENRE and p["s"] == sub
    assert p["sr"] == "Every Noise" and _inside(p["x"], p["y"], genretree.tree()["sub"][sub]["poly"])


def test_an_artist_without_a_decision_still_appears():
    points, missing = atlas.place(*frames(), decisions=_decision(4, "nu disco"))
    by = {p["n"]: p for p in points}
    assert by["Tagged"]["g"] == "dub techno" and by["Deezer Broad"]["lv"] == atlas.MAIN and missing == 1
    assert atlas.place(*frames(), decisions=None) == atlas.place(*frames(), decisions=pd.DataFrame())


def test_the_spiral_keeps_artists_apart_and_inside():
    x, y, sub = genretree.position()["deep house"]
    pts = [{"id": i, "g": "deep house", "s": sub, "lv": atlas.GENRE, "w": 300 - i, "x": x, "y": y} for i in range(200)]
    atlas._spiral(pts)
    xy = np.array([[p["x"] * genretree.ASPECT, p["y"]] for p in pts])
    d = np.hypot(*(xy[:, None, :] - xy[None, :, :]).transpose(2, 0, 1))
    assert d[np.triu_indices(len(pts), 1)].min() >= 0.0034
    assert all(_inside(p["x"], p["y"], genretree.tree()["sub"][sub]["poly"]) for p in pts)
    centre = np.array([x * genretree.ASPECT, y])
    assert int(np.argmin(np.hypot(*(xy - centre).T))) == 0   # the most listened, closest to its genre


def test_an_album_without_its_own_genres_follows_its_artist():
    artists, plays, tags, albums, pt, fav = frames()
    albums = pd.concat([albums, pd.DataFrame({"id": [500], "artist_id": [1], "deezer_genres": [None]})], ignore_index=True)
    plays = pd.concat([plays, pd.DataFrame({"play_id": [12], "artist_id": [1], "album_id": [500], "minutes": [2.0], "genre": [None]})])
    points = {p["id"]: p for p in atlas.place_albums(artists, plays, tags, albums, pt, fav, decisions=_decision(1, "nu disco"))}
    assert points[500]["g"] == "nu disco" and points[500]["s"] == genretree.position()["nu disco"][2]
    assert points[500]["sr"] == "Every Noise"


def _with_untagged_album(frames_):
    artists, plays, tags, albums, pt, fav = frames_
    albums = pd.concat([albums, pd.DataFrame({"id": [500], "artist_id": [1], "deezer_genres": [None]})], ignore_index=True)
    plays = pd.concat([plays, pd.DataFrame({"play_id": [12], "artist_id": [1], "album_id": [500], "minutes": [2.0], "genre": [None]})])
    return artists, plays, tags, albums, pt, fav


def test_an_untagged_album_lands_on_its_artists_decided_genre_even_a_regional_or_broad_one():
    """"rap francais" means nothing to meaning() (a region) and "pop" only a main genre: the decision places it."""
    for genre in ("rap francais", "pop"):
        points = {p["id"]: p for p in atlas.place_albums(*_with_untagged_album(frames()), decisions=_decision(1, genre))}
        assert 500 in points, genre
        p = points[500]
        assert (p["lv"], p["g"], p["s"]) == (atlas.GENRE, genre, genretree.position()[genre][2]), genre
        assert p["m"] == genretree.tree()["sub"][p["s"]]["main"]
        assert p["sr"] == "Every Noise" and p["tg"] == genre


def test_an_albums_own_genres_win_when_precise_or_in_another_main_genre():
    artists, plays, tags, albums, pt, fav = _with_untagged_album(frames())
    tags = pd.concat([tags, pd.DataFrame({"entity_type": ["album"], "entity_id": [500], "tag": ["deep house"],
                                          "count": [3], "source": ["mb"]})], ignore_index=True)
    decisions = pd.concat([_decision(1, "nu disco"), _decision(2, "rap francais")], ignore_index=True)
    points = {p["id"]: p for p in atlas.place_albums(artists, plays, tags, albums, pt, fav, decisions=decisions)}
    assert points[500]["g"] == "deep house"                  # its own precise genre, though its artist is nu disco
    house = genretree.position()["deep house"][2]
    assert points[200]["lv"] == atlas.SUB and points[200]["s"] == house   # Electro, Techno/House: not French rap
    decisions = pd.concat([_decision(1, "nu disco"), _decision(2, "nu disco")], ignore_index=True)
    points = {p["id"]: p for p in atlas.place_albums(artists, plays, tags, albums, pt, fav, decisions=decisions)}
    assert points[200]["g"] == "nu disco" and points[200]["lv"] == atlas.GENRE   # same main, less precise: the decision


def test_a_crowded_genre_near_a_border_stays_by_its_genre():
    """300 artists on a genre near the edge of its sub-genre: the spiral moves a little, not across the sub-genre."""
    x, y, sub = genretree.position()["electro-pop francais"]
    pts = [{"id": i, "g": "electro-pop francais", "lv": atlas.GENRE, "w": 300 - i, "x": x, "y": y} for i in range(300)]
    atlas._spiral(pts)
    heaviest = pts[0]
    assert np.hypot((heaviest["x"] - x) * genretree.ASPECT, heaviest["y"] - y) <= 0.012
    assert all(_inside(p["x"], p["y"], genretree.tree()["sub"][sub]["poly"]) for p in pts)
