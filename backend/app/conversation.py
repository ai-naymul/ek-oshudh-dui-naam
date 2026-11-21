"""One patient's case: everything the web app, the agent and the MCP server share.

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
from app.core.candidates import Candidate, CandidateIndex, parse_hints
from app.core.decide import Decider, products_per_brand
from app.core.graph import ROOT, Graph, brand_key
from app.core.rerank import distinct_brands, r1, r3
from app.core.rules import Item, Rules
from app.core.schedule import parse as parse_schedule
from app.core.settings import DEFAULTS as SETTINGS_DEFAULTS, _merge, load_settings

POLICY_PATH = os.path.join(ROOT, "models", "policy.json")
DEFAULT_POLICY = {"method": "R1+R3", "r1_accept": 0.85, "r1_margin": 0.10, "r2_accept": 0.98, "agree_min": None,
                  "note": "default until E1/R2 sets thresholds"}
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
    agent: dict | None = None     # the resolver's suggestion for an unclear item (still needs the user's tap)
    taking: str = "unsure"        # current | stopped | unsure, set by the family; red duplicates need 'current'


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
    def __init__(self, settings: dict | None = None):
        self.settings = load_settings() if settings is None else _merge(SETTINGS_DEFAULTS, settings)
        self.graph = Graph()
        self.index = CandidateIndex(self.graph)
        self.rules = Rules(self.graph, self.settings["rules"])
        self.policy = load_policy()
        if self.settings["matching"]["auto_accept_threshold"] is not None:
            self.policy["r2_accept"] = float(self.settings["matching"]["auto_accept_threshold"])
        self.decider = None
        if self.policy.get("method", "").startswith("R2") and Decider.available():
            self.decider = Decider()
            self.ppb = products_per_brand(self.graph)
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
        if case and time.time() - case.created > TTL_SECONDS:   # expired: forget it now, not only on the next new case
            with self.lock:
                self.cases.pop(case_id, None)
            case = None
        if not case:
            raise KeyError(case_id)
        return case

    # ---------- matching ----------
    def _options(self, cands: list[Candidate], k: int = 3) -> list[dict]:
        return [{"product_id": c.product_id, "brand": c.brand, "strength": c.strength, "form": c.form,
                 "maker": c.manufacturer, "generic": c.generic, "score": round(c.name_score, 3)}
                for c in distinct_brands(cands, k)]

    def match(self, reading: str, alternatives: list[str], crop_parts: list | None, handwritten: bool) -> tuple:
        """-> (chosen product or None, confidence, method, needs_confirm, candidates in display order).
        With settings matching.always_confirm every reading waits for the family's tap."""
        chosen, conf, method, confirm, cands = self._match(reading, alternatives, crop_parts, handwritten)
        return chosen, conf, method, confirm or bool(self.settings["matching"]["always_confirm"]), cands

    def _match(self, reading: str, alternatives: list[str], crop_parts: list | None, handwritten: bool) -> tuple:
        if self.decider is not None:
            return self._match_r2(reading, alternatives, crop_parts, exact_ok=not handwritten)
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

    def _match_r2(self, reading: str, alternatives: list[str], crop_parts: list | None, exact_ok: bool = False) -> tuple:
        """Shipped policy from E1 (models/policy.json): accept when the decision model is sure; otherwise ask the
        constrained AI to pick from the model's top-5 and accept only if it independently agrees; else ask the user.
        exact_ok (typed names, printed strips/boxes): the threshold was calibrated on handwriting, so for these an
        exact registry brand name is accepted as written; anything fuzzier still follows the policy."""
        cands, ranked = self.decider.rank_reading(self.index, reading, alternatives, self.ppb)
        if not ranked:
            return None, 0.0, "none", True, []
        order = [c for c, _ in ranked] + [c for c in cands if c.brand not in {x.brand for x, _ in ranked}]
        top, p = ranked[0]
        if p >= self.policy["r2_accept"]:
            return top, round(p, 3), "R2", False, order
        if exact_ok and brand_key(parse_hints(reading)[0]) == brand_key(top.brand):
            return top, round(p, 3), "exact name", False, order
        if crop_parts:
            third = r3(crop_parts, [c for c, _ in ranked[:5]], k=5)
            agree_min = self.policy.get("agree_min")
            if third.candidate and third.candidate.brand == top.brand and agree_min is not None and p >= agree_min:
                return top, round(p, 3), "R2+R3 agree", False, order
            if third.candidate and third.candidate.brand == top.brand:  # agree, but the policy still wants a tap
                return top, round(p, 3), "R2+R3 agree, confirm", True, order
            if third.candidate:  # disagreement: show the AI's pick first, but the user decides
                order = [third.candidate] + [c for c in order if c.brand != third.candidate.brand]
                return third.candidate, round(p, 3), "R2/R3 disagree", True, order
        return top, round(p, 3), "R2 unsure", True, order

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

    def add_voice(self, case: Case, data: bytes, mime: str) -> dict:
        """Voice note -> transcript (shown verbatim) -> medicine mentions -> catalog matcher. Spoken brand names are
        short and easy to mishear (e.g. 'Ace'), so every spoken item waits for the user's one-tap confirmation."""
        from app.ai.speech import audio_to_text, mentions
        t0 = time.time()
        transcript, meta = audio_to_text(data, mime)
        case.step("transcribe", t0, model=meta.get("model"), chars=len(transcript))
        t1 = time.time()
        found, meta2 = mentions(transcript)
        case.step("extract", t1, mentions=len(found), model=meta2.get("model"))
        new = []
        for m in found:
            t2 = time.time()
            said, latin = (m.get("name_as_said") or "").strip(), (m.get("name_english_letters") or "").strip()
            reading = " ".join(x for x in (latin or said, m.get("strength_text", "")) if x)
            alts = [a for a in (said, latin) if a and a != (latin or said)]
            sched_text = m.get("schedule_text", "") or ""
            sched = parse_schedule(sched_text)
            chosen, conf, method, _, cands = self.match(reading, alts, None, False)
            ci = CaseItem(f"I{len(case.items) + 1}", "voice", "voice", said or latin, alts, m.get("strength_text", ""),
                          sched_text, False, None, self._options(cands), chosen.product_id if chosen else None,
                          round(conf, 3), method, True, sched.per_day, sched.to_dict(), None)
            case.items.append(ci)
            new.append(ci)
            case.step("match", t2, item=ci.item_id, reading=reading, method=method, confidence=ci.confidence,
                      chosen=self.options_brand(ci))
        return {"transcript": transcript, "items": [self.item_view(i) for i in new]}

    def speech(self, case: Case) -> tuple[bytes, str, str]:
        from app.ai.speech import findings_speech, speak_bn
        result = self.check(case)
        text = findings_speech(result["findings"])
        t0 = time.time()
        audio, mime, meta = speak_bn(text)
        case.step("speak", t0, model=meta.get("model"), chars=len(text))
        return audio, mime, text

    def set_status(self, case: Case, item_id: str, taking: str) -> dict:
        """The family says whether this medicine is taken now, stopped, or not known."""
        it = next(i for i in case.items if i.item_id == item_id)
        it.taking = taking
        case.step("status", time.time(), item=item_id, taking=taking)
        return self.item_view(it)

    def resolve(self, case: Case, item_id: str) -> dict:
        """Ask the agent to look for evidence for one unclear item. It can only reorder the options and explain;
        the item still waits for the user's confirmation."""
        from app.agent.resolver import safe_resolve
        it = next(i for i in case.items if i.item_id == item_id)
        t0 = time.time()
        out = safe_resolve(self, case, it)
        case.step("agent", t0, item=item_id, tools=[s["tool"] for s in out.get("steps", [])], grounded=out.get("grounded"),
                  suggestion=self.graph.product(out["product_id"]).brand if out.get("product_id") else None)
        if out.get("product_id"):
            pid = out["product_id"]
            p = self.graph.product(pid)
            first = {"product_id": pid, "brand": p.brand, "strength": p.strength, "form": p.form,
                     "maker": p.manufacturer, "generic": "", "score": 1.0}
            it.options = [first] + [o for o in it.options if o["brand"] != p.brand][:2]
            it.agent = {"product_id": pid, "brand": p.brand, "reason_bn": out["reason_bn"],
                        "tools": [s["tool"] for s in out["steps"]]}
        else:
            it.agent = {"product_id": None, "brand": None, "reason_bn": "", "tools": [s["tool"] for s in out.get("steps", [])]}
        return self.item_view(it)

    def confirm(self, case: Case, item_id: str, product_id: int | None, per_day: float | None = None) -> dict:
        it = next(i for i in case.items if i.item_id == item_id)
        it.product_id, it.needs_confirm, it.method = product_id, False, "user"
        if per_day is not None:
            it.per_day = per_day
        return self.item_view(it)

    # ---------- check ----------
    def check(self, case: Case) -> dict:
        t0 = time.time()
        items = [Item(i.item_id, i.source, i.doc_id, i.product_id,
                      confirmed=not i.needs_confirm, handwritten=i.handwritten, per_day=i.per_day, doctor=i.doctor,
                      taking=i.taking)
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
                "options": it.options, "schedule": it.schedule, "per_day": it.per_day, "has_crop": it.crop is not None,
                "agent": it.agent, "doctor": it.doctor, "taking": it.taking}
