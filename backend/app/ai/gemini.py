"""Minimal Gemini REST client: image/audio/text parts in, strict JSON (or text/audio) out.

- Key only from the environment (GEMINI_API_KEY, loaded from the repo's gitignored .env).
- Concurrency limit (semaphore), retry with backoff on 429/5xx, optional fallback model.
- temperature 0 so the same input gives the same reading as far as the model allows.
"""
from __future__ import annotations

import base64
import http.client
import json
import mimetypes
import os
import threading
import time
import urllib.error
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
READ_MODEL = "gemini-3.8-flash"
LITE_MODEL = "gemini-3.1-flash-lite"
_SEM = threading.BoundedSemaphore(int(os.environ.get("GEMINI_CONCURRENCY", "8")))


def _load_env() -> None:
    path = os.path.join(ROOT, ".env")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.strip().split("=", 1)
                os.environ.setdefault(k, v)


_load_env()


class GeminiError(RuntimeError):
    pass


def image_part(path_or_bytes, mime: str | None = None) -> dict:
    if isinstance(path_or_bytes, (bytes, bytearray)):
        data, mime = bytes(path_or_bytes), mime or "image/jpeg"
    else:
        data = open(path_or_bytes, "rb").read()
        mime = mime or mimetypes.guess_type(path_or_bytes)[0] or "image/jpeg"
    return {"inline_data": {"mime_type": mime, "data": base64.b64encode(data).decode()}}


def generate(parts: list, model: str = READ_MODEL, schema: dict | None = None, thinking: str | None = "low",
             retries: int = 3, timeout: int = 120) -> tuple[object, dict]:
    """Returns (parsed JSON or text, meta={model, seconds, tokens}). Raises GeminiError on hard failure."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise GeminiError("GEMINI_API_KEY is not set")
    gc: dict = {"temperature": 0}
    if schema is not None:
        gc["responseMimeType"] = "application/json"
        gc["responseSchema"] = schema
    if thinking and "lite" not in model:
        gc["thinkingConfig"] = {"thinkingLevel": thinking}
    body = json.dumps({"contents": [{"role": "user", "parts": parts}], "generationConfig": gc}).encode()
    last = ""
    for attempt in range(retries + 1):
        req = urllib.request.Request(URL.format(model=model), data=body,
                                     headers={"x-goog-api-key": key, "Content-Type": "application/json"})
        t0 = time.time()
        try:
            with _SEM:
                resp = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
            cand = resp["candidates"][0]
            text = "".join(p.get("text", "") for p in cand["content"]["parts"] if not p.get("thought"))
            meta = {"model": model, "seconds": round(time.time() - t0, 2),
                    "tokens": resp.get("usageMetadata", {}).get("totalTokenCount")}
            return (json.loads(text) if schema is not None else text), meta
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read().decode()[:200]}"
            if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(2 * (attempt + 1))
                continue
            break
        except (KeyError, IndexError, json.JSONDecodeError, urllib.error.URLError, TimeoutError,
                http.client.HTTPException, ConnectionError, OSError) as e:
            last = f"{type(e).__name__}: {e}"
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
                continue
    raise GeminiError(f"{model} failed: {last}")
