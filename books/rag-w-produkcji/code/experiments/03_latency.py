"""Reranking latency: both cross-encoders, 20 and 50 candidates, measured back to back on one device.

`03_rerank.py` measures quality and times the runs it makes anyway, but those runs are minutes apart
and the machine's load changes between them. This script times both models on the same questions, one
model in memory at a time, so the ratio between them means something.

The device is the first argument (`cpu` or `cuda`); without it sentence-transformers picks whatever
it finds. Quality metrics do not depend on the device, only these numbers do.

Run from the `code/` directory:  ../.venv/bin/python experiments/03_latency.py cuda
"""
from __future__ import annotations

import sys
import time

from ragbook.corpus import fixed_window_chunks, load_sections
from ragbook.embed import Embedder
from ragbook.evaluate import load_golden
from ragbook.hybrid import BM25Index, HybridIndex, make_tokenizer
from ragbook.rerank import BGE, MMARCO, CrossEncoderReranker, free_mb
from ragbook.store import DenseIndex

CHUNKER = lambda sections, tokenizer: fixed_window_chunks(sections, tokenizer, window=128, overlap=32)
POOLS, STEM, RRF_K, N_QUESTIONS = (20, 50), 5, 60, 20
BGE_MIN_FREE_MB = 5000


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(p * len(ordered)))]


def main() -> None:
    device = sys.argv[1] if len(sys.argv) > 1 else None
    embedder = Embedder()
    chunks = CHUNKER(load_sections(), embedder.tokenizer)
    questions = [q for q in load_golden() if q.relevant][:N_QUESTIONS]

    dense = DenseIndex(embedder, chunks)
    lexical = BM25Index(chunks, make_tokenizer(STEM))
    hybrid = HybridIndex(dense, lexical, method="rrf", rrf_k=RRF_K, pool=50)

    print("=== First stage, without any reranker (CPU: BM25 and RRF never touch the GPU) ===")
    print("| Etap | p50 [ms] | p95 [ms] |")
    print("|---|---|---|")
    for name, search in (("gęsty", dense.search), ("BM25", lexical.search), ("hybryda", hybrid.search)):
        times = []
        for q in questions:
            t0 = time.perf_counter()
            search(q.question, 20)
            times.append(1000 * (time.perf_counter() - t0))
        print(f"| {name}, top-20 | {percentile(times, 0.5):.0f} | {percentile(times, 0.95):.0f} |"
              .replace(".", ","))

    pools = {pool: {q.id: hybrid.search(q.question, pool) for q in questions} for pool in POOLS}
    del dense, lexical, hybrid

    print(f"\n=== Cross-encoder latency, {len(questions)} questions, device={device or 'auto'} ===")
    print("| Model | Kandydatów | p50 [ms] | p95 [ms] | ms/para |")
    print("|---|---|---|---|---|")
    for model_name in (MMARCO, BGE):
        if model_name == BGE and device == "cpu" and free_mb() < BGE_MIN_FREE_MB:
            print(f"| {model_name} | – | – | – | brak pamięci ({free_mb()} MB) |")
            continue
        reranker = CrossEncoderReranker(model_name, device=device)
        reranker.rerank(questions[0].question, pools[20][questions[0].id], top_k=5)  # warm-up
        for pool in POOLS:
            times = []
            for q in questions:
                _, dt = reranker.timed_rerank(q.question, pools[pool][q.id], top_k=5)
                times.append(1000 * dt)
            p50 = percentile(times, 0.5)
            print(f"| `{model_name.split('/')[-1]}` | {pool} | {p50:.0f} "
                  f"| {percentile(times, 0.95):.0f} | {p50 / pool:.0f} |".replace(".", ","))
        reranker.close()


if __name__ == "__main__":
    main()
