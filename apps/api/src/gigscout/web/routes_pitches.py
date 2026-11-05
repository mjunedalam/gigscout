"""The pitch approval queue: every drafted message across leads, waiting for a person, and the autopilot settings."""

from typing import Literal

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from gigscout.platform.pitches import pitch_settings
from gigscout.platform.tables import LeadState, Outreach, PitchSettings
from gigscout.web.deps import AdminDep, SessionDep, WsDep, audit
from gigscout.web.routes_outreach import can_approve, outreach_out
from gigscout.web.schemas import PitchItemOut, PitchLeadOut, PitchListOut, PitchSettingsIO, PitchSummaryOut

router = APIRouter(prefix="/api/pitches", tags=["pitches"])

SHOWN = {"pending": ("draft",), "sent": ("sent", "replied", "no_reply"), "rejected": ("rejected",)}


@router.get("")
def list_pitches(session: SessionDep, ws: WsDep, status: Literal["pending", "sent", "rejected"] = "pending",
                 limit: int = Query(default=100, ge=1, le=500)) -> PitchListOut:
    newest = Outreach.reviewed_at.desc() if status != "pending" else Outreach.id.desc()
    rows = list(session.scalars(select(Outreach).where(
        Outreach.workspace_id == ws.id, Outreach.status.in_(SHOWN[status])).order_by(newest, Outreach.id.desc())
        .limit(limit)))
    states = {s.lead_id: s for s in session.scalars(select(LeadState).where(
        LeadState.workspace_id == ws.id, LeadState.lead_id.in_({r.lead_id for r in rows})))}
    approver = can_approve(session, ws)
    items = []
    for row in rows:
        lead, state = ws.index.get(row.lead_id), states.get(row.lead_id)
        items.append(PitchItemOut(
            outreach=outreach_out(row), score=state.score if state else None, reasons=state.reasons if state else "",
            can_approve=approver,
            lead=PitchLeadOut(id=row.lead_id, title=lead.title if lead else row.lead_id, url=lead.url if lead else "",
                              source=lead.source if lead else "", kind=lead.kind if lead else "",
                              client_name=lead.client.name if lead and lead.client else None,
                              status=(state.status if state else None) or "new"),
        ))
    if status == "pending":  # the best leads first: that is what someone approving wants to see
        items.sort(key=lambda i: i.score if i.score is not None else -1, reverse=True)
    return PitchListOut(items=items, can_approve=approver)


@router.get("/summary")
def summary(session: SessionDep, ws: WsDep) -> PitchSummaryOut:
    waiting = session.scalar(select(func.count()).select_from(Outreach).where(
        Outreach.workspace_id == ws.id, Outreach.status == "draft"))
    return PitchSummaryOut(pending=waiting or 0, auto_draft=pitch_settings(session, ws.id).auto_draft,
                           can_approve=can_approve(session, ws))


@router.get("/settings")
def get_settings(session: SessionDep, ws: WsDep) -> PitchSettingsIO:
    return _io(pitch_settings(session, ws.id))


@router.put("/settings")
def put_settings(body: PitchSettingsIO, session: SessionDep, ws: AdminDep) -> PitchSettingsIO:
    row = session.get(PitchSettings, ws.id) or PitchSettings(workspace_id=ws.id)
    for field, value in body.model_dump().items():
        setattr(row, field, value)
    row.updated_by = ws.email
    session.add(row)
    audit(session, ws, "pitch.settings", **body.model_dump())
    session.commit()
    return _io(row)


def _io(row: PitchSettings) -> PitchSettingsIO:
    return PitchSettingsIO(auto_draft=row.auto_draft, min_score=row.min_score, max_per_run=row.max_per_run,
                           follow_up_days=row.follow_up_days, require_admin=row.require_admin,
                           research_first=bool(row.research_first))
