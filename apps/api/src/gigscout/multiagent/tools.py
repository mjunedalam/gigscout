"""The tools each specialist can use: the "Act" in Reason → Act → Observe.

Tools return short plain-text observations (that is what the model reads next) and report problems as text
instead of raising, so the agent can reason about a failure and try something else.
"""

from langchain_core.tools import BaseTool, tool

from gigscout.agent.nodes import budget_label, client_label, with_inbound
from gigscout.models import Candidate, ScoredLead
from gigscout.multiagent.context import RunContext
from gigscout.scoring import blend_with_llm, heuristic_score, is_excluded

SAMPLE_TITLES = 5
DETAIL_CHARS = 2500


def build_scout_tools(ctx: RunContext) -> list[BaseTool]:
    @tool
    def list_sources() -> str:
        """List the lead sources you can search."""
        wanted = ctx.profile.sources
        names = [n for n in ctx.deps.sources if wanted is None or n in wanted]
        return "Available sources: " + ", ".join(names)

    @tool
    def search_source(source: str, query: str) -> str:
        """Search one lead source with a short keyword query (1-3 words) and store the results in memory."""
        query = query.strip().lower()
        if source not in ctx.deps.sources:
            return f"ERROR: unknown source '{source}'. Call list_sources."
        if (source, query) in ctx.searches:
            return f"Already searched {source} for '{query}'. Try a different query or source."
        if ctx.searches_left <= 0:
            return "Search budget exhausted. Stop searching and report what you found."
        ctx.searches.append((source, query))
        budget = ctx.deps.settings.team_max_searches
        ctx.activity.progress("prospector", len(ctx.searches), budget, f"searching {source} for '{query}'")
        try:
            leads = ctx.deps.sources[source].fetch([query], ctx.deps.settings.per_query_limit)
        except Exception as exc:
            ctx.errors.append(f"{source}: {exc}")
            return f"ERROR: {source} failed ({exc}). Try another source."
        fresh = ctx.deps.index.add_new(leads)
        ctx.activity.act("prospector", f"searched {source}")
        ctx.activity.found(source, leads)
        ctx.fetched_ids.update(lead.id for lead in leads)
        ctx.new_count += len(fresh)
        titles = "; ".join(lead.title for lead in leads[:SAMPLE_TITLES]) or "none"
        return f"{source} '{query}': {len(leads)} results ({len(fresh)} new). Examples: {titles}"

    @tool
    def search_progress() -> str:
        """Show how many searches you have run and how many remain in the budget."""
        tried = ", ".join(f"{s}:'{q}'" for s, q in ctx.searches) or "none"
        return f"{ctx.progress()}. Tried: {tried}"

    return [list_sources, search_source, search_progress]


