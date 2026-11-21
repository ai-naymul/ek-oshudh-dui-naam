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
    client.post(f"/api/cases/{cid}/images", files={"file": ("b.jpg", png(), "image/jpeg")})
    res = client.get(f"/api/cases/{cid}/check").json()
    reds = [f for f in res["findings"] if f["rule"] == "DUP_INGREDIENT"]
    assert reds and reds[0]["severity"] == "red"
    assert "request_id" in res and res["trace"]


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
