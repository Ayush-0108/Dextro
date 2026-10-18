"""Tests for the Chinook dataset (reusability criterion):

- Semantic model loads and validates
- Query compiler builds correct SQL for 3 plans (including role-playing employee/manager joins)
- All gold SQL in eval/chinook_dev.yaml executes cleanly on DuckDB
- Oracle model pipeline scores 100% on chinook_dev.yaml
- Skips cleanly if data/chinook/ has not been generated.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from datamind.evaluation import check_gold, load_items, run_eval
from datamind.executors import DuckDBExecutor
from datamind.llm import ScriptedLLM
from datamind.pipeline import DataMind
from datamind.plan import OrderSpec, QueryPlan, compile_plan
from datamind.retrieval import ExampleStore
from datamind.semantic import load_model

ROOT = Path(__file__).resolve().parent.parent
MODEL_PATH = ROOT / "config" / "datasets" / "chinook.yaml"
EVAL_PATH = ROOT / "eval" / "chinook_dev.yaml"
DATA_DIR = ROOT / "data" / "chinook"


@pytest.fixture
def chinook_dir():
    if not DATA_DIR.exists() or not list(DATA_DIR.glob("*.parquet")):
        pytest.skip("data/chinook not generated; run scripts/get_chinook.py")
    return DATA_DIR


@pytest.fixture
def chinook_model():
    return load_model(MODEL_PATH)


@pytest.fixture
def chinook_duck(chinook_dir):
    return DuckDBExecutor(chinook_dir, database="DATAMIND_DB", schema="CHINOOK")


def chinook_oracle_llm() -> ScriptedLLM:
    raw_items = yaml.safe_load(EVAL_PATH.read_text(encoding="utf-8"))["items"]
    idx = {}
    for it in raw_items:
        for q in [it["question"], *it.get("paraphrases", [])]:
            idx[q.strip().lower()] = it

    def find(prompt: str):
        m = re.search(r'NEW QUESTION: (".*")', prompt)
        if m:
            q = json.loads(m.group(1))
        else:
            found = re.findall(r"^Question: (.*)$", prompt, re.M)
            q = found[-1] if found else ""
        return q, idx.get(q.strip().lower())

    def handler(task: str, prompt: str, opts: dict) -> str:
        q, item = find(prompt)
        if task == "router":
            expect = (item or {}).get("expect", "")
            cat = (
                "ambiguous"
                if expect.startswith("clarify")
                else "not_in_data"
                if expect.startswith("not_in_data")
                else "unsafe"
                if expect.startswith("refused")
                else "answerable"
            )
            return json.dumps({
                "category": cat,
                "standalone_question": q,
                "assumptions": [],
                "interpretations": ["by sales", "by track count"] if cat == "ambiguous" else [],
                "clarifying_question": "Which measure?",
                "missing": "that information",
            })
        if task == "plan":
            return json.dumps({"plan": None, "reason": "oracle uses SQL"})
        if task in ("sql", "sql_alt", "repair"):
            sql = item["gold_sql"] if item and item.get("gold_sql") else "SELECT 1"
            return f"```sql\n{sql}\n```"
        if task == "narrate":
            m = re.search(r"\|---\|.*?\n\| (.+?) \|", prompt, re.S)
            first = m.group(1).split(" | ") if m else []
            return "The first result row is " + ", ".join(first) + "." if first else "No rows."
        return ""

    return ScriptedLLM(handler, name="gemma-chinook-oracle-test")


def test_chinook_model_loads(chinook_model):
    assert chinook_model.name == "chinook"
    assert chinook_model.database == "DATAMIND_DB"
    assert chinook_model.schema_name == "CHINOOK"
    assert len(chinook_model.entities) >= 11
    aliases = {e.alias for e in chinook_model.entities}
    assert {"invoice_line", "invoice", "customer", "track", "album", "artist", "genre",
            "media_type", "employee", "support_rep", "manager", "playlist", "playlist_track"} <= aliases
    metrics = {m.name for m in chinook_model.metrics}
    assert {"sales", "track_count", "customer_count", "invoice_count"} <= metrics


def test_chinook_eval_set_is_well_formed():
    items = load_items(EVAL_PATH)
    ids = [i["id"] for i in items]
    assert len(ids) == len(set(ids)) >= 20
    assert all(("gold_sql" in i) != ("expect" in i) for i in items)
    tiers = {i["tier"] for i in items}
    assert {"single_table", "join", "multi_step", "time", "ambiguous", "not_in_data", "unsafe"} <= tiers


def test_chinook_compiler_builds_correct_sql(chinook_model, chinook_duck):
    # Plan 1: Sales by artist (joins: invoice_line -> track -> album -> artist)
    p1 = QueryPlan(
        metrics=["sales"],
        dimensions=["artist.name"],
        order_by=[OrderSpec(field="sales", direction="desc")],
        limit=5,
    )
    c1 = compile_plan(p1, chinook_model)
    assert "DATAMIND_DB.CHINOOK.INVOICE_LINE" in c1.sql
    assert "DATAMIND_DB.CHINOOK.ARTIST" in c1.sql
    r1 = chinook_duck.run(c1.sql)
    assert r1.ok and len(r1.rows) == 5
    assert r1.rows[0][0] == "Iron Maiden"

    # Plan 2: Track count by genre
    p2 = QueryPlan(
        metrics=["track_count"],
        dimensions=["genre.name"],
        order_by=[OrderSpec(field="track_count", direction="desc")],
        limit=5,
    )
    c2 = compile_plan(p2, chinook_model)
    assert "DATAMIND_DB.CHINOOK.GENRE" in c2.sql
    r2 = chinook_duck.run(c2.sql)
    assert r2.ok and len(r2.rows) == 5
    assert r2.rows[0][0] == "Rock"

    # Plan 3: Role-playing join (employee -> manager via reports_to)
    p3 = QueryPlan(
        metrics=["employee_count"],
        dimensions=["manager.last_name"],
        order_by=[OrderSpec(field="employee_count", direction="desc")],
    )
    c3 = compile_plan(p3, chinook_model)
    assert "DATAMIND_DB.CHINOOK.EMPLOYEE AS employee" in c3.sql
    assert "DATAMIND_DB.CHINOOK.EMPLOYEE AS manager" in c3.sql
    assert "employee.reports_to = manager.employee_id" in c3.sql
    r3 = chinook_duck.run(c3.sql)
    assert r3.ok and len(r3.rows) == 3
    assert r3.rows[0][0] == "Edwards"


def test_all_chinook_gold_sql_runs_on_duckdb(chinook_duck):
    items = load_items(EVAL_PATH)
    problems = check_gold(items, chinook_duck)
    assert problems == []


def test_chinook_oracle_pipeline_scores_100_percent(chinook_model, chinook_duck):
    items = load_items(EVAL_PATH)
    dm = DataMind(
        chinook_model,
        chinook_duck,
        chinook_oracle_llm(),
        examples=ExampleStore.load(EVAL_PATH),
        log_dir=None,
        parallel=False,
    )
    report = run_eval(dm, items, chinook_duck, paraphrases=True, progress=False)
    fails = [(r.id, r.variant, r.reason) for r in report.items if not r.passed]
    assert fails == []
    assert report.accuracy() == 1.0
