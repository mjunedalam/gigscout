"""ChromaDB-backed memory of every lead the agent has seen. Doubles as the de-duplication ledger."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import chromadb

from gigscout.models import Candidate, Lead
from gigscout.store.embeddings import Embedder


@dataclass(frozen=True)
class StoredLead:
    lead: Lead
    seen_at: datetime


class LeadIndex:
    def __init__(self, path: Path, collection: str, embedder: Embedder) -> None:
        path.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(path))
        self._collection = self._client.get_or_create_collection(
            name=collection, configuration={"hnsw": {"space": "cosine"}}
        )
        self._embedder = embedder

    def count(self) -> int:
        return self._collection.count()

    def add_new(self, leads: Sequence[Lead]) -> list[Lead]:
        """Store leads not seen before; return only the new ones."""
        unique = list({lead.id: lead for lead in leads}.values())
        if not unique:
            return []
        existing = set(self._collection.get(ids=[lead.id for lead in unique], include=[])["ids"])
        fresh = [lead for lead in unique if lead.id not in existing]
        if fresh:
            now = datetime.now(UTC)
            documents = [lead.document() for lead in fresh]
            self._collection.add(
                ids=[lead.id for lead in fresh],
                embeddings=self._embedder.embed_documents(documents),
                documents=documents,
                metadatas=[_metadata(lead, now) for lead in fresh],
            )
        return fresh

    def get(self, lead_id: str) -> Lead | None:
        rows = self._collection.get(ids=[lead_id], include=["metadatas"])
        return Lead.model_validate_json(rows["metadatas"][0]["payload"]) if rows["ids"] else None

    def records(self) -> list[StoredLead]:
        """Every stored lead with the time it was first seen (for listings and analytics)."""
        if self.count() == 0:
            return []
        rows = self._collection.get(include=["metadatas"])
        return [_stored(meta) for meta in rows["metadatas"]]

    def embeddings(self, ids: Sequence[str]) -> dict[str, list[float]]:
        if not ids:
            return {}
        rows = self._collection.get(ids=list(ids), include=["embeddings"])
        return {lead_id: list(vector) for lead_id, vector in zip(rows["ids"], rows["embeddings"], strict=True)}

    def search(
        self,
        query: str,
        k: int,
        max_age_days: int | None = None,
        sources: Sequence[str] | None = None,
        kinds: Sequence[str] | None = None,
    ) -> list[Candidate]:
        if self.count() == 0:
            return []
        result = self._collection.query(
            query_embeddings=[self._embedder.embed_query(query)],
            n_results=min(k, self.count()),
            where=_where(max_age_days, sources, kinds),
            include=["metadatas", "distances"],
        )
        return [
            Candidate(lead=Lead.model_validate_json(meta["payload"]), similarity=round(1 - dist, 4))
            for meta, dist in zip(result["metadatas"][0], result["distances"][0], strict=True)
        ]


def _metadata(lead: Lead, now: datetime) -> dict:
    posted = lead.posted_at or now
    return {
        "source": lead.source,
        "kind": lead.kind,
        "posted_ts": int(posted.timestamp()),
        "seen_ts": int(now.timestamp()),
        "payload": lead.model_dump_json(),
    }


def _stored(meta: dict) -> StoredLead:
    seen = meta.get("seen_ts", meta["posted_ts"])  # leads stored before seen_ts existed
    return StoredLead(lead=Lead.model_validate_json(meta["payload"]), seen_at=datetime.fromtimestamp(seen, UTC))


def _where(max_age_days: int | None, sources: Sequence[str] | None, kinds: Sequence[str] | None) -> dict | None:
    clauses: list[dict] = []
    if max_age_days:
        cutoff = datetime.now(UTC) - timedelta(days=max_age_days)
        clauses.append({"posted_ts": {"$gte": int(cutoff.timestamp())}})
    if sources:
        clauses.append({"source": {"$in": list(sources)}})
    if kinds:
        clauses.append({"kind": {"$in": list(kinds)}})
    if not clauses:
        return None
    return clauses[0] if len(clauses) == 1 else {"$and": clauses}
