"""Query execution backends.

All SQL in DataMind is written in the Snowflake dialect. SnowflakeExecutor runs it in Snowflake
(the system of record). DuckDBExecutor transpiles it and runs it over local TPC-H Parquet files;
it exists only for offline unit tests and for computing ground truth independently of Snowflake.
"""
from __future__ import annotations

import datetime as dt
import decimal
import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import sqlglot


@dataclass
class QueryResult:
    sql: str
    columns: list[str] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)
    truncated: bool = False
    query_id: str | None = None
    elapsed_ms: int = 0
    engine: str = ""
    role: str | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    @property
    def row_count(self) -> int:
        return len(self.rows)

    def to_json(self) -> dict[str, Any]:
        return {
            "sql": self.sql, "columns": self.columns, "rows": [[_jsonable(v) for v in r] for r in self.rows],
            "truncated": self.truncated, "query_id": self.query_id, "elapsed_ms": self.elapsed_ms,
            "engine": self.engine, "role": self.role, "error": self.error,
        }


def _jsonable(v: Any) -> Any:
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    return v


class Executor(Protocol):
    engine: str

    def run(self, sql: str, tag: dict[str, Any] | None = None, max_rows: int = 1000) -> QueryResult: ...


class SnowflakeExecutor:
    """Runs read-only queries in Snowflake under a least-privilege role.

    Every query is tagged (QUERY_TAG) with the answer id and candidate name so any answer can be
    traced to its entry in Snowflake's query history.
    """
    engine = "snowflake"
    ALLOWED_ROLES = ("DATAMIND_AGENT", "DATAMIND_RESTRICTED")

    def __init__(self, account: str | None = None, user: str | None = None, role: str | None = None,
                 warehouse: str | None = None, database: str | None = None, schema: str | None = None,
                 password: str | None = None, private_key_file: str | None = None,
                 private_key_passphrase: str | None = None, authenticator: str | None = None,
                 statement_timeout_s: int = 120):
        self.params: dict[str, Any] = {
            "account": account or os.environ["SNOWFLAKE_ACCOUNT"],
            "user": user or os.environ["SNOWFLAKE_USER"],
            "role": (role or os.getenv("SNOWFLAKE_ROLE", "DATAMIND_AGENT")).upper(),
            "warehouse": warehouse or os.getenv("SNOWFLAKE_WAREHOUSE", "DATAMIND_WH"),
            "database": database or os.getenv("SNOWFLAKE_DATABASE", "DATAMIND_DB"),
            "schema": schema or os.getenv("SNOWFLAKE_SCHEMA", "TPCH"),
            "session_parameters": {"STATEMENT_TIMEOUT_IN_SECONDS": statement_timeout_s,
                                   "QUERY_TAG": json.dumps({"app": "datamind"})},
            "application": "DataMind",
        }
        pk_file = private_key_file or os.getenv("SNOWFLAKE_PRIVATE_KEY_FILE")
        pw = password or os.getenv("SNOWFLAKE_PASSWORD")
        auth = authenticator or os.getenv("SNOWFLAKE_AUTHENTICATOR")
        if pk_file:
            self.params["private_key_file"] = pk_file
            pp = private_key_passphrase or os.getenv("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE")
            if pp:
                self.params["private_key_file_pwd"] = pp
        elif pw:
            self.params["password"] = pw
        if auth:
            self.params["authenticator"] = auth
        self._conn = None

    @property
    def role(self) -> str:
        return self.params["role"]

    def connect(self):
        if self._conn is None:
            import snowflake.connector  # imported lazily so offline tests don't need credentials
            self._conn = snowflake.connector.connect(**self.params)
            # Only the agent role's privileges may apply: without this, a user's default secondary
            # roles (often ALL) would add write privileges from their other roles to this session.
            self._conn.cursor().execute("USE SECONDARY ROLES NONE")
        return self._conn

    def set_role(self, role: str) -> None:
        role = role.upper()
        if role not in self.ALLOWED_ROLES:
            raise ValueError(f"role {role} is not an allowed agent role")
        if role != self.params["role"]:
            self.params["role"] = role
            if self._conn is not None:
                self._conn.cursor().execute(f"USE ROLE {role}")

    def run(self, sql: str, tag: dict[str, Any] | None = None, max_rows: int = 1000) -> QueryResult:
        conn = self.connect()
        cur = conn.cursor()
        t0 = time.time()
        try:
            qtag = json.dumps({"app": "datamind", **(tag or {})})[:2000]
            cur.execute("ALTER SESSION SET QUERY_TAG = %s", (qtag,))
            cur.execute(sql)
            rows = cur.fetchmany(max_rows + 1)
            cols = [d[0].lower() for d in cur.description] if cur.description else []
            return QueryResult(sql=sql, columns=cols, rows=[tuple(r) for r in rows[:max_rows]],
                               truncated=len(rows) > max_rows, query_id=cur.sfqid,
                               elapsed_ms=int((time.time() - t0) * 1000), engine=self.engine, role=self.role)
        except Exception as e:  # surface the database error to the repair loop
            return QueryResult(sql=sql, query_id=getattr(cur, "sfqid", None), engine=self.engine,
                               elapsed_ms=int((time.time() - t0) * 1000), role=self.role,
                               error=f"{type(e).__name__}: {e}")
        finally:
            cur.close()

    def describe(self) -> dict[str, Any]:
        return {k: self.params[k] for k in ("account", "user", "role", "warehouse", "database", "schema")}


