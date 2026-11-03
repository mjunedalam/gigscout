from gigscout.agent.graph import run_scout
from gigscout.models import AgencyProfile
from tests.conftest import FakeReasoner, FakeSource, make_deps


def test_heuristic_run_ranks_relevant_leads_and_excludes_unwanted(settings, index, profile, sample_leads):
    source = FakeSource("fake", sample_leads)

    result = run_scout(make_deps(settings, index, [source]), profile)

    ids = [m.lead.id for m in result.matches]
    assert ids[0] == "fake:1"
    assert "fake:2" not in ids  # wordpress excluded
    assert result.fetched_count == 3
    assert result.new_count == 3
    assert result.iterations == 1
    assert source.calls == [["django api"]]
    assert "Build Django REST API" in result.report


def test_broadens_queries_when_too_few_good_matches(settings, index, profile):
    strict = settings.model_copy(update={"min_good_matches": 10})
    source = FakeSource("fake", [])

    result = run_scout(make_deps(strict, index, [source]), profile)

    assert result.iterations == 2
    assert source.calls == [["django api"], ["python", "django"]]  # only new queries re-sent
    assert "No matching client leads" in result.report


def test_failing_source_is_recorded_not_fatal(settings, index, profile, sample_leads):
    deps = make_deps(settings, index, [FakeSource("good", sample_leads), FakeSource("bad", [], fail=True)])

    result = run_scout(deps, profile)

    assert result.matches
    assert any("bad: source is down" in e for e in result.errors)


def test_profile_can_restrict_sources(settings, index, sample_leads):
    a, b = FakeSource("a", sample_leads), FakeSource("b", sample_leads)
    profile = AgencyProfile(skills=("python",), sources=("a",))

    run_scout(make_deps(settings, index, [a, b]), profile)

    assert a.calls and not b.calls


def test_llm_plans_grades_and_summarizes(settings, index, profile, sample_leads):
    reasoner = FakeReasoner(score=1.0)

    result = run_scout(make_deps(settings, index, [FakeSource("fake", sample_leads)], reasoner), profile)

    assert result.queries == ("django api", "llm query")
    assert reasoner.graded
    assert result.matches[0].reasons == "LLM says good fit"
    assert result.matches[0].pitch == "We shipped this before."
    assert "💬 We shipped this before." in result.report
    assert "Briefing: great leads today." in result.report


def test_llm_grade_failure_falls_back_to_heuristics(settings, index, profile, sample_leads):
    reasoner = FakeReasoner(fail_grade=True)

    result = run_scout(make_deps(settings, index, [FakeSource("fake", sample_leads)], reasoner), profile)

    assert result.matches[0].reasons.startswith("Matches")
    assert any("llm timeout" in e for e in result.errors)
