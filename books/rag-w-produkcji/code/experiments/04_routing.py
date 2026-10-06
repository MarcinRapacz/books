"""Intent routing measured locally: centroid and kNN over embeddings of 12 labelled examples.

Test set (30 questions): 12 from the golden set (10 positive + 2 negative, both labelled `local`,
because a question without an answer in the corpus is still a documentation question), 8 global
questions and 10 out-of-domain questions written for this chapter (`data/routing.jsonl`).
The 12 prototypes are disjoint from the test set.

Run from the `code/` directory:  ../.venv/bin/python experiments/04_routing.py
"""
from __future__ import annotations

import time

from ragbook.embed import Embedder
from ragbook.evaluate import load_golden
from ragbook.routing import ROUTES, EmbeddingRouter, confusion, load_routing


def build_test_set() -> list[tuple[str, str, str]]:
    """(id, question, true label) - golden questions count as `local`."""
    golden = load_golden()
    positives = [q for q in golden if q.relevant]
    negatives = [q for q in golden if not q.relevant]
    items = [(q.id, q.question, "local") for q in positives[::5]]
    items += [(q.id, q.question, "local") for q in negatives[:2]]
    items += [(r.id, r.question, r.label) for r in load_routing() if r.split == "test"]
    return items


def print_matrix(result: dict, title: str) -> None:
    print(f"\n{title}  (trafność {result['accuracy']:.2f}, n = {result['n']})".replace(".", ","))
    print("| Prawda \\ Predykcja | " + " | ".join(ROUTES) + " |")
    print("|---|" + "|".join("---" for _ in ROUTES) + "|")
    for true in ROUTES:
        print(f"| {true} | " + " | ".join(str(result["matrix"][true][p]) for p in ROUTES) + " |")


def main() -> None:
    embedder = Embedder()
    prototypes = [(r.question, r.label) for r in load_routing() if r.split == "prototype"]
    test = build_test_set()
    print(f"prototypy: {len(prototypes)} ({', '.join(f'{c}: {sum(1 for _, l in prototypes if l == c)}' for c in ROUTES)})")
    print(f"zbiór testowy: {len(test)} " +
          f"({', '.join(f'{c}: {sum(1 for _, _, l in test if l == c)}' for c in ROUTES)})")

    for mode in ("centroid", "knn"):
        router = EmbeddingRouter(embedder, prototypes, mode=mode, k=3)
        predictions = [(qid, true, *router.route(question)) for qid, question, true in test]
        result = confusion([(true, pred) for _, true, pred, _ in predictions])
        print_matrix(result, f"Klasyfikator lokalny, tryb {mode}")
        wrong = [(qid, true, pred, margin) for qid, true, pred, margin in predictions if true != pred]
        for qid, true, pred, margin in wrong:
            question = next(q for i, q, _ in test if i == qid)
            print(f"  pomyłka {qid}: {true} -> {pred} (margines {margin:.3f}) {question!r}")
        if mode == "knn":
            print("  (w trybie knn margines to różnica liczby głosów, więc prawie zawsze wynosi 1)")

    # Cost of the local router: one embedding of the question plus three dot products.
    t0 = time.perf_counter()
    embedder.model.encode([f"query: {q}" for _, q, _ in test], normalize_embeddings=True,
                          batch_size=32, show_progress_bar=False)
    encode_ms = 1000 * (time.perf_counter() - t0) / len(test)
    print(f"\nKoszt klasyfikatora lokalnego: {encode_ms:.0f} ms na pytanie (embedding na CPU, "
          f"bez cache) plus trzy iloczyny skalarne; ten sam wektor zużywa potem retrieval.")

    # Abstain: how much does accuracy improve if we only trust confident predictions?
    router = EmbeddingRouter(embedder, prototypes, mode="centroid")
    predictions = [(true, *router.route(question)) for _, question, true in test]
    for threshold in (0.0, 0.01, 0.02, 0.03):
        confident = [(t, p) for t, p, m in predictions if m >= threshold]
        acc = sum(1 for t, p in confident if t == p) / len(confident)
        print(f"margines >= {threshold:.2f}: {len(confident)}/{len(test)} pytań, trafność {acc:.2f}"
              .replace(".", ","))


if __name__ == "__main__":
    main()
