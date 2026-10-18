"""Result-set equivalence: do two query results contain the same answer?

Used in two places: reconciling independently generated SQL candidates (agreement = confidence)
and scoring the evaluation harness against independently computed gold answers. Comparison is
insensitive to column names, column order, extra helper columns in the prediction, row order
(unless asked) and small floating point / rounding differences.
"""
from __future__ import annotations

import datetime as dt
import decimal
import itertools
import math
from typing import Any, Sequence

REL_TOL = 1e-9    # engines differ only by floating point noise; anything larger is a different answer
ABS_TOL = 0.0051  # tolerates rounding to 2 decimals (cents) for amounts >= 1
MIN_SIG_DIGITS = 4  # a rounded value must keep this many significant digits to count as the same number


def norm(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float, decimal.Decimal)):
        f = float(v)
        return None if math.isnan(f) else f
    if isinstance(v, dt.datetime):
        return v.date().isoformat() if v.time() == dt.time(0) else v.isoformat()
    if isinstance(v, dt.date):
        return v.isoformat()
    if isinstance(v, str):
        s = v.strip()
        try:
            return float(s) if s and s.replace(".", "", 1).replace("-", "", 1).isdigit() else s
        except ValueError:
            return s
    return str(v)


def _decimals(x: float) -> int | None:
    r = repr(x)
    if "e" in r or "E" in r:
        return None
    return len(r.split(".")[1].rstrip("0")) if "." in r else 0


def _sig_digits(x: float) -> int:
    return len(repr(abs(x)).replace(".", "").lstrip("0").rstrip("0"))


def _is_rounding_of(rounded: float, precise: float) -> bool:
    """True if `rounded` is `precise` rounded to the decimals `rounded` shows, keeping enough digits."""
    d, dp = _decimals(rounded), _decimals(precise)
    if d is None or dp is None or d >= dp or _sig_digits(rounded) < MIN_SIG_DIGITS:
        return False
    return math.isclose(round(precise, d), rounded, rel_tol=1e-12, abs_tol=1e-15)


def values_equal(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, float) and isinstance(b, float):
        if a.is_integer() and b.is_integer():
            return a == b   # counts and keys: exact
        if math.isclose(a, b, rel_tol=REL_TOL, abs_tol=1e-12):
            return True
        # tolerate rounding to cents only for amounts, never for small fractions like rates
        if max(abs(a), abs(b)) >= 1 and abs(a - b) <= ABS_TOL:
            return True
        return _is_rounding_of(a, b) or _is_rounding_of(b, a)
    if isinstance(a, float) != isinstance(b, float):
        return False
    return str(a).casefold() == str(b).casefold()


def _sort_key(v: Any) -> tuple:
    if v is None:
        return (0, 0.0, "")
    if isinstance(v, float):
        return (1, v, "")   # exact value: rounding here would make near-equal rates tie and misalign
    return (2, 0.0, str(v).casefold())


def _column(rows: Sequence[Sequence[Any]], i: int) -> list[Any]:
    return [r[i] for r in rows]


def _multiset_equal(a: list[Any], b: list[Any]) -> bool:
    if len(a) != len(b):
        return False
    return all(values_equal(x, y) for x, y in zip(sorted(a, key=_sort_key), sorted(b, key=_sort_key)))


def results_match(pred_rows: Sequence[Sequence[Any]], gold_rows: Sequence[Sequence[Any]],
                  ordered: bool = False, allow_extra_columns: bool = True) -> bool:
    """True if every gold column has a matching prediction column and rows align."""
    P = [[norm(v) for v in r] for r in pred_rows]
    G = [[norm(v) for v in r] for r in gold_rows]
    if len(P) != len(G):
        return False
    if not G:
        return True
    gw, pw = len(G[0]), len(P[0])
    if pw < gw or (not allow_extra_columns and pw != gw):
        return False
    # candidate prediction columns for each gold column (same multiset of values)
    cands: list[list[int]] = []
    for gi in range(gw):
        gcol = _column(G, gi)
        cs = [pi for pi in range(pw) if _multiset_equal(_column(P, pi), gcol)]
        if not cs:
            return False
        cands.append(cs)
    # try column assignments (tiny search space in practice)
    for assign in itertools.islice(itertools.product(*cands), 5000):
        if len(set(assign)) != len(assign):
            continue
        proj = [[r[pi] for pi in assign] for r in P]
        if ordered:
            a, b = proj, G
        else:
            a = sorted(proj, key=lambda r: tuple(_sort_key(v) for v in r))
            b = sorted(G, key=lambda r: tuple(_sort_key(v) for v in r))
        if all(all(values_equal(x, y) for x, y in zip(ra, rb)) for ra, rb in zip(a, b)):
            return True
    return False


def summarize_rows(columns: list[str], rows: Sequence[Sequence[Any]], limit: int = 3) -> str:
    if not rows:
        return "(no rows)"
    head = "; ".join(", ".join(f"{c}={norm(v)}" for c, v in zip(columns, r)) for r in rows[:limit])
    more = f" ... (+{len(rows) - limit} rows)" if len(rows) > limit else ""
    return head + more
