"""API tests with the perception step faked (no network, no API key). The rest of the pipeline is real."""
import io
import os

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core import graph as g

pytestmark = pytest.mark.skipif(not os.path.exists(g.DB_PATH), reason="graph not built")


@pytest.fixture(scope="module")
def client():
    from app.main import app
    return TestClient(app)


def fake_read(lines, kind="prescription", doctor="Dr A"):
    def _read(data):
        img = io.BytesIO()
        Image.new("RGB", (400, 300), "white").save(img, "JPEG")
        return {"kind": kind, "doctor_text": doctor, "date_text": "", "image": img.getvalue(), "size": (400, 300),
                "meta": {"model": "fake"},
                "items": [{"brand_text": b, "alternatives": [], "strength_text": s, "schedule_text": sch,
                           "handwritten": False, "box": [100, 100, 300, 600], "agree": 1.0} for b, s, sch in lines]}
    return _read


def png():
    buf = io.BytesIO()
    Image.new("RGB", (10, 10)).save(buf, "PNG")
    return buf.getvalue()


def test_two_prescriptions_same_medicine_is_red(client, monkeypatch):
    import app.ai.perceive as perceive
    cid = client.post("/api/cases").json()["case_id"]
    monkeypatch.setattr(perceive, "read_image", fake_read([("Napa", "500 mg", "1+1+1")], doctor="Dr A"))
    r1 = client.post(f"/api/cases/{cid}/images", files={"file": ("a.jpg", png(), "image/jpeg")}).json()
    assert r1["items"][0]["chosen"]["brand"] == "Napa"
    monkeypatch.setattr(perceive, "read_image", fake_read([("Ace", "500 mg", "1+0+1")], doctor="Dr B"))
    r2 = client.post(f"/api/cases/{cid}/images", files={"file": ("b.jpg", png(), "image/jpeg")}).json()
    # before the family says both are taken now: the app asks, it does not warn
    first = client.get(f"/api/cases/{cid}/check").json()
    assert [f["rule"] for f in first["findings"] if f["severity"] in ("red", "amber")] == ["DUP_ASK_CURRENT"]
    for it in (r1["items"][0], r2["items"][0]):
        assert client.post(f"/api/cases/{cid}/items/{it['item_id']}/status", json={"taking": "current"}).json()["taking"] == "current"
    res = client.get(f"/api/cases/{cid}/check").json()
    reds = [f for f in res["findings"] if f["rule"] == "DUP_INGREDIENT"]
    assert reds and reds[0]["severity"] == "red"
    assert {m["taking"] for m in res["medicines"]} == {"current"}
    assert "request_id" in res and res["trace"]


def test_status_must_be_one_of_three_words(client):
    cid = client.post("/api/cases").json()["case_id"]
    iid = client.post(f"/api/cases/{cid}/text", json={"text": "Napa 500"}).json()["items"][0]["item_id"]
    assert client.post(f"/api/cases/{cid}/items/{iid}/status", json={"taking": "maybe"}).status_code == 422
    assert client.post(f"/api/cases/{cid}/items/I99/status", json={"taking": "current"}).status_code == 404


def test_typed_names_work_offline(client):
    cid = client.post("/api/cases").json()["case_id"]
    client.post(f"/api/cases/{cid}/text", json={"text": "Seclo 20 1+0+1\nMaxpro 20 0+0+1"})
    res = client.get(f"/api/cases/{cid}/check").json()
    assert any(f["rule"] == "SAME_CLASS" for f in res["findings"])


def test_brand_search_and_random_are_live(client):
    a = client.get("/api/brands/search", params={"q": "Nappa"}).json()
    assert a["options"][0]["brand"] == "Napa" and a["path"]["ingredients"][0]["name"] == "Paracetamol"
    b1, b2 = client.get("/api/brands/random").json(), client.get("/api/brands/random").json()
    assert b1["request_id"] != b2["request_id"]


def test_unknown_case_is_404(client):
    assert client.get("/api/cases/nope/check").status_code == 404


def test_exact_typed_name_is_accepted_but_typo_asks(client):
    cid = client.post("/api/cases").json()["case_id"]
    items = client.post(f"/api/cases/{cid}/text", json={"text": "Seclo 20\nSeclloo 20"}).json()["items"]
    assert items[0]["chosen"]["brand"] == "Seclo" and not items[0]["needs_confirm"]
    assert items[1]["needs_confirm"] and items[1]["options"][0]["brand"] == "Seclo"


def test_expired_case_is_gone(client):
    import app.conversation as conv
    from app.main import engine
    cid = client.post("/api/cases").json()["case_id"]
    engine().cases[cid].created -= conv.TTL_SECONDS + 1
    assert client.get(f"/api/cases/{cid}").status_code == 404 and cid not in engine().cases


def test_stats_are_computed_from_the_registry(client):
    s = client.get("/api/stats").json()
    assert s["products"] == 21363 and s["brand_names"] == 13627
    para = next(e for e in s["examples"] if e["ingredient"] == "Paracetamol")
    assert para["brand_count"] > 100 and "Napa" in para["brands"] and len(para["brands"]) <= 8
    assert s["examples"] == sorted(s["examples"], key=lambda e: -e["brand_count"])
