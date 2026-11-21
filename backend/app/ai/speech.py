"""Voice in and out.

In:  the phone records a voice note -> gemini-3.5-transcribe writes the words down (shown to the user verbatim)
     -> Flash-Lite pulls out the medicines mentioned (schema only, it never names a product)
     -> each mention goes through the same catalog matcher as photos and typed text, then the user confirms.
Out: the Bangla template text of the findings -> gemini-3.8-flash-tts -> WAV played in the browser.
     Only the case's own findings are spoken, so the endpoint cannot be used to speak arbitrary text.
"""
from __future__ import annotations

from app.ai.gemini import LITE_MODEL, generate, speak, transcribe

TRANSCRIBE_MODEL = "gemini-3.5-transcribe"
TTS_MODEL = "gemini-3.8-flash-tts"
VOICE = "Kore"
AUDIO_TYPES = {"audio/webm", "audio/ogg", "audio/mp4", "audio/mpeg", "audio/wav", "audio/x-wav", "audio/aac", "audio/x-m4a"}

EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {"type": "object", "properties": {
        "name_as_said": {"type": "string"},
        "name_english_letters": {"type": "string"},
        "strength_text": {"type": "string"},
        "schedule_text": {"type": "string"},
    }, "required": ["name_as_said", "name_english_letters"]}}},
    "required": ["items"],
}
EXTRACT_PROMPT = (
    "This is what a person in Bangladesh said about the medicines they take. List every medicine mentioned, in order. "
    "For each: the name exactly as said, the same name written in English letters as it would appear on a Bangladeshi "
    "medicine strip, the strength if said (e.g. 500 mg), and how often it is taken if said (e.g. 1+0+1, দিনে ২ বার, রাতে). "
    "Do not add medicines that were not said and do not correct names into other medicines.\n\nTranscript:\n"
)


def audio_to_text(data: bytes, mime: str) -> tuple[str, dict]:
    mime = mime.split(";")[0].strip().lower()
    if mime not in AUDIO_TYPES:
        raise ValueError(f"unsupported audio type {mime}")
    import base64
    text, meta = transcribe([{"inline_data": {"mime_type": mime, "data": base64.b64encode(data).decode()}}], TRANSCRIBE_MODEL)
    return text.strip(), meta


def mentions(transcript: str) -> tuple[list[dict], dict]:
    if not transcript.strip():
        return [], {}
    out, meta = generate([{"text": EXTRACT_PROMPT + transcript}], model=LITE_MODEL, schema=EXTRACT_SCHEMA)
    return [i for i in out.get("items", []) if (i.get("name_as_said") or i.get("name_english_letters"))], meta


def findings_speech(findings: list[dict]) -> str:
    """Bangla script for the voice reply, built only from the template findings (red first, then amber)."""
    order = {"red": 0, "amber": 1, "info": 2}
    chosen = sorted([f for f in findings if f["severity"] in ("red", "amber")], key=lambda f: order[f["severity"]])[:4]
    if not chosen:
        return "আমাদের যাচাইয়ে বড় কোনো সমস্যা পাওয়া যায়নি। তবুও ওষুধের তালিকাটি ডাক্তার বা ফার্মাসিস্টকে দেখান।"
    head = "সতর্কতা। " if chosen[0]["severity"] == "red" else "খেয়াল রাখুন। "
    return head + " ".join(f["bn"] for f in chosen)


def speak_bn(text: str) -> tuple[bytes, str, dict]:
    (audio, mime), meta = speak(text, TTS_MODEL, VOICE)
    return audio, mime, meta
