"""Plain-language explanation generated from the executed SQL itself.

The explanation is derived deterministically from the parsed query, never written by the model,
so it always matches what actually ran: which tables were read, how they were linked, which
filters and groupings were applied, and how each number was calculated.
"""
from __future__ import annotations

import sqlglot
from sqlglot import exp

from .semantic import SemanticError, SemanticModel

_CMP = {exp.EQ: "is", exp.NEQ: "is not", exp.GT: "is greater than", exp.GTE: "is at least",
        exp.LT: "is less than", exp.LTE: "is at most"}
_CMP_DATE = {exp.GT: "is after", exp.GTE: "is on or after", exp.LT: "is before", exp.LTE: "is on or before",
             exp.EQ: "is", exp.NEQ: "is not"}


class _Ctx:
    def __init__(self, model: SemanticModel, tree: exp.Expression):
        self.model = model
        self.alias_table: dict[str, str] = {}
        self.alias_entity: dict[str, object] = {}
        for t in tree.find_all(exp.Table):
            if t.name:
                self.alias_table[t.alias_or_name.lower()] = t.name.lower()
        self._resolve_roles(tree)

    def _resolve_roles(self, tree: exp.Expression) -> None:
        """Work out which semantic entity each table alias plays (e.g. NATION as supplier nation).

        A table that appears in the model more than once (role-playing dimension) is resolved by
        following the join conditions back to an alias whose role is already known.
        """
        ambiguous: set[str] = set()
        for a, table in self.alias_table.items():
            ents = self.model.entities_for_table(table)
            named = [e for e in ents if e.alias.lower() == a]
            if named:
                self.alias_entity[a] = named[0]
            elif len(ents) == 1:
                self.alias_entity[a] = ents[0]
            elif ents:
                ambiguous.add(a)
        eqs = [e for e in tree.find_all(exp.EQ)
               if isinstance(e.this, exp.Column) and isinstance(e.expression, exp.Column)]
        for _ in range(4):
            if not ambiguous:
                break
            for e in eqs:
                for x, y in ((e.this, e.expression), (e.expression, e.this)):
                    xa, ya = x.table.lower(), y.table.lower()
                    if ya in ambiguous and xa in self.alias_entity:
                        known = self.alias_entity[xa]
                        for j in self.model.joins:
                            # known is the many side, unknown is the one side
                            if j.many.lower() == known.alias.lower() and (x.name.lower(), y.name.lower()) in \
                                    {(a.lower(), b.lower()) for a, b in j.keys} and \
                                    self.model.entity(j.one).table.lower() == self.alias_table[ya]:
                                self.alias_entity[ya] = self.model.entity(j.one)
                            # known is the one side, unknown is the many side
                            elif j.one.lower() == known.alias.lower() and (y.name.lower(), x.name.lower()) in \
                                    {(a.lower(), b.lower()) for a, b in j.keys} and \
                                    self.model.entity(j.many).table.lower() == self.alias_table[ya]:
                                self.alias_entity[ya] = self.model.entity(j.many)
                        if ya in self.alias_entity:
                            ambiguous.discard(ya)

    def entity_for(self, alias: str):
        return self.alias_entity.get(alias.lower())

    def column(self, col: exp.Column) -> tuple[str, str]:
        """(label, type) for a column reference."""
        name = col.name
        q = col.table.lower()
        ent = self.alias_entity.get(q) if q else None
        if ent is not None and not ent.column(name):
            ent = None
        if ent is None and q in self.alias_table:
            ents = self.model.entities_for_table(self.alias_table[q])
            ent = next((e for e in ents if e.column(name)), None)
        if ent is None:
            owners = self.model.column_owners(name)
            ent = owners[0] if owners else None
        c = ent.column(name) if ent else None
        if not c:
            return name, "text"
        desc = c.description.split(";")[0].split("(")[0].strip() or name
        desc = desc[:1].lower() + desc[1:]
        return f"{desc} ({name})", c.type


def _value(e: exp.Expression) -> str:
    if isinstance(e, exp.Cast):
        return _value(e.this)
    if isinstance(e, exp.Literal):
        return f"'{e.this}'" if e.is_string else e.this
    if isinstance(e, exp.Null):
        return "empty"
    return e.sql(dialect="snowflake")


