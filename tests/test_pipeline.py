"""End-to-end pipeline tests with a scripted Gemma stand-in and DuckDB (offline)."""
from __future__ import annotations

import json
import re

from datamind.llm import ScriptedLLM, parse_json
from datamind.pipeline import DataMind

PLAN = {"metrics": ["revenue"], "dimensions": [{"field": "cust_nation.n_name"}],
        "filters": [{"field": "cust_region.r_name", "op": "=", "value": "Asia"},
                    {"field": "orders.o_orderdate", "op": "=", "value": 1994, "grain": "year"}],
        "order_by": [{"field": "revenue", "direction": "desc"}], "limit": 3}
GOOD_SQL = """```sql
SELECT n.n_name AS nation, SUM(l.l_extendedprice * (1 - l.l_discount)) AS revenue
FROM DATAMIND_DB.TPCH.LINEITEM l JOIN DATAMIND_DB.TPCH.ORDERS o ON l.l_orderkey = o.o_orderkey
JOIN DATAMIND_DB.TPCH.CUSTOMER c ON o.o_custkey = c.c_custkey
JOIN DATAMIND_DB.TPCH.NATION n ON c.c_nationkey = n.n_nationkey
JOIN DATAMIND_DB.TPCH.REGION r ON n.n_regionkey = r.r_regionkey
WHERE r.r_name = 'ASIA' AND o.o_orderdate >= '1994-01-01' AND o.o_orderdate < '1995-01-01'
GROUP BY n.n_name ORDER BY revenue DESC LIMIT 3
```"""
WRONG_SQL = GOOD_SQL.replace("'ASIA'", "'EUROPE'")


def make(sql="GOOD", alt="GOOD", narr="good", route=None):
    def handler(task, prompt, opts):
        if task == "router":
            return json.dumps(route or {"category": "answerable", "assumptions": ["revenue = net revenue"],
                                        "standalone_question": "Top 3 Asian nations by revenue in 1994"})
        if task == "plan":
            return "```json\n" + json.dumps(PLAN) + "\n```"
        if task in ("sql", "sql_alt"):
            choice = sql if task == "sql" else alt
            return {"GOOD": GOOD_SQL, "WRONG": WRONG_SQL, "BROKEN": "SELECT l.o_orderdate FROM lineitem l"}[choice]
        if task == "repair":
            return GOOD_SQL
        if task == "narrate":
            if narr == "bad":
                return "VIETNAM led with 99,999,999 in revenue."
            rows = re.findall(r"\| ([A-Z ]+) \| ([\d.]+) \|", prompt)
            return f"{rows[0][0]} led with {float(rows[0][1]):,.2f}, ahead of {rows[1][0]}."
        return ""
    return ScriptedLLM(handler)


def agent(model, duck, llm):
    return DataMind(model, duck, llm, log_dir=None, parallel=False)


def test_agreement_gives_high_confidence(model, duck):
    a = agent(model, duck, make()).ask("which asian nations bought the most in 1994?")
    assert a.status == "answered" and a.confidence == "high" and a.chosen.name == "plan"
    assert all(c.status != "unverified" for c in a.number_checks)
    assert any("ASIA" in s for s in a.explanation)
    assert a.result.query_id


def test_repair_loop_fixes_broken_sql(model, duck):
    a = agent(model, duck, make(sql="BROKEN")).ask("q")
    sql_c = next(c for c in a.candidates if c.name == "sql")
    assert sql_c.ok and len(sql_c.attempts) == 2 and a.confidence == "high"


def test_disagreement_triggers_tiebreak_majority(model, duck):
    llm = make(sql="WRONG", alt="GOOD")
    a = agent(model, duck, llm).ask("q")
    assert "sql_alt" in [t for t, _ in llm.log]
    assert a.confidence == "medium" and a.chosen.name == "plan" and a.alternatives


def test_unresolved_disagreement_is_low_confidence(model, duck):
    a = agent(model, duck, make(sql="WRONG", alt="WRONG")).ask("q")
    # WRONG and WRONG agree with each other (2 vs 1) -> majority is the wrong reading; flagged medium, not high
    assert a.confidence in ("medium", "low") and a.alternatives


