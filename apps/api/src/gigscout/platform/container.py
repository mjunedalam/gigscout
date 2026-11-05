"""Builds and owns every long-lived platform object for one server process."""

import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from sqlalchemy import func, select
from sqlalchemy.engine import Engine

from gigscout import competitors
from gigscout.config import Settings
from gigscout.http import PoliteClient
from gigscout.models import AgencyProfile
from gigscout.platform import pipeline
from gigscout.platform.billing import BillingService
from gigscout.platform.competitors import CompetitorWatcher
from gigscout.platform.db import SessionFactory, create_db
from gigscout.platform.digests import DigestManager
from gigscout.platform.events import EventBus
from gigscout.platform.inbox import ReplyDesk
from gigscout.platform.integrations import UpworkConnection
from gigscout.platform.pitches import PitchDesk
from gigscout.platform.runs import RunManager
from gigscout.platform.scheduler import ScheduleManager
from gigscout.platform.security import ACCOUNT_MAX_FAILURES, LoginLimiter, WeakPasswordError, hash_password
from gigscout.platform.tables import DEFAULT_WORKSPACE, AgencyProfileRecord, Membership, User, Workspace
from gigscout.service import ScoutService
from gigscout.store.vector_store import LeadIndex

log = logging.getLogger(__name__)

DEFAULT_PROFILE_PATH = Path("profiles/example.yaml")


@dataclass
class Platform:
    settings: Settings
    service: ScoutService
    engine: Engine
    sessions: SessionFactory
    bus: EventBus
    runs: RunManager
    schedules: ScheduleManager
    digests: DigestManager
    upwork: UpworkConnection
    billing: BillingService
    competitors: CompetitorWatcher
    pitches: PitchDesk
    replies: ReplyDesk
    login_limiter: LoginLimiter = field(default_factory=LoginLimiter)  # per account + client address
    account_limiter: LoginLimiter = field(default_factory=lambda: LoginLimiter(max_failures=ACCOUNT_MAX_FAILURES))
    started_at: float = field(default_factory=time.time)
    _indexes: dict[int, LeadIndex] = field(default_factory=dict)
    _indexes_lock: threading.Lock = field(default_factory=threading.Lock)

    def index_for(self, workspace_id: int) -> LeadIndex:
        """The workspace's own lead store. The first workspace keeps the original collection."""
        if workspace_id == DEFAULT_WORKSPACE:
            return self.service.deps.index
        with self._indexes_lock:
            if workspace_id not in self._indexes:
                name = f"{self.settings.collection_name}_ws{workspace_id}"
                self._indexes[workspace_id] = self.service.deps.index.sibling(name)
            return self._indexes[workspace_id]

    @classmethod
    def build(cls, settings: Settings, service: ScoutService | None = None) -> "Platform":
        service = service or ScoutService.from_settings(settings)
        engine, sessions = create_db(settings.resolved_database_url)
        bus = EventBus()
        upwork = UpworkConnection(sessions, settings)
        indexes = _IndexRef()
        runs = RunManager(service, sessions, bus, extra_sources=upwork.sources, index_for=indexes)
        billing = BillingService(sessions, settings)
        schedules = ScheduleManager(sessions, runs, bus, settings.timezone, blocked=billing.run_blocked)
        digests = DigestManager(sessions, indexes, settings, bus, schedules)
        awards_client = PoliteClient(settings)
        watcher = CompetitorWatcher(sessions, bus, schedules, lambda: competitors.recent_awards(awards_client))
        pitches = PitchDesk(sessions, bus, schedules, indexes, lambda: service.deps.reasoner,
                            lambda: service.web_client)
        runs.after_run = pitches.draft_for_run
        replies = ReplyDesk(sessions, bus, schedules, settings, indexes, lambda: service.deps.reasoner)
        platform = cls(settings, service, engine, sessions, bus, runs, schedules, digests, upwork, billing, watcher,
                       pitches, replies)
        indexes.platform = platform
        return platform

    def start(self) -> None:
        recovered = self.runs.recover()
        if recovered:
            log.warning("Marked %d interrupted run(s) as failed", recovered)
        self._bootstrap_admin()
        self._seed_default_profile()
        self._recheck_quality()
        with self.sessions() as session:
            if added := pipeline.backfill(session, self.settings.good_match_threshold):
                log.info("Built the pipeline history: %d step(s) from earlier data", added)
        self.digests.sync()
        self.competitors.start()
        self.pitches.start()
        self.replies.start()
        self.schedules.start()

    def stop(self) -> None:
        self.schedules.shutdown()
        self.runs.shutdown()
        self.engine.dispose()

    def _recheck_quality(self) -> None:
        """Leads stored before the quality check (or under older rules) are checked once, at startup."""
        with self.sessions() as session:
            workspace_ids = list(session.scalars(select(Workspace.id)))
        for workspace_id in workspace_ids:
            try:
                checked = self.index_for(workspace_id).recheck_quality()
            except Exception:  # a failed backfill must not stop the server; it is tried again next start
                log.warning("Quality check of stored leads failed for workspace %s", workspace_id, exc_info=True)
                continue
            if checked:
                log.info("Quality-checked %d stored leads in workspace %s", checked, workspace_id)

    def _bootstrap_admin(self) -> None:
        email, password = self.settings.admin_email, self.settings.admin_password
        with self.sessions() as session:
            if email and password and not session.scalar(select(User).where(User.email == email.lower())):
                try:
                    password_hash = hash_password(password.get_secret_value())
                except WeakPasswordError as exc:
                    raise RuntimeError(f"GIGSCOUT_ADMIN_PASSWORD is too weak: {exc}") from exc
                user = User(email=email.lower(), name="Admin", role="admin", password_hash=password_hash)
                session.add(user)
                session.flush()
                session.add(Membership(user_id=user.id, workspace_id=DEFAULT_WORKSPACE, role="owner"))
                session.commit()
                log.info("Created bootstrap admin %s", email)
            if not session.scalar(select(func.count()).select_from(User)):
                log.warning("No users yet. Create one with `gigscout create-admin` or GIGSCOUT_ADMIN_EMAIL/PASSWORD")

    def _seed_default_profile(self) -> None:
        with self.sessions() as session:
            if session.scalar(select(func.count()).select_from(AgencyProfileRecord)):
                return
            if not DEFAULT_PROFILE_PATH.is_file():
                return
            profile = AgencyProfile.model_validate(yaml.safe_load(DEFAULT_PROFILE_PATH.read_text()))
            session.add(AgencyProfileRecord(name=profile.name, data=profile.model_dump(mode="json")))
            session.commit()
            log.info("Seeded agency profile '%s' from %s", profile.name, DEFAULT_PROFILE_PATH)


class _IndexRef:
    """Lets managers built before the platform reach Platform.index_for."""

    platform: Platform | None = None

    def __call__(self, workspace_id: int) -> LeadIndex:
        assert self.platform is not None
        return self.platform.index_for(workspace_id)
