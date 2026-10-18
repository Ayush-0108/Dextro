"""Structured query plans and their deterministic compilation to SQL.

Gemma produces a QueryPlan (which metrics, grouped by what, filtered how). This module turns it
into SQL using only joins and metric formulas from the semantic model, so the join logic and the
metric definitions are never invented by the model.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import sqlglot
from pydantic import BaseModel, ConfigDict, field_validator
from sqlglot import exp

from .semantic import Column, Entity, Grain, SemanticError, SemanticModel

Op = Literal["=", "!=", ">", ">=", "<", "<=", "in", "not in", "between", "like", "not like", "is null", "is not null"]


class DimensionRef(BaseModel):
    model_config = ConfigDict(extra="ignore")
    field: str
    grain: Grain | None = None


class FilterSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")
    field: str
    op: Op = "="
    value: Any = None
    grain: Grain | None = None

    @field_validator("op", mode="before")
    @classmethod
    def _op(cls, v: Any) -> Any:
        if isinstance(v, str):
            v = v.strip().lower()
            return {"==": "=", "<>": "!=", "ilike": "like", "contains": "like", "not_in": "not in",
                    "eq": "=", "ne": "!=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}.get(v, v)
        return v


class OrderSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")
    field: str
    direction: Literal["asc", "desc"] = "desc"

    @field_validator("direction", mode="before")
    @classmethod
    def _dir(cls, v: Any) -> Any:
        return v.lower() if isinstance(v, str) else v


class QueryPlan(BaseModel):
    model_config = ConfigDict(extra="ignore")
    metrics: list[str] = []
    dimensions: list[DimensionRef] = []
    filters: list[FilterSpec] = []
    having: list[FilterSpec] = []
    order_by: list[OrderSpec] = []
    limit: int | None = None

    @field_validator("dimensions", mode="before")
    @classmethod
    def _dims(cls, v: Any) -> Any:
        if isinstance(v, list):
            return [{"field": d} if isinstance(d, str) else d for d in v]
        return v


@dataclass
class CompiledPlan:
    sql: str
    expression: exp.Expression
    root: str
    joined: list[str]
    notes: list[str] = field(default_factory=list)


class PlanError(SemanticError):
    pass


_TRUNC = {"quarter": "QUARTER", "month": "MONTH", "week": "WEEK"}


def _col(alias: str, column: Column) -> exp.Column:
    return exp.column(column.name, table=alias)


def _field_expr(ent: Entity, col: Column, grain: str | None) -> exp.Expression:
    c = _col(ent.alias, col)
    if not grain or grain == "day":
        return c
    if col.type != "date":
        raise PlanError(f"time grain '{grain}' used on non-date column {ent.alias}.{col.name}")
    if grain == "year":
        return exp.Year(this=c)
    return exp.DateTrunc(unit=exp.Literal.string(_TRUNC[grain]), this=c)


def _literal(col: Column, value: Any, grain: str | None, model: SemanticModel, notes: list[str]) -> exp.Expression:
    if value is None:
        return exp.Null()
    if isinstance(value, bool):
        return exp.Boolean(this=value)
    if grain == "year":
        return exp.Literal.number(int(str(value)[:4]))
    if col.type == "date" and not grain:
        return exp.Cast(this=exp.Literal.string(str(value)[:10]), to=exp.DataType.build("DATE"))
    if col.type in ("number", "id") and not isinstance(value, str):
        return exp.Literal.number(value)
    if col.type in ("number", "id") and isinstance(value, str):
        try:
            float(value)
            return exp.Literal.number(value)
        except ValueError:
            pass
    if col.type == "category":
        value, note = model.normalize_value(col, str(value))
        if note:
            notes.append(note)
    return exp.Literal.string(str(value))


def _condition(f: FilterSpec, target: exp.Expression, col: Column | None, model: SemanticModel,
               notes: list[str]) -> exp.Expression:
    op = f.op

    def lit(v: Any) -> exp.Expression:
        if col is None:  # metric (HAVING): numeric literal
            return exp.Literal.number(v)
        return _literal(col, v, f.grain, model, notes)

    if op == "is null":
        return exp.Is(this=target, expression=exp.Null())
    if op == "is not null":
        return exp.Not(this=exp.Is(this=target, expression=exp.Null()))
    if op in ("in", "not in"):
        vals = f.value if isinstance(f.value, list) else [f.value]
        cond = exp.In(this=target, expressions=[lit(v) for v in vals])
        return exp.Not(this=cond) if op == "not in" else cond
    if op == "between":
        if not isinstance(f.value, list) or len(f.value) != 2:
            raise PlanError("'between' needs a [low, high] value")
        return exp.Between(this=target, low=lit(f.value[0]), high=lit(f.value[1]))
    if op in ("like", "not like"):
        v = str(f.value)
        if "%" not in v and "_" not in v:
            v = f"%{v}%"
        cond = exp.ILike(this=target, expression=exp.Literal.string(v))
        return exp.Not(this=cond) if op == "not like" else cond
    klass = {"=": exp.EQ, "!=": exp.NEQ, ">": exp.GT, ">=": exp.GTE, "<": exp.LT, "<=": exp.LTE}[op]
    return klass(this=target, expression=lit(f.value))


def compile_plan(plan: QueryPlan, model: SemanticModel, dialect: str = "snowflake",
                 default_limit: int = 1000) -> CompiledPlan:
    notes: list[str] = []
    if not plan.metrics and not plan.dimensions:
        raise PlanError("plan has neither metrics nor dimensions")

    metrics = [model.metric(m) for m in plan.metrics]
    for asked, m in zip(plan.metrics, metrics):
        if asked.lower() != m.name.lower():
            notes.append(f"used metric '{m.name}' for '{asked}' ({m.description})")

    dims = [(d, *model.resolve_field(d.field)) for d in plan.dimensions]
    filters = [(f, *model.resolve_field(f.field)) for f in plan.filters]

    required: set[str] = set()
    for m in metrics:
        required |= m.aliases | {m.grain.lower()}
    required |= {e.alias.lower() for _, e, _ in dims}
    required |= {e.alias.lower() for _, e, _ in filters}

    root = model.choose_root(required)
    for m in metrics:
        if m.grain.lower() != root and not m.fanout_safe:
            raise PlanError(
                f"metric '{m.name}' is defined per {m.grain} row, but the other requested fields need "
                f"{root}-level rows; combining them would double count. Use a separate query."
            )
    joins = model.join_tree(root, required)

    # SELECT list
    select: list[exp.Expression] = []
    group: list[exp.Expression] = []
    dim_alias: dict[str, str] = {}
    used_names: set[str] = set()
    for d, ent, col in dims:
        e = _field_expr(ent, col, d.grain)
        name = col.name if len(model.column_owners(col.name)) == 1 else f"{ent.alias}_{col.name}"
        if d.grain and d.grain != "day":
            name = f"{name}_{d.grain}"
        base, i = name, 2
        while name in used_names:
            name, i = f"{base}_{i}", i + 1
        used_names.add(name)
        dim_alias[d.field.lower()] = name
        dim_alias[f"{ent.alias}.{col.name}".lower()] = name
        select.append(exp.alias_(e, name))
        group.append(e)
    metric_exprs: dict[str, exp.Expression] = {}
    for m in metrics:
        e = sqlglot.parse_one(m.expr, read="snowflake")
        metric_exprs[m.name.lower()] = e
        select.append(exp.alias_(e.copy(), m.name))

    root_ent = model.entity(root)
    q = exp.select(*select).from_(exp.to_table(model.qualified(root_ent)).as_(root_ent.alias))
    for j in joins:
        one = model.entity(j.one)
        on = exp.and_(*[exp.EQ(this=exp.column(a, table=j.many), expression=exp.column(b, table=j.one))
                        for a, b in j.keys])
        q = q.join(exp.to_table(model.qualified(one)).as_(one.alias), on=on,
                   join_type="left" if j.kind == "left" else "inner")

    conds = [_condition(f, _field_expr(ent, col, f.grain), col, model, notes) for f, ent, col in filters]
    if conds:
        q = q.where(exp.and_(*conds))

    if metrics and group:
        q = q.group_by(*group)
    elif not metrics:
        q = q.distinct()

    having = []
    for h in plan.having:
        m = model.metric(h.field)
        if m.name.lower() not in metric_exprs:
            metric_exprs[m.name.lower()] = sqlglot.parse_one(m.expr, read="snowflake")
        having.append(_condition(h, metric_exprs[m.name.lower()].copy(), None, model, notes))
    if having:
        q = q.having(exp.and_(*having))

    order: list[exp.Expression] = []
    for o in plan.order_by:
        key = o.field.lower()
        try:
            mname = model.metric(o.field).name
        except SemanticError:
            mname = None
        if mname and mname.lower() in {m.name.lower() for m in metrics}:
            target: exp.Expression = exp.column(mname)
        elif mname:
            target = sqlglot.parse_one(model.metric(mname).expr, read="snowflake")
        elif key in dim_alias:
            target = exp.column(dim_alias[key])
        else:
            raise PlanError(f"cannot order by {o.field!r}: it is neither a requested metric nor dimension")
        order.append(exp.Ordered(this=target, desc=o.direction == "desc", nulls_first=False))
    if not order and plan.limit and metrics:
        order.append(exp.Ordered(this=exp.column(metrics[0].name), desc=True, nulls_first=False))
        notes.append(f"ranked by {metrics[0].name}, highest first")
    if not order:
        for d, _, _ in dims:
            if d.grain:
                order.append(exp.Ordered(this=exp.column(dim_alias[d.field.lower()]), desc=False))
    if order:
        q = q.order_by(*order)
    limit = min(plan.limit, default_limit) if plan.limit else default_limit
    q = q.limit(limit)

    return CompiledPlan(sql=q.sql(dialect=dialect, pretty=True), expression=q, root=root,
                        joined=[root] + [j.one for j in joins], notes=notes)
