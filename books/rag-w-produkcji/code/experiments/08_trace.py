"""Chapter 8: one trace record per query, and the online metrics you compute from the log.

The retrieval half of the pipeline is real (embedding cache, Qdrant, token counts, latencies, cost model).
Generation is stubbed -- there is no API key here -- and the stub is marked in the trace as `model: "stub"`,
so nothing in the numbers pretends to come from Claude.

Run from the `code/` directory:  ../.venv/bin/python experiments/08_trace.py
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from qdrant_client import QdrantClient

from ragbook.cache import QueryEmbeddingCache, load_pairs
from ragbook.cost import QueryCost
from ragbook.embed import Embedder
from ragbook.indexing import Index, acl_filter, chunk_document, load_documents
from ragbook.security import SYSTEM_POLICY, as_data_block, scan
from ragbook.trace import Retrieved, Trace, TraceLog, online_metrics, prompt_hash

TRACE_PATH = Path("data/traces_08.jsonl")
MODEL = "claude-opus-5"
OUTPUT_TOKENS = 300
SCORE_FLOOR = 0.86          # below this we refuse instead of answering from weak context


def main() -> None:
    random.seed(11)
    questions = [q for pair in load_pairs(Path("data/queries_08.jsonl")) for q in pair[:2]]

    embedder = Embedder()
    docs = load_documents()
    for d in docs:
        d.groups = ("public",) if int(d.doc_id[:2]) <= 7 else ("internal",)
    chunks = [c for d in docs for c in chunk_document(d, embedder.tokenizer)]

    client = QdrantClient(":memory:")
    index = Index(client, "chunks_e5_w128", embedder, recreate=True)
    index.sync(chunks)
    embedder.cache = False      # from here on, a query embedding is really computed on a miss
    qcache = QueryEmbeddingCache(embedder)
    tokenizer = embedder.tokenizer

    if TRACE_PATH.exists():
        TRACE_PATH.unlink()
    log = TraceLog(TRACE_PATH)

    # every second question is asked twice, so the log contains real cache hits
    stream = questions + questions[:10]

    for i, question in enumerate(stream):
        t = Trace(question=question, user_id=f"u{i % 7:02d}", groups=["public", "internal"],
                  variant={"collection": index.collection, "embedding_model": embedder.model_name,
                           "chunker": "fixed-128-32", "k": 5, "generator": "stub"})
        before = qcache.stats.hits
        with t.stage("embed_query"):
            qcache.embed(question)
        t.cache["embedding"] = "hit" if qcache.stats.hits > before else "miss"
        t.cache["answer"] = "miss"

        with t.stage("retrieval"):
            hits = index.search(question, k=5, query_filter=acl_filter(t.groups))
        t.retrieved = [Retrieved(c.id, c.chapter, c.section, round(c.meta["score"], 4)) for c in hits]

        with t.stage("build_prompt"):
            context = as_data_block(hits)
            t.context_tokens = len(tokenizer(context, add_special_tokens=False)["input_ids"])
            t.prompt_hash = prompt_hash(SYSTEM_POLICY, context, question)
            flagged = sorted({f for c in hits for f in scan(c.text)})
            t.flags = flagged

        with t.stage("generation"):
            top1 = t.retrieved[0].score if t.retrieved else 0.0
            if top1 < SCORE_FLOOR:
                t.answer, t.refused = "Nie wiem – w dokumentacji nie ma podstawy do odpowiedzi.", True
            else:
                t.answer = f"[stub] Odpowiedź na podstawie rozdziału {t.retrieved[0].chapter}."

        sys_tokens = len(tokenizer(SYSTEM_POLICY, add_special_tokens=False)["input_ids"])
        q_tokens = len(tokenizer(question, add_special_tokens=False)["input_ids"])
        out_tokens = 0 if t.refused else OUTPUT_TOKENS
        t.usage = {"input_tokens": sys_tokens + t.context_tokens + q_tokens, "output_tokens": out_tokens}
        t.cost_usd = round(QueryCost(MODEL, t.usage["input_tokens"], out_tokens).total, 6)

        if random.random() < 0.25:                      # simulated user feedback
            t.feedback = "down" if t.refused or t.retrieved[0].score < 0.88 else "up"
        log.append(t)

    records = log.read()
    print(f"traces written: {len(records)} -> {TRACE_PATH}")
    print("\n=== one record ===")
    print(json.dumps(records[3], ensure_ascii=False, indent=2)[:1800])

    print("\n=== online metrics ===")
    print(json.dumps(online_metrics(records), ensure_ascii=False, indent=2))

    worst = sorted(records, key=lambda r: r["retrieved"][0]["score"])[:5]
    print("\n=== five weakest top-1 scores (the queue for the golden set) ===")
    for r in worst:
        print(f"  {r['retrieved'][0]['score']:.3f}  {r['question']}")


if __name__ == "__main__":
    main()
