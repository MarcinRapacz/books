"""Chunking that respects fenced code blocks.

A fixed token window cuts a snippet wherever the counter lands: half of an import block in one chunk,
a `client.query_points(...)` call split across two. The chunker here keeps every fenced block whole
and glues the paragraph that introduces it to the front, because that paragraph is what carries the
words a human would actually search for ("indeks payloadu", "wyszukiwanie w Qdrancie").
"""
from __future__ import annotations

import re

from .corpus import Chunk, Section, fixed_window_chunks

_FENCE = re.compile(r"(?ms)^(```[^\n]*\n.*?^```)\s*$")


def split_segments(text: str) -> list[tuple[str, str]]:
    """Split a section into ("prose" | "code", text) segments, in document order."""
    out: list[tuple[str, str]] = []
    pos = 0
    for m in _FENCE.finditer(text):
        prose = text[pos:m.start()].strip()
        if prose:
            out.append(("prose", prose))
        out.append(("code", m.group(1).strip()))
        pos = m.end()
    tail = text[pos:].strip()
    if tail:
        out.append(("prose", tail))
    return out


def last_paragraph(prose: str) -> str:
    paragraphs = [p.strip() for p in prose.split("\n\n") if p.strip()]
    return paragraphs[-1] if paragraphs else ""


def code_aware_chunks(sections: list[Section], tokenizer, window: int = 128, overlap: int = 32,
                      attach_lead: bool = True, max_code_tokens: int = 512) -> list[Chunk]:
    """Prose goes through the fixed window; every fenced block becomes one chunk of its own.

    `attach_lead` prepends the paragraph that precedes the block, so the code chunk also carries the
    words a question is likely to use. Blocks longer than `max_code_tokens` are split on blank lines.
    """
    chunks: list[Chunk] = []

    def add(section: Section, text: str, kind: str) -> None:
        chunks.append(Chunk(f"k{len(chunks):05d}", section.chapter, section.section, text,
                            {"title": section.title, "kind": kind, "path": section.path}))

    for s in sections:
        lead = ""
        for kind, text in split_segments(s.text):
            if kind == "prose":
                lead = last_paragraph(text)
                piece = Section(s.chapter, s.title, s.section, text, s.path)
                chunks.extend(
                    Chunk(f"k{len(chunks) + i:05d}", c.chapter, c.section, c.text,
                          {**c.meta, "kind": "prose"})
                    for i, c in enumerate(fixed_window_chunks([piece], tokenizer, window, overlap))
                )
                continue
            body = f"{lead}\n{text}" if (attach_lead and lead) else text
            n = len(tokenizer(body, add_special_tokens=False)["input_ids"])
            if n <= max_code_tokens:
                add(s, body, "code")
                continue
            head, parts, buf = lead, [], []
            for block in text.split("\n\n"):
                buf.append(block)
                if len(tokenizer("\n\n".join(buf), add_special_tokens=False)["input_ids"]) > max_code_tokens:
                    parts.append("\n\n".join(buf))
                    buf = []
            if buf:
                parts.append("\n\n".join(buf))
            for part in parts:
                add(s, f"{head}\n{part}" if (attach_lead and head) else part, "code")
    return chunks


def code_stats(sections: list[Section], tokenizer) -> dict:
    blocks = [t for s in sections for k, t in split_segments(s.text) if k == "code"]
    lengths = [len(tokenizer(b, add_special_tokens=False)["input_ids"]) for b in blocks]
    return {"blocks": len(blocks), "median_tokens": sorted(lengths)[len(lengths) // 2],
            "max_tokens": max(lengths), "over_128": sum(1 for n in lengths if n > 128)}


if __name__ == "__main__":
    from .corpus import load_sections
    from .embed import Embedder

    secs = load_sections()
    tok = Embedder().tokenizer
    print(code_stats(secs, tok))
    ch = code_aware_chunks(secs, tok)
    print("chunks:", len(ch), "code chunks:", sum(1 for c in ch if c.meta.get("kind") == "code"))
