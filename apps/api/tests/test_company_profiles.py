"""Any type of company can describe itself, and the agents prospect for that company, not a software studio."""

import pytest
from pydantic import ValidationError

from gigscout.agent import prompts as agent_prompts
from gigscout.models import AgencyProfile, Candidate
from gigscout.multiagent import prompts as team_prompts
from gigscout.profile_templates import TEMPLATES, closest_template
from gigscout.scoring import drop_reason, heuristic_score, skill_overlap
from tests.conftest import FakeReasoner, login, make_lead

MARKETING = AgencyProfile(
    name="Bright Lane", company_type="Marketing agency", pitch="Performance marketing for DTC brands",
    services=("seo", "google ads management"), keywords=("ppc", "paid social"),
)


def test_a_profile_needs_no_tech_stack_but_must_say_what_it_sells():
    assert MARKETING.skills == () and MARKETING.company_type == "Marketing agency"
    with pytest.raises(ValidationError, match="what you sell"):
        AgencyProfile(name="Empty Co", company_type="Law firm")


def test_existing_software_profiles_keep_working():
    profile = AgencyProfile(name="Acme", skills=("python",))
    assert profile.company_type == "Software agency"


def test_the_query_and_prompts_describe_the_company_itself():
    query = MARKETING.as_query()
    assert "Company type: Marketing agency" in query and "Tech stack" not in query
    assert MARKETING.who() == 'Marketing agency "Bright Lane"'
    for template in (agent_prompts.PLAN_QUERIES, agent_prompts.QUALIFY_LEAD, agent_prompts.SUMMARIZE,
                     team_prompts.SCOUT, team_prompts.ANALYST, team_prompts.WRITER, team_prompts.SUPERVISOR,
                     team_prompts.KICKOFF):
        assert "software" not in template.lower()
        assert "{company}" in template


def test_fit_uses_services_and_keywords_when_there_are_no_capabilities():
    seo_lead = make_lead("1", "Need an SEO expert", "Looking for seo and ppc help for our store")
    assert skill_overlap(MARKETING, seo_lead) > 0
    assert heuristic_score(MARKETING, Candidate(lead=seo_lead, similarity=0.5)).score > 0.3


def test_drop_reason_is_industry_neutral():
    off = make_lead("2", "Kitchen renovation quote", "tiles and plumbing")
    assert drop_reason(MARKETING, heuristic_score(MARKETING, Candidate(lead=off, similarity=0.1))) == "off-target"


def test_templates_cover_common_company_types_and_are_valid_profiles():
    types = {t.company_type for t in TEMPLATES}
    assert {"Software agency", "Marketing agency", "Recruitment agency", "Law firm", "Construction contractor"} <= types
    for t in TEMPLATES:
        AgencyProfile(name="x", company_type=t.company_type, services=t.services, skills=t.skills, keywords=t.keywords)
    assert closest_template("digital marketing").company_type == "Marketing agency"
    assert closest_template("bakery") is None


def test_templates_and_ai_suggestions_are_served_to_admins(web):
    client, platform = web(reasoner=FakeReasoner())
    login(client)

    templates = client.get("/api/profiles/templates").json()
    assert any(t["company_type"] == "Law firm" and t["services"] for t in templates)

    body = {"company_type": "Bakery", "description": "Wedding cakes"}
    suggestion = client.post("/api/profiles/suggest", json=body).json()
    assert suggestion["source"] == "ai" and suggestion["keywords"]


def test_suggestions_fall_back_to_the_closest_template_without_an_llm(web):
    client, _ = web()
    login(client)

    body = {"company_type": "marketing", "description": "We run ads"}
    fallback = client.post("/api/profiles/suggest", json=body).json()
    assert fallback["source"] == "template" and "seo" in fallback["services"]
    unknown = client.post("/api/profiles/suggest", json={"company_type": "Bakery", "description": "Cakes"}).json()
    assert unknown["source"] == "none" and unknown["services"] == []
