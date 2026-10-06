"""Chapter 6, table 3: how well does a lexical n-gram check separate a good citation from a bad one?

We do not need a model for this. The golden set already contains a reference answer for every
positive question, and the retriever gives us real chunks. For each question we measure the
n-gram coverage of the reference answer in (a) the chunk that really belongs to the relevant
section, (b) the other chunks in the top 5, (c) a chunk drawn at random from the whole corpus.
Those three distributions are exactly the three cases a citation verifier has to tell apart.

Run from the `code/` directory:  ../.venv/bin/python experiments/06_citations.py
"""
from __future__ import annotations

import random
import statistics

from ragbook.corpus import fixed_window_chunks, load_sections
from ragbook.embed import Embedder
from ragbook.evaluate import load_golden
from ragbook.answer import check_citations, ngram_coverage, split_sentences
from ragbook.store import DenseIndex

NS = (2, 3, 4)
RANDOM_SEED = 7


def mark(text: str, k: int) -> str:
    """Put a [k] marker at the end of every sentence, the way the prompt asks the model to."""
    return " ".join(f"{s.rstrip()} [{k}]" for s in split_sentences(text))


def describe(name: str, xs: list[float]) -> str:
    if not xs:
        return f"| {name} | 0 | – | – | – |"
    xs = sorted(xs)
    return (f"| {name} | {len(xs)} | {statistics.mean(xs):.3f} "
            f"| {statistics.median(xs):.3f} | {xs[int(0.9 * (len(xs) - 1))]:.3f} |")


def main() -> None:
    golden = load_golden()
    positives = [q for q in golden if q.relevant and q.answer.strip()]
    print(f"golden set: {len(golden)} pytań, {len(positives)} pozytywnych z odpowiedzią wzorcową\n")

    embedder = Embedder()
    chunks = fixed_window_chunks(load_sections(), embedder.tokenizer)
    index = DenseIndex(embedder, chunks)
    rng = random.Random(RANDOM_SEED)

    for n in NS:
        good, near_miss, random_chunk = [], [], []
        extractive_same, extractive_other = [], []
        for q in positives:
            got = index.search(q.question, 5)
            for c in got:
                cov = ngram_coverage(q.answer, c.text, n)
                (good if c.key in q.relevant else near_miss).append(cov)
            random_chunk.append(ngram_coverage(q.answer, rng.choice(chunks).text, n))
            # Upper bound: an extractive answer, i.e. one long sentence copied out of the chunk itself.
            hit = next((c for c in got if c.key in q.relevant), None)
            if hit:
                sentences = [s for s in split_sentences(hit.text) if len(s.split()) >= 8]
                if sentences:
                    quote = max(sentences, key=len)
                    extractive_same.append(ngram_coverage(quote, hit.text, n))
                    other = next((c for c in got if c.key not in q.relevant), None)
                    if other:
                        extractive_other.append(ngram_coverage(quote, other.text, n))

        print(f"=== pokrycie {n}-gramów w kandydacie na cytat ===")
        print("| twierdzenie vs fragment | przypadków | średnia | mediana | p90 |")
        print("|---|---|---|---|---|")
        print(describe("odpowiedź wzorcowa vs trafna sekcja", good))
        print(describe("odpowiedź wzorcowa vs inny z top-5", near_miss))
        print(describe("odpowiedź wzorcowa vs losowy chunk", random_chunk))
        print(describe("zdanie z fragmentu vs ten fragment", extractive_same))
        print(describe("zdanie z fragmentu vs inny z top-5", extractive_other))

        if n == 3:
            print("\n| próg pokrycia | przepuszcza trafne | przepuszcza nietrafne z top-5 |")
            print("|---|---|---|")
            for t in (0.05, 0.10, 0.20, 0.30, 0.40, 0.50):
                gp = sum(1 for x in good if x >= t) / len(good)
                np_ = sum(1 for x in near_miss if x >= t) / len(near_miss)
                print(f"| {t:.2f} | {gp:.2f} | {np_:.2f} |")
        print()

    print("=== check_citations on three hand-made answers ===")
    q = positives[0]
    got = index.search(q.question, 5)
    right = next((i for i, c in enumerate(got, start=1) if c.key in q.relevant), 1)
    wrong = next((i for i, c in enumerate(got, start=1) if c.key not in q.relevant), 2)
    quote = max((s for s in split_sentences(got[right - 1].text) if len(s.split()) >= 8),
                key=len, default=got[right - 1].text[:200])
    cases = {
        "cytat z fragmentu": f"{quote} [{right}]",
        "ten sam cytat, zły numer": f"{quote} [{wrong}]",
        "parafraza wzorcowa": mark(q.answer, right),
        "twierdzenie zmyślone": f"Domyślna wartość tego parametru to 4096 i zmienia się ją flagą --legacy-mode [{right}].",
    }
    print(f"pytanie: {q.question}")
    for name, text in cases.items():
        for chk in check_citations(text, got):
            print(f"  {name:24s} cited={chk.cited} cov_cited={chk.coverage_cited:.3f} "
                  f"cov_best={chk.coverage_best:.3f}@[{chk.best_chunk}] -> {chk.status}")


if __name__ == "__main__":
    main()
