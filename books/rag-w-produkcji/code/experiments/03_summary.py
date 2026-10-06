"""Before / after for the whole chapter, and the configuration that stays in the project.

The last row is produced by `ragbook.hybrid.project_retriever`, i.e. by the object chapter 4 imports,
not by a copy of the pipeline written for this table.

Run from the `code/` directory:  ../.venv/bin/python experiments/03_summary.py
"""
from __future__ import annotations

import time

from ragbook.corpus import fixed_window_chunks, load_sections
from ragbook.embed import Embedder
from ragbook.evaluate import by_type, evaluate, load_golden
from ragbook.hybrid import BM25Index, HybridIndex, make_tokenizer, project_retriever
from ragbook.store import DenseIndex

CHUNKER = lambda sections, tokenizer: fixed_window_chunks(sections, tokenizer, window=128, overlap=32)
K, K_WIDE, POOL, STEM, RRF_K = 5, 20, 20, 5, 60
BASELINE_MISSES = ["q007", "q021", "q022", "q023", "q029", "q032", "q033", "q037", "q039"]


def precision_at_k(result: dict, golden, k: int = 5) -> float:
    wanted = {q.id: q.relevant for q in golden}
    slots = sum(len(r["top"][:k]) for r in result["per_question"])
    good = sum(1 for r in result["per_question"]
               for chapter, section, _ in r["top"][:k] if (chapter, section) in wanted[r["id"]])
    return good / slots


def main() -> None:
    embedder = Embedder()
    chunks = CHUNKER(load_sections(), embedder.tokenizer)
    golden = load_golden()

    rows = []
    dense = DenseIndex(embedder, chunks)
    rows.append(("stałe okno 128/32 + e5-small (rozdz. 1)", evaluate(dense.search, golden, k=K, ks=(K, K_WIDE))))

    lexical = BM25Index(chunks, make_tokenizer(STEM))
    rows.append(("sam BM25 (obcięcie do 5 znaków)", evaluate(lexical.search, golden, k=K, ks=(K, K_WIDE))))

    hybrid = HybridIndex(dense, lexical, method="rrf", rrf_k=RRF_K, pool=50)
    rows.append(("hybryda RRF (k=60)", evaluate(hybrid.search, golden, k=K, ks=(K, K_WIDE))))
    del dense, lexical, hybrid

    retrieve = project_retriever(chunks, embedder=embedder, mode="hybrid", rerank=True,
                                pool=POOL, rrf_k=RRF_K, stem_to=STEM, max_per_section=1)
    t0 = time.perf_counter()
    result = evaluate(retrieve, golden, k=K, ks=(K, K_WIDE))
    elapsed = time.perf_counter() - t0
    rows.append(("hybryda + rerank top-20 + limit 1/sekcję", result))

    print("| Wariant | recall@5 | recall@20 | MRR@5 | nDCG@5 | precision@5 | Bez trafienia |")
    print("|---|---|---|---|---|---|---|")
    for name, r in rows:
        print(f"| {name} | {r['recall@5']:.2f} | {r['recall@20']:.2f} | {r['mrr@5']:.2f} "
              f"| {r['ndcg@5']:.2f} | {precision_at_k(r, golden):.2f} "
              f"| {r['misses@5']} |".replace(".", ","))

    print(f"\n{elapsed:.1f} s for {result['n']} queries with the full stack "
          f"({1000 * elapsed / result['n']:.0f} ms per query)")

    print("\n| Typ | rozdz. 1 recall@5 | po rozdz. 3 recall@5 | rozdz. 1 MRR@5 | po rozdz. 3 MRR@5 |")
    print("|---|---|---|---|---|")
    b5, f5 = by_type(rows[0][1], "recall@5"), by_type(result, "recall@5")
    bm, fm = by_type(rows[0][1], "mrr"), by_type(result, "mrr")
    for t in ("factual", "procedural", "comparative"):
        print(f"| {t} | {b5[t]:.2f} | {f5[t]:.2f} | {bm[t]:.2f} | {fm[t]:.2f} |".replace(".", ","))

    now = {r["id"]: r["recall@5"] for r in result["per_question"]}
    before = {r["id"]: r["recall@5"] for r in rows[0][1]["per_question"]}
    fixed = [i for i in BASELINE_MISSES if now[i] > 0]
    left = [i for i in BASELINE_MISSES if now[i] == 0]
    print(f"\nof the 9 chapter-1 misses, fixed: {fixed}")
    print(f"still missing: {left}")
    broken = [i for i in now if now[i] < before[i]]
    print(f"regressions (worse than the baseline): {broken}")
    misses = [r["id"] for r in result["per_question"] if r["recall@5"] == 0]
    print(f"all questions with no hit in top-5 now: {misses}")
    retrieve.close()


if __name__ == "__main__":
    main()
