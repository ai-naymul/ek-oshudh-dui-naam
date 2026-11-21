"""Read every handwritten word image with Gemini (perception only, no catalog shown) and save the readings.

These readings are (1) the real-world input for evaluation E1/E3 and (2) the source of real error pairs for
training the decision model. Resumable: results append to training/out/hw_readings_<model>.jsonl.

Run from backend/:  uv run --group training python ../training/read_handwriting.py [model] [splits...]
"""
import csv
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from app.ai.gemini import LITE_MODEL, GeminiError, generate, image_part  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PROMPT = ("This is a cropped handwritten word from a Bangladeshi doctor's prescription. It is usually a medicine "
          "brand name. Transcribe exactly what is written, as your best guess, and give up to 3 alternative readings. "
          "Do not correct it to a medicine you know unless the letters support it.")
SCHEMA = {"type": "object", "properties": {"text": {"type": "string"},
                                            "alternatives": {"type": "array", "items": {"type": "string"}},
                                            "legible": {"type": "boolean"}},
          "required": ["text", "alternatives", "legible"]}


def main():
    model = sys.argv[1] if len(sys.argv) > 1 else LITE_MODEL
    splits = sys.argv[2:] or ["train", "validation", "test"]
    out_path = os.path.join(ROOT, "training", "out", f"hw_readings_{model}.jsonl")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    done = set()
    if os.path.exists(out_path):
        done = {(r["split"], r["file"]) for r in map(json.loads, open(out_path, encoding="utf-8"))}
    jobs = []
    for split in splits:
        for r in csv.DictReader(open(os.path.join(ROOT, "data", "handwriting", "bd", split, "labels.csv"), encoding="utf-8")):
            if (split, r["file"]) not in done:
                jobs.append((split, r))

    def one(job):
        split, r = job
        path = os.path.join(ROOT, "data", "handwriting", "bd", split, r["file"])
        try:
            out, meta = generate([image_part(path), {"text": PROMPT}], model=model, schema=SCHEMA, thinking="low")
            return {"split": split, "file": r["file"], "label": r["medicine_name"], "generic": r["generic_name"], **out, **meta}
        except GeminiError as e:
            return {"split": split, "file": r["file"], "label": r["medicine_name"], "error": str(e)[:200]}

    with open(out_path, "a", encoding="utf-8") as f, ThreadPoolExecutor(8) as ex:
        for i, rec in enumerate(ex.map(one, jobs), 1):
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            if i % 200 == 0:
                f.flush()
                print(f"{i}/{len(jobs)}", flush=True)
    print("done", out_path)


if __name__ == "__main__":
    main()
