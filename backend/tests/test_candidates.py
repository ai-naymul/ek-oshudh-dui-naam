"""Candidate generation tests: the right brand must be in the shortlist, or no reranker can pick it."""
import os
import random
import time

import pytest

from app.core import graph as g

pytestmark = pytest.mark.skipif(not os.path.exists(g.DB_PATH), reason="graph not built (python -m app.core.graph)")


@pytest.fixture(scope="module")
def idx():
    from app.core.candidates import CandidateIndex
    return CandidateIndex()


def test_recall_at_20_on_synthetic_noise(idx):
    from app.core.noise import corrupt
    rng = random.Random(7)
    sample = rng.sample(idx.brands, 300)
    hits = 0
    for b in sample:
        p = rng.choice(idx.g.products_by_brand(b))
        hits += any(c.brand == b for c in idx.search(corrupt(b, rng, strength=p.strength), 20))
    assert hits / len(sample) >= 0.95


@pytest.mark.parametrize("reading,brand", [("নাপা", "Napa"), ("Tab. Nappa 500", "Napa"), ("ACE PLUS", "Ace Plus"),
                                           ("Napa Extend 665", "Napa Extend"), ("seclo 20", "Seclo"), ("Maxpr0", "Maxpro")])
def test_known_readings_find_the_brand(idx, reading, brand):
    assert any(c.brand == brand for c in idx.search(reading, 20))


def test_look_alikes_both_present(idx):
    brands = {c.brand for c in idx.search("Ace", 20)}
    assert {"Ace", "Ace Plus"} <= brands


def test_strength_hint_ranks_matching_product_first(idx):
    top = idx.search("Napa 500", 20)[0]
    assert top.brand == "Napa" and "500" in top.strength


def test_fast_enough(idx):
    t = time.time()
    for _ in range(50):
        idx.search("Tab. Seclo 20", 20)
    assert (time.time() - t) / 50 < 0.05


@pytest.mark.parametrize("reading,brand,strength", [("Ace 500 1+0+1", "Ace", "500"), ("Napa 500 ১+১+১ ৫ দিন", "Napa", "500"),
                                                     ("Tab. Fexo 120 0+0+1 x 10 days", "Fexo", "120"), ("Seclo 20mg", "Seclo", "20")])
def test_schedule_numbers_are_not_read_as_strength(idx, reading, brand, strength):
    top = idx.search(reading, 20)[0]
    assert top.brand == brand and strength in top.strength and top.form.startswith(("Tablet", "Capsule"))
