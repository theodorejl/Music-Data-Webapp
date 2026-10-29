from pathlib import Path

from core import everynoise

FIXTURES = Path(__file__).parent / "fixtures"


def FIX(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_a_genre_page_gives_artist_ids_not_track_ids():
    rows = everynoise.parse_genre_page(FIX("everynoise_genre.html"))
    assert rows[0] == ("0GG2cWaonE4JPrjcCCQ1EG", "SG Lewis", 1)   # the artistprofile id, not playx's track id
    assert [r[2] for r in rows] == [1, 2, 3]
    assert everynoise.parse_genre_page("<html>nothing</html>") == []


def test_the_main_map_links_every_genre_page():
    links = everynoise.genre_links(FIX("everynoise_main.html"))
    assert links["pop"] == "engenremap-pop.html" and "musica mexicana" in links


def test_the_index_gathers_the_genres_of_each_artist_and_finds_names(tmp_path):
    idx = everynoise.build_index({"nu disco": [("A" * 22, "Panama", 3)], "indietronica": [("A" * 22, "Panama", 40), ("B" * 22, "Panamá", 9)]})
    everynoise.save(idx, tmp_path / "i.json.gz")
    i = everynoise.load(tmp_path / "i.json.gz")
    assert sorted(i.genres_of("A" * 22)) == [("indietronica", 40), ("nu disco", 3)]
    assert sorted(i.ids_named("PANAMA!")) == ["A" * 22, "B" * 22]          # names compared normalised
    assert everynoise.load(tmp_path / "missing.json.gz") is None


def test_the_crawler_caches_pages_and_never_fetches_twice(tmp_path):
    from scripts import build_everynoise_index as crawler

    calls = []

    def fake(name):
        calls.append(name)
        return {"engenremap.html": FIX("everynoise_main.html"), "engenremap-pop.html": FIX("everynoise_genre.html")}.get(name, "")

    index = crawler.crawl(tmp_path, pause=0, get=fake)
    assert index["genres"] == ["pop", "musica mexicana"]
    assert len(index["artists"]) == 3                      # the 404 genre is cached empty and adds nothing
    assert (tmp_path / "engenremap-musicamexicana.html").read_text() == ""
    n = len(calls)
    assert crawler.crawl(tmp_path, pause=0, get=fake) == index and len(calls) == n


def test_names_without_latin_letters_are_never_matched_by_name():
    idx = everynoise.Index(everynoise.build_index({"g": [("A" * 22, "坂本龍一", 1), ("B" * 22, "Кино", 2), ("C" * 22, "!!!", 3)]}))
    assert idx.ids_named("坂本龍一") == [] and idx.ids_named("Кино") == [] and idx.ids_named("!!!") == []
    assert idx.name_of("A" * 22) == "坂本龍一"
