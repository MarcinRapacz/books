"""Query transformations: rewriting, multi-query + RRF, HyDE, step-back, decomposition, filters.

Every transformation that needs a model takes a *pluggable* LLM: any object with a
`parse(prompt, output_format)` method returning an instance of the given Pydantic model.
Two implementations ship here:

- `ClaudeLLM`  - real calls to the Messages API (`messages.parse` + `output_format`), needs a key;
- `ScriptedLLM` - replays variants written by hand into `data/query_variants.jsonl`, no key needed.

The scripted one is what `experiments/04_queries.py` measures: real retrieval on the real corpus,
human-written query variants. See the chapter for why that is an upper bound, not a forecast.
"""
from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field

from .corpus import Chunk

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
VARIANTS_PATH = DATA_DIR / "query_variants.jsonl"
MODEL = "claude-haiku-4-5"  # query transformations are short and frequent: the cheap model

Retriever = Callable[[str, int], list[Chunk]]


# --- structured outputs ------------------------------------------------------------------

class Rewrites(BaseModel):
    """N standalone search queries for the same information need."""
    queries: list[str] = Field(description="self-contained search queries, no pronouns")


class Hypothetical(BaseModel):
    """A short hypothetical answer, to be embedded instead of the question (HyDE)."""
    answer: str = Field(description="2-3 sentences written as if quoted from the documentation")


class StepBack(BaseModel):
    """One more general question that the original question is a special case of."""
    question: str


class Decomposition(BaseModel):
    """Independent sub-questions; each one is answerable from a single place in the corpus."""
    subquestions: list[str]


class ExtractedFilter(BaseModel):
    """Self-query: metadata constraints pulled out of a natural-language question."""
    chapter: int | None = Field(default=None, description="chapter number 1-14, null if unspecified")
    kind: str | None = Field(default=None, description="prose, code or table; null if unspecified")
    query: str = Field(description="the question with the constraint removed")


# --- LLM adapters ------------------------------------------------------------------------

class LLM(Protocol):
    def parse(self, prompt: str, output_format: type[BaseModel]) -> BaseModel: ...


class ClaudeLLM:
    """Structured outputs over the Messages API. Requires ANTHROPIC_API_KEY."""

    def __init__(self, model: str = MODEL, max_tokens: int = 512):
        from anthropic import Anthropic
        self.client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self.model = model
        self.max_tokens = max_tokens

    def parse(self, prompt: str, output_format: type[BaseModel]) -> BaseModel:
        response = self.client.messages.parse(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[{"role": "user", "content": prompt}],
            output_format=output_format,
        )
        return response.parsed_output


class ScriptedLLM:
    """Replays hand-written variants keyed by question text. No API key, deterministic."""

    def __init__(self, variants: dict[str, dict], question: str | None = None):
        self.variants = variants
        self.question = question

    def for_question(self, question: str) -> "ScriptedLLM":
        return ScriptedLLM(self.variants, question)

    def parse(self, prompt: str, output_format: type[BaseModel]) -> BaseModel:
        entry = self.variants[self.question]
        if output_format is Rewrites:
            return Rewrites(queries=list(entry["rewrite"]))
        if output_format is Hypothetical:
            return Hypothetical(answer=entry["hyde"])
        if output_format is Decomposition:
            return Decomposition(subquestions=list(entry.get("subquestions", [])))
        raise KeyError(f"no scripted answer for {output_format.__name__}")


def load_variants(path: Path = VARIANTS_PATH) -> dict[str, dict]:
    """Map question id -> {"rewrite": [...], "hyde": "...", "subquestions": [...]}."""
    out = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            out[d["id"]] = d
    return out


# --- prompts and transformations ---------------------------------------------------------

