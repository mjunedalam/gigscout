"""Retrieval-Augmented Generation over the leads the agent has collected ("open-book exam")."""

from dataclasses import dataclass

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


def ask(question: str, index: LeadIndex, reasoner: Reasoner | None, k: int = 8) -> Answer:
    candidates = index.search(question, k=k)
    if not candidates:
        return Answer("No leads indexed yet — run `gigscout scout` first.", [])
    if reasoner is None:
        return Answer("No LLM available; here are the most relevant leads.", candidates)
    return Answer(reasoner.answer(question, build_context(candidates)), candidates)
