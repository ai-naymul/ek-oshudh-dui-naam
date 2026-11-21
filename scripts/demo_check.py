"""Pre-demo check: run at the venue against the laptop or the public tunnel URL. Stdlib only.

    python3 scripts/demo_check.py                          # http://localhost:8000
    python3 scripts/demo_check.py https://xxx.trycloudflare.com --image path/to/rx.jpg

Checks, each with its latency: health; web app page; live brand lookup (typo + Bangla); random brand
(proves nothing is pre-baked); a typed two-medicine case gives a red Bangla finding; the case reopens by link;
the Bangla voice reply; optionally a real photo through the AI reader; WhatsApp webhook rejects a forged
request. Exit code 1 if any required check fails.
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import uuid


def req(base, path, method="GET", body=None, headers=None, raw=False, timeout=90):
    data = body if isinstance(body, (bytes, type(None))) else json.dumps(body).encode()
    h = {"Content-Type": "application/json"} if body is not None and not isinstance(body, bytes) else {}
    h.update(headers or {})
    r = urllib.request.Request(base + path, data=data, method=method, headers=h)
    t0 = time.time()
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        out = resp.read()
        ms = (time.time() - t0) * 1000
        return (out if raw else json.loads(out or b"{}")), ms, resp.headers


def multipart(field, filename, data, mime):
    boundary = uuid.uuid4().hex
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"; filename=\"{filename}\"\r\n"
            f"Content-Type: {mime}\r\n\r\n").encode() + data + f"\r\n--{boundary}--\r\n".encode()
    return body, {"Content-Type": f"multipart/form-data; boundary={boundary}"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base", nargs="?", default="http://localhost:8000")
    ap.add_argument("--image", help="a prescription or strip photo to send through the AI reader")
    ap.add_argument("--skip-voice", action="store_true", help="skip the text-to-speech check (saves a model call)")
    a = ap.parse_args()
    base = a.base.rstrip("/")
    results = []

    def check(name, fn, required=True):
        try:
            detail, ms = fn()
            results.append((True, name, ms, detail))
        except Exception as e:  # report and continue: the point is a full picture before the demo
            results.append((not required and None, name, 0, f"{type(e).__name__}: {e}"[:110]))

    def health():
        d, ms, _ = req(base, "/health")
        assert d["status"] == "ok"
        return f"version {d['version']}", ms

    def page():
        html, ms, _ = req(base, "/", raw=True)
        assert b"<div id=\"root\">" in html
        return f"{len(html)} bytes", ms

    def lookup():
        d, ms, _ = req(base, "/api/brands/search?q=Nappa%20500")
        assert d["options"][0]["brand"] == "Napa", d["options"][0]
        d2, ms2, _ = req(base, "/api/brands/search?q=" + urllib.request.quote("সেকলো"))
        assert d2["options"][0]["brand"] == "Seclo", d2["options"][0]
        return "Nappa→Napa, সেকলো→Seclo", (ms + ms2) / 2

    def random_brand():
        a1, ms, _ = req(base, "/api/brands/random")
        a2, _, _ = req(base, "/api/brands/random")
        assert a1["request_id"] != a2["request_id"]
        return f"{a1['brand']} → {', '.join(i['name'] for i in a1['path']['ingredients'])}", ms

    state = {}

    def typed_case():
        cid = req(base, "/api/cases", "POST", b"")[0]["case_id"]
        req(base, f"/api/cases/{cid}/text", "POST", {"text": "Napa 500 1+0+1\nAce 500 0+0+1"})
        d, ms, _ = req(base, f"/api/cases/{cid}/check")
        red = [f for f in d["findings"] if f["severity"] == "red"]
        assert red and "paracetamol" in red[0]["en"].lower(), d["findings"]
        state["cid"] = cid
        return red[0]["bn"][:60], ms

    def reopen():
        d, ms, _ = req(base, f"/api/cases/{state['cid']}")
        assert len(d["items"]) == 2
        return "2 items", ms

    def voice():
        audio, ms, h = req(base, f"/api/cases/{state['cid']}/speech", raw=True, timeout=120)
        assert len(audio) > 10_000 and "audio" in h.get("Content-Type", "")
        return f"{len(audio) // 1024} KB {h.get('Content-Type')}", ms

    def photo():
        cid = req(base, "/api/cases", "POST", b"")[0]["case_id"]
        data = open(a.image, "rb").read()
        body, hdr = multipart("file", "photo.jpg", data, "image/jpeg")
        d, ms, _ = req(base, f"/api/cases/{cid}/images", "POST", body, hdr, timeout=120)
        got = ", ".join(f"{i['chosen']['brand'] if i['chosen'] else '?'}{'*' if i['needs_confirm'] else ''}" for i in d["items"])
        assert d["items"], "no medicine read"
        return f"{d['kind']}: {got} (* = asks to confirm)", ms

    def forged_webhook():
        try:
            req(base, "/whatsapp/webhook", "POST", {"entry": []}, {"x-hub-signature-256": "sha256=forged"})
            raise AssertionError("forged request accepted: set WA_APP_SECRET before the demo")
        except urllib.error.HTTPError as e:
            assert e.code == 401
            return "forged request rejected (401)", 0

    check("health", health)
    check("web app page", page)
    check("brand lookup (typo + Bangla)", lookup)
    check("random brand", random_brand)
    check("typed case → red finding", typed_case)
    check("reopen case by link", reopen)
    if not a.skip_voice:
        check("Bangla voice reply", voice, required=False)
    if a.image:
        check("photo through AI reader", photo)
    check("WhatsApp webhook signature", forged_webhook, required=False)

    width = max(len(n) for _, n, _, _ in results)
    for ok, name, ms, detail in results:
        mark = "PASS" if ok else ("WARN" if ok is None else "FAIL")
        print(f"{mark}  {name:<{width}}  {ms:7.0f} ms  {detail}")
    failed = [n for ok, n, _, _ in results if ok is False]
    print(f"\n{base}: {'all required checks passed' if not failed else 'FAILED: ' + ', '.join(failed)}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
