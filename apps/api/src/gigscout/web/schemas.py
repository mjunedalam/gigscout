"""Request and response bodies of the web API. Response models never expose secrets or password hashes."""

from datetime import UTC, date, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field

from gigscout.models import AgencyProfile, Lead
from gigscout.platform.security import MIN_PASSWORD_LENGTH

Role = Literal["admin", "member"]  # platform-wide
WorkspaceRole = Literal["owner", "admin", "member", "viewer"]
LeadStatus = Literal["new", "contacted", "proposal", "won", "lost", "archived"]
RunMode = Literal["auto", "team", "pipeline"]

# SQLite returns naive datetimes; every timestamp we store is UTC, so say so on the way out.
UtcDatetime = Annotated[datetime, AfterValidator(lambda v: v if v.tzinfo else v.replace(tzinfo=UTC))]


class Orm(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- auth & users -----------------------------------------------------------------------------------------------
class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)  # not EmailStr: internal domains must still sign in
    password: str = Field(min_length=1, max_length=200)


class UserOut(Orm):
    id: int
    email: str
    name: str
    role: Role
    is_active: bool
    created_at: UtcDatetime
    last_login_at: UtcDatetime | None


class WorkspaceOut(BaseModel):
    id: int
    name: str
    role: WorkspaceRole


class MeOut(UserOut):
    workspaces: list[WorkspaceOut]


class MemberOut(BaseModel):
    """A user as a member of the current workspace; `role` is their role here."""

    id: int
    email: str
    name: str
    role: WorkspaceRole
    platform_admin: bool
    is_active: bool
    created_at: UtcDatetime
    last_login_at: UtcDatetime | None


class UserCreate(BaseModel):
    """Add someone to the workspace. A new email creates the account (password required); an existing one is
    simply added (its password is left alone)."""

    email: EmailStr
    name: str = Field(min_length=1, max_length=120)
    role: WorkspaceRole = "member"
    password: str | None = Field(default=None, min_length=MIN_PASSWORD_LENGTH, max_length=200)


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    role: WorkspaceRole | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=MIN_PASSWORD_LENGTH, max_length=200)


class PlanOut(BaseModel):
    id: str
    label: str
    price: str | None  # as Stripe has it, e.g. "$49/month"
    members: int
    runs_per_month: int


class BillingOut(BaseModel):
    enabled: bool  # False: self-hosted without Stripe, nothing is limited
    plan: str
    status: str
    can_work: bool
    reason: str
    trial_ends_at: UtcDatetime | None
    current_period_end: UtcDatetime | None
    members_limit: int | None
    runs_limit: int | None
    members: int
    runs_this_month: int
    plans: list[PlanOut]
    can_manage: bool  # has a Stripe customer, so the portal can open


class CheckoutIn(BaseModel):
    plan: Literal["starter", "growth"]


class SetupStep(BaseModel):
    id: str
    label: str
    help: str
    href: str
    done: bool
    admin_only: bool  # members see it, but only owners and admins can do it


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class WorkspaceDetail(BaseModel):
    id: int
    name: str
    role: WorkspaceRole
    form_path: str | None = None  # admins only: the website form webhook path, which carries the secret key
    members: int


# --- agency profiles --------------------------------------------------------------------------------------------
class ProfileOut(Orm):
    id: int
    name: str
    data: AgencyProfile
    created_at: UtcDatetime
    updated_at: UtcDatetime


# --- leads ------------------------------------------------------------------------------------------------------
class LeadView(BaseModel):
    lead: Lead
    seen_at: UtcDatetime | None = None
    status: LeadStatus = "new"
    notes: str = ""
    score: float | None = None
    reasons: str = ""
    red_flags: str = ""
    pitch: str = ""
    similarity: float | None = None
    learned: float = 0.0  # how much won/lost leads moved the score
    learned_note: str = ""
    score_parts: list[dict] | None = None  # how the agents' score was built (see ScorePart)
    assigned_to: int | None = None
    assignee: str | None = None  # their name
    follow_up_on: date | None = None
    deal_value_usd: float | None = None


