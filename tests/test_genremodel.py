from core import genremodel
from core.everynoise import Index, build_index


def test_words_become_mass_on_their_genre_sub_and_main():
    ev = genremodel.word_evidence([("Nu-Disco", "discogs", 1.0), ("Pop", "deezer_top", 1.0)])
    d = ev["discogs"]; assert d.genre == {"nu disco": 1.0} and sum(d.sub.values()) == 1.0 and d.main.sum() == 1.0
    p = ev["deezer_top"]; assert p.genre == {} and p.sub == {} and p.main.sum() == 1.0   # a broad word: main only


def test_every_noise_weighs_a_genre_by_the_artists_rank_in_it():
    e = genremodel.everynoise_evidence([("nu disco", 0), ("indietronica", 50)])
    assert e.genre["nu disco"] == 1.0 and e.genre["indietronica"] == 0.5


def test_identity_prefers_the_spotify_id_and_refuses_ambiguous_names():
    idx = Index(build_index({"nu disco": [("A"*22, "Panama", 1)], "metal": [("B"*22, "Panama", 1)], "jazz": [("C"*22, "Solo", 1)]}))
    ctx = {3: genremodel.everynoise_evidence([("metal", 1)]).main}
    got = genremodel.match_everynoise(idx, {1: ["A"*22], 4: ["Z"*22]}, {1: "Panama", 2: "Panama", 3: "Panama", 4: "Solo", 5: "Solo"}, ctx)
    assert got[1] == ("everynoise", "A"*22)              # id first
    assert 2 not in got                                    # two Panamas, no context: refused
    assert got[3] == ("everynoise_name", "B"*22)         # the Panama whose genres fit
    assert 4 not in got                                    # its id is known and absent: never by name
    assert got[5] == ("everynoise_name", "C"*22)         # unique name


def test_evidence_mass_is_main_sum_and_genre_counts_for_sub_and_main():
    e = genremodel.everynoise_evidence([("nu disco", 0)])
    assert e.mass == e.main.sum() == 1.0 and sum(e.sub.values()) == 1.0


def test_a_source_that_is_always_wrong_loses_weight():
    import numpy as np
    ev = {}
    for a in range(40):
        row = {}
        for s, m in (("mb_genre", 0), ("wikidata", 0), ("deezer", 1)):
            e = genremodel.Evidence(); e.add(m, 1.0); row[s] = e
        ev[a] = row
    w = genremodel.reliability(ev)
    assert 0.2 * genremodel.W0["deezer"] <= w[("deezer", 1)] < genremodel.W0["deezer"]
    assert genremodel.W0["mb_genre"] <= w[("mb_genre", 0)] <= 3 * genremodel.W0["mb_genre"]
    assert w[("deezer", 5)] == genremodel.W0["deezer"]       # never observed: keeps its starting weight


# --- Neighbours, propagation, decision ---------------------------------------------------------------

import pandas as pd

from core import genretree

HOUSE = genretree.position()["deep house"][2]
FUSION = genretree.position()["jazz fusion"][2]
ELECTRONIC = genretree.tree()["sub"][HOUSE]["main"]
NO_TRACKS = pd.DataFrame({"playlist_id": [], "track_id": [], "artist_id": []})


def _house():
    return {"everynoise": genremodel.everynoise_evidence([("deep house", 0)])}


def _classify(ids, ev, edges, external=None):
    return genremodel.classify(ids, ev, genremodel.reliability(ev), edges, external or {})


def test_an_artist_without_evidence_takes_the_genre_of_its_neighbours():
    names = [f"Neighbour {i}" for i in range(5)]
    idx = Index(build_index({"deep house": [(str(i) * 22, n, i + 1) for i, n in enumerate(names)]}))
    related = pd.DataFrame({"artist_id": [9] * 5, "related_id": [101, 102, 103, 104, 105],
                            "rank": [0, 1, 2, 3, 4], "related_name": names})
    edges, external = genremodel.graph(related, NO_TRACKS, idx)
    assert set(external) == {101, 102, 103, 104, 105}     # outside the library, known by a unique name
    d = genremodel.classify([9], {}, {}, edges, external)[9]
    assert d.sub == HOUSE and d.genre == "deep house" and d.confidence == "neighbours"
    assert d.words == [] and d.sources == ["Deezer"]


def test_a_lone_pop_word_yields_to_neighbours_all_in_house():
    ev = {9: genremodel.word_evidence([("Pop", "deezer_top", 1.0)]), 1: _house(), 2: _house()}
    edges = [(9, 1, 0.3), (2, 9, 0.3)]                      # two weak playlist links: alone they would not win
    d = _classify([9, 1, 2], ev, edges)[9]
    assert d.main == ELECTRONIC and d.sub == HOUSE and d.confidence == "neighbours"


