"""Multi-agent team: real create_agent ReAct loops driven by scripted models (no Ollama needed)."""

import itertools
from dataclasses import replace

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from gigscout.multiagent.context import RunContext
from gigscout.multiagent.runner import run_team
from gigscout.multiagent.team import TeamModels
from gigscout.multiagent.tools import build_analyst_tools, build_scout_tools, build_writer_tools
from gigscout.service import ScoutService
from tests.conftest import FakeSource, make_deps

_ids = itertools.count()


class ScriptedModel(GenericFakeChatModel):
    """Replays a fixed list of AI turns; tool binding is a no-op."""

    def bind_tools(self, tools, **kwargs):
        return self


def call(name: str, **args) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"call_{next(_ids)}"}])


def say(text: str) -> AIMessage:
    return AIMessage(content=text)


def scripted(*turns: AIMessage) -> ScriptedModel:
    return ScriptedModel(messages=iter(turns))


def happy_team() -> TeamModels:
    return TeamModels(
        supervisor=scripted(
            call("delegate_to_scout", task="Search for django work"),
            call("delegate_to_analyst", task="Shortlist the best"),
            call("check_progress"),
            call("delegate_to_writer", task="Write the briefing"),
            say("DONE: briefing ready."),
        ),
        scout=scripted(
            call("list_sources"),
            call("search_source", source="fake", query="Django API"),
            say("Stored 3 leads."),
        ),
        analyst=scripted(
            call("find_leads", query="python django api", k=5),
            call("read_lead", lead_id="fake:1"),
            call("qualify_lead", lead_id="fake:1", fit_score=0.95, reason="Exact stack", pitch="We built 3 of these"),
            call("qualify_lead", lead_id="fake:3", fit_score=0.4, reason="Python only", red_flags="vague"),
            say("Shortlisted 2."),
        ),
        writer=scripted(
            call("view_shortlist"),
            call("submit_report", markdown="# Leads\n1. Build Django REST API"),
            say("Report submitted."),
        ),
    )


@pytest.fixture
def ctx(settings, index, profile, sample_leads) -> RunContext:
    return RunContext(deps=make_deps(settings, index, [FakeSource("fake", sample_leads)]), profile=profile)


def tools_by_name(tools) -> dict:
    return {t.name: t for t in tools}


def test_team_runs_scout_analyst_writer_through_react_loops(settings, index, profile, sample_leads):
    deps = make_deps(settings, index, [FakeSource("fake", sample_leads)])

    result = run_team(deps, profile, happy_team())

    assert result.mode == "team"
    assert result.queries == ("fake:django api",)
    assert result.fetched_count == 3 and result.new_count == 3
    assert [m.lead.id for m in result.matches] == ["fake:1", "fake:3"]
    assert result.matches[0].reasons == "Exact stack"
    assert result.matches[0].pitch == "We built 3 of these"
    assert result.matches[1].red_flags == "vague"
    assert result.report.startswith("# Leads")
    assert result.iterations == 3
    roles = [step.split(":")[0] for step in result.trace]
    assert roles[:3] == ["supervisor → scout", "scout → supervisor", "supervisor → analyst"]
    assert not result.errors


def test_lazy_supervisor_still_yields_heuristic_shortlist_and_report(settings, index, profile, sample_leads):
    index.add_new(sample_leads)
    lazy = scripted(say("DONE"))

    result = run_team(make_deps(settings, index, []), profile, TeamModels(lazy, lazy, lazy, lazy))

    assert result.matches[0].lead.id == "fake:1"
    assert "fake:2" not in [m.lead.id for m in result.matches]  # exclusions still apply
    assert "| 1 |" in result.report
    assert "fallback: heuristic shortlist of 2 leads" in result.trace


def test_runaway_supervisor_is_stopped_by_recursion_limit(settings, index, profile):
    looping = ScriptedModel(messages=(call("check_progress") for _ in range(1000)))
    tight = settings.model_copy(update={"team_recursion_limit": 6})

    result = run_team(make_deps(tight, index, []), profile, TeamModels.uniform(looping))

    assert "supervisor hit its step limit and was stopped" in result.errors
    assert "No matching client leads" in result.report


