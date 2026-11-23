"""Candidate generation: the top-K real registry products for one messy reading.

Retrieve-then-rerank, step 1 (recall). Signals:
- character n-gram TF-IDF cosine over all 13,627 brand names (tolerant to OCR and handwriting errors);
- a phonetic key (Metaphone) match bonus;
- Bangla-script input transliterated to Latin first (নাপা -> napa), plus a curated Bangla name table when present;
- strength and dosage-form hints then order each brand's products.
Rerankers (R1/R2/R3) pick the final answer from this list; nothing outside the list can ever be chosen.
"""
from __future__ import annotations

import csv
import os
import re
import unicodedata
from dataclasses import dataclass, field

import jellyfish
import numpy as np
from rapidfuzz import fuzz, process
from sklearn.feature_extraction.text import TfidfVectorizer

from .graph import ROOT, Graph, brand_key

BN_MAP = {
    "অ": "o", "আ": "a", "ই": "i", "ঈ": "i", "উ": "u", "ঊ": "u", "ঋ": "ri", "এ": "e", "ঐ": "oi", "ও": "o", "ঔ": "ou",
    "ক": "k", "খ": "kh", "গ": "g", "ঘ": "gh", "ঙ": "ng", "চ": "c", "ছ": "ch", "জ": "j", "ঝ": "jh", "ঞ": "n",
    "ট": "t", "ঠ": "th", "ড": "d", "ঢ": "dh", "ণ": "n", "ত": "t", "থ": "th", "দ": "d", "ধ": "dh", "ন": "n",
    "প": "p", "ফ": "f", "ব": "b", "ভ": "bh", "ম": "m", "য": "j", "র": "r", "ল": "l", "শ": "sh", "ষ": "sh",
    "স": "s", "হ": "h", "ড়": "r", "ঢ়": "rh", "য়": "y", "ৎ": "t", "ং": "ng", "ঃ": "h", "ঁ": "",
    "া": "a", "ি": "i", "ী": "i", "ু": "u", "ূ": "u", "ৃ": "ri", "ে": "e", "ৈ": "oi", "ো": "o", "ৌ": "ou", "্": "",
    "০": "0", "১": "1", "২": "2", "৩": "3", "৪": "4", "৫": "5", "৬": "6", "৭": "7", "৮": "8", "৯": "9",
}
# Form words, abbreviated or in full; each also matches its plural ('tablets', 'Capsules'). The photo reader writes
# the form out in full, and left in the name these words were matched as letters (tablets -> Nitalet).
FORM_WORDS = {"tab": "tablet", "tablet": "tablet", "cap": "capsule", "capsule": "capsule", "syp": "syrup",
              "syrup": "syrup", "susp": "suspension", "suspension": "suspension", "inj": "injection",
              "injection": "injection", "drop": "drops", "cream": "cream", "gel": "gel", "ointment": "ointment",
              "solution": "solution", "sachet": "sachet", "powder": "powder", "lotion": "lotion", "spray": "spray",
              "inhaler": "inhaler", "suppository": "suppository", "suppositorie": "suppository", "oral": None,
              "film coated": None, "chewable": None, "effervescent": None}
_NUM = re.compile(r"(\d+(?:\.\d+)?)")


# য়, ড়, ঢ় are stored as a letter plus a dot below (U+09BC), even after NFC; the dot used to stay in the text and split
# the word ('এক্সিয়াম' -> 'eksij am'). Brand names are English words written in Bangla letters, so the common loan-word
# spellings map back: ক্স is x (এক্সিয়াম Exium, ম্যাক্সপ্রো Maxpro, ফেক্সো Fexo), িয়া is ia, অ্যা / ্যা is a (অ্যালাট্রল).
_BN_PAIRS = [("ক্স", "x"), ("িয়া", "ia"), ("য়", "y"), ("ড়", "r"), ("ঢ়", "rh"), ("অ্যা", "a"),
             ("্যা", "a"), ("্য", ""), ("়", "")]
# Units said or typed in Bangla, so they are read as units and not as letters of the name ('5 এমজি' -> '5 mg').
_BN_UNITS = [("মাইক্রোগ্রাম", "mcg"), ("এমসিজি", "mcg"), ("মিলিগ্রাম", "mg"), ("মিগ্রা", "mg"), ("এমজি", "mg"),
             ("এমএল", "ml"), ("মিলি", "ml"), ("গ্রাম", "g")]


