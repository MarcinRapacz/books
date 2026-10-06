"""One record per query: what was asked, what was retrieved, what was answered, how long and how much.

A `Trace` is a dataclass written as one JSON line. It is deliberately flat and provider-independent:
the same record feeds a JSONL file on disk, an OpenTelemetry span tree or Langfuse, and it is the only
thing you have when a user says "yesterday it answered nonsense".
"""
from __future__ import annotations

import hashlib
import json
import statistics
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


def prompt_hash(system: str, context: str, question: str) -> str:
    """Identifies the prompt *shape*: system prompt + context + question, hashed together."""
    h = hashlib.sha256()
    for part in (system, context, question):
        h.update(part.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()[:16]


@dataclass
class Retrieved:
    id: str
    chapter: int
    section: str
    score: float


@dataclass
class Trace:
    query_id: str = field(default_factory=lambda: f"q_{uuid.uuid4().hex[:12]}")
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    question: str = ""
    user_id: str = ""
    groups: list[str] = field(default_factory=list)
    variant: dict = field(default_factory=dict)          # collection, embedding model, chunker, k
    retrieved: list[Retrieved] = field(default_factory=list)
    context_tokens: int = 0
    prompt_hash: str = ""
    answer: str = ""
    refused: bool = False
    cache: dict = field(default_factory=dict)            # {"embedding": "hit"/"miss", "answer": ...}
    flags: list[str] = field(default_factory=list)       # injection patterns, moderation, policy hits
    latency_ms: dict = field(default_factory=dict)       # per stage
    usage: dict = field(default_factory=dict)            # input/output tokens reported by the API
    cost_usd: float = 0.0
    feedback: str | None = None                          # "up" / "down" / None
    error: str | None = None

    @contextmanager
    def stage(self, name: str):
        """Time one stage of the pipeline and store it in `latency_ms`."""
        started = time.perf_counter()
        try:
            yield
        finally:
            self.latency_ms[name] = round((time.perf_counter() - started) * 1000, 1)

    @property
    def total_ms(self) -> float:
        return round(sum(self.latency_ms.values()), 1)

    def to_json(self) -> str:
        d = asdict(self)
        d["total_ms"] = self.total_ms
        return json.dumps(d, ensure_ascii=False)


class TraceLog:
    """Append-only JSONL sink. In production this is a queue plus a warehouse table; the shape is the same."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, trace: Trace) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(trace.to_json() + "\n")

    def read(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]


def percentiles(values: list[float], ps: tuple[int, ...] = (50, 90, 95, 99)) -> dict[str, float]:
    """Percentiles by nearest rank; latency is never summarised by its mean."""
    if not values:
        return {f"p{p}": 0.0 for p in ps}
    ordered = sorted(values)
    out = {}
    for p in ps:
        idx = min(len(ordered) - 1, max(0, int(round(p / 100 * len(ordered) + 0.5)) - 1))
        out[f"p{p}"] = round(ordered[idx], 1)
    return out


def online_metrics(records: list[dict]) -> dict:
    """The dashboard you watch in production, computed from the trace log alone (no labels needed)."""
    n = len(records)
    if not n:
        return {}
    top1 = [r["retrieved"][0]["score"] for r in records if r["retrieved"]]
    ctx = [r["context_tokens"] for r in records]
    feedback = [r["feedback"] for r in records if r["feedback"]]
    stages = {name for r in records for name in r["latency_ms"]}
    return {
        "queries": n,
        "refusal_rate": round(sum(1 for r in records if r["refused"]) / n, 3),
        "empty_retrieval_rate": round(sum(1 for r in records if not r["retrieved"]) / n, 3),
        "top1_score_mean": round(statistics.fmean(top1), 3) if top1 else 0.0,
        "top1_score_p10": round(sorted(top1)[len(top1) // 10], 3) if top1 else 0.0,
        "context_tokens": {"median": int(statistics.median(ctx)), "max": max(ctx)},
        "answer_cache_hit_rate": round(sum(1 for r in records if r["cache"].get("answer") == "hit") / n, 3),
        "embedding_cache_hit_rate": round(sum(1 for r in records if r["cache"].get("embedding") == "hit") / n, 3),
        "flagged_rate": round(sum(1 for r in records if r.get("flags")) / n, 3),
        "cost_usd_total": round(sum(r["cost_usd"] for r in records), 4),
        "latency_ms": {stage: percentiles([r["latency_ms"][stage] for r in records if stage in r["latency_ms"]])
                       for stage in sorted(stages)},
        "latency_ms_total": percentiles([round(sum(r["latency_ms"].values()), 1) for r in records]),
        "feedback": {"up": feedback.count("up"), "down": feedback.count("down"),
                     "rate": round(len(feedback) / n, 3)},
    }
