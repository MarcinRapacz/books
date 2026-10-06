"""Generation stage of chapter 6: context prompt, structured answer with citations, citation
verification, refusal gate.

This is the production-shaped successor of `ragbook.generate` (the one-call baseline from chapter 1):
same pipeline position, but the answer comes back as a validated object instead of a string.
Nothing here talks to the network unless you call `generate_answer` / `answer_with_citations` /
`stream_with_citations` / `count_prompt_tokens`, which need ANTHROPIC_API_KEY. Everything else
(prompt building, citation checking, the retrieval confidence gate) is local and runs without a key.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from pydantic import BaseModel, Field

from .corpus import Chunk

GEN_MODEL = "claude-opus-5"
JUDGE_MODEL = "claude-haiku-4-5"

SYSTEM = """You answer questions about a Polish handbook on building LLM applications.

Rules:
1. Use only the numbered fragments in <context>. Your own knowledge about LLMs, APIs and
   libraries is not evidence and must not appear in the answer.
2. Every sentence that states a fact must end with the numbers of the fragments it comes from,
   in square brackets: [2] or [2][5].
3. If the fragments do not contain the answer, set answerable to false, leave citations empty
   and write one sentence saying what is missing. Do not guess, do not approximate.
4. Answer in Polish. Be terse: three sentences are usually enough."""


def format_context(chunks: list[Chunk], with_meta: bool = True) -> str:
    """Render retrieved chunks as numbered fragments. Numbering is 1-based and is the citation key."""
    parts = []
    for i, c in enumerate(chunks, start=1):
        if with_meta:
            title = c.meta.get("title", "")
            section = c.section or "wstęp"
            head = f"[{i}] rozdział {c.chapter} „{title}” / sekcja „{section}”"
        else:
            head = f"[{i}]"
        parts.append(f"{head}\n{c.text.strip()}")
    return "\n\n".join(parts)


def build_prompt(question: str, chunks: list[Chunk], with_meta: bool = True) -> str:
    """Context first, question last - the order the long-context guidance asks for."""
    return (f"<context>\n{format_context(chunks, with_meta)}\n</context>\n\n"
            f"<question>{question}</question>")


class Answer(BaseModel):
    """Schema the model must fill. `citations` are 1-based fragment numbers from the prompt."""
    answerable: bool = Field(description="True only if the fragments contain the answer")
    text: str = Field(description="The answer in Polish, or one sentence saying what is missing")
    citations: list[int] = Field(description="1-based numbers of the fragments used; empty if not answerable")


def generate_answer(client, question: str, chunks: list[Chunk], model: str = GEN_MODEL) -> Answer:
    """Structured generation: one API call, a validated Answer back. Needs ANTHROPIC_API_KEY."""
    response = client.messages.parse(
        model=model,
        max_tokens=1024,
        system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": build_prompt(question, chunks)}],
        output_format=Answer,
    )
    return response.parsed_output


def document_blocks(chunks: list[Chunk], cache_last: bool = False) -> list[dict]:
    """One `document` content block per chunk, citations on. Citation indices then point at our chunks.

    `context` carries chunk metadata: it is shown to the model but is not citable text.
    """
    blocks = []
    for c in chunks:
        blocks.append({
            "type": "document",
            "source": {"type": "text", "media_type": "text/plain", "data": c.text.strip()},
            "title": f"r{c.chapter}: {c.section}"[:200],
            "context": f'{{"chapter": {c.chapter}, "section": "{c.section}", "chunk_id": "{c.id}"}}',
            "citations": {"enabled": True},
        })
    if cache_last and blocks:
        blocks[-1]["cache_control"] = {"type": "ephemeral"}
    return blocks


def answer_with_citations(client, question: str, chunks: list[Chunk], model: str = GEN_MODEL):
    """Citations API variant. Returns the raw Message: text blocks carry `.citations`.

    Cannot be combined with output_config/output_format - the API returns 400.
    """
    return client.messages.create(
        model=model,
        max_tokens=1024,
        system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": document_blocks(chunks)
                   + [{"type": "text", "text": question}]}],
    )


def flatten_citations(message) -> list[dict]:
    """Collapse a citations-enabled Message into (claim, cited_text, document_index) rows."""
    rows = []
    for block in message.content:
        if block.type != "text":
            continue
        for cit in (getattr(block, "citations", None) or []):
            rows.append({"claim": block.text.strip(), "cited_text": cit.cited_text,
                         "document_index": cit.document_index, "type": cit.type})
        if not getattr(block, "citations", None) and block.text.strip():
            rows.append({"claim": block.text.strip(), "cited_text": None,
                         "document_index": None, "type": None})
    return rows


def stream_with_citations(client, question: str, chunks: list[Chunk], model: str = GEN_MODEL):
    """Yield ("text", str) and ("citation", citation) pairs as they arrive.

    Citations arrive as a `citations_delta` inside `content_block_delta`; each delta carries one
    citation to append to the current text block. Render the text immediately and attach the
    marker when its citation shows up - it always follows the text it supports.
    """
    with client.messages.stream(
        model=model,
        max_tokens=1024,
        system=[{"type": "text", "text": SYSTEM}],
        messages=[{"role": "user", "content": document_blocks(chunks)
                   + [{"type": "text", "text": question}]}],
    ) as stream:
        for event in stream:
            if event.type != "content_block_delta":
                continue
            if event.delta.type == "text_delta":
                yield "text", event.delta.text
            elif event.delta.type == "citations_delta":
                yield "citation", event.delta.citation


def count_prompt_tokens(client, question: str, chunks: list[Chunk], model: str = GEN_MODEL) -> int:
    """Exact input-token count from the API. Local tokenizers only approximate Claude's."""
    return client.messages.count_tokens(
        model=model,
        system=[{"type": "text", "text": SYSTEM}],
        messages=[{"role": "user", "content": build_prompt(question, chunks)}],
    ).input_tokens


