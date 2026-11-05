"""The connected pipeline: each step is recorded once, and the page, drill-downs and owner report add up."""

from datetime import UTC, date, datetime, timedelta

import pytest

from gigscout.platform import pipeline
from gigscout.platform.pipeline import Step
from gigscout.platform.tables import LeadEvent, LeadState, Outreach
from tests.test_pitches import AUTOPILOT, desk, scout  # noqa: F401  (desk is a fixture)

NOW = datetime(2026, 11, 1, 12, tzinfo=UTC)


def at(days_ago: float) -> datetime:
    return NOW - timedelta(days=days_ago)


STEPS = [
    Step("a", "found", at(20)), Step("a", "qualified", at(19)), Step("a", "drafted", at(18), "GigScout agents"),
    Step("a", "sent", at(17), "ann@x.com"), Step("a", "replied", at(10), "ann@x.com"),
    Step("a", "won", at(5), "ann@x.com"),
    Step("b", "found", at(9)), Step("b", "qualified", at(9)), Step("b", "drafted", at(8), "GigScout agents"),
    Step("b", "sent", at(1), "bob@x.com"),
    Step("c", "found", at(40)), Step("c", "qualified", at(39)), Step("c", "lost", at(3), "ann@x.com"),
    Step("d", "found", at(2)),
]


def stage(rows: dict, name: str) -> dict:
    return next(r for r in rows["stages"] if r["stage"] == name)


def test_summary_counts_conversions_waits_and_the_previous_period():
    s = pipeline.summary(STEPS, at(30), NOW)
    assert [stage(s, n)["count"] for n in ("found", "qualified", "drafted", "sent", "replied", "won", "lost")] == \
        [3, 2, 2, 2, 1, 1, 1]
    assert stage(s, "qualified")["conversion"] == round(2 / 3, 3)
    assert stage(s, "found")["conversion"] is None
    assert stage(s, "sent")["median_hours"] == (24 + 7 * 24) / 2  # a waited 1 day, b waited 7
    assert stage(s, "found")["previous"] == 1  # c was found 40 days ago
    assert stage(s, "lost")["count"] == 1


def test_waiting_shows_where_open_leads_sit_now_and_which_ones_are_stale():
    s = pipeline.summary(STEPS, at(30), NOW)
    assert stage(s, "sent")["waiting"] == 1  # b; a is won, c is lost
    assert stage(s, "found")["waiting"] == 1  # d
    assert stage(s, "won")["waiting"] == 0
    assert stage(s, "sent")["stale"] == 0  # b was sent a day ago
    late = pipeline.summary(STEPS, at(30), NOW + timedelta(days=10))
    assert stage(late, "sent")["stale"] == 1


def test_series_buckets_per_day_and_per_week_for_long_ranges():
    days = pipeline.series(STEPS, date(2026, 10, 3), 30)
    assert len(days) == 30 and sum(r["found"] for r in days) == 3
    weeks = pipeline.series(STEPS, date(2026, 8, 4), 90)
    assert len(weeks) == 13 and sum(r["found"] for r in weeks) == 4


def test_sources_rank_by_value_won_and_people_by_steps_moved():
    sources = pipeline.by_source(STEPS, {"a": "upwork", "b": "hn", "c": "hn", "d": "hn"}, {"a": 12000.0},
                                 at(30), NOW)
    assert sources[0]["source"] == "upwork" and sources[0]["won_value"] == 12000.0
    assert sources[0]["reply_rate"] == 1.0
    people = pipeline.by_person(STEPS, at(30), NOW)
    assert people[0]["actor"] == "ann@x.com" and people[0]["won"] == 1 and people[0]["lost"] == 1
    assert all(p["actor"] for p in people)


def test_mark_keeps_only_the_first_time(web):
    _, platform = web()
    with platform.sessions() as session:
        assert pipeline.mark(session, 1, "x:1", "sent", "ann", at(3))
        assert not pipeline.mark(session, 1, "x:1", "sent", "bob")  # still pending in this session
        session.commit()
        assert not pipeline.mark(session, 1, "x:1", "sent", "bob")
        assert session.query(LeadEvent).count() == 1
        with pytest.raises(ValueError):
            pipeline.mark(session, 1, "x:1", "teleported")


def test_backfill_builds_history_from_earlier_data_once(web):
    _, platform = web()
    with platform.sessions() as session:
        session.query(LeadEvent).delete()
        session.add(Outreach(workspace_id=1, lead_id="x:1", channel="email", status="replied", created_by="ann",
                             sent_at=at(2), sent_by="ann"))
        session.add(LeadState(workspace_id=1, lead_id="x:2", status="won", score=0.9))
        session.commit()
        assert pipeline.backfill(session, 0.6) == 5  # drafted, sent, replied; qualified, won
        assert pipeline.backfill(session, 0.6) == 0


def test_the_whole_line_from_run_to_won_shows_on_the_pipeline_and_report(desk):  # noqa: F811
    client, _ = desk
    client.put("/api/pitches/settings", json=AUTOPILOT)
    scout(client)
    item = client.get("/api/pitches", params={"status": "pending"}).json()["items"][0]
    lead_id = item["outreach"]["lead_id"]
    approved = {"channel": "bid", "to": None, "subject": "", "body": "Hello"}
    assert client.post(f"/api/outreach/{item['outreach']['id']}/send", json=approved).status_code == 200
    assert client.post(f"/api/outreach/{item['outreach']['id']}/status", json={"status": "replied"}).status_code == 200
    assert client.patch(f"/api/leads/{lead_id}", json={"status": "won", "deal_value_usd": 8000}).status_code == 200

    page = client.get("/api/pipeline", params={"days": 7}).json()
    counts = {s["stage"]: s["count"] for s in page["stages"]}
    assert counts["found"] >= counts["qualified"] >= counts["drafted"] >= 1
    assert counts["sent"] == counts["replied"] == counts["won"] == 1
    assert len(page["series"]) == 7 and sum(r["won"] for r in page["series"]) == 1

    won = client.get("/api/pipeline/won/leads", params={"days": 7}).json()["items"]
    assert [w["id"] for w in won] == [lead_id] and won[0]["deal_value_usd"] == 8000
    assert client.get("/api/pipeline/nope/leads").status_code == 404

    report = client.get("/api/reports/owner", params={"days": 7}).json()
    assert report["revenue"]["won"] == 8000 and report["revenue"]["deals"] == 1
    assert report["pitches"]["by_agents"] >= 1 and report["pitches"]["approved"] == 1
    assert report["runs"]["succeeded"] == 1 and report["people"][0]["total"] >= 3
    assert report["sources"][0]["won_value"] == 8000

    csv = client.get("/api/reports/owner.csv", params={"days": 7})
    assert csv.status_code == 200 and csv.headers["content-type"].startswith("text/csv")
    assert "Won lead" in csv.text and "8000" in csv.text


def test_csv_cells_cannot_run_as_formulas():
    from gigscout.web.routes_reports import _safe
    assert _safe("=HYPERLINK(1)") == "'=HYPERLINK(1)" and _safe("upwork") == "upwork"
