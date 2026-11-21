"""Case tools the signature flow needs: the same prescription twice, local spellings, remove, AI readiness, the sample."""
import os

import pytest
from fastapi.testclient import TestClient

from app.core import graph as g

pytestmark = pytest.mark.skipif(not os.path.exists(g.DB_PATH), reason="graph not built")


@pytest.fixture(scope="module")
def client():
    from app.main import app
    return TestClient(app)


def test_the_same_prescription_photographed_twice_is_not_added_again(client, monkeypatch):
    import app.ai.perceive as perceive
    from tests.test_api import fake_read
    from tests.test_robustness import jpg
    monkeypatch.setattr(perceive, "read_image", fake_read([("Napa", "500 mg", "1+0+1"), ("Seclo", "20 mg", "0+0+1")], doctor="Dr A"))
    cid = client.post("/api/cases").json()["case_id"]
    first = client.post(f"/api/cases/{cid}/images", files={"file": ("a.jpg", jpg(), "image/jpeg")}).json()
    again = client.post(f"/api/cases/{cid}/images", files={"file": ("a.jpg", jpg(), "image/jpeg")}).json()
    assert again["duplicate_of"] == first["doc_id"] and again["items"] == []
    assert len(client.get(f"/api/cases/{cid}").json()["items"]) == 2
    forced = client.post(f"/api/cases/{cid}/images", params={"allow_repeat": "true"},
                         files={"file": ("a.jpg", jpg(), "image/jpeg")}).json()
    assert len(forced["items"]) == 2


def test_local_spelling_file_adds_aliases_and_ignores_unknown_targets(tmp_path):
    from app.core.candidates import CandidateIndex
    path = tmp_path / "aliases_local.csv"
    path.write_text("alias,brand,note\nবড় নাপা,Napa Extra,test\nজাদুর বড়ি,No Such Brand,test\n", encoding="utf-8")
    idx = CandidateIndex(g.Graph(), local_aliases_csv=str(path))
    assert idx.search("বড় নাপা ৫০০")[0].brand == "Napa Extra"
    assert "জাদুর বড়ি" not in idx.bn_alias


def test_a_bangla_alias_still_matches_with_strength_and_schedule_after_it():
    from app.core.candidates import CandidateIndex
    idx = CandidateIndex(g.Graph())
    assert idx.search("নাপা ৫০০ ১+০+১")[0].brand == "Napa"


def test_remove_an_item(client):
    cid = client.post("/api/cases").json()["case_id"]
    items = client.post(f"/api/cases/{cid}/text", json={"text": "Napa 500\nSeclo 20"}).json()["items"]
    assert client.delete(f"/api/cases/{cid}/items/{items[0]['item_id']}").status_code == 200
    assert [i["item_id"] for i in client.get(f"/api/cases/{cid}").json()["items"]] == [items[1]["item_id"]]
    assert client.delete(f"/api/cases/{cid}/items/{items[0]['item_id']}").status_code == 404


def test_health_says_whether_the_ai_can_be_reached(client, monkeypatch):
    h = client.get("/api/health").json()
    assert h["registry"]["products"] == 21363 and "key_present" in h["ai"]
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert client.get("/api/health").json()["ai"]["key_present"] is False


def test_sample_case_is_built_live_from_the_settings_lines(client):
    r = client.post("/api/cases/sample").json()
    assert r["sample"] is True and len(r["items"]) >= 2
    assert any(i["source"] == "rx" for i in r["items"]) and any(i["source"] != "rx" for i in r["items"])
    chk = client.get(f"/api/cases/{r['case_id']}/check").json()
    assert any(f["rule"] in ("DUP_ASK_CURRENT", "DUP_INGREDIENT") for f in chk["findings"])


def test_network_addresses_for_opening_on_a_phone(client):
    urls = client.get("/api/network").json()["urls"]
    assert isinstance(urls, list) and all(u.startswith("http://") and u.count(":") == 2 for u in urls)
    assert not any("127.0.0.1" in u or "localhost" in u for u in urls)


@pytest.mark.skipif(not os.path.exists(g.DB_PATH), reason="graph not built")
def test_the_welcome_number_is_the_raw_test_accuracy_not_the_audited_one():
    import json
    from app.main import app
    policy = json.load(open(os.path.join(g.ROOT, "models", "policy.json")))
    ev = TestClient(app).get("/api/stats").json()["eval"]
    assert ev["top1"] == policy["top1_test"]["R2"]
    assert ev["top1_audited"] == policy["top1_test_audited"]["R2"]
