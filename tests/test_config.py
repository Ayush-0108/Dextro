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
