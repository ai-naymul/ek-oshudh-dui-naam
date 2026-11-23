"""Voice in and out.

In:  the phone records a voice note -> Gemini 3.8 Flash hears it and returns the transcript (shown to the user
     verbatim) and the medicine names said (schema only, it never picks a product). Fallback when that call fails:
     gemini-3.5-transcribe writes the words, then Flash-Lite lists the medicines.
     -> each mention goes through the same catalog matcher as photos and typed text, then the user confirms.
Out: the Bangla template text of the findings -> gemini-3.8-flash-tts -> WAV played in the browser.
     Only the case's own findings are spoken, so the endpoint cannot be used to speak arbitrary text.
"""
from __future__ import annotations

import re

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
    "The English letters must spell the same sounds that were said: never replace a name with a different brand you "
    "know, even one with the same medicine inside. Do not add medicines that were not said.\n\nTranscript:\n"
)

# The voice note itself goes to the reader model: it hears the sound in the context of medicine names, instead of
# guessing a spelling from a transcript (the transcript-then-extract path wrote 'Esomep' for a spoken Exium and
# 'Deslor' for Des, other brands of the same medicine). The old two-step path stays as the fallback.
HEAR_MODEL = "gemini-3.8-flash"
# The transcript is written FIRST (Gemini otherwise fills fields alphabetically): listing medicines before writing down
# everything said dropped names (1 of 3 in 3 of 8 test runs; 3 of 3 in 12 of 12 with this order).
HEAR_SCHEMA = {"type": "object", "properties": {"transcript": {"type": "string"}, **EXTRACT_SCHEMA["properties"]},
               "required": ["transcript", "items"], "propertyOrdering": ["transcript", "items"]}
HEAR_SCHEMA["properties"]["items"] = {**EXTRACT_SCHEMA["properties"]["items"], "items": {
    **EXTRACT_SCHEMA["properties"]["items"]["items"],
    "propertyOrdering": ["name_as_said", "name_english_letters", "strength_text", "schedule_text"]}}
_STRENGTH = re.compile(r"[0-9০-৯]+(?:[.,][0-9০-৯]+)?\s*(?:mcg|mg|ml|gm|g|এমসিজি|মাইক্রোগ্রাম|মিলিগ্রাম|মিগ্রা|এমজি|এমএল|মিলি|গ্রাম)?",
                       re.IGNORECASE)


def _tidy(item: dict) -> dict:
    """A model can loop inside one field (once 2,000+ characters of '20 mg, ২০mg, ...'); keep what was said:
    the first strength, and a short schedule."""
    m = _STRENGTH.search(item.get("strength_text") or "")
    return {**item, "strength_text": m.group(0).strip() if m else "", "schedule_text": (item.get("schedule_text") or "")[:60]}
HEAR_PROMPT = (
    "Listen to this voice note from a person in Bangladesh about the medicines they or their family take. Write the "
    "transcript exactly as spoken (Bangla script; English words as said). Then list every medicine name said, in order. "
    "For each: the name as said (as in the transcript), the same name in English letters as it is printed on a "
    "Bangladeshi medicine strip, the strength if said (e.g. 20 mg) and how often if said (e.g. 1+0+1, দিনে ২ বার, রাতে). "
    "Write what you hear: never replace a name with a different brand you know, even one with the same medicine "
    "inside. Do not add medicines that were not said."
)
HEAR_TIMEOUT, HEAR_RETRIES = 45, 1


def hear(data: bytes, mime: str) -> tuple[str, list[dict], dict]:
    """Voice note -> (transcript, medicine mentions, meta). One call with the audio; if the reader fails or refuses,
    the speech-to-text model writes the words and Flash-Lite lists the medicines (meta['fallback'] = True)."""
    import base64
    from app.ai.gemini import GeminiError
    mime = mime.split(";")[0].strip().lower()
    if mime not in AUDIO_TYPES:
        raise ValueError(f"unsupported audio type {mime}")
    audio = {"inline_data": {"mime_type": mime, "data": base64.b64encode(data).decode()}}
    try:
        out, meta = generate([{"text": HEAR_PROMPT}, audio], HEAR_MODEL, HEAR_SCHEMA, "low", HEAR_RETRIES, HEAR_TIMEOUT,
                             optional=True)
        items = [_tidy(i) for i in out.get("items", []) if (i.get("name_as_said") or i.get("name_english_letters"))]
        return (out.get("transcript") or "").strip(), items, {**meta, "fallback": False}
    except GeminiError:
        transcript, m1 = audio_to_text(data, mime)
        found, m2 = mentions(transcript)
        return transcript, [_tidy(i) for i in found], {"model": f"{m1.get('model')} + {m2.get('model')}", "fallback": True}


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


def findings_speech(findings: list[dict], unchecked: int = 0) -> str:
    """Bangla script for the voice reply, built only from the template findings (red first, then amber).
    Medicines still waiting for confirmation are said out loud: the reply never sounds like an all-clear for them."""
    order = {"red": 0, "amber": 1, "info": 2}
    chosen = sorted([f for f in findings if f["severity"] in ("red", "amber")], key=lambda f: order[f["severity"]])[:4]
    from app.core.explain_bn import bn_num, load_copy
    s = load_copy()["speech"]
    pending = s["unchecked"].format(n=bn_num(unchecked)) if unchecked else ""
    if not chosen:
        return pending + s["show"] if unchecked else s["none"]
    head = s["head_red"] if chosen[0]["severity"] == "red" else s["head_amber"]
    return head + " ".join(f["bn"] for f in chosen) + (" " + pending if pending else "")


def speak_bn(text: str) -> tuple[bytes, str, dict]:
    (audio, mime), meta = speak(text, TTS_MODEL, VOICE)
    return audio, mime, meta
