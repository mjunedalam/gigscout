"""Deterministic lead scoring — works with no LLM at all, and is blended with the LLM's judgement when present."""

from gigscout import quality
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
SCAM_FACTOR = 0.2
DUPLICATE_FACTOR = 0.5
WARNING_PENALTY = 0.05
MAX_WARNING_PENALTY = 0.15


def fit_terms(profile: AgencyProfile) -> tuple[str, ...]:
    """What a lead should mention to fit: the capabilities, or (for non-technical companies) services and keywords."""
    return profile.skills or (*profile.services, *profile.keywords)


def skill_overlap(profile: AgencyProfile, lead: Lead) -> float:
    terms = fit_terms(profile)
    text = lead.document()
    return sum(1 for term in terms if contains_term(text, term)) / len(terms)


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


def below_budget(profile: AgencyProfile, lead: Lead) -> bool:
    """A stated total budget under the company's minimum. Unknown budgets pass: many good clients do not state one."""
    max_usd = quality.total_budget_usd(lead)  # an hourly rate is never compared with a project minimum
    return bool(profile.min_budget_usd) and max_usd is not None and max_usd < profile.min_budget_usd


def skip_reason(profile: AgencyProfile, lead: Lead) -> str | None:
    """Why a lead is not worth the agents' time at all, checked before any scoring; None if it is."""
    if quality.is_scam(lead):
        return "looks like a scam"
    if lead.duplicate_of:
        return "duplicate of an earlier lead"
    if below_budget(profile, lead):
        return "budget too low"
    if is_excluded(profile, lead):
        return "excluded by the profile"
    return None


def heuristic_score(profile: AgencyProfile, candidate: Candidate) -> ScoredLead:
    lead = candidate.lead
    score = quality_adjusted(lead, (
        SIMILARITY_WEIGHT * candidate.similarity
        + SKILL_WEIGHT * skill_overlap(profile, lead)
        + BUDGET_WEIGHT * budget_fit(profile, lead)
        + OPPORTUNITY_WEIGHT * opportunity_fit(profile, lead)
    ))
    return ScoredLead(
        lead=lead, similarity=candidate.similarity, score=round(score, 4), reasons=_reasons(profile, lead)
    )


def quality_adjusted(lead: Lead, score: float) -> float:
    """Scams and duplicates sink; each warning costs a little (capped)."""
    if quality.is_scam(lead):
        score *= SCAM_FACTOR
    if lead.duplicate_of:
        score *= DUPLICATE_FACTOR
    return max(0.0, score - min(MAX_WARNING_PENALTY, WARNING_PENALTY * len(quality.warnings(lead))))


def blend_with_llm(scored: ScoredLead, llm_score: float, reasons: str, red_flags: str, pitch: str = "") -> ScoredLead:
    blended = (1 - LLM_WEIGHT) * scored.score + LLM_WEIGHT * llm_score
    return scored.model_copy(
        update={"score": round(blended, 4), "reasons": reasons, "red_flags": red_flags, "pitch": pitch}
    )


def drop_reason(profile: AgencyProfile, scored: ScoredLead) -> str:
    """The main reason a lead did not make the shortlist, as one short label for the cockpit."""
    lead = scored.lead
    if quality.is_scam(lead):
        return "looks like a scam"
    if lead.duplicate_of:
        return "duplicate of an earlier lead"
    if scored.red_flags or quality.warnings(lead):
        return "red flags"
    if below_budget(profile, lead):
        return "budget too low"
    if lead.bid_count is not None and lead.bid_count >= CROWDED_BIDS:
        return "too many bids"
    if skill_overlap(profile, lead) == 0:
        return "off-target"
    return "low fit"


def _reasons(profile: AgencyProfile, lead: Lead) -> str:
    matched = [s for s in fit_terms(profile) if contains_term(lead.document(), s)]
    parts = [f"Matches {', '.join(matched)}" if matched else "Semantically similar, no exact match"]
    if lead.kind == "inbound":
        parts.append("inbound enquiry")
    elif lead.bid_count is not None:
        parts.append(f"{lead.bid_count} competing bids")
    if lead.quality:
        parts.append(f"watch out: {quality.summary(lead.quality)}")
    return "; ".join(parts)
