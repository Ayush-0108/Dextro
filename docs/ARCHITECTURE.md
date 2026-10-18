# Architecture and design decisions

## Components

| Module | Role | AI? |
|---|---|---|
| `semantic.py` | Loads the dataset's semantic model: entities (table aliases), columns with descriptions and known values, many-to-one joins, verified metric formulas. Join graph, root selection. | no |
| `plan.py` | `QueryPlan` schema and the compiler: plan → SQL using only modelled joins and metrics, with the double-counting guard. | no |
| `sqlcheck.py` | Static validation of any SQL before execution; write-intent guard for questions. | no |
| `executors.py` | `SnowflakeExecutor` (read-only role, secondary roles off, QUERY_TAG, timeout, row cap). `DuckDBExecutor` for offline tests and independent gold answers. | no |
| `compare.py` | Result-set equivalence used for candidate agreement and evaluation. | no |
| `explain.py` | Plain-English explanation derived from the executed SQL's syntax tree. | no |
| `numbers.py` | Checks every number in the written answer against the result rows. | no |
| `llm.py` | Gemma clients (Gemini API, Ollama), disk cache, Gemma-only guard, JSON extraction. | — |
| `prompts.py` | Prompts for router, planner, SQL writer, repairer, narrator. | — |
| `pipeline.py` | Orchestration, reconciliation, confidence, fallbacks, run log. | — |
| `retrieval.py` | Few-shot retrieval of verified question→SQL pairs (dev split only). | no |
| `evaluation.py` | Harness: gold execution, scoring, per-tier and calibration report. | no |
| `discover.py` | Drafts a semantic model for a new schema from `INFORMATION_SCHEMA` and data profiling. | no |

## One question, step by step

1. **Guard.** Regex for write intent ("delete all…", "drop the…"): refuse before any model call.
2. **Route (Gemma, JSON).** answerable / ambiguous / not_in_data / unsafe / chitchat, plus a standalone rewrite of
   follow-ups and explicit assumptions (e.g. relative dates are relative to the end of the data).
3. **Two candidates in parallel.**
   - *Plan path*: Gemma emits `{metrics, dimensions, filters, having, order_by, limit}`. The compiler resolves
     every field against the semantic model, picks the coarsest root table from which all needed tables are
     reachable via many-to-one joins, rejects metrics whose grain is coarser than the root (would double count),
     normalises category values (with a note when it corrects a spelling), and emits SQL. If the question doesn't
     fit the plan format, Gemma says so and this path stands down.
   - *SQL path*: Gemma writes Snowflake SQL with the schema, business rules, and the three most similar verified
     examples.
4. **Validate → run → repair.** Each SQL is validated (single SELECT, known tables pinned to the configured
   database/schema, known columns in the right tables, row cap). Validation or Snowflake errors are fed back to Gemma
   up to twice. The plan path is never "repaired" by the model.
5. **Reconcile.** Successful results are grouped by equivalence. Two agreeing candidates → high confidence. Only one
   success, or disagreement → a third, independently prompted query at higher temperature; the majority wins
   (medium), otherwise the plan-path result is shown with low confidence and the alternatives are listed.
6. **Explain** from the executed SQL (tables and their roles, join keys, filters in words, grouping, formulas,
   ordering, limit). Role-playing tables (NATION as customer vs supplier nation) are resolved through join keys.
7. **Narrate (Gemma) and check numbers.** Every number/date is matched to a cell, the question/SQL/result shape,
   or a simple derivation; anything else triggers one rewrite with feedback, then a deterministic template.
8. **Log** the full answer with candidates, query ids and timings to `runs/answers.jsonl`.

## Decisions and trade-offs

- **Plan + SQL instead of SQL only.** The plan path cannot invent joins or formulas and is immune to fan-out bugs,
  but cannot express everything. The SQL path covers the long tail. Running both gives a measurable agreement
  signal for almost free (one extra Gemma call; queries on an X-Small warehouse take well under a second).
- **Agreement on results, not on SQL text.** Different SQL can be equally correct; we compare what Snowflake returned.
- **Deterministic explanations.** Model-written explanations can drift from the query; AST-derived ones cannot.
- **Gemma 4 31B by default.** PS1 allows any Gemma variant; the largest gives the best SQL. The Ollama backend
  keeps a fully local option.
- **No Cortex.** Cortex Analyst/Agents would move the central AI task off Gemma. Snowflake is used for what it is best
  at: storage, execution, governance, cost control, history and time travel.
- **Copy of sample data instead of a view on the share.** Masking policies and the data-change demo need writable,
  owned tables. The copy is ~1 GB inside the account and costs nothing noticeable on a trial.
- **Conservative value correction.** A fuzzy match that maps "ANTARCTICA" to "AMERICA" would be a silent wrong
  answer, so only near-certain typos and explicit aliases are corrected, and every correction is shown.

## Threat model (read-only data agent)

| Threat | Mitigation |
|---|---|
| Prompt asks to modify data | Guard before the model; router `unsafe`; validator rejects non-SELECT; role has SELECT only |
| SQL reads other databases / account usage | Validator allows only modelled tables, pins database and schema; role has no other grants |
| Session inherits a powerful user's roles | `USE SECONDARY ROLES NONE` on connect; dedicated `DATAMIND_APP` user recommended |
| Runaway cost | X-Small, 60 s auto-suspend, 120 s statement timeout, row cap, daily resource monitor |
| PII exposure | Masking policy on phone/balance for the restricted role; DataMind reports masked columns |
| Secrets in repo | `.env` and key files git-ignored; `.env.example` only |

## Coverage and shape checks (added 2026-10-18)
`datamind/verify.py` runs after execution, before reconciliation. It extracts the years, thresholds, known category
values, "top N" and single-number phrasing from the (standalone) question and checks each executed candidate's SQL
and row count against them. Results: preference among disagreeing candidates, a cap at medium confidence, and one
feedback-driven SQL retry when every candidate fails. It makes no model calls. Tests: `tests/test_verify.py`.
