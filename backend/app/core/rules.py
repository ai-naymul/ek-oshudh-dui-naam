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


# What the person has at home: strip/box photos, typed names and spoken names. Prescription lines are "rx".
BAG_SOURCES = ("strip", "text", "voice")


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
    taking: str = "unsure"           # 'current' | 'stopped' | 'unsure': a bag holds old strips, so presence != taken now


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

    @property
    def taking(self) -> str:
        """Taken now if any source says so; stopped only if every source says so; otherwise not known."""
        states = {i.taking for i in self.sources}
        return "current" if "current" in states else "stopped" if states == {"stopped"} else "unsure"

    @property
    def is_combination(self) -> bool:
        return len(self.ingredients) > 1


@dataclass
class Finding:
    rule: str            # DUP_INGREDIENT | DUP_ASK_CURRENT | SAME_CLASS | DOSE_OVER | RISKY_PAIR | OTC_ONLY | CONFIRM_FIRST | UNKNOWN
    severity: str        # red | amber | info
    meds: list[str]
    data: dict
    source: str


# Rule switches (overridden by config/settings.json "rules"): dose limits stay off until a pharmacist reviews them;
# "not on any prescription" is shown as a tag on the medicine, not as a finding.
RULE_DEFAULTS = {"dose_limits": False, "not_on_rx_finding": False}
SEVERITIES = ("red", "amber", "info")


class Rules:
    def __init__(self, graph: Graph, settings: dict | None = None):
        self.settings = {**RULE_DEFAULTS, **(settings or {})}
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
            if it.source in BAG_SOURCES:
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
                first = m.sources[0]
                findings.append(Finding("CONFIRM_FIRST", "info", [m.med_id],
                                        {"brand": m.brand, "source": first.source, "handwritten": first.handwritten},
                                        "reading below the confidence threshold, not yet confirmed by the user"))
        return meds, findings

    # ---------- rules ----------
    def check(self, items: list[Item]) -> tuple[list[Medicine], list[Finding]]:
        meds, findings = self.reconcile(items)
        # confirmed readings only, and never a medicine the family says is no longer taken
        usable = [m for m in meds if m.usable_for_red and m.taking != "stopped"]
        by_ing: dict[str, list[Medicine]] = {}
        for m in usable:
            for ing, _ in m.ingredients:
                by_ing.setdefault(ing, []).append(m)
        findings += self._duplicates(by_ing)
        findings += self._same_family(by_ing)
        if self.settings["dose_limits"]:
            findings += self._dose(by_ing)
        present = set(by_ing)
        for p in self.pairs:
            if p["a"] in present and p["b"] in present:
                ms = sorted({m.med_id for k in (p["a"], p["b"]) for m in by_ing[k]})
                sev = p["severity"] if p["severity"] in SEVERITIES else "amber"
                findings.append(Finding("RISKY_PAIR", sev, ms,
                                        {"a": p["a"], "b": p["b"], "note_en": p["note_en"], "note_bn": p["note_bn"]}, p["source"]))
        if self.settings["not_on_rx_finding"] and any(m.from_rx for m in meds):
            for m in meds:
                if not m.from_rx:
                    findings.append(Finding("OTC_ONLY", "info", [m.med_id], {"brand": m.brand}, "not on any prescription"))
        order = {s: i for i, s in enumerate(SEVERITIES)}
        findings.sort(key=lambda f: (order[f.severity], f.rule))
        return meds, findings

    def _duplicates(self, by_ing: dict[str, list[Medicine]]) -> list[Finding]:
        """One finding per group of medicines sharing ingredients (Napa Extra + Ace Plus share two: one finding).
        Red only when every medicine in the group is taken now; otherwise ask the family first."""
        groups: dict[tuple[str, ...], dict] = {}
        for ing, ms in sorted(by_ing.items()):
            if len(ms) >= 2:
                key = tuple(m.med_id for m in ms)
                groups.setdefault(key, {"meds": ms, "ingredients": []})["ingredients"].append(ing)
        out = []
        for key, grp in groups.items():
            ms = grp["meds"]
            data = {"ingredients": grp["ingredients"], "ingredient": grp["ingredients"][0], "brands": [m.brand for m in ms],
                    "doctors": sorted({d for m in ms for d in m.doctors}),
                    "combination": [m.brand for m in ms if m.is_combination], "taking": [m.taking for m in ms]}
            if all(m.taking == "current" for m in ms):
                out.append(Finding("DUP_INGREDIENT", "red", list(key), data, "registry: brand → ingredient"))
            else:
                out.append(Finding("DUP_ASK_CURRENT", "amber", list(key), data,
                                   "registry: brand → ingredient; waiting for 'taken now' from the family"))
        return out

    def _same_family(self, by_ing: dict[str, list[Medicine]]) -> list[Finding]:
        seen_groups: dict[str, set[str]] = {}
        for ing in by_ing:
            row = self.cls.get(ing)
            if row:
                seen_groups.setdefault(row["group"], set()).add(ing)
        out = []
        for group, ings in sorted(seen_groups.items()):
            if len(ings) >= 2:
                ms = sorted({m.med_id for i in ings for m in by_ing[i]})
                row = self.cls[sorted(ings)[0]]
                out.append(Finding("SAME_CLASS", "amber", ms,
                                   {"group": group, "group_bn": row["group_bn"], "ingredients": sorted(ings),
                                    "brands": sorted({m.brand for i in ings for m in by_ing[i]})},
                                   "curated class_groups.csv"))
        return out

    def _dose(self, by_ing: dict[str, list[Medicine]]) -> list[Finding]:
        """Daily total of one ingredient over solid forms taken now. Liquids (mg per ml) are left out of the sum
        instead of switching the whole check off; a solid medicine without a known schedule means no total."""
        out = []
        for ing, ms in sorted(by_ing.items()):
            limit = self.dose.get(ing)
            if not limit:
                continue
            solid = [m for m in ms if all(mg is not None for i, mg in m.ingredients if i == ing)]
            liquids = [m.brand for m in ms if m not in solid]
            if not solid or any(m.per_day is None for m in solid):
                continue
            total = sum(mg * m.per_day for m in solid for i, mg in m.ingredients if i == ing)
            if total > float(limit["max_daily_mg"]):
                out.append(Finding("DOSE_OVER", "red", [m.med_id for m in solid],
                                   {"ingredient": ing, "total_mg": round(total), "max_mg": int(float(limit["max_daily_mg"])),
                                    "brands": [m.brand for m in solid], "left_out_liquids": liquids},
                                   f"{limit['source_sentence']} ({limit['verified_by']})"))
        return out

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
        if m.unit_price is None or m.per_day is None or any(mg is None for _, mg in m.ingredients):
            return None
        return round(m.unit_price * m.per_day * 30, 2)
