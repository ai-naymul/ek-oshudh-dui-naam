"""Bugs found in the 21 Nov audit, each pinned by a test: bad input must give a clear 4xx, an AI failure must not leave
a half-written case, and one slow AI call must not freeze the server for everyone else."""
import io
import os
import threading
import time

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core import graph as g

pytestmark = pytest.mark.skipif(not os.path.exists(g.DB_PATH), reason="graph not built")


@pytest.fixture(scope="module")
def client():
    from app.main import app
    return TestClient(app)


def jpg():
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), "white").save(buf, "JPEG")
    return buf.getvalue()


def new_case(client, text=None):
    cid = client.post("/api/cases").json()["case_id"]
    items = client.post(f"/api/cases/{cid}/text", json={"text": text}).json()["items"] if text else []
    return cid, items


def test_confirm_rejects_a_product_that_does_not_exist(client):
    cid, items = new_case(client, "Napa 500")
    r = client.post(f"/api/cases/{cid}/items/{items[0]['item_id']}/confirm", json={"product_id": 99999999})
    assert r.status_code == 422
    assert client.get(f"/api/cases/{cid}/check").status_code == 200     # the case still works


def test_confirm_rejects_impossible_daily_amounts(client):
    cid, items = new_case(client, "Napa 500")
    for bad in (-1, 0, 100):
        r = client.post(f"/api/cases/{cid}/items/{items[0]['item_id']}/confirm", json={"product_id": None, "per_day": bad})
        assert r.status_code == 422, bad


def test_a_file_that_is_not_an_image_is_refused(client):
    cid, _ = new_case(client)
    r = client.post(f"/api/cases/{cid}/images", files={"file": ("x.jpg", b"%PDF-1.4 not an image", "image/jpeg")})
    assert r.status_code == 415


def test_very_long_text_is_refused(client):
    cid, _ = new_case(client)
    assert client.post(f"/api/cases/{cid}/text", json={"text": "Napa 500\n" * 200}).status_code == 413


def test_ai_failure_while_choosing_falls_back_to_asking(client, monkeypatch):
    """If the constrained AI choice (R3) fails, the line is kept and the family is asked, instead of a 502."""
    import app.ai.perceive as perceive
    import app.conversation as conv
    from app.ai.gemini import GeminiError
    from tests.test_api import fake_read
    monkeypatch.setattr(perceive, "read_image", fake_read([("Nqpz", "500 mg", "1+0+1")]))

    def broken(*a, **k):
        raise GeminiError("network down")
    monkeypatch.setattr(conv, "r3", broken)
    cid, _ = new_case(client)
    r = client.post(f"/api/cases/{cid}/images", files={"file": ("a.jpg", jpg(), "image/jpeg")})
    assert r.status_code == 200 and r.json()["items"][0]["needs_confirm"] is True


def test_reading_failure_leaves_the_case_unchanged(client, monkeypatch):
    import app.ai.perceive as perceive
    from app.ai.gemini import GeminiError

    def broken(data):
        raise GeminiError("network down")
    monkeypatch.setattr(perceive, "read_image", broken)
    cid, _ = new_case(client, "Napa 500")
    assert client.post(f"/api/cases/{cid}/images", files={"file": ("a.jpg", jpg(), "image/jpeg")}).status_code == 502
    assert len(client.get(f"/api/cases/{cid}").json()["items"]) == 1


def test_agent_survives_bad_ids_from_the_model(monkeypatch):
    import app.agent.resolver as r
    from app.conversation import Engine
    e = Engine()
    case = e.new_case()
    e.add_text(case, "Napa 500")
    e.add_text(case, "Nap")
    item = case.items[-1]
    item.needs_confirm = True
    turns = [[("get_ingredients", {"product_id": 99999999})], [("compare_prices", {"product_id": "abc"})],
             [("answer", {"product_id": "x", "reason_bn": ""})]]
    monkeypatch.setattr(r, "chat", lambda contents, tools, model: (
        {"role": "model", "parts": [{"functionCall": {"name": n, "args": a}} for n, a in turns.pop(0)]}, {}))
    assert e.resolve(case, item.item_id)["agent"]["product_id"] is None


def test_speech_without_audio_is_a_clean_error(monkeypatch):
    import app.ai.gemini as gm
    monkeypatch.setattr(gm, "_post", lambda model, parts, gc, retries, timeout, parse: (parse({"content": {"parts": [{"text": "hi"}]}}), {}))
    with pytest.raises(gm.GeminiError):
        gm.speak("হ্যালো", "tts-model", "Kore")


def test_a_slow_reading_does_not_freeze_other_requests(monkeypatch):
    """Real server (uvicorn, one event loop): while one photo takes 1.5 s to read, /health must still answer at once."""
    import json
    import socket
    import urllib.request

    import uvicorn

    import app.ai.perceive as perceive
    from app.main import app
    from tests.test_api import fake_read
    fast = fake_read([("Napa", "500 mg", "1+0+1")])

    def slow(data):
        time.sleep(1.5)
        return fast(data)
    monkeypatch.setattr(perceive, "read_image", slow)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    threading.Thread(target=server.run, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            urllib.request.urlopen(base + "/health", timeout=1)
            break
        except OSError:
            time.sleep(0.05)
    cid = json.loads(urllib.request.urlopen(urllib.request.Request(base + "/api/cases", method="POST")).read())["case_id"]
    boundary = "b0undary"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"a.jpg\"\r\n"
            f"Content-Type: image/jpeg\r\n\r\n").encode() + jpg() + f"\r\n--{boundary}--\r\n".encode()
    upload = urllib.request.Request(f"{base}/api/cases/{cid}/images", data=body, method="POST",
                                    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    t = threading.Thread(target=lambda: urllib.request.urlopen(upload, timeout=10).read())
    t.start()
    time.sleep(0.3)
    t0 = time.time()
    urllib.request.urlopen(base + "/health", timeout=5).read()
    took = time.time() - t0
    t.join()
    server.should_exit = True
    assert took < 0.6, f"health waited {took:.2f}s behind a slow reading"


def test_parallel_additions_to_one_case_get_unique_ids(client):
    cid, _ = new_case(client)
    threads = [threading.Thread(target=lambda: client.post(f"/api/cases/{cid}/text", json={"text": "Napa 500"})) for _ in range(12)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    ids = [i["item_id"] for i in client.get(f"/api/cases/{cid}").json()["items"]]
    assert len(ids) == 12 and len(set(ids)) == 12
