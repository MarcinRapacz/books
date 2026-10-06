"""PDF extraction for the volume-1 PDF (`build/ai-engineer.pdf`) with PyMuPDF.

Two extractors, on purpose:

- `raw_sections()`   - what you get from `page.get_text()` and nothing else: running heads, page
                       numbers, paragraphs cut at page breaks, code glued to prose, tables scattered.
- `clean_sections()` - the same pages after layout-aware cleaning: repeated header/footer lines are
                       dropped, lines are classified by font size and family (heading / body / code /
                       table), paragraphs are re-joined across line and page breaks, code blocks are
                       fenced again.

Both return `ragbook.corpus.Section` objects so the rest of the toolchain (chunkers, index,
evaluation) does not care where the text came from.
"""
from __future__ import annotations

import collections
import re
from dataclasses import dataclass, field
from pathlib import Path

from .corpus import CODE_DIR, Section

PDF_PATH = CODE_DIR.parent.parent.parent / "build" / "ai-engineer.pdf"

_CHAPTER_RE = re.compile(r"^Rozdział\s+(\d+)\.\s*(.+)$")


@dataclass
class Line:
    page: int
    text: str
    size: float          # dominant font size on the line (points)
    font: str            # dominant font name, e.g. "NotoSerif-Regular", "DejaVuSansMono"
    x0: float
    x1: float
    y0: float
    kind: str = "body"   # h1 | h2 | h3 | body | code | table


@dataclass
class Element:
    kind: str            # h1 | h2 | h3 | para | code | table
    text: str
    pages: tuple[int, ...] = field(default_factory=tuple)


def page_lines(page) -> list[Line]:
    """One `Line` per visual line, with the font size and family of its dominant span."""
    out: list[Line] = []
    for block in page.get_text("dict", sort=True)["blocks"]:
        if block["type"] != 0:            # 0 = text, 1 = image
            continue
        for line in block["lines"]:
            spans = [s for s in line["spans"] if s["text"].strip()]
            if not spans:
                continue
            dominant = max(spans, key=lambda s: len(s["text"]))
            text = "".join(s["text"] for s in line["spans"]).rstrip()
            if not text.strip():
                continue
            x0 = min(s["bbox"][0] for s in spans)
            x1 = max(s["bbox"][2] for s in spans)
            out.append(Line(page.number, text, round(dominant["size"], 2), dominant["font"],
                            x0, x1, line["bbox"][1]))
    return out


def running_lines(lines: list[Line], page_count: int, band: float = 0.08,
                  page_height: float = 841.92) -> set[str]:
    """Text that repeats in the top or bottom band of most pages: the running head and the folio.

    Page numbers differ on every page, so they are folded to `#` before counting.
    """
    counter: collections.Counter[str] = collections.Counter()
    for ln in lines:
        if ln.y0 > band * page_height and ln.y0 < (1 - band) * page_height:
            continue
        counter[re.sub(r"\d+", "#", ln.text.strip())] += 1
    return {pattern for pattern, n in counter.items() if n > page_count / 2}


def classify(line: Line, body_size: float) -> str:
    if line.size >= 1.9 * body_size:
        return "h1"
    if 1.35 * body_size <= line.size < 1.9 * body_size:
        return "h2"
    if 1.10 * body_size <= line.size < 1.35 * body_size:
        return "h3"
    if "Mono" in line.font and line.size < body_size:
        return "code"
    if "Sans" in line.font and line.size < body_size:
        return "table"
    return "body"


def load_lines(pdf_path: Path = PDF_PATH, drop_running: bool = True) -> list[Line]:
    """All lines of the document, classified, with the running head/folio optionally removed."""
    import pymupdf

    doc = pymupdf.open(pdf_path)
    lines = [ln for page in doc for ln in page_lines(page)]
    height = doc[0].rect.height
    page_count = doc.page_count
    doc.close()

    body_size = collections.Counter(
        ln.size for ln in lines for _ in ln.text).most_common(1)[0][0]
    for ln in lines:
        ln.kind = classify(ln, body_size)

    if drop_running:
        patterns = running_lines(lines, page_count, page_height=height)
        lines = [ln for ln in lines
                 if re.sub(r"\d+", "#", ln.text.strip()) not in patterns]
    return lines


def _join(previous: str, nxt: str) -> str:
    """Join two lines of one paragraph, undoing CSS hyphenation (`hyphens: auto`)."""
    if previous.endswith("-") and nxt[:1].islower():
        return previous[:-1] + nxt
    return previous + " " + nxt


