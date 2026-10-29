"""Discovery engine and map of sound, with a fake public API (no network)."""

import pandas as pd

from core import recommend, soundmap


class FakeClient:
    def __init__(self, answers):
        self.answers = answers
        self.calls = []

    def get(self, path):
        self.calls.append(path)
        return self.answers.get(path.split("?")[0])


def track(tid, aid, name=None, rank=100_000):
    return {"id": tid, "title": f"T{tid}", "rank": rank, "artist": {"id": aid, "name": name or f"A{aid}"},
            "album": {"title": "Al", "cover_medium": "c"}}


def profile(**kw):
    seeds = [recommend.Seed(1, "Known", "Electro", 100.0, None, "deep house", 100.0, 200.0),
             recommend.Seed(2, "Other", "Pop", 50.0, None, "dub techno", 300.0, 400.0)]
    base = dict(seeds=seeds, genres=[("Electro", 0.7), ("Pop", 0.3)], home=[("deep house", 0.6), ("dub techno", 0.4)],
                moment="evening", moment_seeds=seeds[:1], known_artists=frozenset({1, 2, 3}),
                known_names=frozenset({recommend.name_key("Famous Name")}), known_tracks=frozenset({10}))
    base.update(kw)
    return recommend.Profile(**base)


def test_neighbours_skip_known_artists_by_id_and_name_and_reward_consensus():
    client = FakeClient({
        "artist/1/related": {"data": [{"id": 3, "name": "A3"}, {"id": 4, "name": "A4"}, {"id": 5, "name": "A5"},
                                      {"id": 7, "name": "Famous Name"}]},
        "artist/2/related": {"data": [{"id": 5, "name": "A5"}]},
        "artist/4/top": {"data": [track(40, 4)]},
        "artist/5/top": {"data": [track(10, 5), track(50, 5)]},  # track 10 is already known
        "artist/7/top": {"data": [track(70, 7, "Famous Name")]},
    })
    recs = recommend.run("neighbours", profile(), 10, client=client)
    assert list(recs["track_id"]) == [50, 40]  # 5 is named by both seeds; 3 and "Famous Name" are known
    assert recs.iloc[0]["reason"] == "Known & Other"
    assert recs.iloc[0]["anchor_x"] == 100.0 and recs.iloc[0]["subgenre"] == "deep house"


def test_subgenres_take_tracks_from_the_playlists_of_each_subgenre():
    answers = {"search/playlist": {"data": [{"id": 900, "title": "Deep House Essentials", "nb_tracks": 50,
                                             "user": {"name": "Laeti - Deezer Editor"}}]},
               "playlist/900/tracks": {"data": [track(91, 9), track(92, 9), track(93, 3), track(94, 11)]}}
    recs = recommend.run("subgenres", profile(), 10, client=FakeClient(answers))
    assert sorted(recs["artist_id"]) == [9, 11]  # one track per artist, artist 3 is known
    assert recs["subgenre"].notna().all() and recs["anchor_x"].notna().all()
    assert {g for g in recs["subgenre"]} <= {g.name for g, *_ in recommend.targets(profile(), 10, "balanced")}


def test_moment_uses_the_radio_and_boldness_prefers_lesser_known_tracks():
    radio = {"artist/1/radio": {"data": [track(90, 9, rank=900_000), track(91, 12, rank=20_000), track(92, 1)]}}
    bold = recommend.run("moment", profile(), 10, client=FakeClient(radio), boldness="bold")
    familiar = recommend.run("moment", profile(), 10, client=FakeClient(radio), boldness="familiar")
    assert list(bold["track_id"]) == [91, 90] and list(familiar["track_id"]) == [90, 91]  # artist 1 is known


def test_profile_counts_the_library_as_known():
    t0 = pd.Timestamp("2026-03-01 21:00", tz="Europe/Zurich")
    plays = pd.DataFrame({"artist_id": [1, 1, 2], "artist_name": ["A", "A", "B"], "artist_picture": [None] * 3,
                          "genre": ["Electro", "Electro", "Pop"], "minutes": [3.0, 3.0, 1.0], "track_id": [10, 11, 12],
                          "album_id": [100, 100, 200], "played_local": [t0, t0, t0 - pd.Timedelta(hours=12)]})
    library = pd.DataFrame({"artist_id": [50], "artist_name": ["Bibliothèque Artist"], "track_id": [500]})
    p = recommend.build_profile(plays, plays, 21, None, library)
    assert [s.name for s in p.seeds] == ["A", "B"] and p.moment == "evening"
    assert 50 in p.known_artists and 500 in p.known_tracks and p.is_known({"id": 999, "name": "bibliotheque artist"})
    assert p.home and p.home[0][0] == "electronica" and p.seeds[0].x is not None


def test_estimate_and_progress():
    p = profile()
    assert recommend.estimate("neighbours", 200, p)[0] > recommend.estimate("neighbours", 10, p)[0]
    client = FakeClient({"artist/1/radio": {"data": [track(90, 9), track(91, 13)]}})
    progress = recommend.Progress(recommend.estimate("moment", 10, p)[0], 10)
    recs = recommend.run("moment", p, 10, progress, client)
    assert len(recs) == 2 and progress.finished and progress.fraction == 1.0 and progress.found == 2


def test_soundmap_matches_tags_and_finds_a_frontier():
    assert soundmap.match("Deep House").name == "deep house"
    assert soundmap.match("synth-pop").name == "synthpop" and soundmap.match("Rap/Hip Hop").name == "hip hop"
    assert soundmap.match("british") is None
    home = [(soundmap.by_name("deep house"), 0.6), (soundmap.by_name("dub techno"), 0.4)]
    near = soundmap.frontier(home, "familiar", 8)
    assert near and all(g.name not in {"deep house", "dub techno"} for g, _, _ in near)
    assert all(not soundmap._regions(g.name) for g, _, _ in near)  # no regional variants


def test_map_regions_are_nested_named_and_stable():
    h = soundmap.hierarchy()
    big, small = h["levels"]
    assert len(big["names"]) == 14 and len(small["names"]) == 110
    assert len(big["of"]) == len(soundmap.genres()) and set(big["of"]) == set(range(14))
    assert all(" & " in n for n in big["names"]) and len(set(big["names"])) == 14  # "House & rap"-style family names
    assert soundmap.hierarchy.__wrapped__()["levels"][0]["names"] == big["names"]  # same seed, same regions
    assert soundmap.display("r&b") == "R&B" and soundmap.display("deep house") == "Deep house"
