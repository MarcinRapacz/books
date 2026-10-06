"""Chapter 6, table 2: can the retrieval score alone tell a positive question from a negative one?

If it can, you refuse before paying for a generation. Local, no API key: we only need the
top-1 cosine score of the baseline retriever for every question in the golden set.

Run from the `code/` directory:  ../.venv/bin/python experiments/06_threshold.py
"""
from __future__ import annotations

import statistics

from ragbook.corpus import fixed_window_chunks, load_sections
from ragbook.embed import Embedder
from ragbook.evaluate import load_golden
from ragbook.store import DenseIndex



def describe(name: str, xs: list[float]) -> None:
    xs = sorted(xs)
    print(f"{name:10s} n={len(xs):3d}  min={xs[0]:.3f}  p25={xs[len(xs) // 4]:.3f}  "
          f"median={statistics.median(xs):.3f}  p75={xs[3 * len(xs) // 4]:.3f}  max={xs[-1]:.3f}")


def main() -> None:
    questions = load_golden()
    print(f"golden set: {len(questions)} pytań\n")

    embedder = Embedder()
    chunks = fixed_window_chunks(load_sections(), embedder.tokenizer)
    index = DenseIndex(embedder, chunks)

    pos, neg = [], []
    rows = []
    for q in questions:
        got = index.search(q.question, 5)
        top1 = got[0].meta["score"]
        mean5 = statistics.mean(c.meta["score"] for c in got)
        (pos if q.relevant else neg).append(top1)
        rows.append((q.id, q.type, top1, mean5, top1 - mean5, bool(q.relevant)))

    print("=== top-1 cosine score ===")
    describe("pozytywne", pos)
    describe("negatywne", neg)
    print(f"\nrozstęp: najgorsze pozytywne {min(pos):.3f}, najlepsze negatywne {max(neg):.3f} "
          f"-> {'rozłączne' if min(pos) > max(neg) else 'NAKŁADAJĄ SIĘ'}")

    print("\n| id | typ | top-1 | średnia top-5 | margines |")
    print("|---|---|---|---|---|")
    for qid, qtype, top1, mean5, margin, _ in sorted(rows, key=lambda r: -r[2]):
        print(f"| {qid} | {qtype} | {top1:.3f} | {mean5:.3f} | {margin:+.3f} |")

    print("\n=== Threshold sweep on top-1 score ===")
    print("| próg | odrzuconych negatywnych | odrzuconych pozytywnych (błąd) |")
    print("|---|---|---|")
    lo, hi = min(pos + neg), max(pos + neg)
    step = (hi - lo) / 12
    for i in range(13):
        t = lo + i * step
        blocked_neg = sum(1 for s in neg if s < t)
        blocked_pos = sum(1 for s in pos if s < t)
        print(f"| {t:.3f} | {blocked_neg}/{len(neg)} | {blocked_pos}/{len(pos)} |")

    print("\n=== Same sweep on the top-1 margin over the mean of the top 5 ===")
    pos_m = [r[4] for r in rows if r[5]]
    neg_m = [r[4] for r in rows if not r[5]]
    describe("pozytywne", pos_m)
    describe("negatywne", neg_m)


if __name__ == "__main__":
    main()
