"""Reranking: cross-encoders run locally, plus a listwise reranker driven by an LLM.

A bi-encoder (the embedding model) sees the question and the chunk separately; a cross-encoder sees the
pair on one input and returns one relevance score. It cannot be precomputed, so it only ever runs on a
short candidate list produced by the first stage.

Memory: the models here are the biggest thing this book loads. `CrossEncoderReranker.close()` drops the
model and calls the garbage collector; `free_mb()` tells you whether you can afford bge-reranker-v2-m3
(about 2.3 GB resident) before you try.
"""
from __future__ import annotations

import gc
import time
from collections.abc import Sequence

from .corpus import Chunk

MMARCO = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"   # 12 layers, multilingual MS MARCO, ~470 MB
BGE = "BAAI/bge-reranker-v2-m3"                         # XLM-R large, multilingual, ~2.2 GB


def free_mb() -> int:
    """Available memory in MiB, read from /proc/meminfo (the number `free -m` prints as 'available')."""
    with open("/proc/meminfo", encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) // 1024
    return 0


class CrossEncoderReranker:
    def __init__(self, model_name: str = MMARCO, max_length: int = 512, batch_size: int = 16,
                 device: str | None = None):
        from sentence_transformers import CrossEncoder
        self.model_name = model_name
        self.batch_size = batch_size
        self.model = CrossEncoder(model_name, max_length=max_length, device=device)
        self.device = str(self.model.model.device)

    def scores(self, question: str, texts: Sequence[str]) -> list[float]:
        pairs = [(question, t) for t in texts]
        return [float(s) for s in self.model.predict(pairs, batch_size=self.batch_size,
                                                     show_progress_bar=False)]

    def rerank(self, question: str, chunks: Sequence[Chunk], top_k: int = 5) -> list[Chunk]:
        """Reorder `chunks` by cross-encoder score; the first-stage score is kept in meta['stage1']."""
        if not chunks:
            return []
        scores = self.scores(question, [c.text for c in chunks])
        order = sorted(range(len(chunks)), key=lambda i: -scores[i])[:top_k]
        out = []
        for i in order:
            c = chunks[i]
            out.append(Chunk(c.id, c.chapter, c.section, c.text,
                             {**c.meta, "stage1": c.meta.get("score"), "score": scores[i]}))
        return out

    def timed_rerank(self, question: str, chunks: Sequence[Chunk], top_k: int = 5) -> tuple[list[Chunk], float]:
        t0 = time.perf_counter()
        out = self.rerank(question, chunks, top_k)
        return out, time.perf_counter() - t0

    def close(self) -> None:
        self.model = None
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass


# --- Listwise reranking with an LLM ------------------------------------------------------------------

LISTWISE_SYSTEM = (
    "Jesteś komponentem wyszukiwarki dokumentacji technicznej. Dostajesz pytanie i ponumerowane "
    "fragmenty. Uszereguj fragmenty od najbardziej do najmniej przydatnego przy odpowiadaniu na to "
    "pytanie. Nie odpowiadaj na pytanie. Zwróć wyłącznie identyfikatory fragmentów."
)


def build_listwise_prompt(question: str, chunks: Sequence[Chunk], snippet_chars: int = 600) -> str:
    parts = ["<fragmenty>"]
    for i, c in enumerate(chunks):
        body = c.text[:snippet_chars].replace("\n", " ")
        parts.append(f'<fragment id="{i}" rozdzial="{c.chapter}" sekcja="{c.section}">{body}</fragment>')
    parts.append("</fragmenty>")
    parts.append(f"\nPytanie: {question}")
    parts.append(f"Zwróć pole `order`: identyfikatory wszystkich {len(chunks)} fragmentów, "
                 "od najbardziej do najmniej trafnego, bez powtórzeń.")
    return "\n".join(parts)


def llm_rerank(question: str, chunks: Sequence[Chunk], top_k: int = 5,
               model: str = "claude-haiku-4-5", client=None) -> list[Chunk]:
    """Listwise reranking: one call, all candidates in the prompt, a permutation back.

    Needs ANTHROPIC_API_KEY. Structured outputs guarantee that `order` is a list of integers, but not
    that it is a valid permutation, so anything the model leaves out keeps its original position.
    """
    import os

    from anthropic import Anthropic
    from pydantic import BaseModel

    class Ranking(BaseModel):
        order: list[int]

    client = client or Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.parse(
        model=model,
        max_tokens=1024,
        system=LISTWISE_SYSTEM,
        messages=[{"role": "user", "content": build_listwise_prompt(question, chunks)}],
        output_format=Ranking,
    )
    order = [i for i in response.parsed_output.order if 0 <= i < len(chunks)]
    seen = set(order)
    order += [i for i in range(len(chunks)) if i not in seen]
    out = []
    for rank, i in enumerate(order[:top_k], start=1):
        c = chunks[i]
        out.append(Chunk(c.id, c.chapter, c.section, c.text,
                         {**c.meta, "stage1": c.meta.get("score"), "score": 1.0 / rank}))
    return out


def listwise_cost(question: str, chunks: Sequence[Chunk], tokenizer, snippet_chars: int = 600,
                  input_per_mtok: float = 1.0, output_per_mtok: float = 5.0) -> dict:
    """Rough token/cost estimate for one listwise call, counted with any HF tokenizer.

    Default rates are Claude Haiku 4.5 (1 USD per million input tokens, 5 USD per million output).
    """
    prompt = LISTWISE_SYSTEM + "\n" + build_listwise_prompt(question, chunks, snippet_chars)
    n_in = len(tokenizer(prompt, add_special_tokens=False)["input_ids"])
    n_out = 4 * len(chunks) + 8          # `{"order": [12, 3, ...]}` is a handful of tokens per id
    return {"input_tokens": n_in, "output_tokens": n_out,
            "usd": n_in / 1e6 * input_per_mtok + n_out / 1e6 * output_per_mtok}
