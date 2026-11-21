"""FastAPI entry point: health, case API for the web app, and live catalog lookups."""
import json
import os
import random
import time
import uuid
from functools import lru_cache

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

APP_VERSION = "0.2.0"
MAX_UPLOAD = 12 * 1024 * 1024

app = FastAPI(title="Ek Oshudh, Dui Naam API", version=APP_VERSION)

# The app is served by this same server (same origin). CORS only matters for the Vite dev server on another port
# and for a phone on the same Wi-Fi or the optional tunnel.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https://.*\.trycloudflare\.com|http://localhost:\d+|http://127\.0\.0\.1:\d+|http://192\.168\.\d+\.\d+:\d+",
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


@app.post("/api/cases/{case_id}/items/{item_id}/resolve")
def resolve_item(case_id: str, item_id: str):
    """Agent looks for evidence (other medicines in the case, registry lookups) for one unclear item."""
    t0 = time.time()
    case = _case(case_id)
    if not any(i.item_id == item_id for i in case.items):
        raise HTTPException(404, "item not found")
    return live(engine().resolve(case, item_id), t0)


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
    """Reopen a case by link (?case=...): its items, so the web app can show confirm or results."""
    t0 = time.time()
    case = _case(case_id)
    return live({"case_id": case.case_id, "items": [engine().item_view(i) for i in case.items]}, t0)


# The same server also serves the built web app (web/dist): one command runs the whole product locally.
_DIST = os.path.join(os.path.dirname(__file__), "..", "..", "web", "dist")
if os.path.isdir(_DIST):
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="web")
