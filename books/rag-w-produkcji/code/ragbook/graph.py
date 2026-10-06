"""Chapter 7: a graph over the corpus, and retrieval that walks it.

Two graphs live here.

1. `build_section_graph` builds a graph with **no LLM at all**: nodes are sections of volume 1,
   edges come from explicit cross-references in the prose ("rozdzial 4"), from shared inline code
   identifiers (`` `max_tokens` ``) and from document adjacency. It is cheap, deterministic and
   measurable, so every number in the chapter's tables comes from it.
2. `Entity` / `Relation` / `extract_graph` are the GraphRAG-style extraction (arXiv 2404.16130):
   one structured-output call per section, entities and relations back. That one needs
   ANTHROPIC_API_KEY; `extraction_cost` prices it before you spend anything.

Community detection (`communities`) is local networkx and runs on either graph.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass

import networkx as nx
import numpy as np
from pydantic import BaseModel, Field

from .corpus import Chunk, Section

EXTRACT_MODEL = "claude-haiku-4-5"
SUMMARY_MODEL = "claude-haiku-4-5"

# "rozdzial 4", "rozdziale 12", "rozdzialu 3", "rozdzialy 9 i 10" - the shapes volume 1 actually uses.
CHAPTER_REF = re.compile(r"rozdzia[lłuey]\w*\s+(\d+)", re.IGNORECASE)
# Inline code spans; fenced blocks are removed first, so this only sees `foo` inside prose.
CODE_SPAN = re.compile(r"`([^`\n]{1,60})`")
FENCE = re.compile(r"```.*?```", re.DOTALL)
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_.\-/]{2,}$")

EDGE_TYPES = ("ref", "term", "adj")


def prose_only(text: str) -> str:
    """Drop fenced code blocks: a reference inside a code sample is not a cross-reference."""
    return FENCE.sub(" ", text)


def section_terms(section: Section) -> set[str]:
    """Identifier-shaped inline code spans of one section, lowercased.

    `max_tokens`, `claude-haiku-4-5`, `sentence-transformers` are kept; `k`, `5`, `pip install x`
    are not (too short, not an identifier, or containing a space).
    """
    out = set()
    for span in CODE_SPAN.findall(prose_only(section.text)):
        token = span.strip()
        if IDENTIFIER.match(token):
            out.add(token.lower())
    return out


def chapter_refs(section: Section, max_chapter: int = 14) -> Counter:
    """Chapters this section points at, with multiplicity. Self-references are dropped."""
    hits = Counter()
    for number in CHAPTER_REF.findall(prose_only(section.text)):
        n = int(number)
        if 1 <= n <= max_chapter and n != section.chapter:
            hits[n] += 1
    return hits


def build_section_graph(sections: list[Section], max_df: int = 20,
                        w_ref: float = 1.0, w_term: float = 1.0, w_adj: float = 1.0) -> nx.Graph:
    """Undirected weighted graph over sections. No model, no API key, ~0.1 s.

    Edge attributes: `ref`, `term`, `adj` (raw per-layer weights, 0 when the layer is absent) and
    `weight` (the normalised combination used by retrieval). Each layer is max-normalised before
    combining, because their raw scales have nothing to do with each other.

    `max_df` drops identifiers that appear in more than that many sections: `user` or `text` are
    in every chapter and would connect everything to everything.
    """
    graph = nx.Graph()
    for s in sections:
        graph.add_node(s.key, chapter=s.chapter, title=s.title, section=s.section,
                       tokens=len(s.text.split()))

    by_chapter: dict[int, list[tuple[int, str]]] = defaultdict(list)
    for s in sections:
        by_chapter[s.chapter].append(s.key)

    raw: dict[tuple, dict[str, float]] = defaultdict(lambda: dict.fromkeys(EDGE_TYPES, 0.0))

    # (a) explicit cross-references: a section pointing at chapter n touches every section of n,
    #     diluted by the size of that chapter, so a pointer to a 14-section chapter says less.
    for s in sections:
        for target, count in chapter_refs(s).items():
            targets = by_chapter.get(target, [])
            if not targets:
                continue
            share = count / len(targets)
            for key in targets:
                if key != s.key:
                    raw[frozenset((s.key, key))]["ref"] += share

    # (b) shared identifiers, weighted by inverse document frequency.
    terms = {s.key: section_terms(s) for s in sections}
    df = Counter(t for ts in terms.values() for t in ts)
    idf = {t: math.log(len(sections) / c) for t, c in df.items() if 2 <= c <= max_df}
    postings: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for key, ts in terms.items():
        for t in ts:
            if t in idf:
                postings[t].append(key)
    for t, keys in postings.items():
        for i, a in enumerate(keys):
            for b in keys[i + 1:]:
                raw[frozenset((a, b))]["term"] += idf[t]

    # (c) document adjacency: neighbouring sections of the same chapter.
    for keys in by_chapter.values():
        for a, b in zip(keys, keys[1:]):
            raw[frozenset((a, b))]["adj"] += 1.0

    scale = {t: max((v[t] for v in raw.values()), default=1.0) or 1.0 for t in EDGE_TYPES}
    weights = {"ref": w_ref, "term": w_term, "adj": w_adj}
    for pair, layers in raw.items():
        a, b = tuple(pair)
        combined = sum(weights[t] * layers[t] / scale[t] for t in EDGE_TYPES)
        graph.add_edge(a, b, weight=combined, **layers)
    return graph


def subgraph_of_type(graph: nx.Graph, edge_type: str) -> nx.Graph:
    """One layer of the graph on its own, with `weight` set to that layer's raw value."""
    out = nx.Graph()
    out.add_nodes_from(graph.nodes(data=True))
    for a, b, data in graph.edges(data=True):
        if data.get(edge_type, 0.0) > 0:
            out.add_edge(a, b, weight=data[edge_type], **{t: data.get(t, 0.0) for t in EDGE_TYPES})
    return out


