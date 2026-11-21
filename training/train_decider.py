"""Train R2 (LightGBM decision model) and run E1: R1 vs R2 vs R3 vs R2->R3 on held-out handwriting.

Data:
- real pairs: Gemini readings of the handwriting train split (+ validation for thresholds), label = true brand
- synthetic pairs: noisy versions of registry brands (app/core/noise.py), so the model sees more than 78 names
Evaluations (both reported):
- A: official test split (same 78 names, unseen handwriting images)
- B: name-disjoint (train on 52 names, test on 26 names never seen in training) -> generalisation to new brands
Outputs: models/decider.txt, models/policy.json (threshold for <= 2% wrong auto-accepts on validation),
training/out/e1_full_report.json.

Run from backend/:  uv run --group training python ../training/train_decider.py
"""
import collections
import json
import os
import random
import sys

import lightgbm as lgb
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from app.core.candidates import CandidateIndex  # noqa: E402
from app.core.decide import FEATURES, features, gather  # noqa: E402
from app.core.noise import corrupt  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(ROOT, "training", "out")


def load_readings(model="gemini-3.1-flash-lite"):
    recs = {}
    for line in open(os.path.join(OUT, f"hw_readings_{model}.jsonl"), encoding="utf-8"):
        r = json.loads(line)
        if "text" in r:
            recs[(r["split"], r["file"])] = r
    return list(recs.values())


def make_rows(idx, ppb, reading, alts, label):
    cands, alt_sets = gather(idx, reading, alts)
    rows = features(reading, alts, cands, alt_sets, ppb)
    return [(c.brand, f, int(c.brand.lower() == label.lower())) for c, f in rows]


def build(idx, ppb, recs, synth_names=(), synth_n=0, seed=0):
    X, y, groups, meta = [], [], [], []
    for r in recs:
        rows = make_rows(idx, ppb, r["text"], r.get("alternatives", []), r["label"])
        if not rows:
            continue
        for b, f, lab in rows:
            X.append(f); y.append(lab)
        groups.append(len(rows)); meta.append((r["label"], [b for b, _, _ in rows]))
    rng = random.Random(seed)
    for name in rng.sample(list(synth_names), min(synth_n, len(synth_names))):
        rows = make_rows(idx, ppb, corrupt(name, rng), [], name)
        for b, f, lab in rows:
            X.append(f); y.append(lab)
        groups.append(len(rows)); meta.append((name, [b for b, _, _ in rows]))
    return np.array(X, dtype=float), np.array(y), groups, meta


def train(X, y):
    params = dict(objective="binary", learning_rate=0.05, num_leaves=15, min_data_in_leaf=20, feature_fraction=0.9,
                  bagging_fraction=0.9, bagging_freq=1, verbose=-1, seed=7)
    return lgb.train(params, lgb.Dataset(X, y, feature_name=FEATURES), num_boost_round=300)


def evaluate(model, X, groups, meta):
    """Per reading: top-1 by R2 probability, its confidence, and R1 (rank-1 candidate) for comparison."""
    probs = model.predict(X) if len(X) else []
    out, i = [], 0
    for g, (label, brands) in zip(groups, meta):
        p = probs[i:i + g]
        j = int(np.argmax(p))
        out.append({"label": label, "r2_ok": brands[j].lower() == label.lower(), "r2_conf": float(p[j]),
                    "r1_ok": brands[0].lower() == label.lower(), "in_list": label.lower() in [b.lower() for b in brands]})
        i += g
    return out


def risk_coverage(rows, conf, ok):
    rows = sorted(rows, key=lambda r: -r[conf])
    return {f"{int(c*100)}%": round(1 - sum(r[ok] for r in rows[:max(1, int(len(rows)*c))]) / max(1, int(len(rows)*c)), 3)
            for c in (1.0, 0.9, 0.8, 0.7, 0.6, 0.5)}


def threshold_for(rows, max_err=0.02):
    """Lowest confidence threshold whose accepted set has <= max_err errors (on validation)."""
    rows = sorted(rows, key=lambda r: -r["r2_conf"])
    best, wrong = 1.01, 0
    for k, r in enumerate(rows, 1):
        wrong += not r["r2_ok"]
        if wrong / k <= max_err:
            best = r["r2_conf"]
    return best


def summary(rows):
    n = len(rows)
    return {"n": n, "recall_list": round(sum(r["in_list"] for r in rows) / n, 3), "R1_top1": round(sum(r["r1_ok"] for r in rows) / n, 3),
            "R2_top1": round(sum(r["r2_ok"] for r in rows) / n, 3), "R2_error_at_coverage": risk_coverage(rows, "r2_conf", "r2_ok")}


def main():
    idx = CandidateIndex()
    ppb = collections.Counter(b for (b,) in idx.g._q("SELECT brand FROM product"))
    recs = load_readings()
    by = collections.defaultdict(list)
    for r in recs:
        by[r["split"]].append(r)
    report = {}
    # A: official split
    Xtr, ytr, _, _ = build(idx, ppb, by["train"], idx.brands, 3000, seed=1)
    model = train(Xtr, ytr)
    Xva, _, gva, mva = build(idx, ppb, by["validation"])
    val_rows = evaluate(model, Xva, gva, mva)
    thr = threshold_for(val_rows)
    Xte, _, gte, mte = build(idx, ppb, by["test"])
    test_rows = evaluate(model, Xte, gte, mte)
    acc = [r for r in test_rows if r["r2_conf"] >= thr]
    report["A_official_test"] = {**summary(test_rows), "threshold": round(thr, 4),
                                 "auto_accept_coverage": round(len(acc) / len(test_rows), 3),
                                 "auto_accept_error": round(1 - sum(r["r2_ok"] for r in acc) / max(1, len(acc)), 3)}
    # B: name-disjoint generalisation
    names = sorted({r["label"] for r in recs})
    rng = random.Random(42)
    rng.shuffle(names)
    held = set(names[: len(names) // 3])
    trB = [r for r in by["train"] + by["validation"] if r["label"] not in held]
    teB = [r for r in by["test"] if r["label"] in held]
    XtrB, ytrB, _, _ = build(idx, ppb, trB, [b for b in idx.brands if b not in held], 3000, seed=2)
    modelB = train(XtrB, ytrB)
    XteB, _, gteB, mteB = build(idx, ppb, teB)
    report["B_unseen_names"] = {**summary(evaluate(modelB, XteB, gteB, mteB)), "held_out_names": len(held)}
    imp = dict(zip(FEATURES, model.feature_importance("gain").round(1).tolist()))
    report["feature_importance_gain"] = dict(sorted(imp.items(), key=lambda x: -x[1]))
    os.makedirs(os.path.join(ROOT, "models"), exist_ok=True)
    model.save_model(os.path.join(ROOT, "models", "decider.txt"))
    json.dump(report, open(os.path.join(OUT, "e1_full_report.json"), "w"), indent=1)
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
