"""Chapter 2, the decision: the shortlist compared in pairs, the "before / after" table, the nine misses.

Differences of 0.05 on 49 questions are noise (chapter 1), so the shortlist is not ranked by the third
digit of the mean. Every candidate is compared with the chapter 1 baseline *question by question*:
how many questions went up, how many went down, and what a paired bootstrap says about the difference.
Then the configuration the project keeps (`ragbook.chunking.project_chunks`) is measured against the
baseline and the nine questions that had no hit in the top 5 are looked at one by one.

Run from the `code/` directory:  ../.venv/bin/python experiments/02_summary.py
"""
from __future__ import annotations

import gc
import random
from collections import Counter

from ragbook.chunking import (BETTER_EMBEDDER, PROJECT_EMBEDDER, evaluate_chunks, merged_block_chunks,
                              project_chunks, recursive_chunks, row, with_context_headers)
from ragbook.corpus import fixed_window_chunks, load_sections
from ragbook.embed import Embedder
from ragbook.evaluate import by_type, load_golden

HEAD = ("| Wariant | Chunków | Mediana tokenów | Tokeny w prompcie @5 | recall@5 | recall@20 "
        "| MRR@5 | nDCG@5 | Bez trafienia |\n|---|---|---|---|---|---|---|---|---|")
BASELINE_MISSES = ["q007", "q021", "q022", "q023", "q029", "q032", "q033", "q037", "q039"]


def precision_at_k(result: dict, golden) -> float:
    wanted = {q.id: q.relevant for q in golden}
    slots = sum(len(r["top"]) for r in result["per_question"])
    good = sum(1 for r in result["per_question"] for ch, sec, _ in r["top"] if (ch, sec) in wanted[r["id"]])
    return good / slots


def paired(base: dict, other: dict, metric: str = "recall@5", trials: int = 10_000) -> dict:
    """Per-question differences plus a paired percentile bootstrap of the mean difference."""
    diffs = [b[metric] - a[metric] for a, b in zip(base["per_question"], other["per_question"])]
    rng = random.Random(7)
    boot = sorted(sum(rng.choices(diffs, k=len(diffs))) / len(diffs) for _ in range(trials))
    return {
        "mean": sum(diffs) / len(diffs),
        "up": sum(1 for d in diffs if d > 0),
        "down": sum(1 for d in diffs if d < 0),
        "lo": boot[int(0.025 * trials)],
        "hi": boot[int(0.975 * trials)],
        "ids_up": [a["id"] for a, d in zip(base["per_question"], diffs) if d > 0],
        "ids_down": [a["id"] for a, d in zip(base["per_question"], diffs) if d < 0],
    }


