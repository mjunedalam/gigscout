"""Graph nodes. Each takes the current state and returns only the keys it changes."""

import logging
import threading
import time
from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel
from langgraph.types import Send

from gigscout.activity import Activity
from gigscout.agent.reasoner import Reasoner
from gigscout.agent.state import FetchTask, ScoutState
from gigscout.config import Settings
from gigscout.inbound.google_ads import SOURCE_NAME as GOOGLE_ADS
from gigscout.models import AgencyProfile, Lead, ScoredLead
from gigscout.scoring import blend_with_llm, heuristic_score, is_excluded
from gigscout.sources.base import Source
from gigscout.store.vector_store import LeadIndex

log = logging.getLogger(__name__)

MAX_BASE_QUERIES = 4
REPORT_ROWS = 15


@dataclass(frozen=True)
class ScoutDeps:
    settings: Settings
    sources: dict[str, Source]
    index: LeadIndex
    reasoner: Reasoner | None
    chat_model: BaseChatModel | None = None  # tool-calling model for the multi-agent team


class ScoutNodes:
    def __init__(self, deps: ScoutDeps, activity: Activity | None = None) -> None:
        self.deps = deps
        self.activity = activity or Activity()
        self._fetch_lock = threading.Lock()
        self._fetch = {"done": 0, "total": 0}  # parallel fetches of the current round, for progress

    def plan_queries(self, state: ScoutState) -> dict:
        """Turn the agency profile into source search queries; on later iterations, broaden them."""
        self.activity.stage("plan")
        self.activity.progress("head", 0, 1, "planning searches")
        profile, previous = state["profile"], state.get("queries", [])
        proposed = [] if previous else _base_queries(profile)
        errors: list[str] = []
        if self.deps.reasoner is not None:
            try:
                proposed += self.deps.reasoner.plan_queries(profile, previous)
            except Exception as exc:  # LLM is optional: degrade, don't die
                log.warning("Query planning failed: %s", exc)
                errors.append(f"plan_queries: {exc}")
        if previous and not self.deps.reasoner:
            proposed += [s.lower() for s in (*profile.services, *profile.skills)]
        pending = [q for q in _dedupe(proposed) if q not in previous]
        self.activity.act("head", f"planned {len(pending)} searches")
        self.activity.progress("head", 1, 1, f"planned {len(pending)} searches")
        return {
            "queries": [*previous, *pending],
            "pending_queries": pending,
            "iteration": state.get("iteration", 0) + 1,
            "errors": errors,
        }

    def route_to_sources(self, state: ScoutState) -> list[Send] | str:
        """Fan out: one parallel fetch branch per enabled source."""
        wanted = state["profile"].sources
        names = [n for n in self.deps.sources if wanted is None or n in wanted]
        pending = state.get("pending_queries", [])
        if not names or not pending:
            return "index"
        with self._fetch_lock:
            self._fetch = {"done": 0, "total": len(names)}
        return [Send("fetch_source", FetchTask(source=n, queries=pending)) for n in names]

    def fetch_source(self, task: FetchTask) -> dict:
        """Call one source. Failures are recorded, never fatal: one broken source must not sink the run."""
        self.activity.stage("search")
        try:
            return self._fetch_one(task)
        finally:
            with self._fetch_lock:
                self._fetch["done"] += 1
                done, total = self._fetch["done"], self._fetch["total"]
            self.activity.progress("prospector", done, total, f"searched {task['source']}")

    def _fetch_one(self, task: FetchTask) -> dict:
        source, started = task["source"], time.monotonic()
        try:
            leads = self.deps.sources[source].fetch(task["queries"], self.deps.settings.per_query_limit)
            log.info("%s returned %d leads", source, len(leads))
            self.activity.hood("prospector", "fetch", f"Prospector searched {source}: {len(leads)} results",
                               _ms(started), source=source, queries=list(task["queries"]), results=len(leads),
                               sample=[lead.title for lead in leads[:5]])
            self.activity.act("prospector", f"searched {task['source']}")
            self.activity.found(task["source"], leads)
            return {"raw_leads": leads}
        except Exception as exc:
            log.warning("Source %s failed: %s", task["source"], exc)
            self.activity.hood("prospector", "fetch", f"Prospector could not search {source}", _ms(started),
                               source=source, queries=list(task["queries"]), error=f"{type(exc).__name__}: {exc}")
            return {"errors": [f"{task['source']}: {exc}"]}

    def index(self, state: ScoutState) -> dict:
        """Embed and store anything new in the vector DB (this is also de-duplication)."""
        raw = state.get("raw_leads", [])
        fresh = self.deps.index.add_new(raw)
        return {"fetched_count": len({lead.id for lead in raw}), "new_count": state.get("new_count", 0) + len(fresh)}

    def retrieve(self, state: ScoutState) -> dict:
        """RAG retrieval: find the stored leads closest in meaning to what the agency sells."""
        self.activity.stage("qualify")
        profile, settings = state["profile"], self.deps.settings
        started = time.monotonic()
        candidates = self.deps.index.search(
            profile.as_query(),
            k=settings.top_k,
            max_age_days=settings.max_lead_age_days,
            sources=with_inbound(profile.sources),
            kinds=profile.kinds,
        )
        kept = [c for c in candidates if not is_excluded(profile, c.lead)]
        self.activity.hood(
            "qualifier", "memory", f"Qualifier recalled the {len(kept)} closest leads from memory", _ms(started),
            query=profile.as_query(), k=settings.top_k, max_age_days=settings.max_lead_age_days,
            excluded=len(candidates) - len(kept), sample=[c.lead.title for c in kept[:5]],
        )
        return {"candidates": kept}

    def grade(self, state: ScoutState) -> dict:
        """Score every candidate with heuristics, then let the LLM qualify the top few."""
        profile = state["profile"]
        scored = sorted((heuristic_score(profile, c) for c in state.get("candidates", [])),
                        key=lambda s: s.score, reverse=True)
        errors: list[str] = []
        if self.deps.reasoner is not None:
            limit = min(self.deps.settings.llm_grade_limit, len(scored))
            checked = []
            for i, s in enumerate(scored[:limit]):
                self.activity.progress("qualifier", i, limit, f"checking \"{s.lead.title[:60]}\"")
                checked.append(self._llm_qualify(profile, s, errors))
            scored = sorted(checked + scored[limit:], key=lambda s: s.score, reverse=True)
        self.activity.progress("qualifier", len(scored), len(scored), f"reviewed {len(scored)} leads")
        threshold = self.deps.settings.good_match_threshold
        for s in scored:
            self.activity.act("qualifier", f"reviewed \"{s.lead.title[:60]}\"")
            self.activity.reviewed(s, qualified=s.score >= threshold)
        return {"scored": scored, "errors": errors}

    def should_broaden(self, state: ScoutState) -> str:
        """Loop back with wider queries if we found too few good leads (bounded by max_iterations)."""
        settings = self.deps.settings
        good = sum(1 for s in state.get("scored", []) if s.score >= settings.good_match_threshold)
        if good < settings.min_good_matches and state["iteration"] < settings.max_iterations:
            return "broaden"
        return "report"

    def report(self, state: ScoutState) -> dict:
        """Render a markdown briefing of the best leads."""
        self.activity.stage("write")
        self.activity.progress("writer", 0, 1, "drafting outreach")
        threshold = self.deps.settings.good_match_threshold
        self.activity.pitched([s for s in state.get("scored", []) if s.score >= threshold])
        self.activity.act("writer", "drafted outreach")
        self.activity.progress("writer", 1, 1, "outreach drafted")
        self.activity.stage("report")
        self.activity.progress("head", 0, 1, "writing the briefing")
        top = state.get("scored", [])[:REPORT_ROWS]
        table = render_table(top)
        summary = ""
        if self.deps.reasoner is not None and top:
            try:
                summary = self.deps.reasoner.summarize(state["profile"], table) + "\n\n"
            except Exception as exc:
                log.warning("Summary failed: %s", exc)
        self.activity.act("head", "wrote the briefing")
        self.activity.progress("head", 1, 1, "briefing ready")
        return {"report": report_header(state["profile"]) + summary + (table or NO_LEADS)}

    def _llm_qualify(self, profile: AgencyProfile, scored: ScoredLead, errors: list[str]) -> ScoredLead:
        try:
            verdict = self.deps.reasoner.qualify(profile, scored.lead)
        except Exception as exc:
            errors.append(f"qualify {scored.lead.id}: {exc}")
            return scored
        return blend_with_llm(scored, verdict.score, verdict.reasons, verdict.red_flags, verdict.pitch)


