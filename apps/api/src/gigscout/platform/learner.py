"""Apply what the company's won and lost leads teach to the scores of its open leads."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from gigscout.learning import OUTCOMES, Learning, learn
from gigscout.platform.tables import LeadState
from gigscout.store.vector_store import LeadIndex


def current_learning(session: Session, index: LeadIndex) -> Learning:
    rows = session.scalars(select(LeadState).where(LeadState.status.in_(OUTCOMES)))
    pairs = [(lead, OUTCOMES[s.status]) for s in rows if (lead := index.get(s.lead_id)) is not None]
    return learn(pairs)


def score_with(learning: Learning, state: LeadState, lead, agent_score: float) -> None:
    """Keep the agents' score and store the learned one next to it."""
    delta, note = learning.nudge(lead)
    state.base_score = agent_score
    state.score = round(min(1.0, max(0.0, agent_score + delta)), 4)
    state.learned, state.learned_note = delta, note


def rescore_open_leads(session: Session, index: LeadIndex) -> int:
    """Re-apply the latest learning to every open, scored lead. Returns how many scores changed."""
    learning = current_learning(session, index)
    changed = 0
    for state in session.scalars(select(LeadState).where(LeadState.status == "new", LeadState.score.is_not(None))):
        lead = index.get(state.lead_id)
        if lead is None:
            continue
        before = state.score
        score_with(learning, state, lead, state.base_score if state.base_score is not None else state.score)
        changed += state.score != before
    return changed
