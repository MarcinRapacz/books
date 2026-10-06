"""Cost of query transformations: how many extra tokens each one sends and gets back.

Input = the real prompt from `ragbook.queries`, filled with a real golden-set question.
Output = the JSON the model would have to return, built from the hand-written variants in
`data/query_variants.jsonl`. Token counts come from the e5 tokenizer (a local approximation -
the billed number comes from `client.messages.count_tokens`, tom 1, rozdział 2), prices from
the Claude pricing page for `claude-haiku-4-5` (1 USD / MTok in, 5 USD / MTok out).

Run from the `code/` directory:  ../.venv/bin/python experiments/04_cost.py
"""
from __future__ import annotations

import json

from ragbook.embed import Embedder
from ragbook.evaluate import load_golden
from ragbook.queries import (DECOMPOSE_PROMPT, HYDE_PROMPT, REWRITE_PROMPT, SELF_QUERY_PROMPT,
                             STEP_BACK_PROMPT, load_variants)
from ragbook.routing import ROUTER_PROMPT

IN_PRICE, OUT_PRICE = 1.0, 5.0  # USD / 1M tokens, claude-haiku-4-5, wrzesień 2026


def main() -> None:
    golden = {q.id: q for q in load_golden()}
    variants = load_variants()
    tokenizer = Embedder().tokenizer

    def count(text: str) -> int:
        return len(tokenizer(text, add_special_tokens=False)["input_ids"])

    def avg(values) -> float:
        values = list(values)
        return sum(values) / len(values)

    ids = sorted(variants)
    comparative = [qid for qid in ids if variants[qid].get("subquestions")]

    def prompt_tokens(template: str, subset=ids) -> float:
        return avg(count(template.format(question=golden[qid].question, n=2)) for qid in subset)

    rows = [
        ("query rewriting (2 warianty)", 1,
         prompt_tokens(REWRITE_PROMPT),
         avg(count(json.dumps({"queries": variants[qid]["rewrite"]}, ensure_ascii=False)) for qid in ids),
         3),
        ("HyDE", 1,
         prompt_tokens(HYDE_PROMPT),
         avg(count(json.dumps({"answer": variants[qid]["hyde"]}, ensure_ascii=False)) for qid in ids),
         1),
        ("step-back", 1,
         prompt_tokens(STEP_BACK_PROMPT),
         avg(count(json.dumps({"question": variants[qid]["rewrite"][0]}, ensure_ascii=False)) for qid in ids),
         2),
        ("dekompozycja (pytania porównawcze)", 1,
         prompt_tokens(DECOMPOSE_PROMPT, comparative),
         avg(count(json.dumps({"subquestions": variants[qid]["subquestions"]}, ensure_ascii=False))
             for qid in comparative),
         2),
        ("self-query (filtr z pytania)", 1,
         prompt_tokens(SELF_QUERY_PROMPT),
         avg(count(json.dumps({"chapter": 10, "kind": None, "query": golden[qid].question},
                              ensure_ascii=False)) for qid in ids),
         1),
        ("routing intencji (LLM)", 1,
         prompt_tokens(ROUTER_PROMPT),
         avg(count(json.dumps({"route": "local", "reason": "Pytanie o konkretny parametr API."},
                              ensure_ascii=False)) for qid in ids),
         1),
    ]

    print("| Technika | Wywołań LLM | Tokeny wejścia | Tokeny wyjścia | USD / 1000 zapytań | Retrievali |")
    print("|---|---|---|---|---|---|")
    for name, calls, tin, tout, searches in rows:
        usd = 1000 * (tin * IN_PRICE + tout * OUT_PRICE) / 1e6
        print(f"| {name} | {calls} | {tin:.0f} | {tout:.0f} | {usd:.2f} | {searches} |".replace(".", ","))

    total_in = sum(r[2] for r in rows[:2]) + rows[5][2]
    total_out = sum(r[3] for r in rows[:2]) + rows[5][3]
    usd = 1000 * (total_in * IN_PRICE + total_out * OUT_PRICE) / 1e6
    print(f"\nRouting + multi-query + HyDE razem: {total_in:.0f} tokenów wejścia, "
          f"{total_out:.0f} wyjścia, {usd:.2f} USD na 1000 zapytań.".replace(f"{usd:.2f}", f"{usd:.2f}".replace(".", ",")))
    print("Dla porównania sam prompt RAG z pięcioma fragmentami po 128 tokenów to około 900 tokenów "
          "wejścia, czyli 0,90 USD na 1000 zapytań na tym samym modelu i ponad 4 USD na Claude Opus 5.")


if __name__ == "__main__":
    main()