REWRITE_PROMPT = """Jesteś modułem przepisywania zapytań w wyszukiwarce po dokumentacji technicznej.
Zamień pytanie użytkownika na {n} samodzielne zapytania wyszukiwawcze: precyzyjne, z terminologią
techniczną i nazwami parametrów, bez zaimków i bez odwołań do rozmowy. Każde zapytanie ma trafiać
w tę samą potrzebę informacyjną innymi słowami. Nie odpowiadaj na pytanie.

Pytanie: {question}"""

HYDE_PROMPT = """Napisz krótki fragment dokumentacji technicznej (2-3 zdania), który odpowiadałby
na poniższe pytanie. Pisz w stylu dokumentacji, rzeczowo, z terminologią i nazwami parametrów.
Nie pisz, że czegoś nie wiesz, i nie zadawaj pytań - zmyślony, ale wiarygodny tekst jest w porządku,
bo posłuży wyłącznie jako zapytanie do wyszukiwarki.

Pytanie: {question}"""

STEP_BACK_PROMPT = """Podaj jedno ogólniejsze pytanie, którego zadane niżej pytanie jest
szczególnym przypadkiem. Ogólniejsze pytanie ma dotyczyć mechanizmu albo pojęcia, a nie
konkretnej wartości. Nie odpowiadaj na żadne z pytań.

Pytanie: {question}"""

DECOMPOSE_PROMPT = """Rozłóż pytanie na niezależne podpytania - tak, żeby na każde dało się
odpowiedzieć z jednego miejsca w dokumentacji. Jeśli pytanie porównuje dwie rzeczy, zrób z niego
dwa podpytania, po jednym na każdą stronę porównania. Jeśli pytanie jest proste, zwróć je bez zmian.
Nie odpowiadaj na pytania.

Pytanie: {question}"""

SELF_QUERY_PROMPT = """Z pytania wyodrębnij ograniczenia po metadanych i zwróć pytanie bez nich.
Korpus to dokumentacja podzielona na 14 rozdziałów: 1 Kim jest AI Engineer, 2 Jak działają LLM-y,
3 Prompt engineering, 4 Context engineering, 5 Modele i platformy, 6 Embeddingi, 7 Bazy wektorowe,
8 RAG, 9 Agenci, 10 MCP, 11 Bezpieczeństwo, 12 Obserwowalność i ewaluacje, 13 Multimodalność,
14 Narzędzia. Każdy fragment ma też typ treści: prose, code albo table.
Pole chapter wypełnij tylko wtedy, gdy pytanie wprost wskazuje rozdział albo jego temat.
Pole kind wypełnij tylko wtedy, gdy pytanie prosi o kod, przykład albo wartość z tabeli.

Pytanie: {question}"""


def rewrite_query(question: str, llm: LLM, n: int = 2) -> list[str]:
    """Potoczne pytanie -> n precyzyjnych zapytań wyszukiwawczych."""
    return list(llm.parse(REWRITE_PROMPT.format(n=n, question=question), Rewrites).queries)


def hyde_query(question: str, llm: LLM) -> str:
    """Hypothetical Document Embeddings: embed a made-up answer instead of the question."""
    return llm.parse(HYDE_PROMPT.format(question=question), Hypothetical).answer


def step_back_query(question: str, llm: LLM) -> str:
    return llm.parse(STEP_BACK_PROMPT.format(question=question), StepBack).question


def decompose_query(question: str, llm: LLM) -> list[str]:
    return list(llm.parse(DECOMPOSE_PROMPT.format(question=question), Decomposition).subquestions)


def self_query(question: str, llm: LLM) -> ExtractedFilter:
    return llm.parse(SELF_QUERY_PROMPT.format(question=question), ExtractedFilter)


def expand_query(question: str, llm: LLM, mode: str = "multi", n: int = 2) -> list[str]:
    """One entry point for every expansion. Returns the list of queries to search with.

    mode: "none" | "rewrite" | "multi" | "hyde" | "hyde+q" | "step-back" | "decompose"
    """
    if mode == "none":
        return [question]
    if mode == "rewrite":
        return rewrite_query(question, llm, n=1)[:1] or [question]
    if mode == "multi":
        return [question, *rewrite_query(question, llm, n=n)]
    if mode == "hyde":
        return [hyde_query(question, llm)]
    if mode == "hyde+q":
        return [question, hyde_query(question, llm)]
    if mode == "step-back":
        return [question, step_back_query(question, llm)]
    if mode == "decompose":
        subs = decompose_query(question, llm)
        return subs or [question]
    raise ValueError(f"unknown mode: {mode}")


