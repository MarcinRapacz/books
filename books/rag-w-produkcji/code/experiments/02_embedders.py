"""Chapter 2, table 5: the embedding model, the prefixes, the size of the index and the cost of building it.

Three multilingual models on the same chunker (the best fixed window from `02_chunking.py`), loaded
one at a time because the GPU has 4 GB and other people use the machine:
- intfloat/multilingual-e5-small          384 dims, 512 tokens, needs query:/passage:
- intfloat/multilingual-e5-base           768 dims, 512 tokens, needs query:/passage:  (--with-base)
- paraphrase-multilingual-MiniLM-L12-v2   384 dims, 128 tokens, no prefixes

Also measures what the E5 prefixes are worth (with and without, cache off so the two variants do not
share a cache entry) and how long embedding the corpus takes without the cache, on GPU and on CPU.

Run from the `code/` directory:  ../.venv/bin/python experiments/02_embedders.py [--with-base]
"""
from __future__ import annotations

import gc
import shutil
import subprocess
import sys
import time

from ragbook.chunking import evaluate_chunks, n_tokens, row
from ragbook.corpus import fixed_window_chunks, load_sections
from ragbook.embed import Embedder
from ragbook.evaluate import load_golden

E5_SMALL = "intfloat/multilingual-e5-small"
E5_BASE = "intfloat/multilingual-e5-base"
MINILM = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
WINDOW = 128

HEAD = ("| Wariant | Chunków | Mediana tokenów | Tokeny w prompcie @5 | recall@5 | recall@20 "
        "| MRR@5 | nDCG@5 | Bez trafienia |\n|---|---|---|---|---|---|---|---|---|")


def release() -> None:
    """One model at a time: 4 GB of VRAM on this machine, and other people are using the box."""
    gc.collect()
    try:
        import torch
        torch.cuda.empty_cache()
    except Exception:
        pass


def enough_room() -> bool:
    free_gb = shutil.disk_usage(".").free / 2 ** 30
    avail_mb = int(subprocess.run(["free", "-m"], capture_output=True, text=True)
                   .stdout.splitlines()[1].split()[-1])
    print(f"disk free {free_gb:.0f} GB, memory available {avail_mb} MB")
    return free_gb > 20 and avail_mb > 4000


def run_model(model_name: str, sections, golden, window: int = WINDOW) -> dict:
    embedder = Embedder(model_name)
    chunks = fixed_window_chunks(sections, embedder.tokenizer, window=window, overlap=0)
    r = evaluate_chunks(f"{model_name.split('/')[-1]}, okno {window}", chunks, embedder, golden)
    r["dim"] = embedder.dim
    r["max_seq"] = embedder.model.max_seq_length
    r["device"] = str(embedder.model.device)
    r["index_mb"] = r["chunks"] * embedder.dim * 4 / 2 ** 20
    print(f"{r['name']:>44}  dim {r['dim']}  max_seq {r['max_seq']}  chunks {r['chunks']}  "
          f"recall@5 {r['recall@5']:.3f}  index {r['index_mb']:.1f} MB  [{r['device']}]", flush=True)
    del embedder
    release()
    return r


def main() -> None:
    sections = load_sections()
    golden = load_golden()

    rows = [run_model(E5_SMALL, sections, golden)]
    rows.append(run_model(MINILM, sections, golden))
    # MiniLM reads 128 tokens and silently drops the rest; show what a 256-token window costs it.
    rows.append(run_model(MINILM, sections, golden, window=256))
    rows.append(run_model(E5_SMALL, sections, golden, window=256))
    if "--with-base" in sys.argv and enough_room():
        rows.append(run_model(E5_BASE, sections, golden))
    elif "--with-base" in sys.argv:
        print("not enough disk or memory for multilingual-e5-base, skipped")

    print("\n=== Model embeddingowy ===")
    print("| Model | Wymiar | Limit wejścia | Chunków | Indeks [MB] | recall@5 | recall@20 | MRR@5 "
          "| nDCG@5 | Bez trafienia |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        print(f"| {r['name']} | {r['dim']} | {r['max_seq']} | {r['chunks']} | "
              f"{r['index_mb']:.2f} | {r['recall@5']:.2f} | {r['recall@20']:.2f} | "
              f"{r['mrr@5']:.2f} | {r['ndcg@5']:.2f} | {r['misses@5']} |".replace(".", ","))
    print()
    print(HEAD)
    for r in rows:
        print(row(r))

    # ---- what are the E5 prefixes worth? ----------------------------------------------------------
    print("\n=== Prefiksy query:/passage: (cache wyłączony, żeby warianty się nie zlały) ===")
    pref_rows = []
    for use_prefixes in (True, False):
        embedder = Embedder(E5_SMALL, cache=False)
        if not use_prefixes:
            embedder.query_prefix = embedder.passage_prefix = ""
        chunks = fixed_window_chunks(sections, embedder.tokenizer, window=WINDOW, overlap=0)
        r = evaluate_chunks(f"e5-small {'z prefiksami' if use_prefixes else 'BEZ prefiksów'}",
                            chunks, embedder, golden)
        pref_rows.append(r)
        print(f"{r['name']:>32}  recall@5 {r['recall@5']:.3f}  mrr@5 {r['mrr@5']:.3f}  "
              f"misses {r['misses@5']}", flush=True)
        del embedder
        release()
    print(HEAD)
    for r in pref_rows:
        print(row(r))

    # ---- how long does embedding the corpus take without the cache? -------------------------------
    print("\n=== Czas embedowania korpusu (cache=False, jednorazowo) ===")
    print("| Model | Urządzenie | Chunków | Tokenów | Czas [s] | Tokenów/s |")
    print("|---|---|---|---|---|---|")
    models = [E5_SMALL, MINILM] + ([E5_BASE] if "--with-base" in sys.argv else [])
    for model_name in models:
        for device in ("cuda", "cpu"):
            embedder = Embedder(model_name, cache=False)
            try:
                embedder.model.to(device)
            except Exception as exc:                      # no GPU on this machine
                print(f"| {model_name.split('/')[-1]} | {device}: {exc} | | | | |")
                del embedder
                release()
                continue
            chunks = fixed_window_chunks(sections, embedder.tokenizer, window=WINDOW, overlap=0)
            texts = [c.text for c in chunks]
            total = sum(n_tokens(t, embedder.tokenizer) for t in texts)
            t0 = time.perf_counter()
            embedder.embed_passages(texts)
            dt = time.perf_counter() - t0
            print(f"| {model_name.split('/')[-1]} | {device} | {len(chunks)} | {total} | {dt:.1f} | "
                  f"{total / dt:.0f} |", flush=True)
            del embedder
            release()


if __name__ == "__main__":
    main()
