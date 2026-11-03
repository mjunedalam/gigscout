"""Numbers behind the dashboards. Pure functions over stored leads, lead states and runs."""

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import numpy as np

from gigscout.models import ALL_LEAD_KINDS
from gigscout.platform.tables import LEAD_STATUSES, LeadState, Run
from gigscout.store.vector_store import StoredLead

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


def most_recent(leads: Sequence[StoredLead], limit: int = MAP_LIMIT) -> list[StoredLead]:
    return sorted(leads, key=lambda s: s.seen_at, reverse=True)[:limit]


def _status_counts(leads: Sequence[StoredLead], states: dict[str, LeadState]) -> dict[str, int]:
    counts = Counter(states[s.lead.id].status if s.lead.id in states else "new" for s in leads)
    return {status: counts.get(status, 0) for status in LEAD_STATUSES}


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)
