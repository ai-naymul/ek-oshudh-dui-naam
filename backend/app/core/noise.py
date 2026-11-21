"""Realistic reading noise for brand names, used by tests (candidate recall) and by decision-model training.

It imitates what OCR and handwriting readers get wrong: look-alike letters (rn↔m, l↔1, o↔0),
dropped/doubled/swapped letters, missing spaces, dosage-form prefixes and strength suffixes.
"""
from __future__ import annotations

import random

CONFUSIONS = [("rn", "m"), ("m", "rn"), ("l", "1"), ("i", "l"), ("o", "0"), ("a", "o"), ("e", "c"), ("u", "v"),
              ("n", "h"), ("c", "e"), ("t", "f"), ("b", "h"), ("g", "q"), ("s", "5"), ("z", "2"), ("x", "k")]
PREFIXES = ["", "", "", "Tab. ", "Tab ", "Cap. ", "T. ", "Syp. "]


def corrupt(name: str, rng: random.Random, strength: str | None = None, edits: int | None = None) -> str:
    s = name
    n = edits if edits is not None else rng.choice([0, 1, 1, 1, 2, 2, 3])
    for _ in range(n):
        if len(s) < 2:
            break
        op = rng.random()
        i = rng.randrange(len(s))
        if op < 0.35:
            a, b = rng.choice(CONFUSIONS)
            j = s.lower().find(a)
            s = s[:j] + b + s[j + len(a):] if j >= 0 else s[:i] + s[i + 1:]
        elif op < 0.55:
            s = s[:i] + s[i + 1:]
        elif op < 0.70:
            s = s[:i] + s[i] + s[i:]
        elif op < 0.85 and i < len(s) - 1:
            s = s[:i] + s[i + 1] + s[i] + s[i + 2:]
        else:
            s = s.replace(" ", "")
    case = rng.random()
    s = s.upper() if case < 0.3 else s.lower() if case < 0.5 else s
    out = rng.choice(PREFIXES) + s
    if strength and rng.random() < 0.5:
        out += " " + strength.split()[0]
    return out
