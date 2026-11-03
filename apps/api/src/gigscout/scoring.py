"""Deterministic lead scoring — works with no LLM at all, and is blended with the LLM's judgement when present."""

from gigscout.models import AgencyProfile, Candidate, Lead, ScoredLead
from gigscout.text import contains_term

SIMILARITY_WEIGHT = 0.45
SKILL_WEIGHT = 0.30
BUDGET_WEIGHT = 0.15
OPPORTUNITY_WEIGHT = 0.10
LLM_WEIGHT = 0.6

UNKNOWN_FIT = 0.5
CROWDED_BIDS = 20  # at this many competing bids, the opportunity signal halves
OFF_TARGET_COUNTRY_PENALTY = 0.5


def skill_overlap(profile: AgencyProfile, lead: Lead) -> float:
    text = lead.document()
    hits = sum(1 for skill in profile.skills if contains_term(text, skill))
    return hits / len(profile.skills)


def budget_fit(profile: AgencyProfile, lead: Lead) -> float:
    if not profile.min_budget_usd:
        return 1.0
    max_usd = lead.budget.max_usd if lead.budget else None
    if max_usd is None:
        return UNKNOWN_FIT
    return min(max_usd / profile.min_budget_usd, 1.0)


def opportunity_fit(profile: AgencyProfile, lead: Lead) -> float:
    """How winnable the lead is: inbound beats marketplace, fewer competing bids beats more, target markets win."""
    if lead.kind == "inbound":
        fit = 1.0
    elif lead.bid_count is None:
        fit = UNKNOWN_FIT
    else:
        fit = 1 / (1 + lead.bid_count / CROWDED_BIDS)
    country = lead.client.country if lead.client else None
    if profile.target_countries and country and not any(
        country.casefold() == c.casefold() for c in profile.target_countries
    ):
        fit *= OFF_TARGET_COUNTRY_PENALTY
    return fit


def is_excluded(profile: AgencyProfile, lead: Lead) -> bool:
    text = f"{lead.title} {lead.description}"
    return any(contains_term(text, term) for term in profile.exclude)


def heuristic_score(profile: AgencyProfile, candidate: Candidate) -> ScoredLead:
    lead = candidate.lead
    score = (
        SIMILARITY_WEIGHT * candidate.similarity
        + SKILL_WEIGHT * skill_overlap(profile, lead)
        + BUDGET_WEIGHT * budget_fit(profile, lead)
        + OPPORTUNITY_WEIGHT * opportunity_fit(profile, lead)
    )
    return ScoredLead(
        lead=lead, similarity=candidate.similarity, score=round(score, 4), reasons=_reasons(profile, lead)
    )


def blend_with_llm(scored: ScoredLead, llm_score: float, reasons: str, red_flags: str, pitch: str = "") -> ScoredLead:
    blended = (1 - LLM_WEIGHT) * scored.score + LLM_WEIGHT * llm_score
    return scored.model_copy(
        update={"score": round(blended, 4), "reasons": reasons, "red_flags": red_flags, "pitch": pitch}
    )


def drop_reason(profile: AgencyProfile, scored: ScoredLead) -> str:
    """The main reason a lead did not make the shortlist, as one short label for the cockpit."""
    lead = scored.lead
    if scored.red_flags:
        return "red flags"
    max_usd = lead.budget.max_usd if lead.budget else None
    if profile.min_budget_usd and max_usd is not None and max_usd < profile.min_budget_usd:
        return "budget too low"
    if lead.bid_count is not None and lead.bid_count >= CROWDED_BIDS:
        return "too many bids"
    if profile.skills and skill_overlap(profile, lead) == 0:
        return "off-stack"
    return "low fit"


def _reasons(profile: AgencyProfile, lead: Lead) -> str:
    matched = [s for s in profile.skills if contains_term(lead.document(), s)]
    parts = [f"Matches {', '.join(matched)}" if matched else "Semantically similar, no exact stack match"]
    if lead.kind == "inbound":
        parts.append("inbound enquiry")
    elif lead.bid_count is not None:
        parts.append(f"{lead.bid_count} competing bids")
    return "; ".join(parts)
