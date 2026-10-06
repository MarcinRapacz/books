"""Listwise reranking with an LLM: the prompt, the call, and what it would cost.

This is the only experiment in the chapter that needs an API key. Without ANTHROPIC_API_KEY the script
still builds the prompt and prices it, so you can decide before you spend anything. With a key it runs
the reranker on the whole golden set and prints the same table as `03_rerank.py`.

Run from the `code/` directory:  ../.venv/bin/python experiments/03_llm_rerank.py
"""
from __future__ import annotations

import os

from ragbook.corpus import fixed_window_chunks, load_sections
from ragbook.embed import Embedder
from ragbook.evaluate import evaluate, load_golden
from ragbook.hybrid import BM25Index, HybridIndex, make_tokenizer
from ragbook.rerank import build_listwise_prompt, listwise_cost, llm_rerank
from ragbook.store import DenseIndex

CHUNKER = lambda sections, tokenizer: fixed_window_chunks(sections, tokenizer, window=128, overlap=32)
K, POOL, STEM, RRF_K = 5, 20, 5, 60
MODEL = "claude-haiku-4-5"          # 1 USD / MTok input, 5 USD / MTok output (stan na wrzesień 2026)


def main() -> None:
    embedder = Embedder()
    chunks = CHUNKER(load_sections(), embedder.tokenizer)
    golden = load_golden()
    questions = [q for q in golden if q.relevant]

    dense = DenseIndex(embedder, chunks)
    lexical = BM25Index(chunks, make_tokenizer(STEM))
    hybrid = HybridIndex(dense, lexical, method="rrf", rrf_k=RRF_K, pool=50)
    candidates = {q.id: hybrid.search(q.question, POOL) for q in questions}

    sample = questions[0]
    prompt = build_listwise_prompt(sample.question, candidates[sample.id])
    print("=== Prompt (first 900 characters) ===")
    print(prompt[:900])
    print("...")

    costs = [listwise_cost(q.question, candidates[q.id], embedder.tokenizer) for q in questions]
    n_in = sum(c["input_tokens"] for c in costs) / len(costs)
    n_out = sum(c["output_tokens"] for c in costs) / len(costs)
    total = sum(c["usd"] for c in costs)
    print(f"\n=== Cost of listwise reranking, {MODEL}, {POOL} candidates, 600 chars each ===")
    print(f"per query: {n_in:.0f} input tokens (e5 tokenizer), {n_out:.0f} output tokens")
    print(f"per query: {total / len(costs):.5f} USD, per 1000 queries: "
          f"{1000 * total / len(costs):.2f} USD")
    print(f"whole golden set ({len(costs)} queries): {total:.4f} USD")
    print("Token counts come from the e5 tokenizer; for the real number call "
          "client.messages.count_tokens with the same request shape.")

    if "ANTHROPIC_API_KEY" not in os.environ:
        print("\nANTHROPIC_API_KEY is not set - skipping the actual calls.")
        return

    ranked = {q.id: llm_rerank(q.question, candidates[q.id], top_k=POOL, model=MODEL)
              for q in questions}
    by_question = {q.question: q.id for q in questions}
    result = evaluate(lambda question, k: ranked[by_question[question]][:k], golden, k=K, ks=(K, POOL))
    print(f"\n| Wariant | recall@5 | MRR@5 | nDCG@5 | Bez trafienia |")
    print("|---|---|---|---|---|")
    print(f"| hybryda → listwise {MODEL} | {result['recall@5']:.2f} | {result['mrr@5']:.2f} "
          f"| {result['ndcg@5']:.2f} | {result['misses@5']} |".replace(".", ","))


if __name__ == "__main__":
    main()
