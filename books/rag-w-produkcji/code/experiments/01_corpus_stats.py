"""Corpus statistics for chapter 1: size of volume 1, per-chapter breakdown, section length distribution.

Run from the `code/` directory:  ../.venv/bin/python experiments/01_corpus_stats.py
"""
from __future__ import annotations

import re
import statistics

from transformers import AutoTokenizer

from ragbook.corpus import load_sections
from ragbook.embed import DEFAULT_MODEL

FENCE = re.compile(r"^```")
TABLE_ROW = re.compile(r"^\s*\|")


def content_mix(text: str) -> dict[str, int]:
    """Classify every line of a section body as code / table / prose.

    Markdown keeps a whole paragraph on one line, so line counts alone are misleading;
    we also sum characters, which is what the chunker actually has to cut through.
    """
    out = {"code_lines": 0, "table_lines": 0, "prose_lines": 0,
           "code_chars": 0, "table_chars": 0, "prose_chars": 0}
    in_fence = False
    for line in text.splitlines():
        if FENCE.match(line):
            in_fence = not in_fence
            out["code_lines"] += 1
            out["code_chars"] += len(line)
            continue
        if in_fence:
            out["code_lines"] += 1
            out["code_chars"] += len(line)
        elif TABLE_ROW.match(line):
            out["table_lines"] += 1
            out["table_chars"] += len(line)
        elif line.strip():
            out["prose_lines"] += 1
            out["prose_chars"] += len(line)
    return out


def main() -> None:
    sections = load_sections()
    tokenizer = AutoTokenizer.from_pretrained(DEFAULT_MODEL)

    rows = []
    for s in sections:
        n_tokens = len(tokenizer(s.text, add_special_tokens=False)["input_ids"])
        rows.append({"chapter": s.chapter, "title": s.title, "section": s.section,
                     "words": len(s.text.split()), "tokens": n_tokens,
                     "chars": len(s.text), **content_mix(s.text)})

    total_words = sum(r["words"] for r in rows)
    total_tokens = sum(r["tokens"] for r in rows)
    body_chars = sum(r["code_chars"] + r["table_chars"] + r["prose_chars"] for r in rows)
    code_chars = sum(r["code_chars"] for r in rows)
    table_chars = sum(r["table_chars"] for r in rows)

    print("=== Corpus totals ===")
    print(f"chapters: {len({r['chapter'] for r in rows})}")
    print(f"sections: {len(rows)}")
    print(f"words:    {total_words}")
    print(f"e5 tokens:{total_tokens}   tokens/word: {total_tokens / total_words:.2f}")
    print(f"code lines: {sum(r['code_lines'] for r in rows)}  table rows: {sum(r['table_lines'] for r in rows)}")
    print(f"chars: {body_chars}  code: {100 * code_chars / body_chars:.1f}%  "
          f"tables: {100 * table_chars / body_chars:.1f}%  "
          f"prose: {100 * (body_chars - code_chars - table_chars) / body_chars:.1f}%")

    print("\n=== Per chapter ===")
    print("| Rozdz. | Tytuł | Sekcje | Słowa | Tokeny e5 | Linie kodu | Wiersze tabel | Udział kodu |")
    print("|---|---|---|---|---|---|---|---|")
    for ch in sorted({r["chapter"] for r in rows}):
        part = [r for r in rows if r["chapter"] == ch]
        chars = sum(r["code_chars"] + r["table_chars"] + r["prose_chars"] for r in part)
        print(f"| {ch} | {part[0]['title']} | {len(part)} | {sum(r['words'] for r in part)} "
              f"| {sum(r['tokens'] for r in part)} | {sum(r['code_lines'] for r in part)} "
              f"| {sum(r['table_lines'] for r in part)} "
              f"| {100 * sum(r['code_chars'] for r in part) / chars:.0f}% |")

    lengths = sorted(r["tokens"] for r in rows)
    print("\n=== Section length in e5 tokens ===")
    print(f"min {lengths[0]}  p25 {lengths[len(lengths) // 4]}  median {statistics.median(lengths):.0f}  "
          f"p75 {lengths[3 * len(lengths) // 4]}  p90 {lengths[int(0.9 * len(lengths))]}  max {lengths[-1]}")
    buckets = [(0, 200), (200, 500), (500, 1000), (1000, 2000), (2000, 4000), (4000, 10**9)]
    print("\n| Długość sekcji (tokeny e5) | Sekcji | Udział | Słów łącznie |")
    print("|---|---|---|---|")
    for lo, hi in buckets:
        part = [r for r in rows if lo <= r["tokens"] < hi]
        label = f"{lo}–{hi}" if hi < 10**9 else f"{lo}+"
        share = f"{100 * len(part) / len(rows):.0f}%"
        print(f"| {label} | {len(part)} | {share} | {sum(r['words'] for r in part)} |")

    print("\n=== 8 longest sections ===")
    for r in sorted(rows, key=lambda r: -r["tokens"])[:8]:
        print(f"  ch{r['chapter']:2d} {r['tokens']:5d} tok  {r['section']!r}")

    boiler = [r for r in rows if r["section"] in ("Podsumowanie", "Co dalej", "Źródła")]
    intro = [r for r in rows if r["section"] == ""]
    print(f"\nboilerplate sections (Podsumowanie/Co dalej/Źródła): {len(boiler)}, "
          f"{sum(r['words'] for r in boiler)} words ({100 * sum(r['words'] for r in boiler) / total_words:.1f}%)")
    print(f"lead-in sections (text before the first ##): {len(intro)}, {sum(r['words'] for r in intro)} words")


if __name__ == "__main__":
    main()
