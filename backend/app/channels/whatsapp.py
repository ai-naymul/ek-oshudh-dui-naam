"""WhatsApp channel (Meta WhatsApp Cloud API, free test number).

Flow: a family member sends prescription/strip photos, a voice note, or typed names to the test number.
- GET  /whatsapp/webhook   Meta's one-time verification (hub.verify_token must match WA_VERIFY_TOKEN)
- POST /whatsapp/webhook   messages; the signature (X-Hub-Signature-256, HMAC of the body with WA_APP_SECRET) is
                           checked, we answer 200 at once and work in the background (Meta retries slow webhooks),
                           and each message id is handled once (Meta can deliver the same message twice).
Every input goes through the same engine as the web app; the reply is the Bangla template findings plus a link
that opens the same case in the web app (picture card, voice, confirm screen). One case per sender; 'নতুন' or
'new' starts a fresh one. Secrets come only from the environment.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
import time
import urllib.request

API_VERSION = os.environ.get("WA_API_VERSION", "v23.0")
GRAPH = f"https://graph.facebook.com/{API_VERSION}"
RESET_WORDS = {"নতুন", "new", "reset", "শুরু"}
HELP = ("আসসালামু আলাইকুম। প্রেসক্রিপশন বা ওষুধের স্ট্রিপের ছবি পাঠান, অথবা ওষুধের নাম লিখে বা বলে পাঠান। "
        "আমরা মিলিয়ে দেখব একই ওষুধ দুই নামে দুইবার খাচ্ছেন কি না। নতুন করে শুরু করতে লিখুন: নতুন")


class WhatsApp:
    def __init__(self, engine, public_url: str | None = None):
        self.engine = engine
        self.token = os.environ.get("WA_TOKEN", "")
        self.phone_id = os.environ.get("WA_PHONE_ID", "")
        self.verify_token = os.environ.get("WA_VERIFY_TOKEN", "")
        self.app_secret = os.environ.get("WA_APP_SECRET", "")
        self.public_url = public_url or os.environ.get("PUBLIC_API_URL", "")
        self.cases: dict[str, str] = {}          # sender -> case id
        self.seen: dict[str, float] = {}         # message id -> time handled
        self.lock = threading.Lock()

    # ---------- webhook plumbing ----------
    def verify(self, mode: str | None, token: str | None, challenge: str | None) -> str | None:
        if mode == "subscribe" and self.verify_token and hmac.compare_digest(token or "", self.verify_token):
            return challenge or ""
        return None

    def signature_ok(self, body: bytes, header: str | None) -> bool:
        if not self.app_secret:          # test-number setups without an app secret: allowed, but logged in the trace
            return True
        expected = "sha256=" + hmac.new(self.app_secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, header or "")

    def first_time(self, message_id: str) -> bool:
        with self.lock:
            now = time.time()
            for k in [k for k, t in self.seen.items() if now - t > 3600]:
                del self.seen[k]
            if message_id in self.seen:
                return False
            self.seen[message_id] = now
            return True

    @staticmethod
    def messages(payload: dict) -> list[dict]:
        out = []
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                out += change.get("value", {}).get("messages", []) or []
        return out

    # ---------- Graph API calls (patched in tests) ----------
    def _graph(self, path: str, body: dict | None = None) -> dict:
        req = urllib.request.Request(f"{GRAPH}/{path}", data=json.dumps(body).encode() if body else None,
                                     headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(req, timeout=30).read())

    def download(self, media_id: str) -> tuple[bytes, str]:
        info = self._graph(media_id)
        req = urllib.request.Request(info["url"], headers={"Authorization": f"Bearer {self.token}"})
        return urllib.request.urlopen(req, timeout=60).read(), info.get("mime_type", "application/octet-stream")

    def send_text(self, to: str, text: str) -> None:
        self._graph(f"{self.phone_id}/messages", {"messaging_product": "whatsapp", "to": to, "type": "text",
                                                   "text": {"body": text[:4000], "preview_url": True}})

    # ---------- conversation ----------
    def _case(self, sender: str, fresh: bool = False):
        cid = None if fresh else self.cases.get(sender)
        try:
            if cid:
                return self.engine.get(cid)
        except KeyError:
            pass
        case = self.engine.new_case()
        self.cases[sender] = case.case_id
        return case

    def handle(self, msg: dict) -> str | None:
        """Process one incoming message and send the reply. Returns the reply text (for tests and the trace)."""
        sender, kind = msg.get("from", ""), msg.get("type")
        if kind == "text" and msg["text"]["body"].strip().lower() in RESET_WORDS:
            self._case(sender, fresh=True)
            reply = "নতুন যাচাই শুরু হলো। " + HELP
            self.send_text(sender, reply)
            return reply
        case = self._case(sender)
        try:
            if kind == "image":
                data, _ = self.download(msg["image"]["id"])
                self.engine.add_image(case, data)
            elif kind == "document" and msg["document"].get("mime_type", "").startswith("image/"):
                data, _ = self.download(msg["document"]["id"])
                self.engine.add_image(case, data)
            elif kind in ("audio", "voice"):
                data, mime = self.download(msg[kind]["id"])
                self.engine.add_voice(case, data, mime)
            elif kind == "text":
                self.engine.add_text(case, msg["text"]["body"])
            else:
                self.send_text(sender, HELP)
                return HELP
        except Exception as e:  # never leave the user without an answer
            reply = f"দুঃখিত, এটি পড়া যায়নি ({type(e).__name__})। আরেকটু কাছ থেকে, আলোতে ছবি তুলে আবার পাঠান।"
            self.send_text(sender, reply)
            return reply
        reply = self.summary(case)
        self.send_text(sender, reply)
        return reply

    def summary(self, case) -> str:
        result = self.engine.check(case)
        unsure = [i for i in case.items if i.needs_confirm]
        meds = ", ".join(f"{m['brand']} {m['strength']}" for m in result["medicines"]) or "কোনো ওষুধ চেনা যায়নি"
        lines = [f"যা পেয়েছি: {meds}"]
        mark = {"red": "🔴 সতর্কতা", "amber": "🟠 খেয়াল রাখুন"}
        for f in result["findings"]:
            if f["severity"] in mark:
                lines.append(f"{mark[f['severity']]}: {f['bn']}")
        if not any(f["severity"] in mark for f in result["findings"]):
            lines.append("আমাদের যাচাইয়ে বড় কোনো সমস্যা পাওয়া যায়নি।")
        if unsure:
            lines.append(f"{len(unsure)}টি নাম নিশ্চিত নয়; নিচের লিংকে ছবির সাথে মিলিয়ে নিশ্চিত করুন, তারপর আবার দেখুন।")
        if self.public_url:
            lines.append(f"ছবি কার্ড, বাংলায় শুনুন ও বিস্তারিত: {self.public_url.rstrip('/')}/?case={case.case_id}")
        lines.append("এটি ডাক্তারের পরামর্শের বিকল্প নয়। ডাক্তার বা ফার্মাসিস্টকে দেখান।")
        return "\n\n".join(lines)
