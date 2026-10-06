"""Chapter 8: caches in front of the pipeline.

1. Exact-match cache for query embeddings: hit rate under different traffic distributions, and the real
   cost of a miss (encoding time) versus a hit (dictionary lookup).
2. Semantic answer cache: the similarity of 20 labelled question pairs (10 with the same answer, 10 with
   different answers) decides what a threshold actually buys and what it breaks.

Run from the `code/` directory:  ../.venv/bin/python experiments/08_cache.py
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from ragbook.cache import QueryEmbeddingCache, SemanticAnswerCache, load_pairs, normalize_question
from ragbook.embed import Embedder

PAIRS_PATH = Path("data/queries_08.jsonl")


def question_pool(questions: list[str], size: int) -> list[str]:
    """A realistic pool: the real questions plus wording variants, so the cache has a long tail to miss on."""
    pool = list(questions)
    i = 0
    while len(pool) < size:
        pool.append(f"{questions[i % len(questions)]} (wariant {i // len(questions) + 1})")
        i += 1
    return pool[:size]


def zipf_stream(questions: list[str], n: int, exponent: float, seed: int = 7) -> list[str]:
    """Synthetic query stream: question i is drawn with probability proportional to 1/(i+1)**exponent."""
    rng = np.random.default_rng(seed)
    weights = np.array([1.0 / (i + 1) ** exponent for i in range(len(questions))])
    weights /= weights.sum()
    return [questions[i] for i in rng.choice(len(questions), size=n, p=weights)]


def main() -> None:
    pairs = load_pairs(PAIRS_PATH)
    questions = [q for pair in pairs for q in pair[:2]]
    print(f"pairs: {len(pairs)}  questions: {len(questions)}")

    embedder = Embedder()

    # --- 1. embedding cache: hit rate vs traffic shape (a simulation: the shape is an assumption) ---
    pool = question_pool(questions, 1000)
    embedder.cache = False      # the disk cache would hide the cost of a miss in this simulation
    print("\n=== exact-match query embedding cache (pool of 1000 distinct questions, 2000 requests) ===")
    print("| Rozkład ruchu | Zapytań | Unikalnych | Trafienia | Hit rate |")
    print("|---|---|---|---|---|")
    for label, exponent in [("jednostajny", 0.0), ("Zipf a=0,8", 0.8), ("Zipf a=1,2", 1.2), ("Zipf a=2,0", 2.0)]:
        cache = QueryEmbeddingCache(embedder)
        stream = zipf_stream(pool, 2000, exponent)
        for q in stream:
            cache.embed(q)
        print(f"| {label} | {cache.stats.total} | {len(set(stream))} | {cache.stats.hits} "
              f"| {cache.stats.hit_rate:.2f} |".replace("0.", "0,"))

    embedder.cache = True
    # Surface variation: the same question typed with different case/whitespace/punctuation.
    variants = [questions[0], questions[0].upper(), f"  {questions[0]}  ", questions[0].rstrip("?")]
    cache = QueryEmbeddingCache(embedder)
    for v in variants:
        cache.embed(v)
    print(f"\nnormalisation: {len(set(variants))} distinct strings -> "
          f"{len({normalize_question(v) for v in variants})} cache keys, hits {cache.stats.hits}/{len(variants)}")

    # Paraphrases never hit an exact-match cache, by construction.
    para = QueryEmbeddingCache(embedder)
    for a, b, same in pairs:
        if same:
            para.embed(a)
            para.embed(b)
    print(f"paraphrase pairs through the exact cache: hits {para.stats.hits} / {para.stats.total}")

    # --- cost of a miss vs a hit, measured ---
    model = embedder.model
    prefix = embedder.query_prefix
    warm = model.encode([prefix + questions[0]], normalize_embeddings=True)
    miss_ms, hit_ms = [], []
    hot = QueryEmbeddingCache(embedder)
    hot.embed(questions[0])
    for q in questions:
        t0 = time.perf_counter()
        model.encode([prefix + q], normalize_embeddings=True)
        miss_ms.append((time.perf_counter() - t0) * 1000)
        t0 = time.perf_counter()
        hot.embed(questions[0])
        hit_ms.append((time.perf_counter() - t0) * 1000)
    print(f"\nembedding a query (cache miss): median {np.median(miss_ms):.1f} ms, "
          f"p95 {np.percentile(miss_ms, 95):.1f} ms   (warm-up vector shape {warm.shape})")
    print(f"cache hit: median {np.median(hit_ms) * 1000:.0f} us, p95 {np.percentile(hit_ms, 95) * 1000:.0f} us")

    # --- 2. semantic answer cache ---
    answer_cache = SemanticAnswerCache(embedder, threshold=0.95)
    audit = answer_cache.audit(pairs)
    same, diff = audit["same"], audit["diff"]
    # base rate: how similar are two *unrelated* questions under this model?
    vecs = embedder.embed_queries(questions)
    sim_matrix = vecs @ vecs.T
    off = sim_matrix[np.triu_indices(len(questions), k=1)]
    print(f"\nbaseline similarity of two arbitrary questions from the set (n={len(off)}): "
          f"median {np.median(off):.3f}, p95 {np.percentile(off, 95):.3f}, max {off.max():.3f}")

    print("\n=== semantic answer cache: similarity of labelled pairs ===")
    print(f"same answer     (n={len(same)}): min {min(same):.3f}  median {np.median(same):.3f}  max {max(same):.3f}")
    print(f"different answer(n={len(diff)}): min {min(diff):.3f}  median {np.median(diff):.3f}  max {max(diff):.3f}")

    print("\n| Próg | Trafienia użyteczne (z 10) | Trafienia błędne (z 10) |")
    print("|---|---|---|")
    for row in audit["rows"]:
        print(f"| {row['threshold']:.2f} | {row['useful_hits']} | {row['wrong_hits']} |".replace(".", ","))

    print("\n=== the dangerous pairs (different answer, similarity >= 0,90) ===")
    for (a, b, flag), sim in zip(pairs, audit["sims"]):
        if not flag and sim >= 0.90:
            print(f"  {sim:.3f}  {a}  ||  {b}")

    print("\n=== the paraphrases an exact cache misses but a semantic cache catches at 0,95 ===")
    for (a, b, flag), sim in zip(pairs, audit["sims"]):
        if flag and sim >= 0.95:
            print(f"  {sim:.3f}  {a}  ||  {b}")

    # --- end-to-end behaviour of the answer cache on a small stream ---
    cache = SemanticAnswerCache(embedder, threshold=0.95)
    cache.put(pairs[0][0], "HNSW to wielowarstwowy graf nawigowalny...", groups=["public"],
              doc_hashes=("7ab3",))
    hit, score = cache.lookup(pairs[0][1], groups=["public"])
    print(f"\nlookup('{pairs[0][1]}') -> {'HIT' if hit else 'MISS'} at {score:.3f}")
    stale, score2 = cache.lookup(pairs[0][1], groups=["public"], live_hashes={"07-bazy-wektorowe.md": "ffff"})
    print(f"the same lookup after the source document changed -> {'HIT' if stale else 'MISS'} at {score2:.3f}")


if __name__ == "__main__":
    main()
