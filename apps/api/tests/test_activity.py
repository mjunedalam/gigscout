"""Structured run activity that drives the live cockpit."""

import threading

import pytest

from gigscout.activity import Activity
from gigscout.agent.graph import run_scout
from gigscout.models import AgencyProfile, Budget, ScoredLead
from gigscout.multiagent.runner import run_team
from gigscout.scoring import drop_reason
from tests.conftest import FakeReasoner, FakeSource, make_deps, make_lead
from tests.test_multiagent import happy_team


def scored(lead, score=0.2, red_flags="") -> ScoredLead:
    return ScoredLead(lead=lead, similarity=0.5, score=score, red_flags=red_flags)


def kinds(events, kind):
    return [e for e in events if e["kind"] == kind]


@pytest.mark.parametrize(("lead_kw", "red_flags", "expected"), [
    ({"budget": Budget(maximum=900, currency="USD")}, "unpaid test task", "red flags"),
    ({"budget": Budget(maximum=900, currency="USD")}, "", "budget too low"),
    ({"bid_count": 45}, "", "too many bids"),
    ({"description": "logo design in illustrator"}, "", "off-target"),
    ({"description": "python django work", "bid_count": 2}, "", "low fit"),
])
def test_drop_reason_names_the_main_problem(lead_kw, red_flags, expected):
    profile = AgencyProfile(skills=("python", "django"), min_budget_usd=1500)
    lead = make_lead("1", "Some project", **lead_kw)

    assert drop_reason(profile, scored(lead, red_flags=red_flags)) == expected


def test_activity_emits_stage_changes_once_and_keeps_a_log():
    events = []
    activity = Activity(events.append)

    activity.stage("plan")
    activity.stage("plan")
    activity.stage("search")

    assert [e["stage"] for e in kinds(events, "stage")] == ["plan", "search"]
    assert all(e["t"] >= 0 for e in events)
    assert activity.log == events


def test_reviews_are_emitted_once_unless_a_lead_is_later_qualified(profile):
    events = []
    activity = Activity(events.append, profile=profile)
    lead = make_lead("1", "Build Django REST API", budget=Budget(maximum=500, currency="USD"))

    activity.reviewed(scored(lead), qualified=False)
    activity.reviewed(scored(lead), qualified=False)
    activity.reviewed(scored(lead, score=0.9), qualified=True)

    reviews = kinds(events, "reviewed")
    assert [r["qualified"] for r in reviews] == [False, True]
    assert reviews[0]["reason"] and reviews[1]["reason"] is None
    assert reviews[0]["lead"] == {"id": "fake:1", "title": "Build Django REST API", "source": "fake", "budget": 500.0}


def test_found_lists_each_lead_once_per_search():
    activity = Activity()
    lead = make_lead("1", "Django API")

    activity.found("fake", [lead, lead, make_lead("2", "Other")])

    assert [item["id"] for item in kinds(activity.log, "found")[0]["leads"]] == ["fake:1", "fake:2"]


def test_activity_is_safe_to_call_from_parallel_fetch_threads():
    activity = Activity()
    leads = [make_lead(str(i), f"Lead {i}") for i in range(20)]
    threads = [threading.Thread(target=activity.found, args=(f"s{i}", leads)) for i in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]

    assert len(kinds(activity.log, "found")) == 8


def test_pipeline_run_reports_steps_leads_reviews_and_pitches(settings, index, profile, sample_leads):
    events = []
    deps = make_deps(settings, index, [FakeSource("fake", sample_leads)], reasoner=FakeReasoner())

    run_scout(deps, profile, activity=Activity(events.append, profile=profile, threshold=settings.good_match_threshold))

    assert [e["stage"] for e in kinds(events, "stage")] == ["plan", "search", "qualify", "write", "report"]
    found = kinds(events, "found")
    assert found[0]["source"] == "fake" and len(found[0]["leads"]) == 3
    reviews = kinds(events, "reviewed")
    assert reviews and any(r["qualified"] for r in reviews)
    assert all(r["reason"] for r in reviews if not r["qualified"])
    pitched = kinds(events, "pitched")
    assert 1 <= len(pitched) <= 3
    assert {p["lead"]["id"] for p in pitched} <= {r["lead"]["id"] for r in reviews if r["qualified"]}
    assert {e["agent"] for e in kinds(events, "act")} >= {"head", "prospector", "qualifier", "writer"}


