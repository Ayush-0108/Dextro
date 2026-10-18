"""Deterministic answer checks: does the executed query actually cover what the question asked?

Two independently generated queries can agree and still both be wrong in the same way, most often by dropping a
condition the user stated ("in 1995", "customers in ASIA", "more than 38 orders") or by returning the wrong shape
("top 5" returning 25 rows). These checks cost no model calls. They are used to
  - prefer, among disagreeing candidates, the one that covers the question,
  - withhold "high confidence" from an answer that fails a check, and
  - give the SQL writer precise feedback for one extra attempt when every candidate fails.
They are deliberately conservative: a check fires only on explicit years, numbers, known category values and
"top N" / "how many" phrasings, so a correct query is not flagged (tested against every gold query).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .executors import QueryResult
from .numbers import parse_numbers
from .semantic import SemanticModel

_YEAR = re.compile(r"(?<![\d,.#])(19\d{2}|20\d{2})(?![\d,])")
_SHORT_YEAR = re.compile(r"['\u2019](\d{2})(?!\d)")
_TOP_N = re.compile(r"\b(?:top|first|best|largest|biggest|highest|lowest|worst|smallest|bottom)\s+(\d{1,3})\b"
                    r"|\bwhich\s+(\d{1,3})\b", re.I)
_PER_GROUP = re.compile(r"\b(each|per|every)\b", re.I)
_SINGLE = re.compile(r"^\s*(?:how many|how much|what (?:is|was|were) (?:the )?(?:total|average|overall|sum|count|number)\b)",
                     re.I)
_GROUPING = re.compile(r"\b(each|per|by|every|breakdown|split|list|which|across|versus|vs|compare|and in)\b", re.I)
_PERIOD_BREAKDOWN = re.compile(r"\b(?:each|every|per|by)\s+(quarter|month|week|year)\b"
                               r"|\b(quarterly|monthly|weekly|yearly|annually)\b", re.I)
_TIME_UNIT = re.compile(r"^\s*(?:day|week|month|quarter|year|hour|minute)s?\b", re.I)
# category values that are also everyday words in questions ("ship mode", "high priority")
_COMMON_WORDS = {"none", "ship", "high", "low", "medium", "open", "other", "pop"}
_SQL_NUMBER = re.compile(r"\d+(?:\.\d+)?")


@dataclass
class Constraints:
    years: set[int] = field(default_factory=set)
    values: dict[str, str] = field(default_factory=dict)      # text in the question -> canonical value
    numbers: list[tuple[str, float, bool]] = field(default_factory=list)   # (text, value, is_percent)
    top_n: int | None = None
    single_value: bool = False
    period_breakdown: str | None = None   # "quarter", "month", ...: the answer needs more than one row


def _value_terms(model: SemanticModel) -> dict[str, str]:
    terms: dict[str, str] = {}
    for e in model.entities:
        for c in e.columns:
            if c.type != "category":
                continue
            for v in c.values:
                if len(v) >= 3 and v.lower() not in _COMMON_WORDS and not v.isdigit():
                    terms.setdefault(v.lower(), v)
            for alias, canon in c.value_aliases.items():
                if len(alias) >= 3 and alias.lower() not in _COMMON_WORDS:
                    terms.setdefault(alias.lower(), canon)
    return terms


def question_constraints(question: str, model: SemanticModel) -> Constraints:
    q = question.strip()
    cons = Constraints()
    cons.years = {int(y) for y in _YEAR.findall(q)}
    # '96 / ’96 = 1996 (two-digit years after an apostrophe)
    short = {(1900 if int(y) >= 50 else 2000) + int(y) for y in _SHORT_YEAR.findall(q)}
    cons.years |= short

    m = _TOP_N.search(q)
    if m and not _PER_GROUP.search(q):
        cons.top_n = int(m.group(1) or m.group(2))
    cons.single_value = bool(_SINGLE.search(q)) and not _GROUPING.search(q)
    pb = _PERIOD_BREAKDOWN.search(q)
    if pb:
        word = (pb.group(1) or pb.group(2)).lower()
        cons.period_breakdown = {"quarterly": "quarter", "monthly": "month", "weekly": "week", "yearly": "year",
                                 "annually": "year"}.get(word, word)

    # known category values, longest first so "REG AIR" wins over "AIR"
    masked = q
    for term in sorted(_value_terms(model), key=len, reverse=True):
        # whole words; "urgent-priority" / "ASIA-based" count, codes like "1-URGENT" or "Brand#23" don't
        pat = re.compile(rf"(?<![\w#])(?<!\d-){re.escape(term)}(?![\w#])(?!-\d)", re.I)
        hit = pat.search(masked)
        if hit:
            cons.values[hit.group(0)] = _value_terms(model)[term]
            masked = masked[:hit.start()] + " " * len(hit.group(0)) + masked[hit.end():]

    # explicit thresholds and amounts ("more than 38 orders", "$600k"), not years, top-N or durations
    top_spans = [mm.span() for mm in _TOP_N.finditer(q)]
    for raw, value, _tol, is_pct, s, e in parse_numbers(q):
        if any(a <= s < b for a, b in top_spans) or (s > 0 and q[s - 1] in "'\u2019"):
            continue
        if not is_pct and float(value).is_integer() and int(value) in cons.years:
            continue
        if _TIME_UNIT.match(q[e:]) or (not is_pct and value in (1, 2, 3, 4) and re.search(r"\bq\s*$", q[:s], re.I)):
            continue
        cons.numbers.append((raw, float(value), is_pct))
    return cons


def _sql_numbers(sql: str) -> set[float]:
    return {float(x) for x in _SQL_NUMBER.findall(sql)}


def _number_used(value: float, is_pct: bool, sql_nums: set[float]) -> bool:
    candidates = {value, value / 100} if is_pct else {value}
    if not is_pct and 0 < value < 1:
        candidates.add(value * 100)
    return any(abs(c - n) <= 1e-9 * max(1.0, abs(c)) for c in candidates for n in sql_nums)


def check_candidate(cons: Constraints, sql: str, result: QueryResult | None) -> list[str]:
    """Plain-language problems with one executed candidate; empty when it covers the question."""
    issues: list[str] = []
    low_sql = sql.lower()
    sql_nums = _sql_numbers(sql)
    for y in sorted(cons.years):
        if str(y) not in sql:
            issues.append(f"the question mentions {y} but the query doesn't use it")
    for text, canon in cons.values.items():
        if canon.lower() not in low_sql and text.lower() not in low_sql:
            issues.append(f"the question mentions '{text}' but the query doesn't filter on {canon}")
    for raw, value, is_pct in cons.numbers:
        if not _number_used(value, is_pct, sql_nums):
            issues.append(f"the question mentions {raw} but the query doesn't use it")
    if result is not None and result.ok:
        n = result.row_count
        if cons.top_n is not None and n > cons.top_n:
            issues.append(f"the question asks for the top {cons.top_n} but the query returned {n} rows")
        if cons.single_value and n > 1:
            issues.append(f"the question asks for a single number but the query returned {n} rows")
        if cons.period_breakdown and n == 1:
            issues.append(f"the question asks for a breakdown by {cons.period_breakdown} but the query returned 1 row")
    return issues
