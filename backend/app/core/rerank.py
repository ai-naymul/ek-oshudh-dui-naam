"""Rerankers: choose ONE real catalog product from the candidate shortlist (or none).

R1  fuzzy baseline: the top candidate by string score (+ strength/form hints).
R3  constrained AI choice: the model looks at the image again and picks one of the top-k distinct brands, or none.
    It can only answer with an index into our list, so it cannot invent a medicine name (RxLens principle).
R2  (decision model) lives in decide.py.
"""
from __future__ import annotations

from dataclasses import dataclass

from .candidates import Candidate


@dataclass
class Choice:
    candidate: Candidate | None
    confidence: float
    method: str
    detail: dict


def distinct_brands(cands: list[Candidate], k: int) -> list[Candidate]:
    """First candidate of each brand, keeping order, up to k brands."""
    seen, out = set(), []
    for c in cands:
        if c.brand not in seen:
            seen.add(c.brand)
            out.append(c)
        if len(out) == k:
            break
    return out


def r1(cands: list[Candidate]) -> Choice:
    if not cands:
        return Choice(None, 0.0, "R1", {})
    top = cands[0]
    second = next((c for c in cands[1:] if c.brand != top.brand), None)
    margin = top.name_score - (second.name_score if second else 0.0)
    return Choice(top, round(min(1.0, top.name_score), 3), "R1", {"margin": round(margin, 3)})


R3_SCHEMA = {"type": "object", "properties": {"choice": {"type": "integer"}, "confidence": {"type": "number"}},
             "required": ["choice", "confidence"]}


def r3(image_parts: list, cands: list[Candidate], k: int = 5, model: str | None = None) -> Choice:
    """image_parts: Gemini parts for the crop (from app.ai.gemini.image_part). Returns the chosen candidate or None."""
    from app.ai.gemini import LITE_MODEL, generate

    options = distinct_brands(cands, k)
    if not options:
        return Choice(None, 0.0, "R3", {})
    listing = "\n".join(f"{i}. {c.brand}" for i, c in enumerate(options, 1))
    prompt = ("The image shows a medicine name handwritten or printed on a Bangladeshi prescription or strip. "
              f"Which of these registered medicine names is written? Answer with its number, or 0 if none fits.\n{listing}\n"
              "Also give your confidence from 0 to 1.")
    out, meta = generate(image_parts + [{"text": prompt}], model=model or LITE_MODEL, schema=R3_SCHEMA)
    n = int(out.get("choice", 0))
    chosen = options[n - 1] if 1 <= n <= len(options) else None
    return Choice(chosen, float(out.get("confidence", 0.0)), "R3", {"options": [c.brand for c in options], **meta})
