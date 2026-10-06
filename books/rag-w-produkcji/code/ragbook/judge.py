"""LLM-as-judge for faithfulness, plus the local arithmetic you need to calibrate it.

The judge is the cheap model (claude-haiku-4-5), the generator is claude-opus-5: never let a model
grade its own output. Only `judge_faithfulness` needs ANTHROPIC_API_KEY; `agreement` and
`cohen_kappa` are local and run on your own spreadsheet of human labels.
"""
from __future__ import annotations

from collections import Counter

from pydantic import BaseModel, Field

from .answer import JUDGE_MODEL, format_context
from .corpus import Chunk

JUDGE_SYSTEM = """You verify whether an answer is grounded in the fragments it was given.

Work in two steps.
1. Split <answer> into atomic claims. An atomic claim is one verifiable statement: split
   sentences that join two facts, and drop pure meta-text ("nie wiem", "oto odpowiedz").
2. For each claim, decide its verdict against <context> ONLY:
   - "supported": the fragments state it, or it follows from them by simple paraphrase.
   - "contradicted": the fragments state something incompatible with it.
   - "missing": the fragments neither state it nor contradict it. Claims that are true in
     general but absent from the fragments are "missing", not "supported".
   Quote the fragment text you relied on in `evidence`, or leave it empty for "missing".

Judge grounding only. Do not reward a longer answer, do not judge style, do not judge whether
the answer is useful. A refusal that states no facts has no claims and is trivially faithful."""


class ClaimVerdict(BaseModel):
    claim: str = Field(description="One atomic claim from the answer, in its original language")
    verdict: str = Field(description='"supported", "contradicted" or "missing"')
    evidence: str = Field(description="Verbatim fragment text supporting the verdict, empty if missing")


class FaithfulnessReport(BaseModel):
    claims: list[ClaimVerdict]


def judge_faithfulness(client, question: str, answer: str, chunks: list[Chunk],
                       model: str = JUDGE_MODEL) -> FaithfulnessReport:
    """One call, one report. Needs ANTHROPIC_API_KEY."""
    response = client.messages.parse(
        model=model,
        max_tokens=2048,
        system=[{"type": "text", "text": JUDGE_SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content":
                   f"<context>\n{format_context(chunks)}\n</context>\n"
                   f"<question>{question}</question>\n"
                   f"<answer>{answer}</answer>"}],
        output_format=FaithfulnessReport,
    )
    return response.parsed_output


def faithfulness_score(report: FaithfulnessReport) -> float:
    """Supported claims / all claims - the same definition RAGAS uses. An empty answer scores 1.0."""
    if not report.claims:
        return 1.0
    supported = sum(1 for c in report.claims if c.verdict == "supported")
    return supported / len(report.claims)


# --- calibration against human labels (local) ---------------------------------------------

def agreement(human: list[str], judge: list[str]) -> float:
    """Raw agreement: fraction of items on which the two label sets match."""
    if len(human) != len(judge) or not human:
        raise ValueError("label lists must be non-empty and of equal length")
    return sum(1 for h, j in zip(human, judge) if h == j) / len(human)


def cohen_kappa(human: list[str], judge: list[str]) -> float:
    """Cohen's kappa: agreement corrected for the agreement you would get by chance alone.

    Below 0.4 the judge is noise; 0.4-0.6 is usable for comparing versions; above 0.6 you can
    quote the number itself.
    """
    n = len(human)
    po = agreement(human, judge)
    ch, cj = Counter(human), Counter(judge)
    pe = sum((ch[label] / n) * (cj[label] / n) for label in set(ch) | set(cj))
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def confusion(human: list[str], judge: list[str]) -> dict[tuple[str, str], int]:
    """Counts of (human label, judge label) pairs - read it to see which direction the judge drifts."""
    return dict(Counter(zip(human, judge)))
