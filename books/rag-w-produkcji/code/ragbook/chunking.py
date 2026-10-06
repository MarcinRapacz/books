"""Chunking strategies for chapter 2, plus the measurement helper every 02_*.py experiment uses.

Every chunker takes `list[Section]` and returns `list[Chunk]` that keeps `chapter` and `section`
untouched, because the golden set judges relevance at the section level (chapter 1). A chunker may
change how the text is cut, prefixed or truncated, never which section a piece belongs to.

Families implemented here:
- alignment:   shifted_window_chunks     (the baseline window, cut a few tokens later: the noise floor)
- structural:  section_chunks, block_chunks, merged_block_chunks  (Markdown blocks: prose, code, tables)
- recursive:   recursive_chunks                                   (headings -> paragraphs -> sentences -> tokens)
- semantic:    semantic_chunks                                    (cut where consecutive sentences drift apart)
- contextual:  with_context_headers                               (chapter/section title glued in front)
- small-to-big: parent_child_chunks + ParentRetriever
- contextual retrieval (Anthropic): CHUNK_TEMPLATE / contextualize (needs an API key, not run here)
- the project's choice: code_aware_window_chunks, exported as project_chunks + PROJECT_EMBEDDER

The fixed-window baseline lives in `ragbook.corpus.fixed_window_chunks` and is not repeated.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from .corpus import Chunk, Section

# --------------------------------------------------------------------------------------- utilities

_SENTENCE = re.compile(r"(?<=[.!?:;…])\s+")


def n_tokens(text: str, tokenizer) -> int:
    return len(tokenizer(text, add_special_tokens=False)["input_ids"])


def truncate(text: str, tokenizer, max_tokens: int) -> tuple[str, bool]:
    """Cut `text` to at most `max_tokens` model tokens. Returns (text, was_truncated)."""
    ids = tokenizer(text, add_special_tokens=False)["input_ids"]
    if len(ids) <= max_tokens:
        return text, False
    return tokenizer.decode(ids[:max_tokens]), True


def split_blocks(text: str) -> list[tuple[str, str]]:
    """Split a section into Markdown blocks as (kind, text), in document order.

    A fenced code block is one block whatever is inside it (blank lines included). Everything else is
    separated by blank lines, which keeps a Markdown table (consecutive `|` lines) and a bullet list
    in one piece as well. `kind` is one of: code, table, list, math, prose.
    """
    blocks: list[tuple[str, str]] = []
    buf: list[str] = []
    in_fence = False

    def flush() -> None:
        body = "\n".join(buf).strip()
        if body:
            blocks.append((classify(body), body))
        buf.clear()

    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            if in_fence:
                buf.append(line)
                in_fence = False
                flush()
                continue
            flush()
            in_fence = True
            buf.append(line)
            continue
        if in_fence:
            buf.append(line)
            continue
        if not line.strip():
            flush()
            continue
        buf.append(line)
    flush()
    return blocks


def classify(body: str) -> str:
    first = body.lstrip().splitlines()[0]
    if first.startswith("```"):
        return "code"
    if first.startswith("|"):
        return "table"
    if first.startswith("$$"):
        return "math"
    if first.startswith(">"):
        return "quote"
    if first.startswith("#"):
        return "heading"
    if re.match(r"^([-*+]|\d+\.)\s", first):
        return "list"
    return "prose"


def sentences(block: str) -> list[str]:
    """Sentence split for prose; code, tables, lists and display math stay in one piece."""
    if classify(block) != "prose":
        return [block]
    return [s for s in _SENTENCE.split(block) if s.strip()]


def _mk(section: Section, text: str, prefix: str, index: int, **meta) -> Chunk:
    return Chunk(f"{prefix}{index:05d}", section.chapter, section.section, text,
                 {"title": section.title, "path": section.path, **meta})


def shifted_window_chunks(sections: list[Section], tokenizer, window: int = 128, overlap: int = 32,
                          offset: int = 0) -> list[Chunk]:
    """The baseline fixed window, but the first cut starts `offset` tokens into the section.

    Nothing about this changes the strategy: same window, same overlap, same number of chunks give or
    take one per section. It exists to measure how much of a recall difference comes from where the
    cuts happen to land, which is the honest yardstick for every other number in this chapter.
    """
    out: list[Chunk] = []
    step = max(1, window - overlap)
    for s in sections:
        ids = tokenizer(s.text, add_special_tokens=False)["input_ids"]
        starts = list(range(0, max(1, len(ids)), step)) if offset == 0 else \
            [0] + list(range(offset, max(1, len(ids)), step))
        for start in starts:
            piece = ids[start:start + window]
            if not piece:
                break
            out.append(_mk(s, tokenizer.decode(piece), "o", len(out), kind="fixed", start_token=start))
            if start + window >= len(ids):
                break
    return out


# ------------------------------------------------------------------------------------- structural

def section_chunks(sections: list[Section], tokenizer, max_tokens: int = 512) -> list[Chunk]:
    """One chunk per section, truncated to what the embedding model can actually read."""
    out: list[Chunk] = []
    for s in sections:
        text, cut = truncate(s.text, tokenizer, max_tokens)
        out.append(_mk(s, text, "s", len(out), kind="section", truncated=cut))
    return out


def block_chunks(sections: list[Section], tokenizer, max_tokens: int = 512) -> list[Chunk]:
    """One chunk per Markdown block: a paragraph, a whole code block, a whole table."""
    out: list[Chunk] = []
    for s in sections:
        for kind, body in split_blocks(s.text):
            text, cut = truncate(body, tokenizer, max_tokens)
            out.append(_mk(s, text, "b", len(out), kind=kind, truncated=cut))
    return out


def merged_block_chunks(sections: list[Section], tokenizer, max_tokens: int = 256,
                        min_tokens: int = 0) -> list[Chunk]:
    """Blocks glued together greedily up to `max_tokens`; code blocks and tables are never split.

    `min_tokens` lets a block that is on its own shorter than the floor be merged with the next one
    even if the result crosses `max_tokens` slightly; 0 disables that.
    """
    out: list[Chunk] = []
    for s in sections:
        buf: list[str] = []
        used = 0
        for _kind, body in split_blocks(s.text):
            size = n_tokens(body, tokenizer)
            if buf and used + size > max_tokens and used >= min_tokens:
                out.append(_mk(s, "\n\n".join(buf), "m", len(out), kind="merged"))
                buf, used = [], 0
            if size > max_tokens and not buf:
                text, cut = truncate(body, tokenizer, max_tokens)
                out.append(_mk(s, text, "m", len(out), kind="merged", truncated=cut))
                continue
            buf.append(body)
            used += size
        if buf:
            out.append(_mk(s, "\n\n".join(buf), "m", len(out), kind="merged"))
    return out


# -------------------------------------------------------------------------------------- recursive

def _recursive_split(text: str, tokenizer, max_tokens: int, separators: list[str]) -> list[str]:
    """Split on the first separator that helps, recurse into pieces that are still too long."""
    if n_tokens(text, tokenizer) <= max_tokens:
        return [text]
    for i, sep in enumerate(separators):
        parts = [p for p in re.split(sep, text) if p.strip()] if sep else []
        if len(parts) > 1:
            out: list[str] = []
            for part in parts:
                out.extend(_recursive_split(part, tokenizer, max_tokens, separators[i + 1:]))
            return out
    ids = tokenizer(text, add_special_tokens=False)["input_ids"]
    return [tokenizer.decode(ids[j:j + max_tokens]) for j in range(0, len(ids), max_tokens)]


def recursive_chunks(sections: list[Section], tokenizer, max_tokens: int = 256,
                     separators: tuple[str, ...] = (r"\n(?=### )", r"\n\s*\n", r"(?<=[.!?])\s+", r"\s+"),
                     ) -> list[Chunk]:
    """Own implementation of the recursive splitter: headings, then blank lines, sentences, whitespace.

    The same idea as LangChain's `RecursiveCharacterTextSplitter`, counted in model tokens instead of
    characters: try the coarsest boundary the document offers, fall back to finer ones only when a
    piece is still too long, then glue neighbouring pieces back together up to the budget.
    """
    out: list[Chunk] = []
    for s in sections:
        pieces = _recursive_split(s.text, tokenizer, max_tokens, list(separators))
        buf: list[str] = []
        used = 0
        for piece in pieces:
            size = n_tokens(piece, tokenizer)
            if buf and used + size > max_tokens:
                out.append(_mk(s, "\n".join(buf), "r", len(out), kind="recursive"))
                buf, used = [], 0
            buf.append(piece.strip())
            used += size
        if buf:
            out.append(_mk(s, "\n".join(buf), "r", len(out), kind="recursive"))
    return out


# --------------------------------------------------------------------------------------- semantic

def semantic_chunks(sections: list[Section], embedder, max_tokens: int = 256,
                    percentile: float = 90.0, min_tokens: int = 40) -> list[Chunk]:
    """Cut where consecutive sentences stop talking about the same thing.

    Every sentence of the corpus is embedded once (one extra pass over the corpus, cached like any
    other). Inside a section we look at the cosine distance between neighbouring sentences and cut at
    the boundaries above the `percentile`-th distance of the whole corpus; `max_tokens` is still a hard
    cap, because a section can be perfectly coherent and far too long.
    """
    tokenizer = embedder.tokenizer
    per_section: list[list[str]] = []
    flat: list[str] = []
    for s in sections:
        sents = [t for block in split_blocks(s.text) for t in sentences(block[1])]
        per_section.append(sents)
        flat.extend(sents)
    vecs = embedder.embed_passages(flat)

    dists: list[float] = []
    pos = 0
    for sents in per_section:
        v = vecs[pos:pos + len(sents)]
        dists.extend(1.0 - float(v[i] @ v[i + 1]) for i in range(len(sents) - 1))
        pos += len(sents)
    threshold = float(np.percentile(dists, percentile)) if dists else 1.0

    out: list[Chunk] = []
    pos = 0
    for s, sents in zip(sections, per_section):
        v = vecs[pos:pos + len(sents)]
        pos += len(sents)
        buf: list[str] = []
        used = 0
        for i, sent in enumerate(sents):
            size = n_tokens(sent, tokenizer)
            if buf and (used + size > max_tokens or
                        (used >= min_tokens and 1.0 - float(v[i - 1] @ v[i]) > threshold)):
                out.append(_mk(s, " ".join(buf), "e", len(out), kind="semantic", threshold=threshold))
                buf, used = [], 0
            buf.append(sent)
            used += size
        if buf:
            out.append(_mk(s, " ".join(buf), "e", len(out), kind="semantic", threshold=threshold))
    return out


# ------------------------------------------------------------------------- contextual chunk headers

def section_leads(sections: list[Section], max_chars: int = 240) -> dict[tuple[int, str], str]:
    """First sentence of every section: the cheapest possible stand-in for an LLM-written context."""
    leads: dict[tuple[int, str], str] = {}
    for s in sections:
        first = next((b for kind, b in split_blocks(s.text) if kind == "prose"), "")
        lead = sentences(first)[0].strip() if first else ""
        leads[s.key] = lead[:max_chars]
    return leads


def with_context_headers(chunks: list[Chunk], mode: str = "title",
                         leads: dict[tuple[int, str], str] | None = None) -> list[Chunk]:
    """Glue context in front of the chunk text, before embedding. Sections and ids stay the same.

    mode="title": "<chapter title> / <section heading>" (contextual chunk headers)
    mode="lead":  the header plus the first sentence of the section (cheap contextual retrieval)
    """
    out: list[Chunk] = []
    for c in chunks:
        header = f"{c.meta.get('title', '')} / {c.section}".strip(" /")
        if mode == "lead" and leads:
            lead = leads.get(c.key, "")
            header = f"{header}\n{lead}".strip()
        out.append(Chunk(c.id, c.chapter, c.section, f"{header}\n{c.text}",
                         {**c.meta, "header": header, "body": c.text}))
    return out


# ------------------------------------------------------------------------------ parent-child (s2b)

def parent_child_chunks(sections: list[Section], tokenizer, child_tokens: int = 128,
                        parent: str = "block", parent_tokens: int = 512,
                        ) -> tuple[list[Chunk], dict[str, Chunk]]:
    """Small chunks for search, a bigger parent for the prompt.

    parent="block":   the Markdown block (paragraph, code block, table) the child was cut from
    parent="section": the whole section, truncated to `parent_tokens`
    Every child carries `meta["parent_id"]`; `ParentRetriever` swaps the text in after the search.
    """
    from .corpus import fixed_window_chunks

    parents: dict[str, Chunk] = {}
    children: list[Chunk] = []
    for s in sections:
        units = split_blocks(s.text) if parent == "block" else [("section", s.text)]
        for u, (kind, body) in enumerate(units):
            pid = f"p{len(parents):05d}"
            ptext, _ = truncate(body, tokenizer, parent_tokens)
            parents[pid] = _mk(s, ptext, "p", len(parents), kind=kind, unit=u)
            piece = Section(s.chapter, s.title, s.section, body, s.path)
            for c in fixed_window_chunks([piece], tokenizer, window=child_tokens, overlap=0):
                children.append(Chunk(f"c{len(children):05d}", c.chapter, c.section, c.text,
                                      {**c.meta, "title": s.title, "parent_id": pid}))
    return children, parents


@dataclass
class ParentRetriever:
    """Search over the children, hand the parents to the prompt. Sections (so metrics) do not change."""
    index: object
    parents: dict[str, Chunk]
    dedup: bool = False

    def search(self, query: str, k: int = 5) -> list[Chunk]:
        out: list[Chunk] = []
        seen: set[str] = set()
        for c in self.index.search(query, k):
            pid = c.meta.get("parent_id")
            parent = self.parents.get(pid)
            text = parent.text if parent else c.text
            if self.dedup and pid in seen:
                text = ""
            seen.add(pid)
            out.append(Chunk(c.id, c.chapter, c.section, text, {**c.meta, "child_text": c.text}))
        return out


# --------------------------------------------------------- contextual retrieval (Anthropic, needs API)

CONTEXT_MODEL = "claude-haiku-4-5"

DOCUMENT_TEMPLATE = """<document>
{document}
</document>"""

CHUNK_TEMPLATE = """Here is the chunk we want to situate within the whole document:
<chunk>
{chunk}
</chunk>

