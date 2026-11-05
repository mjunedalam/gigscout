"""Client research briefs: run the research agent for a lead and keep what it found, so pitches can use it."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from gigscout import research
from gigscout.http import PoliteClient
from gigscout.models import AgencyProfile, Lead
from gigscout.platform.tables import AuditLog, LeadBrief, utcnow
from gigscout.store.vector_store import StoredLead

FRESH_FOR = timedelta(days=14)  # a brief younger than this is reused instead of researched again


def research_lead(session: Session, workspace_id: int, lead: Lead, profile: AgencyProfile,
                  records: Sequence[StoredLead], client: PoliteClient, researcher: object | None,
                  actor: str) -> LeadBrief:
    """Read the client's website and what the lead store knows, write the brief, and keep it (one per lead)."""
    found = research.gather(client, lead, records)
    brief, made_by = research.brief_for(profile, lead, found, researcher)
    row = session.get(LeadBrief, (workspace_id, lead.id)) or LeadBrief(workspace_id=workspace_id, lead_id=lead.id)
    row.website, row.brief, row.tech = found.website, brief.model_dump(), list(found.tech)
    row.sources, row.made_by, row.created_by, row.created_at = found.sources[:12], made_by, actor, utcnow()
    session.merge(row)
    session.add(AuditLog(actor=actor, action="lead.research", target=lead.id, workspace_id=workspace_id,
                         detail={"website": found.website or "", "by": made_by, "errors": found.errors[:5]}))
    return row


def fresh_brief(session: Session, workspace_id: int, lead_id: str, now: datetime | None = None) -> LeadBrief | None:
    row = session.get(LeadBrief, (workspace_id, lead_id))
    if row is None:
        return None
    made = row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=UTC)
    return row if (now or utcnow()) - made < FRESH_FOR else None


def brief_out(row: LeadBrief | None) -> dict | None:
    if row is None:
        return None
    made = row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=UTC)
    return {"lead_id": row.lead_id, "website": row.website, "brief": row.brief, "tech": row.tech or [],
            "sources": row.sources or [], "made_by": row.made_by, "created_by": row.created_by,
            "created_at": made.isoformat()}
