"""Coverage and shape checks (datamind/verify.py): catch queries that drop a stated condition, never flag gold."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from datamind.executors import QueryResult
from datamind.verify import check_candidate, question_constraints

ROOT = Path(__file__).resolve().parent.parent


def rows(n):
    return QueryResult(sql="", columns=["x"], rows=[(i,) for i in range(n)])


def test_constraints_from_a_question(model):
    c = question_constraints("Top 5 customers in ASIA by revenue in 1995 with more than 38 orders shipped by REG AIR",
                             model)
    assert c.years == {1995} and c.top_n == 5
    assert set(c.values.values()) == {"ASIA", "REG AIR"}          # REG AIR wins over AIR
    assert [n[1] for n in c.numbers] == [38.0]


@pytest.mark.parametrize("q", [
    "What was revenue by ship mode in 1995?",           # 'ship' is a word here, not the SHIP mode
    "How many orders in the last 3 months of data?",    # a duration, not a threshold
    "How many orders were placed in Q1 1993?",          # quarter number
    "Top 3 manufacturers by revenue for each year",     # per-group ranking: row count isn't 3
])
def test_no_constraint_from_ordinary_words(model, q):
    c = question_constraints(q, model)
    assert "SHIP" not in c.values.values() and c.numbers == [] and c.top_n is None


def test_two_digit_years(model):
    assert question_constraints("Orders from Mar through May '96", model).years == {1996}


def test_missing_conditions_are_reported(model):
    c = question_constraints("How many orders were placed by customers in ASIA in 1995?", model)
    sql_ok = ("SELECT COUNT(*) FROM orders o JOIN customer c ON 1=1 WHERE r.r_name ILIKE '%asia%' "
              "AND o.o_orderdate BETWEEN '1995-01-01' AND '1995-12-31'")
    assert check_candidate(c, sql_ok, rows(1)) == []
    issues = check_candidate(c, "SELECT COUNT(*) FROM orders o", rows(1))
    assert any("1995" in i for i in issues) and any("ASIA" in i for i in issues)


def test_percent_and_scaled_thresholds(model):
    c = question_constraints("How many line items had a discount above 5% and a price over $90k?", model)
    assert check_candidate(c, "SELECT COUNT(*) FROM lineitem WHERE l_discount > 0.05 AND l_extendedprice > 90000",
                           rows(1)) == []
    assert len(check_candidate(c, "SELECT COUNT(*) FROM lineitem", rows(1))) == 2


def test_result_shape(model):
    top = question_constraints("Which 5 nations had the most revenue?", model)
    assert check_candidate(top, "SELECT 1", rows(5)) == []
    assert "top 5" in check_candidate(top, "SELECT 1", rows(25))[0]
    single = question_constraints("How many customers have a negative balance?", model)
    assert "single number" in check_candidate(single, "SELECT 1", rows(3))[0]
    assert question_constraints("How many orders are there for each priority?", model).single_value is False


@pytest.mark.parametrize("dataset,eval_file,data_fixture", [
    ("config/datasets/tpch.yaml", "eval/tpch_dev.yaml", "duck"),
    ("config/datasets/chinook.yaml", "eval/chinook_dev.yaml", "chinook"),
])
def test_gold_answers_are_never_flagged(request, dataset, eval_file, data_fixture):
    from datamind.executors import DuckDBExecutor
    from datamind.semantic import load_model
    m = load_model(ROOT / dataset)
    if data_fixture == "duck":
        ex = request.getfixturevalue("duck")
    else:
        d = ROOT / "data" / "chinook"
        if not list(d.glob("*.parquet")):
            pytest.skip("Chinook data not generated (python scripts/get_chinook.py)")
        ex = DuckDBExecutor(d, m.database, m.schema_name)
    flagged = []
    for it in yaml.safe_load((ROOT / eval_file).read_text())["items"]:
        if it.get("gold_sql"):
            res = ex.run(it["gold_sql"])
            for q in [it["question"], *it.get("paraphrases", [])]:
                if issues := check_candidate(question_constraints(q, m), it["gold_sql"], res):
                    flagged.append((it["id"], q, issues))
    assert flagged == []


def test_dropping_a_year_from_gold_is_caught(model):
    caught = total = 0
    for it in yaml.safe_load((ROOT / "eval/tpch_dev.yaml").read_text())["items"]:
        c = question_constraints(it["question"], model)
        if it.get("gold_sql") and len(c.years) == 1:
            y = next(iter(c.years))
            total += 1
            caught += bool(check_candidate(c, it["gold_sql"].replace(str(y), str(y - 1)), None))
    assert total >= 10 and caught == total
