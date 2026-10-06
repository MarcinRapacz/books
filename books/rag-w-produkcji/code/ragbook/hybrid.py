"""Lexical retrieval (BM25), rank fusion, diversification and the retriever the project settles on.

Three layers:

1. `tokenize` / `make_tokenizer` - the cheap Polish analyzer: lowercase, split on anything that is not a
   letter or a digit, optionally truncate every token to N characters (poor man's stemming).
2. `BM25Index` (rank_bm25, in process) and `QdrantHybridIndex` (named dense + sparse vectors in Qdrant,
   fused server-side with `FusionQuery`). They answer the same question in two different places.
3. `rrf_fuse` / `weighted_fuse`, `cap_per_section` / `mmr`, and `project_retriever`, which wires a dense
   index, a lexical index, a fusion rule and an optional cross-encoder into one `(question, k) -> list[Chunk]`.

Run everything from the `code/` directory: `../.venv/bin/python experiments/03_fusion.py`.
"""
from __future__ import annotations

import re
from collections.abc import Callable, Sequence

import numpy as np

from .corpus import Chunk
from .embed import Embedder
from .store import DenseIndex

# Runs of letters (any alphabet, so Polish diacritics survive) or runs of digits. Everything else is a
# separator, which means `clear_tool_uses_20250919` becomes [clear, tool, uses, 20250919] and
# `metadata.user_id` becomes [metadata, user, id].
_TOKEN = re.compile(r"[^\W\d_]+|\d+", re.UNICODE)

Tokenizer = Callable[[str], list[str]]


def tokenize(text: str) -> list[str]:
    """Lowercase and split on non-letters/non-digits. No stemming, no stop-word list."""
    return _TOKEN.findall(text.lower())


def make_tokenizer(stem_to: int | None = None) -> Tokenizer:
    """Tokenizer that optionally truncates every token to `stem_to` characters.

    Polish inflection lives in the suffix, so cutting it off is a crude but free substitute for a
    lemmatizer: `wektorowych`, `wektorowy` and `wektorami` all collapse to `wektor` at stem_to=6.
    """
    if stem_to is None:
        return tokenize
    return lambda text: [t[:stem_to] for t in _TOKEN.findall(text.lower())]


class BM25Index:
    """Okapi BM25 over the chunk texts, with the same `search(query, k) -> list[Chunk]` shape as DenseIndex."""

    def __init__(self, chunks: list[Chunk], tokenizer: Tokenizer = tokenize,
                 k1: float = 1.5, b: float = 0.75):
        from rank_bm25 import BM25Okapi
        self.chunks = chunks
        self.tokenize = tokenizer
        self.bm25 = BM25Okapi([tokenizer(c.text) for c in chunks], k1=k1, b=b)

    def search(self, query: str, k: int = 5) -> list[Chunk]:
        scores = self.bm25.get_scores(self.tokenize(query))
        order = np.argsort(-scores)[:k]
        out = []
        for i in order:
            c = self.chunks[int(i)]
            out.append(Chunk(c.id, c.chapter, c.section, c.text, {**c.meta, "score": float(scores[i])}))
        return out


def _key(c: Chunk) -> str:
    return c.id


def rrf_fuse(rankings: Sequence[Sequence[Chunk]], k: int = 60,
             weights: Sequence[float] | None = None) -> list[Chunk]:
    """Reciprocal rank fusion: every chunk scores sum_i w_i / (k + rank_i), ranks starting at 1.

    Operates on positions, not on scores, so a cosine in [0.8, 0.93] and a BM25 score in [0, 30] can be
    combined without normalisation. `k` damps the difference between the top positions.
    """
    weights = list(weights) if weights is not None else [1.0] * len(rankings)
    fused: dict[str, float] = {}
    seen: dict[str, Chunk] = {}
    for ranking, w in zip(rankings, weights):
        for rank, c in enumerate(ranking, start=1):
            fused[_key(c)] = fused.get(_key(c), 0.0) + w / (k + rank)
            seen.setdefault(_key(c), c)
    order = sorted(fused, key=lambda key: -fused[key])
    return [Chunk(seen[key].id, seen[key].chapter, seen[key].section, seen[key].text,
                  {**seen[key].meta, "score": fused[key]}) for key in order]


def minmax(values: list[float]) -> list[float]:
    """Scale a list of scores to [0, 1]; a flat list becomes all ones."""
    lo, hi = min(values), max(values)
    if hi - lo < 1e-12:
        return [1.0] * len(values)
    return [(v - lo) / (hi - lo) for v in values]


def weighted_fuse(rankings: Sequence[Sequence[Chunk]], weights: Sequence[float]) -> list[Chunk]:
    """Weighted sum of min-max normalised scores; chunks missing from a ranking contribute 0 there."""
    fused: dict[str, float] = {}
    seen: dict[str, Chunk] = {}
    for ranking, w in zip(rankings, weights):
        if not ranking:
            continue
        norm = minmax([c.meta.get("score", 0.0) for c in ranking])
        for c, value in zip(ranking, norm):
            fused[_key(c)] = fused.get(_key(c), 0.0) + w * value
            seen.setdefault(_key(c), c)
    order = sorted(fused, key=lambda key: -fused[key])
    return [Chunk(seen[key].id, seen[key].chapter, seen[key].section, seen[key].text,
                  {**seen[key].meta, "score": fused[key]}) for key in order]


