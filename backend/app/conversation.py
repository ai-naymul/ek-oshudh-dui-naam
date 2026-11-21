"""One patient's case, channel-free (web and WhatsApp both use this).

photo/text -> perceive -> candidates -> matching policy -> items to confirm -> rules -> Bangla findings.
Cases live in memory only (images are never written to disk) and expire after two hours.
Every step is timed into a trace that the Proof screen shows.
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field

from app.core import explain_bn
from app.core.candidates import Candidate, CandidateIndex
from app.core.graph import ROOT, Graph
from app.core.rerank import distinct_brands, r1, r3
from app.core.rules import Item, Rules
from app.core.schedule import parse as parse_schedule

POLICY_PATH = os.path.join(ROOT, "models", "policy.json")
DEFAULT_POLICY = {"method": "R1+R3", "r1_accept": 0.85, "r1_margin": 0.10, "note": "default until E1/R2 sets thresholds"}
TTL_SECONDS = 2 * 3600


def load_policy() -> dict:
    if os.path.exists(POLICY_PATH):
        return {**DEFAULT_POLICY, **json.load(open(POLICY_PATH, encoding="utf-8"))}
    return dict(DEFAULT_POLICY)


@dataclass
class CaseItem:
    item_id: str
    doc_id: str
    source: str                   # rx | strip | text
    reading: str
    alternatives: list[str]
    strength_text: str
    schedule_text: str
    handwritten: bool
    agree: float | None
    options: list[dict]           # top-3 catalog products for the confirm screen
    product_id: int | None
    confidence: float
    method: str
    needs_confirm: bool
    per_day: float | None
    schedule: dict
    doctor: str | None
    crop: bytes | None = None


@dataclass
class Case:
    case_id: str
    created: float = field(default_factory=time.time)
    items: list[CaseItem] = field(default_factory=list)
    docs: list[dict] = field(default_factory=list)
    trace: list[dict] = field(default_factory=list)

    def step(self, name: str, t0: float, **info) -> None:
        self.trace.append({"step": name, "ms": round((time.time() - t0) * 1000, 1), **info})


class Engine:
    def __init__(self):
        self.graph = Graph()
        self.index = CandidateIndex(self.graph)
        self.rules = Rules(self.graph)
        self.policy = load_policy()
        self.cases: dict[str, Case] = {}
        self.lock = threading.Lock()

    # ---------- case store ----------
    def new_case(self) -> Case:
        with self.lock:
            now = time.time()
            for cid in [c for c, v in self.cases.items() if now - v.created > TTL_SECONDS]:
                del self.cases[cid]
            case = Case(uuid.uuid4().hex[:10])
            self.cases[case.case_id] = case
            return case

    def get(self, case_id: str) -> Case:
        case = self.cases.get(case_id)
        if not case:
            raise KeyError(case_id)
        return case

    # ---------- matching ----------
    def _options(self, cands: list[Candidate], k: int = 3) -> list[dict]:
        return [{"product_id": c.product_id, "brand": c.brand, "strength": c.strength, "form": c.form,
                 "maker": c.manufacturer, "generic": c.generic, "score": round(c.name_score, 3)}
                for c in distinct_brands(cands, k)]

    def match(self, reading: str, alternatives: list[str], crop_parts: list | None, handwritten: bool) -> tuple:
        cands = self.index.search(reading, 20)
        seen = {c.product_id for c in cands}
        for alt in alternatives[:3]:
            for c in self.index.search(alt, 20):
                if c.product_id not in seen:
                    cands.append(c)
                    seen.add(c.product_id)
        if not cands:
            return None, 0.0, "none", True, []
        first = r1(cands)
        sure = first.confidence >= self.policy["r1_accept"] and first.detail.get("margin", 0) >= self.policy["r1_margin"]
        if sure and not handwritten:
            return first.candidate, first.confidence, "R1", False, cands
        if crop_parts:
            third = r3(crop_parts, cands, k=5)
            if third.candidate and third.candidate.brand == first.candidate.brand and sure:
                return third.candidate, max(first.confidence, third.confidence), "R1+R3 agree", False, cands
            if third.candidate:
                return third.candidate, third.confidence, "R3", True, cands
        return first.candidate, first.confidence, "R1", True, cands

    # ---------- inputs ----------
    def add_image(self, case: Case, data: bytes) -> dict:
        from app.ai.gemini import image_part
        from app.ai.perceive import crop, read_image
        t0 = time.time()
        read = read_image(data)
        doc_id = f"D{len(case.docs) + 1}"
        source = "rx" if read["kind"] == "prescription" else "strip"
        case.step("perceive", t0, doc=doc_id, kind=read["kind"], lines=len(read["items"]), model=read["meta"].get("model"))
        case.docs.append({"doc_id": doc_id, "kind": read["kind"], "doctor": read.get("doctor_text") or doc_id})
        new = []
        for it in read["items"]:
            t1 = time.time()
            c = crop(read["image"], it.get("box"))
            parts = [image_part(c, "image/jpeg")] if c else None
            text = " ".join(x for x in (it.get("brand_text", ""), it.get("strength_text", ""), it.get("form_text", "")) if x)
            chosen, conf, method, confirm, cands = self.match(text, it.get("alternatives", []), parts, bool(it.get("handwritten")))
            sched = parse_schedule(" ".join(x for x in (it.get("schedule_text", ""), it.get("meal_text", ""), it.get("duration_text", "")) if x))
            ci = CaseItem(f"I{len(case.items) + 1}", doc_id, source, it.get("brand_text", ""), it.get("alternatives", []),
                          it.get("strength_text", ""), it.get("schedule_text", ""), bool(it.get("handwritten")), it.get("agree"),
                          self._options(cands), chosen.product_id if chosen else None, round(conf, 3), method, confirm,
                          sched.per_day, sched.to_dict(), read.get("doctor_text") or doc_id, c)
            case.items.append(ci)
            new.append(ci)
            case.step("match", t1, item=ci.item_id, reading=ci.reading, method=method, confidence=ci.confidence,
                      chosen=self.options_brand(ci))
        return {"doc_id": doc_id, "kind": read["kind"], "items": [self.item_view(i) for i in new]}

    def add_text(self, case: Case, text: str) -> dict:
        """Typed or spoken lines, e.g. 'Napa 500 1+0+1'. Works offline: no model call at all."""
        new = []
        for line in [l.strip() for l in text.replace("،", "\n").split("\n") if l.strip()]:
            t0 = time.time()
            sched = parse_schedule(line)
            chosen, conf, method, confirm, cands = self.match(line, [], None, False)
            ci = CaseItem(f"I{len(case.items) + 1}", "typed", "text", line, [], "", line, False, None, self._options(cands),
                          chosen.product_id if chosen else None, round(conf, 3), method, confirm, sched.per_day,
                          sched.to_dict(), None)
            case.items.append(ci)
            new.append(ci)
            case.step("match", t0, item=ci.item_id, reading=line, method=method, confidence=ci.confidence,
                      chosen=self.options_brand(ci))
        return {"items": [self.item_view(i) for i in new]}

    def confirm(self, case: Case, item_id: str, product_id: int | None, per_day: float | None = None) -> dict:
        it = next(i for i in case.items if i.item_id == item_id)
        it.product_id, it.needs_confirm, it.method = product_id, False, "user"
        if per_day is not None:
            it.per_day = per_day
        return self.item_view(it)

    # ---------- check ----------
    def check(self, case: Case) -> dict:
        t0 = time.time()
        items = [Item(i.item_id, i.source if i.source != "text" else "strip", i.doc_id, i.product_id,
                      confirmed=not i.needs_confirm, handwritten=i.handwritten, per_day=i.per_day, doctor=i.doctor)
                 for i in case.items]
        meds, findings = self.rules.check(items)
        case.step("rules", t0, findings=len(findings))
        out_meds = []
        for m in meds:
            out_meds.append({"med_id": m.med_id, "brand": m.brand, "strength": m.strength, "form": m.form,
                             "path": self.graph.path(m.product_id), "per_day": m.per_day, "from_rx": m.from_rx,
                             "doctors": m.doctors, "monthly_cost": Rules.monthly_cost(m),
                             "cheaper": self.rules.cheaper(m.product_id), "items": [s.item_id for s in m.sources]})
        return {"case_id": case.case_id, "medicines": out_meds, "findings": [explain_bn.explain(f) for f in findings],
                "trace": case.trace[-40:], "policy": self.policy}

    # ---------- views ----------
    def options_brand(self, it: CaseItem) -> str | None:
        return self.graph.product(it.product_id).brand if it.product_id else None

    def item_view(self, it: CaseItem) -> dict:
        chosen = None
        if it.product_id:
            p = self.graph.product(it.product_id)
            chosen = {"product_id": p.id, "brand": p.brand, "strength": p.strength, "form": p.form, "maker": p.manufacturer}
        return {"item_id": it.item_id, "doc_id": it.doc_id, "source": it.source, "reading": it.reading,
                "alternatives": it.alternatives, "handwritten": it.handwritten, "agree": it.agree, "chosen": chosen,
                "confidence": it.confidence, "method": it.method, "needs_confirm": it.needs_confirm,
                "options": it.options, "schedule": it.schedule, "per_day": it.per_day, "has_crop": it.crop is not None}
