"""A lotion or eye drop is used, not eaten: the status question says ব্যবহার করছেন for those, খাচ্ছেন for the rest."""
import json
import os

import pytest

from app.core import graph as g

pytestmark = pytest.mark.skipif(not os.path.exists(g.DB_PATH), reason="graph not built")
COPY = os.path.join(os.path.dirname(__file__), "..", "..", "config", "copy_bn.json")


def _first(graph, form_like):
    pid = graph._q("SELECT id FROM product WHERE form LIKE ? LIMIT 1", (form_like,))[0][0]
    return pid


def test_items_and_medicines_say_whether_they_are_applied():
    from app.conversation import Engine
    e = Engine()
    case = e.new_case()
    e.add_text(case, "Napa 500")
    lotion = _first(e.graph, "%Lotion%")
    case.items[0].product_id = lotion
    assert e.item_view(case.items[0])["chosen"]["applied"] is True
    case.items[0].product_id = _first(e.graph, "Tablet")
    assert e.item_view(case.items[0])["chosen"]["applied"] is False
    meds = e.check(case)["medicines"]
    assert meds and meds[0]["applied"] is False


def test_the_used_not_eaten_wording_exists():
    ui = json.load(open(COPY, encoding="utf-8"))["ui"]
    assert ui["status.label_applied"] == "এখন ব্যবহার করছেন?"
    assert ui["status.current_applied"] == "এখন ব্যবহার করছেন"
