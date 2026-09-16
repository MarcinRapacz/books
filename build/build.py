#!/usr/bin/env python3
"""Build the book: chapters/*.md -> build/book.html -> build/book.pdf (headless Chrome)."""
from __future__ import annotations

import html
import re
import subprocess
import sys
from pathlib import Path

import os
import markdown
from pygments.formatters import HtmlFormatter

PRINT = os.environ.get("PRINT") == "1"          # PRINT=1 -> bound, single-sided, toner-friendly variant
DUPLEX = os.environ.get("DUPLEX") == "1"        # DUPLEX=1 -> mirrored margins for double-sided printing

ROOT = Path(__file__).resolve().parent.parent
CHAPTERS = ROOT / "chapters"
BUILD = ROOT / "build"

TITLE = "AI Engineer"
SUBTITLE = "Praktyczny przewodnik po roadmapie roadmap.sh/ai-engineer"
AUTHOR = "Marcin & Claude"

CSS = """
@page { size: A4; margin: __PAGE_MARGIN__;
  @bottom-center { content: counter(page); font-family: "Noto Sans", sans-serif; font-size: 9pt; color: #64748b; }
  @top-right { content: "AI Engineer"; font-family: "Noto Sans", sans-serif; font-size: 8pt; color: #94a3b8; } }
@page :first { margin: 0; @bottom-center { content: none; } @top-right { content: none; } }
html { font-size: 10.5pt; }
body { font-family: "Noto Serif", "Liberation Serif", serif; line-height: 1.5; color: #1a1a1a; margin: 0; }
h1, h2, h3, h4 { font-family: "Noto Sans", "Liberation Sans", sans-serif; color: #0f172a; line-height: 1.2; break-after: avoid; }
h1 { font-size: 26pt; margin: 0 0 18pt; padding-bottom: 8pt; border-bottom: 2px solid #0f172a; }
h2 { font-size: 16pt; margin: 22pt 0 8pt; }
h3 { font-size: 12.5pt; margin: 16pt 0 6pt; }
p { margin: 0 0 8pt; text-align: justify; hyphens: auto; orphans: 3; widows: 3; }
ul, ol { margin: 0 0 8pt; padding-left: 1.4em; }
li { margin-bottom: 3pt; }
li > p { margin-bottom: 3pt; }
blockquote { margin: 0 0 12pt; padding: 8pt 12pt; background: #f1f5f9; border-left: 4px solid #334155; font-size: 9.5pt; }
blockquote p { margin: 0 0 4pt; text-align: left; }
code { font-family: "JetBrains Mono", "DejaVu Sans Mono", "Liberation Mono", monospace; font-size: 0.85em; background: #f1f5f9; padding: 0 3px; border-radius: 2px; }
pre { font-family: "JetBrains Mono", "DejaVu Sans Mono", "Liberation Mono", monospace; font-size: 8.4pt; line-height: 1.35;
      background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 4px; padding: 8pt 10pt; margin: 6pt 0 10pt;
      white-space: pre-wrap; word-break: break-word; break-inside: avoid; }
pre code { background: none; padding: 0; font-size: inherit; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0 12pt; font-size: 9pt; font-family: "Noto Sans", "Liberation Sans", sans-serif; break-inside: auto; }
tr { break-inside: avoid; }
thead { display: table-header-group; }
th, td { border: 1px solid #cbd5e1; padding: 4pt 6pt; vertical-align: top; text-align: left; overflow-wrap: break-word; }
table code, li code { overflow-wrap: break-word; }
th { background: #e2e8f0; }
hr { border: 0; border-top: 1px solid #cbd5e1; margin: 16pt 0; }
a { color: #1d4ed8; text-decoration: none; }
.chapter { break-before: page; }
.chapter:first-of-type { break-before: auto; }
.cover { height: 297mm; width: 210mm; box-sizing: border-box; padding: 60mm 25mm; background: #0f172a; color: #f8fafc;
         display: flex; flex-direction: column; justify-content: space-between; break-after: page; }
.cover h1 { color: #f8fafc; border: 0; font-size: 44pt; margin: 0; }
.cover .subtitle { font-family: "Noto Sans", sans-serif; font-size: 14pt; color: #cbd5e1; margin-top: 12pt; }
.cover .meta { font-family: "Noto Sans", sans-serif; font-size: 11pt; color: #94a3b8; }
.toc { break-after: page; }
.toc h1 { font-size: 22pt; }
.toc ul { list-style: none; padding-left: 0; font-family: "Noto Sans", sans-serif; }
.toc > ul > li { margin: 6pt 0; font-weight: 600; }
.toc ul ul { padding-left: 1.4em; font-weight: 400; font-size: 9.5pt; }
.toc ul ul ul { display: none; }
.toc li > a { display: flex; justify-content: space-between; color: #0f172a; }
.toc li > a .pg { font-weight: 400; color: #64748b; margin-left: 8pt; }
.sources { font-size: 8.5pt; }
.sources li { word-break: break-all; }
.footnote { font-size: 8.5pt; color: #475569; }
.katex-display { margin: 8pt 0 12pt; }
"""

