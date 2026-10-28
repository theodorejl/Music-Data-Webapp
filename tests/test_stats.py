from datetime import date, datetime, timedelta

import pandas as pd
import pytest

from core import stats
from core.models import play_key

T0 = datetime(2026, 3, 2, 8, 0, 0)  # Monday, 09:00 in Zurich (UTC+1)


def make_raw(aliases=None, tags=None) -> stats.RawData:
    plays = pd.DataFrame([
        # play_id, track, played_at, listened, track_title, album, artist
        (1, 100, T0, 200, "Song A", 10, 1),
        (2, 100, T0 + timedelta(minutes=5), 10, "Song A", 10, 1),
        (3, 101, T0 + timedelta(days=1), 180, "Song B", 10, 1),
        (4, 200, T0 + timedelta(days=2), 240, "Song C", 20, 2),
        (5, 300, T0 + timedelta(days=4), 120, "Song D", 30, 3),
    ], columns=["play_id", "track_id", "played_at", "listened_seconds", "track_title", "album_id", "artist_id"])
    plays["duration_is_estimated"] = True
    plays["track_version"] = None
    plays["track_duration"] = 240
    plays["isrc"] = None
    artists = pd.DataFrame({"id": [1, 2, 3], "name": ["Alpha", "Beta", "Alpha (dup)"],
                            "picture_medium": ["a.jpg", "b.jpg", "c.jpg"], "picture_xl": [None] * 3})
    albums = pd.DataFrame({"id": [10, 20, 30], "title": ["Album 1", "Album 2", "Album 3"], "artist_id": [1, 2, 3],
                           "release_date": [None] * 3, "label": [None] * 3, "cover_medium": ["1.jpg", "2.jpg", "3.jpg"],
                           "cover_xl": [None] * 3, "deezer_genres": [["Pop"], [], []]})
    tags = tags if tags is not None else pd.DataFrame(
        [("album", 20, "jazz", 5, "mb_genre"), ("album", 20, "bebop", 9, "mb_tag")],
        columns=["entity_type", "entity_id", "tag", "count", "source"])
    aliases = aliases if aliases is not None else pd.DataFrame(columns=["id", "kind", "source_key", "target", "created_at"])
    return stats.RawData(plays, artists, albums, tags, aliases)


def alias_df(rows):
    return pd.DataFrame([(i, k, s, t, None) for i, (k, s, t) in enumerate(rows)],
                        columns=["id", "kind", "source_key", "target", "created_at"])


def test_assemble_joins_and_genres():
    df = stats.assemble(make_raw())
    assert len(df) == 5
    by_track = df.set_index("play_id")
    assert by_track.loc[1, "artist_name"] == "Alpha"
    assert by_track.loc[1, "genre"] == "Pop"            # Deezer album genre
    assert by_track.loc[4, "genre"] == "Jazz"           # MusicBrainz fallback (genres only, not free tags)
    assert pd.isna(by_track.loc[5, "genre"])
    assert str(df["played_local"].dt.tz) == "Europe/Zurich"
    assert by_track.loc[1, "played_local"].hour == 9


def test_aliases_merge_hide_and_genres():
    aliases = alias_df([
        ("merge_artist", "3", "1"),
        ("hide_play", play_key(100, T0 + timedelta(minutes=5)), ""),
        ("album_genre", "30", "Electro"),
        ("rename_genre", "Pop", "Pop/Rock"),
    ])
    df = stats.assemble(make_raw(aliases))
    assert 2 not in set(df["play_id"])                       # hidden
    assert set(df["artist_id"]) == {1, 2}                    # artist 3 merged into 1
    assert df.loc[df["play_id"] == 5, "artist_name"].item() == "Alpha"
    assert df.loc[df["play_id"] == 5, "genre"].item() == "Electro"
    assert df.loc[df["play_id"] == 1, "genre"].item() == "Pop/Rock"
    top = stats.top(df, "artist", "plays")
    assert top.iloc[0]["label"] == "Alpha" and top.iloc[0]["plays"] == 3


def test_alias_chains_and_cycles_terminate():
    plays = pd.DataFrame({"track_id": [1], "played_at": [T0], "artist_id": [5], "album_id": [7]})
    aliases = alias_df([("merge_artist", "5", "6"), ("merge_artist", "6", "8"),
                        ("merge_album", "7", "9"), ("merge_album", "9", "7")])
    out = stats.apply_aliases(plays, aliases)
    assert out["artist_id"].item() == 8
    assert out["album_id"].item() in (7, 9)


def test_filter_and_kpis():
    df = stats.assemble(make_raw())
    tz = "Europe/Zurich"
    start = pd.Timestamp("2026-03-03", tz=tz)
    end = pd.Timestamp("2026-03-05", tz=tz)
    period = stats.filter_frame(df, start, end)
    assert set(period["play_id"]) == {3, 4}
    assert len(stats.filter_frame(df, min_seconds=30)) == 4
    k = stats.kpis(df)
    assert k["plays"] == 5 and k["artists"] == 3 and k["minutes"] == pytest.approx(750 / 60)


def test_top_by_minutes_and_genre():
    df = stats.assemble(make_raw())
    by_min = stats.top(df, "track", "minutes", 2)
    assert list(by_min["label"]) == ["Song C", "Song A"]  # 240 s vs 210 s
    genres = stats.top(df, "genre", "plays")
    assert dict(zip(genres["label"], genres["plays"])) == {"Pop": 3, "Jazz": 1}


def test_timeline_fills_missing_days():
    df = stats.assemble(make_raw())
    tl = stats.timeline(df, "D")
    assert len(tl) == 5 and tl["plays"].sum() == 5
    assert tl.loc[tl["period"] == pd.Timestamp("2026-03-05"), "plays"].item() == 0
    cum = stats.cumulative(df, "D")
    assert cum["plays"].iloc[-1] == 5


def test_heatmap_streaks_skips():
    df = stats.assemble(make_raw())
    hm = stats.heatmap(df)
    assert hm.shape == (7, 24) and hm.values.sum() == 5 and hm.loc[0, 9] == 2
    s = stats.streaks(df, today=date(2026, 3, 20))
    assert s["longest"] == 3 and s["current"] == 0 and s["active_days"] == 4
    assert stats.skip_rate(df, 30) == pytest.approx(0.2)
    ms = stats.most_skipped(df, 30)
    assert ms.iloc[0]["track_title"] == "Song A" and ms.iloc[0]["skips"] == 1


def test_share_over_time_sums_to_one():
    df = stats.assemble(make_raw())
    sh = stats.share_over_time(df, "artist", "W", top_n=1, other_label="Other")
    totals = sh.groupby("period", observed=True)["share"].sum()
    assert all(abs(v - 1) < 1e-9 for v in totals)
    assert "Other" in set(sh["label"].astype(str))


def test_first_listens_and_discoveries():
    df = stats.assemble(make_raw())
    f = stats.first_listens(df, "artist")
    assert len(f) == 3
    per_month = stats.discoveries_per_month(df)
    assert per_month["new_artists"].sum() == 3 and per_month["new_albums"].sum() == 3


def test_search_history():
    df = stats.assemble(make_raw())
    assert len(stats.search_history(df, "beta")) == 1
    assert len(stats.search_history(df, "song a")) == 2
    assert len(stats.search_history(df, "")) == 5


def test_empty_frames():
    raw = make_raw()
    raw.plays = raw.plays.iloc[0:0]
    df = stats.assemble(raw)
    assert df.empty
    assert stats.top(df, "artist").empty
    assert stats.timeline(df).empty
    assert stats.kpis(df)["plays"] == 0
