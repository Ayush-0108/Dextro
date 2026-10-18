"""Wiring: build a DataMind instance from environment variables (see .env.example)."""
from __future__ import annotations

import os
import re
from pathlib import Path

from .executors import DuckDBExecutor, SnowflakeExecutor
from .llm import LLM, make_llm
from .pipeline import DataMind
from .retrieval import ExampleStore
from .semantic import SemanticModel, load_model

ROOT = Path(__file__).resolve().parent.parent


def parse_env_value(raw: str) -> str:
    """Value of a KEY=VALUE line: quoted values are taken verbatim; unquoted ones end at ' #' (inline comment)."""
    v = raw.strip()
    if v[:1] in ("'", '"'):
        end = v.find(v[0], 1)
        if end != -1:
            return v[1:end]
    return re.split(r"\s+#", v, maxsplit=1)[0].strip()


def load_dotenv(path: str | Path | None = None) -> None:
    """Minimal .env loader (KEY=VALUE lines, inline # comments allowed); existing environment variables win."""
    p = Path(path) if path else ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), parse_env_value(v))


def _path(env: str, default: str) -> Path:
    p = Path(os.getenv(env, default))
    return p if p.is_absolute() else ROOT / p


def dataset_path() -> Path:
    return _path("DATAMIND_DATASET", "config/datasets/tpch.yaml")


def build_model() -> SemanticModel:
    return load_model(dataset_path(), database=os.getenv("SNOWFLAKE_DATABASE"), schema=os.getenv("SNOWFLAKE_SCHEMA"))


def build_executor(model: SemanticModel, engine: str | None = None):
    engine = (engine or os.getenv("DATAMIND_ENGINE", "snowflake")).lower()
    if engine == "snowflake":
        return SnowflakeExecutor(database=model.database, schema=model.schema_name)
    if engine == "duckdb":
        return DuckDBExecutor(_path("DATAMIND_DUCKDB_DATA", "data/tpch_sf0_01"), model.database, model.schema_name)
    raise ValueError(f"unknown DATAMIND_ENGINE {engine!r}")


def build(engine: str | None = None, llm: LLM | None = None) -> DataMind:
    load_dotenv()
    model = build_model()
    executor = build_executor(model, engine)
    examples = ExampleStore.load(_path("DATAMIND_EXAMPLES", f"eval/{model.name}_dev.yaml"))
    return DataMind(
        model=model, executor=executor, llm=llm or make_llm(),
        examples=examples,
        max_rows=int(os.getenv("DATAMIND_MAX_ROWS", "1000")),
        log_dir=_path("DATAMIND_LOG_DIR", "runs"),
        thinking=os.getenv("GEMMA_THINKING", "1") not in ("0", "false", "no"),
    )
