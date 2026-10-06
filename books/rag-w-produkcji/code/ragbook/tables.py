"""Markdown tables: find them, take them out of the prose, and serialise them three ways.

A fixed window does not know what a table is. It cuts rows in half and it leaves every row after the
first without the column names, so the cell "natychmiastowa (reindeksacja dokumentu)" ends up in the
index with nothing saying that the column is "RAG" and the row is "Świeżość danych".

Serialisations here:
- `table_as_chunk`   one chunk for the whole table, prefixed with chapter / section / lead paragraph
- `table_rows`       one chunk per row, with the column names repeated in every cell
- `table_sentences`  one chunk per row, written out as a sentence
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .corpus import Chunk, Section

_SEP = re.compile(r"^\s*\|[\s:|-]+\|\s*$")


@dataclass
class Table:
    chapter: int
    title: str
    section: str
    header: list[str]
    rows: list[list[str]]
    lead: str            # the paragraph right before the table, usually its caption in disguise

    @property
    def key(self) -> tuple[int, str]:
        return (self.chapter, self.section)


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def split_tables(section: Section) -> tuple[str, list[Table]]:
    """Return the section text with every Markdown table removed, plus the parsed tables."""
    lines = section.text.splitlines()
    kept: list[str] = []
    tables: list[Table] = []
    i, in_fence = 0, False
    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            in_fence = not in_fence
        is_table_head = (not in_fence and line.strip().startswith("|")
                         and i + 1 < len(lines) and _SEP.match(lines[i + 1]))
        if not is_table_head:
            kept.append(line)
            i += 1
            continue
        header = _cells(line)
        rows = []
        i += 2
        while i < len(lines) and lines[i].strip().startswith("|"):
            rows.append(_cells(lines[i]))
            i += 1
        lead = next((t for t in reversed(kept) if t.strip() and not t.startswith(("#", "|", "```"))), "")
        tables.append(Table(section.chapter, section.title, section.section, header, rows, lead.strip()))
    return "\n".join(kept).strip(), tables


def find_tables(sections: list[Section]) -> list[Table]:
    return [t for s in sections for t in split_tables(s)[1]]


def _head(t: Table) -> str:
    return f"{t.title} / {t.section}"


def table_as_chunk(t: Table) -> str:
    head = "| " + " | ".join(t.header) + " |"
    sep = "|" + "|".join("---" for _ in t.header) + "|"
    body = ["| " + " | ".join(r) + " |" for r in t.rows]
    return "\n".join([_head(t), t.lead, head, sep, *body]).strip()


def table_rows(t: Table) -> list[str]:
    """One chunk per row: `Kryterium: Świeżość danych; RAG: natychmiastowa; Fine-tuning: ...`."""
    out = []
    for row in t.rows:
        pairs = "; ".join(f"{h}: {c}" for h, c in zip(t.header, row) if c)
        out.append(f"{_head(t)}\n{pairs}")
    return out


def table_sentences(t: Table) -> list[str]:
    """One chunk per row, written as prose: the first column is the subject, the rest are clauses."""
    out = []
    for row in t.rows:
        subject = row[0] if row else ""
        clauses = [f"{h} to {c}" for h, c in zip(t.header[1:], row[1:]) if c]
        if not clauses:
            continue
        label = t.header[0] or "pozycja"
        out.append(f"{_head(t)}\nDla pozycji „{subject}” ({label}): " + ", a ".join(clauses) + ".")
    return out


def build_chunks(sections: list[Section], tokenizer, mode: str = "window",
                 window: int = 128, overlap: int = 32) -> list[Chunk]:
    """Chunk the corpus with one of the table strategies.

    mode="window"     tables stay in the prose and are cut by the fixed window (the baseline)
    mode="table"      tables are pulled out and indexed whole, one chunk each
    mode="rows"       tables are pulled out and indexed row by row, column names repeated
    mode="sentences"  tables are pulled out and indexed row by row as sentences
    """
    from .corpus import fixed_window_chunks

    if mode == "window":
        return fixed_window_chunks(sections, tokenizer, window, overlap)

    stripped: list[Section] = []
    extra: list[Chunk] = []
    for s in sections:
        text, tables = split_tables(s)
        stripped.append(Section(s.chapter, s.title, s.section, text, s.path))
        for t in tables:
            texts = {"table": [table_as_chunk(t)], "rows": table_rows(t),
                     "sentences": table_sentences(t)}[mode]
            for text_i in texts:
                extra.append(Chunk(f"t{len(extra):05d}", t.chapter, t.section, text_i,
                                   {"title": t.title, "kind": "table", "path": s.path}))
    chunks = fixed_window_chunks([s for s in stripped if s.text], tokenizer, window, overlap)
    return chunks + extra


if __name__ == "__main__":
    from .corpus import load_sections

    tables = find_tables(load_sections())
    print(f"{len(tables)} tables, {sum(len(t.rows) for t in tables)} rows")
    t = next(t for t in tables if t.section == "RAG a fine-tuning")
    print(table_rows(t)[2])
    print(table_sentences(t)[2])
