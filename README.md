# Ek Oshudh, Dui Naam (এক ওষুধ, দুই নাম)

**Two names, one medicine.** An older person sees several doctors, each writes a favourite brand, and more medicine is
bought at the pharmacy. In Bangladesh the same ingredient is sold under very many names (in the registry we use:
Cefixime 146 brand names, Omeprazole 138, Paracetamol 117), so nobody at home can see that *Napa* and *Ace* are both
paracetamol.

This app is for the son or daughter sitting with a parent. Photograph the prescriptions and the strips in the
medicine bag (or say or type the names). The app turns every brand into the medicine inside it and shows, in Bangla,
when two names are one medicine **that is being taken now**, with a picture card and a voice reply to show the doctor
or pharmacist.

Team **Agentic Bekar** · CoU AI Hackathon 2026 finals.

## Run it locally (3 commands)

```bash
bash scripts/get_data.sh                                      # registry CSVs (public, MIT)
cd backend && uv sync && uv run python -m app.core.graph      # build the knowledge graph (21,363 products)
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000        # API + the web app at http://localhost:8000
```

Reading photos and voice needs a Gemini key in `.env` (`GEMINI_API_KEY=...`, see `.env.example`). Without it the app
says so, and typed names, the sample case, matching and every rule still work offline.
The web app is pre-built in `web/dist`; to rebuild: `cd web && npm ci && npm run build`.

Try it: **নমুনা দেখুন** (a labelled sample computed live) → **মিলিয়ে দেখুন** → answer **এখন খাচ্ছেন?** for both →
the two names join at the one ingredient. Press **ফোনে খুলুন** for a QR code that opens the app on a phone on the
same Wi-Fi.

## How it works: the model reads, the registry and fixed rules decide

```
photos / voice / typed
  → 1 READ      Gemini 3.8 Flash reads each line into a strict schema (name, alternatives, strength, schedule,
                a box around the whole line); voice notes are transcribed (gemini-3.5-transcribe)
  → 2 FIND      candidates from the national registry: character n-gram TF-IDF + edit distance + phonetic key
                + Bangla→Latin transliteration + local spellings (data/curated/aliases_local.csv)
  → 3 DECIDE    a trained LightGBM decision model ranks the candidates (14 explainable features) and accepts
                only when it is very sure; otherwise the family picks from the closest registered products
                (the photo line is shown) or searches the registry. It can never invent a medicine name.
  → 4 RECONCILE one case per patient: a prescription line and its own strip are one medicine; the same
                prescription photographed twice is not counted twice
  → 5 RULES     deterministic: same ingredient in two medicines both taken now (red); not yet known whether
                both are taken (the app asks); same drug family (needs checking); listed risky pairs
  → 6 EXPLAIN   Bangla templates only (config/copy_bn.json), always "show your doctor or pharmacist",
                never "stop"; voice reply (gemini-3.8-flash-tts); picture card with morning/noon/night icons
  → 7 PROVE     "কীভাবে জানলাম": every step of this check with timings, the matching benchmark, a live lookup
```

**Safety design.** No warning is written by a model. A reading the matcher is unsure of, and every spoken name, waits
for the family's tap and cannot raise a red warning before that. A bag holds old strips, so a duplicate turns red only
when both medicines are marked **taken now**. Dose limits are switched off until a pharmacist reviews them
(`config/settings.json`). The optional evidence agent (**সূত্র খুঁজুন**) only suggests, with guardrails in code
(step budget, grounding check, banned phrases).

## How well does the matching work?

Measured on real handwriting by Bangladeshi doctors (public dataset, 78 medicine names): thresholds were chosen on a
validation split of 780 words and reported once on a separate test split of 780 words the models never saw
(`eval/reports/e1_policy_gemini-3.8-flash.json`, `models/policy.json`).

| Matcher (Gemini 3.8 Flash reader) | Top-1 correct (dataset labels) | After label audit |
|---|---|---|
| R1 fuzzy string match | 82.8% | 84.1% |
| **R2 decision model (shipped)** | **86.8%** | **88.1%** |
| R3 AI picks from the top 5 | 85.0% | 86.3% |

- The right product is among the candidates for 93.8% of words.
- Shipped policy: accept automatically when the decision model's probability is ≥ 0.98, chosen so that the 95% upper
  bound of wrong automatic accepts on validation stays ≤ 2%. On test: 54.5% accepted automatically, 12 of 425 wrong
  as labelled; the other 45.5% are asked, and the right answer is among the three shown 83.9% of the time.
- Label audit (`eval/label_audit.csv`): we looked at every wrong automatic accept. 10 of the 12 were mistakes in the
  dataset's own labels (the image clearly shows the brand we chose); after the audit 2 of 425 (0.5%) are wrong, both
  changing the ingredient, which is why the photo line is always shown. Only disagreements were audited, so the
  audited figure is a best case; raw figures are always reported beside it.
- On 26 medicine names the decision model never saw in training: R2 80.4% vs R1 76.9% (Flash-Lite reader).

These numbers measure name matching on word images, not the whole path from a phone photo to a warning.

## Tests

```bash
cd backend && uv run pytest -q          # 128 tests, no API key needed (also run in CI on every push)
cd web && npm run e2e                   # end-to-end: the signature flow at 1440×900 and 390×844 (Playwright)
python3 scripts/demo_check.py           # checks the running app end to end, with timings
```

The tests pin the safety rules (golden cases: Napa + Ace red only when both are taken now, Seclo + Maxpro needs
checking, combination products, syrups left out of dose sums, nothing ever says "stop"), the matching, the schedule
parser (১+০+১, দিনে দুইবার, রাতে), the API edge cases (not a photo, impossible doses, AI down, a slow reading not
freezing the server) and the wording file.

## Changing it on-site

| Request | Where | Restart? |
|---|---|---|
| Any Bangla or English wording | `config/copy_bn.json` | no (re-read on the next request) |
| Ask for confirmation on every line; accept threshold | `config/settings.json` → `matching` | yes |
| Switch a rule on or off (dose limits, "not on prescription") | `config/settings.json` → `rules` | yes |
| A local spelling of a brand | `data/curated/aliases_local.csv` | yes |
| A risky pair, a drug family, a dose limit | `data/curated/*.csv` (with the source sentence) | yes |
| The sample case | `config/settings.json` → `sample_case` | yes |

Restart: stop the server and run the last command above again. Then `uv run pytest -q` shows the change broke nothing.

## Also in the repo

- `backend/app/mcp_server.py`: the checker as MCP tools (`check_medicines`, `find_brand`) for any MCP client.
- `training/`: how the decision model was trained and evaluated (`train_decider.py`, `eval_policy.py`).
- `eval/`: reports and the label audit.

## Data and licences

See `data/LICENSES.md`. Product photos used for local testing are not redistributed. No patient data is stored;
cases live in memory for two hours.

This is a prototype, not medical advice. Every finding says to show the doctor or pharmacist.
