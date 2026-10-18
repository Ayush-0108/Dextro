# 5-minute demo script

Record in one take with the real system (Snowflake + Gemma). Before recording: run `python -m datamind check`,
then `python scripts/warm_demo.py` (asks every demo question once, in this order, so a 16 GB laptop answers in
seconds instead of minutes), and keep a Snowsight tab open on `snowflake/02_demo_data_change.sql`. Be explicit
when presenting: Gemma's replies come from the disk cache; every SQL query still runs live in Snowflake, with a new
query id each time. Ask the questions in a fresh conversation in the order below.
Rubric criteria in brackets.

| Time | Do | Say |
|---|---|---|
| 0:00 | App home | "DataMind answers questions about data in Snowflake. Every answer is computed by SQL, cross-checked, and traceable." [C1] |
| 0:20 | Ask **"Which 5 nations generated the most revenue from customers in ASIA in 1994?"** | Point at the green highlighted numbers and *high confidence*. [1, 2] |
| 0:45 | Tabs: Result → How it was computed → SQL & evidence | "The explanation is generated from the SQL that ran, not by the AI. Here is the Snowflake query id." Click *Download evidence*. [3] |
| 1:15 | Cross-check tab | "Two independent queries — one compiled from a plan with verified joins, one written by Gemma — returned identical results." [1, 5] |
| 1:35 | Follow-up: **"and in 1995?"** | Follow-ups are rewritten into full questions. [2] |
| 1:55 | Ask **"Who are our best customers?"**, click an interpretation | Ambiguity is surfaced, not guessed. [6] |
| 2:15 | Ask **"What is the average delivery driver rating?"** | Honest "not in this data". [6] |
| 2:30 | Ask **"Delete all orders from 1992"** | Read-only, refused before any model call; the role can't write anyway. [6] |
| 2:45 | Ask **"Which customer generated the most revenue from orders placed in July 1998?"**, then run STEP 1–2 of `02_demo_data_change.sql` in Snowsight, ask again | The answer changes, with a new query id. Run STEP 4: Time Travel shows before vs after. Run STEP 5 to revert. [Outstanding band: "answers change when data changes", Snowflake depth] |
| 3:40 | Sidebar → *Restricted*; ask **"Top 5 customers by account balance in the BUILDING segment"** | Balances are masked by a Snowflake masking policy; DataMind says so. [4] |
| 4:05 | Show `eval/reports/...md` | Accuracy per tier on 66 questions + paraphrases, and the hold-out score. Gold answers are computed independently. [1, 7, C7] |
| 4:30 | Show `config/datasets/tpch.yaml` and `python -m datamind draft-model` | A new dataset is configuration, not code. [7] |
| 4:50 | Close | "Correct when it can be, honest when it can't, and you can check every number." |
