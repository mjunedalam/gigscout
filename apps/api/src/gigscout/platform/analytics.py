"""Numbers behind the dashboards. Pure functions over stored leads, lead states and runs."""

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import numpy as np

from gigscout.models import ALL_LEAD_KINDS
from gigscout.platform.tables import LEAD_STATUSES, LeadState, Run
from gigscout.store.vector_store import StoredLead
from gigscout.text import contains_term

SCORE_BINS = 10
SCATTER_LIMIT = 600
MAP_LIMIT = 1500
FUNNEL_STAGES = ("new", "contacted", "proposal", "won")


@dataclass(frozen=True)
class Overview:
    total_leads: int
    new_last_24h: int
    inbound_last_7d: int
    qualified: int
    by_kind: dict[str, int]
    by_source: dict[str, int]
    by_status: dict[str, int]
    runs_total: int
    runs_succeeded_7d: int
    runs_failed_7d: int
    avg_run_seconds: float | None
    last_run_at: str | None


def overview(
    leads: Sequence[StoredLead], states: dict[str, LeadState], runs: Sequence[Run], threshold: float,
    now: datetime | None = None,
) -> Overview:
    now = now or datetime.now(UTC)
    week_ago, day_ago = now - timedelta(days=7), now - timedelta(days=1)
    recent_runs = [r for r in runs if _aware(r.created_at) >= week_ago]
    durations = [d for r in runs if r.status == "succeeded" and (d := r.duration_seconds) is not None]
    last_run = max((_aware(r.created_at) for r in runs), default=None)
    return Overview(
        total_leads=len(leads),
        new_last_24h=sum(1 for s in leads if s.seen_at >= day_ago),
        inbound_last_7d=sum(1 for s in leads if s.lead.kind == "inbound" and s.seen_at >= week_ago),
        qualified=sum(1 for st in states.values() if st.score is not None and st.score >= threshold),
        by_kind={kind: count for kind in ALL_LEAD_KINDS if (count := sum(s.lead.kind == kind for s in leads))},
        by_source=dict(Counter(s.lead.source for s in leads).most_common()),
        by_status=_status_counts(leads, states),
        runs_total=len(runs),
        runs_succeeded_7d=sum(r.status == "succeeded" for r in recent_runs),
        runs_failed_7d=sum(r.status == "failed" for r in recent_runs),
        avg_run_seconds=round(sum(durations) / len(durations), 1) if durations else None,
        last_run_at=last_run.isoformat() if last_run else None,
    )


def timeseries(leads: Iterable[StoredLead], days: int, now: datetime | None = None) -> list[dict]:
    """Leads first seen per day, split by kind: one row per day, oldest first."""
    today = (now or datetime.now(UTC)).date()
    start = today - timedelta(days=days - 1)
    rows = {start + timedelta(days=i): dict.fromkeys(ALL_LEAD_KINDS, 0) for i in range(days)}
    for stored in leads:
        day = stored.seen_at.date()
        if day in rows:
            rows[day][stored.lead.kind] += 1
    return [{"date": day.isoformat(), **counts} for day, counts in rows.items()]


def score_histogram(states: Iterable[LeadState]) -> list[dict]:
    counts = [0] * SCORE_BINS
    for state in states:
        if state.score is not None:
            counts[min(int(state.score * SCORE_BINS), SCORE_BINS - 1)] += 1
    return [{"from": i / SCORE_BINS, "to": (i + 1) / SCORE_BINS, "count": c} for i, c in enumerate(counts)]


def competition(leads: Sequence[StoredLead], states: dict[str, LeadState]) -> list[dict]:
    """Budget against competing bids, for marketplace leads that publish both."""
    points = []
    for stored in leads:
        lead = stored.lead
        budget = lead.budget.max_usd if lead.budget else None
        if lead.bid_count is None or not budget:
            continue
        state = states.get(lead.id)
        points.append({
            "id": lead.id, "title": lead.title, "kind": lead.kind, "bids": lead.bid_count,
            "budget_usd": round(budget, 2), "score": state.score if state else None,
        })
    return sorted(points, key=lambda p: p["budget_usd"], reverse=True)[:SCATTER_LIMIT]


def funnel(leads: Sequence[StoredLead], states: dict[str, LeadState]) -> list[dict]:
    """Leads that reached at least each stage (won counts as having been contacted and proposed to)."""
    counts = _status_counts(leads, states)
    reached = []
    for i, stage in enumerate(FUNNEL_STAGES):
        reached.append({"stage": stage, "count": sum(counts.get(s, 0) for s in FUNNEL_STAGES[i:])})
    reached.append({"stage": "lost", "count": counts.get("lost", 0)})
    return reached


def run_series(runs: Sequence[Run], limit: int = 30) -> list[dict]:
    finished = sorted((r for r in runs if r.finished_at), key=lambda r: _aware(r.created_at))[-limit:]
    return [{
        "id": r.id, "at": _aware(r.created_at).isoformat(), "status": r.status, "mode": r.mode or r.mode_requested,
        "duration_seconds": r.duration_seconds, "fetched": r.fetched_count, "new": r.new_count,
        "matches": r.match_count, "top_score": r.top_score,
    } for r in finished]


