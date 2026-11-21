"""Deterministic safety rules over one patient's case.

Input: items read from prescriptions, strips, typed text or voice, each already resolved to a registry product
(or not). Output: findings with an id, a severity, the medicines involved and the source behind the rule.
No AI here: the same case always gives the same findings, which is what the tests check.

Reconciliation: a prescription line and its own strip are ONE medicine. Two prescriptions (different doctors)
that contain the same ingredient are NOT merged: that is exactly the "same medicine from two doctors" case.
"""
from __future__ import annotations

import csv
import os
import re
from dataclasses import dataclass, field

from .graph import ROOT, Graph

CURATED = os.path.join(ROOT, "data", "curated")
SALTS = r"\b(hydrochloride|hcl|sodium|potassium|calcium|magnesium|besilate|besylate|bisulfate|bisulphate|tromethamine|" \
        r"sesquihydrate|trihydrate|dihydrate|monohydrate|maleate|mesylate|succinate|tartrate|fumarate|acetate|" \
        r"dihydrochloride|bromide|citrate|phosphate|sulphate|sulfate|acid)\b"


def base_ingredient(name: str) -> str:
    """'Diclofenac Sodium' -> 'diclofenac', 'Amlodipine Besilate' -> 'amlodipine', 'Mefenamic Acid' -> 'mefenamic'."""
    t = re.sub(SALTS, " ", (name or "").lower())
    t = re.sub(r"\(.*?\)", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _csv(name: str) -> list[dict]:
    path = os.path.join(CURATED, name)
    return list(csv.DictReader(open(path, encoding="utf-8"))) if os.path.exists(path) else []


@dataclass
class Item:
    item_id: str
    source: str                      # 'rx' | 'strip' | 'text' | 'voice'
    doc_id: str                      # which prescription / photo it came from
    product_id: int | None
    confirmed: bool = True           # a handwritten line below the threshold must be confirmed before red rules use it
    handwritten: bool = False
    per_day: float | None = None     # from the prescription schedule or the user
    doctor: str | None = None


@dataclass
class Medicine:
    med_id: str
    product_id: int
    brand: str
    strength: str
    form: str
    unit_price: float | None
    ingredients: list[tuple[str, float | None]]  # (base ingredient, mg per unit)
    sources: list[Item] = field(default_factory=list)
    per_day: float | None = None
    usable_for_red: bool = True

    @property
    def doctors(self) -> list[str]:
        return sorted({i.doctor or i.doc_id for i in self.sources if i.source == "rx"})

    @property
    def from_rx(self) -> bool:
        return any(i.source == "rx" for i in self.sources)


@dataclass
class Finding:
    rule: str            # DUP_INGREDIENT | SAME_CLASS | DOSE_OVER | RISKY_PAIR | OTC_ONLY | CONFIRM_FIRST | UNKNOWN
    severity: str        # red | amber | info
    meds: list[str]
    data: dict
    source: str


class Rules:
    def __init__(self, graph: Graph):
        self.g = graph
        self.dose = {r["ingredient"]: r for r in _csv("dose_limits.csv")}
        self.cls: dict[str, dict] = {}
        for r in _csv("class_groups.csv"):
            self.cls[r["ingredient"]] = r
        self.pairs = _csv("risky_pairs.csv")

    # ---------- reconciliation ----------
    def reconcile(self, items: list[Item]) -> tuple[list[Medicine], list[Finding]]:
        meds: list[Medicine] = []
        findings: list[Finding] = []
        for it in items:
            if it.product_id is None:
                findings.append(Finding("UNKNOWN", "info", [it.item_id], {"source": it.source}, "not found in the registry"))
                continue
            p = self.g.product(it.product_id)
            ings = [(base_ingredient(n), mg) for n, _, mg in self.g.ingredients(p.id)]
            target = None
            if it.source == "strip":
                # a strip joins the prescription line (any doctor) or strip with the same product
                target = next((m for m in meds if m.product_id == p.id), None)
            elif it.source == "rx":
                # a prescription line joins a strip of the same product, never another prescription
                target = next((m for m in meds if m.product_id == p.id and not m.from_rx), None)
            if target:
                target.sources.append(it)
                target.per_day = target.per_day if target.per_day is not None else it.per_day
                target.usable_for_red = target.usable_for_red or it.confirmed
                continue
            meds.append(Medicine(f"M{len(meds) + 1}", p.id, p.brand, p.strength, p.form, p.unit_price, ings, [it],
                                 it.per_day, it.confirmed))
        for m in meds:
            if not m.usable_for_red:
                findings.append(Finding("CONFIRM_FIRST", "info", [m.med_id], {"brand": m.brand},
                                        "handwritten reading below the confidence threshold"))
        return meds, findings

    # ---------- rules ----------
    def check(self, items: list[Item]) -> tuple[list[Medicine], list[Finding]]:
        meds, findings = self.reconcile(items)
        usable = [m for m in meds if m.usable_for_red]
        by_ing: dict[str, list[Medicine]] = {}
        for m in usable:
            for ing, _ in m.ingredients:
                by_ing.setdefault(ing, []).append(m)
        for ing, ms in sorted(by_ing.items()):
            if len(ms) >= 2:
                findings.append(Finding("DUP_INGREDIENT", "red", [m.med_id for m in ms],
                                        {"ingredient": ing, "brands": [m.brand for m in ms],
                                         "doctors": sorted({d for m in ms for d in m.doctors})},
                                        "registry: brand → ingredient"))
        seen_groups: dict[str, set[str]] = {}
        for ing, ms in by_ing.items():
            row = self.cls.get(ing)
            if row:
                seen_groups.setdefault(row["group"], set()).add(ing)
        for group, ings in sorted(seen_groups.items()):
            if len(ings) >= 2:
                ms = sorted({m.med_id for i in ings for m in by_ing[i]})
                row = self.cls[sorted(ings)[0]]
                findings.append(Finding("SAME_CLASS", "amber", ms,
                                        {"group": group, "group_bn": row["group_bn"], "ingredients": sorted(ings),
                                         "brands": sorted({m.brand for i in ings for m in by_ing[i]})},
                                        "curated class_groups.csv"))
        for ing, ms in sorted(by_ing.items()):
            limit = self.dose.get(ing)
            if not limit:
                continue
            if any(m.per_day is None for m in ms) or any(mg is None for m in ms for i, mg in m.ingredients if i == ing):
                continue
            total = sum(mg * m.per_day for m in ms for i, mg in m.ingredients if i == ing)
            if total > float(limit["max_daily_mg"]):
                findings.append(Finding("DOSE_OVER", "red", [m.med_id for m in ms],
                                        {"ingredient": ing, "total_mg": round(total), "max_mg": int(float(limit["max_daily_mg"])),
                                         "brands": [m.brand for m in ms]},
                                        f"{limit['source_sentence']} ({limit['verified_by']})"))
        present = set(by_ing)
        for p in self.pairs:
            if p["a"] in present and p["b"] in present:
                ms = sorted({m.med_id for k in (p["a"], p["b"]) for m in by_ing[k]})
                findings.append(Finding("RISKY_PAIR", p["severity"], ms,
                                        {"a": p["a"], "b": p["b"], "note_en": p["note_en"], "note_bn": p["note_bn"]}, p["source"]))
        if any(m.from_rx for m in meds):
            for m in meds:
                if not m.from_rx:
                    findings.append(Finding("OTC_ONLY", "info", [m.med_id], {"brand": m.brand}, "not on any prescription"))
        order = {"red": 0, "amber": 1, "info": 2}
        findings.sort(key=lambda f: (order[f.severity], f.rule))
        return meds, findings

    # ---------- money ----------
    def cheaper(self, product_id: int, limit: int = 3) -> list[dict]:
        """Same ingredient set, same strength and form, lower listed unit price (information only)."""
        p = self.g.product(product_id)
        if p.unit_price is None:
            return []
        rows = self.g._q("SELECT id, brand, manufacturer, unit_price FROM product WHERE generic = ? AND strength = ? AND form = ? "
                         "AND unit_price IS NOT NULL AND unit_price < ? ORDER BY unit_price LIMIT ?",
                         (p.generic, p.strength, p.form, p.unit_price, limit))
        return [{"product_id": r[0], "brand": r[1], "maker": r[2], "unit_price": r[3]} for r in rows]

    @staticmethod
    def monthly_cost(m: Medicine) -> float | None:
        if m.unit_price is None or m.per_day is None:
            return None
        return round(m.unit_price * m.per_day * 30, 2)
