"""Chapter 8: the indexing pipeline as a process.

Measures a full index build against an incremental sync after editing one chapter, shows orphan removal,
document deletion by filter, and a blue/green switch of the collection alias after an embedding-model change.

The corpus is copied to a scratch directory first -- the experiment edits files, and volume 1 must not change.

Run from the `code/` directory:  ../.venv/bin/python experiments/08_indexing.py
Optional: RAGBOOK_WORK=/path/to/scratch to keep the copy around between runs.
"""
from __future__ import annotations

import gc
import os
import shutil
import tempfile
from pathlib import Path

from qdrant_client import QdrantClient

from ragbook.corpus import CORPUS_DIR
from ragbook.embed import DEFAULT_MODEL, Embedder
from ragbook.indexing import Index, alias_target, chunk_document, load_documents, switch_alias

WORK = Path(os.environ.get("RAGBOOK_WORK") or tempfile.mkdtemp(prefix="ragbook-08-"))
CORPUS_COPY = WORK / "corpus"
ALT_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"


def fresh_copy() -> Path:
    if CORPUS_COPY.exists():
        shutil.rmtree(CORPUS_COPY)
    shutil.copytree(CORPUS_DIR, CORPUS_COPY)
    return CORPUS_COPY


def chunks_for(corpus_dir: Path, tokenizer) -> list:
    return [c for doc in load_documents(corpus_dir) for c in chunk_document(doc, tokenizer)]


def main() -> None:
    fresh_copy()
    print(f"work dir: {WORK}")

    # cache=False on purpose: we are measuring embedding time, so it must not be served from disk.
    embedder = Embedder(cache=False)
    client = QdrantClient(":memory:")
    index = Index(client, "chunks_e5", embedder, recreate=True)

    chunks = chunks_for(CORPUS_COPY, embedder.tokenizer)
    print(f"\ndocuments: {len({c.meta['doc_id'] for c in chunks})}  chunks: {len(chunks)}")

    full = index.sync(chunks)
    print("\n=== full build ===")
    print(full.as_row("pełna indeksacja"))

    # --- 1a. edit at the end of a section: one sentence appended before the next heading ---
    target = CORPUS_COPY / "07-bazy-wektorowe.md"
    text = target.read_text(encoding="utf-8")
    marker = "## Podsumowanie"
    text = text.replace(marker, "Qdrant od wersji 1.19 pozwala przełączyć alias kolekcji jedną operacją.\n\n" + marker, 1)
    target.write_text(text, encoding="utf-8")

    changed = chunks_for(CORPUS_COPY, embedder.tokenizer)
    tail_edit = index.sync(changed)
    print("\n=== incremental sync: sentence appended at the end of a section ===")
    print(tail_edit.as_row("dopisek na końcu sekcji"))

    # --- 1b. edit at the beginning of a long section: every window in that section shifts ---
    text = target.read_text(encoding="utf-8")
    head = "## Wybór bazy w praktyce"
    text = text.replace(head + "\n", head + "\n\nOd wersji 1.19 alias kolekcji przełącza się jedną atomową "
                        "operacją, więc migracja indeksu nie wymaga przestoju ani zmian w kodzie klienta.\n", 1)
    target.write_text(text, encoding="utf-8")

    changed = chunks_for(CORPUS_COPY, embedder.tokenizer)
    inc = index.sync(changed)
    print("\n=== incremental sync: paragraph inserted at the start of a long section ===")
    print(inc.as_row("wstawka na początku sekcji"))
    print(f"speedup vs full: {full.seconds / inc.seconds:.1f}x")

    # --- 2. no-op sync: nothing changed, nothing embedded ---
    noop = index.sync(changed)
    print("\n=== sync with no changes ===")
    print(noop.as_row("bez zmian"))

    # --- 3. a document shrinks: orphaned points must go ---
    shrunk = target.read_text(encoding="utf-8")
    cut = shrunk.index("## Podsumowanie")
    target.write_text(shrunk[:cut] + "## Podsumowanie\n\nKrótko.\n", encoding="utf-8")
    after_shrink = chunks_for(CORPUS_COPY, embedder.tokenizer)
    shrink = index.sync(after_shrink)
    print("\n=== document shrunk (sections removed) ===")
    print(shrink.as_row("skrócony rozdział"), "points in collection:", index.count())

    # --- 4. document removed from the corpus: the sync notices, but the explicit delete is instant ---
    (CORPUS_COPY / "13-multimodalnosc.md").unlink()
    removed = index.delete_document("13-multimodalnosc.md")
    after_delete = index.sync(chunks_for(CORPUS_COPY, embedder.tokenizer))
    print(f"\n=== delete_document('13-multimodalnosc.md') -> {removed} points removed, "
          f"{index.count()} left; following sync: {after_delete.as_row('po usunięciu pliku')} ===")

    # --- 5. blue/green: a new embedding model means a new collection, switched by alias ---
    switch_alias(client, "chunks", "chunks_e5")
    q = "jak przełączyć alias kolekcji w Qdrancie"
    before = index.search(q, k=1, collection="chunks")[0]
    print(f"\nalias 'chunks' -> {alias_target(client, 'chunks')}  "
          f"top1: r{before.chapter}/{before.section!r} score {before.meta['score']:.3f}")

    del embedder, index
    gc.collect()

    alt = Embedder(ALT_MODEL, cache=False)
    green = Index(client, "chunks_minilm", alt, recreate=True)
    green_stats = green.sync(chunks_for(CORPUS_COPY, alt.tokenizer))
    print(f"\n=== green collection ({ALT_MODEL}) ===")
    print(green_stats.as_row("nowy model"))

    switch_alias(client, "chunks", "chunks_minilm")
    after = green.search(q, k=1, collection="chunks")[0]
    print(f"alias 'chunks' -> {alias_target(client, 'chunks')}  "
          f"top1: r{after.chapter}/{after.section!r} score {after.meta['score']:.3f}")
    print("collections:", sorted(c.name for c in client.get_collections().collections))

    print("\n| Operacja | Dokumenty | Chunki embedowane | Bez zmian | Usunięte punkty | Czas [s] |")
    print("|---|---|---|---|---|---|")
    for label, st in [("pełna indeksacja", full), ("dopisek na końcu sekcji", tail_edit),
                      ("wstawka na początku sekcji", inc),
                      ("sync bez zmian", noop), ("skrócenie rozdziału", shrink),
                      ("pełna indeksacja nowym modelem", green_stats)]:
        print(f"| {label} | {st.docs_changed} | {st.chunks_embedded} | {st.chunks_unchanged} "
              f"| {st.points_deleted} | {st.seconds:.1f} |")


if __name__ == "__main__":
    main()
