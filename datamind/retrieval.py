"""Retrieval of verified question->SQL examples used as few-shot context for SQL generation.

Examples come from the development split of the evaluation set (never the hold-out split). During
evaluation the item being scored is excluded, so the agent never sees its own answer.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

_STOP = set("""a an the of in on for to by with and or is are was were what which who how many much
do does did me show list give tell from at as per each all any be this that these those it its our we
their there than then""".split())


def _tokens(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9#]+", s.lower()) if t not in _STOP}


class ExampleStore:
    def __init__(self, items: list[dict[str, Any]]):
        # follow-up items ("and in 1997?") aren't standalone questions, so they make poor examples
        self.items = [i for i in items if i.get("gold_sql") and not i.get("history")]
        self._tok = [_tokens(i["question"] + " " + " ".join(i.get("paraphrases", []))) for i in self.items]

    @classmethod
    def load(cls, path: str | Path | None) -> "ExampleStore":
        if not path or not Path(path).exists():
            return cls([])
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        return cls([i for i in data.get("items", []) if i.get("split", "dev") == "dev"])

    def search(self, question: str, k: int = 3, exclude_ids: set[str] = frozenset()) -> list[dict[str, Any]]:
        q = _tokens(question)
        scored = []
        for item, toks in zip(self.items, self._tok):
            if item.get("id") in exclude_ids:
                continue
            if not q or not toks:
                continue
            score = len(q & toks) / len(q | toks)
            if score > 0:
                scored.append((score, item))
        scored.sort(key=lambda x: -x[0])
        return [{"question": i["question"], "sql": i["gold_sql"], "id": i.get("id")} for _, i in scored[:k]]
