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
