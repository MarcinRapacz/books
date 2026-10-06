"""Two caches in front of the pipeline: exact-match query embeddings and a semantic answer cache.

The embedding cache is safe by construction (a hit returns the vector of the very same string).
The answer cache is not: a hit returns an answer written for a *different, similar* question, so the
threshold is a risk decision, not a tuning knob. `SemanticAnswerCache.audit()` measures that risk.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

_WS = re.compile(r"\s+")


def normalize_question(q: str) -> str:
    """Trivial normalisation before the exact-match lookup: case, whitespace, trailing punctuation."""
    return _WS.sub(" ", q.strip().lower()).rstrip("?!. ")


def query_key(q: str, model_name: str) -> str:
    """Cache key. The model name is part of it: vectors from two models are not interchangeable."""
    return hashlib.sha256(f"{model_name}|{normalize_question(q)}".encode("utf-8")).hexdigest()[:24]


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0

    @property
    def total(self) -> int:
        return self.hits + self.misses

    @property
    def hit_rate(self) -> float:
        return self.hits / self.total if self.total else 0.0


class QueryEmbeddingCache:
    """Exact-match cache for query vectors, optionally persisted to a single .npz file."""

    def __init__(self, embedder, path: Path | None = None, max_entries: int = 50_000):
        self.embedder = embedder
        self.path = Path(path) if path else None
        self.max_entries = max_entries
        self.stats = CacheStats()
        self._store: dict[str, np.ndarray] = {}
        if self.path and self.path.exists():
            with np.load(self.path) as data:
                self._store = {k: data[k] for k in data.files}

    def embed(self, question: str) -> np.ndarray:
        key = query_key(question, self.embedder.model_name)
        vec = self._store.get(key)
        if vec is not None:
            self.stats.hits += 1
            return vec
        self.stats.misses += 1
        vec = self.embedder.embed_queries([question])[0]
        if len(self._store) < self.max_entries:
            self._store[key] = vec
        return vec

    def save(self) -> None:
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            np.savez(self.path, **self._store)


@dataclass
class AnswerEntry:
    question: str
    answer: str
    vector: np.ndarray
    created_at: float = field(default_factory=time.time)
    doc_hashes: tuple[str, ...] = ()     # hashes of the documents the answer was grounded in


class SemanticAnswerCache:
    """Answer cache keyed by question *meaning*: a hit is any earlier question above `threshold`.

    Entries expire after `ttl` seconds and are invalidated when the documents they cite change.
    """

    def __init__(self, embedder, threshold: float = 0.95, ttl: float = 24 * 3600):
        self.embedder = embedder
        self.threshold = threshold
        self.ttl = ttl
        self.stats = CacheStats()
        self.entries: list[AnswerEntry] = []
        self._matrix: np.ndarray | None = None

    def _vector(self, question: str) -> np.ndarray:
        return self.embedder.embed_queries([question])[0]

    def lookup(self, question: str, live_hashes: dict[str, str] | None = None) -> tuple[AnswerEntry | None, float]:
        """Return the best entry above the threshold (or None) and the similarity that decided it."""
        self._evict()
        if not self.entries:
            self.stats.misses += 1
            return None, 0.0
        sims = self._matrix @ self._vector(question)
        best = int(np.argmax(sims))
        score = float(sims[best])
        entry = self.entries[best]
        if score < self.threshold or not self._fresh(entry, live_hashes):
            self.stats.misses += 1
            return None, score
        self.stats.hits += 1
        return entry, score

    def put(self, question: str, answer: str, doc_hashes: tuple[str, ...] = ()) -> None:
        self.entries.append(AnswerEntry(question, answer, self._vector(question), doc_hashes=doc_hashes))
        self._rebuild()

    def _fresh(self, entry: AnswerEntry, live_hashes: dict[str, str] | None) -> bool:
        if live_hashes is None or not entry.doc_hashes:
            return True
        return all(h in live_hashes.values() for h in entry.doc_hashes)

    def _evict(self) -> None:
        now = time.time()
        keep = [e for e in self.entries if now - e.created_at < self.ttl]
        if len(keep) != len(self.entries):
            self.entries = keep
            self._rebuild()

    def _rebuild(self) -> None:
        self._matrix = np.vstack([e.vector for e in self.entries]) if self.entries else None

    def audit(self, pairs: list[tuple[str, str, bool]]) -> dict:
        """Measure the cache's error rate on labelled question pairs.

        `pairs` is [(question_a, question_b, same_answer)]. For every threshold we report how many
        same-answer pairs are caught (a useful hit) and how many different-answer pairs are caught
        (a wrong answer served from cache).
        """
        texts = [q for pair in pairs for q in pair[:2]]
        vecs = self.embedder.embed_queries(texts)
        sims = [float(vecs[2 * i] @ vecs[2 * i + 1]) for i in range(len(pairs))]
        same = [s for s, (_, _, flag) in zip(sims, pairs) if flag]
        diff = [s for s, (_, _, flag) in zip(sims, pairs) if not flag]
        rows = []
        for t in (0.85, 0.90, 0.92, 0.95, 0.97, 0.99):
            rows.append({"threshold": t,
                         "useful_hits": sum(1 for s in same if s >= t),
                         "wrong_hits": sum(1 for s in diff if s >= t)})
        return {"sims": sims, "same": same, "diff": diff, "rows": rows}


def load_pairs(path: Path) -> list[tuple[str, str, bool]]:
    """Read labelled question pairs from JSONL: {"a": ..., "b": ..., "same_answer": true}."""
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            out.append((d["a"], d["b"], bool(d["same_answer"])))
    return out