def main() -> None:
    sections = load_sections()
    golden = load_golden()
    embedder = Embedder(PROJECT_EMBEDDER)
    tok = embedder.tokenizer

    candidates = [
        ("stałe okno 128/32 (rozdz. 1)", lambda: fixed_window_chunks(sections, tok, 128, 32), "text"),
        ("stałe okno 128/0", lambda: fixed_window_chunks(sections, tok, 128, 0), "text"),
        ("stałe okno 128/64", lambda: fixed_window_chunks(sections, tok, 128, 64), "text"),
        ("stałe okno 128/32 + nagłówek", lambda: with_context_headers(
            fixed_window_chunks(sections, tok, 128, 32), "title"), "body"),
        ("bloki łączone do 256", lambda: merged_block_chunks(sections, tok, 256), "text"),
        ("rekurencyjny 256", lambda: recursive_chunks(sections, tok, 256), "text"),
        # The one that stays in the project. `ragbook.code_chunks.code_aware_chunks` (chapter 5) is
        # the same idea for code only; it scores +0,010 instead of -0,010, i.e. the same noise band.
        ("kod i tabele w całości 128/32", lambda: project_chunks(sections, tok), "text"),
    ]

    rows = []
    for name, fn, on in candidates:
        r = evaluate_chunks(name, fn(), embedder, golden, count_tokens_on=on)
        rows.append(r)
        print(f"{name:>34}  {r['chunks']:5d} chunks  recall@5 {r['recall@5']:.3f}  "
              f"misses {r['misses@5']}", flush=True)

    print("\n=== Krótka lista ===")
    print(HEAD)
    for r in rows:
        print(row(r))

    print("\n=== Porównanie parami z baseline'em (recall@5) ===")
    print("| Wariant | Średnia różnica | 95% CI (bootstrap parami) | Pytań w górę | Pytań w dół |")
    print("|---|---|---|---|---|")
    base = rows[0]["result"]
    for r in rows[1:]:
        p = paired(base, r["result"])
        mean, lo, hi = (f"{p[key]:+.3f}".replace(".", ",") for key in ("mean", "lo", "hi"))
        print(f"| {r['name']} | {mean} | [{lo}; {hi}] | {p['up']} | {p['down']} |")
    for r in rows[1:]:
        p = paired(base, r["result"])
        print(f"{r['name']}: up {p['ids_up']} down {p['ids_down']}")

    # ---- what the project keeps -------------------------------------------------------------------
    before = rows[0]
    after = rows[-1] | {"name": "rozdz. 2: project_chunks"}

    print("\n=== Przed / po ===")
    print(HEAD)
    print(row(before))
    print(row(after))
    for label, r in (("przed", before), ("po", after)):
        print(f"{label}: precision@5 {precision_at_k(r['result'], golden):.2f}",
              {t: round(v, 2) for t, v in by_type(r["result"], "recall@5").items()})

    print("\n=== Rozbicie po typach ===")
    print("| Typ | Pytań | recall@5 przed | recall@5 po | MRR@5 przed | MRR@5 po |")
    print("|---|---|---|---|---|---|")
    sizes = Counter(r["type"] for r in before["result"]["per_question"])
    b5, a5 = by_type(before["result"], "recall@5"), by_type(after["result"], "recall@5")
    bm, am = by_type(before["result"], "mrr"), by_type(after["result"], "mrr")
    for t in ("factual", "procedural", "comparative"):
        print(f"| {t} | {sizes[t]} | {b5[t]:.2f} | {a5[t]:.2f} | {bm[t]:.2f} | {am[t]:.2f} |".replace(".", ","))

    p = paired(before["result"], after["result"])
    print(f"\nproject_chunks vs baseline: {p['mean']:+.3f} [{p['lo']:+.3f}; {p['hi']:+.3f}], "
          f"up {p['up']} {p['ids_up']}, down {p['down']} {p['ids_down']}")

    print("\n=== Dziewięć porażek baseline'u ===")
    idx = {r["id"]: r for r in after["result"]["per_question"]}
    fixed, still = [], []
    for qid in BASELINE_MISSES:
        r = idx[qid]
        (fixed if r["recall@5"] > 0 else still).append(qid)
        print(f"{qid} [{r['type']}] recall@5 {r['recall@5']:.2f} recall@20 {r['recall@20']:.2f} "
              f"rank {r['hit_rank']}")
        for rank, (chapter, section, score) in enumerate(r["top"], start=1):
            print(f"   {rank}. {score:.3f}  ch{chapter:<2} {section!r}")
    print(f"\nnaprawione: {fixed}")
    print(f"zostają: {still}")

    # The same chunks under the bigger model. Loaded last and alone: one model at a time.
    del embedder
    gc.collect()
    big = Embedder(BETTER_EMBEDDER)
    r = evaluate_chunks("project_chunks + e5-base (poza projektem)",
                        project_chunks(sections, big.tokenizer), big, golden)
    print("\n=== Ten sam chunker pod większym modelem ===")
    print(HEAD)
    print(row(r))
    print("precision@5", round(precision_at_k(r["result"], golden), 2))


if __name__ == "__main__":
    main()
