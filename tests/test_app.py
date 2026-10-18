"""Smoke test of the Streamlit UI with an offline agent (DuckDB + scripted Gemma stand-in)."""
from __future__ import annotations

import re
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

    # the app loads .env on start; tests must never pick up the developer's real credentials
    monkeypatch.setattr(cfg, "load_dotenv", lambda *a, **k: None)
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
    # the question -> query checklist: the year asked for is used in the SQL's WHERE clause
    assert "Your question → the query" in text and "year 1996" in text and "WHERE" in text


def test_app_clarifies_ambiguous_questions(app):
    app.chat_input[0].set_value("Who are our best customers?").run()
    assert not app.exception
    labels = [b.label for b in app.button]
    assert "by revenue" in labels and "by number of orders" in labels


def test_app_shows_verification_tower_and_live_status(app):
    app.chat_input[0].set_value("What was revenue by customer region in 1996?").run()
    assert not app.exception
    titles = [e.label for e in app.expander]
    tower = [t for t in titles if re.match(r"^(✅|⚠️) \d\. ", t)]
    assert len(tower) == 6, titles
    assert any("Question → query coverage" in t and "1 of 1" in t for t in tower)
    sidebar = " ".join(m.value for m in app.sidebar.markdown)
    assert "System status" in sidebar and "Snowflake" in sidebar and "Gemma" in sidebar
    assert "Offline engine" in sidebar          # computed from the real engine (DuckDB here), never hard-coded


def test_switching_dataset_starts_a_new_conversation(app):
    app.chat_input[0].set_value("What was revenue by customer region in 1996?").run()
    assert len(app.session_state.turns) == 1
    options = app.sidebar.selectbox[0].options
    assert any("Chinook" in o for o in options) and any("TPC-H" in o for o in options)
    app.sidebar.selectbox[0].set_value(next(o for o in options if "Chinook" in o)).run()
    assert not app.exception and app.session_state.turns == []
