"""Intent routing: decide *whether* and *how* to search before searching.

Three routes:
- `local`         - answerable from a few sections -> normal RAG (this includes questions whose
                    answer is not in the corpus: the refusal belongs to the generation step);
- `global`        - about the corpus as a whole ("summarise chapter 9", "how many chapters
                    mention cost") -> map-reduce over sections or a structured answer, not top-k;
- `out_of_domain` - smalltalk and everything outside the documentation -> do not search at all.

Two classifiers: `LLMRouter` (structured outputs, needs a key) and `EmbeddingRouter`
(a few labelled examples per class, centroid or kNN over embeddings, runs locally).
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
from pydantic import BaseModel, Field

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ROUTING_PATH = DATA_DIR / "routing.jsonl"
ROUTES = ("local", "global", "out_of_domain")

ACTIONS = {
    "local": "retrieval + generacja z kontekstem",
    "global": "map-reduce po sekcjach albo odpowiedź z metadanych korpusu",
    "out_of_domain": "odpowiedź bez wyszukiwania",
}


class Intent(BaseModel):
    """Structured output of the LLM router."""
    route: Literal["local", "global", "out_of_domain"] = Field(
        description="local: answerable from a few sections; global: about the whole corpus; "
                    "out_of_domain: smalltalk or a topic the documentation does not cover")
    reason: str = Field(description="one short sentence")


ROUTER_PROMPT = """Zaklasyfikuj pytanie użytkownika do jednej z trzech klas.

local - da się na nie odpowiedzieć z kilku fragmentów dokumentacji (pytanie o fakt, parametr,
  procedurę, porównanie dwóch rzeczy); także wtedy, gdy podejrzewasz, że dokumentacja tego
  akurat nie opisuje - odmowa jest zadaniem generacji, nie routingu.
global - dotyczy całego korpusu albo jego struktury: streszczenie rozdziału, "ile rozdziałów
  mówi o X", spis treści, przegląd całości. Wyszukiwanie top-k tu nie pomoże.
out_of_domain - rozmowa towarzyska, prośba niezwiązana z dokumentacją, temat z zupełnie innej
  dziedziny. Nie wyszukujemy wcale.

Korpusem jest dokumentacja techniczna o budowaniu aplikacji na modelach językowych:
LLM-y, prompty, kontekst, embeddingi, bazy wektorowe, RAG, agenci, MCP, bezpieczeństwo,
obserwowalność, multimodalność, narzędzia.

Pytanie: {question}"""


@dataclass
class RoutedQuestion:
    id: str
    question: str
    label: str
    split: str


def load_routing(path: Path = ROUTING_PATH) -> list[RoutedQuestion]:
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            out.append(RoutedQuestion(d["id"], d["question"], d["label"], d["split"]))
    return out


class LLMRouter:
    """One cheap call per question; returns the route and a one-sentence reason."""

    def __init__(self, llm):
        self.llm = llm

    def route(self, question: str) -> Intent:
        return self.llm.parse(ROUTER_PROMPT.format(question=question), Intent)


class EmbeddingRouter:
    """kNN / centroid over embeddings of a handful of labelled examples per class.

    No API call, one embedding per question (which the retriever computes anyway).
    `margin` is the distance between the best and the second-best class score; use it to abstain.
    """

    def __init__(self, embedder, examples: list[tuple[str, str]], mode: str = "centroid", k: int = 3):
        self.embedder = embedder
        self.mode = mode
        self.k = k
        self.labels = [label for _, label in examples]
        self.vectors = embedder.embed_queries([q for q, _ in examples])
        self.classes = sorted(set(self.labels))
        self.centroids = {}
        for cls in self.classes:
            vecs = self.vectors[[i for i, label in enumerate(self.labels) if label == cls]]
            centroid = vecs.mean(axis=0)
            self.centroids[cls] = centroid / np.linalg.norm(centroid)

    def scores(self, question: str) -> dict[str, float]:
        qv = self.embedder.embed_queries([question])[0]
        if self.mode == "centroid":
            return {cls: float(qv @ vec) for cls, vec in self.centroids.items()}
        sims = self.vectors @ qv
        top = np.argsort(-sims)[: self.k]
        votes = Counter(self.labels[i] for i in top)
        return {cls: votes.get(cls, 0) + 1e-3 * float(max([sims[i] for i in top
                                                           if self.labels[i] == cls], default=0.0))
                for cls in self.classes}

    def route(self, question: str) -> tuple[str, float]:
        """Returns (route, margin between the best and the second-best class)."""
        scores = self.scores(question)
        ranked = sorted(scores.items(), key=lambda kv: -kv[1])
        margin = ranked[0][1] - ranked[1][1] if len(ranked) > 1 else 1.0
        return ranked[0][0], float(margin)


def route(question: str, router) -> str:
    """Uniform entry point: works with both routers, returns just the route name."""
    result = router.route(question)
    if isinstance(result, tuple):
        return result[0]
    return result.route


def confusion(pairs: list[tuple[str, str]], classes: tuple[str, ...] = ROUTES) -> dict:
    """Confusion matrix as {true: {predicted: count}} plus accuracy, from (true, predicted) pairs."""
    matrix = {t: {p: 0 for p in classes} for t in classes}
    for true, pred in pairs:
        matrix[true][pred] += 1
    correct = sum(matrix[c][c] for c in classes)
    return {"matrix": matrix, "accuracy": correct / len(pairs) if pairs else 0.0, "n": len(pairs)}
