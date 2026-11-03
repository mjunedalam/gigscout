"""Relational state for the platform. Leads themselves live in the vector store; this holds everything around them."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
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
