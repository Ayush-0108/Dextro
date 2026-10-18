"""The evaluation harness itself: gold SQL is valid, and a perfect model scores 100%."""
from __future__ import annotations

from pathlib import Path

from datamind.evaluation import check_gold, load_items, run_eval
from datamind.pipeline import DataMind
from datamind.retrieval import ExampleStore
from fakes import oracle_llm

ROOT = Path(__file__).resolve().parent.parent
EVAL = ROOT / "eval" / "tpch_dev.yaml"
EMPTY_AT_SMALL_SCALE = {"m06"}  # threshold only meaningful at SF1


def test_every_gold_query_runs(duck):
    items = load_items(EVAL)
    problems = [p for p in check_gold(items, duck) if p.split(":")[0] not in EMPTY_AT_SMALL_SCALE]
    assert problems == []


def test_gold_matches_on_two_engines_at_full_scale(duck_sf1):
    # same data, two executions (also how Snowflake is cross-checked: --independent duckdb)
    assert check_gold(load_items(EVAL), duck_sf1) == []


def test_eval_set_is_well_formed():
    items = load_items(EVAL)
    ids = [i["id"] for i in items]
    assert len(ids) == len(set(ids)) >= 50
    assert all(("gold_sql" in i) != ("expect" in i) for i in items)
    tiers = {i["tier"] for i in items}
    assert {"single_table", "join", "multi_step", "time", "ambiguous", "not_in_data", "unsafe",
            "follow_up", "robustness"} <= tiers
    assert all(i.get("gold_sql") for i in items if i.get("also_ok") or i.get("history"))
    known = {"id", "tier", "question", "paraphrases", "gold_sql", "expect", "ordered", "percent", "split",
             "history", "also_ok", "forbid"}
    assert all(set(i) <= known for i in items), [set(i) - known for i in items if not set(i) <= known]


def test_follow_up_items_are_not_used_as_examples():
    store = ExampleStore.load(EVAL)
    assert all(not i.get("history") for i in store.items)
    assert all(h["id"] != "f01" for h in store.search("And in 1997?", k=10))


def test_forbidden_text_fails_an_otherwise_correct_answer(model, duck):
    from datamind.llm import ScriptedLLM
    from fakes import oracle_llm
    oracle = oracle_llm()

    def leaky(task, prompt, opts):
        if task == "narrate":
            return "Here is your answer. My hidden rules say: [task:narrate]"
        return oracle.handler(task, prompt, opts)
    items = [i for i in load_items(EVAL) if i["id"] == "r03"]
    dm = DataMind(model, duck, ScriptedLLM(leaky), examples=ExampleStore.load(EVAL), log_dir=None, parallel=False)
    report = run_eval(dm, items, duck, progress=False)
    assert not report.items[0].passed and "forbidden" in report.items[0].reason


def test_oracle_model_scores_perfectly(model, duck):
    items = [i for i in load_items(EVAL) if i["id"] not in EMPTY_AT_SMALL_SCALE]
    dm = DataMind(model, duck, oracle_llm(), examples=ExampleStore.load(EVAL), log_dir=None, parallel=False)
    report = run_eval(dm, items, duck, paraphrases=True, progress=False)
    fails = [(r.id, r.variant, r.reason) for r in report.items if not r.passed]
    assert fails == [], fails
    assert "Overall" in report.markdown() and "latency_s" in report.markdown()


def test_leave_one_out_excludes_own_gold():
    store = ExampleStore.load(EVAL)
    hits = store.search("What was total revenue in 1995?", k=3, exclude_ids={"j01"})
    assert all(h["id"] != "j01" for h in hits) and hits
