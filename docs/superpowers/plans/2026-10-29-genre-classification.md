# Reliable Artist Genre Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decide every artist's genre from cross-checked evidence (Every Noise, Wikidata, MusicBrainz, Discogs, Last.fm, Deezer) with measured source reliability and Deezer related-artist propagation, and place each artist on a precise genre of the atlas.

**Architecture:** Two new data sources (a frozen Every Noise artist index in `app/assets/`, Deezer related artists in a new table) feed `core/genremodel.py`, which builds per-source evidence on the genre tree, learns per-(source, main genre) reliability (one-coin Dawid-Skene), propagates over the neighbour graph, and writes one decision per artist to a new table `artist_genre` at each sync. `core/atlas.py` reads those decisions and lays artists out in a sunflower spiral around their genre.

**Tech Stack:** Python 3.12, SQLAlchemy 2, pandas, numpy (already a pandas dependency), requests, pytest; Playwright (scratchpad venv) for browser checks.

**Spec:** `docs/superpowers/specs/2026-10-29-genre-classification-design.md`

## Global Constraints

- No new dependency in `requirements.txt` (no scipy): numpy arrays only.
- Every Noise is cited: "Every Noise at Once, everynoise.com (Glenn McDonald)" in the index file, the README and the existing map caption.
- Crawl politeness: one Every Noise request per second; Deezer through `DeezerPublicClient` (45 requests / 5 s); MusicBrainz 1 request / s (existing `_Pace`).
- The decision is never displayed with a confidence; the tooltip keeps today's fields (genre, label, words, sources).
- Initial reliability weights are today's `atlas.WEIGHT` plus `everynoise: 3.0`, `everynoise_name: 1.5`, `artist_model: 2.0`.
- Reliability: prior of 10 artists, bounds 0.2× to 3× the starting weight, at most 20 rounds.
- Neighbours: Deezer related weight `1 / (1 + rank / 5)` (rank from 0), playlists `0.3 × min(1, shared / 3)` ignoring playlists over 300 tracks; propagation at most 10 rounds; `λ = 1 / (1 + own mass)`; neighbours override when own mass < 1 and neighbours give > 60 % to another main genre.
- Every Noise mass per genre: `1 / (1 + rank / 50)`.
- The `.env` cookie and tokens never appear in code, logs, tests or commits.
- Tests run with `.venv/bin/python -m pytest -q`; the whole suite stays green after every task.

## Review Focus

1. An artist with no evidence and no neighbour must stay off the map and be counted as missing, as today (test in Task 6).
2. An artist synced after the last classification (no `artist_genre` row) must still appear, through today's vote (test in Task 8).
3. An Every Noise page that 404s or has no artists must not stop the crawl; a layout change (fewer than 100 000 artists overall) must fail loudly (tests in Task 1).
4. An artist whose Spotify id is known but absent from the index must get no Every Noise evidence, never a name match (test in Task 4).
5. The app must work without the index file and without the `artist_genre` table (old published database on the hosted site) (test in Task 8).

---

### Task 1: Every Noise index (parser, index, crawler)

**Files:**
- Create: `core/everynoise.py`, `scripts/build_everynoise_index.py`
- Create: `tests/fixtures/everynoise_main.html`, `tests/fixtures/everynoise_genre.html`, `tests/test_everynoise.py`

**Interfaces:**
- Produces:
  - `ASSET: Path`, the file `app/assets/everynoise_artists.json.gz`.
  - `genre_links(main_html: str) -> dict[str, str]`: genre name → `engenremap-….html`.
  - `parse_genre_page(page: str) -> list[tuple[str, str, int]]`: (Spotify artist id, name, rank from 1).
  - `norm_name(name: str) -> str`: NFKD, ASCII, lowercase, only `[a-z0-9]`.
  - `build_index(pages: dict[str, list[tuple[str, str, int]]]) -> dict`: `{"source": str, "genres": [name], "artists": {sid: [name, [[genre_idx, rank], …]]}}`.
  - `save(index: dict, path: Path = ASSET) -> None`: gzip with `mtime=0`.
  - `load(path: Path = ASSET) -> Index | None`: cached; returns None when the file is missing.
  - `class Index(data: dict)` with:
    - `genres_of(sid: str) -> list[tuple[str, int]]`;
    - `ids_named(name: str) -> list[str]`;
    - `name_of(sid: str) -> str`;
    - `__len__`.