def build_analyst_tools(ctx: RunContext) -> list[BaseTool]:
    settings, profile = ctx.deps.settings, ctx.profile

    @tool
    def find_leads(query: str, k: int = 10) -> str:
        """Semantic search over every stored lead. Returns id, title, kind, similarity and a heuristic score."""
        results = ctx.deps.index.search(
            query, k=max(1, min(k, settings.top_k)), max_age_days=settings.max_lead_age_days,
            sources=with_inbound(profile.sources), kinds=profile.kinds,
        )
        kept = [c for c in results if not is_excluded(profile, c.lead)]
        ctx.activity.act("qualifier", f"searched memory for '{query}'")
        filled, slots = len(ctx.shortlist), settings.shortlist_size
        ctx.activity.progress("qualifier", filled, slots, f"searching memory for '{query}'")
        if not kept:
            return "No matching leads in memory. Ask for more prospecting."
        ctx.seen.update({c.lead.id: c for c in kept})
        rows = [_candidate_row(heuristic_score(profile, c)) for c in kept]
        return "id | title | kind | source | similarity | heuristic | budget | notes\n" + "\n".join(rows)

    @tool
    def read_lead(lead_id: str) -> str:
        """Read the full details of one lead by id."""
        lead = ctx.deps.index.get(lead_id)
        if lead is None:
            return f"ERROR: no lead with id '{lead_id}'."
        bids = lead.bid_count if lead.bid_count is not None else "unknown"
        return (
            f"{lead.title} ({lead.kind} from {lead.source})\nURL: {lead.url or 'n/a'}\n"
            f"Client: {client_label(lead)}\nSkills: {', '.join(lead.skills) or 'n/a'}\n"
            f"Budget (USD max): {budget_label(lead)}\nCompeting bids: {bids}\n\n{lead.description[:DETAIL_CHARS]}"
        )

    @tool
    def qualify_lead(lead_id: str, fit_score: float, reason: str, red_flags: str = "", pitch: str = "") -> str:
        """Add a lead to the shortlist. fit_score is your 0-1 judgement; reason and pitch are one sentence each."""
        candidate = ctx.seen.get(lead_id)
        if candidate is None:
            lead = ctx.deps.index.get(lead_id)
            if lead is None:
                return f"ERROR: no lead with id '{lead_id}'."
            candidate = Candidate(lead=lead, similarity=0.0)
        if lead_id not in ctx.shortlist and len(ctx.shortlist) >= settings.shortlist_size:
            return f"Shortlist is full ({settings.shortlist_size}). Finish your analysis."
        score = min(max(fit_score, 0.0), 1.0)
        ctx.shortlist[lead_id] = blend_with_llm(heuristic_score(profile, candidate), score, reason, red_flags, pitch)
        ctx.activity.act("qualifier", f"qualified \"{ctx.shortlist[lead_id].lead.title[:60]}\"")
        ctx.activity.reviewed(ctx.shortlist[lead_id], qualified=True)
        title = ctx.shortlist[lead_id].lead.title[:60]
        ctx.activity.progress("qualifier", len(ctx.shortlist), settings.shortlist_size, f"shortlisted \"{title}\"")
        return f"Qualified {lead_id} ({len(ctx.shortlist)}/{settings.shortlist_size})."

    return [find_leads, read_lead, qualify_lead, _view_shortlist_tool(ctx)]


def build_writer_tools(ctx: RunContext) -> list[BaseTool]:
    @tool
    def submit_report(markdown: str) -> str:
        """Submit the final markdown briefing for the sales team. Call exactly once when done."""
        if not markdown.strip():
            return "ERROR: report is empty."
        ctx.report = markdown.strip()
        ctx.activity.act("writer", "submitted the briefing")
        ctx.activity.progress("writer", 1, 1, "briefing submitted")
        return "Report saved."

    read_lead = next(t for t in build_analyst_tools(ctx) if t.name == "read_lead")
    return [_view_shortlist_tool(ctx), read_lead, submit_report]


def _view_shortlist_tool(ctx: RunContext) -> BaseTool:
    @tool
    def view_shortlist() -> str:
        """Show the current shortlist of qualified leads, best first."""
        ranked = ctx.ranked_shortlist()
        if not ranked:
            return "Shortlist is empty."
        return "\n".join(f"{i}. {_shortlist_row(s)}" for i, s in enumerate(ranked, 1))

    return view_shortlist


def _candidate_row(s: ScoredLead) -> str:
    lead = s.lead
    return (
        f"{lead.id} | {lead.title} | {lead.kind} | {lead.source} | {s.similarity:.2f} | {s.score:.2f} "
        f"| {budget_label(lead)} | {s.reasons}"
    )


def _shortlist_row(s: ScoredLead) -> str:
    lead = s.lead
    flags = f" RED FLAGS: {s.red_flags}" if s.red_flags else ""
    pitch = f" PITCH: {s.pitch}" if s.pitch else ""
    return (
        f"[{s.score:.2f}] {lead.title} ({lead.kind}, {lead.source}, client {client_label(lead)}, "
        f"{budget_label(lead)}) {lead.url} — {s.reasons}{flags}{pitch} (id {lead.id})"
    )
