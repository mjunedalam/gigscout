"""The research agent on demand: brief the team on a lead's client before pitching."""

from fastapi import APIRouter, HTTPException, status
from fastapi.concurrency import run_in_threadpool

from gigscout.platform.briefs import brief_out, research_lead
from gigscout.platform.pitches import _profile_for
from gigscout.platform.tables import LeadBrief
from gigscout.web.deps import PlatformDep, SessionDep, WriterDep, WsDep

router = APIRouter(prefix="/api/research", tags=["research"])


@router.get("/{lead_id:path}")
def get_brief(lead_id: str, session: SessionDep, ws: WsDep) -> dict:
    return {"brief": brief_out(session.get(LeadBrief, (ws.id, lead_id)))}


@router.post("/{lead_id:path}")
async def research(lead_id: str, platform: PlatformDep, session: SessionDep, ws: WriterDep) -> dict:
    """Read the client's website and what we already know about them, and write a brief with its sources."""
    lead = ws.index.get(lead_id)
    if lead is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lead not found")
    profile = _profile_for(session, ws.id, None)
    if profile is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Create a company profile first: research is done for it")

    def work() -> dict:
        row = research_lead(session, ws.id, lead, profile, ws.index.records(), platform.service.web_client,
                            platform.service.deps.reasoner, ws.email)
        session.commit()
        return brief_out(row)

    out = await run_in_threadpool(work)
    platform.bus.publish("lead.researched", {"id": lead_id, "title": lead.title, "by": ws.user.name}, ws.id)
    return {"brief": out}
