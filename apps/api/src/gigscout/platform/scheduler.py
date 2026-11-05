"""Cron schedules for agent runs, stored in the database and executed by APScheduler."""

import logging
from collections.abc import Callable
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from gigscout.platform.db import SessionFactory
from gigscout.platform.events import EventBus
from gigscout.platform.runs import RunManager
from gigscout.platform.tables import Schedule, utcnow

log = logging.getLogger(__name__)

MISFIRE_GRACE_SECONDS = 300


class InvalidCron(ValueError):
    pass


def parse_cron(expression: str, timezone: str) -> CronTrigger:
    """Standard 5-field crontab, e.g. '0 */2 * * 1-5' (every 2 hours on weekdays)."""
    try:
        return CronTrigger.from_crontab(expression.strip(), timezone=timezone)
    except ValueError as exc:
        raise InvalidCron(f"Invalid cron expression '{expression}': {exc}") from exc


class ScheduleManager:
    def __init__(self, sessions: SessionFactory, runs: RunManager, bus: EventBus, timezone: str,
                 blocked: Callable[[int], str | None] = lambda _workspace_id: None) -> None:
        self._sessions = sessions
        self._blocked = blocked  # billing: why a workspace may not run now
        self._runs = runs
        self._bus = bus
        self._timezone = timezone
        self._scheduler = BackgroundScheduler(timezone=timezone, job_defaults={"coalesce": True, "max_instances": 1})

    @property
    def running(self) -> bool:
        return self._scheduler.running

    def start(self) -> None:
        with self._sessions() as session:
            for schedule in session.scalars(select(Schedule).where(Schedule.enabled)):
                self._register(schedule)
        self._scheduler.start()
        log.info("Scheduler started with %d job(s)", len(self._scheduler.get_jobs()))

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    def sync(self, schedule: Schedule) -> None:
        """Call after creating or updating a schedule."""
        self.remove(schedule.id)
        if schedule.enabled:
            self._register(schedule)

    def remove(self, schedule_id: int) -> None:
        job = self._scheduler.get_job(_job_id(schedule_id))
        if job is not None:
            job.remove()

    def next_run(self, schedule_id: int) -> datetime | None:
        job = self._scheduler.get_job(_job_id(schedule_id))
        return getattr(job, "next_run_time", None) if job else None

    def upcoming(self, expression: str, count: int = 5) -> list[datetime]:
        trigger = parse_cron(expression, self._timezone)
        times: list[datetime] = []
        previous = None
        now = datetime.now(trigger.timezone)
        for _ in range(count):
            nxt = trigger.get_next_fire_time(previous, previous or now)
            if nxt is None:
                break
            times.append(nxt)
            previous = nxt
        return times

    def set_daily(self, job_id: str, hour: int | None, func) -> None:
        """(Re)schedule a daily job at `hour` (scheduler timezone), or remove it when hour is None."""
        existing = self._scheduler.get_job(job_id)
        if existing is not None:
            existing.remove()
        if hour is not None:
            self._scheduler.add_job(func, CronTrigger(hour=hour, minute=0, timezone=self._timezone), id=job_id)

    def set_interval(self, job_id: str, seconds: int, func) -> None:
        """(Re)schedule a job every `seconds`; one at a time, and a missed turn is skipped, not queued."""
        existing = self._scheduler.get_job(job_id)
        if existing is not None:
            existing.remove()
        self._scheduler.add_job(func, IntervalTrigger(seconds=seconds), id=job_id, max_instances=1, coalesce=True)

    def has_job(self, job_id: str) -> bool:
        return self._scheduler.get_job(job_id) is not None

    @property
    def job_count(self) -> int:
        return len(self._scheduler.get_jobs())

    def fire(self, schedule_id: int) -> str | None:
        """Start a run for this schedule now. Skips if the same profile already has a run in progress."""
        with self._sessions() as session:
            schedule = session.get(Schedule, schedule_id)
            if schedule is None:
                return None
            reason = self._blocked(schedule.workspace_id)
            if reason:
                log.info("Schedule %s skipped: %s", schedule.name, reason)
                self._bus.publish("schedule.skipped", {"id": schedule.id, "name": schedule.name, "reason": reason},
                                  schedule.workspace_id)
                return None
            if self._runs.has_active_run(schedule.profile_id):
                log.info("Schedule %s skipped: a run for this profile is already active", schedule.name)
                self._bus.publish("schedule.skipped", {"id": schedule.id, "name": schedule.name}, schedule.workspace_id)
                return None
            run = self._runs.submit(schedule.workspace_id, schedule.profile_id, schedule.mode, "schedule",
                                    f"schedule:{schedule.name}")
            schedule.last_run_at, schedule.last_run_id = utcnow(), run.id
            session.commit()
            return run.id

    def _register(self, schedule: Schedule) -> None:
        try:
            trigger = parse_cron(schedule.cron, self._timezone)
        except InvalidCron as exc:
            log.error("Schedule %s not registered: %s", schedule.id, exc)
            return
        self._scheduler.add_job(
            self.fire, trigger, args=[schedule.id], id=_job_id(schedule.id), name=schedule.name,
            replace_existing=True, misfire_grace_time=MISFIRE_GRACE_SECONDS,
        )


def _job_id(schedule_id: int) -> str:
    return f"schedule:{schedule_id}"
