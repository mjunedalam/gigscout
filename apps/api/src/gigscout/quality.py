"""Lead quality check: duplicates and the patterns behind marketplace scams, explained in plain words.

Rules are deliberately simple and visible (no hidden model): each flag says what was found. A `scam` flag keeps a
lead away from the agents; a `warning` lowers its score a little and is shown next to it.
"""

import re
from collections.abc import Iterable

from gigscout.models import Lead, QualityFlag

QUALITY_VERSION = 1  # bump when rules change so stored leads are checked again
MIN_DETAIL_CHARS = 40
TINY_BUDGET_USD = 100
DUPLICATE_SIMILARITY = 0.95  # meaning (cosine) and ...
DUPLICATE_TITLE_OVERLAP = 0.6  # ... title words must both agree, so templated posts are not merged
# Within one site, only near-identical reposts count: a buyer's separate tenders (other towns, other lots) share a
# template and would otherwise look like one.
REPOST_SIMILARITY = 0.97
REPOST_TITLE_OVERLAP = 0.8
MARKETPLACE_KINDS = ("project", "contract")
TOTAL_BUDGET_KINDS = ("fixed", "unknown")  # hourly rates and salaries are not a project's total
TENDER_SOURCES = ("contracts_finder", "find_a_tender", "ted", "sam_gov")  # public notices list contacts by design

_SCAM = [
    (r"\b(registration|application|joining|training|onboarding|processing)\s+fees?\b", "asks you to pay a fee"),
    (r"\bpay\s+(a\s+)?(small\s+|one[- ]time\s+)?(fee|deposit)\b", "asks you to pay a fee"),
    (r"\b(upfront|advance)\s+(payment|fee|deposit)\s+(from|by)\s+(you|the\s+(freelancer|developer|applicant))\b",
     "asks you to pay upfront"),
    (r"\bgift\s*cards?\b", "mentions gift cards"),
    (r"\b(western\s+union|money\s*gram|cash\s*app)\b", "asks for untraceable payment"),
    (r"\bsend\s+(me\s+|us\s+)?(money|funds|bitcoin|btc|usdt|crypto)\b", "asks you to send money"),
    (r"\b(deposit|cash)\s+(the|a|my)\s+(check|cheque)\b", "fake-cheque pattern"),
]
_WARN = [
    (r"\b(contact|message|reach|text|add|ping|dm|call)\s+(me|us)\s+(on|via|at|through)\s+"
     r"(whats\s?app|telegram|wechat|skype|signal)\b", "asks to talk off the platform"),
    (r"\b(whats\s?app|telegram|wechat|skype)\s*(:|number|no\.|id\b|handle|@)", "asks to talk off the platform"),
    (r"\b(unpaid|free)\s+(test|trial|sample|task|work)\b", "wants unpaid work first"),
    (r"\b(equity|revenue[- ]share)\s+only\b", "pays in equity only"),
    (r"\bno\s+(pay|payment)\b(?!\s*(integration|gateway|processing|system|module|provider|method|page|flow|"
     r"upfront|in\s+advance))", "no payment offered"),
]
_CONTACT = re.compile(r"[\w.+-]+@[\w-]+\.[a-z]{2,}|\+\d{1,3}[\s-]?\(?\d[\d\s()-]{7,}\d")
_WORD = re.compile(r"[a-z0-9]+")


def check(lead: Lead) -> tuple[QualityFlag, ...]:
    """Everything that makes this lead look risky or thin. Inbound enquiries are people writing to you directly, so
    only the scam patterns apply to them."""
    text = f"{lead.title}\n{lead.description}".lower()
    flags: dict[str, QualityFlag] = {}
    for pattern, label in _SCAM:
        if re.search(pattern, text):
            flags.setdefault(label, QualityFlag(code="scam", label=label, severity="scam"))
    if lead.kind == "inbound":
        return tuple(flags.values())
    for pattern, label in _WARN:
        if re.search(pattern, text):
            flags.setdefault(label, QualityFlag(code="warning", label=label, severity="warning"))
    if lead.kind == "project" and lead.source not in TENDER_SOURCES and _CONTACT.search(lead.description):
        flags["contact"] = QualityFlag(code="contact", label="posts personal contact details", severity="warning")
    if len(lead.description.strip()) < MIN_DETAIL_CHARS:
        flags["thin"] = QualityFlag(code="thin", label="very little detail", severity="warning")
    max_usd = total_budget_usd(lead)
    if lead.kind in MARKETPLACE_KINDS and max_usd is not None and 0 < max_usd < TINY_BUDGET_USD:
        flags["tiny"] = QualityFlag(code="tiny_budget", label=f"budget under ${TINY_BUDGET_USD}", severity="warning")
    return tuple(flags.values())


def total_budget_usd(lead: Lead) -> float | None:
    """The project's total budget in USD, or None for hourly rates, salaries and unstated budgets."""
    if lead.budget is None or lead.budget.kind not in TOTAL_BUDGET_KINDS:
        return None
    return lead.budget.max_usd


def is_duplicate(lead: Lead, other: Lead, similarity: float) -> bool:
    """The same job: across sites, close in meaning and title; on the same site, a near-identical repost."""
    if lead.source == other.source:
        return similarity >= REPOST_SIMILARITY and _overlap(lead.title, other.title) >= REPOST_TITLE_OVERLAP
    return similarity >= DUPLICATE_SIMILARITY and _overlap(lead.title, other.title) >= DUPLICATE_TITLE_OVERLAP


def assessed(lead: Lead, duplicate_of: str | None = None) -> Lead:
    return lead.model_copy(update={"quality": check(lead), "duplicate_of": duplicate_of})


def is_scam(lead: Lead) -> bool:
    return any(f.severity == "scam" for f in lead.quality)


def warnings(lead: Lead) -> list[QualityFlag]:
    return [f for f in lead.quality if f.severity == "warning"]


def _overlap(a: str, b: str) -> float:
    words_a, words_b = set(_WORD.findall(a.lower())), set(_WORD.findall(b.lower()))
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)


def summary(flags: Iterable[QualityFlag]) -> str:
    return "; ".join(f.label for f in flags)
