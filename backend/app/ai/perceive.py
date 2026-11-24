"""Perception: one photo (prescription, strip or box) -> structured medicine lines. Reading only, no judgement.

The model never decides anything medical. It fills a fixed schema: what is written, alternatives for unclear
words, the schedule text, and where on the image each line is (box, 0-1000 scale). Two models read in parallel
(Flash + Flash-Lite); whether they agree on the brand text becomes a confidence signal for matching.
Patient names are deliberately not part of the schema.
"""
from __future__ import annotations

import io
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from concurrent.futures import TimeoutError as FuturesTimeout

from PIL import Image
from rapidfuzz import fuzz

from .gemini import LITE_MODEL, READ_MODEL, GeminiError, generate, image_part

PROMPT = """You are the reading step of a medicine-safety tool used in Bangladesh.
Look at the photo. It is a doctor's prescription (handwritten or printed), a medicine strip, or a medicine box.
Report ONLY what is written. Do not correct names to medicines you know unless the letters support it.
Do not include the patient's name, age, phone number or address.
For each medicine line give:
- brand_text: the medicine name exactly as written (Latin or Bangla script)
- alternatives: up to 3 other readings if the word is unclear
- strength_text, form_text (Tab/Cap/Syp/Inj ...), generic_text if printed
- schedule_text exactly as written (e.g. 1+0+1, ১+০+১, BD, সকালে ১টা), meal_text (before/after food), duration_text
- expiry_text if printed (strips/boxes)
- handwritten: true if this line is handwritten
- box: [ymin, xmin, ymax, xmax] around the WHOLE written line or label for this medicine (number, form, name, strength and schedule), scaled 0-1000
For a strip or box: the same medicine is printed many times, in English and in Bangla, often with its ingredients.
Give each different medicine product ONCE: brand_text is the brand name in English letters (the Bangla name only if no
English one is printed); put ingredient names in generic_text, never as separate medicines.
Only MEDICINES go in items. The diagnosis, complaints, findings, tests and advice are not medicines: Bangladeshi
prescriptions often write the diagnosis at the top or on the left (C/C, Dx, D/D, O/E), for example 'T. corporis',
'T. cruris', 'T. capitis', 'T. versicolor', 'Scabies', 'Acne', 'HTN', 'DM'. There 'T.' means Tinea (a skin disease),
not Tablet. Put the diagnosis in diagnosis_text, never in items.
Also give kind and, for prescriptions, doctor_text (doctor or clinic name only), date_text and diagnosis_text."""

SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": ["prescription", "strip", "box", "other"]},
        "doctor_text": {"type": "string"},
        "date_text": {"type": "string"},
        "diagnosis_text": {"type": "string"},
        "items": {"type": "array", "items": {"type": "object", "properties": {
            "brand_text": {"type": "string"},
            "alternatives": {"type": "array", "items": {"type": "string"}},
            "strength_text": {"type": "string"}, "form_text": {"type": "string"}, "generic_text": {"type": "string"},
            "schedule_text": {"type": "string"}, "meal_text": {"type": "string"}, "duration_text": {"type": "string"},
            "expiry_text": {"type": "string"}, "handwritten": {"type": "boolean"},
            "box": {"type": "array", "items": {"type": "integer"}}},
            "required": ["brand_text", "alternatives", "handwritten"]}},
    },
    "required": ["kind", "items"],
}


def _resize(data: bytes, max_side: int = 1600) -> tuple[bytes, tuple[int, int]]:
    img = Image.open(io.BytesIO(data)).convert("RGB")
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return buf.getvalue(), img.size


def crop(data: bytes, box: list[int] | None, pad: float = 0.03, pad_x: float = 0.06) -> bytes | None:
    """Cut the region of one line (box on the 0-1000 scale) for the confirm screen and the R3 reranker.
    The box covers the whole line; a margin (growing with the box, never less than pad/pad_x) keeps the first and
    last letters in view: the person confirming must see the whole written line, not a clipped word."""
    if not box or len(box) != 4:
        return None
    img = Image.open(io.BytesIO(data)).convert("RGB")
    w, h = img.size
    y0, x0, y1, x1 = [v / 1000 for v in box]
    px, py = max(pad_x, 0.06 * (x1 - x0)), max(pad, 0.35 * (y1 - y0))
    x0, x1 = max(0, x0 - px), min(1, x1 + px)
    y0, y1 = max(0, y0 - py), min(1, y1 + py)
    if x1 <= x0 or y1 <= y0:
        return None
    buf = io.BytesIO()
    img.crop((int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h))).save(buf, "JPEG", quality=90)
    return buf.getvalue()


def name_agreement(text: str, others: list[str]) -> float:
    """How closely the second reader wrote the same NAME (strength and form words left out), 0..1."""
    from app.core.candidates import parse_hints
    name = parse_hints(text)[0]
    best = max((fuzz.ratio(name, parse_hints(o)[0]) for o in others), default=0)
    return round(best / 100, 2)


# A judge or a family must never wait minutes for one photo: the main reader gets 45 s and one retry, and the optional
# second reader (it only checks the names) gets at most SECOND_READER_WAIT seconds more after the first has answered.
READ_TIMEOUT, READ_RETRIES, SECOND_READER_WAIT = 45, 1, 8
# 24 Nov, venue network: the main reader sometimes hung to its time limit and retried (a photo waited 96 s). After
# MAIN_WAIT seconds, whichever reader answers first is used; the second reader runs from the start anyway.
MAIN_WAIT = 25
_readers = ThreadPoolExecutor(8)


def read_image(data: bytes) -> dict:
    """Returns {kind, doctor_text, date_text, items[...] with 'agree' added, image (resized bytes), meta}.
    'agree' is None when the second reader was too slow: then an exact name from this photo is asked, not accepted."""
    small, size = _resize(data)
    parts = [image_part(small, "image/jpeg"), {"text": PROMPT}]
    main_f = _readers.submit(generate, parts, READ_MODEL, SCHEMA, "low", READ_RETRIES, READ_TIMEOUT)
    lite_f = _readers.submit(generate, parts, LITE_MODEL, SCHEMA, None, READ_RETRIES, READ_TIMEOUT, optional=True)
    lite, from_main = None, True
    try:
        main, meta = main_f.result(timeout=MAIN_WAIT)
    except GeminiError:
        main, meta = lite_f.result()  # fallback reader
        meta["fallback"], from_main = True, False
    except FuturesTimeout:            # main reader stalled: from now on, whichever reader answers first
        wait([main_f, lite_f], return_when=FIRST_COMPLETED)
        main_ok = main_f.done() and main_f.exception() is None
        if not main_ok and lite_f.done() and lite_f.exception() is None:
            main, meta = lite_f.result()
            meta, from_main = {**meta, "fallback": "main reader slow"}, False
        else:
            try:
                main, meta = main_f.result()
            except GeminiError:
                main, meta = lite_f.result()
                meta["fallback"], from_main = True, False
    if from_main:
        try:
            lite, _ = lite_f.result(timeout=SECOND_READER_WAIT)
        except (GeminiError, FuturesTimeout):
            lite = None
    lite_texts = [i.get("brand_text", "") for i in lite.get("items", [])] if lite else None
    for it in main.get("items", []):
        it["agree"] = name_agreement(it.get("brand_text", ""), lite_texts) if lite_texts is not None else None
    return {"kind": main.get("kind", "other"), "doctor_text": main.get("doctor_text", ""),
            "date_text": main.get("date_text", ""), "items": main.get("items", []), "image": small,
            "size": size, "meta": meta}
