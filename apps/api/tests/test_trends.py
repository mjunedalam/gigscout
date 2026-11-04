"""Market trends: skills in demand and how fast that changes, budgets per week, growing sources."""

from datetime import UTC, datetime, timedelta

from gigscout.models import Budget
from gigscout.platform.analytics import trends
from gigscout.store.vector_store import StoredLead
from tests.conftest import login, make_lead

NOW = datetime(2026, 11, 5, 12, tzinfo=UTC)


def stored(pid, skills=(), days_ago=1, source="fake", text="", budget=None):
    lead = make_lead(pid, f"Job {pid}", text or f"job {pid}", source=source, skills=skills,
                     budget=Budget(maximum=budget, currency="USD", kind="fixed") if budget else None)
    return StoredLead(lead=lead, seen_at=NOW - timedelta(days=days_ago))


def test_demand_rising_and_falling_compare_the_last_weeks_with_the_weeks_before():
    leads = (
        [stored(f"r{i}", ("React",), days_ago=3) for i in range(6)]      # react: 6 recent, 2 before
        + [stored(f"o{i}", ("React",), days_ago=40) for i in range(2)]
        + [stored(f"p{i}", ("PHP",), days_ago=3) for i in range(1)]      # php: 1 recent, 5 before
        + [stored(f"q{i}", ("PHP",), days_ago=40) for i in range(5)]
        + [stored(f"n{i}", ("Rust",), days_ago=2) for i in range(3)]     # rust: new
        + [stored("old", ("Cobol",), days_ago=200)]                       # outside both windows
    )
    t = trends(leads, now=NOW, weeks=4)
    by_term = {row["term"]: row for row in t["demand"]}
    assert by_term["react"] == {"term": "react", "recent": 6, "previous": 2, "change": 2.0, "yours": False}
    assert [r["term"] for r in t["rising"]] == ["react"] and [r["term"] for r in t["falling"]] == ["php"]
    assert [r["term"] for r in t["new"]] == ["rust"] and "cobol" not in by_term


def test_the_companys_own_skills_count_wherever_leads_mention_them():
    leads = [stored(f"{i}", text="we need a django developer") for i in range(3)]
    [row] = trends(leads, ["Django"], now=NOW)["demand"]
    assert row["term"] == "django" and row["yours"] is True and row["recent"] == 3


def test_budgets_are_weekly_medians_of_project_totals():
    leads = [stored("a", budget=1000, days_ago=1), stored("b", budget=3000, days_ago=1),
             stored("c", budget=9000, days_ago=1)]
    [week] = trends(leads, now=NOW)["budgets"]
    assert week["median_usd"] == 3000 and week["count"] == 3


def test_the_trends_endpoint_uses_the_workspaces_profiles(web):
    client, platform = web()
    platform.index_for(1).add_new([make_lead(str(i), "Python work", "a python django api") for i in range(3)])
    login(client)
    client.post("/api/profiles", json={"name": "Acme", "pitch": "APIs", "skills": ["django"]})
    t = client.get("/api/metrics/trends").json()
    assert any(r["term"] == "django" and r["yours"] and r["recent"] == 3 for r in t["demand"])
    assert t["sources"] == [{"source": "fake", "recent": 3, "previous": 0}]
