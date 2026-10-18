# Status

_Last updated: 2026-10-18 (session 2: Phase 0 audit + fixes)_

## Done
- Track chosen: **PS1 DataMind** (reasoning in `docs/DECISION_LOG.md`).
- Full codebase: semantic model + compiler with fan-out guard, SQL validator, Snowflake/DuckDB executors, Gemma
  clients (Gemini API + Ollama, cached), two-path pipeline with reconciliation, AST explanations, number grounding,
  evaluation harness, schema-discovery drafter, Streamlit UI, CLI.
- Snowflake scripts: setup (warehouse + resource monitor, 3 roles, data copy, masking, grants), data-change demo
  with Time Travel, evidence queries, teardown.
- Eval set: 51 TPC-H questions (7 tiers) + 36 paraphrases, gold SQL hand-written. Gold reproduces published
  TPC-H reference answers (Q3, Q5, Q14) on locally generated SF1 data.
- 123 offline tests passing (Python 3.12.13), incl. the SF1 two-engine gold check run locally; CI workflow in
  `.github/workflows/tests.yml` (CI skips the SF1 test).
- Phase 0 audit: `docs/AUDIT.md` (23 findings). Fixed with tests: double counting via HAVING/ORDER BY, unsafe plan
  values, period filters, comparison tolerance (counts now exact), leading-question numbers, number-checker gaps,
  validator bypasses (table functions, Cortex, cartesian joins, FETCH), write-intent guard, empty-result confidence,
  masked aggregates, Snowflake reconnect + per-query role, Gemini timeout/retry/system-instruction fallback.
- Snowflake trial account created (2026-10-18, $400 credits, trial ends ~2026-11-17). Details in `CLAUDE.local.md`.

## Verified only offline (not yet against live services)
- `snowflake/01_setup.sql` has not been run on a real account yet.
- Prompts have not been run against real Gemma; expect a tuning round after the first eval.

## Next (in order)
0. Decide how the code moves to the team repo `ZERODAY-2026/Dextro` (currently only a README, no LICENSE).
   Save the participant guide PDF into `private/` and re-check the rubric mapping in `docs/AUDIT.md`.
   Make key-pair auth for a `TYPE = SERVICE` app user the default sign-in (audit C1) before step 2.
1. Edition check in a Snowsight worksheet (masking policies need Enterprise):
   ```sql
   SELECT CURRENT_ORGANIZATION_NAME(), CURRENT_ACCOUNT_NAME(), CURRENT_REGION(), CURRENT_USER(), CURRENT_ROLE();
   SHOW DATABASES LIKE 'SNOWFLAKE_SAMPLE_DATA';
   CREATE OR REPLACE DATABASE DM_EDITION_CHECK;
   CREATE MASKING POLICY DM_EDITION_CHECK.PUBLIC.TEST_POLICY AS (v STRING) RETURNS STRING -> v;  -- errors on Standard
   DROP DATABASE DM_EDITION_CHECK;
   ```
   If Standard: remove section 4 (masking) from the setup script and the restricted-role demo; everything else works.
2. Run `snowflake/01_setup.sql` as ACCOUNTADMIN; expect 6001215 / 1500000 / 150000 rows at the end.
3. Gemini API key from https://aistudio.google.com/apikey → `.env`; `python -m datamind check`.
4. `python -m datamind check-gold --independent duckdb` (after `make_local_tpch.py --scale 1`).
5. First `python -m datamind eval`; triage failures; iterate.
6. Hold-out set written by a teammate who never edits prompts (`eval/HOLDOUT_TEMPLATE.yaml`).
7. Optional: second dataset via `draft-model` (criterion 7). Then demo video (`docs/DEMO_SCRIPT.md`).

## Open questions (ask Kanhaiya)
- Push to `ZERODAY-2026/Dextro`? It has its own initial commit (README by rd6260), so our history needs a merge or
  a rebase onto it; force-pushing would delete that commit.
- Submission deadline and judging dates? (decides when to create the fresh judging-window trial account)
- Team members and who owns what (eval hold-out author, demo video, second dataset)?
- Gemma backend for the demo: Gemini API (default) or Ollama — what RAM do the team's laptops have?
- Second dataset: OWID, a UCI dataset, or skip?

## Eval results log
| Date | Model | Split | Overall | Notes |
|---|---|---|---|---|
| – | – | – | – | first real run pending |
