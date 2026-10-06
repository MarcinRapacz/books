"""Everything together: chapter 2 chunker + chapter 3 retriever (hybrid + rerank) + chapter 4 queries.

The query variants are the hand-written ones from `data/query_variants.jsonl`, exactly as in
`experiments/04_queries.py`, so the delta measured here is comparable with the rest of the chapter.
Candidates from all query variants are fused with RRF *before* the reranker, so the cross-encoder
runs once per question instead of once per variant.

Run from the `code/` directory:  ../.venv/bin/python experiments/04_full_stack.py
"""
from __future__ import annotations

import sys

from ragbook.corpus import fixed_window_chunks, load_sections
from ragbook.embed import Embedder
from ragbook.evaluate import evaluate, load_golden
from ragbook.queries import ScriptedLLM, expand_query, load_variants, rrf
from ragbook.store import DenseIndex

try:
    from ragbook.chunking import project_chunks
    from ragbook.hybrid import project_retriever
except ImportError as exc:  # chapters 2 and 3 are written in parallel with this one
    print(f"Brakuje modułu z rozdziału 2 albo 3 ({exc}). Uruchom ten skrypt, gdy powstaną "
          f"`ragbook/chunking.py` (project_chunks) i `ragbook/hybrid.py` (project_retriever).")
    sys.exit(1)

K, K_WIDE, POOL = 5, 20, 30
COLUMNS = ["n", "recall@5", "recall@20", "mrr@5", "ndcg@5", "misses@5"]
LABELS = {"n": "Pytań", "recall@5": "recall@5", "recall@20": "recall@20",
          "mrr@5": "MRR@5", "ndcg@5": "nDCG@5", "misses@5": "Bez trafienia"}


def table(rows: list[dict]) -> str:
    lines = ["| Wariant | " + " | ".join(LABELS[c] for c in COLUMNS) + " |",
             "|---|" + "|".join("---" for _ in COLUMNS) + "|"]
    for r in rows:
        cells = [f"{r[c]:.2f}".replace(".", ",") if isinstance(r[c], float) else str(r[c]) for c in COLUMNS]
        lines.append(f"| {r['name']} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main() -> None:
    sections = load_sections()
    golden = load_golden()
    variants = load_variants()
    by_question = {q.question: q.id for q in golden}
    embedder = Embedder()
    llm = ScriptedLLM(variants)

    rows = []

    # Reference point: the chapter-1 baseline, same numbers as everywhere else in this book.
    base_chunks = fixed_window_chunks(sections, embedder.tokenizer, window=128, overlap=32)
    base_index = DenseIndex(embedder, base_chunks)
    res = evaluate(base_index.search, golden, k=K, ks=(K, K_WIDE))
    rows.append({"name": "baseline z rozdziału 1", **{c: res[c] for c in COLUMNS}})
    del base_index, base_chunks

    chunks = project_chunks(sections, embedder.tokenizer)
    retriever = project_retriever(chunks, embedder=embedder)
    print(f"chunków z rozdziału 2: {len(chunks)}; retriever z rozdziału 3: "
          f"tryb {retriever.mode}, rerank {'tak' if retriever.reranker else 'nie'}")

    def full_stack(question: str, k: int):
        return retriever(question, k)

    def expanded(mode: str):
        def retrieve(question: str, k: int):
            queries = expand_query(question, llm.for_question(by_question[question]), mode=mode)
            pool = rrf([retriever.candidates(q, POOL) for q in queries], limit=POOL)
            if retriever.reranker:
                pool = retriever.reranker.rerank(question, pool, top_k=len(pool))
            return pool[:k]
        return retrieve

    per_question = {}
    for name, retrieve in [("rozdz. 2 + 3 (pytanie użytkownika)", full_stack),
                           ("rozdz. 2 + 3 + multi-query", expanded("multi")),
                           ("rozdz. 2 + 3 + HyDE + pytanie", expanded("hyde+q"))]:
        res = evaluate(retrieve, golden, k=K, ks=(K, K_WIDE))
        rows.append({"name": name, **{c: res[c] for c in COLUMNS}})
        per_question[name] = {row["id"]: row["recall@5"] for row in res["per_question"]}
        print(f"{name}: recall@5 {res['recall@5']:.2f}, misses {res['misses@5']}")

    print("\n=== Cały potok, 49 pytań pozytywnych ===")
    print(table(rows))

    stack = per_question["rozdz. 2 + 3 (pytanie użytkownika)"]
    print("\n=== Co zmienia przekształcanie zapytań na gotowym potoku ===")
    for name in ("rozdz. 2 + 3 + multi-query", "rozdz. 2 + 3 + HyDE + pytanie"):
        per = per_question[name]
        better = sorted(qid for qid in stack if per[qid] > stack[qid])
        worse = sorted(qid for qid in stack if per[qid] < stack[qid])
        print(f"{name}: lepiej {', '.join(better) or '-'}; gorzej {', '.join(worse) or '-'}")
    retriever.close()


if __name__ == "__main__":
    main()
