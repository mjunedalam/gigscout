"""Runs the team and guarantees a usable result even when a small local model drops the ball."""

import logging
from collections.abc import Callable

from langgraph.errors import GraphRecursionError

from gigscout.activity import Activity
from gigscout.agent.nodes import NO_LEADS, REPORT_ROWS, ScoutDeps, render_table, report_header, with_inbound
from gigscout.models import AgencyProfile, ScoutResult
from gigscout.multiagent import prompts
from gigscout.multiagent.context import RunContext
from gigscout.multiagent.team import TeamModels, build_team, message_text
from gigscout.scoring import heuristic_score, is_excluded

log = logging.getLogger(__name__)


def run_team(
    deps: ScoutDeps,
    profile: AgencyProfile,
    models: TeamModels,
    on_step: Callable[[str], None] | None = None,
    activity: Activity | None = None,
) -> ScoutResult:
    ctx = RunContext(deps=deps, profile=profile, on_step=on_step, activity=activity or Activity())
    ctx.activity.stage("plan")
    ctx.activity.act("head", "read the agency profile")
    supervisor = build_team(ctx, models)
    try:
        result = supervisor.invoke(
            {"messages": [{"role": "user", "content": _kickoff(ctx)}]},
            config={"recursion_limit": deps.settings.team_recursion_limit},
        )
        ctx.log(f"supervisor: {message_text(result['messages'][-1])[:300]}")
    except GraphRecursionError:
        ctx.errors.append("supervisor hit its step limit and was stopped")
    except Exception as exc:
        log.warning("Team run failed: %s", exc)
        ctx.errors.append(f"supervisor failed: {exc}")

    _ensure_shortlist(ctx)
    _ensure_report(ctx)
    ranked = ctx.ranked_shortlist()
    for scored in ranked:  # fallback shortlists never went through qualify_lead
        ctx.activity.reviewed(scored, qualified=True)
    ctx.activity.pitched(ranked)
    ctx.activity.stage("report")
    ctx.activity.act("head", "briefing ready")
    return ScoutResult(
        queries=tuple(f"{source}:{query}" for source, query in ctx.searches),
        iterations=sum(1 for entry in ctx.trace if entry.startswith("supervisor → ")),
        fetched_count=len(ctx.fetched_ids),
        new_count=ctx.new_count,
        errors=tuple(ctx.errors),
        matches=tuple(ranked),
        report=ctx.report or "",
        mode="team",
        trace=tuple(ctx.trace),
    )


def _kickoff(ctx: RunContext) -> str:
    p = ctx.profile
    return prompts.KICKOFF.format(
        profile=p.as_query(),
        exclude=", ".join(p.exclude) or "nothing",
        min_budget=p.min_budget_usd or "any",
        countries=", ".join(p.target_countries) or "any",
        kinds=", ".join(p.kinds),
        shortlist_size=ctx.deps.settings.shortlist_size,
    )


def _ensure_shortlist(ctx: RunContext) -> None:
    """Fallback: if the qualifier shortlisted nothing, rank stored leads with the heuristic scorer."""
    if ctx.shortlist:
        return
    settings = ctx.deps.settings
    candidates = ctx.deps.index.search(
        ctx.profile.as_query(), k=settings.top_k, max_age_days=settings.max_lead_age_days,
        sources=with_inbound(ctx.profile.sources), kinds=ctx.profile.kinds,
    )
    scored = sorted(
        (heuristic_score(ctx.profile, c) for c in candidates if not is_excluded(ctx.profile, c.lead)),
        key=lambda s: s.score, reverse=True,
    )[: settings.shortlist_size]
    ctx.shortlist = {s.lead.id: s for s in scored}
    if scored:
        ctx.log(f"fallback: heuristic shortlist of {len(scored)} leads")


def _ensure_report(ctx: RunContext) -> None:
    """Fallback: if the writer never submitted, render the shortlist as a table."""
    if ctx.report:
        return
    table = render_table(ctx.ranked_shortlist()[:REPORT_ROWS])
    ctx.report = report_header(ctx.profile) + (table or NO_LEADS)
    ctx.log("fallback: table report")
