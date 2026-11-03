"""The run queue: agent runs execute one at a time on a worker thread and stream progress to the event bus."""

import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from sqlalchemy import select, update

from gigscout.learning import Learning
from gigscout.models import AgencyProfile, ScoutResult
from gigscout.platform.db import SessionFactory
from gigscout.platform.events import EventBus
from gigscout.platform.learner import current_learning, score_with
from gigscout.platform.tables import AgencyProfileRecord, Connector, LeadState, Run, SourceToggle, utcnow
from gigscout.service import Mode, ScoutService
from gigscout.sources.base import Source
from gigscout.sources.website import WebsiteSource

log = logging.getLogger(__name__)

Trigger = Literal["manual", "schedule"]
StopOutcome = Literal["cancelled", "stopping"]
ACTIVE_STATUSES = ("queued", "running")


class ProfileNotFound(LookupError):
    pass


class RunStopped(BaseException):  # noqa: N818 - a control-flow signal, like KeyboardInterrupt
    """Raised inside a run when someone stops it. A BaseException on purpose: agents and nodes catch Exception to
    survive a failing step, and a stop request must not be swallowed that way."""


class RunManager:
    def __init__(self, service: ScoutService, sessions: SessionFactory, bus: EventBus) -> None:
        self._service = service
        self._sessions = sessions
        self._bus = bus
        # One worker: runs share the vector store and the local LLM, and are cheap to queue.
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="gigscout-run")
        self._lock = threading.Lock()
        self._live_activity: dict[str, list[dict]] = {}  # activity of the run in progress, until it is stored
        self._stop_requested: set[str] = set()

    def recover(self) -> int:
        """Runs left queued/running by a previous process can never finish; mark them failed."""
        with self._sessions() as session:
            result = session.execute(
                update(Run).where(Run.status.in_(ACTIVE_STATUSES))
                .values(status="failed", finished_at=utcnow(), errors=["interrupted by a server restart"])
            )
            session.commit()
            return result.rowcount

    def submit(self, profile_id: int, mode: Mode, trigger: Trigger, triggered_by: str) -> Run:
        with self._sessions() as session:
            record = session.get(AgencyProfileRecord, profile_id)
            if record is None:
                raise ProfileNotFound(f"No agency profile {profile_id}")
            run = Run(
                id=str(uuid.uuid4()), profile_id=profile_id, profile_name=record.name, mode_requested=mode,
                trigger=trigger, triggered_by=triggered_by,
            )
            session.add(run)
            session.commit()
        self._bus.publish("run.queued", _summary(run))
        self._executor.submit(self._execute, run.id)
        return run

    def has_active_run(self, profile_id: int) -> bool:
        with self._sessions() as session:
            stmt = select(Run.id).where(Run.profile_id == profile_id, Run.status.in_(ACTIVE_STATUSES)).limit(1)
            return session.scalar(stmt) is not None

    def cancel(self, run_id: str) -> StopOutcome | None:
        """A queued run is cancelled at once. A running one is asked to stop: it halts the next time it reports
        activity (agents waiting on a slow LLM call finish that call first). None if the run is already over."""
        with self._sessions() as session:
            result = session.execute(
                update(Run).where(Run.id == run_id, Run.status == "queued")
                .values(status="cancelled", finished_at=utcnow())
            )
            session.commit()
            if result.rowcount:
                self._bus.publish("run.cancelled", {"id": run_id})
                return "cancelled"
            run = session.get(Run, run_id)
            if run is None or run.status != "running":
                return None
        with self._lock:
            self._stop_requested.add(run_id)
        self._bus.publish("run.stopping", {"id": run_id})
        return "stopping"

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _execute(self, run_id: str) -> None:
        started = self._start(run_id)
        if started is None:
            return
        mode, agency = started
        try:
            result = self._service.scout(
                agency, mode, on_step=lambda line: self._step(run_id, line),
                on_activity=lambda event: self._activity(run_id, event), sources=self.sources_for_run(),
            )
        except RunStopped:
            self._finish_stopped(run_id)
            return
        except Exception as exc:
            log.exception("Run %s failed", run_id)
            self._finish_failed(run_id, exc)
            return
        self._finish(run_id, result)

    def _start(self, run_id: str) -> tuple[Mode, AgencyProfile] | None:
        with self._sessions() as session:
            run = session.get(Run, run_id)
            if run is None or run.status != "queued":
                return None  # cancelled while waiting
            record = session.get(AgencyProfileRecord, run.profile_id) if run.profile_id else None
            if record is None:
                run.status, run.finished_at, run.errors = "failed", utcnow(), ["agency profile was deleted"]
                session.commit()
                self._bus.publish("run.finished", _summary(run))
                return None
            run.status, run.started_at = "running", utcnow()
            session.commit()
            self._bus.publish("run.started", _summary(run))
            return run.mode_requested, AgencyProfile.model_validate(record.data)

    def sources_for_run(self) -> dict[str, Source]:
        """Built-in sources an admin left on, plus the websites they added and enabled."""
        with self._sessions() as session:
            off = set(session.scalars(select(SourceToggle.name).where(SourceToggle.enabled.is_(False))))
            sites = list(session.scalars(select(Connector).where(Connector.enabled.is_(True))))
        sources: dict[str, Source] = {n: s for n, s in self._service.deps.sources.items() if n not in off}
        for site in sites:
            sources[site.name] = WebsiteSource(
                self._service.web_client, site.name, site.url, site.kind, site.feed_url, lead_kind=site.lead_kind,
            )
        return sources

    def activity(self, run_id: str) -> list[dict] | None:
        """Activity so far for a running run, or the stored activity of a finished one; None if no such run."""
        with self._lock:
            live = self._live_activity.get(run_id)
            if live is not None:
                return list(live)
        with self._sessions() as session:
            run = session.get(Run, run_id)
            return None if run is None else list(run.activity or [])

    def _activity(self, run_id: str, event: dict) -> None:
        with self._lock:
            self._live_activity.setdefault(run_id, []).append(event)
        self._bus.publish("run.activity", {"id": run_id, **event})
        self._check_stop(run_id)

    def _check_stop(self, run_id: str) -> None:
        with self._lock:
            if run_id in self._stop_requested:
                raise RunStopped

    def _take_activity(self, run_id: str) -> list[dict]:
        with self._lock:
            return self._live_activity.pop(run_id, [])

    def _step(self, run_id: str, line: str) -> None:
        self._bus.publish("run.step", {"id": run_id, "line": line[:500]})
        self._check_stop(run_id)

    def _finish(self, run_id: str, result: ScoutResult) -> None:
        with self._sessions() as session:
            run = session.get(Run, run_id)
            run.status, run.finished_at, run.mode = "succeeded", utcnow(), result.mode
            run.fetched_count, run.new_count = result.fetched_count, result.new_count
            run.match_count = len(result.matches)
            run.top_score = max((m.score for m in result.matches), default=0.0)
            run.report, run.queries = result.report, list(result.queries)
            run.errors, run.trace = list(result.errors), list(result.trace)
            run.activity = self._take_activity(run_id)
            _record_qualifications(session, run_id, result, current_learning(session, self._service.deps.index))
            blocked = _record_site_health(session, result)
            session.commit()
            self._bus.publish("run.finished", _summary(run))
        for site in blocked:
            self._bus.publish("source.blocked", site)

    def _finish_stopped(self, run_id: str) -> None:
        with self._lock:
            self._stop_requested.discard(run_id)
        with self._sessions() as session:
            run = session.get(Run, run_id)
            run.status, run.finished_at, run.errors = "cancelled", utcnow(), ["stopped before it finished"]
            run.activity = self._take_activity(run_id)
            session.commit()
            self._bus.publish("run.finished", _summary(run))

    def _finish_failed(self, run_id: str, exc: Exception) -> None:
        with self._sessions() as session:
            run = session.get(Run, run_id)
            run.status, run.finished_at, run.errors = "failed", utcnow(), [f"{type(exc).__name__}: {exc}"]
            run.activity = self._take_activity(run_id)
            session.commit()
            self._bus.publish("run.finished", _summary(run))


