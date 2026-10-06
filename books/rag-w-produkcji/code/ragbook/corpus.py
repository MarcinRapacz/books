"""Corpus loader: the 14 Markdown chapters of volume 1 ("AI Engineer") split into sections.

A *section* is one `##` heading of one chapter, with the chapter title attached. Sections are the unit
of relevance in the golden set, so every chunk produced from a section must keep `chapter` and `section`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parent.parent
CORPUS_DIR = CODE_DIR.parent.parent / "ai-engineer" / "chapters"


@dataclass
class Section:
    chapter: int            # chapter number in volume 1 (0 = preface)
    title: str              # chapter title, e.g. "RAG: generowanie wspomagane wyszukiwaniem"
    section: str            # exact `##` heading text, e.g. "Chunking"; "" for text before the first heading
    text: str               # Markdown body of the section (without the heading line)
    path: str               # source file name

    @property
    def key(self) -> tuple[int, str]:
        return (self.chapter, self.section)


@dataclass
class Chunk:
    id: str
    chapter: int
    section: str
    text: str
    meta: dict = field(default_factory=dict)

    @property
    def key(self) -> tuple[int, str]:
        return (self.chapter, self.section)


_H1 = re.compile(r"^#\s+(?:Rozdział\s+(\d+)\.\s*)?(.+?)\s*$")
_H2 = re.compile(r"^##\s+(.+?)\s*$")


def load_sections(corpus_dir: Path = CORPUS_DIR, include_preface: bool = False) -> list[Section]:
    """Parse every `NN-*.md` chapter into sections. Headings inside fenced code blocks are ignored."""
    sections: list[Section] = []
    for path in sorted(corpus_dir.glob("[0-9][0-9]-*.md")):
        chapter, title, current, buf = None, "", "", []
        in_fence = False
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("```"):
                in_fence = not in_fence
            if not in_fence:
                m1 = _H1.match(line)
                if m1 and chapter is None:
                    chapter = int(m1.group(1)) if m1.group(1) else 0
                    title = m1.group(2)
                    continue
                m2 = _H2.match(line)
                if m2:
                    if chapter is not None:
                        sections.append(Section(chapter, title, current, "\n".join(buf).strip(), path.name))
                    current, buf = m2.group(1), []
                    continue
            buf.append(line)
        if chapter is not None:
            sections.append(Section(chapter, title, current, "\n".join(buf).strip(), path.name))
    if not include_preface:
        sections = [s for s in sections if s.chapter > 0]
    return [s for s in sections if s.text]


def fixed_window_chunks(sections: list[Section], tokenizer, window: int = 128, overlap: int = 32,
                        prefix_with_title: bool = False) -> list[Chunk]:
    """Naive baseline chunker: fixed token window with overlap, cut inside each section.

    `tokenizer` is a Hugging Face tokenizer (e.g. `SentenceTransformer(...).tokenizer`).
    """
    chunks: list[Chunk] = []
    step = max(1, window - overlap)
    for s in sections:
        ids = tokenizer(s.text, add_special_tokens=False)["input_ids"]
        for start in range(0, max(1, len(ids)), step):
            piece = ids[start:start + window]
            if not piece:
                break
            text = tokenizer.decode(piece)
            if prefix_with_title:
                text = f"{s.title} / {s.section}\n{text}"
            chunks.append(Chunk(f"c{len(chunks):05d}", s.chapter, s.section, text,
                                {"title": s.title, "start_token": start, "path": s.path}))
            if start + window >= len(ids):
                break
    return chunks


if __name__ == "__main__":
    secs = load_sections()
    words = sum(len(s.text.split()) for s in secs)
    print(f"{len(secs)} sections, {words} words, chapters {min(s.chapter for s in secs)}-{max(s.chapter for s in secs)}")
    for s in secs[:5]:
        print(s.chapter, repr(s.section), len(s.text.split()), "words")
