"""Prompt templates for each Gemma task. Every task gets the full semantic model as context."""
from __future__ import annotations

import datetime as dt
import decimal
import json
from typing import Any, Sequence

from .semantic import SemanticModel

ROUTER_SYSTEM = (
    "You are the router of DataMind, an assistant that answers questions ONLY by running read-only SQL "
    "over one dataset in Snowflake. You classify questions; you never answer them. Reply with JSON only. "
    "[task:router]"
)
PLAN_SYSTEM = (
    "You translate business questions into a JSON query plan over a semantic model. The plan is compiled "
    "to SQL by code using verified joins and metric formulas. Reply with JSON only. [task:plan]"
)
SQL_SYSTEM = (
    "You are a senior analytics engineer who writes correct, read-only Snowflake SQL. You follow the schema "
    "and business rules exactly and never invent tables, columns or values. [task:sql]"
)
SQL_ALT_SYSTEM = (
    "You are a meticulous analytics engineer double-checking a colleague. Solve the question independently "
    "in Snowflake SQL, reasoning step by step with CTEs. [task:sql_alt]"
)
REPAIR_SYSTEM = "You fix broken Snowflake SQL so that it runs and answers the question. [task:repair]"
NARRATE_SYSTEM = (
    "You write short, precise answers for business users using only the numbers in a query result. "
    "You never invent numbers. [task:narrate]"
)


def _history_block(history: Sequence[dict[str, Any]]) -> str:
    if not history:
        return "(no previous questions)"
    lines = []
    for h in history[-4:]:
        lines.append(f"Q: {h.get('standalone_question') or h.get('question')}")
        if h.get("summary"):
            lines.append(f"   answered: {h['summary']}")
    return "\n".join(lines)


def router_prompt(model: SemanticModel, question: str, history: Sequence[dict[str, Any]]) -> tuple[str, str]:
    prompt = f"""{model.render()}

CONVERSATION SO FAR (oldest first):
{_history_block(history)}

NEW QUESTION: {json.dumps(question)}

Classify the new question:
- "answerable": the dataset can answer it, possibly using a sensible default that you state as an assumption.
- "ambiguous": two or more readings would give materially different answers and there is no sensible default
  (for example "best customers" with no measure). List the readings as interpretations.
- "not_in_data": it needs information this dataset does not contain (fields that do not exist, dates outside the
  coverage, external facts). Say what is missing and suggest the closest question that CAN be answered.
- "unsafe": it asks to change or delete data, to reveal credentials, system tables or other databases, or to do
  anything other than read this dataset.
- "chitchat": greetings or questions about what you can do.

Rules:
- Prefer "answerable" with an explicit assumption when a default is common sense (e.g. revenue = net revenue).
- Relative dates ("last year", "recently", "this year") are relative to the END of the data coverage, not today;
  state that as an assumption.
- Rewrite a follow-up into a standalone question using the conversation (e.g. "and in 1996?" -> the full question).

Reply with exactly this JSON:
{{"category": "answerable|ambiguous|not_in_data|unsafe|chitchat",
  "standalone_question": "...",
  "assumptions": ["..."],
  "interpretations": ["..."],
  "clarifying_question": "...",
  "missing": "...",
  "reason": "..."}}"""
    return ROUTER_SYSTEM, prompt


def _plan_example(model: SemanticModel) -> str:
    """A schematic example built from this model, so the prompt works for any dataset."""
    m = model.metrics[0] if model.metrics else None
    if m is None:
        return ""
    paths = model.upward_paths(m.grain)
    dim = date = None
    for alias in paths:
        ent = model.entity(alias)
        for c in ent.columns:
            if c.type == "category" and c.values and dim is None:
                dim = (ent.alias, c)
            if c.type == "date" and date is None:
                date = (ent.alias, c)
    if not dim:
        return ""
    plan: dict[str, Any] = {"metrics": [m.name], "dimensions": [{"field": f"{dim[0]}.{dim[1].name}", "grain": None}],
                            "filters": [], "having": [], "order_by": [{"field": m.name, "direction": "desc"}], "limit": 3}
    q = f"Top 3 {dim[1].description.lower()} by {m.name.replace('_', ' ')}"
    if date:
        plan["filters"].append({"field": f"{date[0]}.{date[1].name}", "op": "=", "value": 1995, "grain": "year"})
        q += f" in 1995 (by {date[1].description.lower()})"
    return f"Example\nQuestion: {q}\nPlan: {json.dumps(plan)}"


def plan_prompt(model: SemanticModel, question: str, assumptions: Sequence[str]) -> tuple[str, str]:
    prompt = f"""{model.render()}

Translate the question into a JSON query plan. Code compiles the plan into SQL with the verified joins and
metric formulas above, so you only decide WHAT to compute.

Plan format:
{{"metrics": ["<metric name from VERIFIED METRICS>"],
  "dimensions": [{{"field": "<alias.column>", "grain": null | "year" | "quarter" | "month" | "week" | "day"}}],
  "filters": [{{"field": "<alias.column>", "op": "=|!=|>|>=|<|<=|in|not in|between|like|is null|is not null",
               "value": <value, [values] for in, [low, high] for between>, "grain": null | "year" | ...}}],
  "having": [{{"field": "<metric name>", "op": ">", "value": 100}}],
  "order_by": [{{"field": "<metric name or alias.column>", "direction": "desc|asc"}}],
  "limit": null | <integer>}}

Rules:
- Only metric names from VERIFIED METRICS and fields written as alias.column from TABLES.
- Category values must be spelled exactly as listed. Text patterns use op "like" (e.g. "BRASS").
- Dates: "between" with ISO dates ["1995-01-01", "1995-12-31"], or grain "year" with a 4-digit value.
- "Top N" / "which ... the most": order_by the metric and set limit. A single total: no dimensions.
- Listing records without aggregation: dimensions only, no metrics.
- If the question needs something this format cannot express (ratios between groups, ranks within groups,
  comparison with an average, several steps, or a measure that is not a listed metric), reply
  {{"plan": null, "reason": "..."}}.

{_plan_example(model)}

Question: {question}
Assumptions already made: {json.dumps(list(assumptions))}
Reply with the JSON plan only."""
    return PLAN_SYSTEM, prompt


