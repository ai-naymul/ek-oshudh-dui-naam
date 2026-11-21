"""Findings of the 21 Nov clinical-safety review, each pinned by a test: no false reassurance, no false alarms that
would make a family drop a medicine, no instruction hidden in a source line, and the agent only suggests what its own
tools found."""
import csv
import os

import pytest

from app.core import graph as g
from app.core.rules import CURATED, Item, Rules, base_ingredient

pytestmark = pytest.mark.skipif(not os.path.exists(g.DB_PATH), reason="graph not built")


@pytest.fixture(scope="module")
def graph():
    return g.Graph()


def pid(graph, brand, strength=None, form="Tablet"):
    ps = [p for p in graph.products_by_brand(brand) if strength is None or strength == p.strength or strength in p.strength]
    ps = [p for p in ps if p.form.startswith(form)] or ps
    assert ps, brand
    return ps[0].id


def item(graph, i, brand, strength=None, form="Tablet", source="rx", doc="Rx1", taking="current", confirmed=True):
    return Item(f"I{i}", source, doc, pid(graph, brand, strength, form), confirmed=confirmed, doctor=doc if source == "rx" else None,
                taking=taking)


def rules_of(findings):
    return {(f.rule, f.severity) for f in findings}


def test_one_prescription_with_two_strengths_is_not_a_red_duplicate(graph):
    _, f = Rules(graph).check([item(graph, 1, "Farin", "5 mg"), item(graph, 2, "Farin", "1 mg")])
    assert ("DUP_INGREDIENT", "red") not in rules_of(f)
    assert ("DUP_SAME_RX", "amber") in rules_of(f)


def test_two_doctors_with_the_same_drug_are_still_red(graph):
    _, f = Rules(graph).check([item(graph, 1, "Farin", "5 mg", doc="Dr A"), item(graph, 2, "Farin", "1 mg", doc="Dr B")])
    assert ("DUP_INGREDIENT", "red") in rules_of(f)


def test_eye_drops_and_a_tablet_of_the_same_drug_are_not_a_duplicate(graph):
    _, f = Rules(graph).check([item(graph, 1, "Anfenac", form="Ophthalmic"), item(graph, 2, "Clofenac", "50 mg", doc="Dr B")])
    assert not [x for x in f if x.rule in ("DUP_INGREDIENT", "DUP_ASK_CURRENT", "DUP_SAME_RX")]


def test_mineral_salts_keep_their_names():
    assert base_ingredient("Potassium Citrate") == "potassium citrate"
    assert base_ingredient("Calcium Acetate") == "calcium acetate"
    assert base_ingredient("Potassium Chloride") == "potassium chloride"
    assert base_ingredient("Calcium Carbonate [Elemental Calcium]") == "calcium carbonate"
    assert base_ingredient("Diclofenac Sodium") == "diclofenac"


def test_different_mineral_salts_are_not_called_the_same_medicine(graph):
    _, f = Rules(graph).check([item(graph, 1, "Urilit"), item(graph, 2, "Lofos", doc="Dr B")])
    assert not [x for x in f if x.rule.startswith("DUP")]


def test_an_unclear_line_does_not_disappear_into_a_confirmed_strip(graph):
    _, f = Rules(graph).check([item(graph, 1, "Napa", "500", source="strip", doc="photo1"),
                               item(graph, 2, "Napa", "500", confirmed=False)])
    assert ("CONFIRM_FIRST", "info") in rules_of(f)


def test_no_cheaper_switch_suggested_for_narrow_therapeutic_drugs(graph):
    assert Rules(graph).cheaper(pid(graph, "Farin", "5 mg")) == []


def test_source_lines_carry_citations_not_instructions():
    for row in csv.DictReader(open(os.path.join(CURATED, "risky_pairs.csv"), encoding="utf-8")):
        assert "avoid" not in row["source"].lower() and "do not" not in row["source"].lower()


def test_a_check_with_unconfirmed_lines_says_it_is_partial():
    from app.conversation import Engine
    e = Engine()
    case = e.new_case()
    e.add_text(case, "Napa 500")
    e.add_text(case, "Nqpz")
    case.items[-1].needs_confirm = True
    assert e.check(case)["unchecked"] == 1


def test_speech_does_not_reassure_when_lines_are_unchecked():
    from app.ai.speech import findings_speech
    text = findings_speech([], unchecked=2)
    assert "বড় কোনো সমস্যা পাওয়া যায়নি" not in text and "২" in text


def test_agent_suggestion_must_come_from_its_own_tools(monkeypatch):
    import app.agent.resolver as r
    from app.conversation import Engine
    e = Engine()
    case = e.new_case()
    e.add_text(case, "Nap")
    it = case.items[-1]
    it.needs_confirm = True
    first_option = it.options[0]["product_id"]
    monkeypatch.setattr(r, "chat", lambda contents, tools, model: (
        {"role": "model", "parts": [{"functionCall": {"name": "answer", "args": {"product_id": first_option, "reason_bn": "এটাই"}}}]}, {}))
    assert e.resolve(case, it.item_id)["agent"]["product_id"] is None


@pytest.mark.parametrize("reason", ["এটা বাদ দিন।", "একটা খেলেই হবে।", "কোনো সমস্যা নেই।", "বন্ধ করে দিন।"])
def test_agent_reasons_that_sound_like_advice_are_dropped(reason):
    from app.agent.resolver import Resolver
    out = Resolver._finish({"product_id": 7, "reason_bn": reason}, {7}, [{"tool": "check_bag"}])
    assert out["product_id"] is None


def test_photo_line_needs_reader_agreement_for_an_exact_name(monkeypatch):
    import app.conversation as conv
    from app.ai.gemini import GeminiError
    from app.conversation import Engine

    def down(*a, **k):
        raise GeminiError("off")
    monkeypatch.setattr(conv, "r3", down)
    e = Engine()
    e.policy = {**e.policy, "r2_accept": 1.01}     # the decision model alone never accepts: only the exact-name path can
    unsure = e.match("Seclo 20", [], [{}], False, agree=0.5)
    sure = e.match("Seclo 20", [], [{}], False, agree=1.0)
    assert unsure[3] is True and sure[3] is False


def test_an_unconfirmed_medicine_is_listed_as_not_checked():
    from app.conversation import Engine
    e = Engine()
    case = e.new_case()
    e.add_text(case, "Seclo 20")
    e.add_text(case, "Napa 500")
    case.items[-1].needs_confirm = True
    meds = {m["brand"]: m for m in e.check(case)["medicines"]}
    assert meds["Seclo"]["checked"] is True
    assert meds["Napa"]["checked"] is False and meds["Napa"]["cheaper"] == []
