"""Chapter 5, table 1: Markdown vs raw PDF vs cleaned PDF, on data/golden_pdf.jsonl.

Run from `code/`:  ../.venv/bin/python experiments/05_pdf.py
"""
from pathlib import Path

from ragbook import pdf
from ragbook.corpus import fixed_window_chunks, load_sections
from ragbook.embed import Embedder
from ragbook.evaluate import evaluate, format_table, load_golden
from ragbook.store import DenseIndex

GOLDEN = Path("data/golden_pdf.jsonl")
WINDOW, OVERLAP, K = 128, 32, 5


def main() -> None:
    golden = load_golden(GOLDEN)
    embedder = Embedder()
    tok = embedder.tokenizer

    lines_all = pdf.load_lines(drop_running=False)
    lines_kept = pdf.load_lines()
    els = pdf.elements(lines_kept)
    print(f"lines: {len(lines_all)}, dropped as running head/folio: {len(lines_all) - len(lines_kept)}")
    print("paragraphs re-joined across a page break:",
          sum(1 for e in els if e.kind == "para" and len(e.pages) > 1))

    variants = {
        "Markdown (ground truth)": load_sections(),
        "PDF surowy, nagłówki zgadywane": pdf.raw_sections(headings="guess"),
        "PDF surowy, nagłówki podpowiedziane": pdf.raw_sections(headings="known"),
        "PDF oczyszczony": pdf.clean_sections(),
    }
    truth = {s.key for s in load_sections()}

    tables_golden = load_golden(Path("data/golden_tables.jsonl"))
    rows, table_rows = [], []
    for name, sections in variants.items():
        chunks = fixed_window_chunks(sections, tok, WINDOW, OVERLAP)
        index = DenseIndex(embedder, chunks, collection=name[:10])
        res = evaluate(lambda q, k: index.search(q, k), golden, k=K)
        tab = evaluate(lambda q, k: index.search(q, k), tables_golden, k=K)
        keys = {s.key for s in sections}
        rows.append({"name": name, "chunks": len(chunks), "sections": f"{len(keys & truth)}/{len(keys)}",
                     **{m: res[m] for m in ("recall@5", "recall@20", "mrr@5", "misses@5")}})
        table_rows.append({"name": name, **{m: tab[m] for m in ("recall@5", "mrr@5", "misses@5")}})
        print(name, {m: round(res[m], 3) for m in ("recall@5", "recall@20", "mrr@5")},
              "misses:", res["misses@5"], "| tabele recall@5:", round(tab["recall@5"], 3))
        for row in res["per_question"]:
            if row["recall@5"] == 0:
                print("   miss:", row["id"], row["top"][:2])
        del index

    print()
    print(format_table(rows, ["sections", "chunks", "recall@5", "recall@20", "mrr@5", "misses@5"],
                       {"sections": "Sekcje trafne/wszystkie", "chunks": "Chunki",
                        "misses@5": "Pytania bez trafienia"}))
    print()
    print("pytania o wartości z tabel (data/golden_tables.jsonl):")
    print(format_table(table_rows, ["recall@5", "mrr@5", "misses@5"],
                       {"misses@5": "Pytania bez trafienia"}))


if __name__ == "__main__":
    main()