class DuckDBExecutor:
    """Offline executor over TPC-H Parquet files laid out as <database>.<schema>.<TABLE>.

    Used for unit tests and for independent ground-truth computation. Not used to answer
    questions in the judged demo, which always runs in Snowflake.
    """
    engine = "duckdb"

    def __init__(self, data_dir: str | Path, database: str = "DATAMIND_DB", schema: str = "TPCH",
                 materialize: bool = False):
        import duckdb
        self.data_dir = Path(data_dir)
        self.con = duckdb.connect()
        self.con.execute(f"ATTACH ':memory:' AS {database}")
        self.con.execute(f"CREATE SCHEMA {database}.{schema}")
        kind = "TABLE" if materialize else "VIEW"
        files = sorted(self.data_dir.glob("*.parquet"))
        if not files:
            raise FileNotFoundError(f"no parquet files in {self.data_dir}; run scripts/make_local_tpch.py")
        for f in files:
            self.con.execute(
                f"CREATE {kind} {database}.{schema}.{f.stem.upper()} AS SELECT * FROM read_parquet('{f.as_posix()}')"
            )
        self.role = "local"

    def transpile(self, sql: str) -> str:
        return sqlglot.transpile(sql, read="snowflake", write="duckdb")[0]

    def run(self, sql: str, tag: dict[str, Any] | None = None, max_rows: int = 1000) -> QueryResult:
        t0 = time.time()
        qid = "duckdb-" + hashlib.sha1(f"{sql}{time.time()}".encode()).hexdigest()[:12]
        try:
            local = self.transpile(sql)
            cur = self.con.execute(local)
            rows = cur.fetchmany(max_rows + 1)
            cols = [d[0].lower() for d in cur.description] if cur.description else []
            return QueryResult(sql=sql, columns=cols, rows=[tuple(r) for r in rows[:max_rows]],
                               truncated=len(rows) > max_rows, query_id=qid,
                               elapsed_ms=int((time.time() - t0) * 1000), engine=self.engine, role=self.role)
        except Exception as e:
            return QueryResult(sql=sql, query_id=qid, engine=self.engine, role=self.role,
                               elapsed_ms=int((time.time() - t0) * 1000), error=f"{type(e).__name__}: {e}")

    def execute_admin(self, sql: str) -> None:
        """Run a write statement (only for the data-change demo/tests on materialized tables)."""
        self.con.execute(self.transpile(sql))

    def describe(self) -> dict[str, Any]:
        return {"engine": "duckdb (offline dev/test only)", "data_dir": str(self.data_dir)}
