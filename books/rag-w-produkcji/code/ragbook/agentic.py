"""Chapter 7: retrieval that runs more than once.

Two halves, split by what they cost.

- `iterative_search` is the agentic loop: the model gets a `search` tool and decides for itself
  whether what it has is enough. It needs ANTHROPIC_API_KEY. The loop itself is the one from
  volume 1, chapter 9; only the tool and the stopping rule are new here.
- Everything below `--- corrective retrieval` is local and measurable: a cross-encoder grades
  every retrieved fragment, fragments below the threshold are dropped, and if too few survive the
  query is rewritten from the best surviving fragment (pseudo-relevance feedback) and run again.
  That is CRAG's shape (arXiv 2401.15884) with a small model in place of the LLM evaluator and
  the corpus in place of the web.
"""
from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import dataclass, field

from .answer import normalize
from .corpus import Chunk

AGENT_MODEL = "claude-opus-5"
GRADER_MODEL = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"

SEARCH_TOOL = {
    "name": "corpus_search",
    "description": (
        "Search the handbook 'AI Engineer' (14 chapters, Polish) by meaning and return the "
        "best matching fragments. Use it before answering any question about the handbook, and "
        "use it again with a different query whenever the fragments you already have do not "
        "contain the answer - for example when the question compares two things and you only "
        "found one of them. Write the query in Polish, in the words the handbook would use, not "
        "in the words of the user. Returns a JSON array of objects with chapter, section and "
        "text, ordered by similarity; at most 20 items. An empty array means nothing matched, "
        "which is an answer, not an error. The tool does not read whole chapters and does not "
        "search the internet."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string",
                      "description": "What to look for, in Polish, e.g. 'limit tokenow e5-small'"},
            "k": {"type": "integer", "description": "How many fragments to return, 1-20 (default 5)"},
        },
        "required": ["query"],
    },
}

AGENT_SYSTEM = """You answer questions about a Polish handbook on building LLM applications, using
only what `corpus_search` gives you.

How to work:
1. Search first. Never answer from your own knowledge about LLMs, APIs or libraries.
2. After each search, decide out loud whether the fragments contain the whole answer. If part of
   it is missing - a second technique to compare, a number you did not see, a section the
   fragments only point at - search again with a query aimed at exactly that missing part.
3. Stop as soon as you can answer, and do not search more than four times in total.
4. If after your searches the answer is still not in the fragments, say so in one sentence
   instead of guessing.
5. Answer in Polish, in at most four sentences, and name the chapter and section of every fact."""


@dataclass
class AgentRun:
    """One agentic retrieval: what the model asked for, what it got, what it cost."""
    answer: str = ""
    queries: list[str] = field(default_factory=list)
    chunks: list[Chunk] = field(default_factory=list)
    steps: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: str = ""

    def cost_usd(self, price_in: float = 5.0, price_out: float = 25.0) -> float:
        return self.input_tokens * price_in / 1e6 + self.output_tokens * price_out / 1e6


def iterative_search(client, question: str, retrieve, max_steps: int = 4,
                     model: str = AGENT_MODEL, k_default: int = 5) -> AgentRun:
    """Let the model run the retriever as many times as it needs, up to `max_steps`.

    `retrieve` is any `(query, k) -> list[Chunk]` - the dense index of chapter 1, the hybrid
    pipeline of chapter 3, whatever you measured best. The loop is the manual one from volume 1,
    chapter 9: call, look at `stop_reason`, execute every `tool_use` block, send the results back
    in one `user` message. The step budget lives in the code, never in the prompt.
    """
    run = AgentRun()
    messages: list[dict] = [{"role": "user", "content": question}]
    seen: set[str] = set()

    while run.steps <= max_steps:
        message = client.messages.create(
            model=model,
            max_tokens=2048,
            system=[{"type": "text", "text": AGENT_SYSTEM, "cache_control": {"type": "ephemeral"}}],
            tools=[SEARCH_TOOL],
            messages=messages,
        )
        run.input_tokens += message.usage.input_tokens
        run.output_tokens += message.usage.output_tokens
        run.stop_reason = message.stop_reason
        messages.append({"role": "assistant", "content": message.content})

        if message.stop_reason != "tool_use":
            run.answer = "".join(b.text for b in message.content if b.type == "text")
            return run

        results = []
        for block in message.content:
            if block.type != "tool_use":
                continue
            query = block.input.get("query", "")
            k = min(int(block.input.get("k", k_default)), 20)
            run.queries.append(query)
            hits = retrieve(query, k)
            for c in hits:
                if c.id not in seen:
                    seen.add(c.id)
                    run.chunks.append(c)
            payload = json.dumps([{"chapter": c.chapter, "section": c.section, "text": c.text}
                                  for c in hits], ensure_ascii=False)
            results.append({"type": "tool_result", "tool_use_id": block.id, "content": payload})
        messages.append({"role": "user", "content": results})
        run.steps += 1

    # Budget spent. Ask once more with tools switched off, so the run ends with an answer.
    message = client.messages.create(
        model=model, max_tokens=1024,
        system=[{"type": "text", "text": AGENT_SYSTEM}],
        messages=messages + [{"role": "user", "content":
                              "Step budget spent. Answer from the fragments you already have, "
                              "or say in one sentence that they are not enough."}],
    )
    run.input_tokens += message.usage.input_tokens
    run.output_tokens += message.usage.output_tokens
    run.answer = "".join(b.text for b in message.content if b.type == "text")
    run.stop_reason = "max_steps"
    return run


