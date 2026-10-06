"""Chapter 2, table 3: giving a chunk back the context it lost when it was cut.

Three things that all glue something in front of the chunk before embedding, measured on the frozen
golden set:
- contextual chunk headers: "<chapter title> / <section heading>",
- the cheap approximation of contextual retrieval: header + the first sentence of the section,
- parent-child (small-to-big): a 128-token child is searched, its parent goes into the prompt.

The real contextual retrieval (an LLM writing one or two sentences per chunk) needs an API key; the
code lives in `ragbook.chunking.contextualize` and is printed here, not run.

Run from the `code/` directory:  ../.venv/bin/python experiments/02_context.py
"""
from __future__ import annotations

import time

from ragbook.chunking import (ParentRetriever, evaluate_chunks, merged_block_chunks,
                              parent_child_chunks, recursive_chunks, row, section_leads,
                              with_context_headers)
from ragbook.corpus import fixed_window_chunks, load_sections
from ragbook.embed import Embedder
from ragbook.evaluate import by_type, load_golden

HEAD = ("| Wariant | Chunków | Mediana tokenów | Tokeny w prompcie @5 | recall@5 | recall@20 "
        "| MRR@5 | nDCG@5 | Bez trafienia |\n|---|---|---|---|---|---|---|---|---|")


def main() -> None:
    sections = load_sections()
    golden = load_golden()
    embedder = Embedder()
    tok = embedder.tokenizer
    leads = section_leads(sections)

    base = {
        "stałe okno 128/32": lambda: fixed_window_chunks(sections, tok, 128, 32),
        "stałe okno 128/0": lambda: fixed_window_chunks(sections, tok, 128, 0),
        "bloki łączone do 256": lambda: merged_block_chunks(sections, tok, 256),
        "rekurencyjny 256": lambda: recursive_chunks(sections, tok, 256),
    }

    rows = []
    for label, fn in base.items():
        plain = fn()
        rows.append(evaluate_chunks(f"{label}", plain, embedder, golden))
        rows.append(evaluate_chunks(f"{label} + nagłówek", with_context_headers(plain, "title"),
                                    embedder, golden, count_tokens_on="body"))
        rows.append(evaluate_chunks(f"{label} + nagłówek + 1. zdanie sekcji",
                                    with_context_headers(plain, "lead", leads),
                                    embedder, golden, count_tokens_on="body"))
        for r in rows[-3:]:
            print(f"{r['name']:>44}  {r['chunks']:5d} chunks  recall@5 {r['recall@5']:.3f}  "
                  f"misses {r['misses@5']}", flush=True)

    print("\n=== Kontekst doklejany przed embedowaniem ===")
    print(HEAD)
    for r in rows:
        print(row(r))
    for r in rows:
        print(f"{r['name']:>44}  by type:",
              {t: round(v, 2) for t, v in by_type(r["result"], "recall@5").items()})

    # ---- parent-child: identical retrieval, different prompt --------------------------------------
    print("\n=== Parent-child (small-to-big) ===")
    p_rows = []
    for parent_kind in ("block", "section"):
        t0 = time.perf_counter()
        children, parents = parent_child_chunks(sections, tok, child_tokens=128, parent=parent_kind)
        heads = with_context_headers(children, "title")
        for dedup in (False, True):
            name = f"dziecko 128 -> rodzic ({parent_kind}){', dedup' if dedup else ''}"
            r = evaluate_chunks(name, heads, embedder, golden,
                                wrap=lambda idx, p=parents, d=dedup: ParentRetriever(idx, p, d))
            p_rows.append(r)
            print(f"{name:>44}  {len(children)} children, {len(parents)} parents, "
                  f"recall@5 {r['recall@5']:.3f}, prompt {r['prompt_tokens@5']} tok "
                  f"({time.perf_counter() - t0:.0f} s)", flush=True)
    child_only = evaluate_chunks("dziecko 128 (do promptu też dziecko)",
                                 with_context_headers(
                                     parent_child_chunks(sections, tok, 128, "block")[0], "title"),
                                 embedder, golden, count_tokens_on="body")
    print(HEAD)
    print(row(child_only))
    for r in p_rows:
        print(row(r))

    print("\n=== Prompt Contextual Retrieval (Anthropic), nieuruchamiany ===")
    from ragbook.chunking import CHUNK_TEMPLATE, CONTEXT_MODEL
    print("model:", CONTEXT_MODEL)
    print(CHUNK_TEMPLATE.format(chunk="<treść chunku>"))


if __name__ == "__main__":
    main()
