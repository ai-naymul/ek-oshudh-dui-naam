"""'Currently taking' gate and rule settings.

A medicine bag holds old strips and old prescriptions, so being in the bag does not mean being taken now.
A duplicate turns red only when every medicine involved is marked as taken now; otherwise the app asks.
Products come from the real registry (brand + strength + form)."""
import os

import pytest

from app.core import graph as g
from app.core.rules import Item, Rules

pytestmark = pytest.mark.skipif(not os.path.exists(g.DB_PATH), reason="graph not built")


@pytest.fixture(scope="module")
def graph():
    return g.Graph()


def pid(graph, brand, strength=None, form="Tablet"):
    ps = [p for p in graph.products_by_brand(brand) if strength is None or strength in p.strength]
    ps = [p for p in ps if p.form.startswith(form)] or ps
    assert ps, brand
    return ps[0].id


def rx(graph, i, brand, taking="unsure", strength=None, form="Tablet", per_day=None, doc="Rx1"):
    return Item(f"I{i}", "rx", doc, pid(graph, brand, strength, form), per_day=per_day, doctor=doc, taking=taking)


def bag(graph, i, brand, taking="unsure", strength=None, form="Tablet", per_day=None):
    return Item(f"S{i}", "strip", f"photo{i}", pid(graph, brand, strength, form), per_day=per_day, taking=taking)


def fired(findings):
    return {(f.rule, f.severity) for f in findings}


def test_duplicate_is_red_when_both_are_taken_now(graph):
    _, f = Rules(graph).check([rx(graph, 1, "Napa", "current", "500"), bag(graph, 2, "Ace", "current", "500")])
    assert ("DUP_INGREDIENT", "red") in fired(f)


def test_duplicate_with_unknown_status_asks_instead_of_warning(graph):
    _, f = Rules(graph).check([rx(graph, 1, "Napa", strength="500"), bag(graph, 2, "Ace", strength="500")])
    assert ("DUP_INGREDIENT", "red") not in fired(f)
    ask = [x for x in f if x.rule == "DUP_ASK_CURRENT"]
    assert ask and ask[0].severity == "amber" and ask[0].data["ingredients"] == ["paracetamol"]


def test_stopped_medicine_is_left_out(graph):
    _, f = Rules(graph).check([rx(graph, 1, "Napa", "current", "500"), bag(graph, 2, "Ace", "stopped", "500")])
    assert not [x for x in f if x.rule in ("DUP_INGREDIENT", "DUP_ASK_CURRENT")]


def test_combination_pair_gives_one_finding_listing_every_shared_ingredient(graph):
    _, f = Rules(graph).check([rx(graph, 1, "Napa Extra", "current"), bag(graph, 2, "Ace Plus", "current")])
    dups = [x for x in f if x.rule == "DUP_INGREDIENT"]
    assert len(dups) == 1
    assert set(dups[0].data["ingredients"]) == {"paracetamol", "caffeine"}
    assert sorted(dups[0].data["combination"]) == ["Ace Plus", "Napa Extra"]


def test_dose_limit_rule_is_off_by_default(graph):
    items = [rx(graph, 1, "Napa", "current", "500", per_day=6), bag(graph, 2, "Ace", "current", "500", per_day=4)]
    assert "DOSE_OVER" not in {x.rule for x in Rules(graph).check(items)[1]}
    assert "DOSE_OVER" in {x.rule for x in Rules(graph, {"dose_limits": True}).check(items)[1]}


def test_a_syrup_does_not_switch_off_the_tablet_dose_check(graph):
    items = [rx(graph, 1, "Napa", "current", "500", per_day=10),
             bag(graph, 2, "Napa", "current", "120", form="Syrup", per_day=3)]
    f = Rules(graph, {"dose_limits": True}).check(items)[1]
    over = [x for x in f if x.rule == "DOSE_OVER"]
    assert over and over[0].data["total_mg"] == 5000


def test_not_on_prescription_is_not_a_finding_by_default(graph):
    _, f = Rules(graph).check([rx(graph, 1, "Napa", "current", "500"), bag(graph, 2, "Seclo", "current", "20", form="Capsule")])
    assert "OTC_ONLY" not in {x.rule for x in f}


def test_unknown_severity_in_a_curated_table_does_not_crash(graph):
    r = Rules(graph)
    r.pairs = [{"a": "paracetamol", "b": "omeprazole", "severity": "high", "note_en": "x", "note_bn": "x", "source": "test"}]
    _, f = r.check([rx(graph, 1, "Napa", "current", "500"), bag(graph, 2, "Seclo", "current", "20", form="Capsule")])
    assert [x.severity for x in f if x.rule == "RISKY_PAIR"] == ["amber"]
