"""The pitch desk: the agents draft pitches on their own, and nothing leaves until a person approves it.

After each run the best new leads get a drafted pitch; a daily pass drafts one follow-up for emails nobody answered.
Every draft waits in the approval queue (status "draft") where people edit, approve (send) or reject it.
"""

import logging
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta

from sqlalchemy import select

from gigscout import quality
from gigscout.models import AgencyProfile, ScoredLead
from gigscout.outreach import Drafter, draft_outreach, follow_up_draft
from gigscout.platform.db import SessionFactory
from gigscout.platform.events import EventBus
from gigscout.platform.scheduler import ScheduleManager
from gigscout.platform.tables import (
    AGENT_AUTHOR,
    AgencyProfileRecord,
    AuditLog,
    LeadState,
    Outreach,
    PitchSettings,
    Run,
    utcnow,
)
from gigscout.store.vector_store import LeadIndex

log = logging.getLogger(__name__)

JOB_ID = "follow_ups"
FOLLOW_UP_HOUR = 9
DEFAULTS = {"auto_draft": False, "min_score": 0.7, "max_per_run": 5, "follow_up_days": 0, "require_admin": False}


def pitch_settings(session, workspace_id: int) -> PitchSettings:
    """The workspace's saved settings, or the defaults (not added to the session)."""
    return session.get(PitchSettings, workspace_id) or PitchSettings(workspace_id=workspace_id, **DEFAULTS)


class PitchDesk:
    def __init__(self, sessions: SessionFactory, bus: EventBus, schedules: ScheduleManager,
                 index_for: Callable[[int], LeadIndex], drafter: Callable[[], Drafter | None]) -> None:
        self._sessions = sessions
        self._bus = bus
        self._schedules = schedules
        self._index_for = index_for
        self._drafter = drafter  # the LLM when one is running; templates otherwise

    def start(self) -> None:
        self._schedules.set_daily(JOB_ID, FOLLOW_UP_HOUR, self.follow_up_all)

    def draft_for_run(self, workspace_id: int, run_id: str, agency: AgencyProfile, matches: Sequence[ScoredLead],
                      on_step: Callable[[str], None] = lambda _line: None) -> int:
        """Draft a pitch for each of the run's best leads nobody is working yet. Returns how many were drafted."""
        with self._sessions() as session:
            settings = pitch_settings(session, workspace_id)
            if not settings.auto_draft:
                return 0
            picked = self._worth_pitching(session, workspace_id, settings, matches)
        if not picked:
            return 0
        on_step(f"Pitch writer: drafting {len(picked)} pitch(es) for your approval")
        drafter = self._drafter()
        drafts = [(match, draft_outreach(agency, match.lead, match.pitch, drafter)) for match in picked]
        with self._sessions() as session:
            taken = _pitched(session, workspace_id, [m.lead.id for m in picked])  # someone may have started one
            drafted = 0
            for match, draft in drafts:
                if match.lead.id in taken:
                    continue
                session.add(Outreach(workspace_id=workspace_id, lead_id=match.lead.id, channel=draft.channel,
                                     to_address=draft.to, subject=draft.subject, body=draft.body, source=draft.source,
                                     run_id=run_id, created_by=AGENT_AUTHOR))
                session.add(AuditLog(actor=AGENT_AUTHOR, action="pitch.auto_draft", target=match.lead.id,
                                     detail={"run_id": run_id, "channel": draft.channel}, workspace_id=workspace_id))
                drafted += 1
            session.commit()
        if drafted:
            on_step(f"Pitch writer: {drafted} pitch(es) are waiting for approval")
            self._bus.publish("pitch.drafted", {"count": drafted, "run_id": run_id}, workspace_id)
        return drafted

    def follow_ups(self, workspace_id: int, now: datetime | None = None) -> int:
        """Draft one follow-up for each email that got no answer within the workspace's follow-up days."""
        with self._sessions() as session:
            days = pitch_settings(session, workspace_id).follow_up_days
            if days <= 0:
                return 0
            cutoff = (now or utcnow()) - timedelta(days=days)
            quiet = list(session.scalars(select(Outreach).where(
                Outreach.workspace_id == workspace_id, Outreach.status == "sent", Outreach.channel == "email",
                Outreach.kind == "first", Outreach.sent_at <= cutoff).order_by(Outreach.id)))
            latest = _latest_message(session, workspace_id, [row.lead_id for row in quiet])
            index = self._index_for(workspace_id)
            drafted = 0
            for row in quiet:
                if latest.get(row.lead_id, row.id) != row.id:  # a newer message exists: already followed up
                    continue
                lead, agency = index.get(row.lead_id), _profile_for(session, workspace_id, row.run_id)
                if lead is None or agency is None:
                    continue
                draft = follow_up_draft(agency, lead, row.to_address or "", row.subject, row.body)
                session.add(Outreach(workspace_id=workspace_id, lead_id=row.lead_id, channel="email",
                                     to_address=draft.to, subject=draft.subject, body=draft.body, kind="follow_up",
                                     run_id=row.run_id, created_by=AGENT_AUTHOR))
                session.add(AuditLog(actor=AGENT_AUTHOR, action="pitch.follow_up", target=row.lead_id,
                                     detail={"after_days": days}, workspace_id=workspace_id))
                drafted += 1
            session.commit()
        if drafted:
            self._bus.publish("pitch.drafted", {"count": drafted, "follow_up": True}, workspace_id)
        return drafted

    def follow_up_all(self) -> None:
        with self._sessions() as session:
            ids = list(session.scalars(select(PitchSettings.workspace_id).where(PitchSettings.follow_up_days > 0)))
        for workspace_id in ids:
            try:
                self.follow_ups(workspace_id)
            except Exception:
                log.warning("Follow-up drafting failed for workspace %s", workspace_id, exc_info=True)

    @staticmethod
    def _worth_pitching(session, workspace_id: int, settings: PitchSettings,
                        matches: Sequence[ScoredLead]) -> list[ScoredLead]:
        ids = [m.lead.id for m in matches]
        taken = _pitched(session, workspace_id, ids)
        statuses = dict(session.execute(select(LeadState.lead_id, LeadState.status).where(
            LeadState.workspace_id == workspace_id, LeadState.lead_id.in_(ids))).all())
        fresh = [m for m in matches if m.score >= settings.min_score and m.lead.id not in taken
                 and (statuses.get(m.lead.id) or "new") == "new"
                 and not quality.is_scam(m.lead) and not m.lead.duplicate_of]
        return sorted(fresh, key=lambda m: m.score, reverse=True)[:settings.max_per_run]


