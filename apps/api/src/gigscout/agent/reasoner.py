"""The LLM-powered "judgement" the agent calls into. A Protocol so tests and offline runs can swap it."""

import logging
from collections.abc import Iterator, Sequence
from typing import Protocol

import httpx
from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field

from gigscout.agent import prompts
from gigscout.config import Settings
from gigscout.models import AgencyProfile, Lead, LeadAssessment, OutreachText, ProfileSuggestion
from gigscout.replies import ReplyRead
from gigscout.store.knowledge import format_evidence

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

    def suggest_profile(self, company_type: str, description: str) -> ProfileSuggestion: ...

    def answer_stream(self, question: str, context: str) -> Iterator[str]: ...

    def draft_outreach(self, profile: AgencyProfile, lead: Lead, pitch: str, channel: str,
                       evidence: str = "") -> OutreachText: ...


class OllamaReasoner:
    def __init__(self, llm: BaseChatModel) -> None:
        self._llm = llm

    def plan_queries(self, profile: AgencyProfile, previous: Sequence[str]) -> list[str]:
        extra = prompts.BROADEN_HINT.format(previous=", ".join(previous)) if previous else ""
        prompt = prompts.PLAN_QUERIES.format(
            company=profile.who(), profile=profile.as_query(), extra=extra, max_queries=MAX_QUERIES,
        )
        plan = self._llm.with_structured_output(QueryPlan).invoke(prompt)
        return [q.strip().lower() for q in plan.queries if q.strip()][:MAX_QUERIES]

    def qualify(self, profile: AgencyProfile, lead: Lead) -> LeadAssessment:
        prompt = prompts.QUALIFY_LEAD.format(
            company=profile.who(),
            profile=profile.as_query(),
            kind=lead.kind,
            source=lead.source,
            title=lead.title,
            client=describe_client(lead),
            skills=", ".join(lead.skills) or "n/a",
            budget=describe_budget(lead),
            bids=lead.bid_count if lead.bid_count is not None else "unknown",
            description=_with_checks(lead),
        )
        return self._llm.with_structured_output(LeadAssessment).invoke(prompt)

    def summarize(self, profile: AgencyProfile, leads: str) -> str:
        prompt = prompts.SUMMARIZE.format(company=profile.who(), profile=profile.as_query(), leads=leads)
        return str(self._llm.invoke(prompt).content)

    def suggest_profile(self, company_type: str, description: str) -> ProfileSuggestion:
        prompt = prompts.SUGGEST_PROFILE.format(company_type=company_type, description=description)
        return self._llm.with_structured_output(ProfileSuggestion).invoke(prompt)

    def answer(self, question: str, context: str) -> str:
        return str(self._llm.invoke(prompts.ANSWER_WITH_CONTEXT.format(context=context, question=question)).content)

    def answer_stream(self, question: str, context: str) -> Iterator[str]:
        for chunk in self._llm.stream(prompts.ANSWER_WITH_CONTEXT.format(context=context, question=question)):
            if isinstance(chunk.content, str) and chunk.content:
                yield chunk.content


    def draft_outreach(self, profile: AgencyProfile, lead: Lead, pitch: str, channel: str,
                       evidence: str = "") -> OutreachText:
        prompt = prompts.DRAFT_OUTREACH.format(evidence=evidence or format_evidence(()),
            company=profile.who(), profile=profile.as_query(), name=profile.name, kind=lead.kind, source=lead.source,
            title=lead.title, client=describe_client(lead), budget=describe_budget(lead),
            description=lead.description[:DESCRIPTION_CHARS_FOR_GRADING], pitch=pitch or "none",
            channel="an email" if channel == "email" else "a proposal pasted into the marketplace's bid form",
            subject_rule="required" if channel == "email" else "leave it empty",
        )
        return self._llm.with_structured_output(OutreachText).invoke(prompt)


    def read_reply(self, profile: AgencyProfile, lead: Lead, original: str, reply: str) -> ReplyRead:
        prompt = prompts.READ_REPLY.format(company=profile.who(), title=lead.title, original=original[:2000],
                                           reply=reply[:4000])
        return self._llm.with_structured_output(ReplyRead).invoke(prompt)

    def draft_answer(self, profile: AgencyProfile, lead: Lead, original: str, reply: str, intent: str,
                     evidence: str) -> OutreachText:
        prompt = prompts.DRAFT_ANSWER.format(company=profile.who(), name=profile.name, profile=profile.as_query(),
                                             title=lead.title, original=original[:2000], reply=reply[:4000],
                                             intent=intent.replace("_", " "), evidence=evidence)
        return self._llm.with_structured_output(OutreachText).invoke(prompt)


def build_chat_model(settings: Settings) -> BaseChatModel | None:
    """Return a tool-calling chat model, or None (heuristic-only mode) if no LLM is configured or reachable."""
    if settings.llm_provider == "none":
        return None
    if settings.llm_provider == "anthropic":
        return _anthropic(settings)
    try:
        httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=3).raise_for_status()
    except httpx.HTTPError as exc:
        log.warning("Ollama not reachable at %s (%s); running without an LLM", settings.ollama_base_url, exc)
        return None
    from langchain_ollama import ChatOllama

    return ChatOllama(model=settings.llm_model, base_url=settings.ollama_base_url, temperature=0, reasoning=False)


def _with_checks(lead: Lead) -> str:
    """The description, after what the automated quality check found (so the model weighs it)."""
    from gigscout.quality import summary

    checks = f"[Automated quality checks flagged: {summary(lead.quality)}]\n" if lead.quality else ""
    return checks + lead.description[:DESCRIPTION_CHARS_FOR_GRADING]


def _anthropic(settings: Settings) -> BaseChatModel | None:
    if settings.anthropic_api_key is None:
        log.warning("GIGSCOUT_LLM_PROVIDER=anthropic needs GIGSCOUT_ANTHROPIC_API_KEY; running without an LLM")
        return None
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(
        model=settings.anthropic_model, api_key=settings.anthropic_api_key.get_secret_value(), temperature=0,
        max_tokens=settings.anthropic_max_tokens, timeout=settings.http_timeout * 4, max_retries=2,
    )


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
