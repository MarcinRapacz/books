"""Cross-encoder reranking on top of the dense and the hybrid candidate list, with CPU latency.

One model is loaded at a time and dropped before the next one. bge-reranker-v2-m3 needs about 2.3 GB
resident, so it only runs when there is room:

    ../.venv/bin/python experiments/03_rerank.py            # mmarco-mMiniLMv2 only
    ../.venv/bin/python experiments/03_rerank.py bge        # bge-reranker-v2-m3 only

Run from the `code/` directory.
"""
from __future__ import annotations

import sys
import time

from ragbook.corpus import fixed_window_chunks, load_sections
from ragbook.embed import Embedder
from ragbook.evaluate import by_type, evaluate, load_golden
from ragbook.hybrid import BM25Index, HybridIndex, make_tokenizer
from ragbook.rerank import BGE, MMARCO, CrossEncoderReranker, free_mb
from ragbook.store import DenseIndex

CHUNKER = lambda sections, tokenizer: fixed_window_chunks(sections, tokenizer, window=128, overlap=32)
K, POOLS, STEM, RRF_K = 5, (20, 50), 5, 60
BGE_MIN_FREE_MB = 5000


def row(name: str, r: dict, extra: str = "") -> str:
    return (f"| {name} | {r['recall@5']:.2f} | {r['recall@20']:.2f} | {r['mrr@5']:.2f} "
            f"| {r['ndcg@5']:.2f} | {r['misses@5']} |{extra}").replace(".", ",")


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(p * len(ordered)))]


def main() -> None:
    embedder = Embedder()
    chunks = CHUNKER(load_sections(), embedder.tokenizer)
    golden = load_golden()
    questions = [q for q in golden if q.relevant]

    dense = DenseIndex(embedder, chunks)
    lexical = BM25Index(chunks, make_tokenizer(STEM))
    hybrid = HybridIndex(dense, lexical, method="rrf", rrf_k=RRF_K, pool=50)
    bases = {"gęsty": dense.search, "hybryda": hybrid.search}

    print("=== Without a reranker ===")
    print("| Wariant | recall@5 | recall@20 | MRR@5 | nDCG@5 | Bez trafienia |")
    print("|---|---|---|---|---|---|")
    for name, search in bases.items():
        print(row(f"{name}, bez rerankera", evaluate(search, golden, k=K, ks=(K, 20))))

    # Collect every candidate list once; the reranker then only sees text, not the index.
    # bge-reranker-v2-m3 is ~40x slower per pair than mMiniLM on CPU, so it only gets the hybrid arm.
    which = sys.argv[1] if len(sys.argv) > 1 else "mmarco"
    wanted = ["hybryda"] if which == "bge" else list(bases)
    pools = {(name, pool): {q.id: bases[name](q.question, pool) for q in questions}
             for name in wanted for pool in POOLS}

    model_name = {"mmarco": MMARCO, "bge": BGE}[which]
    if which == "bge":
        free = free_mb()
        print(f"\nfree memory: {free} MB (need {BGE_MIN_FREE_MB} MB for {BGE})")
        if free < BGE_MIN_FREE_MB:
            print("not enough memory, skipping bge-reranker-v2-m3")
            return
    del dense, lexical, hybrid, bases

    print(f"\n=== Reranking with {model_name} ===")
    t0 = time.perf_counter()
    reranker = CrossEncoderReranker(model_name)
    print(f"model loaded in {time.perf_counter() - t0:.1f} s, free memory now {free_mb()} MB")
    print("| Wariant | recall@5 | recall@20 | MRR@5 | nDCG@5 | Bez trafienia | p50 [ms] | p95 [ms] |")
    print("|---|---|---|---|---|---|---|---|")
    fixed = {}
    for (name, pool), cached in pools.items():
        times: list[float] = []
        reranked: dict[str, list] = {}
        for q in questions:
            out, dt = reranker.timed_rerank(q.question, cached[q.id], top_k=pool)
            times.append(1000 * dt)
            reranked[q.id] = out
        by_id = {q.question: reranked[q.id] for q in questions}
        result = evaluate(lambda question, k: by_id[question][:k], golden, k=K, ks=(K, 20))
        fixed[(name, pool)] = result
        print(row(f"{name} → rerank top-{pool}", result,
                  f" {percentile(times, 0.5):.0f} | {percentile(times, 0.95):.0f} |"))

    best = max(fixed, key=lambda key: fixed[key]["recall@5"])
    print(f"\nbest: {best[0]} → rerank top-{best[1]}")
    result = fixed[best]
    print("| Typ | recall@5 | MRR@5 |")
    print("|---|---|---|")
    r5, mr = by_type(result, "recall@5"), by_type(result, "mrr")
    for t in ("factual", "procedural", "comparative"):
        print(f"| {t} | {r5[t]:.2f} | {mr[t]:.2f} |".replace(".", ","))
    misses = [r["id"] for r in result["per_question"] if r["recall@5"] == 0]
    print(f"still missed: {misses}")

    reranker.close()
    print(f"after close: free memory {free_mb()} MB")


if __name__ == "__main__":
    main()
