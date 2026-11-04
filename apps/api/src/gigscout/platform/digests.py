"""Daily digest settings, scheduling and delivery, one per workspace (content is built in gigscout.digest)."""

import logging
from collections.abc import Callable
from functools import partial

from sqlalchemy import select

from gigscout import digest as digest_lib
from gigscout.config import Settings
from gigscout.digest import Digest, DigestSettingsView
from gigscout.mail import email_ready
from gigscout.platform.db import SessionFactory
from gigscout.platform.events import EventBus
from gigscout.platform.scheduler import ScheduleManager
from gigscout.platform.tables import DigestSettings, LeadState, Workspace, utcnow
from gigscout.store.vector_store import LeadIndex

log = logging.getLogger(__name__)

JOB_ID = "digest:{workspace_id}"
EDITABLE = ("enabled", "hour", "emails", "min_score", "max_leads")


class DigestManager:
    def __init__(self, sessions: SessionFactory, index_for: Callable[[int], LeadIndex], settings: Settings,
                 bus: EventBus, schedules: ScheduleManager) -> None:
        self._sessions = sessions
        self._index_for = index_for
        self._settings = settings
        self._bus = bus
        self._schedules = schedules

    def config(self, workspace_id: int) -> DigestSettings:
        with self._sessions() as session:
            row = self._row(session, workspace_id)
            if row is None:
                row = DigestSettings(workspace_id=workspace_id)
                session.add(row)
                session.commit()
            return row

    @staticmethod
    def _row(session, workspace_id: int) -> DigestSettings | None:
        return session.scalar(select(DigestSettings).where(DigestSettings.workspace_id == workspace_id))

    def save(self, workspace_id: int, change: dict) -> DigestSettings:
        """slack_webhook: None keeps the saved one, "" clears it, anything else must be a Slack webhook URL."""
        webhook = change.get("slack_webhook")
        checked = digest_lib.check_slack_webhook(webhook) if webhook else webhook
        self.config(workspace_id)  # make sure the row exists
        with self._sessions() as session:
            row = self._row(session, workspace_id)
            for field in EDITABLE:
                setattr(row, field, change[field])
            if checked is not None:
                row.slack_webhook = checked or None
            session.commit()
        self.sync(workspace_id)
        return self.config(workspace_id)

    def sync(self, workspace_id: int | None = None) -> None:
        """(Re)schedule one workspace's digest, or every workspace's at startup."""
        if workspace_id is None:
            with self._sessions() as session:
                ids = list(session.scalars(select(Workspace.id)))
            for each in ids:
                self.sync(each)
            return
        row = self.config(workspace_id)
        self._schedules.set_daily(JOB_ID.format(workspace_id=workspace_id), row.hour if row.enabled else None,
                                  partial(self.send_scheduled, workspace_id))

    def preview(self, workspace_id: int) -> Digest:
        row = self.config(workspace_id)
        with self._sessions() as session:
            states = list(session.scalars(select(LeadState).where(
                LeadState.workspace_id == workspace_id, LeadState.status == "new")))
        view = DigestSettingsView(min_score=row.min_score, max_leads=row.max_leads, last_sent_at=row.last_sent_at)
        return digest_lib.build_digest(states, self._index_for(workspace_id), view, utcnow())

    def send(self, workspace_id: int) -> dict:
        """Send now to every configured channel. A channel that fails does not stop the others."""
        row, digest = self.config(workspace_id), self.preview(workspace_id)
        sent, errors = [], []
        if row.emails and email_ready(self._settings):
            try:
                digest_lib.send_email(self._settings, row.emails, digest)
                sent.append("email")
            except Exception as exc:
                log.warning("Digest email failed", exc_info=True)
                errors.append(f"email: {type(exc).__name__}")
        if row.slack_webhook:
            try:
                digest_lib.send_slack(row.slack_webhook, digest)
                sent.append("slack")
            except Exception as exc:
                log.warning("Digest Slack post failed", exc_info=True)
                errors.append(f"slack: {type(exc).__name__}")
        if not sent and not errors:
            errors.append("no channel configured: add an email address (with SMTP set up) or a Slack webhook")
        with self._sessions() as session:
            stored = self._row(session, workspace_id)
            if sent:
                stored.last_sent_at = utcnow()
            stored.last_result = f"sent {len(digest.leads)} leads via {', '.join(sent)}" if sent else "; ".join(errors)
            session.commit()
        result = {"sent": sent, "count": len(digest.leads), "errors": errors}
        self._bus.publish("digest.sent", result, workspace_id)
        return result

    def send_scheduled(self, workspace_id: int) -> None:
        if not self.preview(workspace_id).leads:
            log.info("Digest for workspace %s skipped: nothing new", workspace_id)
            return
        self.send(workspace_id)
