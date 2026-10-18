# Status

_Last updated: 2026-10-18_

## Done
- Track chosen: **PS1 DataMind** (reasoning in `docs/DECISION_LOG.md`).
- Full codebase: semantic model + compiler with fan-out guard, SQL validator, Snowflake/DuckDB executors, Gemma
  clients (Gemini API + Ollama, cached), two-path pipeline with reconciliation, AST explanations, number grounding,
  evaluation harness, schema-discovery drafter, Streamlit UI, CLI.
- Snowflake scripts: setup (warehouse + resource monitor, 3 roles, data copy, masking, grants), data-change demo
  with Time Travel, evidence queries, teardown.
- Eval set: 51 TPC-H questions (7 tiers) + 36 paraphrases, gold SQL hand-written. Gold reproduces published
  TPC-H reference answers (Q3, Q5, Q14) on locally generated SF1 data.
- 55 offline tests passing; CI workflow in `.github/workflows/tests.yml`.
- Snowflake trial account created (2026-10-18, $400 credits, trial ends ~2026-11-17). Details in `CLAUDE.local.md`.

## Verified only offline (not yet against live services)
- `snowflake/01_setup.sql` has not been run on a real account yet.
- Prompts have not been run against real Gemma; expect a tuning round after the first eval.

## Next (in order)
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
- Submission deadline and judging dates? (decides when to create the fresh judging-window trial account)
- Team members and who owns what (eval hold-out author, demo video, second dataset)?
- Gemma backend for the demo: Gemini API (default) or Ollama — what RAM do the team's laptops have?
- Second dataset: OWID, a UCI dataset, or skip?

## Eval results log
| Date | Model | Split | Overall | Notes |
|---|---|---|---|---|
| – | – | – | – | first real run pending |
