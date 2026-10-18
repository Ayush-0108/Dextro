"""The DataMind question-answering pipeline.

    question
      -> write-intent guard (deterministic)
      -> router (Gemma): answerable / ambiguous / not in data / unsafe / chitchat, standalone rewrite
      -> two independent candidates, generated in parallel:
           plan: Gemma -> JSON plan -> compiled to SQL with verified joins + metrics (deterministic)
           sql:  Gemma -> SQL directly, with retrieved verified examples
      -> each: static validation -> Snowflake execution under a read-only role -> repair loop on error
      -> reconcile: identical results = high confidence; disagreement -> third independent query, majority
      -> deterministic explanation from the executed SQL
      -> Gemma narrates from the rows; every number is checked against the rows (else retry / fallback)
"""
from __future__ import annotations

import dataclasses
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Sequence

import sqlglot
from pydantic import ValidationError
from sqlglot import exp

from .compare import results_match, summarize_rows
from .executors import QueryResult
from .explain import explain_sql
from .llm import LLM, LLMError, parse_json
from .numbers import NumberCheck, check_numbers, unverified
from .plan import QueryPlan, compile_plan
from .prompts import narrate_prompt, plan_prompt, repair_prompt, router_prompt, sql_prompt
from .retrieval import ExampleStore
from .semantic import SemanticError, SemanticModel
from .sqlcheck import extract_sql, is_write_request, validate_sql

Status = Literal["answered", "empty", "clarify", "not_in_data", "refused", "chitchat", "error"]
_PREFERENCE = {"plan": 0, "sql": 1, "sql_alt": 2}


@dataclass
class Candidate:
    name: str
    sql: str | None = None
    plan: dict[str, Any] | None = None
    notes: list[str] = field(default_factory=list)
    error: str | None = None
    attempts: list[dict[str, Any]] = field(default_factory=list)
    result: QueryResult | None = None

    @property
    def ok(self) -> bool:
        return self.result is not None and self.result.ok

    def to_json(self, max_rows: int = 50) -> dict[str, Any]:
        r = self.result.to_json() if self.result else None
        if r:
            r["rows"] = r["rows"][:max_rows]
        return {"name": self.name, "sql": self.sql, "plan": self.plan, "notes": self.notes, "error": self.error,
                "attempts": self.attempts, "result": r}


@dataclass
class Answer:
    answer_id: str
    question: str
    standalone_question: str
    status: Status
    message: str
    confidence: Literal["high", "medium", "low"] | None = None
    agreement: str = ""
    assumptions: list[str] = field(default_factory=list)
    interpretations: list[str] = field(default_factory=list)
    chosen: Candidate | None = None
    candidates: list[Candidate] = field(default_factory=list)
    alternatives: list[dict[str, Any]] = field(default_factory=list)
    explanation: list[str] = field(default_factory=list)
    number_checks: list[NumberCheck] = field(default_factory=list)
    narration: str = "gemma"          # gemma | fallback
    timings: dict[str, float] = field(default_factory=dict)
    model_name: str = ""
    engine: str = ""
    role: str | None = None

    @property
    def result(self) -> QueryResult | None:
        return self.chosen.result if self.chosen else None

    def history_entry(self) -> dict[str, Any]:
        return {"question": self.question, "standalone_question": self.standalone_question,
                "summary": self.message[:240], "sql": self.chosen.sql if self.chosen else None}

    def to_json(self) -> dict[str, Any]:
        return {
            "answer_id": self.answer_id, "question": self.question, "standalone_question": self.standalone_question,
            "status": self.status, "message": self.message, "confidence": self.confidence,
            "agreement": self.agreement, "assumptions": self.assumptions, "interpretations": self.interpretations,
            "chosen": self.chosen.name if self.chosen else None,
            "candidates": [c.to_json() for c in self.candidates], "alternatives": self.alternatives,
            "explanation": self.explanation, "number_checks": [dataclasses.asdict(n) for n in self.number_checks],
            "narration": self.narration, "timings": self.timings, "model": self.model_name, "engine": self.engine,
            "role": self.role,
        }


