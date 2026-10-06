"""Diversifying the top-5: a cap on chunks per section, or MMR over the dense vectors.

Multi-section questions (mostly `comparative`) need two different sections inside the top-5, and both
the dense ranking and the reranker like to fill the list from one place. Measured on the reranked
hybrid candidates, so the only thing that changes is the last step.

Run from the `code/` directory:  ../.venv/bin/python experiments/03_diversify.py
"""
from __future__ import annotations

from ragbook.corpus import fixed_window_chunks, load_sections
from ragbook.embed import Embedder
from ragbook.evaluate import by_type, evaluate, load_golden
from ragbook.hybrid import (BM25Index, HybridIndex, minmax, cap_per_section, make_tokenizer,
                            mmr)
from ragbook.rerank import MMARCO, CrossEncoderReranker
from ragbook.store import DenseIndex

CHUNKER = lambda sections, tokenizer: fixed_window_chunks(sections, tokenizer, window=128, overlap=32)
K, POOL, STEM, RRF_K = 5, 20, 5, 60


def main() -> None:
    embedder = Embedder()
    chunks = CHUNKER(load_sections(), embedder.tokenizer)
    golden = load_golden()
    questions = [q for q in golden if q.relevant]

    dense = DenseIndex(embedder, chunks)
    lexical = BM25Index(chunks, make_tokenizer(STEM))
    hybrid = HybridIndex(dense, lexical, method="rrf", rrf_k=RRF_K, pool=50)
    candidates = {q.id: hybrid.search(q.question, POOL) for q in questions}
    del dense, lexical, hybrid

    reranker = CrossEncoderReranker(MMARCO)
    ranked = {q.id: reranker.rerank(q.question, candidates[q.id], top_k=POOL) for q in questions}
    reranker.close()

    vectors = embedder.embed_passages([c.text for c in chunks])
    position = {c.id: i for i, c in enumerate(chunks)}
    qvecs = {q.id: embedder.embed_queries([q.question])[0] for q in questions}
    by_question = {q.question: q.id for q in questions}

    def variant(name: str, pick):
        got = {qid: pick(qid, ranked[qid]) for qid in ranked}
        result = evaluate(lambda question, k: got[by_question[question]][:k], golden, k=K, ks=(K, POOL))
        sections = [len({c.key for c in got[qid][:K]}) for qid in got]
        comparative = by_type(result, "recall@5").get("comparative", 0.0)
        print(f"| {name} | {result['recall@5']:.2f} | {comparative:.2f} | {result['mrr@5']:.2f} "
              f"| {result['ndcg@5']:.2f} | {sum(sections) / len(sections):.1f} |".replace(".", ","))
        return result

    print("| Wariant | recall@5 | recall@5 comparative | MRR@5 | nDCG@5 | Sekcji w top-5 |")
    print("|---|---|---|---|---|---|")
    variant("hybryda + rerank (bez dywersyfikacji)", lambda qid, cs: cs)
    for cap in (3, 2, 1):
        variant(f"limit {cap} chunków na sekcję", lambda qid, cs, cap=cap: cap_per_section(cs, POOL, cap))
    for lam in (0.9, 0.8, 0.7, 0.5):
        variant(f"MMR na kosinusie, lambda={lam}".replace(".", ","),
                lambda qid, cs, lam=lam: mmr(cs, vectors[[position[c.id] for c in cs]],
                                             qvecs[qid], POOL, lam))
    for lam in (0.9, 0.8, 0.7):
        variant(f"MMR na score cross-enkodera, lambda={lam}".replace(".", ","),
                lambda qid, cs, lam=lam: mmr(cs, vectors[[position[c.id] for c in cs]],
                                             qvecs[qid], POOL, lam,
                                             relevance=minmax([c.meta["score"] for c in cs])))

    print("\n=== Multi-section questions only ===")
    multi = {q.id for q in questions if len(q.relevant) > 1}
    print(f"{len(multi)} questions with more than one relevant section: {sorted(multi)}")
    base = {qid: ranked[qid][:K] for qid in ranked}
    capped = {qid: cap_per_section(ranked[qid], K, 2) for qid in ranked}
    capped1 = {qid: cap_per_section(ranked[qid], K, 1) for qid in ranked}
    rel = {q.id: q.relevant for q in questions}
    for label, got in (("bez limitu", base), ("limit 2 na sekcję", capped),
                       ("limit 1 na sekcję", capped1)):
        full = sum(1 for qid in multi if rel[qid] <= {c.key for c in got[qid]})
        print(f"{label}: both sections inside top-5 for {full} of {len(multi)} questions")


if __name__ == "__main__":
    main()