def test_solid_evidence_keeps_its_genre_against_neighbours():
    ev = {9: genremodel.word_evidence([("jazz fusion", "mb_genre", 1.0), ("Jazz Fusion", "discogs", 1.0)])}
    ev.update({j: _house() for j in range(1, 6)})
    d = _classify([9, 1, 2, 3, 4, 5], ev, [(9, j, 1.0) for j in range(1, 6)])[9]
    assert d.sub == FUSION and d.genre == "jazz fusion" and d.confidence != "neighbours"


def test_a_multi_genre_artist_goes_to_its_dominant_genre_on_a_precise_genre():
    words = ["deep house", "tech house", "house", "jazz fusion", "bebop"]   # 60 % house, 40 % jazz
    ev = {9: genremodel.word_evidence([(w, "mb_genre", 1.0) for w in words])}
    d = _classify([9], ev, [])[9]
    assert d.main == ELECTRONIC and genretree.position()[d.genre][2] == HOUSE
    assert d.confidence == "likely" and d.sources == ["MusicBrainz"]
    assert set(d.words) == {"deep house", "tech house", "house"}


def test_an_isolated_artist_without_anything_is_not_decided():
    ev = {10: genremodel.word_evidence([("nu disco", "mb_genre", 1.0)])}
    got = _classify([9, 10], ev, [])
    assert 9 not in got and got[10].genre == "nu disco"


def test_two_agreeing_sources_make_a_sure_decision():
    ev = {9: genremodel.word_evidence([("nu disco", "mb_genre", 1.0), ("Nu-Disco", "discogs", 1.0)])}
    d = _classify([9], ev, [])[9]
    assert d.genre == "nu disco" and d.confidence == "sure" and d.sources == ["Discogs", "MusicBrainz"]


def test_the_graph_is_symmetric_and_keeps_the_30_most_shared_playlist_neighbours():
    related = pd.DataFrame({"artist_id": [1, 2, 1, 1, 1], "related_id": [2, 1, 5, 6, 7], "rank": [0, 5, 0, 0, 0],
                            "related_name": ["B", "A", "Solo", "Panama", "Nobody"]})
    rows = [("p", t, a) for t, a in enumerate([1, 2, None])]                          # a track without artist
    rows += [(f"q{k}", t, a) for k in range(2) for t, a in enumerate([1, 2, 3])]
    rows += [("big", t, 1 if t == 0 else 4) for t in range(301)]                     # over 300 tracks: ignored
    for hub, first in ((10, 100), (11, 200)):                                         # two hubs, 30 strong partners each
        rows += [(f"h{hub}-{k}", t, a) for k in range(3) for t, a in enumerate([hub, *range(first, first + 30)])]
    rows += [("weak", 0, 10), ("weak", 1, 11)]                                        # the hubs share one playlist
    pt = pd.DataFrame(rows, columns=["playlist_id", "track_id", "artist_id"])
    idx = Index(build_index({"metal": [("A" * 22, "Panama", 1), ("C" * 22, "Solo", 1)], "jazz": [("B" * 22, "Panama", 1)]}))
    edges, external = genremodel.graph(related, pt, idx)
    w = {(a, b): x for a, b, x in edges}
    assert len(w) == len(edges) and all(a < b for a, b, _ in edges)                   # each pair once
    assert abs(w[(1, 2)] - (1.0 + 0.3)) < 1e-9                                        # best related link + 3 shared playlists
    assert abs(w[(1, 3)] - 0.2) < 1e-9 and (1, 4) not in w
    assert (10, 100) in w and (10, 11) not in w                                       # beyond both hubs' 30 best
    assert set(external) == {5} and set(external[5].genre) == {"metal"}             # homonym and unknown: skipped


def test_an_own_precise_genre_beats_the_neighbours_and_without_one_the_neighbours_decide():
    tech = {"everynoise": genremodel.everynoise_evidence([("tech house", 0)])}
    ev = {9: genremodel.word_evidence([("deep house", "mb_genre", 1.0)]),   # a precise genre of the house sub
          8: genremodel.word_evidence([("House", "deezer", 1.0)])}         # Deezer only says the sub
    assert ev[8]["deezer"].genre == {} and set(ev[8]["deezer"].sub) == {HOUSE}
    ev.update({j: tech for j in range(1, 6)})
    edges = [(a, j, 1.0) for a in (8, 9) for j in range(1, 6)]
    got = _classify([9, 8, 1, 2, 3, 4, 5], ev, edges)
    assert got[9].sub == got[8].sub == HOUSE
    assert got[9].genre == "deep house" and got[8].genre == "tech house"


