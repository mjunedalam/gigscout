"""Explainable scores: every score says how it was built."""

from gigscout.models import Budget, Candidate
from gigscout.platform.tables import LeadState
from gigscout.scoring import LLM_WEIGHT, blend_with_llm, heuristic_score
from tests.conftest import FakeReasoner, FakeSource, login, make_lead, wait_for_run


def test_the_rule_score_is_the_sum_of_its_parts(profile):
    lead = make_lead("1", "Django REST API", "python django api", skills=("Django",),
                     budget=Budget(maximum=5000, currency="USD", kind="fixed"))
    scored = heuristic_score(profile, Candidate(lead=lead, similarity=0.8))
    keys = [p.key for p in scored.parts]
    assert keys == ["similarity", "skills", "budget", "opportunity"]
    assert abs(sum(p.points for p in scored.parts) - scored.score) < 0.001
    similarity = scored.parts[0]
    assert similarity.value == 0.8 and similarity.points == round(0.8 * similarity.weight, 4)


def test_quality_penalties_show_up_as_their_own_part(profile):
    lead = make_lead("1", "Django API", "python django api. Pay the registration fee to start")
    from gigscout import quality

    scored = heuristic_score(profile, Candidate(lead=quality.assessed(lead), similarity=0.8))
    penalty = next(p for p in scored.parts if p.key == "quality")
    assert penalty.points < 0 and abs(sum(p.points for p in scored.parts) - scored.score) < 0.001


def test_the_ai_judgement_is_blended_in_and_still_adds_up(profile):
    scored = heuristic_score(profile, Candidate(lead=make_lead("1", "Django API"), similarity=0.5))
    blended = blend_with_llm(scored, 0.9, "fits", "")
    ai = blended.parts[-1]
    assert ai.key == "ai" and ai.value == 0.9 and ai.weight == LLM_WEIGHT
    assert abs(sum(p.points for p in blended.parts) - blended.score) < 0.001


def test_runs_store_the_breakdown_and_the_api_returns_it(web, sample_leads):
    client, platform = web(sources=[FakeSource("fake", sample_leads)], reasoner=FakeReasoner())
    login(client)
    profile_id = client.get("/api/profiles").json()[0]["id"]
    run = client.post("/api/runs", json={"profile_id": profile_id, "mode": "pipeline"}).json()
    assert wait_for_run(client, run["id"])["status"] == "succeeded"
    with platform.sessions() as session:
        state = next(s for s in session.query(LeadState) if s.score_parts)
    view = client.get(f"/api/leads/{state.lead_id}").json()
    assert {p["key"] for p in view["score_parts"]} >= {"similarity", "skills", "ai"}
    assert abs(sum(p["points"] for p in view["score_parts"]) - state.base_score) < 0.001
