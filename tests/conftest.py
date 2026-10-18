from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from datamind.executors import DuckDBExecutor  # noqa: E402
from datamind.semantic import load_model  # noqa: E402


@pytest.fixture(scope="session")
def model():
    return load_model(ROOT / "config" / "datasets" / "tpch.yaml")


@pytest.fixture(scope="session")
def tpch_small_dir():
    d = ROOT / "data" / "tpch_sf0_01"
    if len(list(d.glob("*.parquet"))) < 8:
        try:
            from make_local_tpch import generate
            d = generate(0.01)
        except SystemExit:
            pytest.skip("tpchgen-cli not installed: pip install tpchgen-cli")
    return d


@pytest.fixture(scope="session")
def duck(tpch_small_dir):
    return DuckDBExecutor(tpch_small_dir)


@pytest.fixture()
def duck_writable(tpch_small_dir):
    return DuckDBExecutor(tpch_small_dir, materialize=True)


@pytest.fixture(scope="session")
def duck_sf1():
    d = ROOT / "data" / "tpch_sf1"
    if len(list(d.glob("*.parquet"))) < 8:
        pytest.skip("SF1 data not generated (python scripts/make_local_tpch.py --scale 1)")
    return DuckDBExecutor(d)


@pytest.fixture(autouse=True, scope="session")
def no_real_credentials_in_tests():
    """Fail loudly if any test loaded the developer's real .env into the environment."""
    import os
    before = {k for k in os.environ if k.startswith(("SNOWFLAKE_", "GEMINI_", "HF_TOKEN"))}
    yield
    leaked = {k for k in os.environ if k.startswith(("SNOWFLAKE_", "GEMINI_", "HF_TOKEN"))} - before
    assert not leaked, f"tests leaked real configuration into the environment: {sorted(leaked)}"
