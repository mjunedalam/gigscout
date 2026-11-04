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
from gigscout.web.deps import PlatformDep, SessionDep, WsDep
from gigscout.web.routes_leads import load_states
from gigscout.web.schemas import LearningOut, LearningSignalOut

router = APIRouter(prefix="/api", tags=["insights"])

KEEPALIVE_SECONDS = 15.0


@router.get("/metrics/overview")
def metrics_overview(platform: PlatformDep, session: SessionDep, ws: WsDep) -> dict:
    return snapshot(platform, session, ws.id)


@router.get("/metrics/learning")
def metrics_learning(session: SessionDep, ws: WsDep) -> LearningOut:
    """What won and lost leads have taught so far, strongest signals first."""
    learning = current_learning(session, ws.index, ws.id)
    return LearningOut(
        active=learning.active, outcomes=learning.outcomes, wins=learning.wins,
        losses=learning.outcomes - learning.wins, needed=MIN_OUTCOMES, base_rate=learning.base_rate,
        signals=[LearningSignalOut(label=s.label, wins=s.wins, total=s.total, lift=s.lift, explain=s.explain())
                 for s in learning.top_signals()],
    )


@router.get("/metrics/analytics")
def metrics_analytics(
    session: SessionDep, ws: WsDep, days: int = Query(default=14, ge=1, le=90),
) -> dict:
    leads = ws.index.records()
    states = load_states(session, ws.id)
    runs = list(session.scalars(select(Run).where(Run.workspace_id == ws.id)))
    return {
        "timeseries": analytics.timeseries(leads, days),
        "score_histogram": analytics.score_histogram(states.values()),
        "competition": analytics.competition(leads, states),
        "funnel": analytics.funnel(leads, states),
        "runs": analytics.run_series(runs),
    }


@router.get("/metrics/map")
def lead_map(session: SessionDep, ws: WsDep) -> list[dict]:
    recent = analytics.most_recent(ws.index.records())
    return analytics.semantic_map(recent, ws.index.embeddings([s.lead.id for s in recent]), load_states(session, ws.id))


@router.get("/events/recent")
def recent_events(platform: PlatformDep, ws: WsDep, limit: int = Query(default=50, ge=1, le=200)) -> list[dict]:
    return [event.as_dict() for event in platform.bus.recent(limit, ws.id)]


@router.get("/events/stream")
async def event_stream(request: Request, platform: PlatformDep, ws: WsDep) -> StreamingResponse:
    """Live events for the workspace (EventSource cannot send headers, so it passes ?workspace=)."""
    return StreamingResponse(
        _sse(request, platform, ws.id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def snapshot(platform: Platform, session, workspace_id: int) -> dict:
    runs = list(session.scalars(select(Run).where(Run.workspace_id == workspace_id)))
    overview = analytics.overview(
        platform.index_for(workspace_id).records(), load_states(session, workspace_id), runs,
        platform.settings.good_match_threshold,
    )
    active = [r for r in runs if r.status in ("queued", "running")]
    return {
        **overview.__dict__,
        "active_runs": [{"id": r.id, "status": r.status, "profile_name": r.profile_name} for r in active],
        "live_clients": platform.bus.subscribers_in(workspace_id),
    }


async def _sse(request: Request, platform: Platform, workspace_id: int) -> AsyncIterator[str]:
    sub = platform.bus.subscribe(workspace_id)
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