Please give a short succinct context to situate this chunk within the overall document for the purposes
of improving search retrieval of the chunk. Answer only with the succinct context and nothing else.
Answer in Polish."""


def contextualize(client, document: str, chunk_text: str, model: str = CONTEXT_MODEL) -> str:
    """One to two sentences placing `chunk_text` inside `document`, with the document cached.

    The document block is marked with `cache_control`, so the second and every further chunk of the
    same document reads it from the cache at 0.1x the input price instead of paying for it again.
    Claude Haiku 4.5 caches prompts from 4096 tokens up (platform.claude.com, prompt caching).
    """
    message = client.messages.create(
        model=model,
        max_tokens=150,
        messages=[{"role": "user", "content": [
            {"type": "text", "text": DOCUMENT_TEMPLATE.format(document=document),
             "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": CHUNK_TEMPLATE.format(chunk=chunk_text)},
        ]}],
    )
    return next(b.text for b in message.content if b.type == "text").strip()


# ----------------------------------------------------------------------------- measurement helper

def evaluate_chunks(name: str, chunks: list[Chunk], embedder, golden, k: int = 5, k_wide: int = 20,
                    wrap: Callable | None = None, count_tokens_on: str = "text") -> dict:
    """Index `chunks`, run the golden set and return one row for a Markdown table.

    `wrap(index)` may return a different retriever (used by ParentRetriever). `count_tokens_on`
    decides what counts towards the prompt budget: the indexed text, or the raw body without the
    context header ("body"), or the parent text ("text" after wrapping).
    """
    from .evaluate import evaluate, load_golden
    from .store import DenseIndex

    golden = golden if golden is not None else load_golden()
    index = DenseIndex(embedder, chunks, collection=f"c{abs(hash(name)) % 10 ** 8}")
    retriever = wrap(index) if wrap else index
    result = evaluate(retriever.search, golden, k=k, ks=(k, k_wide))

    tok = embedder.tokenizer
    budget = []
    for q in golden:
        if not q.relevant:
            continue
        hits = retriever.search(q.question, k)
        budget.append(sum(n_tokens(h.meta.get(count_tokens_on, h.text) or h.text, tok) for h in hits))
    lengths = [n_tokens(c.text, tok) for c in chunks]
    return {
        "name": name,
        "chunks": len(chunks),
        "median_tokens": int(np.median(lengths)),
        "prompt_tokens@5": int(round(sum(budget) / len(budget))),
        "recall@5": result[f"recall@{k}"],
        "recall@20": result[f"recall@{k_wide}"],
        "mrr@5": result[f"mrr@{k}"],
        "ndcg@5": result[f"ndcg@{k}"],
        "misses@5": result[f"misses@{k}"],
        "result": result,
    }


def row(r: dict, columns: tuple[str, ...] = ("chunks", "median_tokens", "prompt_tokens@5",
                                             "recall@5", "recall@20", "mrr@5", "ndcg@5", "misses@5")) -> str:
    cells = []
    for c in columns:
        v = r[c]
        cells.append(f"{v:.2f}".replace(".", ",") if isinstance(v, float) else f"{v}")
    return f"| {r['name']} | " + " | ".join(cells) + " |"


# ------------------------------------------------------------------------- the project configuration

PROJECT_EMBEDDER = "intfloat/multilingual-e5-small"
# Measured in `experiments/02_embedders.py`: the same chunks under multilingual-e5-base give
# recall@5 0.88 instead of 0.81 and 2 misses instead of 5, for 768 dims and 1.1 GB of weights.
# The book stays on e5-small so every chapter measures on the same model; switch this constant
# (and reindex) if you have the memory.
BETTER_EMBEDDER = "intfloat/multilingual-e5-base"


def code_aware_window_chunks(sections: list[Section], tokenizer, window: int = 128, overlap: int = 32,
                             max_block_tokens: int = 512, attach_lead: bool = True) -> list[Chunk]:
    """Fixed window over prose, whole fenced code blocks and whole Markdown tables.

    Prose blocks that stand next to each other are glued back together and cut by the fixed window, so
    the prose behaves exactly like the chapter 1 baseline. A code block or a table becomes one chunk
    with the paragraph that introduces it in front (`attach_lead`), because that paragraph carries the
    words a question is going to use. A block longer than `max_block_tokens` is cut on blank lines.
    """
    from .corpus import fixed_window_chunks

    out: list[Chunk] = []
    for s in sections:
        lead, buf = "", []

        def flush_prose(buf=buf, s=s) -> None:
            if not buf:
                return
            piece = Section(s.chapter, s.title, s.section, "\n\n".join(buf), s.path)
            for c in fixed_window_chunks([piece], tokenizer, window, overlap):
                out.append(Chunk(f"w{len(out):05d}", c.chapter, c.section, c.text,
                                 {**c.meta, "title": s.title, "kind": "prose"}))
            buf.clear()

        for kind, body in split_blocks(s.text):
            if kind not in ("code", "table"):
                buf.append(body)
                if kind == "prose":
                    lead = body
                continue
            flush_prose()
            text = f"{lead}\n{body}" if (attach_lead and lead) else body
            if n_tokens(text, tokenizer) <= max_block_tokens:
                out.append(_mk(s, text, "w", len(out), kind=kind))
                continue
            # Too long to keep whole: cut on blank lines first, then on tokens, so that nothing is
            # handed to the model above its input limit and silently truncated.
            parts, part = [], []
            for line_group in body.split("\n\n"):
                part.append(line_group)
                if n_tokens("\n\n".join(part), tokenizer) > max_block_tokens:
                    parts.append("\n\n".join(part))
                    part = []
            if part:
                parts.append("\n\n".join(part))
            for p in parts:
                ids = tokenizer(p, add_special_tokens=False)["input_ids"]
                for j in range(0, len(ids), max_block_tokens):
                    out.append(_mk(s, tokenizer.decode(ids[j:j + max_block_tokens]), "w", len(out),
                                   kind=kind, split=True))
        flush_prose()
    return out


def project_chunks(sections: list[Section], tokenizer) -> list[Chunk]:
    """The chunker chapter 2 settles on; chapters 3 and 4 start from here.

    The chapter 1 window (128 tokens, 32 of overlap) over the prose, plus the one change in this
    chapter that has a mechanism behind it rather than a lucky alignment: fenced code blocks and
    Markdown tables stay whole and carry the paragraph that introduces them.
    """
    return code_aware_window_chunks(sections, tokenizer, window=128, overlap=32)
