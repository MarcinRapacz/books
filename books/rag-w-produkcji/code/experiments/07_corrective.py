"""Chapter 7, part 3: corrective RAG measured locally.

The cross-encoder plays CRAG's retrieval evaluator, and pseudo-relevance feedback plays its
web-search fallback. Everything is real: no API key, and never two models in memory at once - the
script loads the embedder, frees it, loads the cross-encoder, frees it, and repeats.

Run from the `code/` directory:

    ../.venv/bin/python experiments/07_corrective.py
"""
from __future__ import annotations

import gc
import time

import numpy as np

from ragbook.agentic import CrossEncoderGrader, Vocabulary, expand_query
from ragbook.corpus import fixed_window_chunks, load_sections
from ragbook.embed import Embedder
from ragbook.evaluate import by_type, evaluate, load_golden

WINDOW, OVERLAP = 128, 32
K, K_WIDE = 5, 20
POOL = 20
THRESHOLDS = (-6.0, -4.0, -2.0, 0.0, 2.0)
MIN_KEPT = 3
FEEDBACK_TERMS = 5
FEEDBACK_DOCS = 3


def ranking_retriever(table: dict[str, list]):
    def retrieve(question: str, k: int = 5):
        return table[question][:k]
    return retrieve


def row(name, table, golden):
    result = evaluate(ranking_retriever(table), golden, k=K, ks=(K, K_WIDE))
    return {"name": name, "recall@5": result["recall@5"], "recall@20": result["recall@20"],
            "mrr@5": result["mrr@5"], "ndcg@5": result["ndcg@5"], "misses@5": result["misses@5"],
            "comp@5": by_type(result, "recall@5").get("comparative", 0.0), "result": result}


def print_table(rows):
    print("| Wariant | recall@5 | recall@20 | MRR@5 | nDCG@5 | comparative recall@5 | bez trafienia |")
    print("|---|---|---|---|---|---|---|")
    for r in rows:
        print(f"| {r['name']} | {r['recall@5']:.2f} | {r['recall@20']:.2f} | {r['mrr@5']:.2f} "
              f"| {r['ndcg@5']:.2f} | {r['comp@5']:.2f} | {r['misses@5']} |".replace(".", ","))


