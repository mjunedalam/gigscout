"""Learn from outcomes: leads the company won or lost nudge the scores of similar open leads.

Signals are plain and explainable (where a lead came from, its kind, its budget band, the skills it asks for), each a
smoothed win rate compared with the company's overall one. The nudge is small and capped, so the agents' judgement
still leads and one lucky win cannot take over the ranking.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field

from gigscout.models import Lead

MIN_OUTCOMES = 8  # learning starts after this many won/lost leads, with at least one of each
MIN_SIGNAL = 3  # a signal needs this many outcomes behind it
PRIOR = 2.0  # pseudo-outcomes at the overall rate, so small samples stay close to it
SCALE = 0.5  # how much of a signal's lift becomes score
MAX_NUDGE = 0.15
MAX_SKILLS = 8
TOP_SIGNALS = 8
OUTCOMES = {"won": True, "lost": False}
BUDGET_BANDS = ((1_000, "under $1k"), (5_000, "$1k-5k"), (20_000, "$5k-20k"))


@dataclass(frozen=True)
class Signal:
    key: str
    label: str  # e.g. "peopleperhour leads"
    wins: int
    total: int
    lift: float  # smoothed win rate minus the overall rate

    def explain(self) -> str:
        if self.lift >= 0:
            return f"You won {self.wins} of {self.total} {self.label}"
        return f"You lost {self.total - self.wins} of {self.total} {self.label}"


@dataclass(frozen=True)
class Learning:
    outcomes: int = 0
    wins: int = 0
    base_rate: float = 0.5
    signals: dict[str, Signal] = field(default_factory=dict)

    @property
    def active(self) -> bool:
        return self.outcomes >= MIN_OUTCOMES and 0 < self.wins < self.outcomes

    def nudge(self, lead: Lead) -> tuple[float, str]:
        """How much to move this lead's score, and the main reason in one sentence."""
        if not self.active:
            return 0.0, ""
        matched = [self.signals[key] for key in features(lead) if key in self.signals]
        if not matched:
            return 0.0, ""
        delta = max(-MAX_NUDGE, min(MAX_NUDGE, SCALE * sum(s.lift for s in matched)))
        if abs(delta) < 0.005:
            return 0.0, ""
        same_way = [s for s in matched if (s.lift > 0) == (delta > 0)]
        return round(delta, 4), max(same_way, key=lambda s: abs(s.lift)).explain()

    def top_signals(self, limit: int = TOP_SIGNALS) -> list[Signal]:
        ranked = sorted(self.signals.values(), key=lambda s: abs(s.lift), reverse=True)
        return [s for s in ranked if abs(s.lift) >= 0.01][:limit]


def features(lead: Lead) -> dict[str, str]:
    """The traits a lead is judged on, as key -> plain label."""
    found = {f"source:{lead.source}": f"{lead.source} leads", f"kind:{lead.kind}": f"{lead.kind} leads"}
    max_usd = lead.budget.max_usd if lead.budget else None
    if max_usd:
        band = next((label for limit, label in BUDGET_BANDS if max_usd < limit), "over $20k")
        found[f"budget:{band}"] = f"leads with budgets {band}"
    for skill in lead.skills[:MAX_SKILLS]:
        name = skill.strip().lower()
        if name:
            found[f"skill:{name}"] = f"leads asking for {name}"
    return found


def learn(outcomes: Iterable[tuple[Lead, bool]]) -> Learning:
    rows = list(outcomes)
    wins = sum(won for _, won in rows)
    base = (wins + 1) / (len(rows) + 2)
    counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    labels: dict[str, str] = {}
    for lead, won in rows:
        for key, label in features(lead).items():
            counts[key][0] += won
            counts[key][1] += 1
            labels[key] = label
    signals = {
        key: Signal(key, labels[key], w, n, round((w + PRIOR * base) / (n + PRIOR) - base, 4))
        for key, (w, n) in counts.items() if n >= MIN_SIGNAL
    }
    return Learning(outcomes=len(rows), wins=wins, base_rate=round(base, 4), signals=signals)