def test_a_decision_pulled_by_its_neighbours_still_names_a_source():
    ev = {9: genremodel.word_evidence([("Pop", "deezer", 1.0)])}   # own mass above 1: no override
    ev.update({j: _house() for j in range(1, 6)})
    d = _classify([9, 1, 2, 3, 4, 5], ev, [(9, j, 1.0) for j in range(1, 6)])[9]
    assert d.main == ELECTRONIC and d.confidence == "likely" and d.sources == ["Deezer"]


# --- Stored at each sync -----------------------------------------------------------------------------

def test_run_writes_one_decision_per_artist_and_replaces_them(engine):
    from sqlalchemy import func, select
    from sqlalchemy.orm import Session

    from core.models import Artist, ArtistGenre, PlaylistTrack, Tag, Track
    with Session(engine) as s:
        s.add_all([Artist(id=1, name="Parcels"), Artist(id=2, name="Kerri Chandler")])
        s.add_all([Track(id=10, title="t", artist_id=1), Track(id=20, title="t", artist_id=2)])
        s.add_all([PlaylistTrack(playlist_id=1, position=0, track_id=10), PlaylistTrack(playlist_id=1, position=1, track_id=20)])
        s.add_all([Tag(entity_type="artist", entity_id=1, tag="nu disco", count=3, source="mb_genre"),
                   Tag(entity_type="artist", entity_id=2, tag="Deep House", count=2, source="discogs")])
        s.commit()
    summary = genremodel.run(engine)
    assert summary["artists"] == 2 and summary["missing"] == 0
    assert summary["sure"] + summary["likely"] + summary["neighbours"] == 2
    genremodel.run(engine)
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(ArtistGenre)) == 2
        assert s.get(ArtistGenre, 1).genre == "nu disco" and s.get(ArtistGenre, 2).genre == "deep house"


def test_run_finds_library_artists_in_every_noise_by_their_name(engine, monkeypatch):
    from sqlalchemy.orm import Session

    from core import everynoise
    from core.models import Artist, ArtistGenre, PlaylistTrack, Track
    idx = Index(build_index({"nu disco": [("a" * 22, "Parcels", 1)], "deep house": [("b" * 22, "Not In Library", 1)]}))
    monkeypatch.setattr(everynoise, "load", lambda *a, **k: idx)
    with Session(engine) as s:
        s.add_all([Artist(id=1, name="Parcels"), Artist(id=2, name="Not In Library")])  # 2: no track, no playlist
        s.add(Track(id=10, title="t", artist_id=1))
        s.add(PlaylistTrack(playlist_id=1, position=0, track_id=10))
        s.commit()
    assert genremodel.run(engine)["artists"] == 1
    with Session(engine) as s:
        assert s.get(ArtistGenre, 1).genre == "nu disco" and s.get(ArtistGenre, 2) is None


def test_a_database_without_any_evidence_breaks_nothing(engine):
    """A first sync knows no genre yet: no weights, no decisions, no failure."""
    from sqlalchemy.orm import Session

    from core.models import Artist, PlaylistTrack, Track
    assert genremodel.reliability({}) == {} and genremodel.reliability({9: {}}) == {}
    assert genremodel.run(engine)["artists"] == 0                    # an empty database
    with Session(engine) as s:
        s.add(Artist(id=1, name="Zqxw Nobody Knows 4821"))
        s.add(Track(id=10, title="t", artist_id=1))
        s.add(PlaylistTrack(playlist_id=1, position=0, track_id=10))
        s.commit()
    summary = genremodel.run(engine)
    assert summary["artists"] == 0 and summary["missing"] == 1 and summary["weights"] == {}
    ev = {9: genremodel.word_evidence([("nu disco", "mb_genre", 1.0)])}
    assert genremodel.classify([9], ev, {}, [], {})[9].genre == "nu disco"   # no weights: the starting ones


# --- Evaluation --------------------------------------------------------------------------------------

def test_evaluation_reports_cold_and_single_source_accuracy():
    two = [("deep house", "mb_genre", 1.0), ("Deep House", "discogs", 1.0)]   # two families agree: a reference
    ev = {a: genremodel.word_evidence(two) for a in range(1, 11)}
    edges = [(a, b, 1.0) for a in range(1, 11) for b in range(a + 1, 11)]
    pt = pd.DataFrame({"playlist_id": [1] * 10, "track_id": range(10), "artist_id": [float(a) for a in range(1, 11)]})
    got = genremodel.evaluate(ev, genremodel.reliability(ev), edges, {}, ids=list(ev), playlist_tracks=pt)
    assert got["reference"] == 10
    assert got["cold_main"] == 1.0 and got["cold_sub"] == 1.0      # hidden, each one is found again by its neighbours
    assert got["cold_main_old"] == 1.0                                 # the playlist guess finds the main genre too
    assert 0 <= got["single_sub"] <= 1 and got["single_main"] == 1.0
