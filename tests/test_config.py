"""Configuration helpers: .env parsing and the interactive .env writer (no real credentials involved)."""
from __future__ import annotations

import os

import pytest

from datamind.config import load_dotenv, parse_env_value
from make_env import normalize_account, render_env


@pytest.mark.parametrize("raw,value", [
    ("api                          # api = Gemini API", "api"),
    ("gemma-4-31b-it   # api: gemma-4-31b-it or gemma-4-26b-a4b-it", "gemma-4-31b-it"),
    ("'pa ss #1'", "pa ss #1"),
    ('"it\'s"', "it's"),
    ("pa#ss", "pa#ss"),          # a # without a space before it is part of the value
    ("", ""),
])
def test_inline_comments_are_not_part_of_values(raw, value):
    assert parse_env_value(raw) == value


def test_env_example_parses_to_clean_values(tmp_path, monkeypatch):
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    monkeypatch.setattr(os, "environ", {})   # isolated: nothing from .env.example leaks into other tests
    load_dotenv(root / ".env.example")
    assert os.environ["GEMMA_BACKEND"] == "api" and os.environ["GEMMA_MODEL"] == "gemma-4-31b-it"
    assert os.environ["SNOWFLAKE_ROLE"] == "DATAMIND_AGENT" and os.environ["DATAMIND_ENGINE"] == "snowflake"


@pytest.mark.parametrize("raw,expected", [
    ("MYORG-MYACCT", "MYORG-MYACCT"),
    ("MYORG.MYACCT", "MYORG-MYACCT"),
    ("https://myorg-myacct.snowflakecomputing.com", "myorg-myacct"),
    ("https://app.snowflake.com/myorg/myacct/#/workspaces", "MYORG-MYACCT"),
    ("xy12345.ap-south-1.aws", "xy12345.ap-south-1.aws"),
    ("  MYORG-MY_ACCT  ", "MYORG-MY_ACCT"),
])
def test_account_identifier_forms(raw, expected):
    assert normalize_account(raw) == expected


def test_account_identifier_rejects_garbage():
    with pytest.raises(ValueError):
        normalize_account("my account")


def test_render_env_fills_values_and_keeps_comments(tmp_path, monkeypatch):
    template = "# header\nSNOWFLAKE_ACCOUNT=myorg-myaccount   # hint\nSNOWFLAKE_PASSWORD=\n# SNOWFLAKE_PRIVATE_KEY_FILE=keys/x\n"
    out = render_env(template, {"SNOWFLAKE_ACCOUNT": "A-B", "SNOWFLAKE_PASSWORD": "p'w #1", "GEMINI_API_KEY": "k"})
    assert "# header" in out and "# SNOWFLAKE_PRIVATE_KEY_FILE=keys/x" in out
    env = tmp_path / ".env"
    env.write_text(out)
    monkeypatch.setattr(os, "environ", {})
    load_dotenv(env)
    assert os.environ["SNOWFLAKE_ACCOUNT"] == "A-B" and os.environ["SNOWFLAKE_PASSWORD"] == "p'w #1"
    assert os.environ["GEMINI_API_KEY"] == "k"


def test_fill_mode_asks_only_for_missing_values(tmp_path, monkeypatch):
    import make_env
    (tmp_path / ".env").write_text("SNOWFLAKE_ACCOUNT='A-B'\nSNOWFLAKE_USER='me'\nSNOWFLAKE_PASSWORD=\nGEMINI_API_KEY=\n")
    monkeypatch.setattr(make_env, "ROOT", tmp_path)
    asked = []
    monkeypatch.setattr(make_env.getpass, "getpass", lambda prompt: asked.append(prompt) or "secret value")
    monkeypatch.setattr("builtins.input", lambda prompt: pytest.fail(f"should not ask: {prompt}"))
    assert make_env.main(["--fill"]) == 0
    assert len(asked) == 2 and make_env.missing_values((tmp_path / ".env").read_text()) == []
    assert (tmp_path / ".env.bak").exists() and oct((tmp_path / ".env").stat().st_mode)[-3:] == "600"
    monkeypatch.setattr(os, "environ", {})
    load_dotenv(tmp_path / ".env")
    assert os.environ["SNOWFLAKE_ACCOUNT"] == "A-B" and os.environ["SNOWFLAKE_PASSWORD"] == "secret value"


def test_placeholders_count_as_missing():
    from make_env import missing_values
    assert missing_values("SNOWFLAKE_ACCOUNT=myorg-myaccount\nSNOWFLAKE_USER=your_login_name\n") == [
        "SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_PASSWORD", "GEMINI_API_KEY"]


def test_script_runs_standalone(tmp_path):
    # run exactly as a user would, from outside the repo, so only scripts/ is on the path
    import subprocess
    import sys
    from pathlib import Path
    script = Path(__file__).resolve().parent.parent / "scripts" / "make_env.py"
    code = (f"import runpy, sys; sys.argv = ['make_env.py']; "
            f"g = runpy.run_path({str(script)!r}, run_name='not_main'); print(g['missing_values']('X=1'))")
    r = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "SNOWFLAKE_PASSWORD" in r.stdout