class LeadPage(BaseModel):
    items: list[LeadView]
    total: int
    page: int
    page_size: int


class LeadUpdate(BaseModel):
    """Only the fields sent change. assigned_to and follow_up_on can be sent as null to clear them."""

    status: LeadStatus | None = None
    notes: str | None = Field(default=None, max_length=5000)
    assigned_to: int | None = None
    follow_up_on: date | None = None
    deal_value_usd: float | None = Field(default=None, ge=0, le=1_000_000_000)


class MemberName(BaseModel):
    id: int
    name: str
    hint: str  # tells same-named people apart: the email for admins, masked ("a•••@acme.com") for everyone else


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    k: int = Field(default=8, ge=1, le=30)


class AskResponse(BaseModel):
    answer: str
    sources: list[LeadView]


# --- runs & schedules -------------------------------------------------------------------------------------------
class RunCreate(BaseModel):
    profile_id: int
    mode: RunMode = "auto"


class RunOut(Orm):
    id: str
    profile_id: int | None
    profile_name: str
    mode_requested: str
    mode: str | None
    status: str
    trigger: str
    triggered_by: str
    created_at: UtcDatetime
    started_at: UtcDatetime | None
    finished_at: UtcDatetime | None
    duration_seconds: float | None
    fetched_count: int
    new_count: int
    match_count: int
    top_score: float
    errors: list[str]


class RunDetail(RunOut):
    report: str
    queries: list[str]
    trace: list[str]


class ScheduleIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    profile_id: int
    cron: str = Field(min_length=9, max_length=120, examples=["0 */2 * * *"])
    mode: RunMode = "auto"
    enabled: bool = True


class ScheduleOut(Orm):
    id: int
    name: str
    profile_id: int
    cron: str
    mode: str
    enabled: bool
    created_by: str
    created_at: UtcDatetime
    last_run_at: UtcDatetime | None
    last_run_id: str | None
    next_run_at: UtcDatetime | None = None


class CronPreview(BaseModel):
    cron: str
    valid: bool
    error: str | None = None
    next_runs: list[UtcDatetime] = []


# --- admin ------------------------------------------------------------------------------------------------------
class AuditOut(Orm):
    id: int
    at: UtcDatetime
    actor: str
    action: str
    target: str
    detail: dict


class SourceHealth(BaseModel):
    name: str
    channel: Literal["pull", "push"]
    enabled: bool
    recent_failures: int
    last_error: str | None = None
    custom: bool = False  # a website an admin added
    id: int | None = None
    label: str | None = None
    url: str | None = None
    kind: Literal["feed", "page"] | None = None
    status: Literal["ok", "blocked", "error"] | None = None
    lead_kind: str | None = None
    bot_check: bool | None = None  # website form only: Cloudflare Turnstile is on
    site_key: str | None = None  # the public Turnstile site key, for the form snippet


class ProfileSuggestRequest(BaseModel):
    company_type: str = Field(min_length=2, max_length=80)
    description: str = Field(default="", max_length=1000)


class ProfileSuggestOut(BaseModel):
    source: Literal["ai", "template", "none"]  # where the suggestion came from
    services: list[str]
    skills: list[str]
    keywords: list[str]
    exclude: list[str]
    industries: list[str]


class DigestConfigIn(BaseModel):
    enabled: bool
    hour: int = Field(ge=0, le=23)
    emails: list[EmailStr] = Field(default_factory=list, max_length=20)
    slack_webhook: str | None = Field(default=None, max_length=300, description="None keeps the saved one; '' clears")
    min_score: float = Field(ge=0, le=1)
    max_leads: int = Field(ge=1, le=50)


class DigestConfigOut(BaseModel):
    enabled: bool
    hour: int
    timezone: str
    emails: list[str]
    slack_configured: bool  # the webhook itself is a secret and is never returned
    min_score: float
    max_leads: int
    last_sent_at: UtcDatetime | None
    last_result: str
    email_ready: bool  # SMTP is configured on the server


