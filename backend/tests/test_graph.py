"""Knowledge graph tests. They need the downloaded registry (scripts/get_data.sh); CI downloads it first."""
import os

import pytest

from app.core import graph as g

pytestmark = pytest.mark.skipif(not os.path.exists(os.path.join(g.RAW, "medicine.csv")),
                                reason="registry not downloaded (run scripts/get_data.sh)")


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    # Build a private copy: never replace the shared database a running server may be reading.
    path = str(tmp_path_factory.mktemp("graph") / "graph.sqlite")
    stats = g.build(db_path=path)
    return stats, g.Graph(path)


def test_counts_match_dataset(built):
    stats, _ = built
    assert stats["products"] == 21363          # the registry's own rows; local additions are counted apart
    assert stats["brand_names"] == 13627
    assert stats["generics"] == 1508


def test_a_brand_missing_from_the_registry_is_added_from_the_curated_file(built):
    # Candifast SB 65 mg (itraconazole) was on a real prescription and is not in the registry snapshot
    stats, gr = built
    assert stats["local_products"] >= 1
    p = gr.products_by_brand("Candifast SB")
    assert p and (p[0].generic, p[0].strength, p[0].form) == ("Itraconazole", "65 mg", "Capsule")
    assert [n for n, _, _ in gr.ingredients(p[0].id)] == ["Itraconazole"]


def test_every_local_product_names_its_source():
    import csv
    rows = list(csv.DictReader(open(os.path.join(g.ROOT, "data", "curated", "products_local.csv"), encoding="utf-8")))
    assert rows and all(r["source"].startswith("http") and r["generic"] and r["strength"] for r in rows)


def test_brands_map_to_their_ingredient(built):
    _, gr = built
    for brand, ingredient in [("Napa", "Paracetamol"), ("Ace", "Paracetamol"), ("Seclo", "Omeprazole"), ("Maxpro", "Esomeprazole")]:
        names = {n for p in gr.products_by_brand(brand) for n, _, _ in gr.ingredients(p.id)}
        assert ingredient in names, (brand, names)


def test_combination_is_split_with_strengths(built):
    _, gr = built
    p = next(p for p in gr.products_by_brand("Napa Extra") if p.form.startswith("Tablet"))
    ings = {n: (s, mg) for n, s, mg in gr.ingredients(p.id)}
    assert set(ings) == {"Paracetamol", "Caffeine"}
    assert ings["Paracetamol"][1] == 500 and ings["Caffeine"][1] == 65


def test_strength_parsing():
    assert g.to_mg("500 mg") == 500
    assert g.to_mg("1 gm") == 1000
    assert g.to_mg("120 mg/5 ml") is None
    assert g.brand_key(" Napa  Extra ") == "napaextra"


def test_path_explains_brand_to_class(built):
    _, gr = built
    p = next(p for p in gr.products_by_brand("Seclo") if "20" in p.strength)
    path = gr.path(p.id)
    assert path["ingredients"][0]["name"] == "Omeprazole"
    assert path["ingredients"][0]["class"]


@pytest.mark.skipif(not os.path.exists(g.DB_PATH), reason="graph not built")
def test_the_prescription_line_finds_the_added_brand():
    from app.conversation import Engine
    for line in ["Candifast SB 65mg", "Cap. Candifast SB 65 mg", "Candifast"]:
        chosen, *_ = Engine().match(line, [], None, False)
        assert chosen and chosen.brand == "Candifast SB", (line, chosen and chosen.brand)
