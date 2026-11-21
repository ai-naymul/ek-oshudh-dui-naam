"""Golden cases for the deterministic rules. Products are looked up by brand + strength + form from the real registry."""
import os

import pytest

from app.core import explain_bn
from app.core import graph as g
from app.core.rules import Item, Rules, base_ingredient

pytestmark = pytest.mark.skipif(not os.path.exists(g.DB_PATH), reason="graph not built")


@pytest.fixture(scope="module")
def rules():
    return Rules(g.Graph())


def pid(rules, brand, strength=None, form="Tablet"):
    ps = [p for p in rules.g.products_by_brand(brand) if (strength is None or strength in p.strength)]
    ps = [p for p in ps if p.form.startswith(form)] or ps
    assert ps, brand
    return ps[0].id


def rx(rules, i, brand, per_day=None, doc="Rx1", strength=None, form="Tablet", confirmed=True, taking="current"):
    return Item(f"I{i}", "rx", doc, pid(rules, brand, strength, form), confirmed=confirmed, per_day=per_day, doctor=doc,
                taking=taking)


def strip(rules, i, brand, strength=None, form="Tablet", taking="current"):
    return Item(f"S{i}", "strip", f"photo{i}", pid(rules, brand, strength, form), taking=taking)


def rules_fired(findings):
    return {(f.rule, f.severity) for f in findings}


def test_base_ingredient():
    assert base_ingredient("Diclofenac Sodium") == "diclofenac"
    assert base_ingredient("Amlodipine Besilate") == "amlodipine"
    assert base_ingredient("Fexofenadine Hydrochloride") == "fexofenadine"


def test_napa_plus_ace_is_red(rules):
    _, f = rules.check([rx(rules, 1, "Napa", strength="500"), rx(rules, 2, "Ace", strength="500", doc="Rx2")])
    dup = [x for x in f if x.rule == "DUP_INGREDIENT"]
    assert dup and dup[0].severity == "red" and dup[0].data["ingredient"] == "paracetamol"
    assert dup[0].data["doctors"] == ["Rx1", "Rx2"]


def test_combination_napa_extra_plus_ace_is_red(rules):
    _, f = rules.check([rx(rules, 1, "Napa Extra"), rx(rules, 2, "Ace", strength="500")])
    assert any(x.rule == "DUP_INGREDIENT" and x.data["ingredient"] == "paracetamol" for x in f)


def test_seclo_plus_maxpro_is_amber(rules):
    _, f = rules.check([rx(rules, 1, "Seclo", strength="20", form="Capsule"), rx(rules, 2, "Maxpro", strength="20", form="Capsule")])
    assert ("SAME_CLASS", "amber") in rules_fired(f)
    assert ("DUP_INGREDIENT", "red") not in rules_fired(f)


def test_paracetamol_4500mg_is_red_when_dose_limits_are_switched_on(rules):
    _, f = Rules(rules.g, {"dose_limits": True}).check([rx(rules, 1, "Napa", per_day=6, strength="500"), rx(rules, 2, "Ace", per_day=3, strength="500")])
    over = [x for x in f if x.rule == "DOSE_OVER"]
    assert over and over[0].data["total_mg"] == 4500 and over[0].data["max_mg"] == 4000


def test_prescription_and_its_own_strip_are_one_medicine(rules):
    meds, f = rules.check([rx(rules, 1, "Napa", strength="500"), strip(rules, 2, "Napa", strength="500")])
    assert len(meds) == 1 and not any(x.rule == "DUP_INGREDIENT" for x in f)


def test_bag_only_item_is_flagged_otc_when_that_setting_is_on(rules):
    _, f = Rules(rules.g, {"not_on_rx_finding": True}).check([rx(rules, 1, "Seclo", strength="20", form="Capsule"), strip(rules, 2, "Fexo", strength="120")])
    assert ("OTC_ONLY", "info") in rules_fired(f)


def test_unconfirmed_handwriting_never_turns_red(rules):
    _, f = rules.check([rx(rules, 1, "Napa", strength="500"), rx(rules, 2, "Ace", strength="500", doc="Rx2", confirmed=False)])
    assert ("DUP_INGREDIENT", "red") not in rules_fired(f)
    assert ("CONFIRM_FIRST", "info") in rules_fired(f)


def test_unknown_product_is_reported_not_guessed(rules):
    _, f = rules.check([Item("I1", "rx", "Rx1", None)])
    assert [x.rule for x in f] == ["UNKNOWN"]


def test_clean_case_has_no_warnings(rules):
    _, f = rules.check([rx(rules, 1, "Seclo", strength="20", form="Capsule"), rx(rules, 2, "Fexo", strength="120")])
    assert not [x for x in f if x.severity in ("red", "amber")]


def test_explanations_never_say_stop_or_safe(rules):
    _, f = Rules(rules.g, {"dose_limits": True, "not_on_rx_finding": True}).check([rx(rules, 1, "Napa", per_day=6, strength="500"), rx(rules, 2, "Ace", per_day=3, strength="500", doc="Rx2"),
                        rx(rules, 3, "Seclo", strength="20", form="Capsule"), rx(rules, 4, "Maxpro", strength="20", form="Capsule")])
    texts = " ".join(explain_bn.explain(x)["bn"] for x in f) + open(explain_bn.COPY_PATH, encoding="utf-8").read()
    for banned in ("বন্ধ করুন", "খাবেন না", "নিরাপদ"):
        assert banned not in texts
    ask = explain_bn.load_copy()["ask"]["bn"]
    assert all(ask in explain_bn.explain(x)["bn"] for x in f if x.severity == "red")
