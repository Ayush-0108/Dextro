"""Evaluation harness: score DataMind against independently computed ground truth.

Each eval item has a question (plus optional paraphrases) and either hand-written gold SQL or an
expected behaviour (clarify / not_in_data / refused). Gold SQL is executed on a gold engine
(Snowflake, or DuckDB over the official TPC-H generator output for a fully independent check),
and the agent's chosen result is compared with result-set equivalence.
"""
from __future__ import annotations

import datetime as dt
import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .compare import results_match, summarize_rows
from .pipeline import DataMind

BEHAVIOURS = {"clarify": {"clarify"}, "clarify_or_assume": {"clarify", "answered"},
              "not_in_data": {"not_in_data"}, "refused": {"refused"}, "empty": {"empty"},
              "not_in_data_or_empty": {"not_in_data", "empty"},
              "refused_or_not_in_data": {"refused", "not_in_data"}}


def _scaled(rows, factor: float):
    out = []
    for r in rows:
        out.append(tuple(float(v) * factor if isinstance(v, (int, float)) and not isinstance(v, bool)
                         or type(v).__name__ == "Decimal" else v for v in r))
    return out


def _match(pred_rows, gold_rows, ordered: bool, percent: bool) -> bool:
    if results_match(pred_rows, gold_rows, ordered=ordered):
        return True
    if percent:  # a share may be reported as 0.163 or 16.3
        return results_match(pred_rows, _scaled(gold_rows, 100.0), ordered=ordered) or \
            results_match(pred_rows, _scaled(gold_rows, 0.01), ordered=ordered)
    return False


@dataclass
class ItemResult:
    id: str
    tier: str
    question: str
    variant: str
    passed: bool
    status: str
    confidence: str | None
    reason: str = ""
    sql: str | None = None
    query_id: str | None = None
    seconds: float = 0.0
    narration: str = ""


@dataclass
class Report:
    items: list[ItemResult] = field(default_factory=list)
    started: str = field(default_factory=lambda: dt.datetime.now().isoformat(timespec="seconds"))
    meta: dict[str, Any] = field(default_factory=dict)

    def by_tier(self) -> dict[str, tuple[int, int]]:
        agg: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for r in self.items:
            agg[r.tier][0] += int(r.passed)
            agg[r.tier][1] += 1
        return {k: (v[0], v[1]) for k, v in sorted(agg.items())}

    def accuracy(self) -> float:
        return sum(r.passed for r in self.items) / max(1, len(self.items))

    def calibration(self) -> dict[str, tuple[int, int]]:
        agg: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for r in self.items:
            if r.confidence:
                agg[r.confidence][0] += int(r.passed)
                agg[r.confidence][1] += 1
        return {k: (v[0], v[1]) for k, v in agg.items()}

    def markdown(self) -> str:
        lines = [f"# DataMind evaluation — {self.started}", ""]
        for k, v in self.meta.items():
            lines.append(f"- **{k}**: {v}")
        lines += ["", f"**Overall: {sum(r.passed for r in self.items)}/{len(self.items)} "
                      f"({self.accuracy():.0%})**", "", "| Tier | Passed | Total | Accuracy |", "|---|---|---|---|"]
        for tier, (p, n) in self.by_tier().items():
            lines.append(f"| {tier} | {p} | {n} | {p / n:.0%} |")
        cal = self.calibration()
        if cal:
            lines += ["", "Confidence calibration (accuracy of answers by the confidence the agent reported):", "",
                      "| Confidence | Correct | Total |", "|---|---|---|"]
            for k in ("high", "medium", "low"):
                if k in cal:
                    lines.append(f"| {k} | {cal[k][0]} | {cal[k][1]} |")
        fails = [r for r in self.items if not r.passed]
        if fails:
            lines += ["", "## Failures", ""]
            for r in fails:
                lines.append(f"- **{r.id}** ({r.tier}, {r.variant}) — {r.question}  \n  status `{r.status}`; {r.reason}")
                if r.sql:
                    lines.append(f"  ```sql\n  {r.sql.strip().replace(chr(10), chr(10) + '  ')}\n  ```")
        return "\n".join(lines) + "\n"

    def save(self, out_dir: str | Path) -> Path:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        stamp = self.started.replace(":", "").replace("-", "")
        (out / f"eval_{stamp}.json").write_text(json.dumps(
            {"meta": self.meta, "started": self.started, "items": [r.__dict__ for r in self.items]}, indent=2, default=str))
        md = out / f"eval_{stamp}.md"
        md.write_text(self.markdown(), encoding="utf-8")
        return md