# --- fusion ------------------------------------------------------------------------------

def rrf(runs: Iterable[list[Chunk]], k: int = 60, limit: int | None = None) -> list[Chunk]:
    """Reciprocal rank fusion: score(d) = sum over runs of 1 / (k + rank(d)).

    Rank-based, so it fuses result lists whose scores are not comparable (different queries,
    different retrievers). `k` damps the top of each list; 60 is the value from the original paper.
    """
    scores: dict[str, float] = {}
    best: dict[str, Chunk] = {}
    for run in runs:
        for rank, chunk in enumerate(run, start=1):
            scores[chunk.id] = scores.get(chunk.id, 0.0) + 1.0 / (k + rank)
            best.setdefault(chunk.id, chunk)
    order = sorted(scores, key=lambda cid: -scores[cid])
    out = [Chunk(best[cid].id, best[cid].chapter, best[cid].section, best[cid].text,
                 {**best[cid].meta, "score": round(scores[cid], 6)}) for cid in order]
    return out[:limit] if limit else out


def multi_retrieve(retrieve: Retriever, queries: list[str], k: int, per_query: int | None = None) -> list[Chunk]:
    """Run the retriever for every query variant and fuse the result lists with RRF."""
    per_query = per_query or k
    return rrf([retrieve(q, per_query) for q in queries], limit=k)


def make_retriever(retrieve: Retriever, llm: LLM, mode: str = "multi") -> Retriever:
    """Wrap a plain retriever into one that expands the query first. Signature stays (question, k)."""
    def wrapped(question: str, k: int) -> list[Chunk]:
        queries = expand_query(question, llm, mode=mode)
        return retrieve(queries[0], k) if len(queries) == 1 else multi_retrieve(retrieve, queries, k)
    return wrapped


# --- metadata ----------------------------------------------------------------------------

TABLE_DENSITY, CODE_DENSITY = 0.010, 0.050
CODE_CHARS = "(){}[]=_<>;`\""


def tag_kind(text: str) -> str:
    """Content type of a chunk: "table", "code" or "prose", from character densities.

    Line-based heuristics do not survive `tokenizer.decode`, which drops newlines - so the tag is
    computed from how often table pipes and code punctuation appear per character. The thresholds
    are calibrated on this corpus (chapter 1: 24,5% of characters are code, 2,8% table rows).
    Chapter 2 assigns this tag while chunking; here it is recomputed, so that this chapter's
    experiments do not depend on another chapter's module.
    """
    n = max(1, len(text))
    if text.count("|") / n >= TABLE_DENSITY:
        return "table"
    if sum(text.count(c) for c in CODE_CHARS) / n >= CODE_DENSITY:
        return "code"
    return "prose"


def tag_chunks(chunks: list[Chunk]) -> list[Chunk]:
    """Add `meta["kind"]` to every chunk, in place, and return the list."""
    for c in chunks:
        c.meta["kind"] = tag_kind(c.text)
    return chunks


def chapter_filter(chapters: int | Iterable[int], kind: str | None = None):
    """Qdrant filter: `must` on the chapter payload field, optionally also on the content kind."""
    from qdrant_client import models
    chapters = [chapters] if isinstance(chapters, int) else list(chapters)
    match = models.MatchValue(value=chapters[0]) if len(chapters) == 1 else models.MatchAny(any=chapters)
    must = [models.FieldCondition(key="chapter", match=match)]
    if kind:
        must.append(models.FieldCondition(key="kind", match=models.MatchValue(value=kind)))
    return models.Filter(must=must)
