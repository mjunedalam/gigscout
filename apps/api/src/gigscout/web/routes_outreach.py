"""Outreach: draft a first message per lead, edit it, send it, track the reply, and push the lead to the CRM."""

import logging
import smtplib
import threading
from datetime import timedelta

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from gigscout import crm as crm_lib
from gigscout import outreach as outreach_lib
from gigscout.mail import email_ready
from gigscout.models import AgencyProfile, Lead
from gigscout.platform.tables import AgencyProfileRecord, CrmRecord, LeadState, Outreach, utcnow
from gigscout.web.deps import PlatformDep, SessionDep, UserDep, WriterDep, Ws, WsDep, audit
from gigscout.web.schemas import (
    CrmLinkOut,
    CrmSyncIn,
    CrmSyncOut,
    OutreachConfigOut,
    OutreachCreate,
    OutreachOut,
    OutreachStatusIn,
    OutreachUpdate,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/outreach", tags=["outreach"])

HOURLY_EMAIL_LIMIT = 30  # per person: protects the sender domain's reputation
_sending = threading.Lock()  # count, send and record as one step, so parallel sends cannot pass the limit
SMTP_HELP = "Email is not set up: set GIGSCOUT_SMTP_HOST and GIGSCOUT_SMTP_FROM in apps/api/.env"
CRM_HELP = "No CRM connected: set GIGSCOUT_HUBSPOT_TOKEN or GIGSCOUT_PIPEDRIVE_TOKEN in apps/api/.env"


@router.get("/config")
def outreach_config(platform: PlatformDep, _: UserDep) -> OutreachConfigOut:
    return OutreachConfigOut(email_ready=email_ready(platform.settings),
                             crms=[c.name for c in crm_lib.configured(platform.settings)])


@router.get("")
def list_outreach(lead_id: str, session: SessionDep, ws: WsDep) -> list[OutreachOut]:
    rows = session.scalars(select(Outreach).where(Outreach.workspace_id == ws.id, Outreach.lead_id == lead_id)
                           .order_by(Outreach.id.desc()))
    return [_out(r) for r in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_draft(body: OutreachCreate, platform: PlatformDep, session: SessionDep, user: WriterDep) -> OutreachOut:
    lead = _lead(user, body.lead_id)
    profile = _profile(session, user.id, body.profile_id)
    state = session.get(LeadState, (user.id, lead.id))
    draft = outreach_lib.draft_outreach(profile, lead, state.pitch if state else "", platform.service.deps.reasoner)
    row = Outreach(workspace_id=user.id, lead_id=lead.id, channel=draft.channel, to_address=draft.to,
                   subject=draft.subject, body=draft.body, source=draft.source, created_by=user.email)
    session.add(row)
    session.flush()
    audit(session, user, "outreach.draft", lead.id, channel=draft.channel, source=draft.source)
    session.commit()
    return _out(row)


@router.put("/{outreach_id}")
def edit_draft(outreach_id: int, body: OutreachUpdate, session: SessionDep, ws: WriterDep) -> OutreachOut:
    row = _draft(session, ws.id, outreach_id)
    if body.channel == "email" and not body.to:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "An email needs an address to send to")
    row.channel, row.to_address, row.subject, row.body = body.channel, body.to, body.subject.strip(), body.body
    session.commit()
    return _out(row)


@router.post("/{outreach_id}/send")
def send(outreach_id: int, platform: PlatformDep, session: SessionDep, user: WriterDep) -> OutreachOut:
    """Email it, or for a marketplace bid record that it was pasted into the bid form. A draft is sent once."""
    row = _draft(session, user.id, outreach_id)
    with _sending:
        session.refresh(row)
        if row.status != "draft":
            raise HTTPException(status.HTTP_409_CONFLICT, "Already sent: start a new draft to follow up")
        if row.channel == "email":
            _email(platform, session, user, row)
        row.status, row.sent_at, row.sent_by = "sent", utcnow(), user.email
        session.commit()
    state = session.get(LeadState, (user.id, row.lead_id)) or LeadState(workspace_id=user.id, lead_id=row.lead_id)
    if (state.status or "new") == "new":
        state.status, state.updated_by = "contacted", user.email
    session.merge(state)
    audit(session, user, "outreach.send", row.lead_id, channel=row.channel, to=row.to_address or "")
    session.commit()
    lead = user.index.get(row.lead_id)
    platform.bus.publish("lead.updated", {"id": row.lead_id, "title": lead.title if lead else row.lead_id,
                                          "by": user.user.name, "status": state.status}, user.id)
    return _out(row)


@router.post("/{outreach_id}/status")
def set_status(outreach_id: int, body: OutreachStatusIn, session: SessionDep, user: WriterDep) -> OutreachOut:
    row = session.get(Outreach, outreach_id)
    if row is None or row.workspace_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
    if row.status == "draft":
        raise HTTPException(status.HTTP_409_CONFLICT, "Send the message before recording a reply")
    row.status = body.status
    audit(session, user, "outreach.status", row.lead_id, status=body.status)
    session.commit()
    return _out(row)


@router.get("/crm")
def crm_links(lead_id: str, session: SessionDep, ws: WsDep) -> CrmSyncOut:
    rows = session.scalars(select(CrmRecord).where(CrmRecord.workspace_id == ws.id, CrmRecord.lead_id == lead_id)
                           .order_by(CrmRecord.id))
    return CrmSyncOut(links=[_link(r) for r in rows])


@router.post("/crm")
def push_to_crm(body: CrmSyncIn, platform: PlatformDep, session: SessionDep, user: WriterDep) -> CrmSyncOut:
    """Create a deal in every connected CRM that does not have this lead yet."""
    crms = crm_lib.configured(platform.settings)
    if not crms:
        raise HTTPException(status.HTTP_409_CONFLICT, CRM_HELP)
    lead = _lead(user, body.lead_id)
    existing = {r.crm: r for r in session.scalars(select(CrmRecord).where(
        CrmRecord.workspace_id == user.id, CrmRecord.lead_id == lead.id))}
    state = session.get(LeadState, (user.id, lead.id))
    errors: list[str] = []
    for crm in crms:
        if crm.name in existing:
            continue
        try:
            link = crm.push(lead, state.pitch if state else "")
        except crm_lib.CrmError as exc:
            errors.append(str(exc))
            continue
        existing[crm.name] = CrmRecord(workspace_id=user.id, lead_id=lead.id, crm=link.crm,
                                       external_id=link.external_id, url=link.url, created_by=user.email)
        session.add(existing[crm.name])
        audit(session, user, "crm.push", lead.id, crm=link.crm, external_id=link.external_id)
    session.commit()
    if not existing:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "; ".join(errors))
    return CrmSyncOut(links=[_link(r) for r in existing.values()], errors=errors)


