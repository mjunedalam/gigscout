"""Structured run activity for the live cockpit.

Both run modes report the same small vocabulary, so the UI can draw one production line for either:

    stage     a step started: plan → search → qualify → write → report (a broadened run may revisit steps)
    act       an agent did one unit of work (a search, a review, a draft)
    progress  how far the current step is: done out of total, and what the agent is busy with right now
    found     a source search returned leads
    reviewed  a lead was judged: qualified, or dropped with a reason
    pitched   outreach was drafted for a shortlisted lead

Every event carries `t`, seconds since the run started, so a finished run can be replayed at its real pace.
Fetches run in parallel threads, hence the lock.
"""

import threading
import time
from collections.abc import Callable
from typing import Any

from gigscout.models import AgencyProfile, Lead, ScoredLead
from gigscout.scoring import drop_reason

ActivityListener = Callable[[dict[str, Any]], None]

STAGE_AGENT = {"plan": "head", "search": "prospector", "qualify": "qualifier", "write": "writer", "report": "head"}
PITCHES = 3
MAX_LOG = 3000  # a run's stored activity stays bounded even if an agent loops
TITLE_CHARS = 120


class Activity:
    def __init__(
        self,
        listener: ActivityListener | None = None,
        profile: AgencyProfile | None = None,
        threshold: float = 0.6,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._listener = listener
        self._profile = profile
        self.threshold = threshold
        self._clock = clock
        self._started = clock()
        self._lock = threading.Lock()
        self._log: list[dict[str, Any]] = []
        self._stage: str | None = None
        self._verdicts: dict[str, bool] = {}
        self._pitched: set[str] = set()

    @property
    def log(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._log)

    def stage(self, name: str) -> None:
        with self._lock:
            if name == self._stage:
                return
            self._stage = name
        self._emit("stage", stage=name, agent=STAGE_AGENT[name])

    def act(self, agent: str, what: str = "") -> None:
        self._emit("act", agent=agent, what=what)

    def progress(self, agent: str, done: int, total: int, label: str = "") -> None:
        """Reported before slow work starts too, so the UI can show what an agent is waiting on."""
        self._emit("progress", agent=agent, stage=self._stage, done=done, total=total, label=label)

    def found(self, source: str, leads: list[Lead]) -> None:
        unique = {lead.id: lead for lead in leads}  # a source returns a lead once per matching query
        self._emit("found", source=source, leads=[_lead(lead) for lead in unique.values()])

    def reviewed(self, scored: ScoredLead, qualified: bool) -> None:
        """First verdict wins, except that a dropped lead can still be qualified later."""
        lead_id = scored.lead.id
        with self._lock:
            previous = self._verdicts.get(lead_id)
            if previous is not None and (previous or not qualified):
                return
            self._verdicts[lead_id] = qualified
        reason = None if qualified else drop_reason(self._profile, scored) if self._profile else "low fit"
        self._emit(
            "reviewed", lead=_lead(scored.lead), score=round(scored.score, 3), qualified=qualified, reason=reason
        )

    def was_reviewed(self, lead_id: str) -> bool:
        with self._lock:
            return lead_id in self._verdicts

    def pitched(self, ranked_shortlist: list[ScoredLead]) -> None:
        """Outreach goes to the best few; a writer asked twice does not pitch the same lead twice."""
        for scored in ranked_shortlist[:PITCHES]:
            with self._lock:
                if scored.lead.id in self._pitched:
                    continue
                self._pitched.add(scored.lead.id)
            self._emit("pitched", lead=_lead(scored.lead))

    def _emit(self, kind: str, **data: Any) -> None:
        event = {"kind": kind, "t": round(self._clock() - self._started, 2), **data}
        with self._lock:
            if len(self._log) < MAX_LOG:
                self._log.append(event)
        if self._listener is not None:
            self._listener(event)


def _lead(lead: Lead) -> dict[str, Any]:
    budget = lead.budget.max_usd if lead.budget else None
    return {"id": lead.id, "title": lead.title[:TITLE_CHARS], "source": lead.source, "budget": budget}
