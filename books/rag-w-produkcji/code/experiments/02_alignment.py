"""Chapter 2: how much recall depends on nothing but where the cuts happen to land.

Same chunker, same window, same overlap, same model — only the first cut of every section starts a
few tokens later. Nothing about the strategy changes, so every difference this experiment shows is
the width of the lottery that every other table in this chapter is played on.

Run from the `code/` directory:  ../.venv/bin/python experiments/02_alignment.py
"""
from __future__ import annotations

import sys

from ragbook.chunking import BETTER_EMBEDDER, PROJECT_EMBEDDER, evaluate_chunks, row, shifted_window_chunks
from ragbook.corpus import load_sections
from ragbook.embed import Embedder
from ragbook.evaluate import load_golden

OFFSETS = (0, 16, 32, 48, 64, 80, 96)
HEAD = ("| Wariant | Chunków | Mediana tokenów | Tokeny w prompcie @5 | recall@5 | recall@20 "
        "| MRR@5 | nDCG@5 | Bez trafienia |\n|---|---|---|---|---|---|---|---|---|")


def main() -> None:
    sections = load_sections()
    golden = load_golden()
    model_name = BETTER_EMBEDDER if "--base" in sys.argv else PROJECT_EMBEDDER
    embedder = Embedder(model_name)
    print("model:", model_name, "device:", embedder.model.device)

    rows = []
    for offset in OFFSETS:
        chunks = shifted_window_chunks(sections, embedder.tokenizer, 128, 32, offset)
        r = evaluate_chunks(f"okno 128/32, przesunięcie {offset}", chunks, embedder, golden)
        rows.append(r)
        print(f"offset {offset:3d}  {r['chunks']:5d} chunks  recall@5 {r['recall@5']:.3f}  "
              f"mrr@5 {r['mrr@5']:.3f}  misses {r['misses@5']}", flush=True)

    print("\n=== Ta sama strategia, inne miejsce cięcia ===")
    print(HEAD)
    for r in rows:
        print(row(r))

    values = [r["recall@5"] for r in rows]
    print(f"\nrecall@5: min {min(values):.3f} max {max(values):.3f} rozstęp {max(values) - min(values):.3f}")
    values = [r["mrr@5"] for r in rows]
    print(f"MRR@5:    min {min(values):.3f} max {max(values):.3f} rozstęp {max(values) - min(values):.3f}")
    values = [r["misses@5"] for r in rows]
    print(f"pytań bez trafienia: min {min(values)} max {max(values)}")


if __name__ == "__main__":
    main()
