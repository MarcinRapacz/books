"""Chapter 2, table 2: chunking that follows the structure of the document.

Compares, against the best fixed window from `02_chunking.py`:
- section as a chunk (with the truncation the embedding model performs anyway),
- one Markdown block per chunk (paragraph, whole code block, whole table),
- blocks merged up to a budget (128 / 256 / 384 tokens),
- the recursive splitter (headings -> blank lines -> sentences -> tokens),
- the semantic splitter (cut where neighbouring sentences drift apart).

Run from the `code/` directory:  ../.venv/bin/python experiments/02_structure.py
"""
from __future__ import annotations

import time
from collections import Counter

from ragbook.chunking import (block_chunks, evaluate_chunks, merged_block_chunks, n_tokens,
                              recursive_chunks, row, section_chunks, semantic_chunks, split_blocks)
from ragbook.corpus import fixed_window_chunks, load_sections
from ragbook.embed import Embedder
from ragbook.evaluate import by_type, load_golden

HEAD = ("| Wariant | Chunków | Mediana tokenów | Tokeny w prompcie @5 | recall@5 | recall@20 "
        "| MRR@5 | nDCG@5 | Bez trafienia |\n|---|---|---|---|---|---|---|---|---|")


def main() -> None:
    sections = load_sections()
    golden = load_golden()
    embedder = Embedder()
    tok = embedder.tokenizer

    # How much does "section as a chunk" actually lose to the 512-token limit of e5-small?
    lengths = [n_tokens(s.text, tok) for s in sections]
    over = [n for n in lengths if n > 512]
    kept = sum(min(n, 512) for n in lengths)
    print(f"sections: {len(sections)}  longer than 512 e5 tokens: {len(over)} "
          f"({100 * len(over) / len(sections):.0f}%)")
    print(f"tokens in the corpus: {sum(lengths)}  indexed if one section = one chunk: {kept} "
          f"({100 * kept / sum(lengths):.0f}%)  lost: {sum(lengths) - kept}")

    kinds = Counter(kind for s in sections for kind, _ in split_blocks(s.text))
    print("Markdown blocks:", dict(kinds), "total", sum(kinds.values()))

    variants = [
        ("stałe okno 128/32 (baseline)", lambda: fixed_window_chunks(sections, tok, 128, 32)),
        ("sekcja = chunk (ucięta do 512)", lambda: section_chunks(sections, tok, 512)),
        ("blok Markdown = chunk", lambda: block_chunks(sections, tok, 512)),
        ("bloki łączone do 128", lambda: merged_block_chunks(sections, tok, 128)),
        ("bloki łączone do 256", lambda: merged_block_chunks(sections, tok, 256)),
        ("bloki łączone do 384", lambda: merged_block_chunks(sections, tok, 384)),
        ("rekurencyjny 256", lambda: recursive_chunks(sections, tok, 256)),
        ("rekurencyjny 128", lambda: recursive_chunks(sections, tok, 128)),
        ("semantyczny 256 (p90)", lambda: semantic_chunks(sections, embedder, 256, 90.0)),
        ("semantyczny 256 (p80)", lambda: semantic_chunks(sections, embedder, 256, 80.0)),
    ]

    rows = []
    for name, fn in variants:
        t0 = time.perf_counter()
        chunks = fn()
        r = evaluate_chunks(name, chunks, embedder, golden)
        r["seconds"] = time.perf_counter() - t0
        rows.append(r)
        print(f"{name:>32}  {len(chunks):5d} chunks  recall@5 {r['recall@5']:.3f}  "
              f"prompt {r['prompt_tokens@5']:4d} tok  ({r['seconds']:.0f} s)", flush=True)

    print("\n=== Podział po strukturze ===")
    print(HEAD)
    for r in rows:
        print(row(r))

    best = max(rows, key=lambda r: r["recall@5"])
    print(f"\nbest: {best['name']}")
    for metric in ("recall@5", "mrr"):
        print(f"  by type, {metric}:", {t: round(v, 2) for t, v in by_type(best["result"], metric).items()})
    base = rows[0]["result"]
    moved = [(a["id"], a["recall@5"], b["recall@5"])
             for a, b in zip(base["per_question"], best["result"]["per_question"])
             if a["recall@5"] != b["recall@5"]]
    print(f"  questions that changed vs baseline: {len(moved)} "
          f"(+{sum(1 for _, a, b in moved if b > a)} / -{sum(1 for _, a, b in moved if b < a)})")
    print("  ", moved)

    # Cost of the semantic splitter: how many extra embeddings does it need?
    sents = sum(len(split_blocks(s.text)) for s in sections)
    print(f"\nsemantic splitter: {sents} Markdown blocks split into sentences, embedded once extra "
          f"before any chunk exists")


if __name__ == "__main__":
    main()
