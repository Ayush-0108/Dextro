"""Schema discovery: draft a semantic model YAML for a new schema.

Reads INFORMATION_SCHEMA, profiles text columns (distinct counts, small value lists), guesses
column types and many-to-one joins from key naming, and writes a draft YAML marked for human
review. A reviewed YAML is all DataMind needs to answer questions over a new dataset.

    python -m datamind draft-model --schema MY_SCHEMA --name mydata --out config/datasets/mydata.yaml
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

import yaml

MAX_CATEGORY_VALUES = 30


def _type(data_type: str, name: str) -> str:
    t = data_type.upper()
    n = name.lower()
    if re.search(r"(^id$|_id$|key$)", n):
        return "id"
    if any(x in t for x in ("DATE", "TIME")):
        return "date"
    if any(x in t for x in ("NUMBER", "INT", "DECIMAL", "NUMERIC", "FLOAT", "DOUBLE", "REAL")):
        return "number"
    if "BOOL" in t:
        return "boolean"
    return "text"


def _stem(col: str) -> str:
    c = col.lower()
    c = re.sub(r"^[a-z]{1,3}_", "", c)       # TPC-H style prefixes: l_orderkey -> orderkey
    c = re.sub(r"_?(id|key)$", "", c)
    return c


def _singular(t: str) -> str:
    t = t.lower()
    return t[:-3] + "y" if t.endswith("ies") else t[:-1] if t.endswith("s") else t


def _columns(executor: Any, database: str, schema: str) -> list[tuple[str, str, str, str]]:
    if executor.engine == "duckdb":
        sql = (f"SELECT table_name, column_name, data_type, '' FROM information_schema.columns "
               f"WHERE table_catalog = '{database}' AND table_schema = '{schema}' ORDER BY table_name, ordinal_position")
        res = executor.con.execute(sql).fetchall()  # metadata query, not user SQL
        return [tuple(r) for r in res]
    r = executor.run(f"SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, COALESCE(COMMENT, '') "
                     f"FROM {database}.INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = '{schema.upper()}' "
                     f"ORDER BY TABLE_NAME, ORDINAL_POSITION", max_rows=5000)
    if not r.ok:
        raise RuntimeError(r.error)
    return [tuple(x) for x in r.rows]


def draft_model(executor: Any, database: str, schema: str, name: str, title: str | None = None) -> str:
    cols = _columns(executor, database, schema)
    tables: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for table, column, dtype, comment in cols:
        tables[table].append({"name": column.lower(), "type": _type(dtype, column),
                              "description": comment or f"TODO describe {column.lower()}"})
    if not tables:
        raise RuntimeError(f"no tables found in {database}.{schema}")

    # profile text columns: small distinct sets become categories with their value lists
    for table, cs in tables.items():
        text_cols = [c for c in cs if c["type"] == "text" and not re.search(r"comment|description|note", c["name"])]
        if not text_cols:
            continue
        exprs = ", ".join(f"COUNT(DISTINCT {c['name']}) AS d{i}" for i, c in enumerate(text_cols))
        r = executor.run(f"SELECT {exprs} FROM {database}.{schema}.{table}")
        if not r.ok or not r.rows:
            continue
        for c, d in zip(text_cols, r.rows[0]):
            if d is not None and 0 < int(d) <= MAX_CATEGORY_VALUES:
                v = executor.run(f"SELECT DISTINCT {c['name']} FROM {database}.{schema}.{table} "
                                 f"WHERE {c['name']} IS NOT NULL ORDER BY 1", max_rows=MAX_CATEGORY_VALUES)
                if v.ok:
                    c["type"] = "category"
                    c["values"] = [str(x[0]) for x in v.rows]

    # guess primary keys (first id column) and many-to-one joins by key-name stems
    pk = {t: next((c["name"] for c in cs if c["type"] == "id"), None) for t, cs in tables.items()}
    unique: dict[str, bool] = {}
    for t, k in pk.items():   # a join target must have a unique key, otherwise it is not many-to-one
        if k:
            r = executor.run(f"SELECT COUNT(*) = COUNT(DISTINCT {k}) AS u FROM {database}.{schema}.{t}")
            unique[t] = bool(r.ok and r.rows and r.rows[0][0])
    joins = []
    for t, cs in tables.items():
        for c in cs:
            if c["type"] != "id":
                continue
            st = _stem(c["name"])
            for u, upk in pk.items():
                if u == t or not upk or not unique.get(u):
                    continue
                if _stem(upk) == st or (_singular(u) == st and upk.lower() in ("id", f"{st}_id")):
                    joins.append({"many": t.lower(), "one": u.lower(), "keys": [[c["name"], upk]]})

    doc = {
        "name": name,
        "title": title or f"TODO title for {schema}",
        "description": "TODO: one paragraph describing the business and what one row of each table means.",
        "database": database, "schema": schema,
        "data_coverage": "TODO: date range and row counts",
        "notes": ["TODO: business rules, e.g. which date column 'a year' refers to"],
        "sample_questions": ["TODO"],
        "entities": [{"alias": t.lower(), "table": t, "description": f"TODO: one row per ...",
                      "primary_key": [pk[t]] if pk[t] else [], "columns": cs} for t, cs in tables.items()],
        "joins": joins,
        "metrics": [{"name": f"{t.lower()}_count", "expr": "COUNT(*)", "grain": t.lower(),
                     "description": f"Number of {t.lower()} rows", "format": "integer"} for t in tables],
    }
    header = ("# DRAFT generated by `python -m datamind draft-model`. REVIEW BEFORE USE:\n"
              "#  - fix descriptions and table aliases (role-playing tables need one entity per role)\n"
              "#  - check every join is truly many-to-one; add missing joins\n"
              "#  - replace the starter COUNT metrics with real business metrics (exact formulas)\n"
              "#  - mark sensitive columns with `sensitive: true`\n")
    # COUNT(*) metrics have no alias.column references, so grain is explicit
    return header + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=120)
