"""Download the Doctor's Handwritten Prescription BD dataset (HF mirror lance-format/handwriting-ocr, ODbL)
and export it as PNG word images + labels.csv per split under data/handwriting/bd/<split>/.

Run from backend/:  uv run --group training python ../scripts/get_handwriting.py
"""
import csv
import io
import os

import lance
from huggingface_hub import snapshot_download
from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(ROOT, "data", "handwriting", "bd")


def main():
    local = snapshot_download("lance-format/handwriting-ocr", repo_type="dataset",
                              cache_dir=os.path.join(ROOT, "data", "raw", "hf_cache"))
    for split in ("train", "validation", "test"):
        ds = lance.dataset(os.path.join(local, "data", f"{split}.lance"))
        cols = ds.schema.names
        img_col = next(c for c in cols if c in ("image", "img", "image_bytes"))
        out_dir = os.path.join(OUT, split)
        os.makedirs(out_dir, exist_ok=True)
        rows = []
        for batch in ds.to_batches(columns=cols):
            for r in batch.to_pylist():
                img = r[img_col]
                data = img["bytes"] if isinstance(img, dict) else img
                fname = f"{r['id']}.png"
                Image.open(io.BytesIO(data)).convert("RGB").save(os.path.join(out_dir, fname))
                rows.append({"file": fname, "medicine_name": r.get("medicine_name", ""), "generic_name": r.get("generic_name", "")})
        with open(os.path.join(out_dir, "labels.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["file", "medicine_name", "generic_name"])
            w.writeheader()
            w.writerows(rows)
        print(split, len(rows), "images; columns:", cols)


if __name__ == "__main__":
    main()