# --- corrective retrieval, the part that runs without a key --------------------------------

class CrossEncoderGrader:
    """The `retrieval evaluator` of CRAG, played by a small multilingual cross-encoder.

    Scores are raw logits, not probabilities: on this model useful fragments sit above roughly
    zero and noise well below. Measure the distribution on your own data before fixing a
    threshold - `experiments/07_corrective.py` does exactly that.
    """

    def __init__(self, model_name: str = GRADER_MODEL, max_length: int = 512):
        from sentence_transformers import CrossEncoder
        self.model = CrossEncoder(model_name, max_length=max_length)

    def score(self, query: str, chunks: list[Chunk], batch_size: int = 32) -> list[float]:
        if not chunks:
            return []
        pairs = [(query, c.text) for c in chunks]
        return [float(s) for s in self.model.predict(pairs, batch_size=batch_size,
                                                     show_progress_bar=False)]


class Vocabulary:
    """Document frequencies over the corpus, so pseudo-relevance feedback picks rare words."""

    STOP = {"the", "and", "for", "you", "that", "this", "with", "jest", "nie", "sie", "jak",
            "ale", "czy", "tym", "tego", "ktory", "ktora", "ktore", "lub", "czyli", "przy",
            "juz", "tylko", "wiec", "byc", "moze", "ma", "to", "co", "od", "do", "na", "za",
            "po", "we", "przez", "bez", "oraz", "jest", "sa", "jako", "tak", "gdy", "bo"}

    def __init__(self, texts: list[str]):
        self.n = len(texts)
        self.df = Counter()
        for text in texts:
            self.df.update(set(normalize(text)))

    def idf(self, term: str) -> float:
        return math.log(self.n / (1 + self.df.get(term, 0)))

    def keywords(self, text: str, top_n: int = 5, min_len: int = 4) -> list[str]:
        """Highest tf-idf words of one fragment: the terms worth adding to the next query."""
        tokens = [t for t in normalize(text)
                  if len(t) >= min_len and t not in self.STOP and not t.isdigit()]
        tf = Counter(tokens)
        scored = sorted(((count * self.idf(term), term) for term, count in tf.items()),
                        key=lambda kv: -kv[0])
        return [term for _, term in scored[:top_n]]

    def feedback_terms(self, texts: list[str], top_n: int = 5, min_len: int = 4,
                       min_docs: int = 2, min_df: int = 3) -> list[str]:
        """RM3-shaped expansion terms: frequent across the feedback fragments, rare in the corpus.

        Scoring one fragment alone picks its hapaxes, which in Polish prose are inflected forms of
        nothing in particular. Requiring a term in `min_docs` of the feedback fragments and in at
        least `min_df` fragments of the corpus leaves the words the topic is actually written in.
        """
        per_doc = [set(t for t in normalize(text)
                       if len(t) >= min_len and t not in self.STOP and not t.isdigit())
                   for text in texts]
        docs = Counter(t for tokens in per_doc for t in tokens)
        tf = Counter(t for text in texts for t in normalize(text))
        scored = []
        for term, in_docs in docs.items():
            if in_docs < min_docs or self.df.get(term, 0) < min_df:
                continue
            scored.append((in_docs * tf[term] * self.idf(term), term))
        scored.sort(key=lambda kv: -kv[0])
        return [term for _, term in scored[:top_n]]


def expand_query(question: str, chunks: list[Chunk], vocab: Vocabulary, top_n: int = 5) -> str:
    """Pseudo-relevance feedback: the question plus the vocabulary of the best fragments.

    This is the cheap stand-in for CRAG's web-search fallback. The corpus is all we have, so the
    only way to reach elsewhere in it is to ask with different words - and the words the graded
    fragments used are the best guess at the vocabulary the document actually uses.
    """
    asked = set(normalize(question))
    terms = vocab.feedback_terms([c.text for c in chunks], top_n=top_n + len(asked))
    extra = [t for t in terms if t not in asked][:top_n]
    return f"{question} {' '.join(extra)}".strip()


def correct(question: str, first: list[Chunk], scores: list[float], threshold: float,
            min_kept: int) -> tuple[list[Chunk], bool]:
    """CRAG's decision, in two lines: keep what clears the bar, and say whether to search again."""
    kept = [c for c, s in zip(first, scores) if s >= threshold]
    return kept, len(kept) < min_kept
