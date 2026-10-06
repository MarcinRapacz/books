"""Chapter 2, table 1: the fixed-window grid (64/128/256/512 tokens x 0/25/50 % overlap).

Every variant is indexed with multilingual-e5-small and measured on the frozen golden set with the
metrics of chapter 1. `prompt_tokens@5` is the real average number of e5 tokens in the five chunks
that would go into the prompt, so the cost column is measured, not estimated.

Run from the `code/` directory:  ../.venv/bin/python experiments/02_chunking.py
"""
from __future__ import annotations

import time

from ragbook.chunking import evaluate_chunks, row
from ragbook.corpus import fixed_window_chunks, load_sections
from ragbook.embed import Embedder
from ragbook.evaluate import by_type, load_golden

WINDOWS = (64, 128, 256, 512)
OVERLAPS = (0.0, 0.25, 0.5)
HEAD = ("| Wariant | Chunków | Mediana tokenów | Tokeny w prompcie @5 | recall@5 | recall@20 "
        "| MRR@5 | nDCG@5 | Bez trafienia |\n|---|---|---|---|---|---|---|---|---|")


def main() -> None:
    sections = load_sections()
    golden = load_golden()
    embedder = Embedder()

    rows = []
    for window in WINDOWS:
        for frac in OVERLAPS:
            overlap = int(window * frac)
            t0 = time.perf_counter()
            chunks = fixed_window_chunks(sections, embedder.tokenizer, window=window, overlap=overlap)
            name = f"{window}/{overlap} ({int(frac * 100)}%)"
            r = evaluate_chunks(name, chunks, embedder, golden)
            r["seconds"] = time.perf_counter() - t0
            rows.append(r)
            print(f"{name:>16}  {len(chunks):5d} chunks  recall@5 {r['recall@5']:.3f}  "
                  f"prompt {r['prompt_tokens@5']:4d} tok  ({r['seconds']:.0f} s)", flush=True)

    print("\n=== Stałe okno: siatka rozmiar x zakładka ===")
    print(HEAD)
    for r in rows:
        print(row(r))

    best = max(rows, key=lambda r: r["recall@5"])
    print(f"\nbest by recall@5: {best['name']}  recall@5 {best['recall@5']:.3f} "
          f"recall@20 {best['recall@20']:.3f} misses {best['misses@5']}")
    for metric in ("recall@5", "mrr"):
        print(f"by type, {best['name']}, {metric}:",
              {t: round(v, 2) for t, v in by_type(best["result"], metric).items()})

    print("\n=== Koszt promptu a rozmiar okna (zakładka 25%) ===")
    print("| Okno | Chunków | Tokeny w prompcie @5 | recall@5 |")
    print("|---|---|---|---|")
    for r in rows:
        if r["name"].endswith("(25%)"):
            print(f"| {r['name'].split('/')[0]} | {r['chunks']} | {r['prompt_tokens@5']} | "
                  f"{r['recall@5']:.2f} |".replace(".", ","))


if __name__ == "__main__":
    main()