class HybridIndex:
    """Dense + BM25 fused in process. `pool` candidates are taken from each arm before fusion."""

    def __init__(self, dense: DenseIndex, lexical: BM25Index, method: str = "rrf",
                 rrf_k: int = 60, weights: Sequence[float] = (0.5, 0.5), pool: int = 50):
        self.dense, self.lexical = dense, lexical
        self.method, self.rrf_k, self.weights, self.pool = method, rrf_k, tuple(weights), pool

    def search(self, query: str, k: int = 5) -> list[Chunk]:
        limit = max(k, self.pool)
        arms = [self.dense.search(query, limit), self.lexical.search(query, limit)]
        if self.method == "rrf":
            fused = rrf_fuse(arms, k=self.rrf_k, weights=self.weights)
        elif self.method == "weighted":
            fused = weighted_fuse(arms, self.weights)
        else:
            raise ValueError(f"unknown fusion method: {self.method}")
        return fused[:k]


class QdrantHybridIndex:
    """One Qdrant collection with two named vectors (`dense`, `sparse`), fused server-side.

    The sparse side is a BM25 bag of term ids produced by fastembed's `Qdrant/bm25` model (10 MB, no
    neural network - it is an IDF-weighted tokenizer). The collection declares
    `modifier=models.Modifier.IDF`, which makes Qdrant apply the inverse document frequency at query time.

    `language` selects the stop-word list and the Snowball stemmer. fastembed supports 18 languages and
    Polish is not one of them, so a Polish corpus runs with `disable_stemmer=True`.
    """

    def __init__(self, embedder: Embedder, chunks: list[Chunk], collection: str = "hybrid",
                 sparse_model: str = "Qdrant/bm25", language: str = "english",
                 disable_stemmer: bool = True):
        from fastembed import SparseTextEmbedding
        from qdrant_client import QdrantClient, models

        self.chunks = chunks
        self.embedder = embedder
        self.collection = collection
        self.models = models
        self.sparse = SparseTextEmbedding(model_name=sparse_model, language=language,
                                          disable_stemmer=disable_stemmer)
        dense_vecs = embedder.embed_passages([c.text for c in chunks])
        sparse_vecs = list(self.sparse.embed([c.text for c in chunks]))

        self.client = QdrantClient(":memory:")
        self.client.create_collection(
            collection_name=collection,
            vectors_config={"dense": models.VectorParams(size=dense_vecs.shape[1],
                                                         distance=models.Distance.COSINE)},
            sparse_vectors_config={"sparse": models.SparseVectorParams(modifier=models.Modifier.IDF)},
        )
        self.client.upload_points(
            collection_name=collection,
            points=[
                models.PointStruct(
                    id=i,
                    vector={"dense": dense_vecs[i].tolist(),
                            "sparse": models.SparseVector(indices=sv.indices.tolist(),
                                                          values=sv.values.tolist())},
                    payload={"chapter": c.chapter, "section": c.section, **c.meta},
                )
                for i, (c, sv) in enumerate(zip(chunks, sparse_vecs))
            ],
        )

    def _to_chunks(self, points) -> list[Chunk]:
        out = []
        for p in points:
            c = self.chunks[int(p.id)]
            out.append(Chunk(c.id, c.chapter, c.section, c.text, {**c.meta, "score": float(p.score)}))
        return out

    def search(self, query: str, k: int = 5, pool: int = 50, rrf_k: int | None = 60) -> list[Chunk]:
        models = self.models
        qv = self.embedder.embed_queries([query])[0]
        qs = next(iter(self.sparse.query_embed(query)))
        limit = max(k, pool)
        res = self.client.query_points(
            collection_name=self.collection,
            prefetch=[
                models.Prefetch(query=qv.tolist(), using="dense", limit=limit),
                models.Prefetch(query=models.SparseVector(indices=qs.indices.tolist(),
                                                          values=qs.values.tolist()),
                                using="sparse", limit=limit),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF) if rrf_k is None
            else models.RrfQuery(rrf=models.Rrf(k=rrf_k)),
            limit=k,
        ).points
        return self._to_chunks(res)

    def search_arm(self, query: str, k: int, using: str) -> list[Chunk]:
        """One arm only, for checking that the server-side fusion matches our own implementation."""
        models = self.models
        if using == "dense":
            q = self.embedder.embed_queries([query])[0].tolist()
        else:
            qs = next(iter(self.sparse.query_embed(query)))
            q = models.SparseVector(indices=qs.indices.tolist(), values=qs.values.tolist())
        res = self.client.query_points(collection_name=self.collection, query=q, using=using,
                                       limit=k).points
        return self._to_chunks(res)


