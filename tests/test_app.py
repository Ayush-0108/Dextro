"""Smoke test of the Streamlit UI with an offline agent (DuckDB + scripted Gemma stand-in)."""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def app(model, duck, monkeypatch):
    st_testing = pytest.importorskip("streamlit.testing.v1")
    import datamind.config as cfg
    from datamind.pipeline import DataMind
    from datamind.retrieval import ExampleStore
    from fakes import oracle_llm

    monkeypatch.setattr(cfg, "build", lambda *a, **k: DataMind(
        model, duck, oracle_llm(), examples=ExampleStore.load(ROOT / "eval" / "tpch_dev.yaml"), log_dir=None))
    at = st_testing.AppTest.from_file(str(ROOT / "app" / "streamlit_app.py"), default_timeout=60)
    at.run()
    return at


def test_app_answers_with_evidence(app):
    assert not app.exception
    app.chat_input[0].set_value("What was revenue by customer region in 1996?").run()
    assert not app.exception
    text = " ".join(m.value for m in app.markdown)
    assert "Answered" in text and "confidence" in text
    assert len(app.tabs) >= 4                      # result / explanation / SQL & evidence / cross-check
    assert any("SELECT" in c.value for c in app.code)
    assert app.dataframe                            # result rows rendered


def test_app_clarifies_ambiguous_questions(app):
    app.chat_input[0].set_value("Who are our best customers?").run()
    assert not app.exception
    labels = [b.label for b in app.button]
    assert "by revenue" in labels and "by number of orders" in labels
