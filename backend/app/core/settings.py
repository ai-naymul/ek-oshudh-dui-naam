"""Switches that can be changed on-site without touching code: config/settings.json (repo root).

Only the keys present in the file override the defaults below; a missing or partial file is fine.
"""
from __future__ import annotations

import copy
import json
import os

from .graph import ROOT
from .rules import RULE_DEFAULTS

SETTINGS_PATH = os.path.join(ROOT, "config", "settings.json")
DEFAULTS = {
    "matching": {
        "auto_accept_threshold": None,   # None = use the threshold chosen by the evaluation (models/policy.json)
        "always_confirm": False,         # True = every reading waits for the family's tap, even exact names
    },
    "rules": dict(RULE_DEFAULTS),
}


def _merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (extra or {}).items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load_settings(path: str | None = None) -> dict:
    path = path or SETTINGS_PATH
    data = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
    return _merge(DEFAULTS, {k: v for k, v in data.items() if not k.startswith("_")})
