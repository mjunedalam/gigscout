"""Platform building blocks in isolation: security, the event bus, cron parsing and analytics."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from gigscout.platform import analytics
from gigscout.platform.events import EventBus
from gigscout.platform.scheduler import InvalidCron, parse_cron
from gigscout.platform.security import (
    LoginLimiter,
    WeakPasswordError,
    hash_password,
    hash_token,
    new_token,
    verify_password,
)
from gigscout.platform.tables import LeadState, Run
from gigscout.store.vector_store import StoredLead
from tests.conftest import make_lead


def test_password_hashing_round_trip_and_rejects_weak_passwords():
    stored = hash_password("correct-horse-battery")
    assert stored.startswith("scrypt$") and "correct" not in stored
    assert verify_password("correct-horse-battery", stored)
    assert not verify_password("wrong-password!", stored)
    assert not verify_password("anything", "garbage")
    with pytest.raises(WeakPasswordError):
        hash_password("tiny")


def test_tokens_are_random_and_only_hashes_are_stored():
    a, b = new_token(), new_token()
    assert a != b and len(a) >= 40
    assert hash_token(a) == hash_token(a) != hash_token(b)


def test_login_limiter_blocks_after_max_failures_and_resets():
    limiter = LoginLimiter(max_failures=2, window_seconds=60)
    limiter.record_failure("k")
    assert not limiter.blocked("k")
    limiter.record_failure("k")
    assert limiter.blocked("k") and not limiter.blocked("other")
    limiter.reset("k")
    assert not limiter.blocked("k")


def test_login_limiter_reserves_attempts_atomically():
    limiter = LoginLimiter(max_failures=2, window_seconds=60)
    assert limiter.try_attempt("k") and limiter.try_attempt("k")
    assert not limiter.try_attempt("k")
    limiter.reset("k")
    assert limiter.try_attempt("k")


def test_event_bus_delivers_across_threads_and_keeps_recent_history():
    bus = EventBus()

    async def scenario():
        sub = bus.subscribe()
        await asyncio.to_thread(bus.publish, "run.step", {"line": "hi"})
        bus.publish("metrics.snapshot", {"n": 1})
        first, second = await sub.queue.get(), await sub.queue.get()
        bus.unsubscribe(sub)
        return first, second

    first, second = asyncio.run(scenario())
    assert (first.type, first.data) == ("run.step", {"line": "hi"})
    assert second.type == "metrics.snapshot"
    assert [e.type for e in bus.recent()] == ["run.step"]  # snapshots are not activity
    assert bus.subscriber_count == 0


def test_create_db_adds_columns_missing_from_an_older_database(tmp_path):
    import sqlite3

    from gigscout.platform.db import create_db

    path = tmp_path / "old.db"
    with sqlite3.connect(path) as conn:  # a runs table from before run activity was stored
        conn.execute("CREATE TABLE runs (id VARCHAR(36) PRIMARY KEY, profile_name VARCHAR(120))")

    engine, _ = create_db(f"sqlite:///{path}")

    with engine.connect() as conn:
        columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(runs)")}
    assert "activity" in columns


def test_cron_parsing():
    assert parse_cron("*/30 * * * *", "UTC")
    with pytest.raises(InvalidCron):
        parse_cron("every tuesday", "UTC")


def _stored(pid: str, days_ago: float, **kw) -> StoredLead:
    return StoredLead(make_lead(pid, f"lead {pid}", **kw), datetime.now(UTC) - timedelta(days=days_ago))


def test_overview_timeseries_and_funnel():
    leads = [_stored("1", 0.1), _stored("2", 3, kind="inbound"), _stored("3", 30, kind="hiring")]
    states = {
        "fake:1": LeadState(lead_id="fake:1", status="won", score=0.9),
        "fake:2": LeadState(lead_id="fake:2", status="contacted", score=0.4),
    }
    now = datetime.now(UTC)
    runs = [
        Run(id="a", profile_name="p", mode_requested="auto", trigger="manual", triggered_by="x", status="succeeded",
            created_at=now, started_at=now, finished_at=now + timedelta(seconds=30)),
        Run(id="b", profile_name="p", mode_requested="auto", trigger="manual", triggered_by="x", status="failed",
            created_at=now - timedelta(days=10)),
    ]

    o = analytics.overview(leads, states, runs, threshold=0.6)
    assert (o.total_leads, o.new_last_24h, o.inbound_last_7d, o.qualified) == (3, 1, 1, 1)
    assert o.by_kind == {"project": 1, "hiring": 1, "inbound": 1}
    assert o.by_status["won"] == 1 and o.by_status["new"] == 1
    assert (o.runs_succeeded_7d, o.runs_failed_7d, o.avg_run_seconds) == (1, 0, 30.0)

    series = analytics.timeseries(leads, days=7)
    assert len(series) == 7 and sum(row["inbound"] for row in series) == 1 and series[-1]["project"] == 1

    stages = {row["stage"]: row["count"] for row in analytics.funnel(leads, states)}
    assert stages == {"new": 3, "contacted": 2, "proposal": 1, "won": 1, "lost": 0}

    histogram = analytics.score_histogram(states.values())
    assert histogram[9]["count"] == 1 and histogram[4]["count"] == 1


def test_run_series_orders_finished_runs():
    now = datetime.now(UTC)
    runs = [Run(id=str(i), profile_name="p", mode_requested="auto", trigger="manual", triggered_by="x",
                status="succeeded", created_at=now - timedelta(hours=i), finished_at=now) for i in range(3)]
    assert [r["id"] for r in analytics.run_series(runs)] == ["2", "1", "0"]
