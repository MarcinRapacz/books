"""Retrieval metrics on the golden set. Relevance is judged at the *section* level:
a retrieved chunk is a hit if (chunk.chapter, chunk.section) is one of the question's relevant sections.

Metrics per question (then averaged):
- recall@k: fraction of relevant sections that appear among the sections of the top-k chunks
- MRR: 1 / rank of the first relevant chunk (0 if none in top-k)
- nDCG@k: DCG over chunk ranks with binary gains, deduplicated by section, normalised by the ideal DCG
Negative questions (no relevant sections) are skipped by the retrieval metrics and reported separately.
"""
from __future__ import annotations

import json
import math
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .corpus import Chunk

GOLDEN_PATH = Path(__file__).resolve().parent.parent / "data" / "golden.jsonl"


@dataclass
class Question:
    id: str
    question: str
    type: str
    relevant: set[tuple[int, str]]
    answer: str = ""


def load_golden(path: Path = GOLDEN_PATH) -> list[Question]:
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        rel = {(int(r["chapter"]), r["section"]) for r in d.get("relevant", [])}
        out.append(Question(d["id"], d["question"], d.get("type", "factual"), rel, d.get("answer", "")))
    return out


def recall_at_k(retrieved: list[Chunk], relevant: set[tuple[int, str]], k: int) -> float:
    got = {c.key for c in retrieved[:k]}
    return len(got & relevant) / len(relevant) if relevant else 0.0


def mrr(retrieved: list[Chunk], relevant: set[tuple[int, str]], k: int) -> float:
    for rank, c in enumerate(retrieved[:k], start=1):
        if c.key in relevant:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(retrieved: list[Chunk], relevant: set[tuple[int, str]], k: int) -> float:
    seen, dcg = set(), 0.0
    for rank, c in enumerate(retrieved[:k], start=1):
        if c.key in relevant and c.key not in seen:
            seen.add(c.key)
            dcg += 1.0 / math.log2(rank + 1)
    ideal = sum(1.0 / math.log2(r + 1) for r in range(1, min(len(relevant), k) + 1))
    return dcg / ideal if ideal else 0.0


Retriever = Callable[[str, int], list[Chunk]]


def evaluate(retrieve: Retriever, golden: list[Question], k: int = 5, ks: tuple[int, ...] = (5, 20)) -> dict:
    """Run `retrieve(question, max(ks))` for every non-negative question and average the metrics.

    Returns {"n": ..., "recall@5": ..., "recall@20": ..., "mrr@5": ..., "ndcg@5": ..., "misses@5": ...,
             "per_question": [{"id", "type", "recall@k", "mrr", "hit_rank", "top": [(chapter, section, score), ...]}]}
    """
    kmax = max(max(ks), k)
    qs = [q for q in golden if q.relevant]
    agg = {f"recall@{kk}": 0.0 for kk in ks} | {f"mrr@{k}": 0.0, f"ndcg@{k}": 0.0, f"misses@{k}": 0}
    per = []
    for q in qs:
        got = retrieve(q.question, kmax)
        row = {"id": q.id, "type": q.type, "top": [(c.chapter, c.section, round(c.meta.get("score", 0.0), 3)) for c in got[:k]]}
        for kk in ks:
            r = recall_at_k(got, q.relevant, kk)
            agg[f"recall@{kk}"] += r
            row[f"recall@{kk}"] = r
        m = mrr(got, q.relevant, k)
        agg[f"mrr@{k}"] += m
        agg[f"ndcg@{k}"] += ndcg_at_k(got, q.relevant, k)
        row["mrr"] = m
        row["hit_rank"] = int(round(1 / m)) if m else None
        if recall_at_k(got, q.relevant, k) == 0:
            agg[f"misses@{k}"] += 1
        per.append(row)
    n = len(qs)
    out = {key: (val / n if key.startswith(("recall", "mrr", "ndcg")) else val) for key, val in agg.items()}
    out["n"] = n
    out["per_question"] = per
    return out


def by_type(result: dict, metric: str = "recall@5") -> dict[str, float]:
    """Average one per-question metric grouped by question type."""
    groups: dict[str, list[float]] = {}
    for row in result["per_question"]:
        groups.setdefault(row["type"], []).append(row[metric])
    return {t: sum(v) / len(v) for t, v in groups.items()}


def format_table(rows: list[dict], columns: list[str], labels: dict[str, str] | None = None) -> str:
    """Render a Markdown table (Polish decimal comma) from a list of result dicts, each with a "name" key."""
    labels = labels or {}
    head = "| Wariant | " + " | ".join(labels.get(c, c) for c in columns) + " |"
    sep = "|---|" + "|".join("---" for _ in columns) + "|"
    lines = [head, sep]
    for r in rows:
        cells = []
        for c in columns:
            v = r[c]
            cells.append(f"{v:.2f}".replace(".", ",") if isinstance(v, float) else str(v))
        lines.append(f"| {r['name']} | " + " | ".join(cells) + " |")
    return "\n".join(lines)