def cap_per_section(chunks: Sequence[Chunk], k: int, max_per_section: int = 2) -> list[Chunk]:
    """Keep the ranking, but never let one section take more than `max_per_section` of the top-k slots."""
    counts: dict[tuple[int, str], int] = {}
    kept, spare = [], []
    for c in chunks:
        if counts.get(c.key, 0) < max_per_section:
            counts[c.key] = counts.get(c.key, 0) + 1
            kept.append(c)
            if len(kept) == k:
                return kept
        else:
            spare.append(c)
    return (kept + spare)[:k]


def mmr(chunks: Sequence[Chunk], vectors: np.ndarray, query_vector: np.ndarray, k: int,
        lambda_mult: float = 0.5, relevance: np.ndarray | None = None) -> list[Chunk]:
    """Maximal marginal relevance over unit-normalised vectors aligned with `chunks`.

    Relevance defaults to the cosine against the query. Pass `relevance` (min-max normalised to [0, 1])
    to keep the ranking of an earlier stage - e.g. the cross-encoder score - as the relevance term.
    """
    if not len(chunks):
        return []
    rel = vectors @ query_vector if relevance is None else np.asarray(relevance, dtype=np.float32)
    selected: list[int] = []
    remaining = list(range(len(chunks)))
    while remaining and len(selected) < k:
        if not selected:
            best = max(remaining, key=lambda i: rel[i])
        else:
            sims = vectors[remaining] @ vectors[selected].T
            worst = sims.max(axis=1)
            scores = lambda_mult * rel[remaining] - (1 - lambda_mult) * worst
            best = remaining[int(np.argmax(scores))]
        selected.append(best)
        remaining.remove(best)
    return [chunks[i] for i in selected]


class ProjectRetriever:
    """The retrieval stack this chapter settles on. Callable as `(question, k) -> list[Chunk]`.

    mode: "dense" | "bm25" | "hybrid". `rerank` turns on the cross-encoder over the top `pool` candidates,
    `max_per_section` caps how many chunks one section may occupy in the returned list, and
    `diversify="mmr"` replaces that cap with MMR over the dense vectors.

    The defaults are the configuration chapter 3 settles on and measures: hybrid RRF (k=60) over a BM25
    arm with 5-character truncation, cross-encoder rerank of the top 20, one chunk per section.
    """

    def __init__(self, chunks: list[Chunk], embedder: Embedder | None = None, mode: str = "hybrid",
                 rerank: bool = True, reranker_model: str | None = None, pool: int = 20,
                 rrf_k: int = 60, stem_to: int | None = 5, max_per_section: int | None = 1,
                 diversify: str | None = None, mmr_lambda: float = 0.7):
        self.embedder = embedder or Embedder()
        self.chunks = chunks
        self.mode, self.pool, self.rrf_k = mode, pool, rrf_k
        self.max_per_section, self.diversify, self.mmr_lambda = max_per_section, diversify, mmr_lambda
        self.dense = DenseIndex(self.embedder, chunks) if mode in ("dense", "hybrid") else None
        self.lexical = (BM25Index(chunks, make_tokenizer(stem_to))
                        if mode in ("bm25", "hybrid") else None)
        self.hybrid = (HybridIndex(self.dense, self.lexical, rrf_k=rrf_k, pool=max(pool, 50))
                       if mode == "hybrid" else None)
        self.reranker = None
        if rerank:
            from .rerank import CrossEncoderReranker
            self.reranker = CrossEncoderReranker(reranker_model) if reranker_model \
                else CrossEncoderReranker()
        self._vectors = None

    def _vecs_for(self, chunks: Sequence[Chunk]) -> np.ndarray:
        if self._vectors is None:
            self._vectors = self.embedder.embed_passages([c.text for c in self.chunks])
        pos = {c.id: i for i, c in enumerate(self.chunks)}
        return self._vectors[[pos[c.id] for c in chunks]]

    def candidates(self, question: str, n: int) -> list[Chunk]:
        if self.mode == "dense":
            return self.dense.search(question, n)
        if self.mode == "bm25":
            return self.lexical.search(question, n)
        return self.hybrid.search(question, n)

    def __call__(self, question: str, k: int = 5) -> list[Chunk]:
        n = max(k, self.pool) if self.reranker else k
        got = self.candidates(question, n)
        if self.reranker:
            got = self.reranker.rerank(question, got, top_k=len(got))
        if self.diversify == "mmr":
            qv = self.embedder.embed_queries([question])[0]
            rel = np.asarray(minmax([c.meta.get("score", 0.0) for c in got]), dtype=np.float32) \
                if self.reranker else None
            got = mmr(got, self._vecs_for(got), qv, k, self.mmr_lambda, relevance=rel)
        elif self.max_per_section:
            got = cap_per_section(got, k, self.max_per_section)
        return got[:k]

    def close(self) -> None:
        if self.reranker is not None:
            self.reranker.close()
            self.reranker = None


def project_retriever(chunks: list[Chunk], embedder: Embedder | None = None, mode: str = "hybrid",
                      rerank: bool = True, **kwargs) -> ProjectRetriever:
    """Factory kept as a function so chapter 4 can write `retrieve = project_retriever(chunks)`."""
    return ProjectRetriever(chunks, embedder=embedder, mode=mode, rerank=rerank, **kwargs)
