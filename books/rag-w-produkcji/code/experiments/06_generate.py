"""Chapter 6: the full generation stage end to end. This is the one script that needs an API key.

Without ANTHROPIC_API_KEY it still runs: it builds the real prompts from the real retriever and
prints them, plus the estimated token cost of the run. With a key (`export ANTHROPIC_API_KEY=...`)
it additionally calls claude-opus-5 for the answers, verifies the citations locally, and grades
faithfulness with claude-haiku-4-5.

Run from the `code/` directory:  ../.venv/bin/python experiments/06_generate.py [n_questions]
"""
from __future__ import annotations

import os
import sys

import tiktoken

from ragbook.answer import (GEN_MODEL, SYSTEM, answer_with_citations, build_prompt,
                            check_citations, document_blocks, flatten_citations,
                            generate_answer, should_ask_model)
from ragbook.corpus import fixed_window_chunks, load_sections
from ragbook.embed import Embedder
from ragbook.evaluate import load_golden
from ragbook.judge import JUDGE_MODEL, faithfulness_score, judge_faithfulness
from ragbook.store import DenseIndex

K = 5
SCORE_GATE = 0.0   # measured in experiments/06_threshold.py; 0.0 disables the gate
PRICE = {"claude-opus-5": (5.0, 25.0), "claude-haiku-4-5": (1.0, 5.0)}  # USD/MTok, September 2026


def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    golden = load_golden()
    sample = [q for q in golden if q.relevant][:limit - 2] + [q for q in golden if not q.relevant][:2]

    embedder = Embedder()
    chunks = fixed_window_chunks(load_sections(), embedder.tokenizer)
    index = DenseIndex(embedder, chunks)
    enc = tiktoken.get_encoding("o200k_base")

    key = os.environ.get("ANTHROPIC_API_KEY")
    client = None
    if key:
        from anthropic import Anthropic
        client = Anthropic(api_key=key)

    total_in = 0
    for q in sample:
        got = index.search(q.question, K)
        prompt = build_prompt(q.question, got)
        total_in += len(enc.encode(prompt)) + len(enc.encode(SYSTEM))
        gate = should_ask_model(got, SCORE_GATE)
        print(f"\n=== {q.id} [{q.type}] {q.question}")
        print(f"    top-1 score={got[0].meta['score']:.3f}  gate={'ask' if gate else 'refuse'}  "
              f"fragments: " + ", ".join(f"[{i}] r{c.chapter}/{c.section}" for i, c in enumerate(got, 1)))
        if not client:
            continue
        if not gate:
            print("    -> refused without calling the model")
            continue
        answer = generate_answer(client, q.question, got)
        print(f"    answerable={answer.answerable}  citations={answer.citations}")
        print(f"    {answer.text}")
        for chk in check_citations(answer.text, got, answer.citations):
            print(f"      [{','.join(map(str, chk.cited)) or '-'}] cov={chk.coverage_cited:.2f} "
                  f"{chk.status}  {chk.sentence[:70]}")
        report = judge_faithfulness(client, q.question, answer.text, got)
        print(f"    faithfulness={faithfulness_score(report):.2f} "
              f"({len(report.claims)} claims)")
        for c in report.claims:
            print(f"      {c.verdict:13s} {c.claim[:70]}")

    gen_in, gen_out = PRICE[GEN_MODEL]
    jud_in, jud_out = PRICE[JUDGE_MODEL]
    print(f"\n--- estimated input tokens for {len(sample)} questions: {total_in} "
          f"(~{total_in / 1e6 * gen_in:.4f} USD on {GEN_MODEL} before caching)")
    print(f"--- the judge re-reads the same context on {JUDGE_MODEL}: "
          f"~{total_in / 1e6 * jud_in:.4f} USD")
    if not key:
        print("--- ANTHROPIC_API_KEY not set: prompts built, no model called")

    print("\n=== Citations API variant (one question) ===")
    q = sample[0]
    got = index.search(q.question, K)
    if client:
        message = answer_with_citations(client, q.question, got)
        for row in flatten_citations(message):
            src = f"[{row['document_index'] + 1}]" if row["document_index"] is not None else "[-]"
            print(f"  {src} {row['claim'][:80]}")
            if row["cited_text"]:
                print(f"       cited_text: {row['cited_text'][:90]}")
    else:
        blocks = document_blocks(got)
        print(f"  {len(blocks)} document blocks, citations enabled on all of them")
        print(f"  first block: title={blocks[0]['title']!r} context={blocks[0]['context']!r}")


if __name__ == "__main__":
    main()
