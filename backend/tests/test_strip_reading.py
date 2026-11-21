"""From the 70-photo strip run (eval/reports/e2_strips.json): the photo reader writes the form in full and in plural
('Napa 500 mg tablets', 'Fast 120 mg/5 ml Suspension', 'Seclo 40 mg Capsules'). Those words must not be matched as
letters of a name: they made the decision model pick Nitalet, Tensicon and Becosules."""
import os

import pytest

from app.core import graph as g
from app.core.candidates import parse_hints


@pytest.mark.parametrize("reading,name,form", [
    ("Napa 500 mg tablets", "napa", "tablet"),
    ("Fast 120 mg/5 ml Suspension", "fast", "suspension"),
    ("Seclo 40 mg Capsules", "seclo", "capsule"),
    ("Flagyl 200 mg/5 ml oral suspension", "flagyl", "suspension"),
    ("Afun 1% Cream", "afun", "cream"),
])
def test_form_words_are_not_part_of_the_name(reading, name, form):
    got = parse_hints(reading)
    assert got[0] == name and got[2] == form


@pytest.mark.skipif(not os.path.exists(g.DB_PATH), reason="graph not built")
@pytest.mark.parametrize("reading,brand", [("Napa 500 mg tablets", "Napa"), ("Fast 120 mg/5 ml Suspension", "Fast"),
                                           ("Seclo 40 mg Capsules", "Seclo")])
def test_printed_strip_readings_rank_the_right_brand_first(reading, brand):
    from app.conversation import Engine
    e = Engine()
    _, ranked = e.decider.rank_reading(e.index, reading, [], e.ppb)
    assert ranked[0][0].brand == brand and ranked[0][1] >= 0.9


def test_reader_agreement_compares_the_names_not_the_whole_line():
    from app.ai.perceive import name_agreement
    assert name_agreement("Seclo 40 mg Capsules", ["Seclo 40"]) == 1.0
    assert name_agreement("Napa 500 mg tablets", ["NAPA"]) == 1.0
    assert name_agreement("Napa", ["Nopa 500"]) < 0.9
    assert name_agreement("Napa", []) == 0.0
