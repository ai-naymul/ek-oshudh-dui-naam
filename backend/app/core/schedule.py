"""Parse a dosing schedule written on a Bangladeshi prescription or said in a voice note.

Handles: '1+0+1', '1-0-1', '১+০+১', '½+0+½'; 'দিনে ২ বার', 'দিনে দুইবার', 'twice daily'; 'সকালে/দুপুরে/রাতে ১টা' and
a time of day on its own ('রাতে', 'সকালে ও রাতে', 'at night');
BD/TDS/TID/OD/QID/HS/SOS/PRN; before/after meals; duration ('৭ দিন', 'x 7 days', '১ মাস', 'চলবে').
Deterministic: the same text always gives the same schedule.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass

BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
ABBR = {"od": 1, "qd": 1, "bd": 2, "bid": 2, "tds": 3, "tid": 3, "qid": 4, "qds": 4, "hs": 1}
_FRACTION = {"½": 0.5, "1/2": 0.5, "¼": 0.25, "1/4": 0.25}


@dataclass
class Schedule:
    morning: float | None = None
    noon: float | None = None
    night: float | None = None
    per_day: float | None = None
    as_needed: bool = False
    meal: str | None = None          # 'before' | 'after' | None
    days: int | None = None
    continuing: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def _num(tok: str) -> float:
    tok = tok.strip()
    if tok in _FRACTION:
        return _FRACTION[tok]
    return float(tok) if tok else 0.0


# Spoken numbers before 'বার/টা' (times/pieces) and English frequency words, turned into digits first.
_BN_NUM_WORDS = {"এক": "1", "দুই": "2", "দু": "2", "তিন": "3", "চার": "4"}
_EN_FREQ = {"once": "1 times", "twice": "2 times", "thrice": "3 times", "one time": "1 times", "two times": "2 times",
            "three times": "3 times", "four times": "4 times"}
# Time-of-day words: on their own they mean one dose at that time.
_SLOTS = (("সকালে", "morning"), ("সকাল", "morning"), ("দুপুরে", "noon"), ("দুপুর", "noon"), ("রাতে", "night"),
          ("রাত্রে", "night"), ("ঘুমানোর আগে", "night"), ("morning", "morning"), ("noon", "noon"), ("lunch", "noon"),
          ("night", "night"), ("bedtime", "night"))


def _words_to_digits(t: str) -> str:
    t = re.sub(r"(এক|দুই|দু|তিন|চার)\s*['’]?\s*(বার|টা|টি|টো)", lambda m: f"{_BN_NUM_WORDS[m.group(1)]} {m.group(2)}", t)
    for word, digits in _EN_FREQ.items():
        t = re.sub(rf"\b{word}\b", digits, t)
    return t


def parse(text: str) -> Schedule:
    t = _words_to_digits(unicodedata.normalize("NFC", text or "").translate(BN_DIGITS).lower())
    s = Schedule()
    m = re.search(r"(½|1/2|¼|\d+(?:\.\d+)?)\s*[+\-–]\s*(½|1/2|¼|\d+(?:\.\d+)?)\s*[+\-–]\s*(½|1/2|¼|\d+(?:\.\d+)?)", t)
    if m:
        s.morning, s.noon, s.night = (_num(g) for g in m.groups())
        s.per_day = s.morning + s.noon + s.night
    else:
        m = re.search(r"(?:দিনে|daily|a day|per day)?\s*(\d+)\s*(?:বার|times?|x)\s*(?:দিনে|daily|a day|per day)?", t)
        if m and re.search(r"দিনে|daily|a day|per day|বার", t):
            s.per_day = float(m.group(1))
        for word, slot in _SLOTS:
            if getattr(s, slot) is not None or word not in t:
                continue
            mm = re.search(rf"{word}\s*(\d+(?:\.\d+)?)", t)
            setattr(s, slot, float(mm.group(1)) if mm else 1.0)
        if s.per_day is None and any(v is not None for v in (s.morning, s.noon, s.night)):
            s.per_day = sum(v or 0 for v in (s.morning, s.noon, s.night))
        if s.per_day is None:
            for ab, n in ABBR.items():
                if re.search(rf"\b{ab}\b", t):
                    s.per_day = float(n)
                    if ab == "hs":
                        s.night = 1.0
                    break
    if re.search(r"\b(sos|prn)\b|প্রয়োজনে|দরকার হলে|as needed", t):
        s.as_needed = True
    if re.search(r"খাবারের?\s*আগে|before\s*(meal|food)|\bac\b|খালি পেটে", t):
        s.meal = "before"
    elif re.search(r"খাবারের?\s*পরে|after\s*(meal|food)|\bpc\b", t):
        s.meal = "after"
    d = re.search(r"(\d+)\s*(দিন|days?|d\b)", t)
    if d:
        s.days = int(d.group(1))
    else:
        mo = re.search(r"(\d+)\s*(মাস|months?)", t)
        if mo:
            s.days = int(mo.group(1)) * 30
    if re.search(r"চলবে|continue|cont\.", t):
        s.continuing = True
    return s
