"""FastAPI entry point. Routes are added issue by issue; see PROJECT.md for the status board."""
import time
import uuid

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

APP_VERSION = "0.1.0"

app = FastAPI(title="Ek Oshudh, Dui Naam API", version=APP_VERSION)

# The web app is served from Cloudflare Pages and calls this backend through a tunnel, so CORS must allow it.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https://.*\.pages\.dev|http://localhost:\d+|http://127\.0\.0\.1:\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    """Liveness check used by the tunnel test and demo_check. Every call gets a fresh id and time, so it can't be cached."""
    return {"status": "ok", "version": APP_VERSION, "request_id": uuid.uuid4().hex[:12], "server_time": time.time()}
