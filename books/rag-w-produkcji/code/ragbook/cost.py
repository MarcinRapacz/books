"""Cost model for one RAG query. Prices from platform.claude.com/docs/en/about-claude/pricing (September 2026).

Everything is USD per million tokens. `cache_read` is the price of a prompt-cache hit, `cache_write_5m`
the price of writing the 5-minute cache (1.25x base input).
"""
from __future__ import annotations

from dataclasses import dataclass

MTOK = 1_000_000

PRICES = {
    #                    input  cache_write_5m  cache_read  output
    "claude-opus-5":    (5.00,  6.25,           0.50,       25.00),
    "claude-haiku-4-5": (1.00,  1.25,           0.10,        5.00),
}


@dataclass
class QueryCost:
    model: str
    input_tokens: int
    output_tokens: int
    cached_tokens: int = 0
    cache_write_tokens: int = 0

    @property
    def parts(self) -> dict[str, float]:
        base, write, read, out = PRICES[self.model]
        return {
            "input": self.input_tokens * base / MTOK,
            "cache_write": self.cache_write_tokens * write / MTOK,
            "cache_read": self.cached_tokens * read / MTOK,
            "output": self.output_tokens * out / MTOK,
        }

    @property
    def total(self) -> float:
        return sum(self.parts.values())

    def per_1k_queries(self) -> float:
        return self.total * 1000


def prompt_tokens(system_tokens: int, chunk_tokens: int, k: int, question_tokens: int,
                  overhead_per_chunk: int = 12) -> int:
    """System prompt + k chunks (each wrapped in its own tag with a source line) + the question."""
    return system_tokens + k * (chunk_tokens + overhead_per_chunk) + question_tokens
