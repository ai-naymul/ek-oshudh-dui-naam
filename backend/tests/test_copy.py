"""All user-facing wording lives in config/copy_bn.json, so a wording change on-site is a JSON edit, not a code change."""
import copy
import json
import os

import pytest
from fastapi.testclient import TestClient

from app.core import graph as g
from app.core.explain_bn import explain, load_copy
from app.core.graph import ROOT
from app.core.rules import Finding

COPY_PATH = os.path.join(ROOT, "config", "copy_bn.json")
SAMPLE = {
    "DUP_INGREDIENT": {"ingredients": ["paracetamol"], "ingredient": "paracetamol", "brands": ["Napa", "Ace"], "doctors": ["Dr A", "Dr B"]},
    "DUP_ASK_CURRENT": {"ingredients": ["paracetamol"], "ingredient": "paracetamol", "brands": ["Napa", "Ace"], "doctors": []},
    "SAME_CLASS": {"group": "PPI", "group_bn": "অ্যাসিড কমানোর ওষুধ", "brands": ["Seclo", "Maxpro"]},
    "DOSE_OVER": {"ingredient": "paracetamol", "total_mg": 4500, "max_mg": 4000, "brands": ["Napa", "Ace"]},
    "RISKY_PAIR": {"note_bn": "একসাথে খেলে কাজ কমতে পারে", "note_en": "may work less well together"},
    "OTC_ONLY": {"brand": "Fexo"},
    "CONFIRM_FIRST": {"brand": "Napa", "source": "rx", "handwritten": True},
    "UNKNOWN": {},
}
SEVERITY = {"DUP_INGREDIENT": "red", "DOSE_OVER": "red", "DUP_ASK_CURRENT": "amber", "SAME_CLASS": "amber", "RISKY_PAIR": "amber"}


def test_copy_file_has_no_banned_phrases():
    text = open(COPY_PATH, encoding="utf-8").read()
    for banned in ("বন্ধ করুন", "খাবেন না", "নিরাপদ", "stop taking", "safe to"):
        assert banned not in text, banned


@pytest.mark.parametrize("rule", sorted(SAMPLE))
def test_every_rule_has_complete_wording(rule):
    out = explain(Finding(rule, SEVERITY.get(rule, "info"), ["M1"], SAMPLE[rule], "test"))
    assert out["title_bn"] and out["bn"] and out["en"] and "{" not in out["bn"] + out["en"]
    if SEVERITY.get(rule) in ("red", "amber") and rule != "DUP_ASK_CURRENT":
        assert load_copy()["ask"]["bn"] in out["bn"]


def test_editing_the_copy_changes_the_message():
    custom = copy.deepcopy(load_copy())
    custom["templates"]["DUP_INGREDIENT"]["bn"] = "পরীক্ষা: {brands} — {ings}"
    out = explain(Finding("DUP_INGREDIENT", "red", ["M1", "M2"], SAMPLE["DUP_INGREDIENT"], "test"), copy=custom)
    assert out["bn"] == "পরীক্ষা: Napa আর Ace — Paracetamol"


@pytest.mark.skipif(not os.path.exists(g.DB_PATH), reason="graph not built")
def test_the_app_gets_its_wording_from_the_same_file():
    from app.main import app
    served = TestClient(app).get("/api/copy").json()
    assert served["ui"] == json.load(open(COPY_PATH, encoding="utf-8"))["ui"]


def test_copy_is_clean_unicode():
    import re
    import unicodedata
    text = open(COPY_PATH, encoding="utf-8").read()
    assert unicodedata.normalize("NFC", text) == text
    assert not re.search("[،​‌‍﻿]", text), "Arabic comma or invisible character in the copy"


def test_same_family_wording_counts_the_brands():
    three = dict(SAMPLE["SAME_CLASS"], brands=["Seclo", "Maxpro", "Pantonix"])
    assert "সবগুলোই" in explain(Finding("SAME_CLASS", "amber", ["M1"], three, "test"))["bn"]
    assert "দুটোই" in explain(Finding("SAME_CLASS", "amber", ["M1"], SAMPLE["SAME_CLASS"], "test"))["bn"]
