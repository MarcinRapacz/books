"""Chapter 5, table 2: how to put a Markdown table into the index, on data/golden_tables.jsonl.

Run from `code/`:  ../.venv/bin/python experiments/05_tables.py
"""
from pathlib import Path

from ragbook.corpus import load_sections
from ragbook.embed import Embedder
from ragbook.evaluate import evaluate, format_table, load_golden
from ragbook.store import DenseIndex
from ragbook.value_check import value_hits
from ragbook.tables import build_chunks, find_tables, table_rows, table_sentences

GOLDEN = Path("data/golden_tables.jsonl")
WINDOW, OVERLAP, K = 128, 32, 5
MODES = {"stałe okno (baseline)": "window", "tabela jako jeden chunk": "table",
         "wiersz po wierszu": "rows", "wiersz jako zdanie": "sentences"}


def main() -> None:
    sections = load_sections()
    golden = load_golden(GOLDEN)
    embedder = Embedder()
    tok = embedder.tokenizer

    tables = find_tables(sections)
    print(f"tabele w korpusie: {len(tables)}, wierszy razem: {sum(len(t.rows) for t in tables)}")
    demo = next(t for t in tables if t.section == "RAG a fine-tuning")
    print("\nwiersz po wierszu:\n ", table_rows(demo)[2])
    print("wiersz jako zdanie:\n ", table_sentences(demo)[2])

    # what the fixed window does to that table
    from ragbook.corpus import fixed_window_chunks
    base = fixed_window_chunks([s for s in sections if s.key == demo.key], tok, WINDOW, OVERLAP)
    print(f"\nsekcja „{demo.section}” w stałym oknie: {len(base)} chunków")
    for c in base:
        print("  ---", repr(c.text[:110]))

    rows = []
    for label, mode in MODES.items():
        chunks = build_chunks(sections, tok, mode, WINDOW, OVERLAP)
        index = DenseIndex(embedder, chunks, collection=mode)
        res = evaluate(lambda q, k: index.search(q, k), golden, k=K)
        value_recall, missed = value_hits(index, GOLDEN, K)
        rows.append({"name": label, "chunks": len(chunks), "value@5": value_recall,
                     **{m: res[m] for m in ("recall@5", "recall@20", "mrr@5", "misses@5")}})
        print("   wartość w top-5:", round(value_recall, 3), "brak dla:", missed)
        print(label, {m: round(res[m], 3) for m in ("recall@5", "mrr@5")}, "misses:", res["misses@5"])
        for row in res["per_question"]:
            if row["recall@5"] == 0:
                print("   miss:", row["id"], row["top"][:2])
        del index

    print()
    print(format_table(rows, ["chunks", "recall@5", "mrr@5", "value@5", "misses@5"],
                       {"chunks": "Chunki", "value@5": "Wartość w top-5",
                        "misses@5": "Pytania bez trafienia"}))


if __name__ == "__main__":
    main()