def load_items(path: str | Path, split: str | None = None) -> list[dict[str, Any]]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    items = data.get("items", [])
    return [i for i in items if split is None or i.get("split", "dev") == split]


def run_eval(dm: DataMind, items: list[dict[str, Any]], gold_executor: Any, paraphrases: bool = False,
             leave_one_out: bool = True, progress: bool = True) -> Report:
    report = Report(meta={"model": dm.llm.name, "engine": getattr(dm.executor, "engine", "?"),
                          "gold_engine": getattr(gold_executor, "engine", "?"), "items": len(items),
                          "paraphrases": paraphrases, "few_shot": "leave-one-out" if leave_one_out else "all"})
    for item in items:
        variants = [("original", item["question"])]
        if paraphrases:
            variants += [(f"paraphrase {i + 1}", p) for i, p in enumerate(item.get("paraphrases", []))]
        gold = None
        if item.get("gold_sql"):
            gold = gold_executor.run(item["gold_sql"], max_rows=dm.max_rows)
            if not gold.ok:
                report.items.append(ItemResult(item["id"], item.get("tier", "?"), item["question"], "gold", False,
                                               "gold_error", None, f"gold SQL failed: {gold.error}"))
                continue
        for variant, q in variants:
            t0 = time.time()
            ans = dm.ask(q, exclude_example_ids=[item["id"]] if leave_one_out else [])
            secs = round(time.time() - t0, 1)
            res = ans.result
            if gold is not None:
                if ans.status not in ("answered", "empty") or res is None:
                    ok, why = False, f"expected an answer, got {ans.status}: {ans.message[:160]}"
                else:
                    ok = _match(res.rows, gold.rows, bool(item.get("ordered")), bool(item.get("percent")))
                    why = "" if ok else (f"result differs. got {summarize_rows(res.columns, res.rows)} | "
                                         f"gold {summarize_rows(gold.columns, gold.rows)}")
            else:
                expect = item.get("expect", "answered")
                allowed = BEHAVIOURS.get(expect, {expect})
                ok = ans.status in allowed
                if expect == "clarify_or_assume" and ans.status == "answered":
                    ok = bool(ans.assumptions)
                why = "" if ok else f"expected {expect}, got {ans.status}: {ans.message[:160]}"
            report.items.append(ItemResult(item["id"], item.get("tier", "?"), q, variant, ok, ans.status,
                                           ans.confidence, why, ans.chosen.sql if ans.chosen else None,
                                           res.query_id if res else None, secs, ans.narration))
            if progress:
                print(f"{'PASS' if ok else 'FAIL'} {item['id']:<6} {variant:<12} {ans.status:<12} "
                      f"{(ans.confidence or ''):<6} {secs:>5}s  {q[:70]}", flush=True)
    return report


def check_gold(items: list[dict[str, Any]], primary: Any, independent: Any | None = None) -> list[str]:
    """Run every gold query; optionally confirm a second engine computes the same answer."""
    problems = []
    for item in items:
        if not item.get("gold_sql"):
            continue
        a = primary.run(item["gold_sql"])
        if not a.ok:
            problems.append(f"{item['id']}: gold SQL fails on {primary.engine}: {a.error}")
            continue
        if a.row_count == 0:
            problems.append(f"{item['id']}: gold SQL returns no rows")
        if independent is not None:
            b = independent.run(item["gold_sql"])
            if not b.ok:
                problems.append(f"{item['id']}: gold SQL fails on {independent.engine}: {b.error}")
            elif not results_match(a.rows, b.rows, ordered=bool(item.get("ordered"))):
                problems.append(f"{item['id']}: {primary.engine} and {independent.engine} disagree: "
                                f"{summarize_rows(a.columns, a.rows)} vs {summarize_rows(b.columns, b.rows)}")
    return problems
