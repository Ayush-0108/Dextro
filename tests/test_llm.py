"""Gemini API client behaviour against a fake client (no key or network needed)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

import datamind.llm as llm_mod
from datamind.llm import GemmaAPI, LLMError


class FakeModels:
    def __init__(self, script):
        self.script, self.calls = list(script), []

    def generate_content(self, model, contents, config):
        self.calls.append(SimpleNamespace(model=model, contents=contents, config=config))
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        if callable(step):
            return step(contents, config)
        return SimpleNamespace(text=step)


def api(script):
    models = FakeModels(script)
    return GemmaAPI(model="gemma-4-31b-it", client=SimpleNamespace(models=models)), models


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    slept = []
    monkeypatch.setattr(llm_mod.time, "sleep", slept.append)
    return slept


def test_system_instruction_is_folded_into_prompt_when_rejected(no_sleep):
    g, models = api([Exception("400 INVALID_ARGUMENT. Developer instruction is not enabled for models/gemma-4-31b-it"),
                     "ok", "ok again"])
    assert g.complete("question", system="SYSTEM RULES") == "ok"
    assert models.calls[0].config.system_instruction == "SYSTEM RULES"
    assert models.calls[1].config.system_instruction is None
    assert models.calls[1].contents.startswith("SYSTEM RULES") and "question" in models.calls[1].contents
    g.complete("next", system="SYSTEM RULES")   # remembered: no failing call first
    assert models.calls[2].config.system_instruction is None and no_sleep == []


def test_rate_limit_waits_as_long_as_the_server_asks(no_sleep):
    g, _ = api([Exception("429 RESOURCE_EXHAUSTED {'retryDelay': '17s'}"), "ok"])
    assert g.complete("q") == "ok" and no_sleep == [17.0]


def test_rate_limit_wait_is_bounded(no_sleep):
    g, _ = api([Exception("429 RESOURCE_EXHAUSTED {'retryDelay': '900s'}"), "ok"])
    assert g.complete("q") == "ok" and no_sleep == [60.0]


def test_thinking_settings_are_dropped_when_rejected(no_sleep):
    g, models = api([Exception("400 thinking_level is not supported for this model"), "ok"])
    assert g.complete("q", thinking=True) == "ok"
    assert models.calls[0].config.thinking_config is not None and models.calls[1].config.thinking_config is None


def test_non_retryable_errors_fail_fast(no_sleep):
    g, models = api([Exception("400 API key not valid")])
    with pytest.raises(LLMError, match="API key not valid"):
        g.complete("q")
    assert len(models.calls) == 1 and no_sleep == []


def test_gives_up_after_max_retries(no_sleep):
    g, models = api([Exception("503 UNAVAILABLE")] * 5)
    with pytest.raises(LLMError):
        g.complete("q")
    assert len(models.calls) == 5 and no_sleep == [2.0, 4.0, 8.0, 16.0]


def test_output_budget_leaves_room_for_thinking():
    g, models = api(["ok"])
    g.complete("q", thinking=True)
    assert models.calls[0].config.max_output_tokens >= 8192


def test_client_gets_a_timeout(monkeypatch):
    seen = {}

    class FakeGenaiClient:
        def __init__(self, api_key, http_options):
            seen["timeout"] = http_options.timeout
    import google.genai
    monkeypatch.setattr(google.genai, "Client", FakeGenaiClient)
    GemmaAPI(model="gemma-4-31b-it", api_key="test-key", timeout_s=30)
    assert seen["timeout"] == 30000


def test_only_gemma_models_are_accepted():
    with pytest.raises(ValueError):
        GemmaAPI(model="gemini-2.5-pro", client=object())


def test_usage_is_recorded_for_rate_limit_measurement(no_sleep):
    from datamind.llm import CachedLLM
    g, _ = api([Exception("429 RESOURCE_EXHAUSTED {'retryDelay': '5s'}"), "ok"])
    c = CachedLLM(g, enabled=False)
    c.complete("q")
    assert c.stats == {"cache_hits": 0, "model_calls": 1, "requests": 2, "rate_limited": 1, "waited_s": 5.0}
