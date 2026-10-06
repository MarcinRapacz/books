"""A stricter relevance check than section-level recall: did the answer text actually come back?

Section relevance says whether the retrieved chunk belongs to the right section. For a question about
a value in a table or an identifier in a snippet that is not enough - the chunk can sit in the right
section and still have lost the row or the line that answers the question. The evaluation files of
this chapter (`data/golden_tables.jsonl`, `data/golden_code.jsonl`) therefore carry an extra `value`
field, and this module checks for it literally in the top-k texts.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


def _norm(s: str) -> str:
    return re.sub(r"[\s`*]+", " ", s).lower().strip()


def value_hits(index, golden_path, k: int = 5) -> tuple[float, list[str]]:
    """Stricter than section recall: did any of the top-k chunks literally contain the answer value?

    `golden_path` points at a JSONL file whose rows carry an extra `value` field.
    Returns (share of questions whose value appeared in the top-k, ids of the questions where it did not).
    """
    rows = [json.loads(line) for line in Path(golden_path).read_text(encoding="utf-8").splitlines() if line.strip()]
    hits, missed = 0, []
    for row in rows:
        needle = _norm(row["value"])
        got = index.search(row["question"], k)
        if any(needle in _norm(c.text) for c in got):
            hits += 1
        else:
            missed.append(row["id"])
    return hits / len(rows), missed