- [ ] **Step 1: Write the fixtures.**
  - `everynoise_genre.html`: the three `<div id=item1..3 …>` lines of the live nu disco page (SG Lewis `0GG2cWaonE4JPrjcCCQ1EG`, The Knocks `2x7EATekOPhFGRx3syMGEC`, Panama `3W9UldYu0xJcaOAw2SUTDI`), as returned by `curl https://everynoise.com/engenremap-nudisco.html`.
  - `everynoise_main.html`: the `item1` (pop, `engenremap-pop.html`) and `item12` (musica mexicana) divs of `https://everynoise.com/engenremap.html`, each followed by its `<a class=navlink href="engenremap-….html"`.

- [ ] **Step 2: Write the failing tests** in `tests/test_everynoise.py`:

```python
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
```

- [ ] **Step 3: Run the tests.** Run `.venv/bin/python -m pytest -q tests/test_everynoise.py`. Expected: FAIL (`No module named core.everynoise`).

- [ ] **Step 4: Implement `core/everynoise.py`.** In `parse_genre_page`:
  - the rank is the `id=itemN` number;
  - the name is the unescaped text before `<a class=navlink`;
  - the id comes from `artistprofile.html?id=([0-9A-Za-z]{22})`.

  `load` clears its cache per path (key the `lru_cache` on the path).

- [ ] **Step 5: Run the tests.** Run `.venv/bin/python -m pytest -q tests/test_everynoise.py`. Expected: PASS.

- [ ] **Step 6: Implement `scripts/build_everynoise_index.py`** (`python -m scripts.build_everynoise_index [--pause 1.0]`).
  - Cache the main page as `data/everynoise/_main.html`, and each genre page as `data/everynoise/<slug>.html`.
  - A cached page is never fetched again; a 404 is cached as an empty file.
  - Print progress every 100 pages.
  - At the end:
    - build the index from all cached pages and `save` it;
    - print the artist count and the file size;
    - raise `SystemExit` if there are fewer than 100 000 artists (Review Focus 3).

- [ ] **Step 7: Start the real crawl in the background.** Run `.venv/bin/python -m scripts.build_everynoise_index > logs/everynoise.log 2>&1` (about 1 h 45). The later tasks do not wait for it, except Task 10.

- [ ] **Step 8: Commit.** Commit code and fixtures, not the asset yet: `git commit -m "Every Noise artist index: page parser, index, resumable crawler"`.

### Task 2: Spotify ids from Wikidata and MusicBrainz

**Files:**
- Modify: `core/artistinfo.py` (`Wikidata.lookup`, `enrich`, new `enrich_spotify_ids`), `scripts/enrich_artists.py`
- Test: `tests/test_artistinfo.py`

**Interfaces:**
- Produces:
  - Rows in `tags` with `entity_type="artist_spotify"`, `tag=<22-char id>`, `source` in {`wikidata`, `musicbrainz`}.
  - `Wikidata.lookup` items gain `"spotify": list[str]`.
  - `enrich_spotify_ids(session, deadline, wikidata, musicbrainz) -> dict[str, int]`.
  - New `checked` keys: `spotify_wd` and `spotify_mb`.

- [ ] **Step 1: Write the failing tests.**
  - The existing Wikidata fixture gains `"spotify": {"value": "4tZwfgrHOc3mvqYlEYSvVi"}`, and `lookup` returns `"spotify": ["4tZwfgrHOc3mvqYlEYSvVi"]`.
  - `test_enrich_stores_spotify_ids_from_wikidata_and_musicbrainz`:
    - a fake MusicBrainz returns `relations=[{"url": {"resource": "https://open.spotify.com/artist/0GG2cWaonE4JPrjcCCQ1EG"}}]`;
    - expect both `("artist_spotify", 1, "4tZwfgrHOc3mvqYlEYSvVi", "wikidata")` and the MusicBrainz row.
  - `test_spotify_backfill_asks_only_artists_not_asked_yet`: an artist already marked `wikidata` but not `spotify_wd` is looked up once; a second call looks up nothing.