# --- local verification -------------------------------------------------------------------

_WORD = re.compile(r"\w+", re.UNICODE)
_CIT = re.compile(r"\[(\d+)\]")


def normalize(text: str) -> list[str]:
    """Lowercase, strip Polish diacritics, keep word characters. Cheap and language-agnostic enough."""
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return _WORD.findall(text)


def ngrams(tokens: list[str], n: int) -> set[tuple[str, ...]]:
    return {tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)}


def split_sentences(text: str) -> list[str]:
    """Split on sentence enders. A fragment made only of [k] markers belongs to the sentence before it,
    because models write both `... [1].` and `... . [1]`."""
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", text.strip()) if p.strip()]
    out: list[str] = []
    for p in parts:
        if out and not re.sub(r"\[\d+\]|\s|[.;,]", "", p):
            out[-1] = f"{out[-1]} {p}"
        else:
            out.append(p)
    return out


def ngram_coverage(claim: str, context: str, n: int = 3) -> float:
    """Fraction of the claim's word n-grams that also occur in the context. 0.0 if the claim is too short."""
    claim_grams = ngrams(normalize(claim), n)
    if not claim_grams:
        return 0.0
    return len(claim_grams & ngrams(normalize(context), n)) / len(claim_grams)


@dataclass
class CitationCheck:
    sentence: str
    cited: list[int]
    coverage_cited: float
    coverage_best: float
    best_chunk: int | None
    threshold: float = 0.15

    @property
    def status(self) -> str:
        if not self.cited:
            return "no-citation"
        if self.coverage_cited >= self.threshold:
            return "ok"
        if self.best_chunk is not None and self.coverage_best >= self.threshold:
            return "wrong-chunk"
        return "low-overlap"


def check_citations(answer_text: str, chunks: list[Chunk], citations: list[int] | None = None,
                    n: int = 3, threshold: float = 0.15) -> list[CitationCheck]:
    """Verify, sentence by sentence, that the cited fragment really contains the claim's wording.

    Citation numbers are read from inline [k] markers; `citations` (the schema field) is the
    fallback when the model put no markers in the text. This is a lexical test: it catches a
    pointer to the wrong fragment, not a faithful paraphrase. Judge that with an LLM (judge.py).
    """
    out = []
    for sentence in split_sentences(answer_text):
        marked = [int(m) for m in _CIT.findall(sentence)]
        cited = marked or list(citations or [])
        bare = _CIT.sub("", sentence)
        cited_ctx = "\n".join(chunks[i - 1].text for i in cited if 1 <= i <= len(chunks))
        cov_cited = ngram_coverage(bare, cited_ctx, n) if cited_ctx else 0.0
        per_chunk = [(ngram_coverage(bare, c.text, n), i) for i, c in enumerate(chunks, start=1)]
        cov_best, best = max(per_chunk, default=(0.0, None))
        out.append(CitationCheck(bare.strip(), cited, cov_cited, cov_best,
                                 best if cov_best > 0 else None, threshold))
    return out


def should_ask_model(chunks: list[Chunk], min_score: float) -> bool:
    """Retrieval confidence gate: below the threshold, refuse without paying for a generation."""
    if not chunks:
        return False
    return max(c.meta.get("score", 0.0) for c in chunks) >= min_score
