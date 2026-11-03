"""The contract every lead source implements (pull-based: the agent asks, the source answers)."""

from collections.abc import Sequence
from typing import Protocol

from gigscout.models import Lead


class Source(Protocol):
    name: str

    def fetch(self, queries: Sequence[str], limit: int) -> list[Lead]:
        """Return recent leads relevant to any of `queries` (at most ~`limit` per query)."""
        ...
