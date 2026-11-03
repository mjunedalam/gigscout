"""The multi-agent team: a supervisor ReAct agent whose tools are three specialist ReAct agents.

    Head of Sales (supervisor, ReAct)
        ──tool call──► delegate_to_scout   ──► Prospector (ReAct)     ─► lead-source tools
        ──tool call──► delegate_to_analyst ──► Qualifier (ReAct)      ─► memory/scoring tools
        ──tool call──► delegate_to_writer  ──► Outreach Writer (ReAct) ─► briefing tools
        ──tool call──► check_progress      (reads the shared blackboard)

Internal role names (scout / analyst / writer) stay short because they appear in tool names and traces.

This is LangChain's "subagents as tools" pattern: each specialist keeps its own short context window,
and the supervisor only sees their summaries.
"""

from dataclasses import dataclass

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool, tool
from langgraph.errors import GraphRecursionError

from gigscout.multiagent import prompts
from gigscout.multiagent.context import RunContext
from gigscout.multiagent.tools import build_analyst_tools, build_scout_tools, build_writer_tools
from gigscout.scoring import heuristic_score

SUMMARY_CHARS = 1500
ROLE_STAGE = {"scout": "search", "analyst": "qualify", "writer": "write"}


@dataclass(frozen=True)
class TeamModels:
    """One model per role. Production uses the same model everywhere; tests script each role separately."""

    supervisor: BaseChatModel
    scout: BaseChatModel
    analyst: BaseChatModel
    writer: BaseChatModel

    @classmethod
    def uniform(cls, model: BaseChatModel) -> "TeamModels":
        return cls(model, model, model, model)


def build_team(ctx: RunContext, models: TeamModels):
    workers = {
        "scout": create_agent(models.scout, build_scout_tools(ctx), system_prompt=prompts.SCOUT, name="scout"),
        "analyst": create_agent(
            models.analyst, build_analyst_tools(ctx), system_prompt=prompts.ANALYST, name="analyst"
        ),
        "writer": create_agent(models.writer, build_writer_tools(ctx), system_prompt=prompts.WRITER, name="writer"),
    }
    return create_agent(
        models.supervisor,
        _delegation_tools(ctx, workers),
        system_prompt=prompts.SUPERVISOR,
        name="supervisor",
    )


def _delegation_tools(ctx: RunContext, workers: dict) -> list[BaseTool]:
    def delegate(role: str, task: str) -> str:
        ctx.log(f"supervisor → {role}: {task}")
        ctx.activity.act("head", f"briefed {role}")
        ctx.activity.stage(ROLE_STAGE[role])
        if role == "writer":
            ctx.activity.progress("writer", 0, 1, "writing the briefing")
        brief = f"{task}\n\nAgency:\n{ctx.profile.as_query()}\n\nShared state: {ctx.progress()}"
        try:
            result = workers[role].invoke(
                {"messages": [{"role": "user", "content": brief}]},
                config={"recursion_limit": ctx.deps.settings.worker_recursion_limit},
            )
            summary = message_text(result["messages"][-1])[:SUMMARY_CHARS]
        except GraphRecursionError:
            summary = f"{role} hit its step limit and was stopped."
            ctx.errors.append(summary)
        except Exception as exc:
            summary = f"{role} failed: {exc}"
            ctx.errors.append(summary)
        ctx.log(f"{role} → supervisor: {summary}")
        _report_outcome(ctx, role)
        return f"{summary}\n\nShared state now: {ctx.progress()}"

    @tool
    def delegate_to_scout(task: str) -> str:
        """Ask the Prospector to search lead sources. Describe what to look for (services, stack, sources)."""
        return delegate("scout", task)

    @tool
    def delegate_to_analyst(task: str) -> str:
        """Ask the Qualifier to review stored leads and build or extend the shortlist."""
        return delegate("analyst", task)

    @tool
    def delegate_to_writer(task: str) -> str:
        """Ask the Outreach Writer to produce the final briefing and outreach messages from the shortlist."""
        return delegate("writer", task)

    @tool
    def check_progress() -> str:
        """Read the shared state: searches run, leads stored, shortlist size, briefing status."""
        return ctx.progress()

    return [delegate_to_scout, delegate_to_analyst, delegate_to_writer, check_progress]


def _report_outcome(ctx: RunContext, role: str) -> None:
    """Close the loop for the cockpit: leads the analyst looked at but did not shortlist were dropped."""
    if role == "analyst":
        for lead_id, candidate in ctx.seen.items():
            if lead_id not in ctx.shortlist and not ctx.activity.was_reviewed(lead_id):
                ctx.activity.reviewed(heuristic_score(ctx.profile, candidate), qualified=False)
    if role == "writer":
        ctx.activity.pitched(ctx.ranked_shortlist())


def message_text(message: BaseMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    return " ".join(part.get("text", "") for part in content if isinstance(part, dict))
