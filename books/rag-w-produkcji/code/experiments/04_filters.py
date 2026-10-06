"""Metadata filtering: what a correct chapter filter buys, and what a wrong one costs.

The oracle filter uses the chapter(s) from the golden set - an upper bound for self-query.
The wrong filter picks a deterministic other chapter - the lower bound, i.e. what a self-query
extractor does to you when it guesses. The break-even accuracy between them is printed at the end.

Run from the `code/` directory:  ../.venv/bin/python experiments/04_filters.py
"""
from __future__ import annotations

from collections import Counter

from ragbook.corpus import fixed_window_chunks, load_sections
from ragbook.embed import Embedder
from ragbook.evaluate import evaluate, load_golden
from ragbook.queries import chapter_filter, tag_chunks
from ragbook.store import DenseIndex

WINDOW, OVERLAP = 128, 32
K, K_WIDE = 5, 20
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
    embedder = Embedder()
    chunks = tag_chunks(fixed_window_chunks(sections, embedder.tokenizer, window=WINDOW, overlap=OVERLAP))
    index = DenseIndex(embedder, chunks)

    kinds = Counter(c.meta["kind"] for c in chunks)
    print(f"chunks: {len(chunks)}  " + "  ".join(f"{k}: {v} ({100 * v / len(chunks):.0f}%)"
                                                 for k, v in kinds.most_common()))

    wanted = {q.question: sorted({ch for ch, _ in q.relevant}) for q in golden if q.relevant}
    chapters = sorted({s.chapter for s in sections})

    def no_filter(question: str, k: int):
        return index.search(question, k)

    def oracle(question: str, k: int):
        return index.search(question, k, query_filter=chapter_filter(wanted[question]))

    def wrong(question: str, k: int):
        good = set(wanted[question])
        pick = [c for c in chapters if c not in good][(len(question) * 7) % (len(chapters) - len(good))]
        return index.search(question, k, query_filter=chapter_filter(pick))

    def prose_only(question: str, k: int):
        from qdrant_client import models
        f = models.Filter(must=[models.FieldCondition(key="kind", match=models.MatchValue(value="prose"))])
        return index.search(question, k, query_filter=f)

    rows, results = [], {}
    for name, retrieve in [("bez filtra", no_filter),
                           ("filtr rozdziału trafny (oracle)", oracle),
                           ("filtr rozdziału błędny", wrong),
                           ("filtr kind = prose", prose_only)]:
        res = evaluate(retrieve, golden, k=K, ks=(K, K_WIDE))
        results[name] = res
        rows.append({"name": name, **{c: res[c] for c in COLUMNS}})
    print("\n=== Filtrowanie po metadanych, 49 pytań pozytywnych ===")
    print(table(rows))

    base = results["bez filtra"]["recall@5"]
    good = results["filtr rozdziału trafny (oracle)"]["recall@5"]
    bad = results["filtr rozdziału błędny"]["recall@5"]
    p = (base - bad) / (good - bad)
    print(f"\nProg opłacalności self-query: filtr musi być trafny w co najmniej "
          f"{100 * p:.0f}% przypadków, żeby nie pogorszyć recall@5 "
          f"(bez filtra {base:.2f}, trafny {good:.2f}, błędny {bad:.2f}).")

    # Multi-section questions cross chapters: how often is a single-chapter filter even possible?
    multi_chapter = sum(1 for chs in wanted.values() if len(chs) > 1)
    print(f"Pytań, których trafne sekcje leżą w więcej niż jednym rozdziale: "
          f"{multi_chapter} z {len(wanted)} - dla nich filtr po jednym rozdziale "
          f"z definicji gubi połowę odpowiedzi.")

    # Where does the oracle filter help most?
    per_base = {row["id"]: row["recall@5"] for row in results["bez filtra"]["per_question"]}
    per_good = {row["id"]: row["recall@5"] for row in results["filtr rozdziału trafny (oracle)"]["per_question"]}
    fixed = sorted(qid for qid in per_base if per_good[qid] > per_base[qid])
    print(f"Filtr trafny poprawia {len(fixed)} pytań: {', '.join(fixed)}")


if __name__ == "__main__":
    main()
