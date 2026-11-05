"""Relational state for the platform. Leads themselves live in the vector store; this holds everything around them."""

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

ROLES = ("admin", "member")  # platform-wide: an admin runs the whole installation and every workspace
# within one workspace: owners and admins manage it, members work leads and start runs, viewers only look
WORKSPACE_ROLES = ("owner", "admin", "member", "viewer")
DEFAULT_WORKSPACE = 1  # existing data and env-configured inbound channels (Google Ads, Typeform, Meta) land here
WS = "workspaces.id"
RUN_STATUSES = ("queued", "running", "succeeded", "failed", "cancelled")
LEAD_STATUSES = ("new", "contacted", "proposal", "won", "lost", "archived")
AGENT_AUTHOR = "GigScout agents"  # created_by on pitches the agents drafted on their own


def utcnow() -> datetime:
    return datetime.now(UTC)


def workspace_fk(**kwargs: Any) -> Any:
    return mapped_column(ForeignKey(WS, ondelete="CASCADE"), default=DEFAULT_WORKSPACE, **kwargs)


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
    # the workspace that created this account: only its admins may change the account itself (password, name,
    # active), and only while it belongs nowhere else. None (bootstrap and older accounts): platform admins only.
    home_workspace_id: Mapped[int | None] = mapped_column(ForeignKey(WS, ondelete="SET NULL"), default=None)


class Workspace(Base):
    """One company using GigScout: its own leads, profiles, runs, sources, settings and members."""

    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    form_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # its website form's webhook key
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Membership(Base):
    __tablename__ = "memberships"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey(WS, ondelete="CASCADE"), primary_key=True)
    role: Mapped[str] = mapped_column(String(16), default="member")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Subscription(Base):
    """A workspace's Stripe subscription, as Stripe last reported it. No row: it never subscribed (trial)."""

    __tablename__ = "subscriptions"

    workspace_id: Mapped[int] = workspace_fk(primary_key=True)
    plan: Mapped[str] = mapped_column(String(16), default="trial")
    status: Mapped[str] = mapped_column(String(24), default="incomplete")
    stripe_customer_id: Mapped[str | None] = mapped_column(String(64), default=None, index=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(64), default=None, index=True)
    current_period_end: Mapped[datetime | None] = mapped_column(default=None)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class AuthToken(Base):
    __tablename__ = "auth_tokens"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime]


