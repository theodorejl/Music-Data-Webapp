"""Recommendation engines, with a fake public API (no network)."""

import pandas as pd

from core import recommend


class FakeClient:
    def __init__(self, answers):
        self.answers = answers

    def get(self, path):
        return self.answers.get(path.split("?")[0])


def track(tid, aid, title="T"):
    return {"id": tid, "title": title, "artist": {"id": aid, "name": f"A{aid}"}, "album": {"title": "Al", "cover_medium": "c"}}


def profile():
    seeds = [recommend.Seed(1, "Known", "Electro", 100.0, None), recommend.Seed(2, "Other", "Pop", 50.0, None)]
    return recommend.Profile(seeds=seeds, genres=[("Electro", 0.7), ("Pop", 0.3)], moment="evening",
                             moment_seeds=seeds[:1], known_artists=frozenset({1, 2, 3}), known_tracks=frozenset({10}))


def test_engines_skip_known_music_and_never_repeat_a_track():
    client = FakeClient({
        "artist/1/related": {"data": [{"id": 3}, {"id": 4}, {"id": 5}]},  # 3 is already known
        "artist/2/related": {"data": [{"id": 5}]},
        "artist/4/top": {"data": [track(40, 4)]},
        "artist/5/top": {"data": [track(10, 5), track(50, 5)]},  # track 10 is already known
        "genre": {"data": [{"id": 106, "name": "Electro"}, {"id": 132, "name": "Pop"}]},
        "chart/106/tracks": {"data": [track(50, 5), track(60, 6), track(61, 6), track(70, 7)]},
        "chart/132/tracks": {"data": [track(80, 8)]},
        "artist/1/radio": {"data": [track(10, 1), track(90, 9), track(60, 6)]},
    })
    recs = recommend.recommend(profile(), 3, client)
    assert not recs["track_id"].duplicated().any()
    assert not recs["track_id"].isin([10]).any() and not recs["artist_id"].isin([3]).any()
    n = recs.set_index("track_id")
    # artist 5 is a neighbour of both seeds, so it ranks first; its known track is skipped
    assert list(recs[recs.engine == "neighbours"]["track_id"]) == [50, 40]
    assert n.loc[50, "reason"] == "Known & Other"
    assert set(recs[recs.engine == "genres"]["track_id"]) == {60, 70, 80}  # one track per artist, no duplicate of 50
    assert list(recs[recs.engine == "moment"]["track_id"]) == [90]  # 60 already taken by the genres engine


def test_profile_from_plays():
    t0 = pd.Timestamp("2026-03-01 21:00", tz="Europe/Zurich")
    plays = pd.DataFrame({"artist_id": [1, 1, 2], "artist_name": ["A", "A", "B"], "artist_picture": [None] * 3,
                          "genre": ["Electro", "Electro", "Pop"], "minutes": [3.0, 3.0, 1.0], "track_id": [10, 11, 12],
                          "played_local": [t0, t0, t0 - pd.Timedelta(hours=12)]})
    p = recommend.build_profile(plays, plays, hour=21)
    assert [s.name for s in p.seeds] == ["A", "B"] and p.moment == "evening"
    assert p.genres[0][0] == "Electro" and abs(sum(s for _, s in p.genres) - 1) < 1e-9
    assert [s.name for s in p.moment_seeds] == ["A"] and p.known_tracks == {10, 11, 12}