def graph_stats(graph: nx.Graph) -> dict:
    """Node/edge counts, degree summary, components and the centrality rankings worth reading."""
    degrees = [d for _, d in graph.degree()]
    strength = dict(graph.degree(weight="weight"))
    pagerank = nx.pagerank(graph, weight="weight") if graph.number_of_edges() else {}
    betweenness = nx.betweenness_centrality(graph, weight=None) if graph.number_of_edges() else {}
    per_type = {t: sum(1 for _, _, d in graph.edges(data=True) if d.get(t, 0.0) > 0) for t in EDGE_TYPES}
    n = graph.number_of_nodes()
    return {
        "nodes": n,
        "edges": graph.number_of_edges(),
        "edges_by_type": per_type,
        "density": nx.density(graph),
        "degree_mean": sum(degrees) / n if n else 0.0,
        "degree_median": sorted(degrees)[n // 2] if n else 0,
        "degree_max": max(degrees, default=0),
        "isolated": sum(1 for d in degrees if d == 0),
        "components": nx.number_connected_components(graph),
        "top_strength": sorted(strength.items(), key=lambda kv: -kv[1])[:10],
        "top_pagerank": sorted(pagerank.items(), key=lambda kv: -kv[1])[:10],
        "top_betweenness": sorted(betweenness.items(), key=lambda kv: -kv[1])[:10],
    }


def communities(graph: nx.Graph, resolution: float = 1.0, seed: int = 7) -> list[set]:
    """Louvain partition, largest community first. Local, deterministic given `seed`."""
    from networkx.algorithms.community import louvain_communities
    parts = louvain_communities(graph, weight="weight", resolution=resolution, seed=seed)
    return sorted((set(p) for p in parts), key=len, reverse=True)


# --- retrieval: dense first, then one hop over the graph -----------------------------------

class GraphRetriever:
    """Dense retrieval, then one hop over the graph. Three ways of combining the two.

    Common part: run the dense search, take the `seeds` best distinct sections, and spread a boost
    from each of them to its `per_seed` heaviest neighbours,
    `boost(t) = sum over seeds s of cos(q, s) * w(s, t)`.

    - `mode="boost"`: `score(c) = cos(q, c) + beta * boost(section(c))`. Simple, and hostage to the
      scale of the similarity: e5 cosines live between 0.84 and 0.93, so beta has to be tiny.
    - `mode="rrf"`: reciprocal rank fusion of the dense ranking with the ranking by boost. Scale
      free, the same fusion chapter 3 uses for hybrid search.
    - `mode="reserve"`: the dense ranking, except that the positions listed in `reserve_positions`
      go to the best chunk of a boosted section that is not represented yet. This is the "add the
      neighbours and re-rank" recipe in its most literal form, and unlike a "last `r` slots" rule
      it produces one ranking that means the same thing at k = 5 and at k = 20.
    - `mode="dedup"`: no graph at all, just one chunk per section. The control that tells you
      whether a gain came from the graph or merely from not returning the same section twice.

    `mode="boost"` with `beta = 0` reproduces the dense baseline of chapter 1 exactly.
    """

    def __init__(self, embedder, chunks: list[Chunk], graph: nx.Graph, beta: float = 0.005,
                 seeds: int = 5, per_seed: int = 3, edge_type: str = "weight",
                 mode: str = "boost", rrf_k: int = 60, reserve_positions: tuple[int, ...] = (5,)):
        self.embedder = embedder
        self.chunks = chunks
        self.graph = graph
        self.beta = beta
        self.seeds = seeds
        self.per_seed = per_seed
        self.edge_type = edge_type
        self.mode = mode
        self.rrf_k = rrf_k
        self.reserve_positions = set(reserve_positions)
        self.matrix = embedder.embed_passages([c.text for c in chunks])
        self.keys = [c.key for c in chunks]
        self.neighbours = {
            node: sorted(((nb, data.get(edge_type, 0.0)) for nb, data in graph[node].items()),
                         key=lambda kv: -kv[1])[:per_seed]
            for node in graph.nodes
        }

    def seed_sections(self, cos: np.ndarray) -> dict[tuple[int, str], float]:
        """The `seeds` best distinct sections of the dense ranking, with their best cosine."""
        out: dict[tuple[int, str], float] = {}
        for i in np.argsort(-cos):
            key = self.keys[int(i)]
            if key not in out:
                out[key] = float(cos[int(i)])
            if len(out) >= self.seeds:
                break
        return out

    def boost(self, cos: np.ndarray) -> dict[tuple[int, str], float]:
        out: dict[tuple[int, str], float] = defaultdict(float)
        for key, score in self.seed_sections(cos).items():
            for neighbour, weight in self.neighbours.get(key, []):
                if weight > 0:
                    out[neighbour] += score * weight
        return out

    def _wrap(self, i: int, score: float, cos: np.ndarray, boost: dict) -> Chunk:
        c = self.chunks[i]
        return Chunk(c.id, c.chapter, c.section, c.text,
                     {**c.meta, "score": score, "cos": float(cos[i]),
                      "boost": float(boost.get(c.key, 0.0))})

    def search(self, query: str, k: int = 5) -> list[Chunk]:
        qv = self.embedder.embed_queries([query])[0]
        cos = self.matrix @ qv
        boost = self.boost(cos) if (self.beta or self.mode != "boost") else {}

        if self.mode == "boost":
            final = cos + self.beta * np.array([boost.get(key, 0.0) for key in self.keys],
                                               dtype=np.float32)
            return [self._wrap(int(i), float(final[int(i)]), cos, boost)
                    for i in np.argsort(-final)[:k]]

        dense_order = np.argsort(-cos)
        if self.mode == "rrf":
            fused = defaultdict(float)
            for rank, i in enumerate(dense_order, start=1):
                fused[int(i)] += 1.0 / (self.rrf_k + rank)
            boosted = [int(i) for i in dense_order if boost.get(self.keys[int(i)], 0.0) > 0]
            boosted.sort(key=lambda i: (-boost[self.keys[i]], -cos[i]))
            for rank, i in enumerate(boosted, start=1):
                fused[i] += 1.0 / (self.rrf_k + rank)
            best = sorted(fused.items(), key=lambda kv: -kv[1])[:k]
            return [self._wrap(i, score, cos, boost) for i, score in best]

        if self.mode in ("reserve", "dedup"):
            dense_queue = [int(i) for i in dense_order]
            graph_queue = [i for i in dense_queue if boost.get(self.keys[i], 0.0) > 0]
            graph_queue.sort(key=lambda i: (-boost[self.keys[i]], -cos[i]))
            out_idx: list[int] = []
            seen_sections: set = set()
            used: set[int] = set()
            dense_pos = graph_pos = 0
            for position in range(1, k + 1):
                pick = None
                if self.mode == "reserve" and position in self.reserve_positions:
                    while graph_pos < len(graph_queue):
                        i = graph_queue[graph_pos]
                        graph_pos += 1
                        if i not in used and self.keys[i] not in seen_sections:
                            pick = i
                            break
                if pick is None:
                    while dense_pos < len(dense_queue):
                        i = dense_queue[dense_pos]
                        dense_pos += 1
                        if i in used:
                            continue
                        if self.mode == "dedup" and self.keys[i] in seen_sections:
                            continue
                        pick = i
                        break
                if pick is None:
                    break
                out_idx.append(pick)
                used.add(pick)
                seen_sections.add(self.keys[pick])
            return [self._wrap(i, float(cos[i]), cos, boost) for i in out_idx]

        raise ValueError(f"unknown mode: {self.mode}")


def reachability(retriever: GraphRetriever, questions, k: int = 5) -> dict:
    """Could a one-hop walk even find what the dense search missed?

    For every relevant section absent from the dense top-k, check whether it is a neighbour of one
    of the retrieved sections, and at what position in that neighbour's weight-ordered list. This
    is the ceiling on what any graph expansion can do, before you tune a single coefficient.
    """
    total = hop1 = in_top = 0
    ranks = []
    for q in questions:
        if not q.relevant:
            continue
        hits = retriever.search(q.question, k)
        found = {c.key for c in hits}
        for key in q.relevant - found:
            total += 1
            best = None
            for hit in found:
                if retriever.graph.has_edge(hit, key):
                    ordered = sorted(retriever.graph[hit].items(),
                                     key=lambda kv: -kv[1].get(retriever.edge_type, 0.0))
                    position = [nb for nb, _ in ordered].index(key) + 1
                    best = position if best is None else min(best, position)
            if best is not None:
                hop1 += 1
                ranks.append(best)
                if best <= retriever.per_seed:
                    in_top += 1
    return {"missing": total, "one_hop": hop1, "within_per_seed": in_top,
            "median_rank": sorted(ranks)[len(ranks) // 2] if ranks else None,
            "mean_rank": sum(ranks) / len(ranks) if ranks else None}


# --- GraphRAG with an LLM (needs ANTHROPIC_API_KEY) ----------------------------------------

class Entity(BaseModel):
    name: str = Field(description="Canonical name of the entity, as written in the text")
    type: str = Field(description='One of: concept, model, library, parameter, metric, format, role')
    description: str = Field(description="One sentence about what this entity is, in Polish")


class Relation(BaseModel):
    source: str = Field(description="Name of the source entity, exactly as in entities")
    target: str = Field(description="Name of the target entity, exactly as in entities")
    description: str = Field(description="One sentence on how the two are related, in Polish")
    strength: int = Field(description="1-10, how strongly the fragment ties the two together")


class GraphChunk(BaseModel):
    entities: list[Entity]
    relations: list[Relation]


EXTRACT_SYSTEM = """You build a knowledge graph out of a Polish handbook on LLM engineering.

From the fragment you are given, list the entities it actually talks about and the relations the
fragment itself states. Rules:
1. Only what the fragment says. Do not add relations you know from elsewhere.
2. Entity names are the terms the text uses: "RAG", "multilingual-e5-small", "max_tokens",
   "recall@5". Keep identifiers verbatim, including case.
3. Every `source` and `target` must be the name of an entity you also returned.
4. Skip entities the fragment only mentions in passing with nothing said about them.
5. `strength` is 10 when the fragment is about that relation and 1 when it is an aside."""


def extract_graph(client, text: str, model: str = EXTRACT_MODEL) -> GraphChunk:
    """One structured-output call per fragment. Needs ANTHROPIC_API_KEY."""
    response = client.messages.parse(
        model=model,
        max_tokens=4096,
        system=[{"type": "text", "text": EXTRACT_SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": f"<fragment>\n{text}\n</fragment>"}],
        output_format=GraphChunk,
    )
    return response.parsed_output


def entity_graph(records: list[GraphChunk]) -> nx.Graph:
    """Merge per-fragment extractions into one graph. Duplicate edges accumulate strength."""
    graph = nx.Graph()
    for record in records:
        for e in record.entities:
            key = e.name.strip().lower()
            if graph.has_node(key):
                graph.nodes[key]["descriptions"].append(e.description)
            else:
                graph.add_node(key, name=e.name.strip(), type=e.type, descriptions=[e.description])
        for r in record.relations:
            a, b = r.source.strip().lower(), r.target.strip().lower()
            if a == b or not graph.has_node(a) or not graph.has_node(b):
                continue
            if graph.has_edge(a, b):
                graph[a][b]["weight"] += r.strength
                graph[a][b]["descriptions"].append(r.description)
            else:
                graph.add_edge(a, b, weight=float(r.strength), descriptions=[r.description])
    return graph


SUMMARY_SYSTEM = """You summarise one community of a knowledge graph built from a Polish handbook.

You get its entities with their descriptions and the relations between them. Write a summary in
Polish: one sentence naming what the community is about, then three to six sentences on what it
contains and how its parts connect. Use only the material given. This summary will be the only
thing a reader sees when answering a corpus-wide question, so name the entities explicitly."""


def community_report(client, graph: nx.Graph, nodes: set, model: str = SUMMARY_MODEL) -> str:
    """One summary per community: the pre-generated answer to global questions. Needs a key."""
    sub = graph.subgraph(nodes)
    lines = [f"- {sub.nodes[n].get('name', n)}: {'; '.join(sub.nodes[n].get('descriptions', [])[:3])}"
             for n in sub.nodes]
    edges = [f"- {sub.nodes[a].get('name', a)} -> {sub.nodes[b].get('name', b)}: "
             f"{'; '.join(d.get('descriptions', [])[:2])}" for a, b, d in sub.edges(data=True)]
    body = "<entities>\n" + "\n".join(lines) + "\n</entities>\n<relations>\n" + "\n".join(edges) + "\n</relations>"
    message = client.messages.create(
        model=model, max_tokens=1024,
        system=[{"type": "text", "text": SUMMARY_SYSTEM}],
        messages=[{"role": "user", "content": body}],
    )
    return next(b.text for b in message.content if b.type == "text")


# --- what the LLM pass would cost (local arithmetic) ---------------------------------------

@dataclass
class ExtractionCost:
    """Price of one GraphRAG indexing pass, from real token counts plus stated assumptions."""
    calls: int
    input_tokens: int
    output_tokens: int
    price_in: float          # USD per million input tokens
    price_out: float         # USD per million output tokens
    label: str = ""

    @property
    def usd(self) -> float:
        return self.input_tokens * self.price_in / 1e6 + self.output_tokens * self.price_out / 1e6


def extraction_cost(fragment_tokens: list[int], price_in: float, price_out: float,
                    system_tokens: int = 200, entities_per_1k: float = 8.0,
                    relations_per_1k: float = 6.0, tokens_per_entity: int = 35,
                    tokens_per_relation: int = 45, gleanings: int = 0,
                    label: str = "") -> ExtractionCost:
    """Cost of one extraction pass over fragments of the given token lengths.

    Input tokens are real (count them with a tokenizer). Output tokens are an estimate built from
    four assumptions you can change: how many entities and relations a thousand tokens of this
    corpus yields, and how long one of each is in JSON. `gleanings` repeats the call on the same
    fragment to catch what the first pass missed (GraphRAG calls this a gleaning round); each
    repeat pays the full input again.
    """
    passes = 1 + gleanings
    calls = len(fragment_tokens) * passes
    input_tokens = sum(t + system_tokens for t in fragment_tokens) * passes
    output_tokens = int(sum(
        (t / 1000) * (entities_per_1k * tokens_per_entity + relations_per_1k * tokens_per_relation)
        for t in fragment_tokens) * passes)
    return ExtractionCost(calls, input_tokens, output_tokens, price_in, price_out, label)
