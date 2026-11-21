# Ek Oshudh, Dui Naam (এক ওষুধ, দুই নাম)

**Same medicine. Different names. Double the risk.**

Send photos of a family's prescriptions (even from different doctors) and medicine strips. The app finds:
- the same medicine hiding under different brand names;
- two medicines from the same family;
- daily doses over the safe limit;
- money wasted on duplicates.

It answers in Bangla, as text, voice and a picture card.

Built for the CoU AI Hackathon 2026 finals.

> Results are reported here only after they are measured.

## How it works

1. **Read.** Gemini reads each prescription line or strip into a fixed schema, with alternatives for unclear words.
2. **Match.** A catalog-constrained matcher picks a **real product** from a Bangladesh medicine registry of 21,363 products (13,627 brand names). It never invents a name.
3. **Decide.** Fixed, tested rules decide every warning.
4. **Explain.** Bangla templates show the warning, the knowledge-graph path and the source sentence behind it.

## Run locally

```bash
cd backend
uv sync --python 3.12
uv run uvicorn app.main:app --reload --port 8000
uv run pytest -q
```

## Repository layout

- `backend/`: FastAPI app, core pipeline, tests.
- `web/`: React web app (Cloudflare Pages).
- `scripts/`: data download and evaluation scripts.
- `data/curated/`: verified safety tables, each row with its source sentence.
- `eval/`: evaluation cases and results.
- `training/`: decision-model training.

## Data sources

Listed with licences in `data/LICENSES.md` (added with the download scripts).