def _examples_block(examples: Sequence[dict[str, Any]]) -> str:
    if not examples:
        return ""
    parts = ["VERIFIED EXAMPLES (question -> correct SQL for this dataset):"]
    for ex in examples:
        parts.append(f"Question: {ex['question']}\n```sql\n{ex['sql'].strip()}\n```")
    return "\n".join(parts)


_SQL_RULES = """Rules:
- One read-only SELECT statement (CTEs allowed). Never modify data.
- Use fully qualified tables with the aliases above, e.g. FROM {db}.{schema}.LINEITEM AS lineitem, and
  qualify every column as alias.column.
- Join only with the listed join conditions. Start from the most detailed table you need and join along
  many-to-one links. If you need an order-level or customer-level measure together with line-level data,
  aggregate in a CTE first so nothing is double counted.
- Use the VERIFIED METRICS formulas for those concepts and follow the BUSINESS RULES.
- Category literals must match the listed values exactly; use ILIKE '%word%' for text patterns.
- Select the label columns that identify each row (e.g. names) and the computed values, each computed
  column with a short snake_case alias. Do not round unless asked.
- Rankings: ORDER BY the measure DESC with a tie-breaker column, then LIMIT N.
- Percentages: compute as a fraction 0-1 unless the question asks otherwise."""


def sql_prompt(model: SemanticModel, question: str, assumptions: Sequence[str],
               examples: Sequence[dict[str, Any]], previous_sql: str | None = None,
               alt: bool = False) -> tuple[str, str]:
    prev = f"\nPREVIOUS QUERY IN THIS CONVERSATION (for follow-ups):\n```sql\n{previous_sql}\n```\n" if previous_sql else ""
    approach = ("Work it out independently: first decide the grain of each measure, then build CTEs step by step, "
                "then the final SELECT.\n" if alt else "")
    prompt = f"""{model.render()}

{_SQL_RULES.format(db=model.database, schema=model.schema_name)}

{_examples_block(examples)}
{prev}
{approach}Question: {question}
Assumptions: {json.dumps(list(assumptions))}
Reply with only the SQL in a ```sql code block."""
    return (SQL_ALT_SYSTEM if alt else SQL_SYSTEM), prompt


def repair_prompt(model: SemanticModel, question: str, sql: str, error: str) -> tuple[str, str]:
    prompt = f"""{model.render()}

{_SQL_RULES.format(db=model.database, schema=model.schema_name)}

Question: {question}

This SQL failed:
```sql
{sql}
```
Error: {error}

Return the corrected SQL only, in a ```sql code block."""
    return REPAIR_SYSTEM, prompt


def _fmt(v: Any) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, decimal.Decimal):
        return format(v.normalize(), "f") if v == v.to_integral() else str(v)
    if isinstance(v, float):
        return f"{v:.6g}" if abs(v) < 1 else f"{v:.4f}".rstrip("0").rstrip(".")
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    return str(v)


def result_table(columns: Sequence[str], rows: Sequence[Sequence[Any]], limit: int = 25) -> str:
    head = "| " + " | ".join(columns) + " |\n|" + "---|" * len(columns)
    body = "\n".join("| " + " | ".join(_fmt(v) for v in r) + " |" for r in rows[:limit])
    more = f"\n(... {len(rows) - limit} more rows not shown)" if len(rows) > limit else ""
    return f"{head}\n{body}{more}"


def narrate_prompt(question: str, explanation: Sequence[str], assumptions: Sequence[str],
                   columns: Sequence[str], rows: Sequence[Sequence[Any]], truncated: bool,
                   feedback: str | None = None) -> tuple[str, str]:
    fb = f"\nYOUR PREVIOUS DRAFT USED NUMBERS THAT ARE NOT IN THE TABLE: {feedback}. Use only table values.\n" if feedback else ""
    prompt = f"""Question: {question}

How the result was computed:
{chr(10).join('- ' + s for s in explanation)}

Assumptions: {json.dumps(list(assumptions))}

Result ({len(rows)} row{'s' if len(rows) != 1 else ''}{', truncated' if truncated else ''}):
{result_table(columns, rows)}
{fb}
Write 1-3 plain sentences that directly answer the question.
- Copy numbers from the table. You may round (e.g. 15,472,321.71 or 15.47 million) and show fractions as percents.
- Only derive a new number if it is a simple difference, percent change, share or total of table values.
- With many rows, name the top few and say how many rows there are.
- Mention an assumption only if it changes the meaning. No headings, no SQL, no markdown tables."""
    return NARRATE_SYSTEM, prompt