class DataMind:
    def __init__(self, model: SemanticModel, executor: Any, llm: LLM, examples: ExampleStore | None = None,
                 max_rows: int = 1000, log_dir: str | Path | None = "runs", thinking: bool = True,
                 max_repairs: int = 2, parallel: bool = True):
        self.model = model
        self.executor = executor
        self.llm = llm
        self.examples = examples or ExampleStore([])
        self.max_rows = max_rows
        self.log_dir = Path(log_dir) if log_dir else None
        self.thinking = thinking
        self.max_repairs = max_repairs
        self.parallel = parallel

    # ------------------------------------------------------------------ public
    def ask(self, question: str, history: Sequence[dict[str, Any]] = (), role: str | None = None,
            exclude_example_ids: Sequence[str] = ()) -> Answer:
        t0 = time.time()
        aid = uuid.uuid4().hex[:10]
        # the role travels with every query (the executor may be shared by several app sessions)
        ans = Answer(answer_id=aid, question=question, standalone_question=question, status="error", message="",
                     model_name=self.llm.name, engine=getattr(self.executor, "engine", ""),
                     role=role.upper() if role else getattr(self.executor, "role", None))
        try:
            self._ask(ans, question, list(history), set(exclude_example_ids))
        except Exception as e:  # never crash the UI; report honestly
            ans.status, ans.message = "error", f"Something went wrong while answering: {type(e).__name__}: {e}"
        ans.timings["total_s"] = round(time.time() - t0, 2)
        self._log(ans)
        return ans

    # ------------------------------------------------------------------ steps
    def _ask(self, ans: Answer, question: str, history: list[dict[str, Any]], exclude: set[str]) -> None:
        if is_write_request(question):
            ans.status = "refused"
            ans.message = ("DataMind is read-only: it answers questions about the data but never changes it. "
                           "Its Snowflake role has SELECT privileges only.")
            return

        t = time.time()
        route = self._route(question, history)
        ans.timings["route_s"] = round(time.time() - t, 2)
        cat = route.get("category", "answerable")
        ans.standalone_question = route.get("standalone_question") or question
        ans.assumptions = [a for a in route.get("assumptions", []) if isinstance(a, str) and a.strip()]
        if cat == "chitchat":
            ans.status = "chitchat"
            ans.message = (f"I answer questions about **{self.model.title}** by running read-only SQL in Snowflake "
                           f"and showing the query and rows behind every answer. {self.model.data_coverage.strip()} "
                           "Try: " + "; ".join(f"“{q}”" for q in self.model.sample_questions[:3]))
            return
        if cat == "unsafe":
            ans.status = "refused"
            ans.message = ("I can't do that. I only run read-only queries over this dataset. "
                           + (route.get("reason") or "")).strip()
            return
        if cat == "not_in_data":
            ans.status = "not_in_data"
            missing = route.get("missing") or route.get("reason") or "the information needed"
            ans.message = f"This dataset doesn't contain {missing.rstrip('.')}. {self.model.data_coverage.strip()}"
            if route.get("clarifying_question"):
                ans.message += f" {route['clarifying_question']}"
            return
        if cat == "ambiguous":
            ans.status = "clarify"
            ans.interpretations = [i for i in route.get("interpretations", []) if isinstance(i, str)]
            ans.message = route.get("clarifying_question") or "Your question can be read in more than one way. Which did you mean?"
            return

        q = ans.standalone_question
        examples = self.examples.search(q, k=3, exclude_ids=exclude)
        previous_sql = next((h.get("sql") for h in reversed(history) if h.get("sql")), None)

        t = time.time()
        jobs = [lambda: self._plan_candidate(q, ans.assumptions),
                lambda: self._sql_candidate(q, ans.assumptions, examples, previous_sql)]
        if self.parallel:
            with ThreadPoolExecutor(max_workers=2) as pool:
                cands = list(pool.map(lambda f: f(), jobs))
        else:
            cands = [f() for f in jobs]
        ans.timings["generate_s"] = round(time.time() - t, 2)

        t = time.time()
        for c in cands:
            self._validate_and_run(c, q, ans.answer_id, ans.role)
        ans.candidates = cands
        self._reconcile(ans, q, examples, previous_sql)
        ans.timings["execute_s"] = round(time.time() - t, 2)
        if not ans.chosen:
            return

        res = ans.chosen.result
        assert res is not None
        ans.assumptions += [n for n in ans.chosen.notes if n not in ans.assumptions]
        ans.explanation = explain_sql(ans.chosen.sql or "", self.model)
        masked = self._masked_columns(res, ans.chosen.sql or "")
        if res.row_count == 0:
            ans.status = "empty"
            if ans.confidence == "high":
                # agreeing on "nothing found" is weak evidence: a filter value that doesn't occur in the data
                # makes every candidate return zero rows
                ans.confidence = "medium"
                ans.agreement += " An empty result can also mean a filter value doesn't occur in the data."
            filters = next((s for s in ans.explanation if s.startswith("Kept only rows where")), "")
            ans.message = ("No rows matched this question, so there is nothing to report. "
                           + (f"{filters} " if filters else "Check the filters in “How this was computed”. ")
                           + self.model.data_coverage.strip())
            return
        ans.status = "answered"
        t = time.time()
        self._narrate(ans, q, res)
        ans.timings["narrate_s"] = round(time.time() - t, 2)
        if masked:
            ans.message += (f" Note: {', '.join(masked)} {'is' if len(masked) == 1 else 'are'} masked for the "
                            f"{ans.role} role by a Snowflake masking policy, so those values are hidden.")

    def _route(self, question: str, history: list[dict[str, Any]]) -> dict[str, Any]:
        system, prompt = router_prompt(self.model, question, history)
        try:
            d = parse_json(self.llm.complete(prompt, system=system, json_mode=True))
            if not isinstance(d, dict):
                raise LLMError("router reply is not an object")
            d["category"] = str(d.get("category", "answerable")).strip().lower().replace(" ", "_")
            if d["category"] not in {"answerable", "ambiguous", "not_in_data", "unsafe", "chitchat"}:
                d["category"] = "answerable"
            return d
        except LLMError:
            return {"category": "answerable", "standalone_question": question, "assumptions": []}

    def _plan_candidate(self, q: str, assumptions: list[str]) -> Candidate:
        c = Candidate(name="plan")
        system, prompt = plan_prompt(self.model, q, assumptions)
        feedback = ""
        for attempt in range(2):
            try:
                raw = self.llm.complete(prompt + feedback, system=system, json_mode=True, thinking=self.thinking,
                                        sample=attempt)
                d = parse_json(raw)
                if isinstance(d, dict) and "plan" in d and d["plan"] is None:
                    c.error = f"not expressible as a plan: {d.get('reason', '')}".strip()
                    return c
                if isinstance(d, dict) and isinstance(d.get("plan"), dict):
                    d = d["plan"]
                plan = QueryPlan.model_validate(d)
                compiled = compile_plan(plan, self.model, default_limit=self.max_rows)
                c.plan, c.sql, c.notes, c.error = plan.model_dump(), compiled.sql, compiled.notes, None
                return c
            except (SemanticError, ValidationError, LLMError, ValueError) as e:
                msg = str(e).splitlines()[0][:400]
                c.attempts.append({"stage": "plan", "error": msg})
                c.error = f"plan rejected: {msg}"
                feedback = f"\n\nYour previous plan was rejected: {msg}\nFix it and reply with the JSON plan only."
        return c

    def _sql_candidate(self, q: str, assumptions: list[str], examples: list[dict[str, Any]],
                       previous_sql: str | None, alt: bool = False) -> Candidate:
        c = Candidate(name="sql_alt" if alt else "sql")
        system, prompt = sql_prompt(self.model, q, assumptions, examples, previous_sql, alt=alt)
        try:
            raw = self.llm.complete(prompt, system=system, thinking=self.thinking,
                                    temperature=0.4 if alt else 0.0, sample=1 if alt else 0)
            c.sql = extract_sql(raw)
        except LLMError as e:
            c.error = str(e)
        return c

    def _validate_and_run(self, c: Candidate, q: str, answer_id: str, role: str | None = None) -> None:
        if not c.sql:
            return
        sql = c.sql
        for attempt in range(self.max_repairs + 1):
            v = validate_sql(sql, self.model, max_rows=self.max_rows)
            if v.ok:
                res = self.executor.run(v.sql, tag={"answer_id": answer_id, "candidate": c.name, "attempt": attempt},
                                        max_rows=self.max_rows, role=role)
                c.attempts.append({"stage": "execute", "sql": v.sql, "query_id": res.query_id, "error": res.error})
                if res.ok:
                    c.sql, c.result, c.error = v.sql, res, None
                    return
                error = res.error or "execution failed"
            else:
                error = "; ".join(v.errors)
                c.attempts.append({"stage": "validate", "sql": sql, "error": error})
            c.error = error
            if c.name == "plan" or attempt == self.max_repairs:
                return
            system, prompt = repair_prompt(self.model, q, sql, error)
            try:
                sql = extract_sql(self.llm.complete(prompt, system=system, thinking=self.thinking, sample=attempt))
            except LLMError as e:
                c.error = str(e)
                return

    @staticmethod
    def _group(cands: list[Candidate]) -> list[list[Candidate]]:
        groups: list[list[Candidate]] = []
        for c in cands:
            for g in groups:
                a, b = c.result, g[0].result
                if results_match(a.rows, b.rows) or results_match(b.rows, a.rows):  # type: ignore[union-attr]
                    g.append(c)
                    break
            else:
                groups.append([c])
        return groups

    def _reconcile(self, ans: Answer, q: str, examples: list[dict[str, Any]], previous_sql: str | None) -> None:
        ok = [c for c in ans.candidates if c.ok]
        if len(ok) <= 1 or len(self._group(ok)) > 1:
            alt = self._sql_candidate(q, ans.assumptions, examples, previous_sql, alt=True)
            self._validate_and_run(alt, q, ans.answer_id, ans.role)
            ans.candidates.append(alt)
            ok = [c for c in ans.candidates if c.ok]
        if not ok:
            errs = [f"{c.name}: {c.error}" for c in ans.candidates if c.error]
            ans.status = "error"
            ans.message = ("I couldn't build a working query for this question, so I won't guess. "
                           "Try rephrasing it or naming the measure and grouping you want.")
            ans.alternatives = [{"note": e} for e in errs]
            return
        groups = sorted(self._group(ok), key=lambda g: (-len(g), min(_PREFERENCE.get(c.name, 9) for c in g)))
        best = groups[0]
        ans.chosen = min(best, key=lambda c: _PREFERENCE.get(c.name, 9))
        n_ok, n_best = len(ok), len(best)
        if n_best >= 2 and len(groups) == 1:
            ans.confidence = "high"
            ans.agreement = f"{n_best} independently generated queries returned the same result."
        elif n_best >= 2:
            ans.confidence = "medium"
            ans.agreement = f"{n_best} of {n_ok} independently generated queries agreed; the others differed."
        elif n_ok == 1:
            ans.confidence = "medium"
            ans.agreement = "Only one query could be built and run, so the result was not cross-checked."
        else:
            ans.confidence = "low"
            ans.agreement = (f"The {n_ok} independently generated queries disagree. Showing the one built from "
                             "the verified semantic model; the others are listed as alternatives.")
        for g in groups[1:]:
            c = min(g, key=lambda x: _PREFERENCE.get(x.name, 9))
            ans.alternatives.append({"candidate": c.name, "sql": c.sql,
                                     "summary": summarize_rows(c.result.columns, c.result.rows)})  # type: ignore[union-attr]

    def _narrate(self, ans: Answer, q: str, res: QueryResult) -> None:
        # only the executed SQL is trusted context: numbers that appear only in the question or in model-written
        # assumptions must be found in the rows, or a leading question could verify its own premise
        context = [res.sql]
        feedback = None
        for attempt in range(2):
            system, prompt = narrate_prompt(q, ans.explanation, ans.assumptions, res.columns, res.rows,
                                            res.truncated, feedback)
            try:
                text = self.llm.complete(prompt, system=system, sample=attempt).strip()
            except LLMError:
                break
            checks = check_numbers(text, res.columns, res.rows, context)
            bad = unverified(checks)
            if not bad and text:
                ans.message, ans.number_checks, ans.narration = text, checks, "gemma"
                return
            feedback = ", ".join(b.text for b in bad)
        ans.message = fallback_summary(res)
        ans.number_checks = check_numbers(ans.message, res.columns, res.rows, context)
        ans.narration = "fallback"

    def _masked_columns(self, res: QueryResult, sql: str) -> list[str]:
        """Result columns whose values are hidden by a masking policy.

        A masked column comes back as NULL or a '***' string. Besides columns named like a sensitive column,
        this catches aggregates over one (AVG(c_acctbal) is NULL when every balance is masked).
        """
        sensitive = {c.name.lower() for e in self.model.entities for c in e.columns if c.sensitive}
        try:
            used = {c.name.lower() for c in sqlglot.parse_one(sql, read="snowflake").find_all(exp.Column)}
        except sqlglot.errors.ParseError:
            used = set()
        touches_sensitive = bool(used & sensitive)
        out = []
        for i, col in enumerate(res.columns):
            vals = [r[i] for r in res.rows]
            if (col.lower() in sensitive or touches_sensitive) and vals and \
                    all(v is None or (isinstance(v, str) and "*" in v) for v in vals):
                out.append(col)
        return out

    def _log(self, ans: Answer) -> None:
        if not self.log_dir:
            return
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            with open(self.log_dir / "answers.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(ans.to_json(), default=str) + "\n")
        except OSError:
            pass


def _fmt_num(v: Any) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if f.is_integer() and abs(f) < 1e15:
        return f"{int(f):,}"
    return f"{f:,.2f}" if abs(f) >= 1 else f"{f:.4f}"


def fallback_summary(res: QueryResult, top: int = 3) -> str:
    """Deterministic answer text built only from result cells (used when narration can't be verified)."""
    cols, rows = res.columns, res.rows
    if len(rows) == 1 and len(cols) == 1:
        return f"The result is {_fmt_num(rows[0][0])} ({cols[0]})."
    def row_text(r: Sequence[Any]) -> str:
        return ", ".join(f"{c} = {_fmt_num(v) if not isinstance(v, str) else v}" for c, v in zip(cols, r))
    if len(rows) == 1:
        return f"Result: {row_text(rows[0])}."
    shown = "; ".join(row_text(r) for r in rows[:top])
    return f"The query returned {len(rows)} rows{' (truncated)' if res.truncated else ''}. First {min(top, len(rows))}: {shown}."
