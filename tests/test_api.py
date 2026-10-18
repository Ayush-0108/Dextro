"""The REST API used by the React frontend, against an offline agent (DuckDB + scripted Gemma stand-in)."""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def client(model, duck, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    import api.server as server
    from datamind.pipeline import DataMind
    from datamind.retrieval import ExampleStore
    from fakes import oracle_llm
    server.agent.cache_clear()
    monkeypatch.setattr(server.config, "build", lambda *a, **k: DataMind(
        model, duck, oracle_llm(), examples=ExampleStore.load(ROOT / "eval" / "tpch_dev.yaml"), log_dir=None))
    yield TestClient(server.app)
    server.agent.cache_clear()


def test_datasets_lists_every_semantic_model(client):
    d = client.get("/api/datasets").json()
    ids = {x["id"] for x in d["datasets"]}
    assert {"tpch", "chinook"} <= ids and d["default"] in ids
    assert all(x["sample_questions"] for x in d["datasets"])


def test_health_is_computed_not_claimed(client):
    h = client.get("/api/health").json()
    assert h["snowflake"]["state"] == "warn" and h["snowflake"]["label"] == "Offline engine"   # DuckDB here
    assert "gemma" in h


def test_ask_returns_evidence(client):
    r = client.post("/api/ask", json={"question": "What was revenue by customer region in 1996?"})
    assert r.status_code == 200
    a = r.json()
    assert a["status"] == "answered" and a["confidence"] == "high"
    assert a["chosen"]["sql"].upper().startswith(("SELECT", "WITH"))
    assert a["result"]["columns"] and a["result"]["rows"] and a["result"]["query_id"]
    assert any(i["asked"] == "year 1996" and i["found"] for i in a["coverage"])
    assert a["explanation"] and a["history_entry"]["sql"]


def test_follow_up_uses_history_and_refusal_needs_no_model(client):
    first = client.post("/api/ask", json={"question": "What was revenue by customer region in 1996?"}).json()
    r = client.post("/api/ask", json={"question": "Delete all orders from 1992", "history": [first["history_entry"]]})
    assert r.json()["status"] == "refused"


def test_bad_input_is_rejected(client):
    assert client.post("/api/ask", json={"question": ""}).status_code == 422
    assert client.post("/api/ask", json={"question": "x", "role": "admin"}).status_code == 422
    assert client.post("/api/ask", json={"question": "x", "dataset": "nope"}).status_code == 404
