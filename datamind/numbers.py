"""Number grounding: every number in a written answer must be traceable to the result rows.

The narrator (Gemma) writes a short plain-language answer from the query result. This module
extracts every number and date from that text and checks it against the rows. A number is:
  verified   - matches a result cell (we keep the row/column so the UI can highlight it)
  derived    - equals a simple difference / ratio / percent change / share / total of result cells
  context    - comes from the question, the executed SQL, or the shape of the result (row count)
  unverified - none of the above: the pipeline regenerates or falls back to a templated answer
"""
from __future__ import annotations

import datetime as dt
import decimal
import itertools
import re
from dataclasses import dataclass
from typing import Any, Literal, Sequence

Status = Literal["verified", "derived", "context", "unverified"]

_SCALE = {
    "k": 1e3, "thousand": 1e3, "m": 1e6, "mn": 1e6, "million": 1e6, "b": 1e9, "bn": 1e9,
    "billion": 1e9, "lakh": 1e5, "lakhs": 1e5, "crore": 1e7, "crores": 1e7, "cr": 1e7,
}
_DATE = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
_NUM = re.compile(
    r"(?<![\w.#/-])(?P<sign>[-−])?(?P<cur>[$₹€£])?\s?"
    r"(?P<num>\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?:\s?(?P<unit>%|percent(?!\w)|per\s?cent(?!\w)|thousand(?!\w)|million(?!\w)|billion(?!\w)|"
    r"lakhs?(?!\w)|crores?(?!\w)|mn(?!\w)|bn(?!\w)|cr(?!\w)|[kKMB](?![\w]))|(?![\w]))"
)


@dataclass
class NumberCheck:
    text: str
    value: float
    status: Status
    source: str = ""
    cell: tuple[int, str] | None = None
    start: int = 0
    end: int = 0


def _f(v: Any) -> float | None:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float, decimal.Decimal)):
        return float(v)
    return None


def parse_numbers(text: str) -> list[tuple[str, float, float, bool, int, int]]:
    """Return (raw, value, tolerance, is_percent, start, end) for each number in text."""
    out = []
    masked = _DATE.sub(lambda m: " " * len(m.group(0)), text)
    for m in _NUM.finditer(masked):
        raw_num = m.group("num")
        unit = (m.group("unit") or "").strip().lower().replace(" ", "")
        digits = raw_num.replace(",", "")
        value = float(digits)
        decimals = len(digits.split(".")[1]) if "." in digits else 0
        scale = 1.0
        is_pct = unit in ("%", "percent", "percent")
        if unit and not is_pct:
            scale = _SCALE.get(unit, 1.0)
        if m.group("sign"):
            value = -value
        tol = 0.5 * (10 ** -decimals) * scale
        out.append((m.group(0).strip(), value * scale, tol, is_pct, m.start(), m.end()))
    return out


def _context_numbers(texts: Sequence[str]) -> list[float]:
    vals: list[float] = []
    for t in texts:
        for d in _DATE.finditer(t or ""):
            vals.extend(float(x) for x in d.groups())
        for _, v, _, _, _, _ in parse_numbers(t or ""):
            vals.append(v)
    return vals


def check_numbers(text: str, columns: Sequence[str], rows: Sequence[Sequence[Any]],
                  context: Sequence[str] = ()) -> list[NumberCheck]:
    cells: list[tuple[float, int, str]] = []
    date_cells: list[tuple[dt.date, int, str]] = []
    for ri, r in enumerate(rows):
        for c, v in zip(columns, r):
            f = _f(v)
            if f is not None:
                cells.append((f, ri, c))
            elif isinstance(v, (dt.date, dt.datetime)):
                date_cells.append((v if isinstance(v, dt.date) else v.date(), ri, c))
    ctx_vals = _context_numbers(context) + [float(len(rows)), float(len(columns))]
    if len(rows) <= 100:
        ctx_vals += [float(i) for i in range(1, len(rows) + 1)]

    derived: list[tuple[float, str]] = []
    nums = [x for x in cells if x[0] != 0]
    by_col: dict[str, list[float]] = {}
    for f, _, c in cells:
        by_col.setdefault(c, []).append(f)
    for c, vs in by_col.items():
        derived.append((sum(vs), f"total of {c}"))
        derived.append((sum(vs) / len(vs), f"average of {c}"))
    if len(nums) <= 60:
        for (a, ra, ca), (b, rb, cb) in itertools.permutations(nums, 2):
            derived += [
                (a - b, f"difference of row {ra + 1} {ca} and row {rb + 1} {cb}"),
                (a / b, f"ratio of row {ra + 1} {ca} to row {rb + 1} {cb}"),
                ((a - b) / abs(b) * 100, f"percent change from row {rb + 1} {cb} to row {ra + 1} {ca}"),
                (a / b * 100, f"row {ra + 1} {ca} as a percent of row {rb + 1} {cb}"),
            ]
        for c, vs in by_col.items():
            tot = sum(vs)
            if tot:
                for ri, v in enumerate(vs):
                    derived.append((v / tot * 100, f"share of row {ri + 1} in total {c}"))

    checks: list[NumberCheck] = []
    # ISO dates in the text
    for m in _DATE.finditer(text):
        try:
            d = dt.date(*map(int, m.groups()))
        except ValueError:
            continue
        hit = next(((ri, c) for dd, ri, c in date_cells if dd == d), None)
        if hit:
            checks.append(NumberCheck(m.group(0), float(d.year), "verified", f"row {hit[0] + 1}, {hit[1]}", hit, m.start(), m.end()))
        elif any(m.group(0) in (t or "") for t in context):
            checks.append(NumberCheck(m.group(0), float(d.year), "context", "from the question or query", None, m.start(), m.end()))
        else:
            checks.append(NumberCheck(m.group(0), float(d.year), "unverified", "", None, m.start(), m.end()))

    for raw, val, tol, is_pct, s, e in parse_numbers(text):
        def close(x: float) -> bool:
            return abs(x - val) <= max(tol, abs(val) * 1e-6)

        targets = [val]
        status: Status | None = None
        source, cell = "", None
        for f, ri, c in cells:
            if close(f) or (is_pct and close(f * 100)):
                status, source, cell = "verified", f"row {ri + 1}, {c}", (ri, c)
                break
        if status is None:
            for dd, ri, c in date_cells:
                if val in (dd.year, dd.month, dd.day) and not is_pct and "." not in raw:
                    status, source, cell = "verified", f"row {ri + 1}, {c}", (ri, c)
                    break
        if status is None and any(close(x) for x in ctx_vals):
            status, source = "context", "from the question, query or result size"
        if status is None:
            for f, why in derived:
                if close(f) or (is_pct and close(f * 100)):
                    status, source = "derived", why
                    break
        checks.append(NumberCheck(raw, targets[0], status or "unverified", source, cell, s, e))
    checks.sort(key=lambda c: c.start)
    return checks


def unverified(checks: Sequence[NumberCheck]) -> list[NumberCheck]:
    return [c for c in checks if c.status == "unverified"]