def elements(lines: list[Line], right_margin: float | None = None,
             tolerance: float = 6.0) -> list[Element]:
    """Group classified lines into paragraphs, code blocks, tables and headings.

    A paragraph continues while its lines reach the right margin - that is what justified text gives
    you, and it is the only signal that survives a page break.
    """
    body = [ln for ln in lines if ln.kind == "body"]
    if right_margin is None:
        right_margin = max((ln.x1 for ln in body), default=0.0)

    out: list[Element] = []
    buf: list[Line] = []
    buf_kind = ""

    def flush() -> None:
        nonlocal buf, buf_kind
        if not buf:
            return
        pages = tuple(sorted({ln.page for ln in buf}))
        if buf_kind == "code":
            text = "\n".join(ln.text for ln in buf)
            out.append(Element("code", text, pages))
        elif buf_kind == "table":
            out.append(Element("table", "\n".join(ln.text for ln in buf), pages))
        elif buf_kind in ("h1", "h2", "h3"):
            text = " ".join(ln.text.strip() for ln in buf)
            out.append(Element(buf_kind, text, pages))
        else:
            text = buf[0].text.strip()
            for ln in buf[1:]:
                text = _join(text, ln.text.strip())
            out.append(Element("para", text, pages))
        buf, buf_kind = [], ""

    for ln in lines:
        if ln.kind != buf_kind:
            flush()
            buf_kind = ln.kind
        buf.append(ln)
        if ln.kind == "body" and ln.x1 < right_margin - tolerance:
            flush()                       # short line: the paragraph ended here
    flush()
    return out


def _sections_from_elements(els: list[Element]) -> list[Section]:
    """Walk headings and collect the body under each `h2` into a `Section`."""
    sections: list[Section] = []
    chapter, title, section, buf = None, "", "", []

    def close() -> None:
        if chapter is not None and buf:
            sections.append(Section(chapter, title, section, "\n\n".join(buf).strip(),
                                    "ai-engineer.pdf"))

    for el in els:
        if el.kind == "h1":
            close()
            buf = []
            m = _CHAPTER_RE.match(el.text)
            chapter = int(m.group(1)) if m else 0
            title = m.group(2) if m else el.text
            section = ""
        elif el.kind == "h2":
            close()
            buf = []
            section = el.text
        elif el.kind == "h3":
            buf.append("### " + el.text)
        elif el.kind == "code":
            buf.append("```\n" + el.text + "\n```")
        else:
            buf.append(el.text)
    close()
    return [s for s in sections if s.chapter and s.text]


def clean_sections(pdf_path: Path = PDF_PATH) -> list[Section]:
    """Layout-aware extraction: no running head, paragraphs re-joined, code fenced, sections named."""
    return _sections_from_elements(elements(load_lines(pdf_path)))


def looks_like_heading(text: str) -> bool:
    """The heuristic everyone writes first: a short line that is not a sentence."""
    t = text.strip()
    if not (0 < len(t) <= 60) or t[0].islower() or t[-1] in ".,:;-–—)":
        return False
    return not t.replace(" ", "").isdigit()


def raw_sections(pdf_path: Path = PDF_PATH, headings: str = "known") -> list[Section]:
    """`page.get_text()` and nothing more, split into sections by one of two heading rules.

    headings="known"  lines matching a `##` heading of the Markdown ground truth start a section.
                      Deliberately generous - it hands the raw variant metadata it could not have -
                      so that the comparison isolates text quality.
    headings="guess"  `looks_like_heading()`, i.e. what you write when you only have `get_text()`.

    Everything else - running heads, folios, broken paragraphs, code glued to prose - stays in.
    """
    import pymupdf

    known: set[str] = set()
    if headings == "known":
        from .corpus import load_sections
        known = {s.section for s in load_sections() if s.section}

    doc = pymupdf.open(pdf_path)
    sections: list[Section] = []
    chapter, title, section, buf = None, "", "", []

    def close() -> None:
        if chapter is not None and buf:
            sections.append(Section(chapter, title, section, "\n".join(buf).strip(),
                                    "ai-engineer.pdf"))

    for page in doc:
        for line in page.get_text().splitlines():
            stripped = line.strip()
            m = _CHAPTER_RE.match(stripped)
            if m:
                close()
                buf = []
                chapter, title, section = int(m.group(1)), m.group(2), ""
            elif (stripped in known) if headings == "known" else looks_like_heading(stripped):
                close()
                buf = []
                section = stripped
            else:
                buf.append(line)
    close()
    doc.close()
    return [s for s in sections if s.chapter and s.text]


if __name__ == "__main__":
    lines = load_lines(drop_running=False)
    kinds = collections.Counter(ln.kind for ln in lines)
    print("lines:", len(lines), dict(kinds))
    kept = load_lines()
    print("after dropping running head/folio:", len(kept))
    els = elements(kept)
    print("elements:", collections.Counter(e.kind for e in els))
    print("paragraphs spanning a page break:",
          sum(1 for e in els if e.kind == "para" and len(e.pages) > 1))
    secs = clean_sections()
    print("clean sections:", len(secs), "words:", sum(len(s.text.split()) for s in secs))
    raw = raw_sections()
    print("raw sections:", len(raw), "words:", sum(len(s.text.split()) for s in raw))
