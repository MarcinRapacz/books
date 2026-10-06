"""Validate data/golden.jsonl against the corpus. Exits with 1 on the first broken invariant.

Run from the `code/` directory:  ../.venv/bin/python experiments/01_validate_golden.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter

from ragbook.corpus import load_sections
from ragbook.evaluate import GOLDEN_PATH, load_golden

# Relevance policy for the golden set (chapter 1 explains why):
# "Co dalej" and "Źródła" are never a valid answer, they only point elsewhere.
FORBIDDEN_SECTIONS = {"Co dalej", "Źródła"}
VALID_TYPES = {"factual", "procedural", "comparative", "negative"}
TARGET_SIZE = (50, 60)


def main() -> int:
    sections = load_sections()
    known = {s.key for s in sections}
    by_key = {s.key: s for s in sections}
    golden = load_golden()
    raw = [json.loads(line) for line in GOLDEN_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]

    errors: list[str] = []

    ids = [q.id for q in golden]
    for qid, count in Counter(ids).items():
        if count > 1:
            errors.append(f"duplicate id: {qid}")

    questions = [q.question.strip().lower() for q in golden]
    for text, count in Counter(questions).items():
        if count > 1:
            errors.append(f"duplicate question: {text[:60]}")

    for q, row in zip(golden, raw):
        if q.type not in VALID_TYPES:
            errors.append(f"{q.id}: unknown type {q.type!r}")
        if not q.question.strip():
            errors.append(f"{q.id}: empty question")
        # every (chapter, section) must exist in load_sections()
        for chapter, section in sorted(q.relevant):
            if (chapter, section) not in known:
                near = sorted(s for c, s in known if c == chapter)
                errors.append(f"{q.id}: no such section ({chapter}, {section!r}); chapter {chapter} has {near}")
            elif section in FORBIDDEN_SECTIONS:
                errors.append(f"{q.id}: section {section!r} is excluded by the relevance policy")
        if q.type == "negative":
            if q.relevant:
                errors.append(f"{q.id}: negative question must have an empty `relevant`")
            if row.get("answer"):
                errors.append(f"{q.id}: negative question must have an empty `answer`")
        else:
            if not q.relevant:
                errors.append(f"{q.id}: non-negative question with no relevant section")
            if len(q.answer.split()) < 3:
                errors.append(f"{q.id}: missing or too short reference answer")
        if q.type == "comparative" and len(q.relevant) < 2:
            errors.append(f"{q.id}: comparative question should point at 2+ sections")

    counts = Counter(q.type for q in golden)
    print(f"golden set: {len(golden)} questions, {sum(len(q.relevant) for q in golden)} relevance labels")
    for t in ("factual", "procedural", "comparative", "negative"):
        print(f"  {t:12} {counts[t]:3d}  ({100 * counts[t] / len(golden):.0f}%)")
    if not TARGET_SIZE[0] <= len(golden) <= TARGET_SIZE[1]:
        errors.append(f"golden set has {len(golden)} questions, expected {TARGET_SIZE[0]}-{TARGET_SIZE[1]}")

    hit_chapters = Counter(c for q in golden for c, _ in q.relevant)
    print("  chapters covered:", len(hit_chapters), "of", len({s.chapter for s in sections}),
          "->", dict(sorted(hit_chapters.items())))
    multi = [q.id for q in golden if len(q.relevant) > 1]
    print(f"  multi-section questions: {len(multi)}")
    lengths = [len(by_key[k].text.split()) for q in golden for k in q.relevant]
    print(f"  relevant sections: median length {sorted(lengths)[len(lengths) // 2]} words, "
          f"longest {max(lengths)} words")

    if errors:
        print("\nFAILED:")
        for e in errors:
            print("  -", e)
        return 1
    print("\nOK: every (chapter, section) exists in load_sections() and the policy holds.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
