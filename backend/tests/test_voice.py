"""Voice path with the speech models faked (no network). Matching, rules and templates are real."""
import os

import pytest
from fastapi.testclient import TestClient

from app.core import graph as g
from app.core.explain_bn import explain
from app.core.rules import Finding

pytestmark = pytest.mark.skipif(not os.path.exists(g.DB_PATH), reason="graph not built")


@pytest.fixture(scope="module")
def client():
    from app.main import app
    return TestClient(app)


def fake_voice(monkeypatch, transcript, items):
    import app.ai.speech as speech
    monkeypatch.setattr(speech, "audio_to_text", lambda data, mime: (transcript, {"model": "fake"}))
    monkeypatch.setattr(speech, "mentions", lambda text: (items, {"model": "fake"}))

    def fake_hear(data, mime):
        if mime.split(";")[0].strip().lower() not in speech.AUDIO_TYPES:
            raise ValueError(f"unsupported audio type {mime}")
        return transcript, items, {"model": "fake", "fallback": False}
    monkeypatch.setattr(speech, "hear", fake_hear)


def test_spoken_medicines_are_matched_but_wait_for_confirmation(client, monkeypatch):
    fake_voice(monkeypatch, "আমি নাপা পাঁচশো দিনে দুইবার খাই", [
        {"name_as_said": "নাপা", "name_english_letters": "Napa", "strength_text": "500 mg", "schedule_text": "দিনে ২ বার"}])
    cid = client.post("/api/cases").json()["case_id"]
    r = client.post(f"/api/cases/{cid}/voice", files={"file": ("v.webm", b"x" * 100, "audio/webm")}).json()
    assert r["transcript"].startswith("আমি নাপা")
    it = r["items"][0]
    assert it["source"] == "voice" and it["chosen"]["brand"] == "Napa" and it["needs_confirm"]
    assert it["schedule"]["per_day"] == 2
    # unconfirmed spoken item: no red rule, a 'please confirm' note in Bangla that names the cause
    chk = client.get(f"/api/cases/{cid}/check").json()
    assert not [f for f in chk["findings"] if f["severity"] == "red"]
    note = next(f for f in chk["findings"] if f["rule"] == "CONFIRM_FIRST")
    assert "কথায় শোনা" in note["bn"]


def test_confirmed_voice_item_joins_prescription_rules(client, monkeypatch):
    import app.ai.perceive as perceive
    from tests.test_api import fake_read
    cid = client.post("/api/cases").json()["case_id"]
    monkeypatch.setattr(perceive, "read_image", fake_read([("Napa", "500 mg", "1+0+1")], doctor="Dr A"))
    from tests.test_robustness import jpg
    client.post(f"/api/cases/{cid}/images", files={"file": ("a.jpg", jpg(), "image/jpeg")})
    fake_voice(monkeypatch, "আর এস খাই", [{"name_as_said": "এস", "name_english_letters": "Ace", "strength_text": "500"}])
    it = client.post(f"/api/cases/{cid}/voice", files={"file": ("v.webm", b"x" * 100, "audio/webm")}).json()["items"][0]
    client.post(f"/api/cases/{cid}/items/{it['item_id']}/confirm", json={"product_id": it["chosen"]["product_id"]})
    for iid in ("I1", it["item_id"]):
        client.post(f"/api/cases/{cid}/items/{iid}/status", json={"taking": "current"})
    chk = client.get(f"/api/cases/{cid}/check").json()
    assert any(f["rule"] == "DUP_INGREDIENT" and f["severity"] == "red" for f in chk["findings"])


def test_voice_rejects_non_audio_and_huge_files(client):
    cid = client.post("/api/cases").json()["case_id"]
    assert client.post(f"/api/cases/{cid}/voice", files={"file": ("v.txt", b"hello", "text/plain")}).status_code == 415
    assert client.post(f"/api/cases/{cid}/voice", files={"file": ("v.webm", b"x" * (5 * 1024 * 1024 + 1), "audio/webm")}).status_code == 413


def test_speech_text_comes_only_from_findings():
    from app.ai.speech import findings_speech
    red = {"severity": "red", "bn": "Napa আর Ace: দুটোতেই একই ওষুধ আছে।"}
    info = {"severity": "info", "bn": "তথ্য"}
    assert findings_speech([info, red]).startswith("সতর্কতা। Napa আর Ace")
    assert "দুবার পাওয়া যায়নি" in findings_speech([info])          # says what was checked, not "no problem"


@pytest.mark.parametrize("source,handwritten,phrase", [("voice", False, "কথায় শোনা"), ("text", False, "লেখা নামটি"),
                                                        ("rx", True, "হাতের লেখা"), ("strip", False, "ছবির লেখা")])
def test_confirm_message_names_the_real_cause(source, handwritten, phrase):
    f = Finding("CONFIRM_FIRST", "info", ["M1"], {"brand": "Napa", "source": source, "handwritten": handwritten}, "x")
    assert phrase in explain(f)["bn"]
