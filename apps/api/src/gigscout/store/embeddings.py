"""Turns text into vectors ("GPS coordinates for meaning"). Uses FastEmbed (ONNX, CPU-only, no PyTorch)."""

from collections.abc import Sequence
from typing import Protocol


class Embedder(Protocol):
    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class FastEmbedder:
    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._model = None  # loaded lazily: the first call downloads ~130 MB

    def _load(self):
        if self._model is None:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(model_name=self._model_name)
        return self._model

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [vector.tolist() for vector in self._load().embed(list(texts))]

    def embed_query(self, text: str) -> list[float]:
        return next(iter(self._load().query_embed(text))).tolist()
