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
    assert _safe("  =1+1") == "'  =1+1" and _safe("\t@SUM(A1)").startswith("'")


def test_the_report_csv_never_lets_the_workspace_name_run_as_a_formula(web):
    from tests.conftest import login
    client, platform = web()
    login(client)
    with platform.sessions() as session:
        from gigscout.platform.tables import Workspace
        session.get(Workspace, 1).name = "=cmd|' /C calc'!A0"
        session.commit()
    first_line = client.get("/api/reports/owner.csv").text.splitlines()[0]
    assert first_line.startswith("Report,'=cmd")


def _report(**over) -> dict:
    stages = [
        {"stage": "found", "label": "Found", "count": 100, "previous": 60, "conversion": None, "median_hours": None,
         "waiting": 50, "stale": 0},
        {"stage": "qualified", "label": "Qualified", "count": 20, "previous": 20, "conversion": 0.2,
         "median_hours": 3.0, "waiting": 5, "stale": 0},
        {"stage": "sent", "label": "Sent", "count": 20, "previous": 10, "conversion": 1.0, "median_hours": 40.0,
         "waiting": 8, "stale": 3},
        {"stage": "replied", "label": "Replied", "count": 2, "previous": 4, "conversion": 0.1, "median_hours": 72.0,
         "waiting": 1, "stale": 0},
        {"stage": "won", "label": "Won", "count": 0, "previous": 1, "conversion": 0.0, "median_hours": None,
         "waiting": 0, "stale": 0},
    ]
    base = {"days": 30, "start": "2026-10-07T00:00:00", "end": "2026-11-06T00:00:00", "stages": stages,
            "revenue": {"won": 0, "previous": 5000, "deals": 0, "valued": 0},
            "pitches": {"drafted": 10, "by_agents": 8, "approved": 2, "rejected": 6, "waiting": 2, "replied": 2,
                        "approval_rate": 0.25, "median_review_hours": 30.0},
            "runs": {"total": 9, "succeeded": 8, "failed": 1, "leads_fetched": 900, "new_leads": 100},
            "sources": [{"source": "hn_hiring", "found": 30, "qualified": 6, "sent": 5, "replied": 2, "won": 0,
                         "won_value": 0, "reply_rate": 0.4, "proposal": 0, "drafted": 5, "lost": 0},
                        {"source": "remoteok", "found": 40, "qualified": 0, "sent": 0, "replied": 0, "won": 0,
                         "won_value": 0, "reply_rate": None, "proposal": 0, "drafted": 0, "lost": 0}],
            "people": [{"actor": "ann@x.com", "drafted": 2, "sent": 10, "won": 0}], "replies": {"meeting": 1}}
    return {**base, **over}


def test_the_analyst_finds_what_moved_and_what_needs_attention():
    from gigscout import analyst
    found = analyst.insights(_report())
    texts = " | ".join(i.text for i in found)
    assert "Reply rate 10%, from 40%" in texts  # 2/20 vs 4/10
    assert "3 lead(s) waiting too long at sent" in texts
    assert "Only 25% of pitches were approved" in texts
    assert "hn_hiring brought the most results" in texts and "remoteok found leads but none qualified" in texts
    assert "Sent: 20 vs 10" in texts
    assert all(i.metric for i in found)


def test_the_analyst_answers_from_the_fact_sheet_or_falls_back_to_insights():
    from gigscout import analyst
    sheet = analyst.fact_sheet(_report())
    assert "Replied: 2 (before: 4)" in sheet and "Source remoteok: found 40" in sheet and "meeting 1" in sheet

    class Broken:
        def analyze(self, *_a):
            raise RuntimeError("llm down")

    reply, by = analyst.answer("Why did replies drop?", _report(), Broken())
    assert by == "rules" and "Reply rate" in reply.answer and reply.actions


def test_ask_the_analyst_over_the_api(desk):  # noqa: F811
    client, _ = desk
    scout(client)
    got = client.post("/api/analyst/ask", json={"question": "Why did replies drop?", "days": 30}).json()
    assert got["by"] == "ai" and got["answer"].startswith("AI: Why did replies drop?")
    assert "insights" in client.get("/api/analyst/insights").json()
    assert client.post("/api/analyst/ask", json={"question": "x"}).status_code == 422