def transliterate(text: str) -> str:
    t = unicodedata.normalize("NFC", text or "")
    for bn, lat in _BN_UNITS:
        t = re.sub(rf"(?<=[\s0-9০-৯]){bn}\.?(?![ঀ-৿])", " " + lat, t)
    for bn, lat in _BN_PAIRS:
        t = t.replace(bn, lat)
    return "".join(BN_MAP.get(ch, ch) for ch in t)


_DIGIT_AS_LETTER = {"0": "o", "1": "l", "5": "s"}


# Words that say WHEN to take a medicine, typed after its name ("Seclo 20 রাতে", "Napa 500 after meals"). None of
# them is a word inside a registry brand name. Without this, রাতে was transliterated to "rate" and matched Encorate.
SCHEDULE_WORDS = {
    "রাতে", "রাত", "সকালে", "সকাল", "দুপুরে", "দুপুর", "বিকালে", "বিকেলে", "সন্ধ্যায়", "দিনে", "প্রতিদিন", "রোজ",
    "একবার", "দুইবার", "দুবার", "তিনবার", "চারবার", "বার", "খাবারের", "খাবার", "আগে", "পরে", "পর", "খালি", "ভরা",
    "পেটে", "ঘুমানোর", "করে", "ও", "আর", "দিন", "সপ্তাহ", "মাস", "চলবে",
    "night", "nightly", "morning", "noon", "evening", "daily", "once", "twice", "thrice", "after", "before", "meal",
    "meals", "food", "bedtime", "empty", "stomach", "days", "weeks", "months", "and",
}
# Dose abbreviations are also parts of real brands (Avloclav BID, Umactin BD, Glunor OD), so they are dropped only
# after a number: "Napa 500 BD" is a schedule, "Avloclav BID" is a name.
SCHEDULE_ABBR = {"od", "qd", "bd", "bid", "tds", "tid", "qid", "qds", "hs"}


def drop_schedule_words(reading: str) -> str:
    """Remove schedule words typed after a medicine name; the first word is never removed."""
    tokens = reading.split()
    keep, seen_number = tokens[:1], bool(tokens and re.search(r"[0-9০-৯]", tokens[0]))
    for i, tok in enumerate(tokens[1:], start=1):
        word = tok.strip(".,;:()").lower()
        nxt = tokens[i + 1].strip(".,;:()").lower() if i + 1 < len(tokens) else ""
        if word in SCHEDULE_WORDS or (seen_number and word in SCHEDULE_ABBR) or (word == "at" and nxt in SCHEDULE_WORDS):
            continue
        seen_number = seen_number or bool(re.search(r"[0-9০-৯]", tok))
        keep.append(tok)
    return " ".join(keep)


def parse_hints(reading: str) -> tuple[str, str | None, str | None]:
    """Split a reading into (name part, strength number, form) e.g. 'Tab. Napa 500' -> ('napa', '500', 'tablet')."""
    t = transliterate(drop_schedule_words(reading)).lower()
    form = None
    for w, f in FORM_WORDS.items():
        pat = rf"\b{w}s?\b\.?"
        if re.search(pat, t):
            form = f or form
            t = re.sub(pat, " ", t)
    # remove the dosing schedule and duration first, so "Ace 500 1+0+1" keeps 500 as the strength, not 1
    t = re.sub(r"(?:½|\d+(?:\.\d+)?)\s*[+\-–]\s*(?:½|\d+(?:\.\d+)?)\s*[+\-–]\s*(?:½|\d+(?:\.\d+)?)", " ", t)
    t = re.sub(r"\b(?:x\s*)?\d+\s*(?:din|days?|d|mas|months?)\b", " ", t)
    # a single digit misread for a letter inside a name: 'Sec1o' -> 'seclo', 'Maxpr0' -> 'maxpro'
    # (a strength is several digits or stands apart: 'Napa500', 'Rosuva 10' are left alone)
    t = re.sub(r"(?<=[a-z])([015])(?=[a-z])", lambda m: _DIGIT_AS_LETTER[m.group(1)], t)
    t = re.sub(r"(?<=[a-z]{3})([01])\b", lambda m: _DIGIT_AS_LETTER[m.group(1)], t)
    unit = re.search(r"(\d+(?:\.\d+)?)\s*(?:mg|gm|g|ml|mcg)\b", t)
    nums = _NUM.findall(t)
    strength = unit.group(1) if unit else (nums[0] if nums else None)
    name = re.sub(r"\d+(\.\d+)?\s*(mg|gm|g|ml|mcg)?", " ", t)
    name = re.sub(r"[^a-z\s]+", " ", name)
    return re.sub(r"\s+", " ", name).strip(), strength, form


