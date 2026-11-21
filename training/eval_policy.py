"""E1 (final): which matcher ships? R1 fuzzy vs R2 decision model vs R3 constrained AI choice vs hybrid R2->R3.

Real Bangladeshi doctors' handwriting (78 medicine names, word images). The reader is a Gemini model; every method
only chooses among registry products, so none of them can invent a medicine name.

- Thresholds are chosen on the VALIDATION split (wrong automatic accepts <= 2%), then reported once on TEST.
- The policy that covers the most validation items within that error budget is written to models/policy.json,
  which the app loads at start-up. Nothing is tuned on test.
- Items below the threshold are not guessed: the app asks the user with the photo crop and the top-3 options.
  'asked_in_top3' says how often the right answer is among those three.

Run from backend/:  uv run --group training python ../training/eval_policy.py [reader_model]
R3 calls are cached in training/out/e1_policy_<reader>.jsonl, so a rerun only calls the API for missing rows.
"""
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from app.ai.gemini import GeminiError, image_part  # noqa: E402
from app.core.candidates import CandidateIndex  # noqa: E402
from app.core.decide import Decider, products_per_brand  # noqa: E402
from app.core.rerank import r1, r3  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(ROOT, "training", "out")
MAX_ERR = 0.02


def low(s):
    return (s or "").strip().lower()


def score_rows(reader, split, idx, dec, ppb):
    recs = [json.loads(l) for l in open(os.path.join(OUT, f"hw_readings_{reader}.jsonl"), encoding="utf-8")]
    recs = list({r["file"]: r for r in recs if r.get("split") == split and "text" in r}.values())
    cache_path = os.path.join(OUT, f"e1_policy_{reader}.jsonl")
    cache = {}
    if os.path.exists(cache_path):
        for line in open(cache_path, encoding="utf-8"):
            r = json.loads(line)
            cache[(r["split"], r["file"])] = r
    lock = threading.Lock()

    def one(rec):
        key = (split, rec["file"])
        cands, ranked = dec.rank_reading(idx, rec["text"], rec.get("alternatives", []), ppb)
        c1 = r1(cands)
        row = {"split": split, "file": rec["file"], "label": rec["label"],
               "in_list": low(rec["label"]) in {low(c.brand) for c in cands},
               "r1": c1.candidate.brand if c1.candidate else None, "r1_conf": c1.confidence,
               "r2": [[c.brand, round(p, 4)] for c, p in ranked[:5]]}
        if key in cache and cache[key].get("r2_top5_for_r3") == [b for b, _ in row["r2"]]:
            row.update({k: cache[key][k] for k in ("r3", "r3_conf")})
        else:
            try:
                img = image_part(os.path.join(ROOT, "data", "handwriting", "bd", split, rec["file"]))
                c3 = r3([img], [c for c, _ in ranked[:5]], k=5)
                row.update(r3=c3.candidate.brand if c3.candidate else None, r3_conf=c3.confidence)
            except GeminiError as e:
                row.update(r3=None, r3_conf=0.0, r3_error=str(e)[:100])
            with lock, open(cache_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({**row, "r2_top5_for_r3": [b for b, _ in row["r2"]]}) + "\n")
        return row

    with ThreadPoolExecutor(8) as ex:
        return list(ex.map(one, recs))


def decide(row, policy):
    """-> (accepted automatically?, answer brand, top-3 shown to the user if asked)."""
    r2top, p2 = (row["r2"][0] if row["r2"] else (None, 0.0))
    m = policy["method"]
    if m == "R1":
        acc, ans = row["r1_conf"] >= policy["t"], row["r1"]
    elif m == "R2":
        acc, ans = p2 >= policy["t"], r2top
    elif m == "R3":
        acc, ans = row["r3"] is not None and row["r3_conf"] >= policy["t"], row["r3"]
    else:  # R2+R3: sure by the decision model, or the AI's independent pick agrees with it
        agree = row["r3"] is not None and low(row["r3"]) == low(r2top)
        acc, ans = (p2 >= policy["t"]) or (agree and p2 >= policy["t_agree"]), r2top
    shown = ([row["r3"]] if row["r3"] else []) + [b for b, _ in row["r2"]]
    top3 = list(dict.fromkeys(shown))[:3]
    return acc, ans, top3


