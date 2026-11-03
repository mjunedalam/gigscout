"""The shared clipboard passed between graph nodes. Annotated fields are merged with a reducer."""

import operator
from typing import Annotated, TypedDict

from gigscout.models import AgencyProfile, Candidate, Lead, ScoredLead


class ScoutState(TypedDict, total=False):
    profile: AgencyProfile
    queries: list[str]  # every query tried so far
    pending_queries: list[str]  # queries not yet sent to the sources
    iteration: int
    raw_leads: Annotated[list[Lead], operator.add]  # every fan-out branch appends here
    errors: Annotated[list[str], operator.add]
    fetched_count: int
    new_count: int
    candidates: list[Candidate]
    scored: list[ScoredLead]
    report: str


class FetchTask(TypedDict):
    """Payload for one parallel fetch branch (sent with langgraph.types.Send)."""

    source: str
    queries: list[str]
