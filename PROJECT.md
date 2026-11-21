# PROJECT.md: state of the build (single source of truth)

Last updated: 21 Nov 2026 · Day 1 started

## How to resume (after a break or a context compaction)

1. Read this file top to bottom.
2. Check what's open: `gh issue list -R ai-naymul/ek-oshudh-dui-naam --state open --milestone "Day 1 · 21 Nov"` (then Day 2, Day 3, Final).
3. Check recent work: `git log --oneline -10`.
4. Continue the **first open issue in the current milestone**, then update "Status", "Numbers" and "Next 3 actions" below.

**Full approved plan:** `~/.claude/plans/peppy-gliding-kite.md`.
**Learning material:** `../runs/cou-ai-hackathon-2026/finals/` (prep book PDF + `project_handbook.md` written during the build).

## Goal

A family member (or a judge, on their own phone) sends **prescriptions from several doctors and/or photos of medicine strips**. The app finds:
- the same medicine under different brand names;
- two medicines from the same family;
- daily doses over the limit;
- money wasted.

It explains in Bangla (text, voice, picture card) and shows the proof.

**Pipeline:** AI reads → catalog-constrained matcher picks a **real** registry product → fixed rules decide → Bangla templates speak.

## Decisions (why each one: handbook Part 10)

- **Inputs:** any mix of prescriptions, strips, typed names, Bangla voice → one case per patient.
- **Channels:**
  - Bangla web app opened by QR (judges' phones);
  - WhatsApp on Meta's free test number (team phones);
  - share-to-WhatsApp on every result;
  - MCP server as stretch.

  No Telegram, no Messenger.
- **Hosting (free):** web on Cloudflare Pages; backend on this Mac via a Cloudflare quick tunnel; the QR code carries `?api=<tunnel>`; fallback is the LAN server on the hotspot. The home PC (32 GB) is for heavy pre-build jobs only, never the demo.
- **Matching:** three rerankers are built and held-out data (E1) picks the winner:
  - R1 fuzzy;
  - R2 LightGBM decision model;
  - R3 constrained AI choice.

  R2 ships only if it beats R1. Research basis: RxLens (catalog selection prevents hallucinated drug names); MIRAGE (zero-shot handwriting is weak → measure + confirm).
- **Safety:**
  - no model-written warnings;
  - no free-text medicine names;
  - unconfirmed handwriting never turns a card red;
  - never "stop taking"; always "show your doctor".
- **Commits:** only the team's own accounts. **No Co-Authored-By trailers.** No squash, no force-push.
- **Models:**
  - `gemini-3.8-flash` (read);
  - `gemini-3.1-flash-lite` (fallback, R3);
  - `gemini-3.5-transcribe` (voice in);
  - `gemini-3.8-flash-tts` (voice out);
  - `gemini-embedding-2` (optional).

## Status (issue → state)

**Day 1 · 21 Nov**

| # | Issue | State |
|---|---|---|
| 1 | Repo setup: skeleton, CI, PROJECT.md, commit rules | done except CI file (needs `gh auth refresh -s workflow`) |
| 2 | Cloudflare Pages hello + quick tunnel hello | todo |
| 3 | Download scripts: registry + handwriting datasets (+ licences) | registry + LICENSES.md done; handwriting script todo |
| 4 | Knowledge graph build (graph.py) + tests | **done** (21,363 / 13,627 / 1,508; 13,253 priced) |
| 5 | Candidate generation (candidates.py) + tests | **done** (recall@20 98.3%, 1.7 ms) |
| 6 | Schedule parser (schedule.py) + tests | **done** (15 tests: 1+0+1, ১+০+১, ½, BD/TDS, দিনে ২ বার, meals, days) |
| 7 | Perception smoke test: strips, 2 prescriptions, 100 handwritten words | todo |
| 8 | Handwriting label coverage vs registry + recall@20 | todo |
| 9 | Handbook: graph, candidates, schedule, tests | todo |

Teammate issues (Day 1):
- #10 online images
- #11 home photos + 2 prescriptions
- #12 curated tables
- #13 WhatsApp test number + pharmacist

**Day 2 · 22 Nov**
- **Matching:** #14 R1 + R3 · #15 R2 LightGBM · #16 E1 report → shipped policy.
- **Pipeline:** #17 perceive.py · #18 reconcile + rules + Bangla templates.
- **Web, agent, handbook:** #19 web flow (Apple-design) + Pages · #20 agent + guardrails · #21 handbook.
- **Teammates:** #22 eval cases · #23 pharmacist · #24 usability round 1.

**Day 3 · 23 Nov**
- **Product:** #25 Proof screen · #26 picture card + share · #27 voice · #28 WhatsApp bot.
- **Evals and handbook:** #29 E2–E5 + README + demo_check · #30 handbook + PDF + backup video.
- **Teammates:** #31 round 2 + cards + mirror + drills.
- **Stretch:** #34 MCP server.

**Final · 24 Nov**
- #32 runbook · #33 reserved live items.
- **Stretch:** #35 Gemma 4 offline (home PC) · #36 MCP Apps card.

(Exact numbers and titles: `gh issue list`. Mark items done here when their issue closes.)

## Live URLs (no secrets here)

| What | Value |
|---|---|
| Repo | https://github.com/ai-naymul/ek-oshudh-dui-naam |
| Web (Cloudflare Pages) | _not yet_ |
| Backend tunnel (changes on restart) | _not yet_ |
| WhatsApp test number | _not yet_ (token and phone id live only in `.env`) |

## Numbers (filled as evals run; never invent)

| Eval | Result |
|---|---|
| Candidates (#5) | brand recall@20 = **98.3%** on 600 synthetic noisy readings (seed 7); median 1.7 ms per search |
| Perception smoke test (#7) | _pending_ |
| Handwriting coverage + recall@20 (#8) | _pending_ |
| E1 matching (R1 / R2 / R3 / R2→R3) | _pending_ |
| E2 perception, E3 handwriting, E4 end-to-end, E5 baseline | _pending_ |

## What changed since last update

- 21 Nov: repo, milestones, labels, 36 issues; skeleton pushed (CI file waiting for workflow scope); `main` protected.
- 21 Nov: knowledge graph built and tested (#4); candidate generation: TF-IDF char n-grams + rapidfuzz edit distance + Metaphone + Bangla transliteration, recall@20 98.3% (#5).

## Next 3 actions

1. #2 Cloudflare Pages + tunnel hello; #3 handwriting download script; #8 coverage.
2. #7 perception smoke test (needs the user's 2 prescription photos + a few strip images in `data/prescriptions/`, `data/images_online/`).
3. #3 handwriting download script + #8 coverage; push CI once the token has workflow scope.