def _target(e: exp.Expression, ctx: _Ctx) -> tuple[str, str] | None:
    if isinstance(e, exp.Column):
        return ctx.column(e)
    if isinstance(e, exp.Year) and isinstance(e.this, exp.Column):
        return f"the year of {ctx.column(e.this)[0]}", "number"
    if isinstance(e, exp.Anonymous) and str(e.name).upper() == "YEAR" and e.expressions and isinstance(e.expressions[0], exp.Column):
        return f"the year of {ctx.column(e.expressions[0])[0]}", "number"
    if isinstance(e, (exp.DateTrunc, exp.TimestampTrunc)) and isinstance(e.this, exp.Column):
        unit = e.args.get("unit")
        return f"the {_value(unit).strip(chr(39)).lower() if unit else 'period'} of {ctx.column(e.this)[0]}", "date"
    return None


def _condition(e: exp.Expression, ctx: _Ctx) -> str:
    if isinstance(e, exp.Paren):
        return _condition(e.this, ctx)
    if isinstance(e, exp.Not):
        inner = e.this
        if isinstance(inner, exp.Is):
            t = _target(inner.this, ctx)
            if t:
                return f"{t[0]} is not empty"
        return f"NOT ({_condition(inner, ctx)})"
    if isinstance(e, exp.Or):
        return " or ".join(f"({_condition(x, ctx)})" for x in e.flatten())
    if type(e) in _CMP:
        t = _target(e.this, ctx)
        if t and not e.expression.find(exp.Column):
            words = (_CMP_DATE if t[1] == "date" else _CMP)[type(e)]
            return f"{t[0]} {words} {_value(e.expression)}"
    if isinstance(e, exp.Between):
        t = _target(e.this, ctx)
        if t:
            return f"{t[0]} is between {_value(e.args['low'])} and {_value(e.args['high'])}"
    if isinstance(e, exp.In) and not e.args.get("query"):
        t = _target(e.this, ctx)
        if t:
            return f"{t[0]} is one of {', '.join(_value(x) for x in e.expressions)}"
    if isinstance(e, (exp.ILike, exp.Like)):
        t = _target(e.this, ctx)
        if t:
            pat = _value(e.expression).strip("'")
            if pat.startswith("%") and pat.endswith("%"):
                return f"{t[0]} contains '{pat.strip('%')}'"
            return f"{t[0]} matches '{pat}'"
    if isinstance(e, exp.Is):
        t = _target(e.this, ctx)
        if t:
            return f"{t[0]} is empty"
    return e.sql(dialect="snowflake")


def _conjuncts(e: exp.Expression) -> list[exp.Expression]:
    return list(e.flatten()) if isinstance(e, exp.And) else [e]