- [ ] **Step 2: Run the tests.** Run `.venv/bin/python -m pytest -q tests/test_artistinfo.py`. Expected: FAIL on `spotify`.

- [ ] **Step 3: Implement the change.**
  - In the SPARQL query, add `OPTIONAL { ?item wdt:P1902 ?sp }` and `(GROUP_CONCAT(DISTINCT ?sp; separator="|") AS ?spotify)`.
  - `enrich` stores the ids from both sources (regex `open\.spotify\.com/artist/([0-9A-Za-z]{22})` on MusicBrainz relations) and marks `spotify_wd` / `spotify_mb` when it stored them.
  - `enrich_spotify_ids`:
    - Wikidata in batches of 300 for artists asked `wikidata` but not `spotify_wd`;
    - then `musicbrainz.artist(mbid)` for artists with an mbid not asked `spotify_mb`;
    - both stop at the deadline.
  - `scripts/enrich_artists.py`: `--spotify-ids` runs only `enrich_spotify_ids`.

- [ ] **Step 4: Run the tests.** Run `.venv/bin/python -m pytest -q`. Expected: all PASS.

- [ ] **Step 5: Commit.** `git commit -m "Spotify ids of artists from Wikidata and MusicBrainz"`.

### Task 3: Deezer related artists

**Files:**
- Modify: `core/models.py` (new `ArtistRelated`), `core/deezer_public.py` (`related`), `core/artistinfo.py` (`fetch_related`, `enrich_from_settings`), `scripts/enrich_artists.py` (`--related`), `scripts/migrate_sqlite_to_postgres.py` (`TABLES`)
- Test: `tests/test_artistinfo.py`, `tests/test_cloud_db.py`

**Interfaces:**
- Produces:
  - Table `artist_related`: `artist_id` BigInteger PK, `related_id` BigInteger PK, `rank` Integer (0 = closest), `related_name` String(300).
  - `DeezerPublicClient.related(artist_id: int, limit: int = 20) -> list[dict]`.
  - `fetch_related(session, public, deadline, progress=None) -> int`, with `checked` key `deezer_related`.
  - `TABLES` gains `(ArtistRelated, ["artist_id", "related_id"], [])`.

- [ ] **Step 1: Write the failing tests.**
  - `test_related_artists_are_stored_with_their_rank_once`: a fake public client returns 3 related artists for artist 1. Expect 3 rows with ranks 0, 1, 2 and their names; a second call asks nothing.
  - In `test_cloud_db.py`, `test_publish_and_pull_round_trip` also checks that an `ArtistRelated` row published by A is present in B after `pull`.

- [ ] **Step 2: Run the tests.** Run `.venv/bin/python -m pytest -q tests/test_artistinfo.py tests/test_cloud_db.py`. Expected: FAIL (`ArtistRelated` missing).

- [ ] **Step 3: Implement the change.**
  - `related` calls `get(f"artist/{id}/related?limit={limit}")` and returns `data["data"]` or `[]`.
  - `fetch_related` loops over `library_artists(session)` not asked yet, commits every 50, and stops at the deadline.
  - `enrich_from_settings` runs `enrich_spotify_ids` and then `fetch_related` after `enrich`, within the same deadline.
  - `--related` runs only `fetch_related`.

- [ ] **Step 4: Run the tests.** Run `.venv/bin/python -m pytest -q`. Expected: all PASS.

- [ ] **Step 5: Start the real backfill in the background,** one after the other so SQLite has one writer: `.venv/bin/python -m scripts.enrich_artists --related --minutes 30 && .venv/bin/python -m scripts.enrich_artists --spotify-ids --minutes 60`. Log to `logs/related.log`.

- [ ] **Step 6: Commit.** `git commit -m "Deezer related artists, stored and published"`.

### Task 4: Evidence on the genre tree

**Files:**
- Create: `core/genremodel.py`, `tests/test_genremodel.py`

