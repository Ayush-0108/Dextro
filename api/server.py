"""Nexora REST API for the React frontend (web/). It only *uses* the DataMind pipeline; nothing here changes how
answers are computed. Every status it reports comes from live checks or from the answer's own run.

    uvicorn api.server:app --port 8000          # API (and the built web app at /, if web/dist exists)
"""
from __future__ import annotations

import dataclasses
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from datamind import config
from datamind.pipeline import Answer

ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = ROOT / "config" / "datasets"
ROLES = {"analyst": "DATAMIND_AGENT", "restricted": "DATAMIND_RESTRICTED"}
MAX_ROWS_TO_CLIENT = 500

app = FastAPI(title="Nexora API", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["GET", "POST"], allow_headers=["*"])
_build_lock = threading.Lock()


def datasets() -> dict[str, dict[str, Any]]:
    """Every semantic model in config/datasets, keyed by its file stem."""
    out = {}
    for p in sorted(DATASET_DIR.glob("*.yaml")):
        try:
            d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue
        out[p.stem] = {"id": p.stem, "path": str(p.relative_to(ROOT)), "title": d.get("title") or p.stem,
                       "coverage": (d.get("data_coverage") or "").strip(),
                       "tables": len(d.get("entities") or []), "sample_questions": d.get("sample_questions") or []}
    return out


@lru_cache(maxsize=8)
def agent(dataset_id: str):
    ds = datasets().get(dataset_id)
    if ds is None:
        raise HTTPException(404, f"unknown dataset {dataset_id!r}")
    with _build_lock:
        return config.build(dataset=ds["path"])


def default_dataset() -> str:
    import os
    want = Path(os.getenv("DATAMIND_DATASET", "config/datasets/tpch.yaml")).stem
    ids = list(datasets())
    return want if want in ids else ids[0]


class HistoryItem(BaseModel):
    question: str
    standalone_question: str | None = None
    summary: str | None = None
    sql: str | None = None


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    dataset: str | None = None
    role: Literal["analyst", "restricted"] = "analyst"
    history: list[HistoryItem] = []


def answer_payload(a: Answer, warehouse: str = "") -> dict[str, Any]:
    """Answer.to_json plus the chosen result rows (capped), checked numbers with their cells, and history entry."""
    d = a.to_json()
    res = a.result
    d["chosen"] = {"name": a.chosen.name, "sql": a.chosen.sql} if a.chosen else None
    d["result"] = None if res is None else {
        **{k: v for k, v in res.to_json().items() if k != "rows"},
        "rows": res.to_json()["rows"][:MAX_ROWS_TO_CLIENT], "row_count": res.row_count, "warehouse": warehouse}
    d["number_checks"] = [dataclasses.asdict(n) for n in a.number_checks]
    d["history_entry"] = a.history_entry()
    return d


@app.get("/api/datasets")
def list_datasets() -> dict[str, Any]:
    return {"default": default_dataset(), "datasets": list(datasets().values())}


@app.get("/api/health")
def health(dataset: str | None = None) -> dict[str, Any]:
    """Live checks: a Snowflake context query (no warehouse time) and whether the Gemma model is available."""
    ag = agent(dataset or default_dataset())
    out: dict[str, Any] = {}
    ex = ag.executor
    if getattr(ex, "engine", "") == "snowflake":
        r = ex.run("SELECT CURRENT_REGION(), CURRENT_VERSION()", tag={"purpose": "health"})
        desc = ex.describe()
        out["snowflake"] = ({"state": "ok", "label": "Connected", "warehouse": desc.get("warehouse"),
                             "region": r.rows[0][0], "version": r.rows[0][1]} if r.ok and r.rows
                            else {"state": "bad", "label": "Not reachable", "detail": (r.error or "")[:120]})
    else:
        out["snowflake"] = {"state": "warn", "label": "Offline engine", "detail": f"{getattr(ex, 'engine', '?')} — development only"}
    llm = getattr(ag.llm, "inner", ag.llm)
    host, model = getattr(llm, "host", None), getattr(llm, "model", "")
    if host:
        try:
            import httpx
            tags = [m.get("name", "") for m in httpx.get(f"{host}/api/tags", timeout=2).json().get("models", [])]
            ok = any(t == model or t.split(":")[0] == model for t in tags)
            out["gemma"] = {"state": "ok" if ok else "bad", "label": "Ready" if ok else "Model not pulled",
                            "detail": f"Ollama · {model}"}
        except Exception as e:  # noqa: BLE001 - reported to the client
            out["gemma"] = {"state": "bad", "label": "Ollama not reachable", "detail": str(e)[:120]}
    else:
        out["gemma"] = {"state": "ok", "label": "Configured", "detail": ag.llm.name}
    return out


@app.post("/api/ask")
def ask(req: AskRequest) -> dict[str, Any]:
    ag = agent(req.dataset or default_dataset())
    role = ROLES[req.role] if getattr(ag.executor, "engine", "") == "snowflake" else None
    a = ag.ask(req.question, history=[h.model_dump() for h in req.history], role=role)
    wh = ag.executor.describe().get("warehouse", "") if hasattr(ag.executor, "describe") else ""
    return answer_payload(a, wh)


_dist = ROOT / "web" / "dist"
if _dist.exists():   # the built React app, served from the same origin as the API
    app.mount("/", StaticFiles(directory=_dist, html=True), name="web")
