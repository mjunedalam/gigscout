"""The team's shared blackboard for one run.

Agents never talk to each other directly. They read and write this board through their tools, and the
supervisor reads a progress summary from it. It is deliberately the only mutable object in a run;
everything stored on it (Lead, Candidate, ScoredLead) is frozen.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from gigscout.agent.nodes import ScoutDeps
from gigscout.models import AgencyProfile, Candidate, ScoredLead


@dataclass
class RunContext:
    deps: ScoutDeps
    profile: AgencyProfile
    searches: list[tuple[str, str]] = field(default_factory=list)  # (source, query)
    fetched_ids: set[str] = field(default_factory=set)
    new_count: int = 0
    seen: dict[str, Candidate] = field(default_factory=dict)  # everything the qualifier has looked at
    shortlist: dict[str, ScoredLead] = field(default_factory=dict)
    report: str | None = None
    errors: list[str] = field(default_factory=list)
    trace: list[str] = field(default_factory=list)
    on_step: Callable[[str], None] | None = None  # live progress listener (the UI's run console)

    @property
    def searches_left(self) -> int:
        return self.deps.settings.team_max_searches - len(self.searches)

    def ranked_shortlist(self) -> list[ScoredLead]:
        return sorted(self.shortlist.values(), key=lambda s: s.score, reverse=True)

    def progress(self) -> str:
        return (
            f"Source searches run: {len(self.searches)} (budget left: {self.searches_left}); "
            f"leads fetched: {len(self.fetched_ids)} ({self.new_count} new); "
            f"total in memory: {self.deps.index.count()}; "
            f"qualified: {len(self.shortlist)}/{self.deps.settings.shortlist_size}; "
            f"briefing written: {'yes' if self.report else 'no'}"
        )

    def log(self, entry: str) -> None:
        self.trace.append(entry)
        if self.on_step is not None:
            self.on_step(entry)
