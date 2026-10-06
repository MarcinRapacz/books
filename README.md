# Seria „AI Engineer”

Książki pisane w Markdown, składane do PDF przez `build/build.py` (Markdown → HTML → headless Chrome).

```
books/
  ai-engineer/        tom 1: „AI Engineer. Praktyczny przewodnik po roadmapie roadmap.sh/ai-engineer” (143 strony, gotowy)
    BRIEF.md          zasady pisania (obowiązują też kolejne tomy)
    PLAN.md           plan i status rozdziałów
    book.json         tytuł, podtytuł, nagłówek strony, autor
    chapters/         NN-slug.md
  rag-w-produkcji/    tom 2: „RAG w produkcji” (w toku)
    BRIEF.md          różnice względem tomu 1, projekt przewodni, golden set
    PLAN.md
    book.json
    chapters/
    code/             kod projektu: pakiet ragbook, data/golden.jsonl, experiments/
    .venv/            venv projektu (uv), ignorowany przez git
build/
  build.py            skład: `.venv/bin/python build/build.py <slug>` → build/<slug>.pdf
  <slug>.pdf          gotowe PDF-y (PRINT=1 → <slug>-print.pdf, wariant do bindowania)
NEXT-BOOKS.md         plan kolejnych tomów
```

Skład tomu 1: `.venv/bin/python build/build.py ai-engineer`. Tomu 2: `.venv/bin/python build/build.py rag-w-produkcji`.
Venv do składu (`.venv` w katalogu głównym) ma tylko `markdown`, `pygments`, `pypdf`; venvy projektów książek są osobne.