def _email(platform, session, user: Ws, row: Outreach) -> None:
    if not email_ready(platform.settings):
        raise HTTPException(status.HTTP_409_CONFLICT, SMTP_HELP)
    if not outreach_lib.single_address(row.to_address) or not row.subject:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "An email needs one valid address and a subject")
    since = utcnow() - timedelta(hours=1)
    recent = session.scalar(select(func.count()).select_from(Outreach).where(
        Outreach.sent_by == user.email, Outreach.channel == "email", Outreach.sent_at >= since,
    ))
    if recent >= HOURLY_EMAIL_LIMIT:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"At most {HOURLY_EMAIL_LIMIT} emails an hour")
    try:
        outreach_lib.send_email(platform.settings, row.to_address, row.subject, row.body)
    except (smtplib.SMTPException, OSError) as exc:
        log.warning("Outreach email to %s failed", row.to_address, exc_info=True)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"The mail server refused it ({type(exc).__name__})") from None


def _lead(ws: Ws, lead_id: str) -> Lead:
    lead = ws.index.get(lead_id)
    if lead is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lead not found")
    return lead


def _profile(session, workspace_id: int, profile_id: int | None) -> AgencyProfile:
    record = session.get(AgencyProfileRecord, profile_id) if profile_id else session.scalar(
        select(AgencyProfileRecord).where(AgencyProfileRecord.workspace_id == workspace_id)
        .order_by(AgencyProfileRecord.id).limit(1))
    if record is None or record.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Create a company profile first: drafts are written in its voice")
    return AgencyProfile.model_validate(record.data)


def _draft(session, workspace_id: int, outreach_id: int) -> Outreach:
    row = session.get(Outreach, outreach_id)
    if row is None or row.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
    if row.status != "draft":
        raise HTTPException(status.HTTP_409_CONFLICT, "Already sent: start a new draft to follow up")
    return row


def _out(row: Outreach) -> OutreachOut:
    return OutreachOut(id=row.id, lead_id=row.lead_id, channel=row.channel, to=row.to_address, subject=row.subject,
                       body=row.body, status=row.status, source=row.source, created_by=row.created_by,
                       created_at=row.created_at, sent_at=row.sent_at)


def _link(row: CrmRecord) -> CrmLinkOut:
    return CrmLinkOut(crm=row.crm, external_id=row.external_id, url=row.url, created_at=row.created_at)