**Interfaces:**
- Consumes: `atlas.meaning`, `atlas._strength`, `atlas._artist_votes`, `everynoise.Index`, `genretree.tree()` (`main` 22, `sub` 162 with `main`, `genres` as `[name, sub, x, y]` in popularity order).
- Produces:
  - `W0: dict[str, float]` (Global Constraints).
  - `@dataclass Evidence`, with `main: np.ndarray` (shape 22), `sub: dict[int, float]`, `genre: dict[str, float]`, `words: Counter`, and `.mass -> float` (= `main.sum()`).
  - `word_evidence(votes: list[tuple[str, str, float]]) -> dict[str, Evidence]`: keyed by source.
  - `everynoise_evidence(genres: list[tuple[str, int]]) -> Evidence`.
  - `match_everynoise(index, spotify_of: dict[int, list[str]], names: dict[int, str], context: dict[int, np.ndarray]) -> dict[int, tuple[str, str]]`: artist → (`"everynoise"` | `"everynoise_name"`, sid).

- [ ] **Step 1: Write the failing tests.**

```python
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
    assert 4 not in got                                    # its id is known and absent: never by name (Review Focus 4)
    assert got[5] == ("everynoise_name", "C"*22)         # unique name
```

- [ ] **Step 2: Run the tests.** Run `.venv/bin/python -m pytest -q tests/test_genremodel.py`. Expected: FAIL (no module).

- [ ] **Step 3: Implement the evidence.**
  - Genre mass also counts for its sub and its main; sub mass also counts for its main.
  - A homonym is accepted when the cosine between its Every Noise main vector and `context[a]` is ≥ 0.6 and beats the runner-up by ≥ 0.2.

- [ ] **Step 4: Run the tests.** Run `.venv/bin/python -m pytest -q tests/test_genremodel.py`. Expected: PASS.

- [ ] **Step 5: Commit.** `git commit -m "Genre model: evidence on the tree, Every Noise identity"`.

### Task 5: Measured source reliability

**Files:**
- Modify: `core/genremodel.py`
- Test: `tests/test_genremodel.py`

**Interfaces:**
- Produces: `reliability(ev: dict[int, dict[str, Evidence]], prior: dict[str, float] = W0, rounds: int = 20) -> dict[tuple[str, int], float]`, the weight of (source, main genre).

- [ ] **Step 1: Write the failing test.** `test_a_source_that_is_always_wrong_loses_weight`, on 40 toy artists:
  - sources `mb_genre` and `wikidata` both say main 0 (electronic);
  - `deezer` always says main 1.
  - Expect:
    - `w[("deezer", 1)] < W0["deezer"]` and `≥ 0.2 * W0["deezer"]`;
    - `w[("mb_genre", 0)] >= W0["mb_genre"]` and `≤ 3 * W0["mb_genre"]`.

- [ ] **Step 2: Run the test.** Run `.venv/bin/python -m pytest -q tests/test_genremodel.py`. Expected: FAIL (`reliability` missing).

- [ ] **Step 3: Implement `reliability`.**

```text
weights = {(s, m): W0[s]}
repeat ≤ rounds:
  for each artist a, source s with evidence: top_s = argmax(ev[a][s].main)
    others = Σ_{s'≠s} weights[(s', ·)] ⊙ normalised(ev[a][s'].main);  skip if others is all zero
    n[s, top_s] += 1;  agree[s, top_s] += (argmax(others) == top_s)
  acc = (agree + 10·0.7) / (n + 10)                              # prior: 10 artists at 70 %
  new[(s, m)] = W0[s] · clip(logit(acc) / logit(0.7), 0.2, 3)    # one-coin Dawid–Skene log-odds
  stop when max |new − weights| < 1e-3
```

- [ ] **Step 4: Run the tests.** Run `.venv/bin/python -m pytest -q tests/test_genremodel.py`. Expected: PASS.

- [ ] **Step 5: Commit.** `git commit -m "Genre model: reliability of each source per main genre"`.

### Task 6: Neighbours, propagation, decision

**Files:**
- Modify: `core/genremodel.py`
- Test: `tests/test_genremodel.py`

