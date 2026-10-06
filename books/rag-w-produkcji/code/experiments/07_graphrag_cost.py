"""Chapter 7, part 2: what a GraphRAG indexing pass over this corpus would cost.

Input token counts are real (o200k_base over the 131 sections). Output token counts rest on four
stated assumptions about how many entities and relations a thousand tokens of this corpus yields;
change them at the top and the whole table moves. Prices from the official price list
(September 2026): claude-haiku-4-5 $1 / $5 per million, claude-opus-5 $5 / $25 per million.

Local, no API key. Run from the `code/` directory:

    ../.venv/bin/python experiments/07_graphrag_cost.py
"""
from __future__ import annotations

import tiktoken

from ragbook.corpus import load_sections
from ragbook.graph import build_section_graph, communities, extraction_cost

PRICES = {"claude-haiku-4-5": (1.0, 5.0), "claude-opus-5": (5.0, 25.0)}

ENTITIES_PER_1K = 8.0        # entities a 1000-token fragment of this corpus yields
RELATIONS_PER_1K = 6.0       # relations likewise
TOKENS_PER_ENTITY = 35       # one Entity(name, type, description) as JSON
TOKENS_PER_RELATION = 45     # one Relation(source, target, description, strength) as JSON
SUMMARY_OUT = 400            # tokens of one community report


def main() -> None:
    sections = load_sections()
    enc = tiktoken.get_encoding("o200k_base")
    per_section = [len(enc.encode(s.text)) for s in sections]
    total = sum(per_section)
    print(f"{len(sections)} sekcji, {total} tokenów o200k_base "
          f"(mediana {sorted(per_section)[len(per_section) // 2]}, maks {max(per_section)})")

    print("\n=== Pierwszy przebieg: ekstrakcja encji i relacji ===")
    print("| Model | Przebiegi | Wywołań | Tokeny wejścia | Tokeny wyjścia | Koszt |")
    print("|---|---|---|---|---|---|")
    passes = {}
    for model, (price_in, price_out) in PRICES.items():
        for gleanings in (0, 1):
            cost = extraction_cost(per_section, price_in, price_out,
                                   entities_per_1k=ENTITIES_PER_1K,
                                   relations_per_1k=RELATIONS_PER_1K,
                                   tokens_per_entity=TOKENS_PER_ENTITY,
                                   tokens_per_relation=TOKENS_PER_RELATION,
                                   gleanings=gleanings, label=model)
            passes[(model, gleanings)] = cost
            print(f"| {model} | {1 + gleanings} | {cost.calls} | {cost.input_tokens} "
                  f"| {cost.output_tokens} | {cost.usd:.3f} USD |".replace(".", ","))

    entities = total / 1000 * ENTITIES_PER_1K
    relations = total / 1000 * RELATIONS_PER_1K
    print(f"\nprzy tych założeniach graf ma około {entities:.0f} encji i {relations:.0f} relacji")

    print("\n=== Drugi przebieg: podsumowania społeczności ===")
    # Size of a community report's input: every entity and relation description in it.
    desc_tokens = entities * TOKENS_PER_ENTITY + relations * TOKENS_PER_RELATION
    print("| Liczba społeczności | Model | Wywołań | Tokeny wejścia | Tokeny wyjścia | Koszt |")
    print("|---|---|---|---|---|---|")
    for n_comm in (20, 60):
        for model, (price_in, price_out) in PRICES.items():
            in_tokens = int(desc_tokens + n_comm * 200)
            out_tokens = n_comm * SUMMARY_OUT
            usd = in_tokens * price_in / 1e6 + out_tokens * price_out / 1e6
            print(f"| {n_comm} | {model} | {n_comm} | {in_tokens} | {out_tokens} "
                  f"| {usd:.3f} USD |".replace(".", ","))

    print("\n=== Razem, jeden przebieg indeksowania ===")
    print("| Wariant | Wywołań | Koszt |")
    print("|---|---|---|")
    for model in PRICES:
        for gleanings in (0, 1):
            cost = passes[(model, gleanings)]
            price_in, price_out = PRICES[model]
            summary = (desc_tokens + 60 * 200) * price_in / 1e6 + 60 * SUMMARY_OUT * price_out / 1e6
            print(f"| {model}, {1 + gleanings} przebieg(i) + 60 podsumowań | {cost.calls + 60} "
                  f"| {cost.usd + summary:.3f} USD |".replace(".", ","))

    print("\n=== Punkt odniesienia ===")
    embed_equivalent = 71.0
    print(f"pełna indeksacja gęsta tego korpusu: {embed_equivalent:.0f} s CPU, 0 USD "
          f"(model embeddingowy lokalny)")
    query = 0.01146
    cheapest = min(passes[(m, 0)].usd for m in PRICES)
    print(f"jedno zapytanie RAG (claude-opus-5, k=5, rozdział 8): {query} USD -> "
          f"ekstrakcja najtańszym wariantem to {cheapest / query:.0f} zapytań")

    print("\n=== Społeczności grafu sekcji (lokalnie, bez LLM-a) ===")
    graph = build_section_graph(sections)
    for resolution in (0.5, 1.0, 1.5, 2.0):
        parts = communities(graph, resolution=resolution)
        sizes = [len(p) for p in parts]
        print(f"resolution {resolution}: {len(parts)} społeczności, rozmiary {sizes}")


if __name__ == "__main__":
    main()