def test_unverifiable_narration_falls_back_to_template(model, duck):
    a = agent(model, duck, make(narr="bad")).ask("q")
    assert a.narration == "fallback" and "99,999,999" not in a.message
    assert all(c.status in ("verified", "context") for c in a.number_checks)


def test_leading_question_cannot_verify_its_own_number(model, duck):
    def lying(task, prompt, opts):
        if task == "narrate":
            return "Yes, revenue was 300 million."
        return make().handler(task, prompt, opts)
    a = agent(model, duck, ScriptedLLM(lying)).ask("Was revenue 300 million in 1994?")
    assert a.narration == "fallback" and "300 million" not in a.message


def test_empty_agreement_is_not_high_confidence(model, duck):
    empty_plan = {**PLAN, "filters": [PLAN["filters"][0], {"field": "orders.o_orderdate", "op": "=", "value": 2005,
                                                          "grain": "year"}]}
    empty_sql = GOOD_SQL.replace("'1994-01-01'", "'2005-01-01'").replace("'1995-01-01'", "'2006-01-01'")

    def handler(task, prompt, opts):
        if task == "plan":
            return json.dumps(empty_plan)
        if task in ("sql", "sql_alt"):
            return empty_sql
        return make().handler(task, prompt, opts)
    a = agent(model, duck, ScriptedLLM(handler)).ask("Top Asian nations by revenue in 2005")
    assert a.status == "empty" and a.confidence == "medium"
    assert "2005" in a.message and "Kept only rows where" in a.message


def test_masked_aggregate_is_reported_as_masked(model, duck):
    masked_sql = ("```sql\nSELECT AVG(CASE WHEN 1 = 0 THEN c.c_acctbal END) AS avg_balance "
                  "FROM DATAMIND_DB.TPCH.CUSTOMER c\n```")

    def handler(task, prompt, opts):
        if task == "plan":
            return json.dumps({"plan": None, "reason": "x"})
        if task in ("sql", "sql_alt"):
            return masked_sql
        if task == "narrate":
            return "The average balance is not available."
        return make().handler(task, prompt, opts)
    a = agent(model, duck, ScriptedLLM(handler)).ask("average customer balance")
    assert "masked" in a.message and "avg_balance" in a.message


NO_YEAR_PLAN = {**PLAN, "filters": [PLAN["filters"][0]]}
NO_YEAR_SQL = GOOD_SQL.replace(" AND o.o_orderdate >= '1994-01-01' AND o.o_orderdate < '1995-01-01'", "")


def test_agreeing_on_a_dropped_condition_triggers_a_checked_retry(model, duck):
    assert NO_YEAR_SQL != GOOD_SQL
    seen = {}

    def handler(task, prompt, opts):
        if task == "plan":
            return json.dumps(NO_YEAR_PLAN)
        if task == "sql":
            return NO_YEAR_SQL
        if task == "sql_alt":
            seen["feedback"] = "mentions 1994" in prompt
            return GOOD_SQL
        return make().handler(task, prompt, opts)
    a = agent(model, duck, ScriptedLLM(handler)).ask("which asian nations bought the most in 1994?")
    assert seen["feedback"], "the retry must be told what the first queries missed"
    assert a.chosen.name == "sql_alt" and a.checks == [] and a.confidence == "medium"
    assert "covers every condition" in a.agreement
    assert all("1994" in i for c in a.candidates if c.name != "sql_alt" for i in c.issues)


def test_answer_missing_a_condition_is_never_high_confidence(model, duck):
    def handler(task, prompt, opts):
        if task == "plan":
            return json.dumps(NO_YEAR_PLAN)
        if task in ("sql", "sql_alt"):
            return NO_YEAR_SQL
        return make().handler(task, prompt, opts)
    a = agent(model, duck, ScriptedLLM(handler)).ask("which asian nations bought the most in 1994?")
    assert a.status == "answered" and a.confidence == "medium"
    assert a.checks and "1994" in a.checks[0] and "Automatic check" in a.agreement
    assert a.to_json()["checks"] == a.checks


