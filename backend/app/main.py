"""FastAPI entry point: health, case API for the web app, and live catalog lookups."""
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
