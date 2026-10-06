"""Last step of the baseline pipeline: turn retrieved chunks into a prompt and ask the model.

Needs ANTHROPIC_API_KEY. Everything above this module (chunking, retrieval, metrics) runs offline;
this is the only place that costs money, which is why the book measures retrieval separately.

    cd code && ../.venv/bin/python -m ragbook.generate "Po co normalizować embeddingi?"
"""
from __future__ import annotations

import os

from .corpus import Chunk

MODEL = "claude-opus-5"
FALLBACK = "BRAK PODSTAWY W KORPUSIE."

SYSTEM = (
    "You answer questions about the book 'AI Engineer' using only the excerpts given to you. "
    "Answer in Polish, in at most three sentences."
)
INSTRUCTIONS = (
    "Answer the question using only the documents above. After every claim put the source id in "
    f"square brackets. If the documents do not contain the answer, reply exactly: {FALLBACK}"
)


def build_prompt(question: str, chunks: list[Chunk]) -> str:
    """Documents first, question last, XML delimiters - the layout from volume 1, chapter 3."""
    documents = "\n".join(
        f'  <document index="{i}">\n'
        f'    <source>rozdz. {c.chapter} / {c.section or "(wstęp)"}</source>\n'
        f"    <document_content>{c.text}</document_content>\n  </document>"
        for i, c in enumerate(chunks, start=1)
    )
    return f"<documents>\n{documents}\n</documents>\n\n{INSTRUCTIONS}\n\nQuestion: {question}"


def answer(question: str, chunks: list[Chunk], model: str = MODEL) -> str:
    from anthropic import Anthropic

    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    message = client.messages.create(
        model=model,
        max_tokens=512,
        system=SYSTEM,
        messages=[{"role": "user", "content": build_prompt(question, chunks)}],
    )
    return next(b.text for b in message.content if b.type == "text")


if __name__ == "__main__":
    import sys

    from .corpus import fixed_window_chunks, load_sections
    from .embed import Embedder
    from .store import DenseIndex

    question = sys.argv[1] if len(sys.argv) > 1 else "Po co normalizować embeddingi?"
    embedder = Embedder()
    index = DenseIndex(embedder, fixed_window_chunks(load_sections(), embedder.tokenizer, 128, 32))
    hits = index.search(question, k=5)
    print(build_prompt(question, hits)[:600], "...\n")
    print(answer(question, hits))
