from __future__ import annotations

import hashlib

import numpy as np
import pytest


class FakeEmbedder:
    """Deterministic offline embedder: identical text -> identical unit vector."""

    model_name = "fake"
    dim = 16

    def __init__(self) -> None:
        self.passages_embedded = 0

    def _vec(self, text: str) -> np.ndarray:
        seed = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:4], "little")
        v = np.random.default_rng(seed).normal(size=self.dim).astype(np.float32)
        return v / np.linalg.norm(v)

    def embed_queries(self, texts: list[str]) -> np.ndarray:
        return np.vstack([self._vec(t) for t in texts])

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        self.passages_embedded += len(texts)
        return np.vstack([self._vec(t) for t in texts])


@pytest.fixture
def embedder() -> FakeEmbedder:
    return FakeEmbedder()
