"""A brand that is not in the registry snapshot: the family types it, and if our registry has no such name the app looks
it up on MedEx (the listing the registry was built from), shows it with its source, and adds it only when the family
taps it. No network here: pages are small made-up snippets shaped like MedEx's."""
import os

import pytest

from app.core import graph as g

PAGE = """<html><h1 class="page-heading-1-l brand"> Newbrand <small class="h1-subtitle" title="Dosage Form">Tablet</small>
<small class="h1-subtitle" title="Dosage Form">Tablet</small></h1>
<div title="Generic Name"> <a href="https://medex.com.bd/generics/1/cetirizine-hydrochloride"> Cetirizine Hydrochloride </a> </div>
<div title="Strength"> 10 mg </div>
<div title="Manufactured by"> <a href="https://medex.com.bd/companies/1/x/brands" class="calm-link"> Example Pharma Ltd. </a></div></html>"""
URL = "https://medex.com.bd/brands/99999/newbrand-10-mg-tablet"


def test_a_medex_brand_page_is_read_into_brand_form_ingredient_strength_and_maker():
    from app.core.web_lookup import parse_brand_page
    assert parse_brand_page(PAGE, URL) == {"brand": "Newbrand", "form": "Tablet", "generic": "Cetirizine Hydrochloride",
                                           "strength": "10 mg", "maker": "Example Pharma Ltd.", "url": URL}
    assert parse_brand_page("<html>not a brand page</html>", URL) is None


def test_lookup_searches_medex_first_then_reads_the_pages(monkeypatch):
    from app.core import web_lookup
    pages = {"https://medex.com.bd/search?search=newbrand": f'<a href="{URL}">x</a>', URL: PAGE}
    monkeypatch.setattr(web_lookup, "_get", lambda url: pages[url])
    out = web_lookup.lookup("newbrand")
    assert out["via"] == "medex" and [r["brand"] for r in out["results"]] == ["Newbrand"]


def test_only_medex_brand_pages_can_be_added():
    from app.core.web_lookup import BRAND_URL
    assert BRAND_URL.fullmatch(URL)
    for bad in ["https://evil.example/brands/1/x", "http://medex.com.bd/brands/1/x", "https://medex.com.bd/generics/1/x",
                "file:///etc/passwd"]:
        assert not BRAND_URL.fullmatch(bad)


@pytest.mark.skipif(not os.path.exists(g.DB_PATH), reason="graph not built")
def test_a_web_brand_the_family_taps_is_a_real_medicine_for_the_rules(monkeypatch, tmp_path):
    # a private copy of the graph: never write into the shared one a running server reads
    import shutil
    db = str(tmp_path / "graph.sqlite")
    shutil.copy(g.DB_PATH, db)
    from fastapi.testclient import TestClient
    import app.main as main
    from app.conversation import Engine
    from app.core import web_lookup
    e = Engine()
    e.graph = g.Graph(db)
    e.rules.g = e.graph
    monkeypatch.setattr(main, "_engine", e, raising=False)
    monkeypatch.setattr(main, "engine", lambda: e)
    monkeypatch.setattr(web_lookup, "_get", lambda url: PAGE)
    client = TestClient(main.app)
    cid = client.post("/api/cases").json()["case_id"]
    client.post(f"/api/cases/{cid}/text", json={"text": "Alatrol 10"})
    new = client.post(f"/api/cases/{cid}/text", json={"text": "Newbrand 10"}).json()["items"][0]
    out = client.post(f"/api/cases/{cid}/items/{new['item_id']}/web", json={"url": URL}).json()
    assert out["chosen"]["brand"] == "Newbrand" and out["chosen"]["web"] == URL and out["needs_confirm"] is False
    for it in client.get(f"/api/cases/{cid}").json()["items"]:
        client.post(f"/api/cases/{cid}/items/{it['item_id']}/status", json={"taking": "current"})
    result = client.get(f"/api/cases/{cid}/check").json()
    assert any(f["rule"] == "DUP_INGREDIENT" for f in result["findings"])      # Alatrol + Newbrand: both cetirizine
    assert client.post(f"/api/cases/{cid}/items/{new['item_id']}/web", json={"url": "https://evil.example/x"}).status_code == 400
