"""Chapter 5, table 3: fixed window vs code-aware chunking, on data/golden_code.jsonl.

Run from `code/`:  ../.venv/bin/python experiments/05_code.py
"""
from pathlib import Path

from ragbook.value_check import value_hits
from ragbook.code_chunks import code_aware_chunks, code_stats, split_segments
from ragbook.corpus import fixed_window_chunks, load_sections
from ragbook.embed import Embedder
from ragbook.evaluate import evaluate, format_table, load_golden
from ragbook.store import DenseIndex

GOLDEN = Path("data/golden_code.jsonl")
PROSE = Path("data/golden_pdf.jsonl")
WINDOW, OVERLAP, K = 128, 32, 5


def main() -> None:
    sections = load_sections()
    golden, prose_golden = load_golden(GOLDEN), load_golden(PROSE)
    embedder = Embedder()
    tok = embedder.tokenizer

    print("bloki kodu:", code_stats(sections, tok))

    # what the fixed window does to one snippet
    demo = next(s for s in sections if s.key == (12, "Obserwowalność"))
    block = next(t for k, t in split_segments(demo.text) if k == "code" and "start_as_current_span" in t)
    pieces = fixed_window_chunks(
        [type(demo)(demo.chapter, demo.title, demo.section, block, demo.path)], tok, WINDOW, OVERLAP)
    print(f"\nblok z {demo.section} ({len(tok(block, add_special_tokens=False)['input_ids'])} tokenów) "
          f"-> {len(pieces)} chunków w stałym oknie")
    for p in pieces:
        print("  ---", repr(p.text[:90]))

    variants = {
        "stałe okno (baseline)": fixed_window_chunks(sections, tok, WINDOW, OVERLAP),
        "blok kodu w całości": code_aware_chunks(sections, tok, WINDOW, OVERLAP, attach_lead=False),
        "blok kodu + poprzedzający akapit": code_aware_chunks(sections, tok, WINDOW, OVERLAP),
    }

    rows = []
    for label, chunks in variants.items():
        index = DenseIndex(embedder, chunks, collection=label[:10])
        res = evaluate(lambda q, k: index.search(q, k), golden, k=K)
        pro = evaluate(lambda q, k: index.search(q, k), prose_golden, k=K)
        ident, missed = value_hits(index, GOLDEN, K)
        rows.append({"name": label, "chunks": len(chunks),
                     **{m: res[m] for m in ("recall@5", "recall@20", "mrr@5", "misses@5")},
                     "value@5": ident, "prose@5": pro["recall@5"]})
        print("   identyfikator w top-5:", round(ident, 3), "brak dla:", missed)
        print(label, {m: round(res[m], 3) for m in ("recall@5", "recall@20", "mrr@5")},
              "misses:", res["misses@5"], "| proza recall@5:", round(pro["recall@5"], 3))
        for row in res["per_question"]:
            if row["recall@5"] == 0:
                print("   miss:", row["id"], row["top"][:2])
        del index

    print()
    print(format_table(rows, ["chunks", "recall@5", "mrr@5", "value@5", "misses@5", "prose@5"],
                       {"chunks": "Chunki", "value@5": "Identyfikator w top-5",
                        "misses@5": "Pytania bez trafienia",
                        "prose@5": "recall@5 na pytaniach o prozę"}))


if __name__ == "__main__":
    main()
