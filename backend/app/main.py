"""FastAPI entry point: health, case API for the web app, and live catalog lookups."""
import json
import os
import random
import time
import uuid
from functools import lru_cache

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel

APP_VERSION = "0.2.0"
MAX_UPLOAD = 12 * 1024 * 1024

app = FastAPI(title="Ek Oshudh, Dui Naam API", version=APP_VERSION)

# The web app is served from Cloudflare Pages and calls this backend through a tunnel, so CORS must allow it.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https://.*\.pages\.dev|https://.*\.trycloudflare\.com|http://localhost:\d+|http://127\.0\.0\.1:\d+|http://192\.168\.\d+\.\d+:\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)


@lru_cache(maxsize=1)
def engine():
    from app.conversation import Engine
    return Engine()


def live(payload: dict, t0: float) -> dict:
    """Every response carries a fresh request id, server time and latency: proof that nothing is cached."""
    return {**payload, "request_id": uuid.uuid4().hex[:12], "server_time": time.time(), "latency_ms": round((time.time() - t0) * 1000, 1)}


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": APP_VERSION, "request_id": uuid.uuid4().hex[:12], "server_time": time.time()}


@app.post("/api/cases")
def new_case():
    t0 = time.time()
    return live({"case_id": engine().new_case().case_id}, t0)


def _case(case_id: str):
    try:
        return engine().get(case_id)
    except KeyError:
        raise HTTPException(404, "case not found or expired")


@app.post("/api/cases/{case_id}/images")
async def add_image(case_id: str, file: UploadFile = File(...)):
    t0 = time.time()
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "image too large (max 12 MB)")
    from app.ai.gemini import GeminiError
    try:
        return live(engine().add_image(_case(case_id), data), t0)
    except GeminiError as e:
        raise HTTPException(502, f"reading failed: {e}")


class TextIn(BaseModel):
    text: str


MAX_AUDIO = 5 * 1024 * 1024


@app.post("/api/cases/{case_id}/voice")
async def add_voice(case_id: str, file: UploadFile = File(...)):
    t0 = time.time()
    case = _case(case_id)
    data = await file.read()
    if not data or len(data) > MAX_AUDIO:
        raise HTTPException(413, "voice note must be under 5 MB")
    from app.ai.gemini import GeminiError
    try:
        out = engine().add_voice(case, data, file.content_type or "audio/webm")
    except ValueError as e:
        raise HTTPException(415, str(e))
    except GeminiError as e:
        raise HTTPException(502, f"could not transcribe: {e}")
    return live(out, t0)


@app.get("/api/cases/{case_id}/speech")
def case_speech(case_id: str):
    """Bangla voice reply for this case's findings (template text only)."""
    case = _case(case_id)
    from app.ai.gemini import GeminiError
    try:
        audio, mime, text = engine().speech(case)
    except GeminiError as e:
        raise HTTPException(502, f"could not create speech: {e}")
    return Response(audio, media_type=mime, headers={"Cache-Control": "no-store", "X-Request-Id": uuid.uuid4().hex[:12]})


@app.post("/api/cases/{case_id}/text")
def add_text(case_id: str, body: TextIn):
    t0 = time.time()
    return live(engine().add_text(_case(case_id), body.text), t0)


class ConfirmIn(BaseModel):
    product_id: int | None = None
    per_day: float | None = None


@app.post("/api/cases/{case_id}/items/{item_id}/confirm")
def confirm(case_id: str, item_id: str, body: ConfirmIn):
    t0 = time.time()
    try:
        return live(engine().confirm(_case(case_id), item_id, body.product_id, body.per_day), t0)
    except StopIteration:
        raise HTTPException(404, "item not found")


@app.get("/api/cases/{case_id}/check")
def check(case_id: str):
    t0 = time.time()
    return live(engine().check(_case(case_id)), t0)


@app.get("/api/cases/{case_id}/items/{item_id}/crop.jpg")
def item_crop(case_id: str, item_id: str):
    it = next((i for i in _case(case_id).items if i.item_id == item_id), None)
    if not it or not it.crop:
        raise HTTPException(404, "no crop")
    return Response(it.crop, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@app.get("/api/brands/search")
def brand_search(q: str):
    """'Try any brand': live lookup in the catalog, with the knowledge-graph path for the top match."""
    t0 = time.time()
    e = engine()
    cands = e.index.search(q, 20)
    opts = e._options(cands, 5)
    return live({"query": q, "options": opts, "path": e.graph.path(opts[0]["product_id"]) if opts else None}, t0)


@app.get("/api/brands/random")
def brand_random():
    t0 = time.time()
    e = engine()
    brand = random.choice(e.index.brands)
    p = e.graph.products_by_brand(brand)[0]
    return live({"brand": brand, "path": e.graph.path(p.id)}, t0)



@app.get("/api/cases/{case_id}")
def get_case(case_id: str):
    """Reopen a case (e.g. from the WhatsApp link): its items, so the web app can show confirm or results."""
    t0 = time.time()
    case = _case(case_id)
    return live({"case_id": case.case_id, "items": [engine().item_view(i) for i in case.items]}, t0)


# ---------- WhatsApp (Meta Cloud API test number) ----------
@lru_cache(maxsize=1)
def whatsapp():
    from app.channels.whatsapp import WhatsApp
    return WhatsApp(engine())


@app.get("/whatsapp/webhook")
def wa_verify(request: Request):
    q = request.query_params
    challenge = whatsapp().verify(q.get("hub.mode"), q.get("hub.verify_token"), q.get("hub.challenge"))
    if challenge is None:
        raise HTTPException(403, "verification failed")
    return PlainTextResponse(challenge)


@app.post("/whatsapp/webhook")
async def wa_receive(request: Request, background: BackgroundTasks):
    body = await request.body()
    wa = whatsapp()
    if not wa.signature_ok(body, request.headers.get("x-hub-signature-256")):
        raise HTTPException(401, "bad signature")
    if not os.environ.get("PUBLIC_API_URL"):
        wa.public_url = str(request.base_url)      # the tunnel URL this request came through
    try:
        payload = json.loads(body or b"{}")
    except ValueError:
        raise HTTPException(400, "bad json")
    for msg in wa.messages(payload):
        if msg.get("id") and wa.first_time(msg["id"]):
            background.add_task(wa.handle, msg)      # answer Meta at once; work after the response
    return {"ok": True}

# The same server also serves the built web app (web/dist), so one tunnel URL is enough for a phone:
# app and API on one origin. Cloudflare Pages serves the same build as the stable public front door.
_DIST = os.path.join(os.path.dirname(__file__), "..", "..", "web", "dist")
if os.path.isdir(_DIST):
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="web")
