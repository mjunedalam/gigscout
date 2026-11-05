"""The company's own knowledge: case studies, past proposals, portfolio and rates, searchable by meaning.

Pitches are written from it (retrieval-augmented), and every claim in a pitch is checked against it, so the agents
never promise work the company has not done.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass

import chromadb
import numpy as np

from gigscout.store.embeddings import Embedder

CHUNK_CHARS = 900
CHUNK_OVERLAP = 150
MIN_EVIDENCE = 0.35  # cosine similarity below this is not about the lead
SUPPORTED = 0.55  # a claim this close to something in the documents is backed by them
DOC_KINDS = ("case_study", "proposal", "portfolio", "pricing", "about", "other")
# sentences that state facts about the company: these need backing
CLAIM = re.compile(
    r"\d|%|\$|€|£|\b(we|our|us)\b.*\b(built|build|delivered|shipped|launched|helped|have|has|worked|work|"
    r"specialise|specialize|experience|clients?|years?|team|certified|award)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Evidence:
    doc_id: int
    title: str
    kind: str
    text: str
    similarity: float


@dataclass(frozen=True)
class Claim:
    sentence: str
    supported: bool
    source: str | None  # the document title that backs it
    similarity: float


def chunk_text(text: str, size: int = CHUNK_CHARS, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split into overlapping pieces on paragraph, then sentence, boundaries; never mid-word if avoidable."""
    text = re.sub(r"[ \t]+", " ", text.replace("\r\n", "\n")).strip()
    if not text:
        return []
    chunks, current = [], ""
    for part in re.split(r"(?<=[.!?])\s+|\n{2,}", text):
        part = part.strip()
        if not part:
            continue
        while len(part) > size:  # one huge sentence: cut it
            chunks.append(part[:size])
            part = part[size - overlap:]
        if current and len(current) + len(part) + 1 > size:
            chunks.append(current)
            current = current[-overlap:].split(" ", 1)[-1] if overlap else ""
        current = f"{current} {part}".strip()
    if current:
        chunks.append(current)
    return chunks


def claim_sentences(body: str) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+|\n+", body)
    return [s.strip() for s in sentences if len(s.strip()) > 12 and CLAIM.search(s) and not s.strip().startswith(">")]


class KnowledgeBase:
    """One Chroma collection per workspace. Each chunk carries its document's id, title and kind."""

    def __init__(self, client: chromadb.ClientAPI, name: str, embedder: Embedder) -> None:
        self._collection = client.get_or_create_collection(name=name, configuration={"hnsw": {"space": "cosine"}})
        self._embedder = embedder

    def add(self, doc_id: int, title: str, kind: str, text: str) -> int:
        chunks = chunk_text(text)
        if not chunks:
            return 0
        self._collection.upsert(
            ids=[f"{doc_id}:{i}" for i in range(len(chunks))],
            embeddings=self._embedder.embed_documents([f"{title}\n{c}" for c in chunks]),
            documents=chunks,
            metadatas=[{"doc_id": doc_id, "title": title, "kind": kind} for _ in chunks],
        )
        return len(chunks)

    def remove(self, doc_id: int) -> None:
        self._collection.delete(where={"doc_id": doc_id})

    def count(self) -> int:
        return self._collection.count()

    def search(self, query: str, k: int = 4, min_similarity: float = MIN_EVIDENCE) -> list[Evidence]:
        if not query.strip() or self._collection.count() == 0:
            return []
        result = self._collection.query(query_embeddings=[self._embedder.embed_query(query)],
                                        n_results=min(k * 3, self._collection.count()),
                                        include=["documents", "metadatas", "distances"])
        found, per_doc = [], {}
        for text, meta, distance in zip(result["documents"][0], result["metadatas"][0], result["distances"][0],
                                        strict=True):
            similarity = round(1 - distance, 3)
            if similarity < min_similarity or per_doc.get(meta["doc_id"], 0) >= 2:  # variety: at most 2 per document
                continue
            per_doc[meta["doc_id"]] = per_doc.get(meta["doc_id"], 0) + 1
            found.append(Evidence(int(meta["doc_id"]), str(meta["title"]), str(meta["kind"]), text, similarity))
        return found[:k]

    def check_claims(self, body: str, evidence: Sequence[Evidence]) -> list[Claim]:
        """Each sentence that states something about the company, and whether the documents back it."""
        sentences = claim_sentences(body)
        if not sentences:
            return []
        pool = list(evidence)
        for sentence in sentences:  # a claim may be backed by a part of the documents the pitch did not retrieve
            pool.extend(self.search(sentence, k=2, min_similarity=SUPPORTED))
        if not pool:
            return [Claim(s, False, None, 0.0) for s in sentences]
        claims_m = _unit(self._embedder.embed_documents(sentences))
        pool_m = _unit(self._embedder.embed_documents([e.text for e in pool]))
        scores = claims_m @ pool_m.T
        claims = []
        for i, sentence in enumerate(sentences):
            best = int(scores[i].argmax())
            similarity = round(float(scores[i][best]), 3)
            supported = similarity >= SUPPORTED
            claims.append(Claim(sentence, supported, pool[best].title if supported else None, similarity))
        return claims


def format_evidence(evidence: Sequence[Evidence]) -> str:
    """The evidence block a drafting prompt gets: numbered, titled excerpts."""
    if not evidence:
        return "none: do not mention any past project, client, number or price"
    return "\n".join(f"[{i}] {e.title} ({e.kind.replace('_', ' ')}): {' '.join(e.text.split())[:600]}"
                     for i, e in enumerate(evidence, 1))


def _unit(vectors: list[list[float]]) -> np.ndarray:
    matrix = np.asarray(vectors, dtype=np.float32)
    return matrix / np.linalg.norm(matrix, axis=1, keepdims=True).clip(min=1e-9)
