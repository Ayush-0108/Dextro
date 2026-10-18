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
import threading
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

    def run(self, sql: str, tag: dict[str, Any] | None = None, max_rows: int = 1000,
            role: str | None = None) -> QueryResult: ...


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
            # keep the session alive while the app sits idle during judging
            "client_session_keep_alive": True,
            # we only run synchronous queries, so a plain logout on close is right (also silences a FutureWarning)
            "enable_server_session_keep_alive_auto_detection": False,
        }
        pk_file = private_key_file or os.getenv("SNOWFLAKE_PRIVATE_KEY_FILE")
        pw = password or os.getenv("SNOWFLAKE_PASSWORD")
        auth = authenticator or os.getenv("SNOWFLAKE_AUTHENTICATOR")
        # Two supported sign-ins: a password (trial accounts are exempt from Snowflake's MFA rollout, so this is
        # the quick start) or a key pair for the TYPE = SERVICE user DATAMIND_APP (works on any account).
        if pk_file:
            pk = Path(pk_file).expanduser()
            if not pk.is_absolute():   # relative paths in .env are relative to the repository
                pk = Path(__file__).resolve().parent.parent / pk
            if not pk.exists():
                raise ValueError(f"SNOWFLAKE_PRIVATE_KEY_FILE={pk_file} not found: run python scripts/make_keypair.py, "
                                 "or remove that line and set SNOWFLAKE_PASSWORD to sign in with a password")
            self.params["private_key_file"] = str(pk)
            pp = private_key_passphrase or os.getenv("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE")
            if pp:
                self.params["private_key_file_pwd"] = pp
        elif pw:
            self.params["password"] = pw
        elif not auth:
            raise ValueError("no Snowflake credentials: set SNOWFLAKE_PASSWORD (trial accounts) or "
                             "SNOWFLAKE_PRIVATE_KEY_FILE (key pair) in .env")
        if auth:
            self.params["authenticator"] = auth
        self._conn = None
        self._session_role: str | None = None
        # one connection is shared by every app session: the role switch and the query must run together
        self._lock = threading.RLock()

    @property
    def role(self) -> str:
        return self.params["role"]

    def connect(self):
        if self._conn is None:
            import snowflake.connector  # imported lazily so offline tests don't need credentials
            self._conn = snowflake.connector.connect(**self.params)
            self._session_role = self.params["role"]
            # Only the agent role's privileges may apply: without this, a user's default secondary
            # roles (often ALL) would add write privileges from their other roles to this session.
            self._conn.cursor().execute("USE SECONDARY ROLES NONE")
        return self._conn

    def _check_role(self, role: str) -> str:
        role = role.upper()
        if role not in self.ALLOWED_ROLES:
            raise ValueError(f"role {role} is not an allowed agent role")
        return role

    def set_role(self, role: str) -> None:
        """Change the default role for later queries (prefer passing `role` to `run`)."""
        with self._lock:
            self.params["role"] = self._check_role(role)

    def _reset(self) -> None:
        try:
            if self._conn is not None:
                self._conn.close()
        except Exception:
            pass
        self._conn, self._session_role = None, None

    def run(self, sql: str, tag: dict[str, Any] | None = None, max_rows: int = 1000,
            role: str | None = None) -> QueryResult:
        role = self._check_role(role or self.params["role"])
        with self._lock:
            for attempt in range(2):
                res = self._run_once(sql, tag, max_rows, role)
                if res.ok or attempt == 1 or not _is_connection_error(res.error or ""):
                    return res
                self._reset()   # session expired or connection dropped: reconnect once
            return res

    def _run_once(self, sql: str, tag: dict[str, Any] | None, max_rows: int, role: str) -> QueryResult:
        t0 = time.time()
        cur = None
        try:
            conn = self.connect()
            cur = conn.cursor()
            if role != self._session_role:
                cur.execute(f"USE ROLE {role}")   # role is checked against ALLOWED_ROLES
                self._session_role = role
            qtag = json.dumps({"app": "datamind", **(tag or {})})[:2000]
            cur.execute("ALTER SESSION SET QUERY_TAG = %s", (qtag,))
            cur.execute(sql)
            rows = cur.fetchmany(max_rows + 1)
            cols = [d[0].lower() for d in cur.description] if cur.description else []
            return QueryResult(sql=sql, columns=cols, rows=[tuple(r) for r in rows[:max_rows]],
                               truncated=len(rows) > max_rows, query_id=cur.sfqid,
                               elapsed_ms=int((time.time() - t0) * 1000), engine=self.engine, role=role)
        except Exception as e:  # surface the database error to the repair loop
            return QueryResult(sql=sql, query_id=getattr(cur, "sfqid", None), engine=self.engine,
                               elapsed_ms=int((time.time() - t0) * 1000), role=role,
                               error=f"{type(e).__name__}: {e}")
        finally:
            if cur is not None:
                try:
                    cur.close()
                except Exception:
                    pass

    def close(self) -> None:
        with self._lock:
            self._reset()

    def describe(self) -> dict[str, Any]:
        return {k: self.params[k] for k in ("account", "user", "role", "warehouse", "database", "schema")}


_CONNECTION_ERRORS = ("authentication token has expired", "session no longer exists", "connection is closed",
                      "session expired", "390114", "390112", "250001", "250002", "08001", "08003")


def _is_connection_error(message: str) -> bool:
    m = message.lower()
    return any(s in m for s in _CONNECTION_ERRORS)


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

    def run(self, sql: str, tag: dict[str, Any] | None = None, max_rows: int = 1000,
            role: str | None = None) -> QueryResult:
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
