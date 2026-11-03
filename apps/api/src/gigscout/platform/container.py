"""Builds and owns every long-lived platform object for one server process."""

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from sqlalchemy import func, select
from sqlalchemy.engine import Engine

from gigscout.config import Settings
from gigscout.models import AgencyProfile
from gigscout.platform.db import SessionFactory, create_db
from gigscout.platform.digests import DigestManager
from gigscout.platform.events import EventBus
from gigscout.platform.runs import RunManager
from gigscout.platform.scheduler import ScheduleManager
from gigscout.platform.security import ACCOUNT_MAX_FAILURES, LoginLimiter, hash_password
from gigscout.platform.tables import AgencyProfileRecord, User
from gigscout.service import ScoutService

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
    login_limiter: LoginLimiter = field(default_factory=LoginLimiter)  # per account + client address
    account_limiter: LoginLimiter = field(default_factory=lambda: LoginLimiter(max_failures=ACCOUNT_MAX_FAILURES))
    started_at: float = field(default_factory=time.time)

    @classmethod
    def build(cls, settings: Settings, service: ScoutService | None = None) -> "Platform":
        service = service or ScoutService.from_settings(settings)
        engine, sessions = create_db(settings.resolved_database_url)
        bus = EventBus()
        runs = RunManager(service, sessions, bus)
        schedules = ScheduleManager(sessions, runs, bus, settings.timezone)
        digests = DigestManager(sessions, service.deps.index, settings, bus, schedules)
        return cls(settings, service, engine, sessions, bus, runs, schedules, digests)

    def start(self) -> None:
        recovered = self.runs.recover()
        if recovered:
            log.warning("Marked %d interrupted run(s) as failed", recovered)
        self._bootstrap_admin()
        self._seed_default_profile()
        self.digests.sync()
        self.schedules.start()

    def stop(self) -> None:
        self.schedules.shutdown()
        self.runs.shutdown()
        self.engine.dispose()

    def _bootstrap_admin(self) -> None:
        email, password = self.settings.admin_email, self.settings.admin_password
        with self.sessions() as session:
            if email and password and not session.scalar(select(User).where(User.email == email.lower())):
                session.add(User(
                    email=email.lower(), name="Admin", role="admin",
                    password_hash=hash_password(password.get_secret_value()),
                ))
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
