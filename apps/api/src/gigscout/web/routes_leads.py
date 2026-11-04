"""The lead workspace: browse, search, open, move through the sales pipeline, and ask questions."""

import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from gigscout.learning import OUTCOMES
from gigscout.models import Candidate
from gigscout.platform.learner import rescore_open_leads
from gigscout.platform.tables import LeadState
from gigscout.store.vector_store import StoredLead
from gigscout.web.deps import PlatformDep, SessionDep, WsDep, audit
from gigscout.web.schemas import AskRequest, AskResponse, LeadPage, LeadUpdate, LeadView

router = APIRouter(prefix="/api/leads", tags=["leads"])

SEMANTIC_POOL = 200
Sort = Literal["score", "recent", "budget"]


@router.get("")
def list_leads(
    session: SessionDep,
    ws: WsDep,
    q: str | None = Query(default=None, max_length=300, description="Semantic search"),
    kind: list[str] = Query(default=[]),
    source: list[str] = Query(default=[]),
    status_: list[str] = Query(default=[], alias="status"),
    min_score: float | None = Query(default=None, ge=0, le=1),
    sort: Sort = "score",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
) -> LeadPage:
    states = load_states(session, ws.id)
    if q and len(q.strip()) >= 2:
        hits = ws.index.search(q, k=SEMANTIC_POOL)
        views = [to_view(None, states, c) for c in hits]
    else:
        views = [to_view(stored, states) for stored in ws.index.records()]
    views = [
        v for v in views
        if (not kind or v.lead.kind in kind)
        and (not source or v.lead.source in source)
        and (not status_ or v.status in status_)
        and (min_score is None or (v.score or 0) >= min_score)
    ]
    if not q:
        views.sort(key=_sort_key(sort), reverse=True)
    start = (page - 1) * page_size
    return LeadPage(items=views[start:start + page_size], total=len(views), page=page, page_size=page_size)


@router.get("/{lead_id:path}")
def get_lead(lead_id: str, session: SessionDep, ws: WsDep) -> LeadView:
    lead = ws.index.get(lead_id)
    if lead is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lead not found")
    state = session.get(LeadState, (ws.id, lead_id))
    return to_view(None, {lead_id: state} if state else {}, Candidate(lead=lead, similarity=1))


@router.patch("/{lead_id:path}")
def update_lead(
    lead_id: str, body: LeadUpdate, platform: PlatformDep, session: SessionDep, ws: WsDep,
) -> LeadView:
    lead = ws.index.get(lead_id)
    if lead is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lead not found")
    state = session.get(LeadState, (ws.id, lead_id)) or LeadState(workspace_id=ws.id, lead_id=lead_id)
    previous = state.status or "new"
    changes = body.model_dump(exclude_none=True)
    for field, value in changes.items():
        setattr(state, field, value)
    outcome_changed = previous != state.status and (previous in OUTCOMES or state.status in OUTCOMES)
    state.updated_by = ws.email
    session.add(state)
    audit(session, ws, "lead.update", lead_id, **changes)
    session.flush()
    if outcome_changed:
        rescore_open_leads(session, ws.index, ws.id)  # a new win or loss teaches something
    session.commit()
    platform.bus.publish("lead.updated", {"id": lead_id, "title": lead.title, "by": ws.user.name, **changes}, ws.id)
    return to_view(None, {lead_id: state}, Candidate(lead=lead, similarity=1))


@router.post("/ask/stream", tags=["leads"])
def ask_stream(body: AskRequest, platform: PlatformDep, session: SessionDep, ws: WsDep) -> StreamingResponse:
    """Like /ask, streamed as newline-delimited JSON: status, sources, answer tokens, then done (or error)."""
    states = load_states(session, ws.id)  # read now: the request's session is gone once streaming starts

    def lines():
        for event in platform.service.ask_stream(body.question, body.k, index=ws.index):
            if event["type"] == "sources":
                views = [to_view(None, states, c).model_dump(mode="json") for c in event["sources"]]
                event = {**event, "sources": views}
            yield json.dumps(event, default=str) + "\n"

    return StreamingResponse(lines(), media_type="application/x-ndjson", headers={"Cache-Control": "no-cache"})


@router.post("/ask", tags=["leads"])
def ask(body: AskRequest, platform: PlatformDep, session: SessionDep, ws: WsDep) -> AskResponse:
    answer = platform.service.ask(body.question, body.k, index=ws.index)
    states = load_states(session, ws.id)
    return AskResponse(answer=answer.text, sources=[to_view(None, states, c) for c in answer.sources])


def load_states(session, workspace_id: int) -> dict[str, LeadState]:
    return {s.lead_id: s for s in session.scalars(select(LeadState).where(LeadState.workspace_id == workspace_id))}


def to_view(stored: StoredLead | None, states: dict[str, LeadState], candidate: Candidate | None = None) -> LeadView:
    lead = stored.lead if stored else candidate.lead
    state = states.get(lead.id)
    return LeadView(
        lead=lead,
        seen_at=stored.seen_at if stored else None,
        similarity=candidate.similarity if candidate and stored is None else None,
        **({
            "status": state.status, "notes": state.notes, "score": state.score, "reasons": state.reasons,
            "red_flags": state.red_flags, "pitch": state.pitch, "learned": state.learned or 0.0,
            "learned_note": state.learned_note or "",
        } if state else {}),
    )


def _sort_key(sort: Sort):
    if sort == "recent":
        return lambda v: v.seen_at.timestamp() if v.seen_at else 0
    if sort == "budget":
        return lambda v: (v.lead.budget.max_usd or 0) if v.lead.budget else 0
    return lambda v: (v.score if v.score is not None else -1, v.seen_at.timestamp() if v.seen_at else 0)
