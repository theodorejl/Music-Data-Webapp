"""The map of sound as a page: one style for « Pour toi » and Univers, in the colours of the page."""

from app.components import interactive

KEYS = ("density", "artists", "found", "zones", "search", "fit", "whole", "hint", "play", "pause", "no_preview", "because",
        "count", "plays", "minutes", "lists", "favs", "open", "lv0", "lv1", "lv2", "zone", "zoom_in", "genre", "artist",
        "label", "words")
LABELS = {k: f"<{k}>" for k in KEYS}
ARTISTS = {"id": [27], "n": ["Daft Punk"], "p": [""], "x": [.5], "y": [.5], "m": [0], "s": [3], "g": ["house"], "lv": [0],
           "pl": [2], "mn": [11], "lt": [58], "fa": [2], "w": [3.0], "lb": ["Daft Life"], "tg": ["house"], "sr": ["Discogs"]}


def test_the_map_is_drawn_in_fira_code_and_the_colours_of_its_page():
    html = interactive.sound_map_html(ARTISTS, [], [], LABELS, "#ff7a59", "fr", family="ocean")
    assert "Rubik" not in html and "d3-delaunay" not in html  # one font; borders come from the atlas itself
    assert "#7591f6" in html and "#6fcbe8" in html and "#1d2b7a" in html  # the ocean family: its stops and its ink
    lilac = interactive.sound_map_html(ARTISTS, [], [], LABELS, "#ff7a59", "fr", family="lilac")
    assert "#9d8cf5" in lilac and "#7591f6" not in lilac


def test_the_univers_map_shows_albums_without_discoveries():
    albums = {"id": [302127], "n": ["Discovery"], "a": ["Daft Punk"], "ai": [27], "p": [""], "x": [.5], "y": [.5], "m": [0],
              "s": [3], "g": [""], "lv": [1], "lb": ["Virgin"], "fa": [1], "mn": [42], "pl": [9], "w": [4.0], "tg": [""], "sr": [""]}
    html = interactive.sound_map_html(albums, [], [], LABELS, "#7d5ef0", "fr", family="lilac", kind="albums")
    assert "<zones>" not in html and "<found>" not in html  # no discoveries, no rings to zoom on them
    assert "https://www.deezer.com/album/" in html


def test_every_text_of_the_map_is_fira_code_medium():
    import re
    html = interactive.sound_map_html(ARTISTS, [], [], LABELS, "#ff7a59", "fr", family="ocean")
    assert "Fira+Code:wght@500&" in html  # only the medium weight is loaded
    weights = re.findall(r"font-weight:(\d+)", html) + re.findall(r"font:(\d+) ", html)  # the page
    weights += re.findall(r"[`'](\d00) [\d.$]", html) + re.findall(r",(\d00),(?:ink|rgba|MC)", html)  # the canvas
    assert weights and set(weights) == {"500"}, set(weights)


def test_the_counts_of_the_map_agree_with_their_number():
    import json
    import pathlib
    for lang, one in (("fr", "1 titre dans tes playlists"), ("en", "1 track in your playlists")):
        reco = json.loads(pathlib.Path(f"app/i18n/{lang}.json").read_text())["reco"]
        for key in ("map_count", "map_plays", "map_lists", "map_favs"):
            assert reco[key].count("|") == 1, (lang, key)  # « 1 écoute|{n} écoutes »: singular, then plural
        assert reco["map_lists"].split("|")[0].replace("{n}", "1") == one
    html = interactive.sound_map_html(ARTISTS, [], [], LABELS, "#ff7a59", "fr", family="ocean")
    assert "split('|')" in html  # the map picks the form that matches the number