def main() -> None:
    sections = load_sections()
    golden = load_golden()

    # --- phase 1: the embedder alone ------------------------------------------------------
    embedder = Embedder()
    chunks = fixed_window_chunks(sections, embedder.tokenizer, window=WINDOW, overlap=OVERLAP)
    matrix = embedder.embed_passages([c.text for c in chunks])
    questions = [q.question for q in golden]
    qvecs = embedder.embed_queries(questions)

    def dense(qv, pool=POOL):
        cos = matrix @ qv
        order = np.argsort(-cos)[:pool]
        out = []
        for i in order:
            c = chunks[int(i)]
            out.append(type(c)(c.id, c.chapter, c.section, c.text,
                               {**c.meta, "score": float(cos[int(i)])}))
        return out

    first = {q: dense(qvecs[i]) for i, q in enumerate(questions)}
    del embedder
    gc.collect()

    # --- phase 2: the cross-encoder alone -------------------------------------------------
    grader = CrossEncoderGrader()
    t0 = time.perf_counter()
    scores = {q: grader.score(q, first[q]) for q in questions}
    grade_ms = 1000 * (time.perf_counter() - t0) / len(questions)
    print(f"ocena {POOL} fragmentów cross-encoderem: {grade_ms:.0f} ms na pytanie "
          f"({len(questions)} pytań)")

    relevant = {q.question: q.relevant for q in golden}
    good = [s for q in questions if relevant[q]
            for c, s in zip(first[q], scores[q]) if c.key in relevant[q]]
    bad = [s for q in questions if relevant[q]
           for c, s in zip(first[q], scores[q]) if c.key not in relevant[q]]
    neg = [s for q in questions if not relevant[q] for s in scores[q]]
    print("\n=== Rozkład ocen cross-encodera w top-20 ===")
    print("| Grupa | Fragmentów | min | mediana | średnia | maks |")
    print("|---|---|---|---|---|---|")
    for name, values in (("z sekcji trafnej", good), ("z sekcji nietrafnej", bad),
                         ("pytania negatywne", neg)):
        arr = np.array(values)
        print(f"| {name} | {len(arr)} | {arr.min():.2f} | {np.median(arr):.2f} "
              f"| {arr.mean():.2f} | {arr.max():.2f} |".replace(".", ","))

    print("\n=== Ile pytań uruchomiłoby drugie wyszukiwanie ===")
    print("| Próg | Zachowanych fragmentów (mediana) | Pytań poniżej progu | Pytań pozytywnych |")
    print("|---|---|---|---|")
    for threshold in THRESHOLDS:
        kept = [sum(1 for s in scores[q] if s >= threshold) for q in questions]
        trig = [q for q, n in zip(questions, kept) if n < MIN_KEPT]
        print(f"| {threshold:.1f} | {int(np.median(kept))} | {len(trig)} "
              f"| {sum(1 for q in trig if relevant[q])} |".replace(".", ","))

    reranked = {q: [c for _, c in sorted(zip(scores[q], first[q]),
                                         key=lambda kv: -kv[0])] for q in questions}

    vocab = Vocabulary([c.text for c in chunks])
    second_query = {}
    for threshold in THRESHOLDS:
        for q in questions:
            kept = sum(1 for s in scores[q] if s >= threshold)
            if kept < MIN_KEPT and (threshold, q) not in second_query:
                second_query[(threshold, q)] = expand_query(q, reranked[q][:FEEDBACK_DOCS],
                                                            vocab, FEEDBACK_TERMS)
    del grader
    gc.collect()

    print("\n=== Przykładowe przepisane zapytania (próg -2,0) ===")
    shown = 0
    for (threshold, q), q2 in second_query.items():
        if threshold == -2.0 and shown < 4:
            print(f"  {q}\n  -> {q2}")
            shown += 1

    # --- phase 3: the embedder again ------------------------------------------------------
    embedder = Embedder()
    extra_queries = sorted(set(second_query.values()))
    second_hits = {}
    if extra_queries:
        vecs = embedder.embed_queries(extra_queries)
        matrix2 = embedder.embed_passages([c.text for c in chunks])
        for i, text in enumerate(extra_queries):
            cos = matrix2 @ vecs[i]
            order = np.argsort(-cos)[:POOL]
            second_hits[text] = [chunks[int(j)] for j in order]
    del embedder
    gc.collect()

    # --- phase 4: the cross-encoder again -------------------------------------------------
    grader = CrossEncoderGrader()
    corrective = {}
    stats = {}
    for threshold in THRESHOLDS:
        table = {}
        fired = 0
        for q in questions:
            pool = list(first[q])
            pool_scores = list(scores[q])
            q2 = second_query.get((threshold, q))
            if q2:
                fired += 1
                fresh = [c for c in second_hits[q2] if c.id not in {x.id for x in pool}]
                if fresh:
                    pool += fresh
                    pool_scores += grader.score(q, fresh)
            table[q] = [c for _, c in sorted(zip(pool_scores, pool), key=lambda kv: -kv[0])]
        corrective[threshold] = table
        stats[threshold] = fired
    del grader
    gc.collect()

    print("\n=== Wyniki ===")
    rows = [row("gęsty baseline (rozdział 1)", first, golden),
            row("reranking cross-encoderem 20 -> 5 (rozdział 3)", reranked, golden)]
    for threshold in THRESHOLDS:
        rows.append(row(f"corrective, próg {threshold:.1f} ({stats[threshold]} pytań z drugim "
                        f"wyszukiwaniem)".replace(".", ","), corrective[threshold], golden))
    print_table(rows)

    print("\n=== Co zmieniło drugie wyszukiwanie (próg -2,0) ===")
    base = {r["id"]: r for r in rows[1]["result"]["per_question"]}
    best = row("corr", corrective[-2.0], golden)
    for r in best["result"]["per_question"]:
        delta = r["recall@5"] - base[r["id"]]["recall@5"]
        if delta:
            print(f"  {r['id']} [{r['type']}] {delta:+.2f}")


if __name__ == "__main__":
    main()
