"""Client replies: the inbox the reply copilot fills, and a way to paste in replies that came another way."""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from gigscout.platform.inbox import imap_ready
from gigscout.platform.tables import Outreach, Reply
from gigscout.replies import INTENTS
from gigscout.web.deps import AdminDep, PlatformDep, SessionDep, WriterDep, WsDep, audit
from gigscout.web.routes_outreach import outreach_out

router = APIRouter(prefix="/api/replies", tags=["replies"])

LIST_LIMIT = 100


class ReplyIn(BaseModel):
    outreach_id: int
    body: str = Field(min_length=2, max_length=20_000)
    from_address: str | None = Field(default=None, max_length=254)


@router.get("")
def list_replies(session: SessionDep, ws: WsDep, state: str = Query(default="open", pattern="^(open|handled)$"),
                 limit: int = Query(default=50, ge=1, le=LIST_LIMIT)) -> dict:
    query = select(Reply).where(Reply.workspace_id == ws.id)
    query = query.where(Reply.handled_at.is_(None) if state == "open" else Reply.handled_at.is_not(None))
    rows = list(session.scalars(query.order_by(Reply.received_at.desc()).limit(limit)))
    linked = {o.id: o for o in session.scalars(select(Outreach).where(Outreach.id.in_(
        [r.outreach_id for r in rows if r.outreach_id] + [r.answer_id for r in rows if r.answer_id])))}
    items = []
    for r in rows:
        lead = ws.index.get(r.lead_id)
        original, answer = linked.get(r.outreach_id), linked.get(r.answer_id)
        items.append({
            "reply": reply_out(r),
            "lead": {"id": r.lead_id, "title": lead.title if lead else r.lead_id, "url": lead.url if lead else "",
                     "client_name": lead.client.name if lead and lead.client else None},
            "original": outreach_out(original) if original else None,
            "answer": outreach_out(answer) if answer else None,
        })
    return {"items": items}


@router.get("/summary")
def summary(platform: PlatformDep, session: SessionDep, ws: WsDep) -> dict:
    open_count = session.scalar(select(func.count()).select_from(Reply).where(
        Reply.workspace_id == ws.id, Reply.handled_at.is_(None)))
    by_intent = dict(session.execute(select(Reply.intent, func.count()).where(Reply.workspace_id == ws.id)
                                     .group_by(Reply.intent)).all())
    return {"open": open_count, "mailbox": imap_ready(platform.settings), "intents": list(INTENTS),
            "by_intent": by_intent}


@router.post("", status_code=status.HTTP_201_CREATED)
async def paste_reply(body: ReplyIn, platform: PlatformDep, ws: WriterDep) -> dict:
    """A reply that came in another way (a marketplace message, a phone note): read it and draft the answer."""
    try:
        reply = await run_in_threadpool(platform.replies.receive, ws.id, body.outreach_id, body.body,
                                        body.from_address, "", None, "pasted", ws.email)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None
    return reply_out(reply)


@router.post("/{reply_id}/done")
def mark_done(reply_id: int, session: SessionDep, ws: WriterDep) -> dict:
    row = session.get(Reply, reply_id)
    if row is None or row.workspace_id != ws.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Reply not found")
    if row.handled_at is None:
        row.handled_by, row.handled_at = ws.email, datetime.now(UTC)
        audit(session, ws, "reply.done", row.lead_id, reply_id=row.id)
        session.commit()
    return reply_out(row)


@router.post("/check-mailbox")
async def check_mailbox(platform: PlatformDep, _: AdminDep) -> dict:
    if not imap_ready(platform.settings):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "The mailbox is not set up: set GIGSCOUT_IMAP_HOST, GIGSCOUT_IMAP_USER and "
                            "GIGSCOUT_IMAP_PASSWORD in apps/api/.env")
    return {"new": await run_in_threadpool(platform.replies.poll)}


def reply_out(r: Reply) -> dict:
    return {"id": r.id, "outreach_id": r.outreach_id, "lead_id": r.lead_id, "from_address": r.from_address,
            "subject": r.subject, "body": r.body, "source": r.source, "intent": r.intent, "summary": r.summary,
            "read_by": r.read_by, "verified": r.verified is not False, "answer_id": r.answer_id,
            "received_at": _iso(r.received_at), "handled_by": r.handled_by, "handled_at": _iso(r.handled_at)}


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return (value if value.tzinfo else value.replace(tzinfo=UTC)).isoformat()
