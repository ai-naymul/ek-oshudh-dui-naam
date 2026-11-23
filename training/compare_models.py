"""Why LightGBM: the same 14 features, the same training rows, the same threshold rule, four model families.

Every model is trained on exactly what R2 was trained on (Flash-Lite readings of the 3,120 train images + 3,000 noisy
registry names, training/train_decider.py::build), picks its accept threshold on the validation split with the same
rule (95% upper bound of wrong automatic accepts <= 2%, training/eval_policy.py::fit) and is scored once on the 780 test
words read by Gemini 3.8 Flash. No AI calls: the saved readings are reused. Output: eval/reports/model_comparison.json.

Run from backend/:  uv run --group training python ../training/compare_models.py
"""
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "backend"))
import eval_policy as ep  # noqa: E402
import train_decider as td  # noqa: E402
from app.core.candidates import CandidateIndex  # noqa: E402
from app.core.decide import features, gather, products_per_brand  # noqa: E402

READER = "gemini-3.8-flash"


def readings(reader, split):
    recs = [json.loads(l) for l in open(os.path.join(ep.OUT, f"hw_readings_{reader}.jsonl"), encoding="utf-8")]
    return list({r["file"]: r for r in recs if r.get("split") == split and "text" in r}.values())


def rows_for(model_predict, idx, ppb, recs):
    """The rows eval_policy.evaluate/fit expect, for the decision model alone (R2 policy; no AI pick)."""
    out = []
    for rec in recs:
        cands, alt_sets = gather(idx, rec["text"], rec.get("alternatives", []))
        feats = features(rec["text"], rec.get("alternatives", []), cands, alt_sets, ppb)
        ranked = []
        if feats:
            probs = model_predict(np.array([f for _, f in feats], dtype=float))
            ranked = sorted(((c.brand, float(p)) for (c, _), p in zip(feats, probs)), key=lambda x: -x[1])
        out.append({"split": rec.get("split"), "file": rec["file"], "label": rec["label"], "r2": ranked[:5],
                    "r1": None, "r1_conf": 0.0, "r3": None, "r3_conf": 0.0,
                    "in_list": ep.low(rec["label"]) in {ep.low(c.brand) for c in cands}})
    return out


def main():
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.neural_network import MLPClassifier
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    idx = CandidateIndex()
    ppb = products_per_brand(idx.g)
    by = {s: [r for r in td.load_readings() if r["split"] == s] for s in ("train", "validation", "test")}
    X, y, _, _ = td.build(idx, ppb, by["train"], idx.brands, 3000, seed=1)
    X, y = np.array(X, dtype=float), np.array(y)
    val, test = readings(READER, "validation"), readings(READER, "test")
    print(f"training rows {len(y)} ({int(y.sum())} correct candidates); validation {len(val)}, test {len(test)} words")

    from app.core.decide import Decider
    models = {
        "LightGBM (shipped model file)": lambda: Decider().model,
        "LightGBM (retrained here)": lambda: td.train(X, y),
        "Logistic regression": lambda: make_pipeline(StandardScaler(), LogisticRegression(max_iter=5000)).fit(X, y),
        "Random forest": lambda: RandomForestClassifier(n_estimators=300, min_samples_leaf=20, n_jobs=-1,
                                                        random_state=0).fit(X, y),
        "Neural network (MLP 32-16)": lambda: make_pipeline(StandardScaler(), MLPClassifier(
            hidden_layer_sizes=(32, 16), max_iter=500, early_stopping=True, random_state=0)).fit(X, y),
    }
    report = {"reader": READER, "rule": "threshold on validation: 95% upper bound of wrong auto-accepts <= 2%",
              "training_rows": int(len(y)), "n_validation": len(val), "n_test": len(test), "models": {}}
    for name, make in models.items():
        t0 = time.time()
        m = make()
        fit_s = time.time() - t0
        predict = m.predict if name.startswith("LightGBM") else (lambda Z, m=m: m.predict_proba(Z)[:, 1])
        vrows, trows = rows_for(predict, idx, ppb, val), rows_for(predict, idx, ppb, test)
        pol, _ = ep.fit(vrows, "R2")
        ev, ev_a = ep.evaluate(trows, pol), ep.evaluate(ep.audited(trows), pol)
        res = {"top1_test": ep.top1(trows)["R2"], "top1_test_audited": ep.top1(ep.audited(trows))["R2"],
               "threshold": pol["t"], "auto_accept": ev["auto_accept_coverage"], "wrong_auto": ev["wrong_n"],
               "accepted": ev["accepted_n"], "wrong_auto_audited": ev_a["wrong_n"],
               "right_in_top3_if_asked": ev["asked_in_top3"], "train_seconds": round(fit_s, 1)}
        report["models"][name] = res
        print(f"{name:30s} top-1 {res['top1_test']:.3f} | auto {res['auto_accept']:.3f} at t={pol['t']} "
              f"({res['wrong_auto']} of {res['accepted']} wrong) | {fit_s:.1f}s")
    path = os.path.join(ep.ROOT, "eval", "reports", "model_comparison.json")
    json.dump(report, open(path, "w", encoding="utf-8"), indent=1)
    print("wrote", path)


if __name__ == "__main__":
    main()
