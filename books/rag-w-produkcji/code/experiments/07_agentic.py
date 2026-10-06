"""Chapter 7, part 4: the agentic loop. This is the only script in the chapter that needs a key.

Without ANTHROPIC_API_KEY it still runs: it prints the token budget of a loop with two, three and
four steps, which is the number that decides whether you want this in production at all.

    export ANTHROPIC_API_KEY=...
    ../.venv/bin/python experiments/07_agentic.py "Wiedza firmowa w modelu: dostroic czy RAG?"
"""
from __future__ import annotations

import json
import os
import sys

import tiktoken

from ragbook.agentic import AGENT_SYSTEM, SEARCH_TOOL, iterative_search
from ragbook.corpus import fixed_window_chunks, load_sections
from ragbook.embed import Embedder
from ragbook.store import DenseIndex

PRICE_IN, PRICE_OUT = 5.0, 25.0     # claude-opus-5, USD per million tokens (September 2026)
TOOL_OVERHEAD = 286                 # tool use system prompt, tool_choice auto, claude-opus-5
DEFAULT_QUESTION = "Wiedza firmowa w modelu: dostroić go czy dołożyć wyszukiwanie?"


def budget(steps: int, system_tokens: int, chunk_tokens: int, k: int = 5,
           answer_tokens: int = 250, thinking: int = 120) -> dict:
    """Tokens billed by a loop of `steps` tool calls: every call resends the whole history."""
    prefix = system_tokens + TOOL_OVERHEAD + 40
    history_in = 0
    context = prefix
    output = 0
    for _ in range(steps):
        history_in += context
        output += thinking
        context += thinking + k * chunk_tokens
    history_in += context
    output += answer_tokens
    return {"calls": steps + 1, "input": history_in, "output": output,
            "usd": history_in * PRICE_IN / 1e6 + output * PRICE_OUT / 1e6}


def main() -> None:
    question = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_QUESTION

    enc = tiktoken.get_encoding("o200k_base")
    system_tokens = len(enc.encode(AGENT_SYSTEM)) + len(enc.encode(json.dumps(SEARCH_TOOL)))

    embedder = Embedder()
    sections = load_sections()
    chunks = fixed_window_chunks(sections, embedder.tokenizer, window=128, overlap=32)
    lengths = sorted(len(enc.encode(c.text)) for c in chunks)
    chunk_tokens = lengths[len(lengths) // 2]
    print(f"system prompt + definicja narzędzia: {system_tokens} tokenów o200k_base; "
          f"mediana chunku: {chunk_tokens} tokenów")

    print("\n=== Budżet pętli (claude-opus-5, k=5) ===")
    print("| Kroków wyszukiwania | Wywołań API | Tokeny wejścia | Tokeny wyjścia | Koszt zapytania |")
    print("|---|---|---|---|---|")
    for steps in (1, 2, 3, 4):
        b = budget(steps, system_tokens, chunk_tokens)
        print(f"| {steps} | {b['calls']} | {b['input']} | {b['output']} "
              f"| {b['usd']:.5f} USD |".replace(".", ","))
    single = budget(1, system_tokens, chunk_tokens)
    four = budget(4, system_tokens, chunk_tokens)
    print(f"cztery kroki kosztują {four['usd'] / single['usd']:.1f} raza tyle co jeden "
          f"i {four['calls']} razy dłużej czekasz")

    print(f"\ndefinicja narzędzia: {SEARCH_TOOL['name']}, "
          f"{len(SEARCH_TOOL['description'].split())} słów opisu")
    print(f"system prompt agenta: {len(AGENT_SYSTEM.split())} słów")

    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print("\nANTHROPIC_API_KEY nie jest ustawiony - pętla nie zostanie uruchomiona.")
        return

    from anthropic import Anthropic

    index = DenseIndex(embedder, chunks)

    run = iterative_search(Anthropic(api_key=key), question, index.search, max_steps=4)
    print(f"\npytanie: {question}")
    for i, query in enumerate(run.queries, start=1):
        print(f"  zapytanie {i}: {query}")
    print(f"  kroków: {run.steps}  stop_reason: {run.stop_reason}  "
          f"unikalnych fragmentów: {len(run.chunks)}")
    print(f"  tokeny: {run.input_tokens} wejścia, {run.output_tokens} wyjścia, "
          f"{run.cost_usd(PRICE_IN, PRICE_OUT):.5f} USD")
    print(f"  sekcje: {sorted({(c.chapter, c.section) for c in run.chunks})}")
    print(f"\n{run.answer}")


if __name__ == "__main__":
    main()
