"""Fusing the dense and the lexical ranking: RRF (and its k), weighted sums, and Qdrant's server-side RRF.

Run from the `code/` directory:  ../.venv/bin/python experiments/03_fusion.py
"""
from __future__ import annotations

from ragbook.corpus import fixed_window_chunks, load_sections
from ragbook.embed import Embedder
from ragbook.evaluate import by_type, evaluate, load_golden
from ragbook.hybrid import (BM25Index, HybridIndex, QdrantHybridIndex, make_tokenizer, rrf_fuse)
from ragbook.store import DenseIndex

CHUNKER = lambda sections, tokenizer: fixed_window_chunks(sections, tokenizer, window=128, overlap=32)
K, K_WIDE, POOL, STEM = 5, 20, 50, 5


def row(name: str, r: dict) -> str:
    return (f"| {name} | {r['recall@5']:.2f} | {r['recall@20']:.2f} | {r['mrr@5']:.2f} "
            f"| {r['ndcg@5']:.2f} | {r['misses@5']} |").replace(".", ",")


def main() -> None:
    embedder = Embedder()
    chunks = CHUNKER(load_sections(), embedder.tokenizer)
    golden = load_golden()
    dense = DenseIndex(embedder, chunks)
    lexical = BM25Index(chunks, make_tokenizer(STEM))

    print("=== RRF: sensitivity to k ===")
    print("| Fuzja | recall@5 | recall@20 | MRR@5 | nDCG@5 | Bez trafienia |")
    print("|---|---|---|---|---|---|")
    for rrf_k in (1, 10, 20, 60, 100, 200):
        h = HybridIndex(dense, lexical, method="rrf", rrf_k=rrf_k, pool=POOL)
        print(row(f"RRF, k={rrf_k}", evaluate(h.search, golden, k=K, ks=(K, K_WIDE))))

    print("\n=== Weighted sum of min-max normalised scores (dense weight w) ===")
    print("| Fuzja | recall@5 | recall@20 | MRR@5 | nDCG@5 | Bez trafienia |")
    print("|---|---|---|---|---|---|")
    for w in (0.2, 0.3, 0.5, 0.7, 0.8):
        h = HybridIndex(dense, lexical, method="weighted", weights=(w, 1 - w), pool=POOL)
        print(row(f"suma ważona, w_gęste={w:.1f}".replace(".", ","),
                  evaluate(h.search, golden, k=K, ks=(K, K_WIDE))))

    print("\n=== Weighted RRF (dense weight w, k=60) ===")
    print("| Fuzja | recall@5 | recall@20 | MRR@5 | nDCG@5 | Bez trafienia |")
    print("|---|---|---|---|---|---|")
    for w in (0.3, 0.5, 0.7):
        h = HybridIndex(dense, lexical, method="rrf", rrf_k=60, weights=(w, 1 - w), pool=POOL)
        print(row(f"RRF ważone, w_gęste={w:.1f}".replace(".", ","),
                  evaluate(h.search, golden, k=K, ks=(K, K_WIDE))))

    print("\n=== Pool size feeding the fusion (RRF k=60) ===")
    print("| Fuzja | recall@5 | recall@20 | MRR@5 | nDCG@5 | Bez trafienia |")
    print("|---|---|---|---|---|---|")
    for pool in (20, 50, 100, 200):
        h = HybridIndex(dense, lexical, method="rrf", rrf_k=60, pool=pool)
        print(row(f"RRF, pula {pool} na ramię", evaluate(h.search, golden, k=K, ks=(K, K_WIDE))))

    chosen = HybridIndex(dense, lexical, method="rrf", rrf_k=60, pool=POOL)
    hyb = evaluate(chosen.search, golden, k=K, ks=(K, K_WIDE))
    dn = evaluate(dense.search, golden, k=K, ks=(K, K_WIDE))
    print("\n=== By question type: dense vs hybrid (RRF k=60) ===")
    print("| Typ | gęsty recall@5 | hybryda recall@5 | gęsty MRR@5 | hybryda MRR@5 |")
    print("|---|---|---|---|---|")
    hr, dr = by_type(hyb, "recall@5"), by_type(dn, "recall@5")
    hm, dm = by_type(hyb, "mrr"), by_type(dn, "mrr")
    for t in ("factual", "procedural", "comparative"):
        print(f"| {t} | {dr[t]:.2f} | {hr[t]:.2f} | {dm[t]:.2f} | {hm[t]:.2f} |".replace(".", ","))

    h_ids = {r["id"]: r["recall@5"] for r in hyb["per_question"]}
    d_ids = {r["id"]: r["recall@5"] for r in dn["per_question"]}
    print("\nfixed by hybrid:", [i for i in h_ids if h_ids[i] > d_ids[i]])
    print("broken by hybrid:", [i for i in h_ids if h_ids[i] < d_ids[i]])

    # --- Qdrant with named dense + sparse vectors, fused server-side -------------------------------
    print("\n=== Qdrant: named vectors + prefetch + FusionQuery ===")
    qh = QdrantHybridIndex(embedder, chunks)
    server = evaluate(lambda q, k: qh.search(q, k, pool=POOL, rrf_k=60), golden, k=K, ks=(K, K_WIDE))
    print("| Wariant | recall@5 | recall@20 | MRR@5 | nDCG@5 | Bez trafienia |")
    print("|---|---|---|---|---|---|")
    print(row("Qdrant dense (named vector)",
              evaluate(lambda q, k: qh.search_arm(q, k, "dense"), golden, k=K, ks=(K, K_WIDE))))
    print(row("Qdrant sparse (Qdrant/bm25 + IDF)",
              evaluate(lambda q, k: qh.search_arm(q, k, "sparse"), golden, k=K, ks=(K, K_WIDE))))
    print(row("Qdrant RRF po stronie serwera", server))

    def own(q: str, k: int):
        arms = [qh.search_arm(q, POOL, "dense"), qh.search_arm(q, POOL, "sparse")]
        return rrf_fuse(arms, k=60)[:k]

    print(row("własny rrf_fuse na tych samych ramionach", evaluate(own, golden, k=K, ks=(K, K_WIDE))))

    question = "Jak nazywa się edycja kontekstu, która kasuje stare wyniki narzędzi?"
    a = qh.search(question, 5, pool=POOL, rrf_k=60)
    b = own(question, 5)
    print(f"\n{question}")
    print("| # | serwer (rozdz./sekcja) | score | własny RRF | score |")
    print("|---|---|---|---|---|")
    for i, (x, y) in enumerate(zip(a, b), start=1):
        print(f"| {i} | {x.chapter}/{x.section!r} | {x.meta['score']:.5f} "
              f"| {y.chapter}/{y.section!r} | {y.meta['score']:.5f} |")
    same = sum(1 for q in golden for x, y in zip(qh.search(q.question, 20, pool=POOL, rrf_k=60),
                                                 own(q.question, 20)) if x.id == y.id)
    print(f"identical ids in top-20 over all {len(golden)} questions: {same} of {20 * len(golden)}")


if __name__ == "__main__":
    main()