def test_team_run_reports_each_delegation_and_the_shortlist(settings, index, profile, sample_leads):
    events = []
    deps = make_deps(settings, index, [FakeSource("fake", sample_leads)])

    run_team(deps, profile, happy_team(), activity=Activity(events.append, profile=profile))

    stages = [e["stage"] for e in kinds(events, "stage")]
    assert stages == ["plan", "search", "qualify", "write", "report"]
    qualified = {r["lead"]["id"] for r in kinds(events, "reviewed") if r["qualified"]}
    assert qualified == {"fake:1", "fake:3"}
    dropped = [r for r in kinds(events, "reviewed") if not r["qualified"]]
    assert all(r["reason"] for r in dropped)  # leads the analyst looked at but did not shortlist
    assert {p["lead"]["id"] for p in kinds(events, "pitched")} == {"fake:1", "fake:3"}
    assert len(kinds(events, "found")[0]["leads"]) == 3


@pytest.mark.parametrize("mode", ["pipeline", "team"])
def test_a_stop_signal_escapes_both_run_modes(settings, index, profile, sample_leads, mode):
    from gigscout.platform.runs import RunStopped

    def stop_after_first_search(event):
        if event["kind"] == "found":
            raise RunStopped

    deps = make_deps(settings, index, [FakeSource("fake", sample_leads)])
    activity = Activity(stop_after_first_search, profile=profile)

    with pytest.raises(RunStopped):
        if mode == "team":
            run_team(deps, profile, happy_team(), activity=activity)
        else:
            run_scout(deps, profile, activity=activity)


def test_progress_reports_done_out_of_total_for_the_current_step():
    events = []
    activity = Activity(events.append)
    activity.stage("search")

    activity.progress("prospector", 2, 4, "searched remoteok")

    assert kinds(events, "progress") == [{
        "kind": "progress", "t": events[-1]["t"], "agent": "prospector", "stage": "search", "done": 2, "total": 4,
        "label": "searched remoteok",
    }]


def test_pipeline_reports_progress_for_every_agent_while_it_works(settings, index, profile, sample_leads):
    events = []
    sources = [FakeSource("a", sample_leads), FakeSource("b", sample_leads)]
    deps = make_deps(settings, index, sources, reasoner=FakeReasoner())

    run_scout(deps, profile, activity=Activity(events.append, profile=profile))

    progress = kinds(events, "progress")
    search = [p for p in progress if p["agent"] == "prospector"]
    assert [p["done"] for p in search][-1] == 2 and all(p["total"] == 2 for p in search)
    qualify = [p for p in progress if p["agent"] == "qualifier"]
    assert qualify and qualify[-1]["done"] == qualify[-1]["total"]
    assert {p["agent"] for p in progress} == {"head", "prospector", "qualifier", "writer"}
    assert all(0 <= p["done"] <= p["total"] for p in progress)


def test_team_reports_search_budget_and_shortlist_progress(settings, index, profile, sample_leads):
    events = []
    deps = make_deps(settings, index, [FakeSource("fake", sample_leads)])

    run_team(deps, profile, happy_team(), activity=Activity(events.append, profile=profile))

    progress = kinds(events, "progress")
    assert any(p["agent"] == "prospector" and p["total"] == settings.team_max_searches for p in progress)
    shortlist = [p for p in progress if p["agent"] == "qualifier"]
    assert shortlist[-1]["done"] == 2 and shortlist[-1]["total"] == settings.shortlist_size
