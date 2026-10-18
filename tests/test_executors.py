"""SnowflakeExecutor behaviour against a fake connector (no credentials or network needed)."""
from __future__ import annotations

import pytest
import snowflake.connector

from datamind.executors import SnowflakeExecutor


class FakeCursor:
    def __init__(self, conn):
        self.conn, self.sfqid, self.description, self._rows = conn, None, None, []

    def execute(self, sql, params=None):
        self.conn.log.append(sql)
        if sql.startswith("SELECT") and self.conn.expired:
            raise snowflake.connector.errors.ProgrammingError(
                "Authentication token has expired.  The user must authenticate again.", errno=390114)
        if sql.startswith("SELECT"):
            self.sfqid, self.description, self._rows = f"q{len(self.conn.log)}", [("N",)], [(1,)]

    def fetchmany(self, n):
        return self._rows[:n]

    def close(self):
        pass


class FakeConn:
    def __init__(self, expired=False):
        self.expired, self.log, self.closed = expired, [], False

    def cursor(self):
        return FakeCursor(self)

    def close(self):
        self.closed = True


@pytest.fixture()
def fake_connect(monkeypatch):
    made = []

    def connect(**params):
        conn = FakeConn(expired=not made)   # the first connection's session has expired
        conn.params = params
        made.append(conn)
        return conn
    monkeypatch.setattr(snowflake.connector, "connect", connect)
    return made


def executor():
    return SnowflakeExecutor(account="a", user="u", password="p", role="DATAMIND_AGENT")


def test_reconnects_once_when_the_session_expired(fake_connect):
    r = executor().run("SELECT 1")
    assert r.ok and r.rows == [(1,)] and len(fake_connect) == 2 and fake_connect[0].closed
    assert fake_connect[1].params["client_session_keep_alive"] is True
    assert fake_connect[1].params["enable_server_session_keep_alive_auto_detection"] is False
    assert fake_connect[1].log[0] == "USE SECONDARY ROLES NONE"


def test_sql_errors_are_not_retried(fake_connect, monkeypatch):
    ex = executor()
    ex.run("SELECT 1")   # reconnected; now force an ordinary SQL error
    monkeypatch.setattr(FakeCursor, "execute", lambda self, sql, params=None: (_ for _ in ()).throw(
        snowflake.connector.errors.ProgrammingError("SQL compilation error: invalid identifier 'X'")))
    r = ex.run("SELECT x")
    assert not r.ok and "invalid identifier" in r.error and len(fake_connect) == 2


def test_role_travels_with_each_query(fake_connect):
    ex = executor()
    a = ex.run("SELECT 1", role="DATAMIND_RESTRICTED")
    b = ex.run("SELECT 1")
    log = fake_connect[-1].log
    assert a.role == "DATAMIND_RESTRICTED" and b.role == "DATAMIND_AGENT"
    assert log.index("USE ROLE DATAMIND_RESTRICTED") < log.index("USE ROLE DATAMIND_AGENT")
    assert ex.role == "DATAMIND_AGENT"   # the default role was not changed for other sessions


def test_only_agent_roles_are_allowed(fake_connect):
    with pytest.raises(ValueError):
        executor().run("SELECT 1", role="ACCOUNTADMIN")


def test_keypair_script_writes_a_loadable_key(tmp_path):
    from cryptography.hazmat.primitives import serialization
    from make_keypair import make
    body = make(tmp_path, passphrase=None)
    key = serialization.load_pem_private_key((tmp_path / "rsa_key.p8").read_bytes(), password=None)
    assert key.key_size == 2048 and body and "-----" not in body
    with pytest.raises(SystemExit):
        make(tmp_path, passphrase=None)   # never silently replaces a working key


def test_relative_key_path_is_resolved_from_repo_root():
    from pathlib import Path
    # any file that exists relative to the repository root stands in for keys/rsa_key.p8
    ex = SnowflakeExecutor(account="a", user="u", private_key_file="tests/conftest.py")
    p = Path(ex.params["private_key_file"])
    assert p.is_absolute() and p.exists() and "password" not in ex.params


def test_password_sign_in_for_trial_accounts(monkeypatch):
    monkeypatch.delenv("SNOWFLAKE_PRIVATE_KEY_FILE", raising=False)
    ex = SnowflakeExecutor(account="a", user="me", password="pw")
    assert ex.params["password"] == "pw" and "private_key_file" not in ex.params


def test_missing_key_file_or_credentials_give_clear_errors(monkeypatch):
    for k in ("SNOWFLAKE_PRIVATE_KEY_FILE", "SNOWFLAKE_PASSWORD", "SNOWFLAKE_AUTHENTICATOR"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(ValueError, match="make_keypair"):
        SnowflakeExecutor(account="a", user="u", private_key_file="keys/does_not_exist.p8")
    with pytest.raises(ValueError, match="SNOWFLAKE_PASSWORD"):
        SnowflakeExecutor(account="a", user="u")