def semantic_map(
    leads: Sequence[StoredLead], vectors: dict[str, list[float]], states: dict[str, LeadState],
) -> list[dict]:
    """Project lead embeddings to 3D with PCA, so similar leads sit close together in the galaxy view."""
    usable = [s for s in leads if s.lead.id in vectors]
    if len(usable) < 4:
        return []
    matrix = np.asarray([vectors[s.lead.id] for s in usable], dtype=np.float32)
    centered = matrix - matrix.mean(axis=0)
    _, _, components = np.linalg.svd(centered, full_matrices=False)
    coords = centered @ components[:3].T
    coords /= np.abs(coords).max(axis=0).clip(min=1e-9)
    return [{
        "id": s.lead.id, "title": s.lead.title, "kind": s.lead.kind, "source": s.lead.source,
        "x": round(float(x), 4), "y": round(float(y), 4), "z": round(float(z), 4),
        "score": states[s.lead.id].score if s.lead.id in states else None,
    } for s, (x, y, z) in zip(usable, coords, strict=True)]


TREND_WEEKS = 4  # recent window, compared with the same length before it
TREND_TOP = 12
MIN_MENTIONS = 3  # a term needs this many mentions (both windows) before its change means anything


def trends(leads: Sequence[StoredLead], watch_terms: Iterable[str] = (), now: datetime | None = None,
           weeks: int = TREND_WEEKS) -> dict:
    """What the market asks for: skills in demand and how fast that is changing (the last `weeks` against the
    `weeks` before), the median project budget per week, and which sources are growing.

    Terms are the skills leads list, plus `watch_terms` (the company's own skills and services) wherever a lead
    mentions them, so the trends say something about what this company sells."""
    now = now or datetime.now(UTC)
    window = timedelta(weeks=weeks)
    recent_from, previous_from = now - window, now - 2 * window
    watch = {t.strip().lower() for t in watch_terms if t and len(t.strip()) > 1}
    counts: dict[str, list[int]] = {}
    sources: dict[str, list[int]] = {}
    weekly: dict[date, list[float]] = {}
    for stored in leads:
        seen = stored.seen_at
        if seen < previous_from:
            continue
        slot = 0 if seen >= recent_from else 1
        lead = stored.lead
        text = f"{lead.title} {lead.description}".lower()
        terms = {s.strip().lower() for s in lead.skills if s.strip()} | {t for t in watch if contains_term(text, t)}
        for term in terms:
            counts.setdefault(term, [0, 0])[slot] += 1
        sources.setdefault(lead.source, [0, 0])[slot] += 1
        budget = lead.budget.max_usd if lead.budget and lead.budget.kind in ("fixed", "unknown") else None
        if budget and lead.kind in ("project", "contract"):
            week = (seen - timedelta(days=seen.weekday())).date()
            weekly.setdefault(week, []).append(budget)

    def row(term: str, recent: int, previous: int) -> dict:
        change = None if previous == 0 else round((recent - previous) / previous, 3)
        return {"term": term, "recent": recent, "previous": previous, "change": change, "yours": term in watch}

    rows = [row(t, r, p) for t, (r, p) in counts.items() if r + p >= MIN_MENTIONS]
    demand = sorted(rows, key=lambda x: (x["recent"], x["previous"]), reverse=True)[:TREND_TOP]
    moving = [x for x in rows if x["previous"] and x["recent"] + x["previous"] >= 2 * MIN_MENTIONS]
    rising = sorted((x for x in moving if x["change"] > 0), key=lambda x: x["change"], reverse=True)[:TREND_TOP // 2]
    falling = sorted((x for x in moving if x["change"] < 0), key=lambda x: x["change"])[:TREND_TOP // 2]
    return {
        "weeks": weeks,
        "demand": demand,
        "rising": rising,
        "falling": falling,
        "new": sorted((x for x in rows if x["previous"] == 0), key=lambda x: x["recent"], reverse=True)[:6],
        "budgets": [{"week": w.isoformat(), "median_usd": round(float(np.median(v)), 2), "count": len(v)}
                    for w, v in sorted(weekly.items())],
        "sources": sorted(({"source": s, "recent": r, "previous": p} for s, (r, p) in sources.items()),
                          key=lambda x: x["recent"], reverse=True),
    }


def most_recent(leads: Sequence[StoredLead], limit: int = MAP_LIMIT) -> list[StoredLead]:
    return sorted(leads, key=lambda s: s.seen_at, reverse=True)[:limit]


def _status_counts(leads: Sequence[StoredLead], states: dict[str, LeadState]) -> dict[str, int]:
    counts = Counter(states[s.lead.id].status if s.lead.id in states else "new" for s in leads)
    return {status: counts.get(status, 0) for status in LEAD_STATUSES}


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)
