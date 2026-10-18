"""Ask the demo questions once, in demo order, so the live demo doesn't wait minutes per answer on a laptop.

    python scripts/warm_demo.py

Gemma's replies are cached on disk (.cache/llm, keyed by the exact prompt). Asking the same questions in the same
order later reuses those replies; every SQL query still runs live in Snowflake at question time, so results, query
ids and "the answer changes when the data changes" are real. Say so when presenting: the model's text is cached,
the data and the computation are not.

Follows docs/DEMO_SCRIPT.md: main question, follow-up, ambiguous question (and each one-click interpretation, as the
UI sends it), not-in-data, write attempt, the data-change question, and the masked-balance question as the
restricted role.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from datamind.config import build  # noqa: E402

CONVERSATION = [
    "Which 5 nations generated the most revenue from customers in ASIA in 1994?",
    "and in 1995?",
]
SINGLE = [
    "Who are our best customers?",
    "What is the average delivery driver rating?",
    "Delete all orders from 1992",
    "Which customer generated the most revenue from orders placed in July 1998?",
]
RESTRICTED = "Top 5 customers by account balance in the BUILDING segment"


def show(a, label: str = "") -> None:
    total = a.timings.get("total_s", 0)
    print(f"{a.status:<12} {(a.confidence or ''):<6} {total:>6.1f}s  {label}{a.question[:80]}", flush=True)


def main() -> int:
    dm = build()
    t0 = time.time()
    history: list[dict] = []
    for q in CONVERSATION:                      # one conversation, exactly like the chat in the UI
        a = dm.ask(q, history=history)
        show(a)
        if a.status in ("answered", "empty"):
            history.append(a.history_entry())
    for q in SINGLE:
        a = dm.ask(q)
        show(a)
        for interp in a.interpretations:        # the UI's interpretation buttons send this exact text
            show(dm.ask(f"{q} (I mean: {interp})"), "  -> ")
    show(dm.ask(RESTRICTED, role="DATAMIND_RESTRICTED"), "[restricted] ")
    print(f"Warmed in {time.time() - t0:.0f}s. Ask these in the same order in a fresh conversation.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
