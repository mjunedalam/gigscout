"""Request and response bodies of the web API. Response models never expose secrets or password hashes."""

from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field

from gigscout.models import AgencyProfile, Lead
from gigscout.platform.security import MIN_PASSWORD_LENGTH

Role = Literal["admin", "member"]
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


class UserCreate(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=120)
    role: Role = "member"
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=200)


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    role: Role | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=MIN_PASSWORD_LENGTH, max_length=200)


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


class LeadPage(BaseModel):
    items: list[LeadView]
    total: int
    page: int
    page_size: int


class LeadUpdate(BaseModel):
    status: LeadStatus | None = None
    notes: str | None = Field(default=None, max_length=5000)


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


class SourceEnabled(BaseModel):
    enabled: bool


class SourceTestResult(BaseModel):
    name: str
    ok: bool
    count: int = 0
    latency_ms: float
    sample: list[str] = []
    error: str | None = None
