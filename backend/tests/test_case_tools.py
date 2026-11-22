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


# Real readings of ONE photo differ a little each time (21 Nov test with a real prescription: "Triocim" one read,
# "Triscim" the next), so an exact comparison let the same prescription in twice and every line turned into a
# false "same medicine twice".
RX_DUTTA = [("Napa Extend", "665 mg", "1+1+1"), ("Triocim", "400 mg", "1+0+1"), ("Remmo", "20 mg", "1+0+1"),
            ("Motigut", "10 mg", "1+0+1")]


def _photo(client, monkeypatch, cid, lines, doctor, date):
    import app.ai.perceive as perceive
    from tests.test_api import fake_read
    from tests.test_robustness import jpg
    monkeypatch.setattr(perceive, "read_image", fake_read(lines, doctor=doctor, date=date))
    return client.post(f"/api/cases/{cid}/images", files={"file": ("a.jpg", jpg(), "image/jpeg")}).json()


@pytest.mark.parametrize("lines,doctor,date", [
    ([("Napa Extend", "665mg", "1-1-1"), ("Triscim", "400mg", "1-0-1"), ("Remmo", "20mg", "1-0-1"),
      ("Motigut", "10mg", "1-0-1")], "Dr Hiranmoy Dutta MBBS", "10/06/2025"),     # letters and formats differ
    (RX_DUTTA, "ডাঃ হিরন্ময় দত্ত", ""),                                           # doctor read in Bangla, no date
    (RX_DUTTA[:2], "Dr. Hiranmoy Dutta", "Jun 10, 2025"),                          # a closer photo of the top half
    (RX_DUTTA, "Dr. Hiranmoy Dutta", "18 Jun 2020"),       # a stamped date misread (day and year digits), same month
])
def test_the_same_prescription_read_a_little_differently_is_still_caught(client, monkeypatch, lines, doctor, date):
    cid = client.post("/api/cases").json()["case_id"]
    first = _photo(client, monkeypatch, cid, RX_DUTTA, "Dr. Hiranmoy Dutta", "Jun 10, 2025")
    again = _photo(client, monkeypatch, cid, lines, doctor, date)
    assert again["duplicate_of"] == first["doc_id"] and again["items"] == []


def test_a_new_visit_with_the_same_medicines_is_not_called_a_repeat(client, monkeypatch):
    cid = client.post("/api/cases").json()["case_id"]
    _photo(client, monkeypatch, cid, RX_DUTTA, "Dr. Hiranmoy Dutta", "Jun 10, 2025")
    later = _photo(client, monkeypatch, cid, RX_DUTTA, "Dr. Hiranmoy Dutta", "28.09.2026")
    assert later["duplicate_of"] is None and len(later["items"]) == 4


def test_a_different_prescription_from_the_same_doctor_is_not_a_repeat(client, monkeypatch):
    cid = client.post("/api/cases").json()["case_id"]
    _photo(client, monkeypatch, cid, RX_DUTTA, "Dr. Ayub Nabi", "")
    other = _photo(client, monkeypatch, cid, [("Exium", "20 mg", "1+0+1"), ("Alatrol", "10 mg", "0+0+1"),
                                              ("Napa Extend", "665 mg", "1+0+1"), ("Calamine", "", "")], "Dr. Ayub Nabi", "")
    assert other["duplicate_of"] is None


@pytest.mark.parametrize("text,parsed", [
    ("Jun 10, 2025", (10, 6, 25)), ("10/06/2025", (10, 6, 25)), ("18/5/25", (18, 5, 25)), ("18 SEP 2026", (18, 9, 26)),
    ("10.08.2026", (10, 8, 26)), ("১০.০৮.২০২৬", (10, 8, 26)), ("24 JUN 2025", (24, 6, 25)), ("", None), ("Date:", None),
])
def test_prescription_dates_in_the_formats_doctors_write(text, parsed):
    from app.conversation import _parse_date
    assert _parse_date(text) == parsed