class AgencyProfileRecord(Base):
    __tablename__ = "agency_profiles"

    workspace_id: Mapped[int] = workspace_fk(index=True)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    data: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class Run(Base):
    __tablename__ = "runs"

    workspace_id: Mapped[int] = workspace_fk(index=True)
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

    workspace_id: Mapped[int] = workspace_fk(index=True)
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

    workspace_id: Mapped[int] = workspace_fk(primary_key=True)
    lead_id: Mapped[str] = mapped_column(String(300), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), default="new", index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    score: Mapped[float | None] = mapped_column(Float, default=None, index=True)
    reasons: Mapped[str] = mapped_column(Text, default="")
    red_flags: Mapped[str] = mapped_column(Text, default="")
    pitch: Mapped[str] = mapped_column(Text, default="")
    base_score: Mapped[float | None] = mapped_column(Float, default=None)  # the agents' score, before learning
    learned: Mapped[float] = mapped_column(Float, default=0.0)  # nudge from won/lost leads (score = base + learned)
    learned_note: Mapped[str] = mapped_column(Text, default="")
    score_parts: Mapped[list[dict] | None] = mapped_column(JSON, default=None)  # how the agents' score was built
    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), default=None,
                                                    index=True)  # who on the team owns the lead
    follow_up_on: Mapped[date | None] = mapped_column(Date, default=None, index=True)
    deal_value_usd: Mapped[float | None] = mapped_column(Float, default=None)  # what a won lead is worth
    last_run_id: Mapped[str | None] = mapped_column(String(36), default=None)
    updated_by: Mapped[str | None] = mapped_column(String(254), default=None)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class Outreach(Base):
    """A message to a lead: drafted, edited, sent (by email, or pasted as a marketplace bid), then tracked."""

    __tablename__ = "outreach"

    workspace_id: Mapped[int] = workspace_fk(index=True)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[str] = mapped_column(String(300), index=True)
    channel: Mapped[str] = mapped_column(String(8))  # email | bid
    to_address: Mapped[str | None] = mapped_column(String(254), default=None)
    subject: Mapped[str] = mapped_column(String(200), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    # draft (waiting for a person to approve) | rejected | sent | replied | no_reply
    status: Mapped[str] = mapped_column(String(12), default="draft", index=True)
    source: Mapped[str] = mapped_column(String(12), default="template")  # ai | template
    kind: Mapped[str] = mapped_column(String(12), default="first")  # first | follow_up
    run_id: Mapped[str | None] = mapped_column(String(36), default=None)  # set when the agents drafted it
    created_by: Mapped[str] = mapped_column(String(254))  # a person's email, or AGENT_AUTHOR
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(default=None, index=True)
    sent_by: Mapped[str | None] = mapped_column(String(254), default=None, index=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(254), default=None)  # who approved or rejected it
    reviewed_at: Mapped[datetime | None] = mapped_column(default=None)
    review_note: Mapped[str] = mapped_column(Text, default="")  # why it was rejected
    evidence: Mapped[list[dict] | None] = mapped_column(JSON, default=None)  # the company documents it drew on
    claims: Mapped[list[dict] | None] = mapped_column(JSON, default=None)  # its claims, and whether they are backed
    message_id: Mapped[str | None] = mapped_column(String(255), default=None, index=True)  # the sent email's id
    in_reply_to: Mapped[str | None] = mapped_column(String(255), default=None)  # for an answer: the client's email
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class CrmRecord(Base):
    """A lead pushed to a CRM, so it is never pushed twice."""

    __tablename__ = "crm_links"
    __table_args__ = (UniqueConstraint("workspace_id", "lead_id", "crm"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = workspace_fk(index=True)
    lead_id: Mapped[str] = mapped_column(String(300), index=True)
    crm: Mapped[str] = mapped_column(String(16))
    external_id: Mapped[str] = mapped_column(String(64))
    url: Mapped[str | None] = mapped_column(String(500), default=None)
    created_by: Mapped[str] = mapped_column(String(254))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class IntegrationToken(Base):
    """An account connected by OAuth (e.g. Upwork). Tokens are stored encrypted."""

    __tablename__ = "integration_tokens"

    workspace_id: Mapped[int] = workspace_fk(primary_key=True)
    name: Mapped[str] = mapped_column(String(32), primary_key=True)
    access_token: Mapped[str] = mapped_column(Text)
    refresh_token: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    connected_by: Mapped[str] = mapped_column(String(254))
    connected_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow)


class Connector(Base):
    """A website an admin added as a lead source (name is the source name the agents see)."""

    __tablename__ = "connectors"
    __table_args__ = (UniqueConstraint("workspace_id", "name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = workspace_fk(index=True)
    name: Mapped[str] = mapped_column(String(60))
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

    workspace_id: Mapped[int] = workspace_fk(primary_key=True)
    name: Mapped[str] = mapped_column(String(60), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class PitchSettings(Base):
    """A workspace's pitch autopilot: what the agents draft on their own, and who must approve before it goes out."""

    __tablename__ = "pitch_settings"

    workspace_id: Mapped[int] = workspace_fk(primary_key=True)
    auto_draft: Mapped[bool] = mapped_column(Boolean, default=False)  # draft pitches for the best leads of each run
    min_score: Mapped[float] = mapped_column(Float, default=0.7)
    max_per_run: Mapped[int] = mapped_column(Integer, default=5)
    follow_up_days: Mapped[int] = mapped_column(Integer, default=0)  # draft a follow-up after this much silence; 0 off
    require_admin: Mapped[bool] = mapped_column(Boolean, default=False)  # only owners and admins approve
    updated_by: Mapped[str] = mapped_column(String(254), default="")
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class DigestSettings(Base):
    """A workspace's daily digest configuration: one row per workspace."""

    __tablename__ = "digest_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = workspace_fk(unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    hour: Mapped[int] = mapped_column(Integer, default=8)  # local hour (Settings.timezone) it is sent at
    emails: Mapped[list[str]] = mapped_column(JSON, default=list)
    slack_webhook: Mapped[str | None] = mapped_column(Text, default=None)
    min_score: Mapped[float] = mapped_column(Float, default=0.6)
    max_leads: Mapped[int] = mapped_column(Integer, default=10)
    last_sent_at: Mapped[datetime | None] = mapped_column(default=None)
    last_result: Mapped[str] = mapped_column(Text, default="")


class Competitor(Base):
    """A company the workspace competes with; its public contract wins are watched."""

    __tablename__ = "competitors"
    __table_args__ = (UniqueConstraint("workspace_id", "name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = workspace_fk(index=True)
    name: Mapped[str] = mapped_column(String(120))
    created_by: Mapped[str] = mapped_column(String(254))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class CompetitorWin(Base):
    """A public contract a competitor won (from an award notice)."""

    __tablename__ = "competitor_wins"
    __table_args__ = (UniqueConstraint("competitor_id", "notice_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = workspace_fk(index=True)
    competitor_id: Mapped[int] = mapped_column(ForeignKey("competitors.id", ondelete="CASCADE"), index=True)
    notice_id: Mapped[str] = mapped_column(String(80))
    supplier: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(300))
    buyer: Mapped[str] = mapped_column(String(200), default="")
    amount: Mapped[float | None] = mapped_column(Float, default=None)
    currency: Mapped[str | None] = mapped_column(String(8), default=None)
    awarded_at: Mapped[datetime | None] = mapped_column(default=None, index=True)
    url: Mapped[str] = mapped_column(String(300), default="")
    found_at: Mapped[datetime] = mapped_column(default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    workspace_id: Mapped[int] = workspace_fk(index=True)
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    actor: Mapped[str] = mapped_column(String(254))
    action: Mapped[str] = mapped_column(String(64))
    target: Mapped[str] = mapped_column(String(300), default="")
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


def _aware(value: datetime) -> datetime:
    """SQLite drops tzinfo on read; every timestamp we write is UTC."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


class LeadEvent(Base):
    """When a lead first reached a pipeline step, and who (or which agent) moved it there. One row per step."""

    __tablename__ = "lead_events"
    __table_args__ = (UniqueConstraint("workspace_id", "lead_id", "stage"),)

    workspace_id: Mapped[int] = workspace_fk(index=True)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[str] = mapped_column(String(300), index=True)
    stage: Mapped[str] = mapped_column(String(16), index=True)
    at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    actor: Mapped[str] = mapped_column(String(254), default="")


class KnowledgeDoc(Base):
    """One of the company's own documents (case study, past proposal, portfolio, rates). Its text is chunked into
    the workspace's knowledge collection; pitches cite it and are checked against it."""

    __tablename__ = "knowledge_docs"

    workspace_id: Mapped[int] = workspace_fk(index=True)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(16), default="other")
    text: Mapped[str] = mapped_column(Text)
    chunks: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str] = mapped_column(String(254))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Reply(Base):
    """A client's answer to one of our messages: read from the mailbox or pasted in, with what it means."""

    __tablename__ = "replies"
    __table_args__ = (UniqueConstraint("workspace_id", "message_id"),)

    workspace_id: Mapped[int] = workspace_fk(index=True)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    outreach_id: Mapped[int | None] = mapped_column(ForeignKey("outreach.id", ondelete="SET NULL"), default=None)
    lead_id: Mapped[str] = mapped_column(String(300), index=True)
    from_address: Mapped[str | None] = mapped_column(String(254), default=None)
    subject: Mapped[str] = mapped_column(String(300), default="")
    body: Mapped[str] = mapped_column(Text)
    message_id: Mapped[str | None] = mapped_column(String(255), default=None)  # dedupes mailbox re-reads
    source: Mapped[str] = mapped_column(String(8), default="email")  # email | pasted
    intent: Mapped[str] = mapped_column(String(16), index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    read_by: Mapped[str] = mapped_column(String(8), default="rules")  # ai | rules
    answer_id: Mapped[int | None] = mapped_column(ForeignKey("outreach.id", ondelete="SET NULL"), default=None)
    received_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    handled_by: Mapped[str | None] = mapped_column(String(254), default=None)
    handled_at: Mapped[datetime | None] = mapped_column(default=None, index=True)
