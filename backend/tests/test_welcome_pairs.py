"""The welcome screen's moving example shows the pairs from the story first (config/settings.json 'welcome_pairs').
Nothing is typed by hand: the shared ingredient and the number of brands are looked up in the registry, and a pair
that does not share an ingredient is left out."""
import os

import pytest

from app.core import graph as g

pytestmark = pytest.mark.skipif(not os.path.exists(g.DB_PATH), reason="graph not built")


def test_the_story_pairs_come_first_with_their_shared_ingredient():
    from app.main import _registry_stats
    ex = _registry_stats()["examples"]
    assert [(e["ingredient"], e["brands"][:2]) for e in ex[:3]] == [
        ("Paracetamol", ["Napa", "Ace"]), ("Cetirizine", ["Alatrol", "Atrizin"]), ("Esomeprazole", ["Exium", "Sergel"])]
    assert ex[1]["brand_count"] >= 80
    assert len({e["ingredient"] for e in ex}) == len(ex)          # no ingredient twice


def test_a_pair_that_does_not_share_an_ingredient_is_left_out():
    from app.main import featured_examples
    by = {"Paracetamol": {"Napa": 3, "Ace": 2}, "Omeprazole": {"Seclo": 2}}
    assert featured_examples([["Napa", "Seclo"], ["Napa", "Nobrand"]], by) == []
    assert featured_examples([["Napa", "Ace"]], by)[0]["ingredient"] == "Paracetamol"
