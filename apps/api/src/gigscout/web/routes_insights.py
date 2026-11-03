"""Dashboards and live updates: metrics, analytics, the 3D lead map, and the Server-Sent Events stream."""

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from gigscout.learning import MIN_OUTCOMES
from gigscout.platform import analytics
from gigscout.platform.container import Platform
from gigscout.platform.learner import current_learning
from gigscout.platform.tables import Run
from gigscout.web.deps import PlatformDep, SessionDep, UserDep
from gigscout.web.routes_leads import load_states
from gigscout.web.schemas import LearningOut, LearningSignalOut

router = APIRouter(prefix="/api", tags=["insights"])

KEEPALIVE_SECONDS = 15.0


@router.get("/metrics/overview")
def metrics_overview(platform: PlatformDep, session: SessionDep, _: UserDep) -> dict:
    return snapshot(platform, session)


@router.get("/metrics/learning")
def metrics_learning(platform: PlatformDep, session: SessionDep, _: UserDep) -> LearningOut:
    """What won and lost leads have taught so far, strongest signals first."""
    learning = current_learning(session, platform.service.deps.index)
    return LearningOut(
        active=learning.active, outcomes=learning.outcomes, wins=learning.wins,
        losses=learning.outcomes - learning.wins, needed=MIN_OUTCOMES, base_rate=learning.base_rate,
        signals=[LearningSignalOut(label=s.label, wins=s.wins, total=s.total, lift=s.lift, explain=s.explain())
                 for s in learning.top_signals()],
    )


@router.get("/metrics/analytics")
def metrics_analytics(
    platform: PlatformDep, session: SessionDep, _: UserDep, days: int = Query(default=14, ge=1, le=90),
) -> dict:
    leads = platform.service.deps.index.records()
    states = load_states(session)
    runs = list(session.scalars(select(Run)))
    return {
        "timeseries": analytics.timeseries(leads, days),
        "score_histogram": analytics.score_histogram(states.values()),
        "competition": analytics.competition(leads, states),
        "funnel": analytics.funnel(leads, states),
        "runs": analytics.run_series(runs),
    }


@router.get("/metrics/map")
def lead_map(platform: PlatformDep, session: SessionDep, _: UserDep) -> list[dict]:
    index = platform.service.deps.index
    recent = analytics.most_recent(index.records())
    return analytics.semantic_map(recent, index.embeddings([s.lead.id for s in recent]), load_states(session))


@router.get("/events/recent")
def recent_events(platform: PlatformDep, _: UserDep, limit: int = Query(default=50, ge=1, le=200)) -> list[dict]:
    return [event.as_dict() for event in platform.bus.recent(limit)]


@router.get("/events/stream")
async def event_stream(request: Request, platform: PlatformDep, _: UserDep) -> StreamingResponse:
    return StreamingResponse(
        _sse(request, platform),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def snapshot(platform: Platform, session) -> dict:
    overview = analytics.overview(
        platform.service.deps.index.records(), load_states(session), list(session.scalars(select(Run))),
        platform.settings.good_match_threshold,
    )
    active = list(session.scalars(select(Run).where(Run.status.in_(("queued", "running")))))
    return {
        **overview.__dict__,
        "active_runs": [{"id": r.id, "status": r.status, "profile_name": r.profile_name} for r in active],
        "live_clients": platform.bus.subscriber_count,
    }


async def _sse(request: Request, platform: Platform) -> AsyncIterator[str]:
    sub = platform.bus.subscribe()
    try:
        yield "retry: 3000\n\n"
        while not await request.is_disconnected():
            try:
                event = await asyncio.wait_for(sub.queue.get(), timeout=KEEPALIVE_SECONDS)
            except TimeoutError:
                yield ": keepalive\n\n"
                continue
            yield f"id: {event.id}\nevent: {event.type}\ndata: {json.dumps(event.as_dict(), default=str)}\n\n"
    finally:
        platform.bus.unsubscribe(sub)
