"""Domain models. All are frozen: nodes return new objects instead of mutating shared state."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# project  = a client posted a project to outsource (freelance marketplaces, RFP/tender feeds)
# contract = a company wants contractors (staff augmentation opportunity)
# hiring   = a company is hiring full-time devs (a buying signal: they may outsource instead)
# inbound  = a prospect contacted the agency directly (e.g. a Google Ads lead form)
LeadKind = Literal["project", "contract", "hiring", "inbound"]
ALL_LEAD_KINDS: tuple[LeadKind, ...] = ("project", "contract", "hiring", "inbound")


class Budget(BaseModel):
    model_config = ConfigDict(frozen=True)

    minimum: float | None = None
    maximum: float | None = None
    currency: str | None = None
    usd_rate: float | None = Field(default=None, description="Multiply by this to convert to USD")
    kind: Literal["fixed", "hourly", "salary", "unknown"] = "unknown"

    @property
    def max_usd(self) -> float | None:
        value = self.maximum if self.maximum is not None else self.minimum
        if value is None:
            return None
        if self.currency == "USD" or self.currency is None:
            return value
        return value * self.usd_rate if self.usd_rate else None


class Client(BaseModel):
    """Who is buying. Marketplaces hide most of this; inbound leads fill it in."""

    model_config = ConfigDict(frozen=True)

    name: str | None = None
    country: str | None = None
    email: str | None = None
    phone: str | None = None


class Lead(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(description="Globally unique: '<source>:<native id>'")
    source: str
    title: str
    description: str
    url: str
    kind: LeadKind = "project"
    skills: tuple[str, ...] = ()
    budget: Budget | None = None
    posted_at: datetime | None = None
    client: Client | None = None
    bid_count: int | None = Field(default=None, ge=0, description="Competing proposals already submitted")

    def document(self) -> str:
        """Text that gets embedded into the vector store."""
        skills = ", ".join(self.skills)
        return f"{self.title}\nSkills: {skills}\n{self.description}"


class AgencyProfile(BaseModel):
    """The software company the agent prospects for."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(default="our agency", min_length=1, max_length=120)
    pitch: str = Field(default="", max_length=2000, description="What the agency does, in a few sentences")
    services: tuple[str, ...] = ()
    skills: tuple[str, ...] = Field(min_length=1, description="Tech stack the team delivers in")
    keywords: tuple[str, ...] = ()
    industries: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    min_budget_usd: float | None = Field(default=None, ge=0)
    target_countries: tuple[str, ...] = Field(default=(), description="Empty = any country")
    kinds: tuple[LeadKind, ...] = ALL_LEAD_KINDS
    sources: tuple[str, ...] | None = Field(default=None, description="None = all enabled sources")

    def as_query(self) -> str:
        """Natural-language description used for semantic retrieval."""
        parts = [self.pitch]
        if self.services:
            parts.append("Services: " + ", ".join(self.services))
        parts.append("Tech stack: " + ", ".join(self.skills))
        if self.industries:
            parts.append("Industries: " + ", ".join(self.industries))
        if self.keywords:
            parts.append("Looking for: " + ", ".join(self.keywords))
        return "\n".join(p for p in parts if p)


class LeadAssessment(BaseModel):
    """What the LLM qualifier returns for one lead."""

    score: float = Field(ge=0, le=1, description="0 = not worth pursuing, 1 = ideal client project")
    reasons: str = Field(description="One or two sentences on why")
    red_flags: str = Field(default="", description="Scam signals, unrealistic budget, vague scope")
    pitch: str = Field(default="", description="One-line outreach angle the agency could open with")


class Candidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    lead: Lead
    similarity: float


class ScoredLead(BaseModel):
    model_config = ConfigDict(frozen=True)

    lead: Lead
    similarity: float
    score: float
    reasons: str = ""
    red_flags: str = ""
    pitch: str = ""


class ScoutResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    queries: tuple[str, ...]
    iterations: int
    fetched_count: int
    new_count: int
    errors: tuple[str, ...]
    matches: tuple[ScoredLead, ...]
    report: str
    mode: Literal["pipeline", "team"] = "pipeline"
    trace: tuple[str, ...] = Field(default=(), description="Team mode: who did what, in order")
