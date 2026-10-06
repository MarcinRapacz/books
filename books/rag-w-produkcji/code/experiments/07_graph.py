"""Chapter 7, part 1: the section graph without an LLM, its statistics, its communities,
and what one hop over it does to retrieval.

Everything here is local: no API key, one model in memory (multilingual-e5-small), embeddings
served from `.cache/`. Run from the `code/` directory:

    ../.venv/bin/python experiments/07_graph.py
"""
from __future__ import annotations

from collections import Counter

from ragbook.corpus import fixed_window_chunks, load_sections
from ragbook.embed import Embedder
from ragbook.evaluate import by_type, evaluate, load_golden
from ragbook.graph import (GraphRetriever, build_section_graph, chapter_refs, communities,
                           graph_stats, reachability, section_terms, subgraph_of_type)

WINDOW, OVERLAP = 128, 32
K, K_WIDE = 5, 20
SHOWCASE = ("q044", "q050", "q053")


def short(key) -> str:
    chapter, section = key
    return f"r{chapter}/{section or 'wstep'}"


def run(name, retriever, golden):
    result = evaluate(retriever.search, golden, k=K, ks=(K, K_WIDE))
    comp = by_type(result, "recall@5").get("comparative", 0.0)
    comp20 = by_type(result, "recall@20").get("comparative", 0.0)
    return {"name": name, "recall@5": result["recall@5"], "recall@20": result["recall@20"],
            "mrr@5": result["mrr@5"], "ndcg@5": result["ndcg@5"], "misses@5": result["misses@5"],
            "comp@5": comp, "comp@20": comp20, "result": result}


def print_table(rows, header="Wariant"):
    print(f"| {header} | recall@5 | recall@20 | MRR@5 | nDCG@5 | comparative recall@5 | bez trafienia |")
    print("|---|---|---|---|---|---|---|")
    for r in rows:
        print(f"| {r['name']} | {r['recall@5']:.2f} | {r['recall@20']:.2f} | {r['mrr@5']:.2f} "
              f"| {r['ndcg@5']:.2f} | {r['comp@5']:.2f} | {r['misses@5']} |".replace(".", ","))