def _pitched(session, workspace_id: int, lead_ids: Sequence[str]) -> set[str]:
    """Leads that already have a message in any state, so the agents never pitch a lead twice."""
    if not lead_ids:
        return set()
    return set(session.scalars(select(Outreach.lead_id).where(
        Outreach.workspace_id == workspace_id, Outreach.lead_id.in_(lead_ids))))


def _latest_message(session, workspace_id: int, lead_ids: Sequence[str]) -> dict[str, int]:
    latest: dict[str, int] = {}
    if lead_ids:
        for lead_id, outreach_id in session.execute(select(Outreach.lead_id, Outreach.id).where(
                Outreach.workspace_id == workspace_id, Outreach.lead_id.in_(lead_ids))):
            latest[lead_id] = max(latest.get(lead_id, 0), outreach_id)
    return latest


def _profile_for(session, workspace_id: int, run_id: str | None) -> AgencyProfile | None:
    """The profile the first message was written for, else the workspace's first profile."""
    run = session.get(Run, run_id) if run_id else None
    record = session.get(AgencyProfileRecord, run.profile_id) if run and run.profile_id else None
    if record is None or record.workspace_id != workspace_id:
        record = session.scalar(select(AgencyProfileRecord).where(AgencyProfileRecord.workspace_id == workspace_id)
                                .order_by(AgencyProfileRecord.id).limit(1))
    return AgencyProfile.model_validate(record.data) if record else None
