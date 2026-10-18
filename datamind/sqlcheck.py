"""Static validation of model-written SQL before it reaches Snowflake.

Defence in depth: the Snowflake role is already read-only, but we also reject anything that is
not a single SELECT over tables in the semantic model, catch unknown/misplaced columns with a
helpful message for the repair loop, pin every table to the configured database and schema, and
cap the number of rows returned.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp

from .semantic import SemanticModel

_FORBIDDEN = [getattr(exp, n) for n in (
    "Insert", "Update", "Delete", "Merge", "Create", "Drop", "Alter", "Command", "Copy", "Grant",
    "Revoke", "TruncateTable", "Set", "Use", "Transaction", "Commit", "Rollback", "LoadData", "Pragma",
    "Describe", "Show",
) if hasattr(exp, n)]

_FENCE = re.compile(r"```(?:sql|snowflake)?\s*(.*?)```", re.S | re.I)


@dataclass
class ValidationResult:
    ok: bool
    sql: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    tables: list[str] = field(default_factory=list)


def extract_sql(text: str) -> str:
    """Pull SQL out of a model reply (code fence or bare)."""
    m = _FENCE.search(text)
    sql = m.group(1) if m else text
    sql = sql.strip()
    # drop a leading 'sql' word some models emit and trailing semicolons
    sql = re.sub(r"^\s*sql\s*\n", "", sql, flags=re.I)
    return sql.rstrip().rstrip(";").strip()


def validate_sql(sql: str, model: SemanticModel, max_rows: int = 1000) -> ValidationResult:
    sql = extract_sql(sql)
    if not sql:
        return ValidationResult(False, sql, ["empty SQL"])
    try:
        stmts = [s for s in sqlglot.parse(sql, read="snowflake") if s is not None]
    except sqlglot.errors.ParseError as e:
        return ValidationResult(False, sql, [f"SQL does not parse: {str(e).splitlines()[0]}"])
    if len(stmts) != 1:
        return ValidationResult(False, sql, ["exactly one statement is allowed"])
    tree = stmts[0]
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(tree, exp.Query):
        return ValidationResult(False, sql, [f"only SELECT queries are allowed (got {tree.key.upper()})"])
    for klass in _FORBIDDEN:
        if tree.find(klass):
            return ValidationResult(False, sql, [f"statement contains a forbidden {klass.__name__.upper()} clause"])
    for fn in tree.find_all(exp.Anonymous):
        name = str(fn.name).upper()
        if name.startswith("SYSTEM$") or name in {"RESULT_SCAN", "GENERATOR"}:
            errors.append(f"function {name} is not allowed")

    cte_names = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    alias_to_table: dict[str, str] = {}
    used_tables: list[str] = []
    for t in tree.find_all(exp.Table):
        name = t.name.lower()
        if not name:
            continue
        if name in cte_names and not t.db:
            alias_to_table[t.alias_or_name.lower()] = name
            continue
        if name not in model.table_names:
            close = difflib.get_close_matches(name, sorted(model.table_names), n=1)
            hint = f" (did you mean {close[0].upper()}?)" if close else ""
            errors.append(f"unknown table {t.name}{hint}; allowed: {', '.join(sorted(n.upper() for n in model.table_names))}")
            continue
        if t.db and t.db.lower() != model.schema_name.lower():
            errors.append(f"table {t.sql()} is outside the allowed schema {model.database}.{model.schema_name}")
            continue
        if t.catalog and t.catalog.lower() != model.database.lower():
            errors.append(f"table {t.sql()} is outside the allowed database {model.database}")
            continue
        t.set("db", exp.to_identifier(model.schema_name))
        t.set("catalog", exp.to_identifier(model.database))
        alias_to_table[t.alias_or_name.lower()] = name
        alias_to_table.setdefault(name, name)
        used_tables.append(name.upper())

    # names that may legitimately appear as columns: model columns + any alias defined in the query
    defined = set(model.column_names)
    defined |= {a.alias.lower() for a in tree.find_all(exp.Alias) if a.alias}
    for ta in tree.find_all(exp.TableAlias):
        defined |= {c.name.lower() for c in ta.columns}
    for col in tree.find_all(exp.Column):
        cname = col.name.lower()
        if not cname or isinstance(col.this, exp.Star):
            continue
        if cname not in defined:
            close = difflib.get_close_matches(cname, sorted(model.column_names), n=1)
            hint = f" (did you mean {close[0]}?)" if close else ""
            errors.append(f"unknown column {col.sql()}{hint}")
            continue
        q = col.table.lower()
        if q and q in alias_to_table and alias_to_table[q] in model.table_names and cname in model.column_names:
            table = alias_to_table[q]
            owners = [e for e in model.entities if e.table.lower() == table]
            if not any(e.column(cname) for e in owners):
                real = sorted({e.table for e in model.column_owners(cname)})
                errors.append(f"column {cname} is not in table {table.upper()} (alias {q}); it is in {', '.join(real)}")

    if errors:
        return ValidationResult(False, sql, errors, warnings, used_tables)

    # cap rows
    if isinstance(tree, exp.Select):
        lim = tree.args.get("limit")
        if lim is None:
            tree = tree.limit(max_rows)
        else:
            try:
                n = int(lim.expression.name) if lim.expression else max_rows
                if n > max_rows:
                    tree = tree.limit(max_rows)
                    warnings.append(f"LIMIT reduced to {max_rows}")
            except (ValueError, AttributeError):
                tree = tree.limit(max_rows)
    else:
        tree = exp.select("*").from_(tree.subquery("_q")).limit(max_rows)

    return ValidationResult(True, tree.sql(dialect="snowflake", pretty=True), [], warnings, sorted(set(used_tables)))


_WRITE_INTENT = re.compile(
    r"^\s*(please\s+|can you\s+|could you\s+)?(delete|drop|truncate|update|insert|alter|grant|revoke|merge|wipe|erase)\b"
    r"|\b(delete|drop|truncate)\s+(all|the|every|table|rows|records|orders|customers|data)\b",
    re.I,
)


def is_write_request(question: str) -> bool:
    """Heuristic guard for questions that ask the agent to change data."""
    return bool(_WRITE_INTENT.search(question))
