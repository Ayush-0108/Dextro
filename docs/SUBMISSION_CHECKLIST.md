# Submission checklist (ZeroDay OSS Hacktoberfest 2026 — PS1)

Status key: ✅ in the repo · 🟡 team action needed

## Gates (pass/fail)

| Gate | Where | Status |
|---|---|---|
| G1 Open-source repo + licence | `LICENSE` (MIT) | 🟡 push to a **public** GitHub repo |
| G2 Reproducible demo | README quick start; `snowflake/01_setup.sql` works on a free trial; local Ollama (free) or Gemma 31B via Hugging Face | ✅ + 🟡 keep a trial account alive through judging (see below) |
| G3 Real system | Live Snowflake + Gemma; the scripted model exists only under `tests/` | ✅ |
| G4 Data disclosure | README → Data and licences | ✅ |
| G5 No secrets | `.env`/keys git-ignored; `.env.example` only | ✅ + 🟡 run `git log -p | grep -i -E "password|api_key"` before publishing |
| P1 Snowflake meaningful | all queries run in Snowflake; roles, masking, tags, monitor, time travel | ✅ |
| P2 Gemma meaningful | router, planner, SQL writer, repairer, narrator; non-Gemma models rejected | ✅ |
| P3 Answers from queries at question time | every answer = rows returned by Snowflake for that question | ✅ |

## Required deliverables

| ID | Where | Status |
|---|---|---|
| S1 Public repo + licence | | 🟡 publish |
| S2 README (overview, setup, run, config, troubleshooting) | `README.md` | ✅ |
| S3 Pinned deps, versions, OS/hardware | `requirements*.txt` | 🟡 add "Tested on: <OS>, Python <x>, <RAM>; Ollama model size" after your runs |
| S4 Architecture | README diagram + `docs/ARCHITECTURE.md` | ✅ |
| S5 Dataset sources, licences, prep | README + `snowflake/01_setup.sql` | ✅ |
| S6 Sponsored tech usage | README → How Snowflake / Gemma is used | ✅ |
| S7 Demo video ≤ ~5 min incl. limits | `docs/DEMO_SCRIPT.md` | 🟡 record |
| S8 Test results + limitations | README → Tests, Evaluation, Known limitations | 🟡 paste eval numbers |
| S9 Reproduce the demo | README + demo script + SQL scripts | ✅ |
| S10 Main technical contribution | README → Main technical contribution | ✅ |

## PS1 extras

| Item | Where | Status |
|---|---|---|
| Evidence answers are grounded (queries, query ids, comparison with independent results) | app Evidence tab, JSON download, `03_evidence_queries.sql`, `check-gold --independent duckdb` | ✅ + 🟡 save a query-history export and screenshots from your account |
| Demo of an answer changing when data changes | `snowflake/02_demo_data_change.sql` | ✅ + 🟡 record it |
| Evidence of Snowflake and Gemma roles | README sections, run log `runs/answers.jsonl` | ✅ |
| Evaluation question set with expected answers and results (recommended) | `eval/tpch_dev.yaml`, `eval/reports/` | ✅ + 🟡 run + hold-out |
| Reproducible Snowflake setup script (recommended) | `snowflake/01_setup.sql` | ✅ |

## Team actions, in order

1. Create the Snowflake trial (**Enterprise**, choose region once — it can't be changed), run `01_setup.sql`.
2. Ollama `gemma4:12b` (or HF token for 31B); `python -m datamind check`.
3. `python -m datamind check-gold --independent duckdb` (after `make_local_tpch.py --scale 1`) — confirms Snowflake's data equals the reference data.
4. `python -m datamind eval` — read the failures, improve the semantic model notes / prompts, re-run. Commit reports.
5. A teammate writes `eval/tpch_holdout.yaml` (≥ 30 questions) without seeing prompts; run it once near the end; report it honestly.
6. Optional but valuable: a second dataset via `draft-model` (criterion 7).
7. ~7 days before submission, a teammate creates a **fresh** trial and runs only the setup script: proves reproducibility and keeps an account alive through judging. Record the demo on it.
8. Publish repo, record video, fill README results table, submit.
