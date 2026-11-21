"""E1 matching evaluation on real handwriting (held-out test split).

For each test word: reader text (+ alternatives) -> candidates -> R1 / R3 (/ R2 when trained).
Reports top-1 accuracy, recall@20, and wrong-auto-accept rate at several coverage levels (risk-coverage).
Results are cached in training/out/e1_<reader>.jsonl so reruns only call the API for missing rows.

Run from backend/:  uv run --group training python ../training/eval_matching.py [reader_model]
"""
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from app.ai.gemini import GeminiError, image_part  # noqa: E402
from app.core.candidates import CandidateIndex  # noqa: E402
from app.core.rerank import r1, r3  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def candidates_for(idx, rec, k=20):
    cands = idx.search(rec["text"], k)
    seen = {c.product_id for c in cands}
    for alt in rec.get("alternatives", [])[:3]:
        for c in idx.search(alt, k):
            if c.product_id not in seen:
                cands.append(c)
                seen.add(c.product_id)
    return cands


def risk_coverage(rows, key_conf, key_ok):
    """Sort by confidence; for each coverage level report the error rate among accepted items."""
    rows = sorted(rows, key=lambda r: -r[key_conf])
    out = {}
    for cov in (1.0, 0.9, 0.8, 0.7, 0.6, 0.5):
        k = max(1, int(len(rows) * cov))
        acc = rows[:k]
        out[f"{int(cov*100)}%"] = round(1 - sum(r[key_ok] for r in acc) / k, 3)
    return out


def main():
    reader = sys.argv[1] if len(sys.argv) > 1 else "gemini-3.1-flash-lite"
    recs = [json.loads(l) for l in open(os.path.join(ROOT, "training", "out", f"hw_readings_{reader}.jsonl"), encoding="utf-8")]
    recs = [r for r in recs if r.get("split") == "test" and "text" in r]
    idx = CandidateIndex()
    cache_path = os.path.join(ROOT, "training", "out", f"e1_{reader}.jsonl")
    cache = {}
    if os.path.exists(cache_path):
        cache = {r["file"]: r for r in map(json.loads, open(cache_path, encoding="utf-8"))}

    def one(rec):
        if rec["file"] in cache:
            return cache[rec["file"]]
        cands = candidates_for(idx, rec)
        label = rec["label"].lower()
        c1 = r1(cands)
        row = {"file": rec["file"], "label": rec["label"], "in20": label in {c.brand.lower() for c in cands},
               "r1_ok": bool(c1.candidate) and c1.candidate.brand.lower() == label, "r1_conf": c1.confidence}
        try:
            img = image_part(os.path.join(ROOT, "data", "handwriting", "bd", "test", rec["file"]))
            c3 = r3([img], cands, k=5)
            row.update(r3_ok=bool(c3.candidate) and c3.candidate.brand.lower() == label, r3_conf=c3.confidence,
                       r3_none=c3.candidate is None)
        except GeminiError as e:
            row.update(r3_ok=False, r3_conf=0.0, r3_none=True, r3_error=str(e)[:120])
        return row

    with ThreadPoolExecutor(8) as ex:
        rows = list(ex.map(one, recs))
    with open(cache_path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    n = len(rows)
    report = {
        "reader": reader, "n": n,
        "recall@20": round(sum(r["in20"] for r in rows) / n, 3),
        "R1_top1": round(sum(r["r1_ok"] for r in rows) / n, 3),
        "R3_top1": round(sum(r["r3_ok"] for r in rows) / n, 3),
        "R3_said_none": round(sum(r["r3_none"] for r in rows) / n, 3),
        "R1_error_at_coverage": risk_coverage(rows, "r1_conf", "r1_ok"),
        "R3_error_at_coverage": risk_coverage(rows, "r3_conf", "r3_ok"),
    }
    print(json.dumps(report, indent=1))
    json.dump(report, open(os.path.join(ROOT, "training", "out", f"e1_report_{reader}.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
