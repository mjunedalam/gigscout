"""Composition root: builds the real dependencies once and exposes the use-cases to the CLI and API."""

import logging
from dataclasses import dataclass
from typing import Literal

from gigscout.activity import Activity, ActivityListener
from gigscout.agent.graph import StepListener, run_scout
from gigscout.agent.nodes import ScoutDeps
from gigscout.agent.reasoner import OllamaReasoner, build_chat_model
from gigscout.config import Settings
from gigscout.http import PoliteClient
from gigscout.inbound import google_ads
from gigscout.models import AgencyProfile, Candidate, Lead, ScoutResult
from gigscout.multiagent.runner import run_team
from gigscout.multiagent.team import TeamModels
from gigscout.rag import Answer, ask
from gigscout.sources.registry import build_sources
from gigscout.store.embeddings import FastEmbedder
from gigscout.store.vector_store import LeadIndex
from gigscout.tracking import tracked_run

log = logging.getLogger(__name__)

Mode = Literal["auto", "team", "pipeline"]


@dataclass(frozen=True)
class ScoutService:
    deps: ScoutDeps
    team_models: TeamModels | None = None  # defaults to deps.chat_model in every role

    @classmethod
    def from_settings(cls, settings: Settings) -> "ScoutService":
        client = PoliteClient(settings)
        index = LeadIndex(settings.chroma_path, settings.collection_name, FastEmbedder(settings.embedding_model))
        model = build_chat_model(settings)
        reasoner = OllamaReasoner(model) if model else None
        return cls(ScoutDeps(settings, build_sources(settings, client), index, reasoner, model))

    def resolve_mode(self, mode: Mode) -> Literal["team", "pipeline"]:
        """`auto` uses the multi-agent team when a tool-calling LLM is available, else the fixed pipeline."""
        has_team = self.team_models is not None or self.deps.chat_model is not None
        if mode == "team" and not has_team:
            log.warning("Team mode needs an LLM; falling back to the pipeline")
        if mode == "pipeline" or not has_team:
            return "pipeline"
        return "team"

    def scout(
        self,
        profile: AgencyProfile,
        mode: Mode = "auto",
        on_step: StepListener | None = None,
        on_activity: ActivityListener | None = None,
    ) -> ScoutResult:
        resolved = self.resolve_mode(mode)
        activity = Activity(on_activity, profile=profile, threshold=self.deps.settings.good_match_threshold)
        with tracked_run(self.deps.settings, profile, mode=resolved) as run:
            if resolved == "team":
                models = self.team_models or TeamModels.uniform(self.deps.chat_model)
                result = run_team(self.deps, profile, models, on_step=on_step, activity=activity)
            else:
                result = run_scout(self.deps, profile, on_step=on_step, activity=activity)
            run.log_result(result)
        return result

    def search(self, query: str, k: int = 10) -> list[Candidate]:
        return self.deps.index.search(query, k=k)

    def ask(self, question: str, k: int = 8) -> Answer:
        return ask(question, self.deps.index, self.deps.reasoner, k=k)

    def ingest_inbound(self, lead: Lead) -> bool:
        """Store a pushed lead (e.g. a Google Ads form submission). Returns False if it was already stored."""
        stored = bool(self.deps.index.add_new([lead]))
        log.info("Inbound lead %s %s", lead.id, "stored" if stored else "already known")
        return stored

    @property
    def inbound_enabled(self) -> bool:
        return self.deps.settings.google_ads_webhook_key is not None

    def source_names(self) -> list[str]:
        """Pull sources the agent searches, plus inbound channels that push leads in."""
        inbound = [google_ads.SOURCE_NAME] if self.inbound_enabled else []
        return [*self.deps.sources, *inbound]
