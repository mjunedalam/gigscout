"""The sales pipeline as one connected line: Found -> Qualified -> Drafted -> Sent -> Replied -> Proposal -> Won.

Every step a lead reaches is recorded once (`mark`), with when and by whom. The numbers behind the Pipeline
page and the owner report are pure functions over those steps.
"""

from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from gigscout.platform.tables import AGENT_AUTHOR, LeadEvent, LeadState, Outreach, utcnow

STAGES = ("found", "qualified", "drafted", "sent", "replied", "proposal", "won")
EXITS = ("lost",)
STAGE_LABELS = {
    "found": "Found", "qualified": "Qualified", "drafted": "Pitch drafted", "sent": "Sent",
    "replied": "Replied", "proposal": "Proposal", "won": "Won", "lost": "Lost",
}
# a lead's status in the pipeline board, as the step it means
STATUS_STAGE = {"contacted": "sent", "proposal": "proposal", "won": "won", "lost": "lost"}
STALE_DAYS = {"drafted": 2, "sent": 7, "replied": 3, "proposal": 14}  # waiting longer than this needs a nudge


@dataclass(frozen=True)
class Step:
    lead_id: str
    stage: str
    at: datetime
    actor: str = ""


def mark(session: Session, workspace_id: int, lead_id: str, stage: str, actor: str = "",
         at: datetime | None = None) -> bool:
    """Record that a lead reached a step. Only the first time counts; returns whether this was it."""
    if stage not in STAGES and stage not in EXITS:
        raise ValueError(f"Unknown pipeline step: {stage}")
    pending = next((o for o in session.new if isinstance(o, LeadEvent) and o.workspace_id == workspace_id
                    and o.lead_id == lead_id and o.stage == stage), None)
    if pending is not None or session.scalar(select(LeadEvent.id).where(
            LeadEvent.workspace_id == workspace_id, LeadEvent.lead_id == lead_id, LeadEvent.stage == stage)):
        return False
    session.add(LeadEvent(workspace_id=workspace_id, lead_id=lead_id, stage=stage, at=at or utcnow(), actor=actor))
    return True


def mark_status(session: Session, workspace_id: int, lead_id: str, status: str, actor: str) -> None:
    if stage := STATUS_STAGE.get(status):
        mark(session, workspace_id, lead_id, stage, actor)


def backfill(session: Session, threshold: float) -> int:
    """Build the step history once from what older versions stored (outreach rows and lead statuses)."""
    if session.scalar(select(LeadEvent.id).limit(1)) is not None:
        return 0
    added = 0
    for o in session.scalars(select(Outreach).order_by(Outreach.created_at)):
        added += mark(session, o.workspace_id, o.lead_id, "drafted", o.created_by, o.created_at)
        if o.sent_at:
            added += mark(session, o.workspace_id, o.lead_id, "sent", o.sent_by or "", o.sent_at)
        if o.status == "replied":
            added += mark(session, o.workspace_id, o.lead_id, "replied", "", o.updated_at)
    for s in session.scalars(select(LeadState)):
        if s.score is not None and s.score >= threshold:
            added += mark(session, s.workspace_id, s.lead_id, "qualified", AGENT_AUTHOR, s.updated_at)
        if stage := STATUS_STAGE.get(s.status or ""):
            added += mark(session, s.workspace_id, s.lead_id, stage, s.updated_by or "", s.updated_at)
    session.commit()
    return added


def load_steps(session: Session, workspace_id: int) -> list[Step]:
    rows = session.execute(select(LeadEvent.lead_id, LeadEvent.stage, LeadEvent.at, LeadEvent.actor)
                           .where(LeadEvent.workspace_id == workspace_id))
    return [Step(lead_id, stage, _aware(at), actor) for lead_id, stage, at, actor in rows]


def with_found(steps: Sequence[Step], found: Iterable[tuple[str, datetime]]) -> list[Step]:
    """Add the 'found' step, which comes from when the lead first entered the lead store."""
    return [*(Step(lead_id, "found", _aware(at), AGENT_AUTHOR) for lead_id, at in found), *steps]


def summary(steps: Sequence[Step], start: datetime, end: datetime) -> dict:
    """Each step in [start, end): how many leads reached it, conversion from the step before, the median wait,
    the same count for the period before (for the change), and how many leads are waiting there now."""
    span = end - start
    first = _first_times(steps)
    in_window = _reached_between(first, start, end)
    before = _reached_between(first, start - span, start)
    waiting = _waiting(first, end)
    rows, previous_count = [], None
    for i, stage in enumerate((*STAGES, *EXITS)):
        count = len(in_window[stage])
        prev_stage = STAGES[i - 1] if 0 < i < len(STAGES) else None
        rows.append({
            "stage": stage, "label": STAGE_LABELS[stage], "count": count, "previous": len(before[stage]),
            "conversion": round(count / previous_count, 3) if prev_stage and previous_count else None,
            "median_hours": _median_wait(first, in_window[stage], prev_stage, stage),
            "waiting": waiting.get(stage, 0), "stale": _stale(first, stage, end),
        })
        if stage in STAGES:
            previous_count = count
    return {"start": start.isoformat(), "end": end.isoformat(), "stages": rows}


