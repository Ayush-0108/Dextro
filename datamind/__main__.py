"""Command line interface.

  python -m datamind check                       # verify Snowflake + Gemma connectivity
  python -m datamind ask "What was revenue in 1995?" [--role DATAMIND_RESTRICTED] [--json]
  python -m datamind eval [--split dev] [--file eval/tpch_dev.yaml] [--paraphrases] [--limit N] [--gold-engine duckdb]
  python -m datamind check-gold [--independent duckdb]   # run gold SQL; optionally cross-check on a 2nd engine
  python -m datamind draft-model --schema MY_SCHEMA --name mydata [--database DB] [--out config/datasets/mydata.yaml]
"""
from __future__ import annotations

import argparse
import json
import sys

from .config import ROOT, build, build_executor, build_model, load_dotenv


def _print_answer(a, as_json: bool) -> None:
    if as_json:
        print(json.dumps(a.to_json(), indent=2, default=str))
        return
    print(f"\n[{a.status}{' / confidence ' + a.confidence if a.confidence else ''}] {a.message}\n")
    if a.assumptions:
        print("Assumptions:", "; ".join(a.assumptions))
    if a.interpretations:
        print("Possible meanings:", " | ".join(a.interpretations))
    if a.chosen and a.result:
        print(f"Agreement: {a.agreement}")
        print(f"\nSQL ({a.chosen.name}, query id {a.result.query_id}, {a.result.elapsed_ms} ms, "
              f"{a.result.row_count} rows):\n{a.chosen.sql}\n")
        print("How it was computed:")
        for s in a.explanation:
            print("  -", s)
        print("\nNumbers in the answer:")
        for n in a.number_checks:
            print(f"  {n.text:>20}  {n.status:<10} {n.source}")
    for alt in a.alternatives:
        print("Alternative:", alt)
    print(f"\n({a.timings})")


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    ap = argparse.ArgumentParser(prog="datamind")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_ask = sub.add_parser("ask")
    p_ask.add_argument("question")
    p_ask.add_argument("--role")
    p_ask.add_argument("--engine")
    p_ask.add_argument("--json", action="store_true")
    p_eval = sub.add_parser("eval")
    p_eval.add_argument("--file", default=None)
    p_eval.add_argument("--split", default=None)
    p_eval.add_argument("--engine")
    p_eval.add_argument("--gold-engine", default=None, help="snowflake (default: same as engine) or duckdb")
    p_eval.add_argument("--paraphrases", action="store_true")
    p_eval.add_argument("--limit", type=int)
    p_eval.add_argument("--ids", help="comma-separated item ids")
    p_gold = sub.add_parser("check-gold")
    p_gold.add_argument("--file", default=None)
    p_gold.add_argument("--engine")
    p_gold.add_argument("--independent", help="second engine to cross-check, e.g. duckdb")
    sub.add_parser("check")
    p_draft = sub.add_parser("draft-model")
    p_draft.add_argument("--schema", required=True)
    p_draft.add_argument("--name", required=True)
    p_draft.add_argument("--database", default=None)
    p_draft.add_argument("--title", default=None)
    p_draft.add_argument("--engine")
    p_draft.add_argument("--out")
    args = ap.parse_args(argv)

    if args.cmd == "draft-model":
        from .discover import draft_model
        model = build_model()
        ex = build_executor(model, args.engine)
        text = draft_model(ex, args.database or model.database, args.schema, args.name, args.title)
        if args.out:
            (ROOT / args.out if not args.out.startswith("/") else __import__("pathlib").Path(args.out)).write_text(text)
            print(f"Draft written to {args.out}. Review it, then set DATAMIND_DATASET={args.out}")
        else:
            print(text)
        return 0

    if args.cmd == "check":
        model = build_model()
        ok = True
        try:
            ex = build_executor(model)
            who = "CURRENT_ROLE() AS role, CURRENT_WAREHOUSE() AS wh, " if ex.engine == "snowflake" else ""
            r = ex.run(f"SELECT {who}COUNT(*) AS n FROM {model.database}.{model.schema_name}.{model.entities[0].table}")
            print("Data engine:", ex.describe() if hasattr(ex, "describe") else ex.engine)
            print("  ->", r.error or f"OK {r.columns} {r.rows} (query id {r.query_id})")
            ok &= r.ok
        except Exception as e:
            print("Data engine: FAILED", e)
            ok = False
        try:
            from .llm import make_llm
            llm = make_llm(cache=False)
            reply = llm.complete("Reply with the single word: ready")
            print(f"Gemma ({llm.name}): {reply.strip()[:60]}")
        except Exception as e:
            print("Gemma: FAILED", e)
            ok = False
        return 0 if ok else 1

    if args.cmd == "ask":
        dm = build(engine=args.engine)
        _print_answer(dm.ask(args.question, role=args.role), args.json)
        return 0

    from .evaluation import check_gold, load_items, run_eval
    model = build_model()
    path = args.file or str(ROOT / "eval" / f"{model.name}_dev.yaml")
    items = load_items(path, getattr(args, "split", None))

    if args.cmd == "check-gold":
        primary = build_executor(model, args.engine)
        independent = build_executor(model, args.independent) if args.independent else None
        problems = check_gold(items, primary, independent)
        print("\n".join(problems) or f"All {sum(1 for i in items if i.get('gold_sql'))} gold queries ran"
              + (f" and matched on {args.independent}" if independent else "") + ".")
        return 1 if problems else 0

    if args.cmd == "eval":
        if args.ids:
            wanted = set(args.ids.split(","))
            items = [i for i in items if i["id"] in wanted]
        if args.limit:
            items = items[: args.limit]
        dm = build(engine=args.engine)
        gold_ex = build_executor(model, args.gold_engine) if args.gold_engine else dm.executor
        report = run_eval(dm, items, gold_ex, paraphrases=args.paraphrases)
        out = report.save(ROOT / "eval" / "reports")
        print("\n" + report.markdown().split("## Failures")[0])
        print(f"Report written to {out}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