def test_worker_failure_is_reported_back_to_supervisor(settings, index, profile):
    broken = scripted()  # raises when asked for a turn
    supervisor = scripted(call("delegate_to_scout", task="go"), say("DONE"))

    result = run_team(make_deps(settings, index, []), profile, TeamModels(supervisor, broken, broken, broken))

    assert any(e.startswith("scout failed") for e in result.errors)
    assert any("scout failed" in step for step in result.trace)


def test_scout_tools_enforce_budget_dedupe_and_unknown_boards(ctx):
    t = tools_by_name(build_scout_tools(ctx))
    ctx.deps = replace(ctx.deps, settings=ctx.deps.settings.model_copy(update={"team_max_searches": 1}))

    assert "fake" in t["list_sources"].invoke({})
    assert "ERROR: unknown source" in t["search_source"].invoke({"source": "nope", "query": "x"})
    assert "3 results (3 new)" in t["search_source"].invoke({"source": "fake", "query": "python"})
    assert "Already searched" in t["search_source"].invoke({"source": "fake", "query": "Python"})
    assert "budget exhausted" in t["search_source"].invoke({"source": "fake", "query": "django"})
    assert "budget left: 0" in t["search_progress"].invoke({})


def test_scout_tool_reports_board_failure_as_observation(settings, index, profile):
    ctx = RunContext(deps=make_deps(settings, index, [FakeSource("bad", [], fail=True)]), profile=profile)
    observation = tools_by_name(build_scout_tools(ctx))["search_source"].invoke({"source": "bad", "query": "x"})
    assert observation.startswith("ERROR: bad failed")
    assert ctx.errors == ["bad: source is down"]


def test_analyst_and_writer_tools(ctx, sample_leads):
    ctx.deps.index.add_new(sample_leads)
    analyst = tools_by_name(build_analyst_tools(ctx))
    writer = tools_by_name(build_writer_tools(ctx))

    listing = analyst["find_leads"].invoke({"query": "django api", "k": 5})
    assert "fake:1" in listing and "fake:2" not in listing  # wordpress excluded
    assert "Build Django REST API" in analyst["read_lead"].invoke({"lead_id": "fake:1"})
    assert "ERROR" in analyst["read_lead"].invoke({"lead_id": "nope"})
    assert "ERROR" in analyst["qualify_lead"].invoke({"lead_id": "nope", "fit_score": 1, "reason": "r"})
    assert writer["view_shortlist"].invoke({}) == "Shortlist is empty."

    analyst["qualify_lead"].invoke({"lead_id": "fake:3", "fit_score": 7, "reason": "unseen but stored"})
    assert ctx.shortlist["fake:3"].similarity == 0.0  # never surfaced by find_candidates
    assert "unseen but stored" in writer["view_shortlist"].invoke({})

    assert "ERROR" in writer["submit_report"].invoke({"markdown": "  "})
    assert writer["submit_report"].invoke({"markdown": "# R"}) == "Report saved." and ctx.report == "# R"


def test_shortlist_respects_size_limit(ctx, sample_leads):
    ctx.deps.index.add_new(sample_leads)
    ctx.deps = replace(ctx.deps, settings=ctx.deps.settings.model_copy(update={"shortlist_size": 1}))
    shortlist = tools_by_name(build_analyst_tools(ctx))["qualify_lead"]

    shortlist.invoke({"lead_id": "fake:1", "fit_score": 0.9, "reason": "a"})
    assert "full" in shortlist.invoke({"lead_id": "fake:3", "fit_score": 0.9, "reason": "b"})


def test_service_mode_resolution(settings, index, sample_leads):
    plain = ScoutService(make_deps(settings, index, []))
    assert plain.resolve_mode("auto") == "pipeline"
    assert plain.resolve_mode("team") == "pipeline"  # no LLM: graceful fallback

    team = ScoutService(make_deps(settings, index, []), team_models=happy_team())
    assert team.resolve_mode("auto") == "team"
    assert team.resolve_mode("pipeline") == "pipeline"


def test_service_runs_team_mode(settings, index, profile, sample_leads):
    service = ScoutService(make_deps(settings, index, [FakeSource("fake", sample_leads)]), team_models=happy_team())
    result = service.scout(profile)
    assert result.mode == "team" and result.matches
