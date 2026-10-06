"""Does the cross-encoder score separate the 7 negative questions from the 49 positive ones?

Chapter 1 showed that the E5 cosine does not: every negative scores above the weakest positive.
The cross-encoder sees the pair (question, chunk) at once, so its score is a different quantity -
this script checks whether a cut-off exists and what it costs. Chapter 6 uses the answer.

Run from the `code/` directory:  ../.venv/bin/python experiments/03_negatives.py
"""
from __future__ import annotations

from ragbook.corpus import fixed_window_chunks, load_sections
from ragbook.embed import Embedder
from ragbook.evaluate import load_golden
from ragbook.hybrid import BM25Index, HybridIndex, make_tokenizer
from ragbook.rerank import MMARCO, CrossEncoderReranker
from ragbook.store import DenseIndex

CHUNKER = lambda sections, tokenizer: fixed_window_chunks(sections, tokenizer, window=128, overlap=32)
POOL, STEM, RRF_K = 20, 5, 60


def quantiles(values: list[float]) -> tuple[float, float, float]:
    s = sorted(values)
    return s[0], s[len(s) // 2], s[-1]


def main() -> None:
    embedder = Embedder()
    chunks = CHUNKER(load_sections(), embedder.tokenizer)
    golden = load_golden()
    dense = DenseIndex(embedder, chunks)
    lexical = BM25Index(chunks, make_tokenizer(STEM))
    hybrid = HybridIndex(dense, lexical, method="rrf", rrf_k=RRF_K, pool=50)
    candidates = {q.id: hybrid.search(q.question, POOL) for q in golden}
    del dense, lexical, hybrid

    reranker = CrossEncoderReranker(MMARCO)
    best: dict[str, float] = {}
    for q in golden:
        best[q.id] = reranker.rerank(q.question, candidates[q.id], top_k=1)[0].meta["score"]
    reranker.close()

    positives = [q for q in golden if q.relevant]
    negatives = [q for q in golden if not q.relevant]
    pos = [best[q.id] for q in positives]
    neg = [best[q.id] for q in negatives]

    print(f"=== Top-1 cross-encoder score ({MMARCO}, logit) ===")
    print("| Grupa | Pytań | min | mediana | max |")
    print("|---|---|---|---|---|")
    for label, values in (("pozytywne", pos), ("negatywne", neg)):
        lo, mid, hi = quantiles(values)
        print(f"| {label} | {len(values)} | {lo:+.2f} | {mid:+.2f} | {hi:+.2f} |".replace(".", ","))

    print("\n=== Negative questions, one by one ===")
    for q in sorted(negatives, key=lambda x: best[x.id]):
        print(f"  {best[q.id]:+7.2f}  {q.id}  {q.question}")

    print("\n=== Threshold sweep ===")
    print("| Próg | Odrzuconych negatywnych (z 7) | Odrzuconych pozytywnych (z 49) |")
    print("|---|---|---|")
    thresholds = sorted({round(v, 1) for v in pos + neg})
    for t in thresholds:
        dropped_neg = sum(1 for v in neg if v < t)
        dropped_pos = sum(1 for v in pos if v < t)
        print(f"| {t:+.1f} | {dropped_neg} | {dropped_pos} |".replace(".", ","))

    all_out = max(neg)
    cost = sum(1 for v in pos if v <= all_out)
    print(f"\nto reject all 7 negatives the threshold must exceed {all_out:+.2f}, "
          f"which also rejects {cost} of {len(pos)} positives")
    safe = min(pos)
    print(f"a threshold that keeps every positive must stay below {safe:+.2f}, "
          f"which rejects {sum(1 for v in neg if v < safe)} of {len(neg)} negatives")

    # Where is the useful operating point? Count questions whose relevant section was actually found.
    for t in (-8.0, -6.0, -4.0, -2.0, 0.0):
        tn = sum(1 for v in neg if v < t)
        fn = sum(1 for v in pos if v < t)
        print(f"threshold {t:+.1f}: catches {tn}/7 negatives, loses {fn}/49 positives")


if __name__ == "__main__":
    main()
