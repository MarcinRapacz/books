"""Chapter 8: what one query costs and where its milliseconds go.

Cost: real chunk lengths (e5 tokenizer) -> prompt size for k=5 and k=10 -> USD per query and per 1000 queries
for claude-opus-5 and claude-haiku-4-5, at the prices published in September 2026.

Latency: measured locally for the stages we control (query embedding, Qdrant search at k=5/20, cross-encoder
reranking of 20 candidates), reported as percentiles. The LLM call is not measured here -- no API key.

Run from the `code/` directory:  ../.venv/bin/python experiments/08_cost_latency.py
"""
from __future__ import annotations

import gc
import statistics
import time
from pathlib import Path

import numpy as np
from qdrant_client import QdrantClient

from ragbook.cache import load_pairs
from ragbook.cost import PRICES, QueryCost, prompt_tokens
from ragbook.embed import Embedder
from ragbook.indexing import Index, chunk_document, load_documents
from ragbook.security import SYSTEM_POLICY
from ragbook.trace import percentiles

RERANKER = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
OUTPUT_TOKENS = 300      # assumption: a grounded answer with citations, measured against your own traffic


def main() -> None:
    questions = [q for pair in load_pairs(Path("data/queries_08.jsonl")) for q in pair[:2]]
    embedder = Embedder()
    tokenizer = embedder.tokenizer

    docs = load_documents()
    chunks = [c for d in docs for c in chunk_document(d, tokenizer)]
    lengths = [len(tokenizer(c.text, add_special_tokens=False)["input_ids"]) for c in chunks]
    sys_tokens = len(tokenizer(SYSTEM_POLICY, add_special_tokens=False)["input_ids"])
    q_tokens = [len(tokenizer(q, add_special_tokens=False)["input_ids"]) for q in questions]

    print(f"chunks: {len(chunks)}")
    print(f"chunk tokens: median {statistics.median(lengths):.0f}  mean {statistics.fmean(lengths):.0f}  "
          f"p90 {sorted(lengths)[int(0.9 * len(lengths))]}  max {max(lengths)}")
    print(f"system prompt: {sys_tokens} tokens;  question: median {statistics.median(q_tokens):.0f} tokens")

    chunk_tok = int(round(statistics.fmean(lengths)))
    q_tok = int(round(statistics.fmean(q_tokens)))

    print("\n=== cost per query (prices: platform.claude.com, September 2026) ===")
    print("| Model | k | Tokeny wejścia | Tokeny wyjścia | Koszt zapytania | Koszt 1000 zapytań |")
    print("|---|---|---|---|---|---|")
    rows = []
    for model in ("claude-opus-5", "claude-haiku-4-5"):
        for k in (5, 10):
            tin = prompt_tokens(sys_tokens, chunk_tok, k, q_tok)
            c = QueryCost(model, tin, OUTPUT_TOKENS)
            rows.append((model, k, tin, c))
            print(f"| `{model}` | {k} | {tin} | {OUTPUT_TOKENS} | ${c.total:.5f} | ${c.per_1k_queries():.2f} |")

    opus5 = next(c for m, k, _, c in rows if m == "claude-opus-5" and k == 5)
    print(f"\nshare of the k=5 opus bill: input {100 * opus5.parts['input'] / opus5.total:.0f}%, "
          f"output {100 * opus5.parts['output'] / opus5.total:.0f}%")

    reranked = QueryCost("claude-opus-5", prompt_tokens(sys_tokens, chunk_tok, 5, q_tok), OUTPUT_TOKENS)
    naive20 = QueryCost("claude-opus-5", prompt_tokens(sys_tokens, chunk_tok, 20, q_tok), OUTPUT_TOKENS)
    print(f"retrieve 20 -> rerank -> k=5: ${reranked.total:.5f} vs k=20 straight into the prompt: "
          f"${naive20.total:.5f} ({naive20.total / reranked.total:.1f}x)")

    base, write5m, read, _ = PRICES["claude-opus-5"]
    print(f"\nprompt caching: the system prompt is {sys_tokens} tokens, the minimum cacheable prefix is "
          f"512 for claude-opus-5 and 4096 for claude-haiku-4-5 -> nothing to cache here.")
    static = 20_000
    cached = QueryCost("claude-opus-5", prompt_tokens(0, chunk_tok, 5, q_tok), OUTPUT_TOKENS,
                       cached_tokens=static)
    uncached = QueryCost("claude-opus-5", prompt_tokens(static, chunk_tok, 5, q_tok), OUTPUT_TOKENS)
    print(f"a {static}-token static prefix: ${uncached.total:.5f} without cache vs ${cached.total:.5f} "
          f"with a cache hit (write costs ${static * write5m / 1e6:.4f} once)")

    # --- latency ---
    print("\n=== latency, measured locally ===")
    client = QdrantClient(":memory:")
    index = Index(client, "chunks", embedder, recreate=True)
    index.sync(chunks)

    model, prefix = embedder.model, embedder.query_prefix
    model.encode([prefix + questions[0]], normalize_embeddings=True)   # warm-up

    embed_ms, search5_ms, search20_ms = [], [], []
    candidates: list[tuple[str, list[str]]] = []
    for q in questions * 3:
        t0 = time.perf_counter()
        vec = model.encode([prefix + q], normalize_embeddings=True)[0]
        embed_ms.append((time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        client.query_points("chunks", query=vec.tolist(), limit=5)
        search5_ms.append((time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        res = client.query_points("chunks", query=vec.tolist(), limit=20).points
        search20_ms.append((time.perf_counter() - t0) * 1000)
        if len(candidates) < len(questions):
            candidates.append((q, [p.payload["text"] for p in res]))

    del embedder, index, model
    gc.collect()

    from sentence_transformers import CrossEncoder
    cross = CrossEncoder(RERANKER, max_length=512)
    cross.predict([(candidates[0][0], candidates[0][1][0])])                      # warm-up
    rerank_ms = []
    for q, texts in candidates:
        t0 = time.perf_counter()
        cross.predict([(q, t) for t in texts])
        rerank_ms.append((time.perf_counter() - t0) * 1000)

    print("| Etap | p50 [ms] | p90 [ms] | p95 [ms] | p99 [ms] |")
    print("|---|---|---|---|---|")
    for label, values in [("embedding zapytania", embed_ms), ("wyszukiwanie k=5", search5_ms),
                          ("wyszukiwanie k=20", search20_ms), ("reranking 20 kandydatów", rerank_ms)]:
        p = percentiles(values)
        print(f"| {label} | {p['p50']} | {p['p90']} | {p['p95']} | {p['p99']} |")

    local_p50 = percentiles(embed_ms)["p50"] + percentiles(search20_ms)["p50"] + percentiles(rerank_ms)["p50"]
    local_p95 = percentiles(embed_ms)["p95"] + percentiles(search20_ms)["p95"] + percentiles(rerank_ms)["p95"]
    print(f"\nretrieval budget (embedding + search k=20 + rerank): p50 {local_p50:.0f} ms, p95 {local_p95:.0f} ms")
    print(f"mean over {len(embed_ms)} queries -- reported as percentiles above, never as the mean "
          f"(mean embedding {np.mean(embed_ms):.1f} ms vs p95 {percentiles(embed_ms)['p95']} ms)")


if __name__ == "__main__":
    main()
