import pytest

from gigscout.models import AgencyProfile, Budget, Candidate, Client
from gigscout.scoring import (
    blend_with_llm,
    budget_fit,
    heuristic_score,
    is_excluded,
    opportunity_fit,
    skill_overlap,
)
from gigscout.text import contains_term, html_to_text, matches_any_query
from tests.conftest import make_lead


def test_html_to_text_strips_tags_and_whitespace():
    assert html_to_text("<p>Hello <b>world</b>\n\n</p>") == "Hello world"
    assert html_to_text(None) == ""


@pytest.mark.parametrize(("text", "term", "expected"), [
    ("Need C++ dev", "c++", True),
    ("node.js backend", "node.js", True),
    ("javascript only", "java", False),
    ("Python", "python", True),
])
def test_contains_term_is_whole_word(text, term, expected):
    assert contains_term(text, term) is expected


def test_matches_any_query_requires_all_words_of_one_query():
    assert matches_any_query("django rest api", ["react", "django api"])
    assert not matches_any_query("django only", ["django api"])
    assert not matches_any_query("anything", [])


def test_skill_overlap_and_budget(profile):
    lead = make_lead("1", "Django API", "python work", budget=Budget(maximum=100, currency="USD"))
    assert skill_overlap(profile, lead) == 1.0
    assert budget_fit(profile, lead) == 0.5
    assert budget_fit(profile, make_lead("2", "x")) == 0.5
    assert budget_fit(AgencyProfile(skills=("x",)), lead) == 1.0


def test_budget_unknown_when_currency_has_no_rate(profile):
    lead = make_lead("1", "x", budget=Budget(maximum=1000, currency="INR"))
    assert budget_fit(profile, lead) == 0.5


@pytest.mark.parametrize(("lead_kw", "expected"), [
    ({"kind": "inbound"}, 1.0),
    ({}, 0.5),  # unknown competition
    ({"bid_count": 0}, 1.0),
    ({"bid_count": 20}, 0.5),
    ({"bid_count": 60}, 0.25),
])
def test_opportunity_fit_prefers_inbound_and_low_competition(profile, lead_kw, expected):
    assert opportunity_fit(profile, make_lead("1", "x", **lead_kw)) == pytest.approx(expected)


def test_opportunity_fit_penalises_clients_outside_target_countries():
    profile = AgencyProfile(skills=("python",), target_countries=("United States",))
    in_market = make_lead("1", "x", bid_count=0, client=Client(country="united states"))
    off_market = make_lead("2", "x", bid_count=0, client=Client(country="Narnia"))
    unknown = make_lead("3", "x", bid_count=0)

    assert opportunity_fit(profile, in_market) == 1.0
    assert opportunity_fit(profile, off_market) == 0.5
    assert opportunity_fit(profile, unknown) == 1.0  # never penalise what we cannot see


def test_exclusion(profile):
    assert is_excluded(profile, make_lead("1", "WordPress fix"))
    assert not is_excluded(profile, make_lead("2", "Django fix"))


def test_heuristic_then_llm_blend(profile):
    candidate = Candidate(lead=make_lead("1", "Django API", "python", bid_count=20), similarity=0.8)
    scored = heuristic_score(profile, candidate)
    assert scored.score == pytest.approx(0.45 * 0.8 + 0.30 * 1 + 0.15 * 0.5 + 0.10 * 0.5)
    assert "python" in scored.reasons and "20 competing bids" in scored.reasons

    blended = blend_with_llm(scored, 1.0, "great", "none", "Open with our fintech case study")
    assert blended.score == pytest.approx(0.4 * scored.score + 0.6)
    assert blended.pitch == "Open with our fintech case study"
    assert scored.reasons != blended.reasons  # original untouched


def test_inbound_reason_is_labelled(profile):
    scored = heuristic_score(profile, Candidate(lead=make_lead("1", "Hi", kind="inbound"), similarity=0.1))
    assert "inbound enquiry" in scored.reasons
