# Contributing

1. `pip install -r requirements-dev.txt && python scripts/make_local_tpch.py --scale 0.01`
2. `python -m pytest -q` must pass (fully offline: DuckDB + a scripted model; no credentials needed).
3. Changes to prompts or the semantic model: run `python -m datamind eval` against Snowflake + Gemma and include the
   before/after report from `eval/reports/` in the pull request. Never add hold-out questions to prompts or the dev set.
4. New datasets: add `config/datasets/<name>.yaml` and `eval/<name>_dev.yaml` (see docs/ADDING_A_DATASET.md).
5. Never commit `.env`, keys, data files or query results containing real data.

Good first issues: more number formats in `numbers.py`; plan support for ratios between groups; more
plain-English renderings in `explain.py`; a second dataset.
