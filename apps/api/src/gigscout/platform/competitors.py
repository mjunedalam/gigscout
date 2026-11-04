"""Checks award notices for every workspace's competitors, daily and on demand."""

import logging
import threading
import time

from sqlalchemy import select

from gigscout import competitors
from gigscout.competitors import Award, AwardFetcher
from gigscout.platform.db import SessionFactory
from gigscout.platform.events import EventBus
from gigscout.platform.scheduler import ScheduleManager
from gigscout.platform.tables import Competitor, CompetitorWin

log = logging.getLogger(__name__)

JOB_ID = "competitors"
CHECK_HOUR = 7
CACHE_SECONDS = 3 * 3600  # award notices are shared by every workspace, and read at most this often


class CompetitorWatcher:
    def __init__(self, sessions: SessionFactory, bus: EventBus, schedules: ScheduleManager,
                 fetch: AwardFetcher) -> None:
        self._sessions = sessions
        self._bus = bus
        self._schedules = schedules
        self._fetch = fetch
        self._cache: tuple[float, list[Award]] = (0.0, [])
        self._lock = threading.Lock()

    def start(self) -> None:
        self._schedules.set_daily(JOB_ID, CHECK_HOUR, self.check_all)

    def awards(self) -> list[Award]:
        with self._lock:
            fetched_at, cached = self._cache
            if cached and time.monotonic() - fetched_at < CACHE_SECONDS:
                return cached
        awards = self._fetch()
        with self._lock:
            self._cache = (time.monotonic(), awards)
        return awards

    def check(self, workspace_id: int) -> dict:
        """Record new wins for this workspace's competitors. Returns how many notices were read and wins found."""
        with self._sessions() as session:
            watched = list(session.scalars(select(Competitor).where(Competitor.workspace_id == workspace_id)))
        if not watched:
            return {"notices": 0, "new": 0}
        awards = self.awards()
        found = 0
        with self._sessions() as session:
            for competitor in watched:
                known = set(session.scalars(select(CompetitorWin.notice_id).where(
                    CompetitorWin.competitor_id == competitor.id)))
                for award, supplier in competitors.wins_for(awards, competitor.name):
                    if award.notice_id in known:
                        continue
                    known.add(award.notice_id)
                    session.add(CompetitorWin(
                        workspace_id=workspace_id, competitor_id=competitor.id, notice_id=award.notice_id[:80],
                        supplier=supplier[:200], title=award.title or "(untitled notice)", buyer=award.buyer,
                        amount=award.amount, currency=award.currency, awarded_at=award.awarded_at, url=award.url,
                    ))
                    found += 1
                    self._bus.publish("competitor.won", {"competitor": competitor.name, "title": award.title,
                                                         "buyer": award.buyer}, workspace_id)
            session.commit()
        return {"notices": len(awards), "new": found}

    def check_all(self) -> None:
        with self._sessions() as session:
            ids = sorted(set(session.scalars(select(Competitor.workspace_id))))
        for workspace_id in ids:
            try:
                self.check(workspace_id)
            except Exception:
                log.warning("Competitor check failed for workspace %s", workspace_id, exc_info=True)
