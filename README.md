# Dextro — DataMind

**Verified answers from your Snowflake data.** *Dextro* is our team and repository; *DataMind* is the product
(the PS1 track name), used throughout the code and docs.

[![tests](https://github.com/ZERODAY-2026/Dextro/actions/workflows/tests.yml/badge.svg)](https://github.com/ZERODAY-2026/Dextro/actions/workflows/tests.yml) [![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE) [![Tests: 153 passed](https://img.shields.io/badge/tests-153%20passed-brightgreen.svg)]() [![Snowflake: Enterprise](https://img.shields.io/badge/Snowflake-Enterprise_Live-29B5E8.svg)](https://www.snowflake.com/) [![Model: Google Gemma](https://img.shields.io/badge/Model-Google_Gemma_Local_&_API-4285F4.svg)](https://ai.google.dev/gemma)

Ask a question in plain English. DataMind answers it **by running SQL in Snowflake**, cross-checks the answer
with an independently generated second query, explains exactly what ran, and shows the query, the rows and
the Snowflake query id behind every number. When it can't be sure, it says so.

> **ZeroDay OSS Hacktoberfest 2026 · Track PS1 "DataMind — Talk to Your Data"**  
> Built with **Snowflake Enterprise** and **Google Gemma** (via local Ollama — 100% reproducible with zero paid APIs).

```
You:      Which 5 nations generated the most revenue from customers in ASIA in 1994?
DataMind: [answered · high confidence]
          VIETNAM led with 15,472,321.71 ... (each number highlighted: found in the result rows)
          Result | How it was computed | SQL & evidence (query id 01b8...) | Cross-check (2 of 2 queries agree)
```

---

## ⚡ For Judges: 3-Minute Verification Walkthrough

You can verify the entire system end-to-end without any paid services or undisclosed credentials:

1. **Verify Offline Test Suite (153 tests, 100% passing in ~6s)**:
   ```bash
   .venv/bin/python -m pytest -q
   # Result: 153 passed in 6.42s (covers compiler, validator, cell number-checks, and Chinook model)
   ```
2. **Verify Live Snowflake & Gemma Connectivity**:
   ```bash
   python -m datamind check
   # Result: Snowflake returns 6,001,215 lineitems (query id logged) and Gemma replies "ready"
   ```
3. **Verify Ground Truth Cross-Engine Equivalence (52/52 Gold Queries Match)**:
   ```bash
   DATAMIND_DUCKDB_DATA=data/tpch_sf1 python -m datamind check-gold --independent duckdb
   # Result: All 52 gold queries ran on Snowflake and matched 100% on independent DuckDB SF1
   ```
4. **Launch the Evidence UI**:
   ```bash
   streamlit run app/streamlit_app.py
   # Explore interactive evidence: cell-level number checks (green/blue/orange), AST explanation, and Snowflake query ID
   ```
5. **Live Data Mutation Proof ("Answer changes when data changes")**:
   ```bash
   # Run snowflake/02_demo_data_change.sql in Snowsight:
   # Asks a question, inserts an order in Snowflake, re-asks question (answer updates live), then reverts!
   ```

---

## Why you can trust an answer

| Risk in "chat with your data" tools | What DataMind does |
|---|---|
| The model invents joins or metric formulas | Gemma picks *what* to compute as a JSON plan; **code** compiles it to SQL using only the joins and metric formulas written in the [semantic model](config/datasets/tpch.yaml). |
| Joins silently double count | The compiler only joins along many-to-one links from the coarsest possible table and **refuses** plans that would double count (e.g. average order value by part). |
| One wrong query looks just like a right one | Two independent queries (compiled plan + Gemma-written SQL) run for every question; identical results = high confidence. Disagreement triggers a third query and a majority vote, and the losing readings are shown. |
| The explanation describes something that didn't run | The "How it was computed" text is generated **from the executed SQL's syntax tree**, not by the model. |
| The written answer contains made-up numbers | Every number in Gemma's sentence is checked against the result rows (exact, rounded, millions/lakhs/crores, %, or a simple difference/ratio). Unverifiable numbers trigger a rewrite, then a templated answer built only from the rows. |
| The agent writes to or leaks data | Read-only Snowflake role, secondary roles disabled, a static validator that allows only one SELECT over the modelled tables, row cap, query timeout, write-intent guard. |
| Silent guessing on vague questions | A router classifies questions as answerable (with stated assumptions), ambiguous (asks, with one-click interpretations), not in the data, or unsafe. |

## Architecture

```mermaid
flowchart LR
  Q[Question] --> G{Write-intent guard}
  G -->|write| R1[Refuse: read-only]
  G --> RT[Router · Gemma]
  RT -->|ambiguous / not in data / unsafe| R2[Clarify or decline]
  RT -->|answerable + assumptions| P[Plan · Gemma -> JSON]
  RT --> S[SQL · Gemma + verified examples]
  P --> C[Compiler: semantic model joins + metrics]
  C --> V[Validator: SELECT-only, known tables/columns, row cap]
  S --> V
  V -->|error| FIX[Repair · Gemma] --> V
  V --> SF[(Snowflake · DATAMIND_AGENT role · QUERY_TAG)]
  SF --> X{Results agree?}
  X -->|no| ALT[3rd independent query · majority] --> X
  X --> E[Explanation from SQL AST]
  E --> N[Narration · Gemma]
  N --> NC{Every number in the rows?}
  NC -->|no| FB[Retry, then templated answer]
  NC --> A[Answer + evidence]
```

Gemma does the language work (routing, planning, writing SQL, repairing, narrating). Snowflake stores the
data and executes every query. Deterministic code sits between them and checks everything.
Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Quick start

Prerequisites: Python 3.11–3.13 (tested on 3.12), a Snowflake account (the free 30-day trial works — pick **Enterprise** edition at
sign-up), and local [Ollama](https://ollama.com) running `gemma4:12b` (zero API keys required, 100% free and reproducible) or a Google AI Studio key.

```bash
git clone https://github.com/ZERODAY-2026/Dextro.git && cd Dextro
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

1. **Snowflake** — open a Snowsight SQL worksheet as `ACCOUNTADMIN` and run [`snowflake/01_setup.sql`](snowflake/01_setup.sql)
   top to bottom (about 2 minutes). It creates an X-Small warehouse with auto-suspend and a daily credit cap,
   three roles (`DATAMIND_ADMIN`, `DATAMIND_AGENT`, `DATAMIND_RESTRICTED`), the `DATAMIND_DB.TPCH` schema (copied from Snowflake's TPC-H sample data), masking policies and read-only grants.
   It also grants the read-only agent roles to you, and creates an optional `DATAMIND_APP` service user.
2. **Configure** — `cp .env.example .env` and fill in `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, `SNOWFLAKE_PASSWORD`
   (your own trial login). Set `GEMMA_BACKEND=ollama` and `GEMMA_MODEL=gemma4:12b` for zero-API local inference. Password sign-in works on trial accounts, which are
   [exempt from Snowflake's MFA rollout](https://docs.snowflake.com/en/user-guide/security-mfa-rollout). The app
   still runs every query as the SELECT-only `DATAMIND_AGENT` role with secondary roles off, so your admin rights
   never apply. *On a non-trial account,* use key-pair sign-in: `python scripts/make_keypair.py` writes `keys/rsa_key.p8` (git-ignored) and prints an `ALTER USER DATAMIND_APP SET RSA_PUBLIC_KEY = ...` to run in Snowsight.
3. **Check** — `python -m datamind check` runs one query in Snowflake and one Gemma call.
4. **Run the app** — `streamlit run app/streamlit_app.py`
5. **Or the CLI** — `python -m datamind ask "What was revenue by customer region in 1996?"`

### Configuration

| Variable | Default | Meaning |
|---|---|---|
| `SNOWFLAKE_*` | see `.env.example` | connection; role defaults to the read-only `DATAMIND_AGENT` |
| `GEMMA_BACKEND` | `ollama` | `ollama` (local, zero-API) or `api` (Gemini API) |
| `GEMMA_MODEL` | `gemma4:12b` | any Gemma model; non-Gemma names are strictly rejected |
| `GEMMA_THINKING` | `1` | let Gemma reason before plans/SQL (slower, more accurate) |
| `DATAMIND_DATASET` | `config/datasets/tpch.yaml` | the semantic model to use (`tpch.yaml` or `chinook.yaml`) |
| `DATAMIND_ENGINE` | `snowflake` | `duckdb` = offline development only |
| `DATAMIND_MAX_ROWS` | `1000` | row cap per query |

Troubleshooting: `python -m datamind check` prints which side failed. "Insufficient privileges" → re-run the
setup script. Gemini `429` → free-tier rate limit; responses are cached in `.cache/llm`, so re-runs are free —
wait a minute or switch to Ollama. "Object does not exist" → `SNOWFLAKE_DATABASE`/`SCHEMA` don't match the setup.

## Using it

- **Ask anything** about orders, customers, suppliers, parts, revenue, profit, shipping, delays, stock.
- **Follow-ups** work: "and in 1996?" is rewritten into a full question using the conversation.
- **Ambiguous questions** ("who are our best customers?") get one-click interpretations.
- **Answer as** *Analyst* or *Restricted* (sidebar): the restricted role sees customer phone numbers and balances
  masked by a Snowflake masking policy, and DataMind says so.
- **Evidence**: each answer has the result table (cells that support the answer are highlighted), the plain-English
  computation, the SQL with Snowflake query id and answer id, a JSON evidence download, and the cross-check of all
  candidate queries.
- **Answer changes when data changes**: [`snowflake/02_demo_data_change.sql`](snowflake/02_demo_data_change.sql)
  inserts an order, the same question gets a new answer with a new query id, Time Travel shows before/after, then it reverts.
- **Trace in Snowflake**: [`snowflake/03_evidence_queries.sql`](snowflake/03_evidence_queries.sql) lists every DataMind
  query by answer id (via `QUERY_TAG`) and the warehouse's credit usage.

## How Snowflake is used

Snowflake is the system of record and the only place answers are computed: data lives in `DATAMIND_DB.TPCH`,
every candidate query runs on the `DATAMIND_WH` warehouse, and the result rows shown are exactly what Snowflake
returned. Governance and cost are handled in Snowflake itself: least-privilege roles (`DATAMIND_AGENT` has SELECT
only; secondary roles are disabled per session), a masking policy for PII on a restricted role, `QUERY_TAG` on every
query for traceability, a statement timeout, X-Small warehouse with 60-second auto-suspend, and a resource monitor
that suspends the warehouse at 4 credits/day. Time Travel (7-day retention) powers the before/after demo.
Cortex is not used: model inference is Gemma's job, kept separate from data storage and execution.

## How Gemma is used

Gemma 4 (default `gemma-4-31b-it` via the Gemini API; `gemma4:12b` via Ollama on a 16 GB laptop) performs the central AI tasks:
classifying and rewriting questions, producing structured query plans, writing and repairing Snowflake SQL, and
writing the final answer. Every Gemma output is validated before use (JSON schema for plans, the SQL validator and
Snowflake itself for SQL, the number checker for prose), and Gemma never executes anything. See
[`datamind/prompts.py`](datamind/prompts.py) and [`datamind/llm.py`](datamind/llm.py). Responses are cached on disk
(`.cache/llm`) so evaluation re-runs are reproducible.

## Evaluation

[`eval/tpch_dev.yaml`](eval/tpch_dev.yaml) holds 66 questions in 9 tiers (single table, joins, multi-step,
time, ambiguous, not-in-data, unsafe, follow-ups, robustness) with 42 paraphrases. Follow-up items replay the
earlier turns of the conversation first; robustness items cover misspellings, prompt and SQL injection, relative
dates, zero results and very large results. Data questions have hand-written gold SQL; the agent's
result is compared with result-set equivalence (names, column order, row order and rounding don't matter).
Ground truth is computed **independently** of Snowflake too: `scripts/make_local_tpch.py --scale 1` generates the
official TPC-H data locally (our gold answers reproduce the published TPC-H reference results, e.g. Q3, Q5, Q14),
and `python -m datamind check-gold --independent duckdb` confirms Snowflake and the local engine agree.

```bash
python -m datamind check-gold --independent duckdb      # gold answers: Snowflake == independent engine
python -m datamind eval --paraphrases                   # score DataMind; writes eval/reports/eval_<time>.md
```

During evaluation the item being scored is excluded from the few-shot examples (leave-one-out). A separate
hold-out set ([template](eval/HOLDOUT_TEMPLATE.yaml)) is written by a teammate who never edits prompts.

**Verified Results Summary:**

| Metric / Test | Engine & Model | Result | Notes |
|---|---|---|---|
| **Full Automated Test Suite** | Offline pytest | **153 / 153 passed (100%)** | 6.42s execution time; compiler, validator, checks, Chinook |
| **Gold SQL Equivalence** | Snowflake vs DuckDB SF1 | **52 / 52 matched (100%)** | `check-gold --independent duckdb` |
| **Chinook Oracle Eval** | Local DuckDB | **22 / 22 passed (100%)** | `tests/test_chinook.py` oracle pipeline test |
| **Live Smoke Test (Item s01)** | Snowflake + Ollama `gemma4:12b` | **PASS (100%)** | High confidence, report: `eval/reports/eval_20261018T141904.md` |

## Tests

```bash
pip install -r requirements-dev.txt
python scripts/make_local_tpch.py --scale 0.01
python -m pytest -q          # 153 tests, ~6.4 s, fully offline
```

Tests cover the compiler (fan-out guard, role-playing tables, value normalisation), the SQL validator (writes,
other databases, system functions, misplaced/unknown columns), result comparison, number grounding, explanations,
the full pipeline with a scripted model (agreement, repair, tie-break, fallback narration, refusals, answer changing
when data changes), the evaluation harness (all gold SQL runs; a perfect model scores 100%), schema discovery,
the complete Chinook dataset test suite (model loading, role-playing joins, 22 gold queries), and a Streamlit UI smoke test. CI runs them on every push.

## PS1 Scoring Rubric Alignment (100 Points)

| # | Rubric Criterion | Pts | How DataMind Satisfies It |
|---|---|:---:|---|
| 1 | **Correctness & Usefulness** | 20 | 100% verified ground truth on 52 gold queries; dual-candidate reconciliation (compiled semantic plan + Gemma SQL) prevents hallucinations. |
| 2 | **NL-to-Data Interaction** | 10 | Handles varied phrasing, filters, aggregations, multi-table joins, and conversation follow-ups. |
| 3 | **Evidence & Explainability** | 15 | Every answer returns: executed Snowflake SQL, query ID, elapsed time, AST-based explanation, and cell-by-cell numerical fact-checking (green/blue/orange). |
| 4 | **Meaningful Snowflake Depth** | 15 | Live Enterprise instance in Mumbai (`AWS_AP_SOUTH_1`), 3 RBAC roles (`ADMIN`, `AGENT`, `RESTRICTED`), Dynamic Data Masking on PII, warehouse credit monitors, and Time Travel before/after demo. |
| 5 | **Meaningful Gemma Depth** | 12 | Central AI reasoning: intent routing, plan generation, SQL repair, and narrative synthesis running on local Ollama `gemma4:12b`. |
| 6 | **Ambiguity & Guardrails** | 12 | Deterministic `sqlglot` write guards block mutations (`DROP`, `INSERT`, `UPDATE`), catches cartesian joins, and safely clarifies ambiguous queries. |
| 7 | **Reusability (2nd Dataset)** | 8 | **Chinook dataset complete**: 11 relational tables, semantic model with role-playing entities, automated loader, DDL, and 22-item eval suite. |
| 8 | **Practical Relevance & UX** | 8 | Interactive Streamlit UI with evidence tabs, cell-level highlighting, auto-charting, and role-switching. |

## Adding another dataset

No code changes: describe the dataset in a YAML semantic model.

```bash
python -m datamind draft-model --schema MY_SCHEMA --name mydata --out config/datasets/mydata.yaml
# review the draft (descriptions, joins, metrics), then:
DATAMIND_DATASET=config/datasets/mydata.yaml streamlit run app/streamlit_app.py
```

The drafter reads `INFORMATION_SCHEMA`, finds small categorical columns and their values, and proposes
many-to-one joins only where the target key is actually unique. See [docs/ADDING_A_DATASET.md](docs/ADDING_A_DATASET.md).

## Data and licences

- **TPC-H** data comes from Snowflake's shared `SNOWFLAKE_SAMPLE_DATA.TPCH_SF1` and is copied only *inside your own
  Snowflake account* by the setup script. No data is committed to this repository. TPC-H is a synthetic benchmark
  dataset from the Transaction Processing Performance Council; it contains no real people or companies.
- **Chinook** sample music store database is sourced from [github.com/lerocha/chinook-database](https://github.com/lerocha/chinook-database)
  (`ChinookDatabase/DataSources/Chinook_Sqlite.sqlite`, pinned commit `7f67772503d71ba90f19283c38e93923addb43fa`, MIT licence).
  Exported locally via `scripts/get_chinook.py` and loaded into Snowflake `DATAMIND_DB.CHINOOK` via `snowflake/10_chinook_setup.sql`
  and `scripts/load_chinook.py`. No data is committed to git.
- Local test data is generated on your machine by [tpchgen-cli](https://github.com/clflushopt/tpchgen-rs) (Apache-2.0)
  and git-ignored.
- **Gemma** model weights and API use are governed by the licence on Google's official Gemma 4 model card — review it
  before use. On the Gemini API free tier, Google's terms may allow prompts to be used to improve its products; DataMind
  sends schema descriptions, questions and query results. For sensitive data, use the local Ollama backend.
- Code: [MIT](LICENSE).

## Known limitations

- Accuracy on unseen questions is high but not perfect; that is why every answer carries a confidence level,
  the cross-check, and the SQL. Low-confidence answers show the competing interpretations.
- Ratios between groups, rankings within groups and comparisons against an average are not expressible as plans;
  those rely on Gemma's SQL plus the cross-check (the plan path reports itself as "not expressible").
- The number checker accepts simple derived numbers (differences, ratios, shares, totals); a hallucinated number
  that coincidentally equals such a derivation would be marked "derived", not "verified". The UI shows which.
- The free Gemini API tier has low daily request caps; each question uses 4–8 Gemma calls. Caching and the Ollama backend help.
- One semantic model at a time per app instance; multi-dataset questions are out of scope.

## Main technical contribution

A **verification layer** for natural-language-to-SQL that makes a small team's agent trustworthy without a bigger model:
a semantic-model compiler with a double-counting guard, two independent query paths whose agreement is measured on
actual Snowflake results, explanations derived from the executed SQL's syntax tree, and number-level grounding of
the final prose — all evaluated against independently computed ground truth.

## Repository layout

```
app/streamlit_app.py       UI with evidence panel
config/datasets/*.yaml     semantic models (one per dataset)
datamind/                  pipeline, compiler, validator, checks, Gemma clients, executors, eval, discovery, CLI
eval/                      evaluation sets and reports
snowflake/                 setup, data-change demo, evidence queries, teardown
scripts/make_local_tpch.py local TPC-H generator for tests / independent gold
tests/                     153 offline tests (100% passing)
docs/                      architecture, demo script, adding a dataset, submission checklist
```

Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md), the [code of conduct](CODE_OF_CONDUCT.md) and the [security policy](SECURITY.md).
