# Adding a dataset

DataMind needs only a semantic model YAML. No code changes.

1. **Load the data into Snowflake** in its own schema (e.g. `DATAMIND_DB.OWID`), using a stage + `COPY INTO`, or
   Snowsight's *Load data* wizard. Grant the agent roles read access:
   ```sql
   USE ROLE ACCOUNTADMIN;
   GRANT USAGE ON SCHEMA DATAMIND_DB.OWID TO ROLE DATAMIND_AGENT;
   GRANT SELECT ON ALL TABLES IN SCHEMA DATAMIND_DB.OWID TO ROLE DATAMIND_AGENT;
   ```
2. **Draft the model**: `python -m datamind draft-model --schema OWID --name owid --out config/datasets/owid.yaml`
3. **Review the draft** — this is where quality comes from:
   - one-sentence descriptions for each table ("one row per …") and column (units!);
   - joins: keep only true many-to-one links; add composite keys; if one table plays two roles (e.g. a country table
     used for both importer and exporter), create one entity per role with distinct aliases;
   - metrics: replace the starter `COUNT(*)` metrics with the business measures, with exact formulas and the grain
     table each is defined over; mark `fanout_safe: true` only for COUNT(DISTINCT …), MIN, MAX;
   - `notes`: business rules (which date "a year" means, how missing values are coded);
   - `data_coverage`, `sample_questions`, `sensitive: true` on personal fields.
4. **Write an eval file** `eval/owid_dev.yaml` with 20–30 questions and gold SQL (see `eval/tpch_dev.yaml`).
5. **Run**: `DATAMIND_DATASET=config/datasets/owid.yaml SNOWFLAKE_SCHEMA=OWID python -m datamind eval`
   and `streamlit run app/streamlit_app.py`.
