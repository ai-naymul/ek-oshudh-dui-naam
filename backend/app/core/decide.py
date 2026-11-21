"""R2: the small decision model. Scores (reading, candidate brand) pairs with a LightGBM classifier.

Features are explainable string and context signals; the model only ranks candidates that already exist in the
catalog, so it can never invent a medicine. Trained by training/train_decider.py; loaded from models/decider.txt.
"""
from __future__ import annotations

import math
import os

import jellyfish
from rapidfuzz import fuzz
from rapidfuzz.distance import JaroWinkler

from .candidates import Candidate, parse_hints
from .graph import ROOT, brand_key

MODEL_PATH = os.path.join(ROOT, "models", "decider.txt")
FEATURES = ["name_score", "edit", "jaro", "partial", "phonetic", "first_letter", "len_ratio", "rank", "margin",
            "alt_hits", "strength_match", "form_match", "log_products", "is_top"]


def brand_rows(cands: list[Candidate]) -> list[Candidate]:
    seen, out = set(), []
    for c in cands:
        if c.brand not in seen:
            seen.add(c.brand)
            out.append(c)
    return out


def gather(index, reading: str, alternatives: list[str], k: int = 20) -> tuple[list[Candidate], list[set[str]]]:
    """Candidates for a reading plus its n-best alternatives (same code in training and in the app: no skew).
    Returns the merged candidate list and, per alternative, the set of brands it retrieved (feature alt_hits)."""
    cands = index.search(reading, k)
    seen = {c.product_id for c in cands}
    alt_sets = []
    for alt in [a for a in alternatives if a and a.strip().lower() != reading.strip().lower()][:3]:
        found = index.search(alt, k)
        alt_sets.append({c.brand for c in found})
        for c in found:
            if c.product_id not in seen:
                cands.append(c)
                seen.add(c.product_id)
    return cands, alt_sets


def features(reading: str, alternatives: list[str], cands: list[Candidate], alt_brands: list[set[str]],
             products_per_brand: dict[str, int]) -> list[tuple[Candidate, list[float]]]:
    name, _, _ = parse_hints(reading)
    rk = brand_key(name)
    brands = brand_rows(cands)
    scores = [c.name_score for c in brands]
    out = []
    for i, c in enumerate(brands):
        bk = brand_key(c.brand)
        nxt = max((s for j, s in enumerate(scores) if j != i), default=0.0)
        out.append((c, [
            c.name_score,
            fuzz.ratio(rk, bk) / 100,
            JaroWinkler.similarity(rk, bk) if rk and bk else 0.0,
            fuzz.partial_ratio(rk, bk) / 100 if rk and bk else 0.0,
            float(bool(rk) and jellyfish.metaphone(rk) == jellyfish.metaphone(bk)),
            float(bool(rk) and bool(bk) and rk[0] == bk[0]),
            min(len(rk), len(bk)) / max(len(rk), len(bk), 1),
            float(i + 1),
            c.name_score - nxt,
            float(sum(c.brand in s for s in alt_brands)),
            float(c.strength_match),
            float(c.form_match),
            math.log1p(products_per_brand.get(c.brand, 1)),
            float(i == 0),
        ]))
    return out


class Decider:
    def __init__(self, path: str = MODEL_PATH):
        import lightgbm as lgb
        self.model = lgb.Booster(model_file=path)

    def rank_reading(self, index, reading: str, alternatives: list[str], products_per_brand: dict[str, int]):
        """-> (all candidates, [(best product of each brand, probability)] sorted high to low)."""
        cands, alt_sets = gather(index, reading, alternatives)
        return cands, self.rank(features(reading, alternatives, cands, alt_sets, products_per_brand))

    def rank(self, feats: list[tuple[Candidate, list[float]]]) -> list[tuple[Candidate, float]]:
        if not feats:
            return []
        probs = self.model.predict([f for _, f in feats])
        return sorted(((c, float(p)) for (c, _), p in zip(feats, probs)), key=lambda x: -x[1])

    @staticmethod
    def available(path: str = MODEL_PATH) -> bool:
        return os.path.exists(path)


def products_per_brand(graph) -> dict[str, int]:
    """How many registry products carry each brand name (feature log_products)."""
    counts: dict[str, int] = {}
    for (brand,) in graph._q("SELECT brand FROM product"):
        counts[brand] = counts.get(brand, 0) + 1
    return counts
