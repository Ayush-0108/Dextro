# DataMind — project instructions for Claude Code

## What this is
Entry for **ZeroDay OSS Hacktoberfest 2026 (IIIT Dharwad), track PS1 "DataMind — Talk to Your Data"**.
Users ask questions in plain English; answers are computed by SQL in **Snowflake** (required), with **Google Gemma**
(required) doing the central AI work. Owner: Kanhaiya. The participant guide is the source of truth for rules.

Read before larger changes: `docs/STATUS.md` (where we are), `docs/DECISION_LOG.md` (why PS1, risks, strategy),
`docs/ARCHITECTURE.md` (design), `docs/SUBMISSION_CHECKLIST.md` (what judges require).

## How we are scored (keep every change aimed at this)
Final = 0.70 × track rubric + 0.30 × common rubric, after pass/fail gates.
- Gates: public repo + licence; judge can reproduce the demo without undisclosed credentials or paid services
  (or a documented path); real system, no mocks/hard-coded outputs; data sources + licences disclosed; no secrets.
  PS1 gates: Snowflake used meaningfully; Gemma used meaningfully; answers come from queries run at question time.
- Track rubric (100): correctness on UNSEEN questions incl. joins/multi-step 20 · NL interaction (phrasing,
  follow-ups) 10 · evidence/traceability 15 · Snowflake depth 15 · Gemma depth 12 · ambiguity/errors/missing
  data/unsafe 12 · reusability on a 2nd dataset via config 8 · UX 8.
- **Trust cap: if correctness is in the Poor band (<25%), the PS1 score is capped at 50.**
- "Outstanding" = verified correct on unseen questions, claim→query→row traceability, answers change when the
  data changes, tested guardrails.
- Not allowed: a Snowflake connection that is never queried, answering from local files, mocked results,
  non-Gemma models (incl. Cortex-hosted ones) doing the central AI task.

## Architecture (one question)
guard (write intent) → router (Gemma JSON) → two candidates in parallel:
plan path (Gemma JSON plan → `plan.py` compiles SQL from the semantic model) and SQL path (Gemma writes SQL with
few-shot examples) → `sqlcheck.py` validation → Snowflake execution → repair loop (SQL path only) → reconcile by
result equality (disagreement → 3rd query, majority) → explanation from the SQL AST (`explain.py`) → Gemma narrates
→ `numbers.py` checks every number against the rows (retry → templated fallback).

| Path | Purpose |
|---|---|
| `datamind/semantic.py` | semantic model, join graph, coarsest-root selection, value normalisation |
| `datamind/plan.py` | QueryPlan schema + compiler + double-counting (fan-out) guard |
| `datamind/sqlcheck.py` | SELECT-only validator, table/column checks, row cap, write-intent regex |
| `datamind/pipeline.py` | orchestration, confidence, fallbacks, run log `runs/answers.jsonl` |
| `datamind/prompts.py`, `llm.py` | Gemma prompts; Gemini API / Ollama clients; disk cache `.cache/llm` |
| `datamind/executors.py` | Snowflake (read-only role, QUERY_TAG) and DuckDB (offline tests / independent gold only) |
| `datamind/compare.py`, `numbers.py`, `explain.py` | result equivalence, number grounding, AST explanations |
| `datamind/evaluation.py`, `eval/` | eval harness + 51-question dev set with gold SQL |
| `datamind/discover.py` | drafts a semantic model for a new schema (reusability) |
| `config/datasets/tpch.yaml` | the TPC-H semantic model (tables, joins, metrics, business rules) |
| `snowflake/*.sql` | setup, data-change demo, evidence queries, teardown |
| `app/streamlit_app.py` | UI with evidence tabs |

## Invariants — do not break these
1. Every answer shown to a user comes from rows Snowflake returned for that question. DuckDB is never used to answer
   in the app or demo; it exists for tests and independent ground truth.
2. Only Gemma models (`require_gemma` in `llm.py`). No Cortex LLMs for the central task.
3. Read-only: SELECT only, agent role has SELECT grants only, `USE SECONDARY ROLES NONE` on connect.
4. The plan path is never "repaired" by the model; joins and metric formulas come only from the semantic model.
5. Explanations are generated from the executed SQL, never written by the model.
6. Numbers in prose must pass `numbers.py`; unverifiable → rewrite → templated fallback.
7. Value correction stays conservative (a wrong fuzzy match = silent wrong answer). Show every correction.
8. Eval honesty: leave-one-out few-shot; hold-out questions never go into prompts, the semantic model or the dev set.
   Don't tune on hold-out failures — add a similar new dev question instead.
9. No secrets or data in git: `.env`, keys, `CLAUDE.local.md`, `data/`, `runs/`, `.cache/` are git-ignored.
10. No mock/hard-coded answers outside `tests/`.

## Commands
```bash
pip install -r requirements-dev.txt
python scripts/make_local_tpch.py --scale 0.01          # test data (scale 1 for independent gold)
python -m pytest -q                                     # 55 offline tests; must pass before every commit
python -m datamind check                                # Snowflake + Gemma connectivity
python -m datamind ask "What was revenue in 1995?"       # one question, prints SQL/evidence
python -m datamind eval [--paraphrases] [--ids j01,m03] # accuracy report -> eval/reports/
python -m datamind check-gold --independent duckdb      # Snowflake gold == independent engine
streamlit run app/streamlit_app.py
```

## Working agreements
- Ask Kanhaiya before guessing on anything unclear: rules, scope, design trade-offs, anything irreversible
  (Snowflake DDL, deleting data, publishing). He may come back with a second opinion from another assistant —
  weigh it on its merits and say plainly where you agree or disagree.
- Prefer the smallest change that moves a rubric line. After prompt or semantic-model changes, re-run the eval and
  report the before/after per tier; commit the report in `eval/reports/` (`.md` only).
- Fix root causes in the deterministic layer (semantic model notes, compiler, validator) before adding prompt rules.
- Keep `docs/STATUS.md` current at the end of each working session (done / verified / next / open questions).
- Snowflake-side changes go in `snowflake/01_setup.sql` (idempotent) so a fresh trial reproduces everything.
- Kanhaiya works on Mac and Windows; give commands for the one he's on.
- Private account details (Snowflake account identifier, usernames) live in `CLAUDE.local.md`, never in tracked files.