def _record_qualifications(session, run_id: str, result: ScoutResult, learning: Learning) -> None:
    """Keep each lead's latest score (with what won/lost leads taught) and pitch; never touch status or notes."""
    for match in result.matches:
        state = session.get(LeadState, match.lead.id) or LeadState(lead_id=match.lead.id)
        score_with(learning, state, match.lead, match.score)
        state.reasons, state.red_flags = match.reasons, match.red_flags
        state.pitch, state.last_run_id = match.pitch, run_id
        session.add(state)


def _record_site_health(session, result: ScoutResult) -> list[dict]:
    """Update each added website from this run's errors; return the ones that now refuse us (robots.txt)."""
    newly_blocked = []
    for site in session.scalars(select(Connector).where(Connector.enabled.is_(True))):
        error = next((e for e in result.errors if e.startswith(f"{site.name}:")), None)
        status = "ok" if error is None else "blocked" if "robots.txt" in error else "error"
        if status == "blocked" and site.status != "blocked":
            reason = "robots.txt does not allow automated access"
            newly_blocked.append({"name": site.name, "url": site.url, "reason": reason})
        site.status, site.last_error, site.checked_at = status, error, utcnow()
    return newly_blocked


def _summary(run: Run) -> dict:
    return {
        "id": run.id, "status": run.status, "profile_name": run.profile_name, "mode": run.mode or run.mode_requested,
        "trigger": run.trigger, "new_count": run.new_count, "match_count": run.match_count,
        "top_score": run.top_score, "duration_seconds": run.duration_seconds,
    }
