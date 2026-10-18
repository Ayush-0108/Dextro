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