def evaluate(rows, policy):
    n = len(rows)
    acc_ok = acc_n = asked_in3 = asked_n = 0
    for r in rows:
        acc, ans, top3 = decide(r, policy)
        if acc:
            acc_n += 1
            acc_ok += low(ans) == low(r["label"])
        else:
            asked_n += 1
            asked_in3 += low(r["label"]) in {low(b) for b in top3}
    return {"auto_accept_coverage": round(acc_n / n, 3), "auto_accept_error": round(1 - acc_ok / max(1, acc_n), 3),
            "asked": round(asked_n / n, 3), "asked_in_top3": round(asked_in3 / max(1, asked_n), 3),
            "correct_if_user_picks_from_top3": round((acc_ok + asked_in3) / n, 3)}


def fit(rows, method):
    """Lowest thresholds on validation with auto-accept error <= MAX_ERR; maximise coverage."""
    grid = np.round(np.arange(0.0, 1.0001, 0.01), 2)
    best = None
    t_agree_grid = grid if method == "R2+R3" else [None]
    for ta in t_agree_grid[::5] if method == "R2+R3" else t_agree_grid:
        for t in grid:
            pol = {"method": method, "t": float(t), "t_agree": None if ta is None else float(ta)}
            ev = evaluate(rows, pol)
            if ev["auto_accept_error"] <= MAX_ERR and (best is None or ev["auto_accept_coverage"] > best[1]["auto_accept_coverage"]):
                best = (pol, ev)
    return best or ({"method": method, "t": 1.01, "t_agree": 1.01}, evaluate(rows, {"method": method, "t": 1.01, "t_agree": 1.01}))


def top1(rows):
    n = len(rows)
    return {"recall_list": round(sum(r["in_list"] for r in rows) / n, 3),
            "R1": round(sum(low(r["r1"]) == low(r["label"]) for r in rows) / n, 3),
            "R2": round(sum(bool(r["r2"]) and low(r["r2"][0][0]) == low(r["label"]) for r in rows) / n, 3),
            "R3": round(sum(low(r["r3"]) == low(r["label"]) for r in rows) / n, 3)}


def main():
    reader = sys.argv[1] if len(sys.argv) > 1 else "gemini-3.8-flash"
    idx = CandidateIndex()
    dec = Decider()
    ppb = products_per_brand(idx.g)
    val = score_rows(reader, "validation", idx, dec, ppb)
    test = score_rows(reader, "test", idx, dec, ppb)
    report = {"reader": reader, "n_validation": len(val), "n_test": len(test), "max_auto_error": MAX_ERR,
              "top1_test": top1(test), "top1_validation": top1(val), "policies": {}}
    for method in ("R1", "R2", "R3", "R2+R3"):
        pol, ev_val = fit(val, method)
        report["policies"][method] = {"thresholds": pol, "validation": ev_val, "test": evaluate(test, pol)}
    chosen = max(report["policies"], key=lambda m: report["policies"][m]["validation"]["auto_accept_coverage"])
    report["chosen"] = chosen
    train_rep = os.path.join(OUT, "e1_full_report.json")
    if os.path.exists(train_rep):
        report["decision_model_training"] = json.load(open(train_rep))
    json.dump(report, open(os.path.join(OUT, f"e1_policy_report_{reader}.json"), "w"), indent=1)
    p = report["policies"][chosen]
    policy = {"method": chosen, "reader": reader, "r2_accept": p["thresholds"]["t"], "agree_min": p["thresholds"]["t_agree"],
              "max_auto_error": MAX_ERR, "chosen_on": "validation split (most items auto-accepted within the error budget)",
              "test": p["test"], "top1_test": report["top1_test"]}
    json.dump(policy, open(os.path.join(ROOT, "models", "policy.json"), "w"), indent=1)
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
