"""ChromaDB-backed memory of every lead the agent has seen. Doubles as the de-duplication ledger."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import chromadb
import numpy as np

from gigscout import quality
from gigscout.models import Candidate, Lead
from gigscout.store.embeddings import Embedder

BACKFILL_BATCH = 500


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

    def sibling(self, collection: str) -> "LeadIndex":
        """Another collection in the same store with the same embedder (one per workspace)."""
        other = object.__new__(LeadIndex)
        other._client, other._embedder = self._client, self._embedder
        other._collection = self._client.get_or_create_collection(
            name=collection, configuration={"hnsw": {"space": "cosine"}}
        )
        return other

    def count(self) -> int:
        return self._collection.count()

    def add_new(self, leads: Sequence[Lead]) -> list[Lead]:
        """Store leads not seen before, quality-checked and marked when they repeat a lead already stored (or one
        earlier in the same batch); return only the new ones, as stored."""
        unique = list({lead.id: lead for lead in leads}.values())
        if not unique:
            return []
        existing = set(self._collection.get(ids=[lead.id for lead in unique], include=[])["ids"])
        fresh = [lead for lead in unique if lead.id not in existing]
        if not fresh:
            return []
        now = datetime.now(UTC)
        documents = [lead.document() for lead in fresh]
        vectors = self._embedder.embed_documents(documents)
        stored = self._with_quality(fresh, vectors)
        self._collection.add(
            ids=[lead.id for lead in stored], embeddings=vectors, documents=documents,
            metadatas=[_metadata(lead, now) for lead in stored],
        )
        return stored

    def _with_quality(self, fresh: list[Lead], vectors: list[list[float]]) -> list[Lead]:
        earlier = self._nearest_stored(vectors)
        out: list[Lead] = []
        for i, (lead, vector) in enumerate(zip(fresh, vectors, strict=True)):
            duplicate_of = None
            match = earlier[i]
            if match and quality.is_duplicate(lead, match[0], match[1]):
                duplicate_of = match[0].duplicate_of or match[0].id
            else:
                for prev, prev_vector in zip(out, vectors[:i], strict=False):
                    if quality.is_duplicate(lead, prev, _cosine(vector, prev_vector)):
                        duplicate_of = prev.duplicate_of or prev.id
                        break
            out.append(quality.assessed(lead, duplicate_of))
        return out

    def _nearest_stored(self, vectors: list[list[float]]) -> list[tuple[Lead, float] | None]:
        if self.count() == 0:
            return [None] * len(vectors)
        result = self._collection.query(query_embeddings=vectors, n_results=1, include=["metadatas", "distances"])
        return [
            (Lead.model_validate_json(metas[0]["payload"]), 1 - dists[0]) if metas else None
            for metas, dists in zip(result["metadatas"], result["distances"], strict=True)
        ]

    def recheck_quality(self) -> int:
        """Quality-check leads stored before the check existed (or under older rules), oldest first, so a repost
        points at the original. Returns how many were updated."""
        if self.count() == 0:
            return 0
        rows = self._collection.get(include=["metadatas", "embeddings"])
        order = sorted(range(len(rows["ids"])), key=lambda i: rows["metadatas"][i].get("seen_ts", 0))
        leads = [Lead.model_validate_json(rows["metadatas"][i]["payload"]) for i in order]
        matrix = np.asarray([rows["embeddings"][i] for i in order], dtype=np.float32)
        stale = [k for k, i in enumerate(order) if rows["metadatas"][i].get("qv") != quality.QUALITY_VERSION]
        if not stale:
            return 0
        updated: dict[int, Lead] = {}
        for k in stale:
            lead, duplicate_of = leads[k], None
            if k:
                sims = matrix[:k] @ matrix[k]
                for j in np.argsort(-sims)[:5]:
                    if sims[j] < quality.DUPLICATE_SIMILARITY:
                        break
                    if quality.is_duplicate(lead, leads[j], float(sims[j])):
                        original = updated.get(j, leads[j])
                        duplicate_of = original.duplicate_of or original.id
                        break
            updated[k] = quality.assessed(lead, duplicate_of)
        ids = [rows["ids"][order[k]] for k in updated]
        metas = [{**rows["metadatas"][order[k]], "payload": lead.model_dump_json(), "qv": quality.QUALITY_VERSION}
                 for k, lead in updated.items()]
        for start in range(0, len(ids), BACKFILL_BATCH):
            end = start + BACKFILL_BATCH
            self._collection.update(ids=ids[start:end], metadatas=metas[start:end])
        return len(ids)

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
        "qv": quality.QUALITY_VERSION,
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


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    va, vb = np.asarray(a), np.asarray(b)
    denominator = float(np.linalg.norm(va) * np.linalg.norm(vb)) or 1.0
    return float(va @ vb) / denominator
