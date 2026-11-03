"""Daily digest settings, scheduling and delivery (the content itself is built in gigscout.digest)."""

import logging

from sqlalchemy import select

from gigscout import digest as digest_lib
from gigscout.config import Settings
from gigscout.digest import Digest, DigestSettingsView
from gigscout.platform.db import SessionFactory
from gigscout.platform.events import EventBus
from gigscout.platform.scheduler import ScheduleManager
from gigscout.platform.tables import DigestSettings, LeadState, utcnow
from gigscout.store.vector_store import LeadIndex

log = logging.getLogger(__name__)

JOB_ID = "digest"
EDITABLE = ("enabled", "hour", "emails", "min_score", "max_leads")


class DigestManager:
    def __init__(self, sessions: SessionFactory, index: LeadIndex, settings: Settings, bus: EventBus,
                 schedules: ScheduleManager) -> None:
        self._sessions = sessions
        self._index = index
        self._settings = settings
        self._bus = bus
        self._schedules = schedules

    def config(self) -> DigestSettings:
        with self._sessions() as session:
            row = session.get(DigestSettings, 1)
            if row is None:
                row = DigestSettings(id=1)
                session.add(row)
                session.commit()
            return row

    def save(self, change: dict) -> DigestSettings:
        """slack_webhook: None keeps the saved one, "" clears it, anything else must be a Slack webhook URL."""
        webhook = change.get("slack_webhook")
        checked = digest_lib.check_slack_webhook(webhook) if webhook else webhook
        with self._sessions() as session:
            row = session.get(DigestSettings, 1) or DigestSettings(id=1)
            for field in EDITABLE:
                setattr(row, field, change[field])
            if checked is not None:
                row.slack_webhook = checked or None
            session.merge(row)
            session.commit()
        self.sync()
        return self.config()

    def sync(self) -> None:
        row = self.config()
        self._schedules.set_daily(JOB_ID, row.hour if row.enabled else None, self.send_scheduled)

    def preview(self) -> Digest:
        row = self.config()
        with self._sessions() as session:
            states = list(session.scalars(select(LeadState).where(LeadState.status == "new")))
        view = DigestSettingsView(min_score=row.min_score, max_leads=row.max_leads, last_sent_at=row.last_sent_at)
        return digest_lib.build_digest(states, self._index, view, utcnow())

    def send(self) -> dict:
        """Send now to every configured channel. A channel that fails does not stop the others."""
        row, digest = self.config(), self.preview()
        sent, errors = [], []
        if row.emails and digest_lib.email_ready(self._settings):
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
            stored = session.get(DigestSettings, 1)
            if sent:
                stored.last_sent_at = utcnow()
            stored.last_result = f"sent {len(digest.leads)} leads via {', '.join(sent)}" if sent else "; ".join(errors)
            session.commit()
        result = {"sent": sent, "count": len(digest.leads), "errors": errors}
        self._bus.publish("digest.sent", result)
        return result

    def send_scheduled(self) -> None:
        if not self.preview().leads:
            log.info("Digest skipped: nothing new")
            return
        self.send()
