from datetime import datetime

import pytest

from core.deezer_gw import DeezerAPIError, extract_history_items, parse_history


def test_parse_recorded_response(history_response):
    plays = parse_history(history_response)
    assert len(plays) == 6
    first = plays[0]
    assert first.track_id == 67238732
    assert first.played_at == datetime(2026, 10, 28, 12, 2, 17)  # TS 1793188937, UTC
    assert first.title == "Instant Crush"
    assert first.artist_id == 27 and first.artist_name == "Daft Punk"
    assert first.album_id == 6575789
    assert first.duration == 337
    assert first.isrc == "USQX91300105"
    assert first.listened_seconds is None  # not provided by the API -> estimated later
    assert "SNG_ID" in first.raw and "TRACK_TOKEN" not in first.raw


def test_same_track_twice_gives_two_plays(history_response):
    plays = parse_history(history_response)
    assert [p.track_id for p in plays].count(67238728) == 2


def test_page_profile_shape(history_response):
    data = history_response["results"]["data"]
    wrapped = {"error": [], "results": {"TAB": {"history": {"data": data}}}}
    assert len(extract_history_items(wrapped)) == len(data)


@pytest.mark.parametrize("bad", [
    {"error": {"GATEWAY_ERROR": "Undefined or invalid output"}, "results": {}},
    {"error": [], "results": {"something": 1}},
    [],
])
def test_unexpected_responses_raise(bad):
    with pytest.raises(DeezerAPIError):
        extract_history_items(bad)


def test_item_without_timestamp_raises():
    with pytest.raises(DeezerAPIError):
        parse_history({"error": [], "results": {"data": [{"SNG_ID": "1"}]}})
