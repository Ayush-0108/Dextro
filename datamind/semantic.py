"""Semantic model: the hand-curated description of a dataset that the agent reasons over.

The semantic model is the single place where a dataset is described: tables (as aliases),
columns with plain-English descriptions and known values, the many-to-one join graph,
and verified metric definitions. Swapping datasets means writing a new YAML file, not code.
"""
from __future__ import annotations

import difflib
import re
from collections import deque
from functools import cached_property
from pathlib import Path
from typing import Any, Literal

import sqlglot
import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlglot import exp

ColType = Literal["id", "number", "category", "text", "date", "boolean"]
Grain = Literal["year", "quarter", "month", "week", "day"]


class SemanticError(ValueError):
    """Raised when a request cannot be mapped onto the semantic model."""


class Column(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    type: ColType = "text"
    description: str = ""
    synonyms: list[str] = []
    values: list[str] = []          # complete list of allowed values for small categories
    value_aliases: dict[str, str] = {}  # common alternative spellings -> canonical value
    value_pattern: str = ""         # description of value format when the list is too long
    sensitive: bool = False         # masked for restricted roles


class Entity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    alias: str
    table: str
    description: str = ""
    primary_key: list[str] = []
    columns: list[Column]

    def column(self, name: str) -> Column | None:
        n = name.lower()
        for c in self.columns:
            if c.name.lower() == n:
                return c
        return None


class Join(BaseModel):
    """A many-to-one relationship: each row of `many` matches at most one row of `one`."""
    model_config = ConfigDict(extra="forbid")
    many: str
    one: str
    keys: list[tuple[str, str]]     # (column on many side, column on one side)
    kind: Literal["inner", "left"] = "inner"


class Metric(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    expr: str                       # aggregate SQL using alias.column references
    grain: str                      # alias whose rows the aggregate is defined over
    description: str = ""
    synonyms: list[str] = []
    fanout_safe: bool = False       # true for COUNT(DISTINCT ...), MIN, MAX
    format: Literal["number", "integer", "currency", "percent"] = "number"

    @cached_property
    def aliases(self) -> set[str]:
        tree = sqlglot.parse_one(self.expr, read="snowflake")
        return {c.table.lower() for c in tree.find_all(exp.Column) if c.table}


class SemanticModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    name: str
    title: str
    description: str = ""
    database: str
    schema_name: str = Field(alias="schema")
    data_coverage: str = ""
    notes: list[str] = []
    sample_questions: list[str] = []
    entities: list[Entity]
    joins: list[Join]
    metrics: list[Metric] = []

    # ------------------------------------------------------------------ loading
    @classmethod
    def load(cls, path: str | Path, database: str | None = None, schema: str | None = None) -> "SemanticModel":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        if database:
            data["database"] = database
        if schema:
            data["schema"] = schema
        return cls.model_validate(data)

    @model_validator(mode="after")
    def _check(self) -> "SemanticModel":
        aliases = [e.alias.lower() for e in self.entities]
        if len(set(aliases)) != len(aliases):
            raise ValueError("entity aliases must be unique")
        for j in self.joins:
            for a in (j.many, j.one):
                if a.lower() not in aliases:
                    raise ValueError(f"join references unknown alias {a!r}")
            for mc, oc in j.keys:
                if not self.entity(j.many).column(mc) or not self.entity(j.one).column(oc):
                    raise ValueError(f"join {j.many}->{j.one} references unknown column")
        for m in self.metrics:
            if m.grain.lower() not in aliases:
                raise ValueError(f"metric {m.name} has unknown grain {m.grain!r}")
            for a in m.aliases:
                if a not in aliases:
                    raise ValueError(f"metric {m.name} references unknown alias {a!r}")
        return self

    # ------------------------------------------------------------------ lookups
    def entity(self, alias: str) -> Entity:
        a = alias.lower()
        for e in self.entities:
            if e.alias.lower() == a:
                return e
        raise SemanticError(f"unknown table alias {alias!r}")

    def entities_for_table(self, table: str) -> list[Entity]:
        t = table.lower()
        return [e for e in self.entities if e.table.lower() == t]

    def qualified(self, entity: Entity) -> str:
        return f"{self.database}.{self.schema_name}.{entity.table}"

    @cached_property
    def table_names(self) -> set[str]:
        return {e.table.lower() for e in self.entities}

    @cached_property
    def column_names(self) -> set[str]:
        return {c.name.lower() for e in self.entities for c in e.columns}

    def column_owners(self, name: str) -> list[Entity]:
        return [e for e in self.entities if e.column(name)]

    def metric(self, name: str) -> Metric:
        n = _norm(name)
        for m in self.metrics:
            if _norm(m.name) == n:
                return m
        for m in self.metrics:
            if n in {_norm(s) for s in m.synonyms}:
                return m
        close = difflib.get_close_matches(n, [_norm(m.name) for m in self.metrics], n=1, cutoff=0.85)
        if close:
            return next(m for m in self.metrics if _norm(m.name) == close[0])
        raise SemanticError(f"unknown metric {name!r}; known metrics: {', '.join(m.name for m in self.metrics)}")

    def resolve_field(self, field: str) -> tuple[Entity, Column]:
        """Resolve 'alias.column' (or an unambiguous bare column name)."""
        field = field.strip().strip('"')
        if "." in field:
            alias, col = field.rsplit(".", 1)
            ent = self.entity(alias)
            c = ent.column(col)
            if not c:
                raise SemanticError(f"{alias} has no column {col!r}")
            return ent, c
        owners = self.column_owners(field)
        if len(owners) == 1:
            return owners[0], owners[0].column(field)  # type: ignore[return-value]
        if not owners:
            raise SemanticError(f"unknown column {field!r}")
        raise SemanticError(
            f"column {field!r} is ambiguous; qualify it as one of: "
            + ", ".join(f"{e.alias}.{field}" for e in owners)
        )

    # ------------------------------------------------------------------ join graph
    def parents(self, alias: str) -> list[Join]:
        a = alias.lower()
        return [j for j in self.joins if j.many.lower() == a]

    def upward_paths(self, root: str) -> dict[str, list[Join]]:
        """Shortest many-to-one join path from `root` to every alias reachable from it."""
        root = root.lower()
        paths: dict[str, list[Join]] = {root: []}
        q = deque([root])
        while q:
            cur = q.popleft()
            for j in self.parents(cur):
                nxt = j.one.lower()
                if nxt not in paths:
                    paths[nxt] = paths[cur] + [j]
                    q.append(nxt)
        return paths

    def choose_root(self, required: set[str]) -> str:
        """Pick the coarsest table from which every required table is reachable via many-to-one joins.

        Joining only along many-to-one edges from the root guarantees that no row of the root is
        duplicated, so aggregates defined at the root grain are never double counted.
        """
        req = {r.lower() for r in required}
        if not req:
            raise SemanticError("the plan references no tables")
        candidates = [e.alias.lower() for e in self.entities if req <= set(self.upward_paths(e.alias))]
        if not candidates:
            raise SemanticError(
                "these tables cannot be combined without a one-to-many join: " + ", ".join(sorted(req))
            )
        # coarsest = a candidate reachable from every other candidate
        for c in candidates:
            if all(c in self.upward_paths(o) for o in candidates):
                return c
        # several incomparable candidates: prefer one that is itself required, then the smallest path set
        required_cands = [c for c in candidates if c in req]
        if required_cands:
            return required_cands[0]
        return min(candidates, key=lambda c: len(self.upward_paths(c)))

    def join_tree(self, root: str, required: set[str]) -> list[Join]:
        paths = self.upward_paths(root)
        ordered: list[Join] = []
        seen: set[str] = {root.lower()}
        for alias in sorted(required, key=lambda a: len(paths.get(a.lower(), []))):
            for j in paths[alias.lower()]:
                if j.one.lower() not in seen:
                    seen.add(j.one.lower())
                    ordered.append(j)
        return ordered

    # ------------------------------------------------------------------ values
    def normalize_value(self, column: Column, value: Any) -> tuple[Any, str | None]:
        """Map a user-supplied value onto a known category value. Returns (value, note)."""
        if not column.values or not isinstance(value, str):
            return value, None
        if value in column.values:
            return value, None
        lower = {v.lower(): v for v in column.values}
        if value.lower() in lower:
            return lower[value.lower()], None
        aliases = {k.lower(): v for k, v in column.value_aliases.items()}
        if value.lower().strip() in aliases:
            canon = aliases[value.lower().strip()]
            return canon, f"interpreted '{value}' as '{canon}'"
        # conservative typo correction only: a wrong guess here would silently change the answer
        close = difflib.get_close_matches(value.upper(), [v.upper() for v in column.values], n=1, cutoff=0.82)
        if close:
            canon = next(v for v in column.values if v.upper() == close[0])
            return canon, f"interpreted '{value}' as '{canon}' ({column.description or column.name})"
        raise SemanticError(
            f"'{value}' is not a known value of {column.name}; known values: {', '.join(column.values)}"
        )

    # ------------------------------------------------------------------ prompt rendering
    def render(self) -> str:
        lines = [f"DATASET: {self.title}", self.description.strip()]
        if self.data_coverage:
            lines.append(f"Coverage: {self.data_coverage}")
        lines.append("")
        lines.append("TABLES (always write FROM <qualified table> AS <alias> and qualify columns as alias.column):")
        for e in self.entities:
            lines.append(f"- {e.alias} = {self.qualified(e)} -- {e.description}")
            for c in e.columns:
                extra = ""
                if c.values:
                    extra = " values: " + ", ".join(c.values)
                    if c.value_aliases:
                        extra += " (" + ", ".join(f"{k} = {v}" for k, v in c.value_aliases.items()) + ")"
                elif c.value_pattern:
                    extra = " format: " + c.value_pattern
                syn = f" (aka {', '.join(c.synonyms)})" if c.synonyms else ""
                lines.append(f"    {c.name} [{c.type}] {c.description}{syn}{extra}")
        lines.append("")
        lines.append("JOINS (many-to-one; use exactly these conditions):")
        for j in self.joins:
            cond = " AND ".join(f"{j.many}.{a} = {j.one}.{b}" for a, b in j.keys)
            lines.append(f"- {j.many} -> {j.one}: {cond}")
        if self.metrics:
            lines.append("")
            lines.append("VERIFIED METRICS (use these exact formulas):")
            for m in self.metrics:
                syn = f" (aka {', '.join(m.synonyms)})" if m.synonyms else ""
                lines.append(f"- {m.name} = {m.expr} -- {m.description}{syn} [per {m.grain}]")
        if self.notes:
            lines.append("")
            lines.append("BUSINESS RULES:")
            lines.extend(f"- {n}" for n in self.notes)
        return "\n".join(lines)

    def label(self, alias: str, column: str) -> str:
        try:
            c = self.entity(alias).column(column)
        except SemanticError:
            c = None
        return (c.description.split(";")[0].split(".")[0] if c and c.description else column)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def load_model(path: str | Path, database: str | None = None, schema: str | None = None) -> SemanticModel:
    return SemanticModel.load(path, database=database, schema=schema)