def test_ranking_by_a_masked_value_is_not_narrated_as_a_ranking(model, duck):
    masked_rank = ("```sql\nSELECT c.c_name, CASE WHEN 1 = 0 THEN c.c_acctbal END AS account_balance "
                   "FROM DATAMIND_DB.TPCH.CUSTOMER c ORDER BY account_balance DESC LIMIT 5\n```")

    def handler(task, prompt, opts):
        if task == "plan":
            return json.dumps({"plan": None, "reason": "x"})
        if task in ("sql", "sql_alt"):
            return masked_rank
        if task == "narrate":
            raise AssertionError("a masked ranking must not be narrated")
        return make().handler(task, prompt, opts)
    a = agent(model, duck, ScriptedLLM(handler)).ask("Top 5 customers by account balance")
    assert a.narration == "masked" and "not meaningful" in a.message and "account_balance" in a.message


def test_low_confidence_text_names_the_query_actually_shown(model, duck):
    def handler(task, prompt, opts):
        if task == "plan":
            return json.dumps({"plan": None, "reason": "x"})
        if task == "sql":
            return GOOD_SQL
        if task == "sql_alt":
            return WRONG_SQL
        return make().handler(task, prompt, opts)
    a = agent(model, duck, ScriptedLLM(handler)).ask("which asian nations bought the most in 1994?")
    assert a.confidence == "low" and a.chosen.name == "sql"
    assert "semantic model" not in a.agreement and "wrote directly" in a.agreement


def test_write_requests_never_reach_the_model(model, duck):
    llm = make()
    a = agent(model, duck, llm).ask("Delete all orders from 1992")
    assert a.status == "refused" and llm.log == []


def test_router_outcomes(model, duck):
    for route, status in [({"category": "ambiguous", "interpretations": ["a", "b"]}, "clarify"),
                          ({"category": "not_in_data", "missing": "driver ratings"}, "not_in_data"),
                          ({"category": "unsafe"}, "refused"), ({"category": "chitchat"}, "chitchat")]:
        a = agent(model, duck, make(route=route)).ask("x")
        assert a.status == status


def test_answer_changes_when_data_changes(model, duck_writable):
    q = """```sql
    SELECT c.c_name, SUM(l.l_extendedprice * (1 - l.l_discount)) AS revenue
    FROM DATAMIND_DB.TPCH.LINEITEM l JOIN DATAMIND_DB.TPCH.ORDERS o ON l.l_orderkey = o.o_orderkey
    JOIN DATAMIND_DB.TPCH.CUSTOMER c ON o.o_custkey = c.c_custkey
    WHERE o.o_orderdate BETWEEN '1998-07-01' AND '1998-07-31'
    GROUP BY c.c_name ORDER BY revenue DESC LIMIT 1
    ```"""

    def handler(task, prompt, opts):
        if task == "router":
            return json.dumps({"category": "answerable"})
        if task == "plan":
            return json.dumps({"plan": None, "reason": "test"})
        if task in ("sql", "sql_alt", "repair"):
            return q
        return "x"
    dm = agent(model, duck_writable, ScriptedLLM(handler))
    before = dm.ask("Which customer generated the most revenue in July 1998?")
    duck_writable.execute_admin(
        "INSERT INTO DATAMIND_DB.TPCH.ORDERS VALUES (9000001, 1, 'O', 5400000.00, DATE '1998-07-15', '1-URGENT', "
        "'Clerk#000000001', 0, 'demo')")
    duck_writable.execute_admin(
        "INSERT INTO DATAMIND_DB.TPCH.LINEITEM VALUES (9000001, 1, 2, 1, 50, 5000000.00, 0.00, 0.08, 'N', 'O', "
        "DATE '1998-07-20', DATE '1998-07-25', DATE '1998-07-28', 'DELIVER IN PERSON', 'AIR', 'demo')")
    after = dm.ask("Which customer generated the most revenue in July 1998?")
    assert before.result.rows[0][0] != after.result.rows[0][0] == "Customer#000000001"
    assert before.result.query_id != after.result.query_id


def test_parse_json_tolerates_chatter():
    assert parse_json('Sure! ```json\n{"a": [1, 2,],}\n``` hope that helps')["a"] == [1, 2]
    assert parse_json('thinking... {"plan": null, "reason": "x {y}"} done')["plan"] is None
