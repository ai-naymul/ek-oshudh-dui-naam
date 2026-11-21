"""E2: real medicine strip/box/bottle photos through the full live pipeline (read -> match -> accept or ask).

Photos: data/images_online/ with sources.csv (brand/strength/form checked against the registry by a person; the
images are product photos from Bangladeshi online pharmacies, kept local, not redistributed). They are clean
studio photos, so this is an easier set than phone photos at home; it is reported as exactly that.

Per photo we record: was the expected brand found, was it accepted automatically or asked, was the strength right,
did we accept a WRONG brand automatically (the number that matters for safety), and how long it took.
Run from backend/:  uv run python ../training/eval_strips.py
"""
import csv
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from app.conversation import Engine  # noqa: E402
from app.core.graph import brand_key  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
IMAGES = os.path.join(ROOT, "data", "images_online")


def norm_strength(s: str) -> str:
    return "".join((s or "").lower().split())


def main():
    rows = list(csv.DictReader(open(os.path.join(IMAGES, "sources.csv"), encoding="utf-8")))
    e = Engine()

    def one(r):
        case = e.new_case()
        t0 = time.time()
        try:
            out = e.add_image(case, open(os.path.join(IMAGES, r["file"]), "rb").read())
        except Exception as ex:  # report, don't hide
            return {"file": r["file"], "brand": r["brand"], "error": f"{type(ex).__name__}: {ex}"[:120]}
        secs = time.time() - t0
        items = out["items"]
        want = brand_key(r["brand"])
        hit = next((i for i in items if i["chosen"] and brand_key(i["chosen"]["brand"]) == want), None)
        in_options = any(brand_key(o["brand"]) == want for i in items for o in i["options"])
        wrong_auto = [i["chosen"]["brand"] for i in items if i["chosen"] and not i["needs_confirm"]
                      and brand_key(i["chosen"]["brand"]) != want]
        return {"file": r["file"], "brand": r["brand"], "strength": r["strength"], "kind": r["kind"], "seconds": round(secs, 1),
                "read_as": [i["reading"] for i in items], "chosen": [i["chosen"]["brand"] if i["chosen"] else None for i in items],
                "found": hit is not None, "auto": bool(hit and not hit["needs_confirm"]), "in_options": in_options,
                "strength_ok": bool(hit and norm_strength(hit["chosen"]["strength"]) == norm_strength(r["strength"])),
                "wrong_auto": wrong_auto, "doc_kind": out["kind"], "method": hit["method"] if hit else None}

    with ThreadPoolExecutor(4) as ex:
        res = list(ex.map(one, rows))
    ok = [x for x in res if "error" not in x]
    n = len(ok)
    report = {
        "n_photos": len(rows), "n_read": n, "errors": [x for x in res if "error" in x],
        "brand_found": round(sum(x["found"] for x in ok) / n, 3),
        "brand_found_or_in_options": round(sum(x["found"] or x["in_options"] for x in ok) / n, 3),
        "accepted_automatically": round(sum(x["auto"] for x in ok) / n, 3),
        "strength_right_when_found": round(sum(x["strength_ok"] for x in ok) / max(1, sum(x["found"] for x in ok)), 3),
        "photos_with_a_wrong_automatic_accept": sum(bool(x["wrong_auto"]) for x in ok),
        "median_seconds": sorted(x["seconds"] for x in ok)[n // 2] if n else None,
        "misses": [{k: x[k] for k in ("file", "brand", "read_as", "chosen")} for x in ok if not x["found"]],
        "wrong_auto_detail": [{k: x[k] for k in ("file", "brand", "read_as", "wrong_auto")} for x in ok if x["wrong_auto"]],
        "strength_mismatches": [{"file": x["file"], "want": x["strength"]} for x in ok if x["found"] and not x["strength_ok"]],
    }
    os.makedirs(os.path.join(ROOT, "eval", "reports"), exist_ok=True)
    json.dump({"summary": report, "rows": res}, open(os.path.join(ROOT, "eval", "reports", "e2_strips.json"), "w"), indent=1, ensure_ascii=False)
    print(json.dumps(report, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
