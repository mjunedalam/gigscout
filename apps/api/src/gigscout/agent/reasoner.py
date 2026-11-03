"""The LLM-powered "judgement" the agent calls into. A Protocol so tests and offline runs can swap it."""

import logging
from collections.abc import Sequence
from typing import Protocol

import httpx
from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field

from gigscout.agent import prompts
from gigscout.config import Settings
from gigscout.models import AgencyProfile, Lead, LeadAssessment

log = logging.getLogger(__name__)

MAX_QUERIES = 6
DESCRIPTION_CHARS_FOR_GRADING = 2500


class QueryPlan(BaseModel):
    queries: list[str] = Field(description="Short keyword search queries")


class Reasoner(Protocol):
    def plan_queries(self, profile: AgencyProfile, previous: Sequence[str]) -> list[str]: ...

    def qualify(self, profile: AgencyProfile, lead: Lead) -> LeadAssessment: ...

    def summarize(self, profile: AgencyProfile, leads: str) -> str: ...

    def answer(self, question: str, context: str) -> str: ...


class OllamaReasoner:
    def __init__(self, llm: BaseChatModel) -> None:
        self._llm = llm

    def plan_queries(self, profile: AgencyProfile, previous: Sequence[str]) -> list[str]:
        extra = prompts.BROADEN_HINT.format(previous=", ".join(previous)) if previous else ""
        prompt = prompts.PLAN_QUERIES.format(profile=profile.as_query(), extra=extra, max_queries=MAX_QUERIES)
        plan = self._llm.with_structured_output(QueryPlan).invoke(prompt)
        return [q.strip().lower() for q in plan.queries if q.strip()][:MAX_QUERIES]

    def qualify(self, profile: AgencyProfile, lead: Lead) -> LeadAssessment:
        prompt = prompts.QUALIFY_LEAD.format(
            profile=profile.as_query(),
            kind=lead.kind,
            source=lead.source,
            title=lead.title,
            client=describe_client(lead),
            skills=", ".join(lead.skills) or "n/a",
            budget=describe_budget(lead),
            bids=lead.bid_count if lead.bid_count is not None else "unknown",
            description=lead.description[:DESCRIPTION_CHARS_FOR_GRADING],
        )
        return self._llm.with_structured_output(LeadAssessment).invoke(prompt)

    def summarize(self, profile: AgencyProfile, leads: str) -> str:
        return str(self._llm.invoke(prompts.SUMMARIZE.format(profile=profile.as_query(), leads=leads)).content)

    def answer(self, question: str, context: str) -> str:
        return str(self._llm.invoke(prompts.ANSWER_WITH_CONTEXT.format(context=context, question=question)).content)


def build_chat_model(settings: Settings) -> BaseChatModel | None:
    """Return a tool-calling chat model, or None (heuristic-only mode) if no LLM is configured or reachable."""
    if settings.llm_provider == "none":
        return None
    try:
        httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=3).raise_for_status()
    except httpx.HTTPError as exc:
        log.warning("Ollama not reachable at %s (%s); running without an LLM", settings.ollama_base_url, exc)
        return None
    from langchain_ollama import ChatOllama

    return ChatOllama(model=settings.llm_model, base_url=settings.ollama_base_url, temperature=0, reasoning=False)


def describe_budget(lead: Lead) -> str:
    budget = lead.budget
    if budget is None or (budget.minimum is None and budget.maximum is None):
        return "not stated"
    return f"{budget.minimum}-{budget.maximum} {budget.currency or ''} ({budget.kind})"


def describe_client(lead: Lead) -> str:
    """Company and country only: contact details (email, phone) never go into prompts."""
    client = lead.client
    if client is None:
        return "unknown"
    return ", ".join(part for part in (client.name, client.country) if part) or "unknown"
