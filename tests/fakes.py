"""Test doubles. An 'oracle' Gemma stand-in that answers with gold SQL, used ONLY to test the
pipeline and evaluation harness offline. It is never used by the app."""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from datamind.llm import ScriptedLLM

ROOT = Path(__file__).resolve().parent.parent


def _index():
    items = yaml.safe_load((ROOT / "eval" / "tpch_dev.yaml").read_text())["items"]
    idx = {}
    for it in items:
        for q in [it["question"], *it.get("paraphrases", [])]:
            idx[q.strip().lower()] = it
    return idx


def oracle_llm() -> ScriptedLLM:
    idx = _index()

    def find(prompt: str):
        m = re.search(r'NEW QUESTION: (".*")', prompt)
        if m:
            q = json.loads(m.group(1))
        else:
            found = re.findall(r"^Question: (.*)$", prompt, re.M)  # last one; earlier ones are few-shot examples
            q = found[-1] if found else ""
        return q, idx.get(q.strip().lower())

    def handler(task: str, prompt: str, opts: dict) -> str:
        q, item = find(prompt)
        if task == "router":
            expect = (item or {}).get("expect", "")
            cat = ("ambiguous" if expect.startswith("clarify") else "not_in_data" if expect.startswith("not_in_data")
                   else "unsafe" if expect.startswith("refused") else "answerable")
            return json.dumps({"category": cat, "standalone_question": q, "assumptions": [],
                               "interpretations": ["by revenue", "by number of orders"] if cat == "ambiguous" else [],
                               "clarifying_question": "Which measure?", "missing": "that information"})
        if task == "plan":
            return json.dumps({"plan": None, "reason": "oracle uses SQL"})
        if task in ("sql", "sql_alt", "repair"):
            return f"```sql\n{item['gold_sql']}\n```" if item and item.get("gold_sql") else "SELECT 1"
        if task == "narrate":
            m = re.search(r"\|---\|.*?\n\| (.+?) \|", prompt, re.S)
            first = m.group(1).split(" | ") if m else []
            return "The first result row is " + ", ".join(first) + "." if first else "No rows."
        return ""

    return ScriptedLLM(handler, name="gemma-oracle-test")
