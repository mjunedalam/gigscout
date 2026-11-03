"""Domain models. All are frozen: nodes return new objects instead of mutating shared state."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    """The company the agents prospect for: any kind of business that sells services or work to clients."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(default="our agency", min_length=1, max_length=120)
    company_type: str = Field(default="Software agency", min_length=1, max_length=80,
                              description="What kind of company this is, e.g. Marketing agency, Law firm")
    pitch: str = Field(default="", max_length=2000, description="What the company does, in a few sentences")
    services: tuple[str, ...] = ()
    skills: tuple[str, ...] = Field(default=(), description="Capabilities: tech stack, specialities, certifications")
    keywords: tuple[str, ...] = ()
    industries: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    min_budget_usd: float | None = Field(default=None, ge=0)
    target_countries: tuple[str, ...] = Field(default=(), description="Empty = any country")
    kinds: tuple[LeadKind, ...] = ALL_LEAD_KINDS
    sources: tuple[str, ...] | None = Field(default=None, description="None = all enabled sources")

    @model_validator(mode="after")
    def _says_what_it_sells(self) -> "AgencyProfile":
        if not (self.services or self.skills or self.keywords):
            raise ValueError("Describe what you sell: add at least one service, capability or search keyword")
        return self

    def who(self) -> str:
        """How prompts name the company, e.g. 'Marketing agency "Bright Lane"'."""
        return f'{self.company_type} "{self.name}"'

    def as_query(self) -> str:
        """Natural-language description used for semantic retrieval."""
        parts = [f"Company type: {self.company_type}", self.pitch]
        if self.services:
            parts.append("Services: " + ", ".join(self.services))
        if self.skills:
            parts.append("Capabilities: " + ", ".join(self.skills))
        if self.industries:
            parts.append("Industries: " + ", ".join(self.industries))
        if self.keywords:
            parts.append("Looking for: " + ", ".join(self.keywords))
        return "\n".join(p for p in parts if p)


class ProfileSuggestion(BaseModel):
    """What the LLM proposes when a company describes itself in a sentence."""

    services: list[str] = Field(default_factory=list, description="3-6 services the company sells, short phrases")
    skills: list[str] = Field(default_factory=list, description="3-8 capabilities or specialities, short phrases")
    keywords: list[str] = Field(
        default_factory=list, description="4-8 short search queries (1-3 words) for finding clients"
    )
    exclude: list[str] = Field(default_factory=list, description="2-5 topics to never show (unpaid, off-target work)")
    industries: list[str] = Field(default_factory=list, description="0-4 client industries it serves best")


class LeadAssessment(BaseModel):
    """What the LLM qualifier returns for one lead."""

    score: float = Field(ge=0, le=1, description="0 = not worth pursuing, 1 = ideal client project")
    reasons: str = Field(description="One or two sentences on why")
    red_flags: str = Field(default="", description="Scam signals, unrealistic budget, vague scope")
    pitch: str = Field(default="", description="One-line outreach angle the company could open with")


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