def series(steps: Sequence[Step], start: date, days: int) -> list[dict]:
    """Leads reaching each step per day (or per week past 45 days), oldest first."""
    width = 7 if days > 45 else 1
    buckets = [start + timedelta(days=i) for i in range(0, days, width)]
    rows = {b: dict.fromkeys((*STAGES, *EXITS), 0) for b in buckets}
    for (_lead, stage), at in _first_times(steps).items():
        offset = (at.date() - start).days
        if 0 <= offset < days:
            rows[buckets[offset // width]][stage] += 1
    return [{"date": b.isoformat(), **counts} for b, counts in rows.items()]


def leads_at(steps: Sequence[Step], stage: str, start: datetime, end: datetime) -> list[Step]:
    """The leads that reached a step in the period, newest first: the drill-down behind a step."""
    first = _first_times(steps)
    hits = [Step(lead, s, at) for (lead, s), at in first.items() if s == stage and start <= at < end]
    return sorted(hits, key=lambda s: s.at, reverse=True)


def by_source(steps: Sequence[Step], sources: dict[str, str], values: dict[str, float],
              start: datetime, end: datetime) -> list[dict]:
    """Per lead source: what it found and how far those leads got, plus the value won. Best sources first."""
    first = _first_times(steps)
    table: dict[str, Counter] = defaultdict(Counter)
    won_value: Counter = Counter()
    for (lead, stage), at in first.items():
        if start <= at < end and lead in sources:
            table[sources[lead]][stage] += 1
            if stage == "won":
                won_value[sources[lead]] += values.get(lead, 0.0)
    rows = [{"source": src, **{s: c[s] for s in (*STAGES, *EXITS)}, "won_value": round(won_value[src], 2),
             "reply_rate": round(c["replied"] / c["sent"], 3) if c["sent"] else None}
            for src, c in table.items()]
    return sorted(rows, key=lambda r: (r["won_value"], r["won"], r["replied"], r["qualified"], r["found"]),
                  reverse=True)


def by_person(steps: Sequence[Step], start: datetime, end: datetime) -> list[dict]:
    """Who moved leads forward in the period. Agents count as one teammate."""
    table: dict[str, Counter] = defaultdict(Counter)
    for step in steps:
        if start <= step.at < end and step.stage != "found" and step.actor:
            table[step.actor][step.stage] += 1
    rows = [{"actor": actor, **{s: c[s] for s in STAGES[1:] + EXITS}, "total": sum(c.values())}
            for actor, c in table.items()]
    return sorted(rows, key=lambda r: r["total"], reverse=True)


def _first_times(steps: Iterable[Step]) -> dict[tuple[str, str], datetime]:
    first: dict[tuple[str, str], datetime] = {}
    for step in steps:
        key = (step.lead_id, step.stage)
        if key not in first or step.at < first[key]:
            first[key] = step.at
    return first


def _reached_between(first: dict[tuple[str, str], datetime], start: datetime, end: datetime) -> dict[str, set]:
    reached: dict[str, set] = defaultdict(set)
    for (lead, stage), at in first.items():
        if start <= at < end:
            reached[stage].add(lead)
    return reached


def _furthest(first: dict[tuple[str, str], datetime], end: datetime) -> dict[str, str]:
    """Each lead's furthest step by `end`; a lost lead is out of the pipeline."""
    rank = {s: i for i, s in enumerate(STAGES)}
    furthest: dict[str, str] = {}
    lost = {lead for (lead, stage), at in first.items() if stage == "lost" and at < end}
    for (lead, stage), at in first.items():
        if at >= end or lead in lost or stage not in rank:
            continue
        if lead not in furthest or rank[stage] > rank[furthest[lead]]:
            furthest[lead] = stage
    return furthest


def _waiting(first: dict[tuple[str, str], datetime], end: datetime) -> dict[str, int]:
    return dict(Counter(s for s in _furthest(first, end).values() if s != "won"))


def _stale(first: dict[tuple[str, str], datetime], stage: str, end: datetime) -> int:
    limit = STALE_DAYS.get(stage)
    if limit is None:
        return 0
    cutoff = end - timedelta(days=limit)
    return sum(1 for lead, s in _furthest(first, end).items() if s == stage and first[(lead, stage)] < cutoff)


def _median_wait(first: dict[tuple[str, str], datetime], leads: set, prev: str | None, stage: str) -> float | None:
    if prev is None:
        return None
    waits = [(first[(lead, stage)] - first[(lead, prev)]).total_seconds() / 3600
             for lead in leads if (lead, prev) in first and first[(lead, prev)] <= first[(lead, stage)]]
    return round(median(waits), 1) if waits else None


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)