NO_LEADS = "_No matching client leads found._"


def _ms(started: float) -> int:
    return round((time.monotonic() - started) * 1000)


def report_header(profile: AgencyProfile) -> str:
    return f"# Client leads for {profile.name}\n\n"


def render_table(rows: list[ScoredLead]) -> str:
    if not rows:
        return ""
    lines = ["| # | Score | Lead | Type | Client | Source | Budget | Why / pitch |", "|---" * 8 + "|"]
    for i, row in enumerate(rows, 1):
        lead = row.lead
        why = row.reasons + (f" ⚠️ {row.red_flags}" if row.red_flags else "") + (f" 💬 {row.pitch}" if row.pitch else "")
        title = f"[{_cell(lead.title)}]({lead.url})" if lead.url else _cell(lead.title)
        lines.append(
            f"| {i} | {row.score:.2f} | {title} | {lead.kind} | {_cell(client_label(lead))} | {lead.source} "
            f"| {budget_label(lead)} | {_cell(why)} |"
        )
    return "\n".join(lines)


def budget_label(lead: Lead) -> str:
    return f"${lead.budget.max_usd:,.0f}" if lead.budget and lead.budget.max_usd else "—"


def client_label(lead: Lead) -> str:
    client = lead.client
    if client is None:
        return "—"
    return " · ".join(part for part in (client.name, client.country) if part) or "—"


def _cell(text: str) -> str:
    return text.replace("|", "/").replace("\n", " ")


def with_inbound(sources: tuple[str, ...] | None) -> tuple[str, ...] | None:
    """Restricting pull sources must not hide inbound leads, which arrive by webhook, not by search."""
    return None if sources is None else (*sources, GOOGLE_ADS)


def _base_queries(profile: AgencyProfile) -> list[str]:
    return [q.lower() for q in (profile.keywords or profile.services or profile.skills)][:MAX_BASE_QUERIES]


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(i for i in items if i))