def main() -> None:
    sections = load_sections()
    golden = load_golden()
    graph = build_section_graph(sections)

    print("=== Graf sekcji (bez LLM-a) ===")
    stats = graph_stats(graph)
    print(f"nodes {stats['nodes']}  edges {stats['edges']}  density {stats['density']:.3f}  "
          f"components {stats['components']}  isolated {stats['isolated']}")
    print(f"degree: mean {stats['degree_mean']:.1f} median {stats['degree_median']} max {stats['degree_max']}")
    print("edges by layer:", stats["edges_by_type"])
    for layer in ("ref", "term", "adj"):
        sub = graph_stats(subgraph_of_type(graph, layer))
        print(f"  {layer:5s} edges {sub['edges']:5d}  components {sub['components']:3d}  "
              f"isolated {sub['isolated']:3d}  mean degree {sub['degree_mean']:.1f}")

    total_refs = sum(sum(chapter_refs(s).values()) for s in sections)
    terms = {s.key: section_terms(s) for s in sections}
    df = Counter(t for ts in terms.values() for t in ts)
    print(f"\ncross-chapter references in prose: {total_refs}")
    print(f"inline identifiers: {len(df)} distinct, {sum(df.values())} occurrences, "
          f"{sum(1 for v in df.values() if v >= 2)} in two or more sections")
    print("most shared identifiers:", [f"{t} ({c})" for t, c in df.most_common(8)])

    print("\n=== Najbardziej centralne sekcje ===")
    print("| Sekcja | Stopień ważony | PageRank | Betweenness |")
    print("|---|---|---|---|")
    strength = dict(stats["top_strength"])
    pagerank = dict(stats["top_pagerank"])
    between = dict(stats["top_betweenness"])
    for key, value in stats["top_pagerank"][:8]:
        print(f"| {short(key)} | {strength.get(key, 0.0):.1f} | {value:.4f} "
              f"| {between.get(key, 0.0):.3f} |".replace(".", ","))
    print("top by betweenness:", [short(k) for k, _ in stats["top_betweenness"][:5]])

    print("\n=== Społeczności (Louvain) ===")
    parts = communities(graph, resolution=1.0)
    from networkx.algorithms.community import modularity
    print(f"{len(parts)} communities, modularity {modularity(graph, parts, weight='weight'):.3f}")
    print("| # | Sekcji | Rozdziały (liczba sekcji) | Przykładowe sekcje |")
    print("|---|---|---|---|")
    for i, part in enumerate(parts, start=1):
        chapters = Counter(c for c, _ in part)
        top = sorted(part, key=lambda key: -graph.degree(key, weight="weight"))[:3]
        spread = " ".join(f"{c}({n})" for c, n in sorted(chapters.items(), key=lambda kv: -kv[1])[:5])
        print(f"| {i} | {len(part)} | {spread} | {', '.join(short(k) for k in top)} |")

    embedder = Embedder()
    chunks = fixed_window_chunks(sections, embedder.tokenizer, window=WINDOW, overlap=OVERLAP)
    print(f"\n{len(chunks)} chunks")

    baseline = GraphRetriever(embedder, chunks, graph, beta=0.0)

    print("\n=== Trzy pytania porównawcze na gęstym retrieverze ===")
    wanted = {q.id: q for q in golden}
    for qid in SHOWCASE:
        q = wanted[qid]
        hits = baseline.search(q.question, K)
        print(f"\n{qid}: {q.question}")
        print(f"  oczekiwane: {', '.join(short(k) for k in sorted(q.relevant))}")
        for rank, c in enumerate(hits, start=1):
            mark = "*" if c.key in q.relevant else " "
            print(f"  {mark}{rank}. {c.meta['cos']:.3f}  {short(c.key)}")
        missing = [k for k in sorted(q.relevant) if k not in {c.key for c in hits}]
        for key in missing:
            best = [(graph[key][nb].get("weight", 0.0), nb) for nb in graph[key]] if key in graph else []
            best.sort(reverse=True)
            print(f"  brakuje {short(key)}; sąsiedzi w grafie: "
                  f"{', '.join(f'{short(nb)} ({w:.2f})' for w, nb in best[:3])}")

    print("\n=== Sufit: czy brakująca sekcja w ogóle leży o jeden skok? ===")
    reach = reachability(baseline, golden, k=K)
    print(f"brakujących sekcji trafnych w top-{K}: {reach['missing']}; "
          f"sąsiadów 1-hop: {reach['one_hop']} ({100 * reach['one_hop'] / reach['missing']:.0f}%); "
          f"wśród {baseline.per_seed} najcięższych sąsiadów: {reach['within_per_seed']}")
    print(f"pozycja brakującej sekcji na liście sąsiadów: mediana {reach['median_rank']}, "
          f"średnia {reach['mean_rank']:.1f}")

    print("\n=== Rozszerzenie po grafie: dodatek do kosinusa ===")
    rows = [run("gęsty baseline (beta=0)", baseline, golden)]
    for beta in (0.001, 0.002, 0.005, 0.01, 0.02, 0.05):
        rows.append(run(f"boost, beta={beta}".replace(".", ","),
                        GraphRetriever(embedder, chunks, graph, beta=beta), golden))
    print_table(rows)

    print("\n=== Rozszerzenie po grafie: fuzja rang (RRF) i rezerwacja slotów ===")
    fusion = [rows[0]]
    for rrf_k in (10, 60):
        fusion.append(run(f"RRF, k={rrf_k}",
                          GraphRetriever(embedder, chunks, graph, mode="rrf", rrf_k=rrf_k), golden))
    fusion.append(run("dedup po sekcjach (kontrola, bez grafu)",
                      GraphRetriever(embedder, chunks, graph, mode="dedup"), golden))
    for positions in ((5,), (4, 5), (3, 5)):
        fusion.append(run(f"rezerwacja pozycji {positions}",
                          GraphRetriever(embedder, chunks, graph, mode="reserve",
                                         reserve_positions=positions), golden))
    print_table(fusion)

    print("\n=== Rozszerzenie po jednej warstwie grafu (rezerwacja 1 slotu) ===")
    layer_rows = [rows[0]]
    for layer in ("ref", "term", "adj"):
        sub = build_section_graph(sections, w_ref=float(layer == "ref"),
                                  w_term=float(layer == "term"), w_adj=float(layer == "adj"))
        layer_rows.append(run(f"tylko {layer}",
                              GraphRetriever(embedder, chunks, sub, mode="reserve"), golden))
    print_table(layer_rows)

    print("\n=== Ile sąsiadów na zalążek (rezerwacja 1 slotu) ===")
    wide = [rows[0]]
    for per_seed in (1, 3, 5, 10):
        wide.append(run(f"per_seed={per_seed}",
                        GraphRetriever(embedder, chunks, graph, mode="reserve",
                                       per_seed=per_seed), golden))
    print_table(wide)

    print("\n=== Co się zmieniło przy rezerwacji jednego slotu (pytanie po pytaniu) ===")
    base_per = {row["id"]: row for row in rows[0]["result"]["per_question"]}
    best = run("rezerwacja 1", GraphRetriever(embedder, chunks, graph, mode="reserve"), golden)
    better, worse = [], []
    for row in best["result"]["per_question"]:
        delta = row["recall@5"] - base_per[row["id"]]["recall@5"]
        if delta > 0:
            better.append((row["id"], row["type"], round(delta, 2)))
        elif delta < 0:
            worse.append((row["id"], row["type"], round(delta, 2)))
    print(f"lepiej ({len(better)}): {better}")
    print(f"gorzej ({len(worse)}): {worse}")

    del embedder


if __name__ == "__main__":
    main()
