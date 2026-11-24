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


def test_the_same_spoken_reply_is_made_only_once(monkeypatch):
    # The result page asks for the reply audio as soon as it appears; asking again (the tap) must not wait again.
    import app.ai.speech as speech
    from app.conversation import Engine
    calls = []
    monkeypatch.setattr(speech, "speak_bn", lambda text: (calls.append(text) or b"RIFF", "audio/wav", {"model": "fake"}))
    e = Engine()
    case = e.new_case()
    e.add_text(case, "Napa 500\nAce 500")
    assert e.speech(case)[0] == e.speech(case)[0] == b"RIFF"
    assert len(calls) == 1


def _wav(seconds=0.2):
    import io
    import wave
    buf = io.BytesIO()
    w = wave.open(buf, "wb")
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
    w.writeframes(b"\x00\x00" * int(24000 * seconds))
    w.close()
    return buf.getvalue()


def test_the_reply_is_spoken_in_parts_at_the_same_time(monkeypatch):
    # One long reply took ~12 s on the venue network; its sentences are now spoken together and joined.
    import io
    import time
    import wave
    import app.ai.speech as speech
    monkeypatch.setattr(speech, "speak_bn", lambda text: (time.sleep(0.5), (_wav(), "audio/wav", {"model": "fake"}))[1])
    t0 = time.time()
    audio, mime, meta = speech.speak_parts(["এক।", "দুই।", "তিন।"])
    assert time.time() - t0 < 1.2 and mime == "audio/wav" and meta["parts"] == 3
    w = wave.open(io.BytesIO(audio))
    assert abs(w.getnframes() / w.getframerate() - (3 * 0.2 + 2 * 0.3)) < 0.01


def test_checking_the_bag_starts_the_reply_before_anyone_asks_for_it(monkeypatch):
    import app.ai.speech as speech
    from app.conversation import Engine
    calls = []
    monkeypatch.setattr(speech, "speak_bn", lambda text: (calls.append(text) or _wav(), "audio/wav", {"model": "fake"}))
    e = Engine()
    case = e.new_case()
    e.add_text(case, "Napa 500\nAce 500")
    e.prefetch_speech(case)
    audio, _, _ = e.speech(case)
    assert audio.startswith(b"RIFF") and len(calls) >= 1
    n = len(calls)
    e.speech(case)
    assert len(calls) == n


def test_cases_survive_a_server_restart(monkeypatch, tmp_path):
    import time
    from app.conversation import Engine
    monkeypatch.setenv("EK_CASES_FILE", str(tmp_path / "cases.pkl"))
    e1 = Engine()
    case = e1.new_case()
    e1.add_text(case, "Napa 500")
    time.sleep(3.5)                                   # saved every 3 s
    e2 = Engine()                                     # a new server process
    assert [i.reading for i in e2.get(case.case_id).items] == ["Napa 500"]
    e2.get(case.case_id).new_ids(1)                  # the case lock works again after loading
