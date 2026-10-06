"""BM25 alone: how much the Polish analyzer matters, and where lexical beats dense.

Chapter 2 picks the project's chunker; this chapter measures hybrid search and reranking on the
baseline chunks from chapter 1, so the two effects stay separable. Swap CHUNKER below to re-measure
everything on another chunking strategy.

Run from the `code/` directory:  ../.venv/bin/python experiments/03_bm25.py
"""
from __future__ import annotations

from collections import Counter

from ragbook.corpus import fixed_window_chunks, load_sections
from ragbook.embed import Embedder
from ragbook.evaluate import by_type, evaluate, load_golden
from ragbook.hybrid import BM25Index, make_tokenizer, tokenize
from ragbook.store import DenseIndex

CHUNKER = lambda sections, tokenizer: fixed_window_chunks(sections, tokenizer, window=128, overlap=32)
K, K_WIDE = 5, 20


def row(name: str, result: dict) -> str:
    return (f"| {name} | {result['recall@5']:.2f} | {result['recall@20']:.2f} | {result['mrr@5']:.2f} "
            f"| {result['ndcg@5']:.2f} | {result['misses@5']} |").replace(".", ",")


def main() -> None:
    embedder = Embedder()
    chunks = CHUNKER(load_sections(), embedder.tokenizer)
    golden = load_golden()
    print(f"{len(chunks)} chunks")

    example = "clear_tool_uses_20250919, metadata.user_id i query_points w Qdrancie"
    print(f"tokenize({example!r})\n  -> {tokenize(example)}")
    print(f"  stem_to=5 -> {make_tokenizer(5)(example)}")

    vocab_raw = Counter(t for c in chunks for t in tokenize(c.text))
    vocab_5 = Counter(t for c in chunks for t in make_tokenizer(5)(c.text))
    vocab_6 = Counter(t for c in chunks for t in make_tokenizer(6)(c.text))
    print(f"\nvocabulary: raw {len(vocab_raw)}  stem5 {len(vocab_5)}  stem6 {len(vocab_6)}")
    print(f"tokens in corpus: {sum(vocab_raw.values())}")

    print("\n=== BM25 alone, by analyzer ===")
    print("| Wariant | recall@5 | recall@20 | MRR@5 | nDCG@5 | Bez trafienia |")
    print("|---|---|---|---|---|---|")
    results = {}
    for name, stem_to in (("BM25, bez stemowania", None), ("BM25, obcięcie do 6 znaków", 6),
                          ("BM25, obcięcie do 5 znaków", 5), ("BM25, obcięcie do 4 znaków", 4)):
        index = BM25Index(chunks, make_tokenizer(stem_to))
        results[stem_to] = evaluate(index.search, golden, k=K, ks=(K, K_WIDE))
        print(row(name, results[stem_to]))

    dense = DenseIndex(embedder, chunks)
    dense_res = evaluate(dense.search, golden, k=K, ks=(K, K_WIDE))
    print(row("gęsty e5-small (baseline rozdz. 1)", dense_res))

    best = results[5]
    print("\n=== By question type (BM25 stem5 vs dense) ===")
    print("| Typ | BM25 recall@5 | gęsty recall@5 |")
    print("|---|---|---|")
    b5, d5 = by_type(best, "recall@5"), by_type(dense_res, "recall@5")
    for t in ("factual", "procedural", "comparative"):
        print(f"| {t} | {b5[t]:.2f} | {d5[t]:.2f} |".replace(".", ","))

    print("\n=== Where BM25 wins and loses against dense (recall@5) ===")
    bm = {r["id"]: r for r in best["per_question"]}
    dn = {r["id"]: r for r in dense_res["per_question"]}
    texts = {q.id: q.question for q in golden}
    wins = [i for i in bm if bm[i]["recall@5"] > dn[i]["recall@5"]]
    losses = [i for i in bm if bm[i]["recall@5"] < dn[i]["recall@5"]]
    print(f"BM25 better on {len(wins)}: {wins}")
    for i in wins:
        print(f"  + {i} [{bm[i]['type']}] {texts[i]}")
    print(f"BM25 worse on {len(losses)}: {losses}")
    for i in losses:
        print(f"  - {i} [{bm[i]['type']}] {texts[i]}")
    both = [i for i in bm if bm[i]["recall@5"] == 0 and dn[i]["recall@5"] == 0]
    print(f"missed by both ({len(both)}): {both}")

    print("\n=== Negative questions: top-1 BM25 score ===")
    index5 = BM25Index(chunks, make_tokenizer(5))
    negatives = [q for q in golden if not q.relevant]
    positives = [q for q in golden if q.relevant]
    neg = [index5.search(q.question, 1)[0].meta["score"] for q in negatives]
    pos = [index5.search(q.question, 1)[0].meta["score"] for q in positives]
    print(f"negatives min {min(neg):.2f} max {max(neg):.2f} mean {sum(neg) / len(neg):.2f}")
    print(f"positives min {min(pos):.2f} max {max(pos):.2f} mean {sum(pos) / len(pos):.2f}")


if __name__ == "__main__":
    main()
