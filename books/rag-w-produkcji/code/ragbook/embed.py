"""Embedding wrapper with an on-disk cache, so repeated experiments do not recompute vectors.

Default model: intfloat/multilingual-e5-small (384 dims, 512 tokens). E5 expects the prefixes
`query: ` and `passage: `; the wrapper adds them for you.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"
DEFAULT_MODEL = "intfloat/multilingual-e5-small"

_PREFIXES = {
    "intfloat/multilingual-e5-small": ("query: ", "passage: "),
    "intfloat/multilingual-e5-base": ("query: ", "passage: "),
    "intfloat/multilingual-e5-large": ("query: ", "passage: "),
}


class Embedder:
    def __init__(self, model_name: str = DEFAULT_MODEL, cache: bool = True):
        from sentence_transformers import SentenceTransformer
        self.model_name = model_name
        self.model = SentenceTransformer(model_name)
        self.query_prefix, self.passage_prefix = _PREFIXES.get(model_name, ("", ""))
        self.cache = cache
        self.dim = self.model.get_embedding_dimension()

    @property
    def tokenizer(self):
        return self.model.tokenizer

    def _cached(self, texts: list[str], kind: str) -> np.ndarray:
        h = hashlib.sha256((self.model_name + "|" + kind + "|" + "\x00".join(texts)).encode()).hexdigest()[:24]
        path = CACHE_DIR / f"{h}.npy"
        if self.cache and path.exists():
            return np.load(path)
        prefix = self.query_prefix if kind == "query" else self.passage_prefix
        vecs = self.model.encode([prefix + t for t in texts], normalize_embeddings=True,
                                 batch_size=32, show_progress_bar=False)
        vecs = np.asarray(vecs, dtype=np.float32)
        if self.cache:
            CACHE_DIR.mkdir(exist_ok=True)
            np.save(path, vecs)
        return vecs

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        return self._cached(texts, "passage")

    def embed_queries(self, texts: list[str]) -> np.ndarray:
        return self._cached(texts, "query")
