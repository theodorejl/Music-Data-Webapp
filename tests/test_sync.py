from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.deezer_gw import PlayRecord, parse_history
from core.models import Album, Artist, Play, SyncRun, Track
from core.sync import estimate_listened, run_sync


class FakeSource:
    def __init__(self, records):
        self.records = records

    def fetch_recent(self):
        return list(self.records)


class FailingSource:
    def fetch_recent(self):
        raise RuntimeError("boom")


def count(engine, model):
    with Session(engine) as s:
        return s.scalar(select(func.count()).select_from(model))


def test_sync_is_idempotent(engine, history_response):
    source = FakeSource(parse_history(history_response))
    first = run_sync(engine, source, enrich=False, window=100)
    second = run_sync(engine, source, enrich=False, window=100)
    assert (first.fetched, first.inserted) == (6, 6)
    assert (second.fetched, second.inserted) == (6, 0)
    assert count(engine, Play) == 6
    assert count(engine, Track) == 5 and count(engine, Album) == 1 and count(engine, Artist) == 1
    with Session(engine) as s:
        runs = s.scalars(select(SyncRun)).all()
        assert [r.status for r in runs] == ["ok", "ok"]
        play = s.scalars(select(Play)).first()
        assert play.raw_json["SNG_ID"]


def test_estimated_durations_after_sync(engine, history_response):
    run_sync(engine, FakeSource(parse_history(history_response)), enrich=False, window=100)
    with Session(engine) as s:
        rows = {p.track_id: p for p in s.scalars(select(Play).order_by(Play.played_at)).all()}
        # "Within" (228 s) was followed by "Instant Crush" 229 s later -> capped at 228.
        assert rows[67238731].listened_seconds == 228
        # Last play: no next play yet -> full duration.
        assert rows[67238732].listened_seconds == 337
        assert all(p.duration_is_estimated for p in rows.values())


def test_new_play_updates_previous_estimate(engine):
    t0 = datetime(2026, 1, 1, 12, 0, 0)
    a = PlayRecord(track_id=1, played_at=t0, duration=200, title="A", artist_id=9, artist_name="X")
    run_sync(engine, FakeSource([a]), enrich=False, window=100)
    b = PlayRecord(track_id=2, played_at=t0 + timedelta(seconds=12), duration=180, title="B", artist_id=9, artist_name="X")
    run_sync(engine, FakeSource([b, a]), enrich=False, window=100)
    with Session(engine) as s:
        p = s.scalars(select(Play).where(Play.track_id == 1)).one()
        assert p.listened_seconds == 12  # skipped after 12 s


def test_gap_detection(engine):
    t0 = datetime(2026, 1, 1)
    old = [PlayRecord(track_id=i, played_at=t0 + timedelta(minutes=i), duration=60) for i in range(3)]
    run_sync(engine, FakeSource(old), enrich=False, window=3)
    # A full window (3 items) that does not overlap stored plays -> possible gap.
    new = [PlayRecord(track_id=10 + i, played_at=t0 + timedelta(days=1, minutes=i), duration=60) for i in range(3)]
    res = run_sync(engine, FakeSource(new), enrich=False, window=3)
    assert res.gap_start == t0 + timedelta(minutes=2)
    assert res.gap_end == t0 + timedelta(days=1)
    # An overlapping window -> no gap.
    overlap = new[1:] + [PlayRecord(track_id=99, played_at=t0 + timedelta(days=1, minutes=5), duration=60)]
    assert run_sync(engine, FakeSource(overlap), enrich=False, window=3).gap_start is None


def test_failed_fetch_is_recorded_and_raised(engine):
    import pytest

    with pytest.raises(RuntimeError):
        run_sync(engine, FailingSource(), enrich=False)
    with Session(engine) as s:
        run = s.scalars(select(SyncRun)).one()
        assert run.status == "error" and "boom" in run.error


def test_estimate_listened_pure():
    t = datetime(2026, 1, 1)
    rows = [(t, 200), (t + timedelta(seconds=30), 200), (t + timedelta(seconds=600), 150), (t + timedelta(hours=2), None)]
    assert estimate_listened(rows) == [30, 200, 150, None]
    assert estimate_listened([]) == []


def test_the_enrichment_logs_the_measured_reliability_of_the_sources(engine, monkeypatch, caplog):
    """Spec 4.2: the reliability weights are written in the log, to be read again."""
    import logging

    from core import genremodel, sync
    for step in ("enrich_public", "enrich_musicbrainz", "enrich_library_genres", "_artist_info"):
        monkeypatch.setattr(sync, step, lambda session, client, deadline: 0)
    monkeypatch.setattr(genremodel, "run", lambda engine: {"artists": 2, "sure": 1, "likely": 1, "neighbours": 0,
                                                           "missing": 0, "weights": {"deezer:1": 0.4, "mb_genre:0": 3.6}})
    with caplog.at_level(logging.INFO, logger="core.sync"):
        sync.run_enrichment(engine, budget_seconds=0, public=object(), mb=object())
    logged = [r.getMessage() for r in caplog.records if r.levelno == logging.INFO]
    assert any("deezer:1=0.4" in m and "mb_genre:0=3.6" in m for m in logged), logged
