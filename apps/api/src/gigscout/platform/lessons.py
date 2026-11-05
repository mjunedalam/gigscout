"""What gets replies: every approved message and whether the client answered, split by what the message was like.

The strongest differences become lessons the pitch writer is given, so the agents write more of what works for
this company. Only differences with enough messages behind them count.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from gigscout.platform.tables import AGENT_AUTHOR, Outreach, utcnow

MIN_SENT = 5  # a trait needs this many sent messages before its reply rate means anything
MIN_TOTAL = 10  # and the workspace needs this many before any lesson is drawn
LIFT = 1.3  # 30% better (or worse) than usual is worth saying
LOOKBACK = timedelta(days=180)
WORDS = ((0, 80, "under 80 words"), (80, 140, "80-140 words"), (140, 10_000, "over 140 words"))


@dataclass(frozen=True)
class Outcome:
    words: int
    channel: str
    kind: str
    cites_work: bool
    by_agents: bool
    edited: bool
    has_question: bool
    replied: bool


@dataclass(frozen=True)
class Lesson:
    trait: str
    sent: int
    replied: int
    rate: float
    lift: float  # rate / the workspace's usual rate

    @property
    def better(self) -> bool:
        return self.lift >= 1

    def says(self) -> str:
        times = f"{self.lift:.1f}x" if self.lift >= 1 else f"{1 / self.lift:.1f}x less"
        return f"Messages {self.trait} got replies {times} as often ({self.replied} of {self.sent})."


def traits(o: Outcome) -> list[str]:
    words = next(label for low, high, label in WORDS if low <= o.words < high)
    found = [words, "sent by email" if o.channel == "email" else "posted as a marketplace bid"]
    found.append("citing your past work" if o.cites_work else "without a case study")
    found.append("ending on a question" if o.has_question else "without a question")
    if o.kind == "follow_up":
        found.append("that were follow-ups")
    if o.by_agents:
        found.append("edited by your team" if o.edited else "sent as the agents wrote them")
    return found


def lessons(outcomes: Sequence[Outcome]) -> list[Lesson]:
    """Traits whose reply rate differs clearly from usual, strongest first. Empty until there is enough to learn."""
    if len(outcomes) < MIN_TOTAL:
        return []
    base = sum(o.replied for o in outcomes) / len(outcomes)
    if base == 0:
        return []
    counts: dict[str, list[int]] = {}
    for o in outcomes:
        for trait in traits(o):
            sent_replied = counts.setdefault(trait, [0, 0])
            sent_replied[0] += 1
            sent_replied[1] += o.replied
    found = []
    for trait, (sent, replied) in counts.items():
        if sent < MIN_SENT or sent == len(outcomes):
            continue  # too few, or every message had it: nothing to compare
        rate = replied / sent
        lift = rate / base if rate else 0.01
        if lift >= LIFT or lift <= 1 / LIFT:
            found.append(Lesson(trait, sent, replied, round(rate, 3), round(lift, 2)))
    return sorted(found, key=lambda lesson: abs(lesson.lift - 1) * lesson.sent, reverse=True)


def load_outcomes(session: Session, workspace_id: int) -> list[Outcome]:
    rows = session.scalars(select(Outreach).where(
        Outreach.workspace_id == workspace_id, Outreach.status.in_(("sent", "replied", "no_reply")),
        Outreach.kind != "answer", Outreach.sent_at >= utcnow() - LOOKBACK))
    return [_outcome(r) for r in rows]


def for_drafting(found: Iterable[Lesson], limit: int = 4) -> str:
    """The lessons as the pitch writer gets them: our own results, so plain instructions are fine."""
    lines = [lesson.says() for lesson in list(found)[:limit]]
    return "\n".join(f"- {line}" for line in lines)


def _outcome(r: Outreach) -> Outcome:
    body = r.body or ""
    original = r.drafted_body if r.drafted_body is not None else body
    mine = "\n".join(line for line in body.splitlines() if not line.startswith(">"))  # skip quoted threads
    return Outcome(words=len(mine.split()), channel=r.channel, kind=r.kind or "first",
                   cites_work=bool(r.evidence), by_agents=r.created_by == AGENT_AUTHOR,
                   edited=" ".join(original.split()) != " ".join(body.split()), has_question="?" in mine,
                   replied=r.status == "replied")