@dataclass
class Candidate:
    product_id: int
    brand: str
    strength: str
    form: str
    manufacturer: str
    generic: str
    name_score: float
    phonetic_match: bool
    strength_match: bool
    form_match: bool
    rank: int = 0
    extra: dict = field(default_factory=dict)


class CandidateIndex:
    def __init__(self, graph: Graph | None = None, bn_names_csv: str | None = None, local_aliases_csv: str | None = None):
        self.g = graph or Graph()
        rows = self.g.con.execute("SELECT DISTINCT brand FROM product").fetchall()
        self.brands = [r[0] for r in rows]
        self.keys = [brand_key(b) for b in self.brands]
        self.vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), lowercase=True, sublinear_tf=True)
        self.mat = self.vec.fit_transform([b.lower() for b in self.brands])
        self.phon = [jellyfish.metaphone(k) if k else "" for k in self.keys]
        self.bn_alias: dict[str, str] = {}
        path = bn_names_csv or os.path.join(ROOT, "data", "curated", "bn_names.csv")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    if r.get("bangla") and r.get("brand"):
                        self.bn_alias[unicodedata.normalize("NFC", r["bangla"].strip())] = r["brand"].strip()
        # Local spellings added on-site (data/curated/aliases_local.csv: alias,brand,note). A target that is not a real
        # registry brand is skipped and reported, never trusted.
        self.alias_errors: list[str] = []
        local = local_aliases_csv or os.path.join(ROOT, "data", "curated", "aliases_local.csv")
        known = set(self.brands)
        if os.path.exists(local):
            with open(local, encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    alias, brand = (r.get("alias") or "").strip(), (r.get("brand") or "").strip()
                    if not alias or not brand:
                        continue
                    if brand not in known:
                        self.alias_errors.append(f"{alias} -> {brand}: not a registry brand")
                        continue
                    self.bn_alias[unicodedata.normalize("NFC", alias)] = brand
        self._aliases_by_length = sorted(self.bn_alias, key=len, reverse=True)

    def apply_alias(self, raw: str) -> str:
        """Replace a known spelling at the start of the reading ('নাপা ৫০০ ১+০+১' -> 'Napa ৫০০ ১+০+১')."""
        for alias in self._aliases_by_length:
            if raw == alias or raw.startswith(alias + " "):
                return self.bn_alias[alias] + raw[len(alias):]
        return raw

    def top_brands(self, name: str, k: int = 30) -> list[tuple[str, float, bool]]:
        """Union of two retrievers: char n-gram TF-IDF cosine and edit-distance similarity (rapidfuzz), plus a phonetic bonus."""
        if not name:
            return []
        q = self.vec.transform([name])
        sims = (self.mat @ q.T).toarray().ravel()
        idx = set(np.argpartition(-sims, min(k, len(sims) - 1))[:k].tolist())
        nk = brand_key(name)
        for _, _, i in process.extract(nk, self.keys, scorer=fuzz.ratio, limit=k):
            idx.add(i)
        qp = jellyfish.metaphone(nk) if nk else ""
        scored = []
        for i in idx:
            edit = fuzz.ratio(nk, self.keys[i]) / 100.0
            ph = bool(qp) and self.phon[i] == qp
            scored.append((max(float(sims[i]), edit) + (0.15 if ph else 0.0), i, max(float(sims[i]), edit), ph))
        scored.sort(key=lambda x: -x[0])
        return [(self.brands[i], s, ph) for _, i, s, ph in scored[:k]]

    def search(self, reading: str, k: int = 20) -> list[Candidate]:
        raw = unicodedata.normalize("NFC", reading or "").strip()
        name, strength, form = parse_hints(self.apply_alias(raw))
        out: list[Candidate] = []
        for brand, sim, ph in self.top_brands(name, k=max(k, 30)):
            for p in self.g.products_by_brand(brand):
                s_ok = bool(strength) and strength in re.sub(r"\s", "", p.strength or "")
                f_ok = bool(form) and form in (p.form or "").lower()
                out.append(Candidate(p.id, p.brand, p.strength, p.form, p.manufacturer, p.generic, sim, ph, s_ok, f_ok))
        def oral_prior(c: Candidate) -> float:
            # when the form is not written, the common oral forms are the safer default (tablet, then capsule)
            if form:
                return 0.0
            f = (c.form or "").lower()
            return 0.03 if f.startswith("tablet") else 0.02 if f.startswith("capsule") else 0.0

        out.sort(key=lambda c: (-(c.name_score + 0.15 * c.phonetic_match + 0.2 * c.strength_match + 0.05 * c.form_match
                                  + oral_prior(c)), c.product_id))
        for i, c in enumerate(out[:k]):
            c.rank = i + 1
        return out[:k]
