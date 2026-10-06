"""Chapter 6, table 1: how big the generation prompt really gets as k grows.

Runs the baseline retriever for real (e5-small + Qdrant) over the golden questions, builds the
actual prompt for each k, and counts tokens two ways: with the e5 tokenizer (the one we already
have loaded) and with tiktoken's o200k_base. Both are approximations of Claude's tokenizer;
the exact number comes from client.messages.count_tokens, which needs an API key.

Run from the `code/` directory:  ../.venv/bin/python experiments/06_prompt_tokens.py
"""
from __future__ import annotations

import statistics

import tiktoken

from ragbook.corpus import fixed_window_chunks, load_sections
from ragbook.embed import Embedder
from ragbook.evaluate import load_golden
from ragbook.answer import SYSTEM, build_prompt
from ragbook.store import DenseIndex

KS = (1, 3, 5, 8, 10, 20)
PRICE_IN = 5.0 / 1_000_000  # USD per input token, claude-opus-5, list price September 2026


def main() -> None:
    questions = load_golden()
    positives = [q for q in questions if q.relevant]
    print(f"golden set: {len(questions)} pytań "
          f"({len(positives)} pozytywnych, {len(questions) - len(positives)} negatywnych)\n")

    embedder = Embedder()
    chunks = fixed_window_chunks(load_sections(), embedder.tokenizer)
    index = DenseIndex(embedder, chunks)
    enc = tiktoken.get_encoding("o200k_base")

    sys_tokens = len(enc.encode(SYSTEM))
    print(f"system prompt: {sys_tokens} tokens (o200k_base); minimum cacheable prefix for "
          f"claude-opus-5 is 512 tokens\n")

    print("| k | tokeny promptu (o200k) | tokeny e5 | min–max o200k | koszt wejścia (Opus 5) |")
    print("|---|---|---|---|---|")
    rows = {}
    for k in KS:
        counts, e5_counts = [], []
        for q in positives:
            got = index.search(q.question, k)
            prompt = build_prompt(q.question, got)
            counts.append(len(enc.encode(prompt)) + sys_tokens)
            e5_counts.append(len(embedder.tokenizer(prompt, add_special_tokens=False)["input_ids"]))
        mean = statistics.mean(counts)
        rows[k] = mean
        print(f"| {k} | {mean:.0f} | {statistics.mean(e5_counts):.0f} "
              f"| {min(counts)}–{max(counts)} | {mean * PRICE_IN:.5f} USD |")

    print(f"\nk=10 vs k=5: +{100 * (rows[10] / rows[5] - 1):.0f}% tokenów wejścia")
    print(f"k=20 vs k=5: +{100 * (rows[20] / rows[5] - 1):.0f}% tokenów wejścia")

    print("\n=== Where the relevant chunk lands in the top 10 ===")
    hist = {i: 0 for i in range(1, 11)}
    missed = 0
    for q in positives:
        got = index.search(q.question, 10)
        rank = next((i for i, c in enumerate(got, start=1) if c.key in q.relevant), None)
        if rank:
            hist[rank] += 1
        else:
            missed += 1
    print("| pozycja pierwszego trafienia | pytań |")
    print("|---|---|")
    for pos, n in hist.items():
        if n:
            print(f"| {pos} | {n} |")
    print(f"| brak w top 10 | {missed} |")
    n = len(positives)
    for kk in (5, 10):
        found = sum(v for pos, v in hist.items() if pos <= kk)
        print(f"pytań z trafieniem w top-{kk}: {found}/{n} = {found / n:.2f}")

    print("\n=== Example prompt (k=3, first positive question) ===")
    q = positives[0]
    print(build_prompt(q.question, index.search(q.question, 3))[:1400])

    print("\n=== Off-target context: a negative question still returns 5 chunks ===")
    neg = [q for q in questions if not q.relevant]
    if neg:
        got = index.search(neg[0].question, 5)
        print(f"question: {neg[0].question}")
        for i, c in enumerate(got, start=1):
            print(f"  [{i}] score={c.meta['score']:.3f}  r{c.chapter} / {c.section}")


if __name__ == "__main__":
    main()
