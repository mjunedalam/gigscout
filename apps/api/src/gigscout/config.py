"""Runtime configuration, loaded from environment variables / `.env` (prefix GIGSCOUT_)."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from gigscout.models import LeadKind


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GIGSCOUT_", env_file=".env", extra="ignore")

    data_dir: Path = Path("data")

    # LLM ("the brain") — any Ollama model; "none" runs the agent with heuristics only.
    llm_provider: Literal["ollama", "none"] = "ollama"
    llm_model: str = "qwen3:8b"
    ollama_base_url: str = "http://localhost:11434"
    llm_grade_limit: int = Field(default=10, ge=0, description="How many top candidates the LLM qualifies")

    # Vector memory
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    collection_name: str = "leads"
    max_lead_age_days: int = Field(default=14, ge=1)

    # Experiment tracking
    mlflow_enabled: bool = True
    mlflow_tracking_uri: str = "sqlite:///data/mlflow.db"
    mlflow_experiment: str = "gigscout"

    # Polite HTTP
    user_agent: str = "gigscout/0.2 (agency lead scout)"
    http_timeout: float = 20.0
    http_min_interval: float = Field(default=1.0, ge=0, description="Seconds between calls to one host")
    http_max_retries: int = Field(default=3, ge=1)

    # Agent loop
    per_query_limit: int = Field(default=25, ge=1)
    top_k: int = Field(default=25, ge=1)
    min_good_matches: int = Field(default=5, ge=0)
    good_match_threshold: float = Field(default=0.6, ge=0, le=1)
    max_iterations: int = Field(default=2, ge=1)

    # Multi-agent team guardrails (ReAct loops must be bounded)
    team_max_searches: int = Field(default=12, ge=1, description="Source searches the scout may run per run")
    team_recursion_limit: int = Field(default=30, ge=5, description="Max ReAct steps for the supervisor")
    worker_recursion_limit: int = Field(default=40, ge=5, description="Max ReAct steps per specialist delegation")
    shortlist_size: int = Field(default=10, ge=1)

    # Extra RSS/Atom feeds (RFP/tender portals, niche boards) and what kind of lead they carry
    rss_feeds: list[str] = Field(default_factory=list)
    rss_feeds_kind: LeadKind = "project"

    # US federal tenders (SAM.gov): a free key from https://api.data.gov/signup. Unset = SAM.gov off.
    # UK Contracts Finder, Find a Tender and EU TED need no key and are always available.
    sam_gov_api_key: SecretStr | None = None

    # Email for the daily digest (any SMTP server: Gmail, Outlook, SES, Postmark...). Unset host = email off.
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_user: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from: str | None = Field(default=None, description="Sender address, e.g. GigScout <scout@your-agency.com>")
    smtp_starttls: bool = True

    # CRM sync: leads are pushed as deals. HubSpot private-app token (scope crm.objects.deals.write) and/or a
    # Pipedrive personal API token. Unset = that CRM is off.
    hubspot_token: SecretStr | None = None
    pipedrive_token: SecretStr | None = None

    # Inbound leads from Google Ads lead form assets (webhook). Unset = webhook disabled.
    google_ads_webhook_key: SecretStr | None = None

    # Platform: users, runs, schedules and lead pipeline state (SQLite by default)
    database_url: str | None = Field(default=None, description="Default: sqlite in data_dir")
    session_ttl_hours: int = Field(default=168, ge=1)
    cookie_secure: bool = Field(default=False, description="Set true when served over HTTPS")
    cors_origins: list[str] = Field(default_factory=list, description="Only needed if the web app is on another origin")
    admin_email: str | None = Field(default=None, description="Bootstrap admin, created at startup if missing")
    admin_password: SecretStr | None = None
    timezone: str = Field(default="UTC", description="Timezone schedules' cron expressions run in")
    metrics_interval_seconds: float = Field(default=5.0, gt=0, description="Live metrics push interval")

    @property
    def chroma_path(self) -> Path:
        return self.data_dir / "chroma"

    @property
    def resolved_database_url(self) -> str:
        return self.database_url or f"sqlite:///{self.data_dir / 'gigscout.db'}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