**Interfaces:**
- Consumes: `Evidence`, `reliability`, `everynoise.Index`.
- Produces:
  - `graph(related: pd.DataFrame, playlist_tracks: pd.DataFrame, index: Index | None) -> tuple[list[tuple[int, int, float]], dict[int, Evidence]]`: symmetric edges between Deezer artist ids, plus fixed evidence for related artists outside the library (Every Noise by unique name; skipped otherwise). Each artist keeps at most 30 playlist neighbours, the most shared first.
  - `@dataclass Decision`, with `main: int`, `sub: int`, `genre: str`, `confidence: str` (`sure` | `likely` | `neighbours`), `words: list[str]`, `sources: list[str]`.
  - `classify(ids: list[int], ev: dict[int, dict[str, Evidence]], weights, edges, external: dict[int, Evidence]) -> dict[int, Decision]`.

- [ ] **Step 1: Write the failing tests:**
  - `test_an_artist_without_evidence_takes_the_genre_of_its_neighbours`:
    - artist 9 has no evidence;
    - its 5 related artists are in "deep house";
    - expect the deep house sub, and `confidence == "neighbours"`.
  - `test_a_lone_pop_word_yields_to_neighbours_all_in_house`:
    - own evidence is only `("Pop", "deezer_top")`;
    - neighbours are all in house;
    - expect the house sub.
  - `test_solid_evidence_keeps_its_genre_against_neighbours`: two sources say jazz fusion, neighbours say house. Expect fusion, with `confidence != "neighbours"`.
  - `test_a_multi_genre_artist_goes_to_its_dominant_genre_on_a_precise_genre`:
    - 60 % house words and 40 % jazz words;
    - expect the house main and a genre name `g` where `position()[g][2]` is the house sub.
  - `test_an_isolated_artist_without_anything_is_not_decided`: an artist with no evidence and no edge is absent from the result (Review Focus 1).
  - `test_two_agreeing_sources_make_a_sure_decision`: `mb_genre` and `discogs` agree on nu disco. Expect `confidence == "sure"`.

- [ ] **Step 2: Run the tests.** Run `.venv/bin/python -m pytest -q tests/test_genremodel.py`. Expected: FAIL.

- [ ] **Step 3: Implement the change.**
  - **Own evidence:**
    - `E_main = Σ_s weights[(s,·)] ⊙ ev_s.main / max(1, ev_s.mass)`, and likewise for subs; own mass `M = E_main.sum()`.
  - **Propagation:**
    - dense numpy arrays `(n, 22)` and `(n, 162)`;
    - `N_i` is the weighted mean of the neighbours' P (external ones fixed);
    - `P_i = normalise(E_i + λ_i · min(3, Σ_j w_ij) · N_i)` with `λ_i = 1 / (1 + M_i)`;
    - `np.add.at` over edge arrays; at most 10 rounds, stop below 1e-4.
  - **Override:** if `M_i < 1`, `max(N_i) > 0.6` and `argmax(N_i) != argmax(E_i)`, then `P_i = N_i`.
  - **Decision, top-down:**
    - main = argmax P_main;
    - sub = argmax P_sub restricted to that main; if all zero, the sub of the main's most popular genre;
    - genre = argmax of own genre masses plus `Σ_j w_ij ·` the neighbours' own genre masses, restricted to that sub; if all zero, the sub's most popular genre.
  - **Confidence:**
    - `sure` if at least two source families (MusicBrainz counted once: mb_genre, mb_tag and album) have their top sub equal to the chosen sub, or `everynoise` (id) agrees on the sub;
    - `neighbours` if `M = 0` or the override fired;
    - `likely` otherwise.
  - **words / sources:**
    - with own evidence: the 4 strongest supporting words, and the source names via `atlas.SOURCE_NAME` plus `everynoise → "Every Noise"`;
    - for `neighbours`: `words=[]` and `sources=["Deezer"]`.

- [ ] **Step 4: Run the tests.** Run `.venv/bin/python -m pytest -q`. Expected: all PASS.

- [ ] **Step 5: Commit.** `git commit -m "Genre model: neighbours, propagation, top-down decision"`.

### Task 7: Store decisions at each sync

**Files:**
- Modify: `core/models.py` (`ArtistGenre`), `core/genremodel.py` (`run`), `core/sync.py` (`run_enrichment`), `core/cloud_db.py` (`SNAPSHOT_TABLES`), `scripts/migrate_sqlite_to_postgres.py` (`TABLES`)
- Create: `scripts/classify_genres.py`
- Test: `tests/test_genremodel.py`, `tests/test_cloud_db.py`

