"""The AI analyst: what changed in the pipeline, said plainly, and answers to questions about the numbers.

What changed is computed, not guessed: the analyst reads the owner report and finds the moves worth a look. The
LLM only puts it into words and answers questions, from a fact sheet built from the same numbers, so every
statement can be traced back to a figure on the report.
"""

import logging
from typing import Literal, Protocol

from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

MIN_VOLUME = 5  # fewer leads than this at a step and a change means little
BIG_CHANGE = 0.25  # a 25% move in a count is worth a line
RATE_CHANGE = 0.05  # five points in a rate
STEP_ORDER = ("found", "qualified", "drafted", "sent", "replied", "proposal", "won")


class Insight(BaseModel):
    kind: Literal["up", "down", "warning", "tip"]
    text: str
    metric: str = ""  # which number it is about, for linking from the page


class AnalystAnswer(BaseModel):
    """An answer to a question about the pipeline, grounded in the fact sheet."""

    answer: str = Field(description="2-5 sentences answering the question with the numbers that show it")
    evidence: list[str] = Field(default_factory=list, description="1-4 exact figures from the fact sheet used")
    actions: list[str] = Field(default_factory=list, description="0-3 concrete next steps")


class Analyst(Protocol):
    def analyze(self, question: str, facts: str) -> AnalystAnswer: ...


def insights(report: dict) -> list[Insight]:
    """The moves worth a look in this period, most important first."""
    found: list[tuple[float, Insight]] = []
    steps = {s["stage"]: s for s in report["stages"]}
    for stage in STEP_ORDER:
        s = steps.get(stage)
        if not s or max(s["count"], s["previous"]) < MIN_VOLUME:
            continue
        change = (s["count"] - s["previous"]) / s["previous"] if s["previous"] else 1.0
        if abs(change) >= BIG_CHANGE:
            kind = "up" if change > 0 else "down"
            text = (f"{s['label']}: {s['count']} vs {s['previous']} the period before ({change:+.0%})."
                    if s["previous"] else f"{s['label']}: {s['count']}, none the period before.")
            weight = abs(change) * (1 + STEP_ORDER.index(stage) / 3)  # later steps matter more
            found.append((weight, Insight(kind=kind, text=text, metric=stage)))
    for stage, s in steps.items():
        if s.get("stale"):
            found.append((2.0, Insight(kind="warning", metric=stage,
                                       text=f"{s['stale']} lead(s) waiting too long at {s['label'].lower()}.")))
    sent, replied = steps.get("sent"), steps.get("replied")
    if sent and replied and sent["count"] >= MIN_VOLUME and sent["previous"] >= MIN_VOLUME:
        now, before = replied["count"] / sent["count"], replied["previous"] / sent["previous"]
        if abs(now - before) >= RATE_CHANGE:
            kind = "up" if now > before else "down"
            found.append((1.8, Insight(kind=kind, metric="reply_rate",
                                       text=f"Reply rate {now:.0%}, from {before:.0%} the period before.")))
    rate = report["pitches"].get("approval_rate")
    if rate is not None and report["pitches"]["approved"] + report["pitches"]["rejected"] >= MIN_VOLUME and rate < 0.5:
        found.append((1.5, Insight(kind="warning", metric="approval_rate",
                                   text=f"Only {rate:.0%} of pitches were approved: tell the agents why in the "
                                        "reject reasons, and add case studies to the knowledge base.")))
    best = next((s for s in report["sources"] if s["won"] or s["replied"]), None)
    if best:
        found.append((1.2, Insight(kind="tip", metric="sources",
                                   text=f"{best['source']} brought the most results: {best['replied']} replies, "
                                        f"{best['won']} won. Schedule it more often.")))
    quiet = [s for s in report["sources"] if s["found"] >= 20 and not s["qualified"]]
    if quiet:
        names = ", ".join(s["source"] for s in quiet[:3])
        found.append((1.0, Insight(kind="tip", metric="sources",
                                   text=f"{names} found leads but none qualified: consider turning them off.")))
    return [i for _w, i in sorted(found, key=lambda pair: pair[0], reverse=True)][:8]


def fact_sheet(report: dict) -> str:
    """Every number the analyst may use, as plain lines."""
    lines = [f"Period: last {report['days']} days ({report['start'][:10]} to {report['end'][:10]}), "
             f"compared with the {report['days']} days before."]
    for s in report["stages"]:
        conv = f", {s['conversion']:.0%} of the step before" if s["conversion"] is not None else ""
        wait = f", median {s['median_hours']} h to get there" if s["median_hours"] is not None else ""
        lines.append(f"- {s['label']}: {s['count']} (before: {s['previous']}){conv}{wait}; open now {s['waiting']}"
                     f"{', ' + str(s['stale']) + ' stuck' if s['stale'] else ''}")
    r, p, runs = report["revenue"], report["pitches"], report["runs"]
    lines.append(f"Revenue won: ${r['won']:,.0f} from {r['deals']} deal(s) (before: ${r['previous']:,.0f}).")
    lines.append(f"Pitches: {p['drafted']} drafted ({p['by_agents']} by the agents), {p['approved']} approved, "
                 f"{p['rejected']} rejected, {p['waiting']} waiting; median review {p['median_review_hours']} h.")
    lines.append(f"Agent runs: {runs['total']} ({runs['failed']} failed), {runs['new_leads']} new leads.")
    for s in report["sources"][:10]:
        lines.append(f"- Source {s['source']}: found {s['found']}, qualified {s['qualified']}, sent {s['sent']}, "
                     f"replied {s['replied']}, won {s['won']} (${s['won_value']:,.0f})")
    for person in report["people"][:8]:
        lines.append(f"- {person['actor']}: drafted {person['drafted']}, sent {person['sent']}, won {person['won']}")
    if report.get("replies"):
        lines.append("Replies by meaning: " + ", ".join(f"{k} {v}" for k, v in report["replies"].items()))
    return "\n".join(lines)


def answer(question: str, report: dict, analyst: object | None) -> tuple[AnalystAnswer, str]:
    """Answer from the numbers: with the LLM when one runs, else with the computed insights."""
    if analyst is not None and hasattr(analyst, "analyze"):
        try:
            return analyst.analyze(question, fact_sheet(report)), "ai"
        except Exception:
            log.warning("The analyst LLM failed; answering with the computed insights", exc_info=True)
    found = insights(report)
    text = " ".join(i.text for i in found[:4]) or "Nothing moved enough in this period to stand out."
    return AnalystAnswer(answer=text, evidence=[i.text for i in found[:4]],
                         actions=[i.text for i in found if i.kind in ("warning", "tip")][:3]), "rules"