def _describe_select(sel: exp.Select, ctx: _Ctx, model: SemanticModel, top: bool,
                     ctes: set[str] = frozenset()) -> list[str]:
    out: list[str] = []

    def proj_label(e: exp.Expression) -> str:
        if isinstance(e, exp.Literal) and not e.is_string:
            idx = int(e.this) - 1
            if 0 <= idx < len(sel.expressions):
                p = sel.expressions[idx]
                t = _target(p.unalias(), ctx)
                return t[0] if t else (p.alias or p.unalias().sql(dialect="snowflake"))
        t = _target(e, ctx)
        return t[0] if t else e.sql(dialect="snowflake")

    frm = sel.args.get("from_") or sel.args.get("from")
    sources = []
    if frm is not None:
        sources.append(frm.this)
    joins = sel.args.get("joins") or []
    sources += [j.this for j in joins]
    names = []
    for s in sources:
        if isinstance(s, exp.Table) and s.name.lower() in ctes and not s.db:
            names.append(f"the intermediate result '{s.name}'")
        elif isinstance(s, exp.Table):
            role = ctx.entity_for(s.alias_or_name)
            ents = [role] if role is not None else model.entities_for_table(s.name)
            desc = ents[0].description if ents else ""
            shown = s.name.upper()
            if ents and ents[0].alias.lower() != s.name.lower() and len(model.entities_for_table(s.name)) > 1:
                shown += f" as {ents[0].alias}"
            names.append(shown + (f" ({desc[:1].lower() + desc[1:]})" if desc else ""))
        elif isinstance(s, exp.Subquery):
            names.append(f"the intermediate result '{s.alias_or_name}'")
    if names:
        out.append("Read " + "; ".join(names) + ".")
    for j in joins:
        on = j.args.get("on")
        if on is not None and isinstance(j.this, exp.Table):
            pairs = []
            for c in _conjuncts(on):
                if isinstance(c, exp.EQ) and isinstance(c.this, exp.Column) and isinstance(c.expression, exp.Column):
                    pairs.append(f"{c.this.table or ''}.{c.this.name} = {c.expression.table or ''}.{c.expression.name}".replace(" .", " "))
            kind = "left-joined" if (j.side or "").upper() == "LEFT" else "linked"
            out.append(f"{kind.capitalize()} {j.this.name.upper()} on {', '.join(pairs) or on.sql()}.")
    where = sel.args.get("where")
    if where is not None:
        conds = [_condition(c, ctx) for c in _conjuncts(where.this)]
        out.append("Kept only rows where " + "; and ".join(conds) + ".")
    group = sel.args.get("group")
    if group is not None:
        labels = [proj_label(g) for g in group.expressions]
        out.append("Grouped by " + ", ".join(labels) + ".")
    metrics = {m.name.lower(): m for m in model.metrics}
    for i, proj in enumerate(sel.expressions, 1):
        inner = proj.unalias()
        if inner.find(exp.AggFunc):
            name = proj.alias or f"column {i}"
            m = metrics.get(name.lower())
            formula = inner.sql(dialect="snowflake")
            if m:
                out.append(f"Calculated {name} = {formula} -- {m.description}.")
            else:
                out.append(f"Calculated {name} = {formula}.")
    if sel.args.get("distinct"):
        out.append("Removed duplicate rows.")
    having = sel.args.get("having")
    if having is not None:
        out.append("Kept only groups where " + "; and ".join(c.sql(dialect="snowflake") for c in _conjuncts(having.this)) + ".")
    order = sel.args.get("order")
    if order is not None:
        parts = []
        for o in order.expressions:
            label = proj_label(o.this)
            parts.append(f"{label} ({'highest first' if o.args.get('desc') else 'lowest first'})")
        out.append("Sorted by " + ", ".join(parts) + ".")
    lim = sel.args.get("limit")
    if lim is not None and lim.expression is not None:
        try:
            n = int(lim.expression.name)
            if n < 1000 or not top:
                out.append(f"Kept the first {n} rows.")
        except ValueError:
            pass
    sub = [s for s in (where.this.find_all(exp.Subquery) if where is not None else [])]
    if sub:
        out.append(f"Used {len(sub)} sub-quer{'y' if len(sub) == 1 else 'ies'} inside the filter.")
    return out


def explain_sql(sql: str, model: SemanticModel) -> list[str]:
    try:
        tree = sqlglot.parse_one(sql, read="snowflake")
    except sqlglot.errors.ParseError:
        return ["(could not parse the query for explanation)"]
    ctx = _Ctx(model, tree)
    steps: list[str] = []
    ctes: set[str] = set()
    with_ = tree.args.get("with_") or tree.args.get("with")
    if with_ is not None:
        ctes = {c.alias.lower() for c in with_.expressions}
        for i, cte in enumerate(with_.expressions, 1):
            body = cte.this
            if isinstance(body, exp.Select):
                inner = " ".join(_describe_select(body, ctx, model, top=False, ctes=ctes))
                steps.append(f"Step {i} -- built '{cte.alias}': {inner}")
    main = tree
    if isinstance(main, exp.Select):
        frm = main.args.get("from_") or main.args.get("from")
        if frm is not None and isinstance(frm.this, exp.Subquery) and frm.this.alias == "_q":
            main = frm.this.this
    if isinstance(main, exp.Select):
        body = _describe_select(main, ctx, model, top=True,
                                ctes={c.alias.lower() for c in with_.expressions} if with_ is not None else set())
        steps.extend(([f"Final step: {' '.join(body)}"] if with_ is not None else body))
    elif isinstance(main, exp.Union):
        steps.append("Combined the results of several queries (UNION).")
    return steps