**Interfaces:**
- Produces:
  - Table `artist_genre`: `artist_id` PK, `main` Integer, `sub` Integer, `genre` String(200), `confidence` String(12), `words` JSON, `sources` JSON, `updated` DateTime.
  - `run(engine) -> dict`: loads with `stats.load_raw`, `stats.load_library` and `stats.assemble(raw, "UTC")`, plus `artist_related`, Spotify tags and the index. It replaces every row of `artist_genre` and returns `{"artists", "sure", "likely", "neighbours", "missing", "weights"}`.
  - `scripts/classify_genres.py` prints that summary.

- [ ] **Step 1: Write the failing tests.**
  - `test_run_writes_one_decision_per_artist_and_replaces_them`: an engine with two artists and tags. After `run`, there are 2 rows; a second `run` still gives 2 rows.
  - `test_round_trip` in `test_cloud_db.py`: an `artist_genre` row only on B is replaced by A's published rows after `pull` (snapshot table).

- [ ] **Step 2: Run the tests.** Run `.venv/bin/python -m pytest -q tests/test_genremodel.py tests/test_cloud_db.py`. Expected: FAIL.

- [ ] **Step 3: Implement the change.**
  - `run` works in this order:
    1. votes (`atlas._artist_votes`), then `word_evidence`;
    2. Spotify ids from the `artist_spotify` tags;
    3. the context of each artist: its own main vector, else the mean Every Noise main vector of its related artists;
    4. `match_everynoise`, then `everynoise_evidence` under the matched source key;
    5. `graph`, `reliability`, `classify`;
    6. store.
  - `run_enrichment` calls `genremodel.run(engine)` after enrichment, inside `try/except Exception` with a logged warning: a failed classification must never fail the sync.
  - Add `"artist_genre"` to `SNAPSHOT_TABLES`, and `(ArtistGenre, ["artist_id"], [])` to `TABLES`.

- [ ] **Step 4: Run the tests.** Run `.venv/bin/python -m pytest -q`. Expected: all PASS.

- [ ] **Step 5: Commit.** `git commit -m "Genre decisions stored at each sync and published"`.

### Task 8: Atlas placement from the decisions

**Files:**
- Modify: `core/atlas.py` (`place`, `place_albums`, new `_spiral`), `core/stats.py` (`RawData.artist_genre`, `load_raw`), `app/views/foryou.py:188`, `app/views/explore.py:28-32`
- Test: `tests/test_atlas.py`

**Interfaces:**
- Consumes: the `artist_genre` table.
- Produces:
  - `place(..., decisions: pd.DataFrame | None = None)` and `place_albums(..., decisions: pd.DataFrame | None = None)`.
  - `_spiral(points: list[dict]) -> None`: sets x and y in place.
  - `SPIRAL = 0.002` (y units).
  - `RawData.artist_genre`: empty DataFrame when the table is missing or empty.

- [ ] **Step 1: Write the failing tests.**
  - `test_place_uses_the_stored_decision`: the decision says nu disco. The point has `g == "nu disco"`, `lv == GENRE`, and lies inside its sub polygon.
  - `test_an_artist_without_a_decision_still_appears`: one artist has no row in `decisions`, so today's vote places it (Review Focus 2). Also, `decisions=None` and an empty frame both behave like today (Review Focus 5).
  - `test_the_spiral_keeps_artists_apart_and_inside`:
    - 200 artists on one genre;
    - every pair is ≥ 0.0034 apart in y units (x scaled by `ASPECT`);
    - every point is inside its sub polygon;
    - the most listened artist is the closest to the genre point.
  - `test_an_album_without_its_own_genres_follows_its_artist`: the album has no tag, and its artist's decision is nu disco, so the album lands in the disco sub.

- [ ] **Step 2: Run the tests.** Run `.venv/bin/python -m pytest -q tests/test_atlas.py`. Expected: FAIL.

