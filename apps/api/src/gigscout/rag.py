"""Retrieval-Augmented Generation over the leads the agent has collected ("open-book exam")."""

import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from gigscout.agent.nodes import budget_label, client_label
from gigscout.agent.reasoner import Reasoner
from gigscout.models import Candidate
from gigscout.store.vector_store import LeadIndex

SNIPPET_CHARS = 600


@dataclass(frozen=True)
class Answer:
    text: str
    sources: list[Candidate]


def build_context(candidates: list[Candidate]) -> str:
    blocks = []
    for i, c in enumerate(candidates, 1):
        lead = c.lead
        header = f"[{i}] {lead.title} ({lead.kind}, {lead.source}, client {client_label(lead)}, {budget_label(lead)})"
        blocks.append(f"{header}\n{lead.url}\n{lead.description[:SNIPPET_CHARS]}")
    return "\n\n".join(blocks)


NO_LEADS = "No leads indexed yet — run `gigscout scout` first."
NO_LLM = "No LLM available; here are the most relevant leads."
FALLBACK_CHUNK = 3  # words per chunk when there is no model to stream from


def ask_stream(question: str, index: LeadIndex, reasoner: Reasoner | None, k: int = 8) -> Iterator[dict[str, Any]]:
    """The same answer as `ask`, as it happens: status → sources (Candidates) → answer tokens → done.

    Model failures mid-answer become an `error` event, so a client keeps the tokens it already showed.
    """
    started = time.monotonic()
    yield {"type": "status", "text": "Searching lead memory"}
    candidates = index.search(question, k=k)
    yield {"type": "sources", "sources": candidates, "elapsed": round(time.monotonic() - started, 2)}
    if not candidates or reasoner is None:
        words = (NO_LEADS if not candidates else NO_LLM).split(" ")
        for i in range(0, len(words), FALLBACK_CHUNK):
            yield {"type": "token", "text": " ".join(words[i : i + FALLBACK_CHUNK]) + " "}
    else:
        yield {"type": "status", "text": f"Reading {len(candidates)} leads"}
        try:
            for chunk in reasoner.answer_stream(question, build_context(candidates)):
                if chunk:
                    yield {"type": "token", "text": chunk}
        except Exception as exc:  # keep what was streamed; tell the client why it stopped
            yield {"type": "error", "message": f"The model stopped answering: {exc}"}
            return
    yield {"type": "done", "elapsed": round(time.monotonic() - started, 2)}


def ask(question: str, index: LeadIndex, reasoner: Reasoner | None, k: int = 8) -> Answer:
    candidates = index.search(question, k=k)
    if not candidates:
        return Answer(NO_LEADS, [])
    if reasoner is None:
        return Answer(NO_LLM, candidates)
    return Answer(reasoner.answer(question, build_context(candidates)), candidates)
