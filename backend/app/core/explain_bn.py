"""Bangla (and English) messages built ONLY from rule findings. The AI never writes warnings.

All wording lives in config/copy_bn.json (edit it on-site; it is re-read when the file changes). Every warning ends by
sending the family to a doctor or pharmacist and never tells anyone to stop a medicine; a test scans the file.
"""
from __future__ import annotations

import json
import os
import threading

from .graph import ROOT
from .rules import Finding

COPY_PATH = os.path.join(ROOT, "config", "copy_bn.json")
BN_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")
_cache: dict = {"mtime": None, "data": None}
_lock = threading.Lock()


def load_copy(path: str = COPY_PATH) -> dict:
    """The wording file, re-read only when it changes on disk."""
    mtime = os.path.getmtime(path)
    with _lock:
        if _cache["mtime"] != (path, mtime):
            _cache["data"] = json.load(open(path, encoding="utf-8"))
            _cache["mtime"] = (path, mtime)
        return _cache["data"]


def bn_num(x) -> str:
    return str(x).translate(BN_DIGITS)


def _and(items: list[str], w: dict) -> str:
    return w["and_bn"].join(items) if len(items) <= 2 else w["list_sep_bn"].join(items[:-1]) + w["and_bn"] + items[-1]


def explain(f: Finding, copy: dict | None = None) -> dict:
    c = copy or load_copy()
    w, d = c["words"], f.data
    ask, ask_en = c["ask"]["bn"], c["ask"]["en"]
    key, bn_fields, en_fields = f.rule, {"ask": ask}, {"ask": ask_en}
    if f.rule in ("DUP_INGREDIENT", "DUP_ASK_CURRENT"):
        docs = d.get("doctors") or []
        ings = [i.title() for i in d.get("ingredients") or [d["ingredient"]]]
        two = len(d["brands"]) == 2
        bn_fields.update(brands=_and(d["brands"], w), who=w["who_bn"].format(n=bn_num(len(docs))) if len(docs) >= 2 else "",
                         each=w["each_two_bn"] if two else w["each_many_bn"], ings=_and(ings, w))
        en_fields.update(brands=w["and_en"].join(d["brands"]), each=w["each_two_en"] if two else w["each_many_en"],
                         ings=w["and_en"].join(ings))
    elif f.rule == "SAME_CLASS":
        bn_fields.update(brands=_and(d["brands"], w), group_bn=d["group_bn"])
        en_fields.update(brands=w["and_en"].join(d["brands"]), group=d["group"])
    elif f.rule == "DOSE_OVER":
        many = len(d["brands"]) > 1
        common = dict(total=d["total_mg"], max=d["max_mg"], ingredient=d["ingredient"].title())
        bn_fields.update(common, brands=_and(d["brands"], w), joined=w["together_bn"] if many else w["from_one_bn"],
                         total=bn_num(d["total_mg"]), max=bn_num(d["max_mg"]))
        lead = (w["lead_many_en"] if many else w["lead_one_en"]).format(brands=", ".join(d["brands"]))
        en_fields.update(common, lead=lead)
    elif f.rule == "RISKY_PAIR":
        bn_fields.update(note=d["note_bn"])
        en_fields.update(note=d["note_en"].capitalize())
    elif f.rule == "OTC_ONLY":
        bn_fields.update(brand=d["brand"])
        en_fields.update(brand=d["brand"])
    elif f.rule == "CONFIRM_FIRST":
        src = d.get("source")
        kind = "voice" if src == "voice" else "text" if src == "text" else "handwritten" if d.get("handwritten", True) else "photo"
        key = f"CONFIRM_FIRST.{kind}"
        bn_fields.update(brand=d["brand"])
        en_fields.update(brand=d["brand"])
    t = c["templates"][key]
    title = c["titles"][f.rule]
    return {"rule": f.rule, "severity": f.severity, "title_bn": title["bn"], "title_en": title["en"],
            "bn": t["bn"].format(**bn_fields), "en": t["en"].format(**en_fields), "source": f.source, "meds": f.meds}