- [ ] **Step 3: Implement the change.**
  - **Spiral:** offsets `r = SPIRAL·√(i+0.5)` and `θ = i·137.508°`, ordered by weight `w` descending; x offset divided by `ASPECT`. Then the existing clamp towards the sub centre.
  - **Albums:** `place_albums` adds the vote `(decision.genre, "artist_model", 1.0)`; it replaces the artist's raw votes when a decision exists. Albums are spiralled too.
  - **Views:** pass `decisions=raw.artist_genre`, and add `len(raw.artist_genre)` to the `_atlas_points` cache key.

- [ ] **Step 4: Run the tests.** Run `.venv/bin/python -m pytest -q`. Expected: all PASS.

- [ ] **Step 5: Commit.** `git commit -m "Atlas: artists on their decided genre, in a sunflower spiral"`.

### Task 9: Nothing drawn outside its territory

**Files:**
- Modify: `app/components/interactive.py` (`SOUND_MAP_JS`, after the anti-overlap relaxation)
- Verification script: scratchpad `stray.py` (Playwright), extended

- [ ] **Step 1: Extend `stray.py`** to check both maps at zooms 1, 3, 8 and 16, over 4 places each. Count the drawn artist and discovery nodes outside their own territory polygon (discoveries: outside `T.o`). Print one line per check.

- [ ] **Step 2: Run it.** Run `pw/bin/python stray.py <shots>`. Record the counts: zero or not, today.

- [ ] **Step 3: Implement the clamp.** After the relaxation, a node whose world point is outside its polygon goes back along the segment towards its unrelaxed position: 8 bisection steps, keeping the inside end.

- [ ] **Step 4: Run it again.** Run `pw/bin/python stray.py <shots>` in Chrome and WebKit. Expected: every line shows 0 outside.

- [ ] **Step 5: Commit.** `git commit -m "Map: what the anti-overlap moves stays inside its territory"`.

### Task 10: Evaluation, real run, documentation

**Files:**
- Create: `scripts/genre_eval.py`
- Modify: `README.md` (map and genre sections)
- Test: `tests/test_genremodel.py`

**Interfaces:**
- Produces: `evaluate(ev, weights, edges, external) -> dict` with:
  - `{"reference": n, "cold_main", "cold_sub", "cold_main_old", "single_main", "single_sub"}` (accuracies in 0..1);
  - a `sample(n=40)` helper for the human read.

- [ ] **Step 1: Write the failing test.** `test_evaluation_reports_cold_and_single_source_accuracy`: on a toy graph where neighbours agree with the reference, `cold_main == 1.0` and `0 ≤ single_sub ≤ 1`.

- [ ] **Step 2: Run the test.** Run `.venv/bin/python -m pytest -q tests/test_genremodel.py`. Expected: FAIL.

- [ ] **Step 3: Implement `evaluate`.**
  - The reference set is the artists where at least two source families, or Every Noise by id, agree on the sub.
  - **Cold:** drop each reference artist's own evidence, then `classify`.
  - **Old:** `atlas.decide` on the playlist guess, as `place` does today.
  - **Single:** keep one random source per reference artist (seed 0).

- [ ] **Step 4: Run the tests.** Run `.venv/bin/python -m pytest -q`. Expected: all PASS.

- [ ] **Step 5: Real run, once the crawl and backfills finish.**
  1. Check `ls -la app/assets/everynoise_artists.json.gz`. If it is over 25 MB, rebuild it keeping only artists whose normalised name is in `artists` or `artist_related`.
  2. `.venv/bin/python -m scripts.classify_genres`
  3. `.venv/bin/python -m scripts.genre_eval`
  4. Check the guard cases in the output: Wally Badarou has a jazz main (fusion or jazz-funk); Lewis OfMan has an electronic or indie main (nu disco, french indie pop…).

- [ ] **Step 6: Verify the maps.**
  - Both maps load: re-run the map screenshots and `stray.py`.
  - The sweep and the app test: `$SP/sweep.py` and `$SP/apptest.py`, 0 errors.

- [ ] **Step 7: Update the README.**
  - Map section: the new sources (Every Noise index, Deezer related artists), the measured reliability, the neighbours, the spiral and the evaluation figures.
  - First-run commands.
  - Every Noise citation.

- [ ] **Step 8: Check for secrets, then commit the asset and the docs, then push.** `git commit -m "Genre model: Every Noise index, evaluation, README"` then `git push`.