class ConnectorCreate(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    url: str = Field(min_length=8, max_length=500)
    lead_kind: Literal["project", "contract", "hiring"] = "project"


class LibraryEntryOut(BaseModel):
    name: str
    url: str
    description: str
    region: str
    lead_kind: str
    company_types: list[str]
    added: bool  # already connected


class SourceEnabled(BaseModel):
    enabled: bool


class SourceTestResult(BaseModel):
    name: str
    ok: bool
    count: int = 0
    latency_ms: float
    sample: list[str] = []
    error: str | None = None


def _single_line(value: str) -> str:
    if "\r" in value or "\n" in value:
        raise ValueError("must be a single line")
    return value


class OutreachCreate(BaseModel):
    lead_id: str = Field(min_length=3, max_length=300)
    profile_id: int | None = None  # whose voice; default: the first company profile


class OutreachUpdate(BaseModel):
    channel: Literal["email", "bid"]
    to: EmailStr | None = None
    subject: Annotated[str, AfterValidator(_single_line)] = Field(default="", max_length=200)
    body: str = Field(min_length=1, max_length=5000)


class OutreachStatusIn(BaseModel):
    status: Literal["replied", "no_reply"]


class OutreachOut(BaseModel):
    id: int
    lead_id: str
    channel: Literal["email", "bid"]
    to: str | None
    subject: str
    body: str
    status: Literal["draft", "rejected", "sent", "replied", "no_reply"]
    source: Literal["ai", "template"]
    kind: Literal["first", "follow_up", "answer"] = "first"
    run_id: str | None = None
    created_by: str
    created_at: UtcDatetime
    sent_at: UtcDatetime | None
    reviewed_by: str | None = None
    reviewed_at: UtcDatetime | None = None
    review_note: str = ""
    evidence: list[dict] | None = None  # the company documents the draft drew on
    claims: list[dict] | None = None  # each claim, and whether those documents back it


class OutreachRejectIn(BaseModel):
    note: str = Field(default="", max_length=500)


class PitchSettingsIO(BaseModel):
    auto_draft: bool = False
    min_score: float = Field(default=0.7, ge=0, le=1)
    max_per_run: int = Field(default=5, ge=1, le=25)
    follow_up_days: int = Field(default=0, ge=0, le=60)
    require_admin: bool = False
    research_first: bool = False  # the research agent reads each client's website before the pitch is written


class PitchLeadOut(BaseModel):
    id: str
    title: str
    url: str
    source: str
    kind: str
    client_name: str | None = None
    status: str = "new"


class PitchItemOut(BaseModel):
    outreach: OutreachOut
    lead: PitchLeadOut
    score: float | None = None
    reasons: str = ""
    can_approve: bool


class PitchListOut(BaseModel):
    items: list[PitchItemOut]
    can_approve: bool


class PitchSummaryOut(BaseModel):
    pending: int
    auto_draft: bool
    can_approve: bool


class OutreachConfigOut(BaseModel):
    email_ready: bool
    crms: list[str]


class CrmSyncIn(BaseModel):
    lead_id: str = Field(min_length=3, max_length=300)


class CrmLinkOut(BaseModel):
    crm: str
    external_id: str
    url: str | None
    created_at: UtcDatetime


class CrmSyncOut(BaseModel):
    links: list[CrmLinkOut]
    errors: list[str] = Field(default_factory=list)


class LearningSignalOut(BaseModel):
    label: str
    wins: int
    total: int
    lift: float
    explain: str


class LearningOut(BaseModel):
    active: bool
    outcomes: int
    wins: int
    losses: int
    needed: int  # outcomes before learning starts
    base_rate: float
    signals: list[LearningSignalOut]


class IntegrationStatusOut(BaseModel):
    configured: bool  # keys are in .env
    connected: bool  # an admin signed in
    connected_by: str | None
    connected_at: UtcDatetime | None
