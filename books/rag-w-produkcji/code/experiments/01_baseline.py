"""Naive RAG baseline: fixed 128/32-token windows, multilingual-e5-small, Qdrant :memory:, top-5 and top-20.

Prints the overall table, the breakdown by question type, the score distribution on negative
questions and the full error analysis (every question with recall@5 equal to 0).

Run from the `code/` directory:  ../.venv/bin/python experiments/01_baseline.py
"""
from __future__ import annotations

import random
import time
from collections import Counter

from ragbook.corpus import fixed_window_chunks, load_sections
from ragbook.embed import Embedder
from ragbook.evaluate import by_type, evaluate, load_golden
from ragbook.store import DenseIndex

WINDOW, OVERLAP = 128, 32
K, K_WIDE = 5, 20


def main() -> None:
    sections = load_sections()
    golden = load_golden()

    embedder = Embedder()
    chunks = fixed_window_chunks(sections, embedder.tokenizer, window=WINDOW, overlap=OVERLAP)
    lengths = [len(embedder.tokenizer(c.text, add_special_tokens=False)["input_ids"]) for c in chunks]
    print(f"sections: {len(sections)}  chunks: {len(chunks)}  "
          f"tokens/chunk: min {min(lengths)} median {sorted(lengths)[len(lengths) // 2]} max {max(lengths)}")
    print(f"chunks per section: {len(chunks) / len(sections):.1f}")

    t0 = time.perf_counter()
    index = DenseIndex(embedder, chunks)
    print(f"index built in {time.perf_counter() - t0:.1f} s (embeddings come from the cache on reruns)")

    t0 = time.perf_counter()
    result = evaluate(index.search, golden, k=K, ks=(K, K_WIDE))
    elapsed = time.perf_counter() - t0
    n = result["n"]

    print("\n=== Baseline, whole set ===")
    print(f"| Wariant | Pytań | recall@5 | recall@20 | MRR@5 | nDCG@5 | Pytań bez trafienia |")
    print("|---|---|---|---|---|---|---|")
    print(f"| fixed 128/32 + e5-small | {n} | {result['recall@5']:.2f} | {result['recall@20']:.2f} "
          f"| {result['mrr@5']:.2f} | {result['ndcg@5']:.2f} | {result['misses@5']} |".replace(".", ","))
    print(f"({elapsed:.1f} s for {n} queries, {1000 * elapsed / n:.0f} ms per query)")

    print("\n=== By question type ===")
    print("| Typ | Pytań | recall@5 | recall@20 | MRR@5 |")
    print("|---|---|---|---|---|")
    r5, r20, mrr = by_type(result, "recall@5"), by_type(result, "recall@20"), by_type(result, "mrr")
    sizes = Counter(row["type"] for row in result["per_question"])
    for t in ("factual", "procedural", "comparative"):
        if t in r5:
            print(f"| {t} | {sizes[t]} | {r5[t]:.2f} | {r20[t]:.2f} | {mrr[t]:.2f} |".replace(".", ","))

    # Negative questions never enter the retrieval metrics; look at their scores instead.
    negatives = [q for q in golden if not q.relevant]
    positives = [q for q in golden if q.relevant]
    neg_top = [index.search(q.question, K)[0].meta["score"] for q in negatives]
    pos_top = [index.search(q.question, K)[0].meta["score"] for q in positives]
    print(f"\n=== Negative questions ({len(negatives)}) ===")
    print(f"top-1 score: negatives min {min(neg_top):.3f} max {max(neg_top):.3f} mean {sum(neg_top) / len(neg_top):.3f}")
    print(f"top-1 score: positives min {min(pos_top):.3f} max {max(pos_top):.3f} mean {sum(pos_top) / len(pos_top):.3f}")
    overlap = sum(1 for s in neg_top if s > min(pos_top))
    print(f"{overlap} of {len(negatives)} negatives score above the weakest positive -> no usable cut-off")

    # How wide is the noise band on 49 questions? Percentile bootstrap over questions.
    per_recall = [row["recall@5"] for row in result["per_question"]]
    rng = random.Random(7)
    boot = sorted(sum(rng.choices(per_recall, k=n)) / n for _ in range(10_000))
    lo, hi = boot[int(0.025 * len(boot))], boot[int(0.975 * len(boot))]
    spread = (sum((x - result["recall@5"]) ** 2 for x in per_recall) / (n - 1)) ** 0.5
    print(f"\n=== How precise is recall@5 on {n} questions? ===")
    print(f"recall@5 = {result['recall@5']:.3f}, sd per question {spread:.3f}, "
          f"standard error {spread / n ** 0.5:.3f}")
    print(f"95% bootstrap CI: [{lo:.3f}, {hi:.3f}]  (width {hi - lo:.3f})")

    # Which sections does the baseline like to return, whether or not they are relevant?
    returned = Counter(sec for row in result["per_question"] for _, sec, _ in row["top"])
    slots = sum(returned.values())
    boiler = sum(returned[s] for s in ("Podsumowanie", "Co dalej", "Źródła"))
    print("\n=== Most often returned sections in top-5 ===")
    for section, count in returned.most_common(8):
        print(f"  {count:3d}x  {section!r}")
    print(f"boilerplate (Podsumowanie/Co dalej/Źródła): {boiler} of {slots} slots "
          f"({100 * boiler / slots:.0f}%); lead-in sections (''): {returned['']} "
          f"({100 * returned[''] / slots:.0f}%)")
    wanted_keys = {q.id: q.relevant for q in golden}
    good = sum(1 for row in result["per_question"]
               for chapter, section, _ in row["top"] if (chapter, section) in wanted_keys[row["id"]])
    print(f"precision@5 (chunks from a relevant section): {good}/{slots} = {good / slots:.2f}")

    print("\n=== Error analysis: questions with recall@5 = 0 ===")
    misses = [row for row in result["per_question"] if row["recall@5"] == 0]
    wanted = {q.id: (q.question, sorted(q.relevant)) for q in golden}
    for row in misses:
        question, relevant = wanted[row["id"]]
        found_at_20 = "tak" if row["recall@20"] > 0 else "NIE"
        print(f"\n{row['id']} [{row['type']}] {question}")
        print(f"  oczekiwane: {relevant}   trafione w top-20: {found_at_20}")
        for rank, (chapter, section, score) in enumerate(row["top"], start=1):
            print(f"  {rank}. {score:.3f}  ch{chapter:<2} {section!r}")
    print(f"\n{len(misses)} of {n} questions have no relevant chunk in the top {K}.")

    partial = [row for row in result["per_question"] if 0 < row["recall@5"] < 1]
    print(f"{len(partial)} questions have only part of their relevant sections in the top {K}: "
          f"{[row['id'] for row in partial]}")


if __name__ == "__main__":
    main()
