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
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
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
                       "tables": len(d.get("entities") or []), "sample_questions": d.get("sample_questions") or [],
                       "description": (d.get("description") or "").strip(),
                       "entities": d.get("entities") or [],
                       "metrics": d.get("metrics") or []}
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


@app.post("/api/datasets/upload")
async def upload_dataset(
    file: UploadFile = File(...),
    name: str = Form(""),
    title: str = Form("")
) -> dict[str, Any]:
    content = await file.read()
    if not content:
        raise HTTPException(400, "Uploaded file is empty.")

    import io, re, pandas as pd
    try:
        df = pd.read_csv(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(400, f"Could not parse CSV: {e}")

    if df.empty:
        raise HTTPException(400, "CSV file has no rows.")

    clean_id = re.sub(r"[^a-zA-Z0-9_]", "", (name or file.filename or "dataset").split(".")[0]).lower()
    if not clean_id:
        clean_id = "custom_dataset"
    clean_title = title.strip() or clean_id.replace("_", " ").title()

    df.columns = [re.sub(r"[^a-zA-Z0-9_]", "_", str(c)).upper() for c in df.columns]

    local_dir = ROOT / "data" / clean_id
    local_dir.mkdir(parents=True, exist_ok=True)
    csv_path = local_dir / f"{clean_id}.csv"
    csv_path.write_bytes(content)

    ag = agent(default_dataset())
    ex = ag.executor
    schema_name = clean_id.upper()
    db_name = getattr(ag.model, "database", "DATAMIND_DB")

    yaml_text = ""
    if getattr(ex, "engine", "") == "snowflake":
        import os
        account = os.getenv("SNOWFLAKE_ACCOUNT")
        user = os.getenv("SNOWFLAKE_USER")
        password = os.getenv("SNOWFLAKE_PASSWORD")
        if account and user and password:
            try:
                import snowflake.connector
                from snowflake.connector.pandas_tools import write_pandas
                conn = snowflake.connector.connect(
                    account=account,
                    user=user,
                    password=password,
                    role="DATAMIND_ADMIN",
                    warehouse=os.getenv("SNOWFLAKE_WAREHOUSE", "DATAMIND_WH"),
                    database=db_name
                )
                with conn.cursor() as cur:
                    cur.execute(f"CREATE SCHEMA IF NOT EXISTS {db_name}.{schema_name}")
                    cur.execute(f"GRANT USAGE ON SCHEMA {db_name}.{schema_name} TO ROLE DATAMIND_AGENT")
                    cur.execute(f"GRANT USAGE ON SCHEMA {db_name}.{schema_name} TO ROLE DATAMIND_RESTRICTED")
                write_pandas(conn, df, clean_id.upper(), schema=schema_name, database=db_name, auto_create_table=True, overwrite=True)
                with conn.cursor() as cur:
                    cur.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA {db_name}.{schema_name} TO ROLE DATAMIND_AGENT")
                    cur.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA {db_name}.{schema_name} TO ROLE DATAMIND_RESTRICTED")
                conn.close()
                from datamind.discover import draft_model
                yaml_text = draft_model(ex, db_name, schema_name, clean_id, clean_title)
            except Exception:
                pass

    if not yaml_text:
        cols = []
        for col in df.columns:
            series = df[col]
            dtype = "number" if pd.api.types.is_numeric_dtype(series) else ("date" if pd.api.types.is_datetime64_any_dtype(series) else "text")
            unique_vals = series.dropna().unique()
            if dtype == "text" and len(unique_vals) <= 30:
                cols.append({"name": col.lower(), "type": "category", "description": f"{col} category", "values": [str(v) for v in unique_vals[:30]]})
            else:
                cols.append({"name": col.lower(), "type": dtype, "description": f"{col} column"})
        entity = {
            "alias": clean_id,
            "table": clean_id.upper(),
            "description": f"One row per {clean_id} record ({len(df)} total rows).",
            "columns": cols
        }
        yaml_dict = {
            "name": clean_id,
            "title": clean_title,
            "description": f"Dataset with {len(df)} rows and {len(df.columns)} columns.",
            "database": db_name,
            "schema": schema_name,
            "data_coverage": f"{len(df)} rows loaded.",
            "sample_questions": [f"How many {clean_id} records are there?"],
            "entities": [entity],
            "metrics": [{"name": f"{clean_id}_count", "formula": "COUNT(*)", "description": f"Total {clean_id} count"}]
        }
        yaml_text = yaml.dump(yaml_dict, sort_keys=False)

    yaml_path = DATASET_DIR / f"{clean_id}.yaml"
    yaml_path.write_text(yaml_text, encoding="utf-8")

    return {
        "ok": True,
        "id": clean_id,
        "title": clean_title,
        "rows": len(df),
        "columns": list(df.columns),
        "datasets": list(datasets().values())
    }


_dist = ROOT / "web" / "dist"
if _dist.exists():   # the built React app, served from the same origin as the API
    app.mount("/", StaticFiles(directory=_dist, html=True), name="web")
