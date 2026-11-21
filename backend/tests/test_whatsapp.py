"""WhatsApp webhook with Meta's Graph API faked: verification, signature, de-duplication, replies."""
import hashlib
import hmac
import json
import os

import pytest
from fastapi.testclient import TestClient

from app.core import graph as g

pytestmark = pytest.mark.skipif(not os.path.exists(g.DB_PATH), reason="graph not built")
SECRET = "test-secret"


@pytest.fixture()
def wa(monkeypatch):
    monkeypatch.setenv("WA_VERIFY_TOKEN", "verify-me")
    monkeypatch.setenv("WA_APP_SECRET", SECRET)
    monkeypatch.setenv("PUBLIC_API_URL", "https://example.trycloudflare.com")
    import app.main as main
    main.whatsapp.cache_clear()
    bot = main.whatsapp()
    sent = []
    monkeypatch.setattr(bot, "send_text", lambda to, text: sent.append((to, text)))
    monkeypatch.setattr(bot, "download", lambda media_id: (b"img", "image/jpeg"))
    yield TestClient(main.app), bot, sent
    main.whatsapp.cache_clear()


def post(client, payload, secret=SECRET):
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post("/whatsapp/webhook", content=body, headers={"x-hub-signature-256": sig, "content-type": "application/json"})


def msg(mid, kind="text", body=None, sender="8801700000000"):
    m = {"from": sender, "id": mid, "type": kind}
    m[kind] = {"body": body} if kind == "text" else {"id": "media-1", "mime_type": "image/jpeg"}
    return {"entry": [{"changes": [{"value": {"messages": [m]}}]}]}


def test_verification(wa):
    client, _, _ = wa
    ok = client.get("/whatsapp/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "verify-me", "hub.challenge": "42"})
    assert ok.status_code == 200 and ok.text == "42"
    assert client.get("/whatsapp/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "42"}).status_code == 403


def test_bad_signature_is_rejected(wa):
    client, _, sent = wa
    assert post(client, msg("m0", body="Napa"), secret="other").status_code == 401 and not sent


def test_typed_names_get_bangla_findings_and_a_link(wa):
    client, _, sent = wa
    assert post(client, msg("m1", body="Napa 500 1+0+1\nAce 500 0+0+1")).status_code == 200
    to, text = sent[-1]
    assert to == "8801700000000" and "🔴 সতর্কতা" in text and "paracetamol" in text
    assert "https://example.trycloudflare.com/?case=" in text and "ডাক্তার বা ফার্মাসিস্টকে দেখান" in text


def test_same_message_twice_is_handled_once(wa):
    client, _, sent = wa
    post(client, msg("dup", body="Napa 500"))
    post(client, msg("dup", body="Napa 500"))
    assert len(sent) == 1


def test_photo_goes_through_the_engine(wa, monkeypatch):
    import app.ai.perceive as perceive
    from tests.test_api import fake_read
    client, _, sent = wa
    monkeypatch.setattr(perceive, "read_image", fake_read([("Seclo", "20 mg", "0+0+1")], kind="strip"))
    post(client, msg("p1", kind="image"))
    assert "Seclo 20 mg" in sent[-1][1]


def test_reset_starts_a_new_case(wa):
    client, bot, sent = wa
    post(client, msg("r1", body="Napa 500"))
    first = bot.cases["8801700000000"]
    post(client, msg("r2", body="নতুন"))
    assert bot.cases["8801700000000"] != first and "নতুন যাচাই" in sent[-1][1]
