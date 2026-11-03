"""Relational state for the platform. Leads themselves live in the vector store; this holds everything around them."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

ROLES = ("admin", "member")
RUN_STATUSES = ("queued", "running", "succeeded", "failed", "cancelled")
LEAD_STATUSES = ("new", "contacted", "proposal", "won", "lost", "archived")


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSON, list[str]: JSON, datetime: DateTime(timezone=True)}


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(16), default="member")
    password_hash: Mapped[str] = mapped_column(String(300))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(default=None)


class AuthToken(Base):
    __tablename__ = "auth_tokens"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime]


class AgencyProfileRecord(Base):
    __tablename__ = "agency_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    data: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    profile_id: Mapped[int | None] = mapped_column(ForeignKey("agency_profiles.id", ondelete="SET NULL"))
    profile_name: Mapped[str] = mapped_column(String(120))
    mode_requested: Mapped[str] = mapped_column(String(16))
    mode: Mapped[str | None] = mapped_column(String(16), default=None)
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    trigger: Mapped[str] = mapped_column(String(16))  # manual | schedule
    triggered_by: Mapped[str] = mapped_column(String(254))
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    started_at: Mapped[datetime | None] = mapped_column(default=None)
    finished_at: Mapped[datetime | None] = mapped_column(default=None)
    fetched_count: Mapped[int] = mapped_column(Integer, default=0)
    new_count: Mapped[int] = mapped_column(Integer, default=0)
    match_count: Mapped[int] = mapped_column(Integer, default=0)
    top_score: Mapped[float] = mapped_column(Float, default=0.0)
    report: Mapped[str] = mapped_column(Text, default="")
    queries: Mapped[list[str]] = mapped_column(JSON, default=list)
    errors: Mapped[list[str]] = mapped_column(JSON, default=list)
    trace: Mapped[list[str]] = mapped_column(JSON, default=list)
    activity: Mapped[list[dict]] = mapped_column(JSON, default=list)  # structured events, for cockpit replay

    @property
    def duration_seconds(self) -> float | None:
        if self.started_at is None or self.finished_at is None:
            return None
        return (_aware(self.finished_at) - _aware(self.started_at)).total_seconds()


class Schedule(Base):
    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    profile_id: Mapped[int] = mapped_column(ForeignKey("agency_profiles.id", ondelete="CASCADE"))
    cron: Mapped[str] = mapped_column(String(120))
    mode: Mapped[str] = mapped_column(String(16), default="auto")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str] = mapped_column(String(254))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_run_at: Mapped[datetime | None] = mapped_column(default=None)
    last_run_id: Mapped[str | None] = mapped_column(String(36), default=None)


class LeadState(Base):
    """The sales pipeline position of a lead, plus its latest qualification from a run."""

    __tablename__ = "lead_states"

    lead_id: Mapped[str] = mapped_column(String(300), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), default="new", index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    score: Mapped[float | None] = mapped_column(Float, default=None, index=True)
    reasons: Mapped[str] = mapped_column(Text, default="")
    red_flags: Mapped[str] = mapped_column(Text, default="")
    pitch: Mapped[str] = mapped_column(Text, default="")
    last_run_id: Mapped[str | None] = mapped_column(String(36), default=None)
    updated_by: Mapped[str | None] = mapped_column(String(254), default=None)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class Outreach(Base):
    """A message to a lead: drafted, edited, sent (by email, or pasted as a marketplace bid), then tracked."""

    __tablename__ = "outreach"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[str] = mapped_column(String(300), index=True)
    channel: Mapped[str] = mapped_column(String(8))  # email | bid
    to_address: Mapped[str | None] = mapped_column(String(254), default=None)
    subject: Mapped[str] = mapped_column(String(200), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(12), default="draft", index=True)  # draft | sent | replied | no_reply
    source: Mapped[str] = mapped_column(String(12), default="template")  # ai | template
    created_by: Mapped[str] = mapped_column(String(254))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(default=None, index=True)
    sent_by: Mapped[str | None] = mapped_column(String(254), default=None, index=True)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class CrmRecord(Base):
    """A lead pushed to a CRM, so it is never pushed twice."""

    __tablename__ = "crm_links"
    __table_args__ = (UniqueConstraint("lead_id", "crm"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[str] = mapped_column(String(300), index=True)
    crm: Mapped[str] = mapped_column(String(16))
    external_id: Mapped[str] = mapped_column(String(64))
    url: Mapped[str | None] = mapped_column(String(500), default=None)
    created_by: Mapped[str] = mapped_column(String(254))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Connector(Base):
    """A website an admin added as a lead source (name is the source name the agents see)."""

    __tablename__ = "connectors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(60), unique=True)
    label: Mapped[str] = mapped_column(String(120), default="")
    url: Mapped[str] = mapped_column(String(500))
    kind: Mapped[str] = mapped_column(String(8))  # feed | page
    lead_kind: Mapped[str] = mapped_column(String(16), default="project")  # what its listings are: project | hiring…
    feed_url: Mapped[str | None] = mapped_column(String(500), default=None)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(16), default="ok")  # ok | blocked | error
    last_error: Mapped[str | None] = mapped_column(Text, default=None)
    checked_at: Mapped[datetime | None] = mapped_column(default=None)
    created_by: Mapped[str] = mapped_column(String(254))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class SourceToggle(Base):
    """A built-in source an admin switched off (or back on). No row means on."""

    __tablename__ = "source_toggles"

    name: Mapped[str] = mapped_column(String(60), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class DigestSettings(Base):
    """The daily digest's configuration: a single row (id=1)."""

    __tablename__ = "digest_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    hour: Mapped[int] = mapped_column(Integer, default=8)  # local hour (Settings.timezone) it is sent at
    emails: Mapped[list[str]] = mapped_column(JSON, default=list)
    slack_webhook: Mapped[str | None] = mapped_column(Text, default=None)
    min_score: Mapped[float] = mapped_column(Float, default=0.6)
    max_leads: Mapped[int] = mapped_column(Integer, default=10)
    last_sent_at: Mapped[datetime | None] = mapped_column(default=None)
    last_result: Mapped[str] = mapped_column(Text, default="")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    actor: Mapped[str] = mapped_column(String(254))
    action: Mapped[str] = mapped_column(String(64))
    target: Mapped[str] = mapped_column(String(300), default="")
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


def _aware(value: datetime) -> datetime:
    """SQLite drops tzinfo on read; every timestamp we write is UTC."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)