PAGE_MARGIN = os.environ.get("PAGE_MARGIN") or ("22mm 18mm 24mm 38mm" if PRINT else "22mm 20mm 24mm 20mm")
CSS = CSS.replace("__PAGE_MARGIN__", PAGE_MARGIN)
PRINT_CSS = """
@page :left { margin: 22mm 38mm 24mm 18mm; }
@page :right { margin: 22mm 18mm 24mm 38mm; }
""" if DUPLEX else ""

# pygments css for codehilite
PYGMENTS_CSS = HtmlFormatter(style="friendly").get_style_defs(".codehilite")


def load_chapters() -> list[tuple[str, str]]:
    files = sorted(p for p in CHAPTERS.glob("*.md") if re.match(r"^\d{2}-", p.name))
    return [(p.stem, p.read_text(encoding="utf-8")) for p in files]


def render(md_text: str) -> str:
    md = markdown.Markdown(
        extensions=["fenced_code", "codehilite", "tables", "toc", "attr_list", "sane_lists", "footnotes", "md_in_html"],
        extension_configs={
            "codehilite": {"guess_lang": False, "css_class": "codehilite", "noclasses": False},
            "toc": {"toc_depth": "1-2", "permalink": False},
        },
    )
    body = md.convert(md_text)
    return body, md.toc


def main() -> int:
    chapters = load_chapters()
    if not chapters:
        print("no chapters found", file=sys.stderr)
        return 1

    # Render all chapters as one document so the TOC covers everything.
    joined = "\n\n".join(text.strip() + "\n" for _, text in chapters)
    body, toc = render(joined)
    # Wrap each chapter (starting at <h1>) in a div for page breaks.
    parts = re.split(r"(?=<h1 )", body)
    body = "".join(f'<section class="chapter">{p}</section>' if p.startswith("<h1") else p for p in parts)
    # Mark sources sections for smaller font.
    body = re.sub(r'(<h2 id="[^"]*">Źródła</h2>)(.*?)(?=<section|</section>|$)', r'\1<div class="sources">\2</div>', body, flags=re.S)

    doc = f"""<!DOCTYPE html>
<html lang="pl"><head><meta charset="utf-8"><title>{html.escape(TITLE)}</title>
<style>{CSS}\n{PRINT_CSS if PRINT else ""}\n{PYGMENTS_CSS}</style>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css">
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/contrib/auto-render.min.js"
  onload="renderMathInElement(document.body, {{delimiters: [{{left: '$$', right: '$$', display: true}}, {{left: '$', right: '$', display: false}}], throwOnError: false}});"></script>
</head>
<body>
<div class="cover">
  <div><h1>{html.escape(TITLE)}</h1><div class="subtitle">{html.escape(SUBTITLE)}</div></div>
  <div class="meta">{html.escape(AUTHOR)} · wydanie robocze · {len(chapters)} rozdz.</div>
</div>
<div class="toc"><h1>Spis treści</h1>{toc}</div>
{body}
</body></html>"""

    BUILD.mkdir(exist_ok=True)
    suffix = "-print" if PRINT else ""
    out_html = BUILD / f"book{suffix}.html"
    out_pdf = BUILD / f"book{suffix}.pdf"

    def print_pdf() -> None:
        cmd = [
            "google-chrome", "--headless=new", "--disable-gpu", "--no-sandbox", "--no-pdf-header-footer",
            "--virtual-time-budget=15000", f"--print-to-pdf={out_pdf}", f"file://{out_html}",
        ]
        subprocess.run(cmd, check=True, capture_output=True)

    # Pass 1: print without page numbers in the TOC.
    out_html.write_text(doc, encoding="utf-8")
    print_pdf()

    # Find the first page (after the TOC) on which each TOC heading appears as a line.
    text = subprocess.run(["pdftotext", "-layout", str(out_pdf), "-"], check=True, capture_output=True, text=True).stdout
    pages = text.split("\f")
    toc_pages = 1 + sum(1 for pg in pages[1:] if "Spis treści" in pg and "Rozdział" in pg)  # cover + toc page(s)

    cursor = [toc_pages]  # headings appear in document order, so never search backwards

    def find_page(title: str) -> int | None:
        norm = re.sub(r"\s+", " ", html.unescape(title)).strip()
        for i, pg in enumerate(pages[cursor[0]:], start=cursor[0] + 1):
            for line in pg.splitlines():
                ln = re.sub(r"\s+", " ", line).strip()
                if ln == norm or (len(norm) > 40 and ln and norm.startswith(ln) and len(ln) >= 25):
                    cursor[0] = i - 1
                    return i
        return None

    def add_page(m: re.Match) -> str:
        href, title = m.group(1), m.group(2)
        pg = find_page(title)
        pg_html = f'<span class="pg">{pg}</span>' if pg else ""
        return f'<a href="{href}"><span>{title}</span>{pg_html}</a>'

    toc_numbered = re.sub(r'<a href="([^"]+)">([^<]+)</a>', add_page, toc)
    doc2 = doc.replace(toc, toc_numbered, 1)
    out_html.write_text(doc2, encoding="utf-8")
    print_pdf()
    print(f"wrote {out_html} and {out_pdf}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
