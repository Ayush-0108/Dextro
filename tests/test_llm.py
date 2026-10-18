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


# ---------------------------------------------------------------- Hugging Face Inference Providers backend
import json as _json

import httpx

from datamind.llm import GemmaHF, make_llm


@pytest.fixture(autouse=True)
def no_hf_env(monkeypatch):
    # other tests may load the developer's real .env; these must not depend on it
    for k in ("GEMMA_MODEL", "HF_PROVIDER", "HF_BASE_URL", "GEMMA_TIMEOUT_S"):
        monkeypatch.delenv(k, raising=False)


def hf(handler, **kw):
    kw.setdefault("model", "google/gemma-4-31B-it")
    return GemmaHF(token="hf_test", transport=httpx.MockTransport(handler), **kw)


def ok(text):
    return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": text}}]})


def test_hf_sends_an_openai_style_request(no_sleep):
    seen = {}

    def handler(req):
        seen["url"], seen["auth"], seen["body"] = str(req.url), req.headers["authorization"], _json.loads(req.content)
        return ok('{"category": "answerable"}')
    g = hf(handler, model="google/gemma-4-31B-it", provider="novita")
    assert g.complete("q", system="rules", json_mode=True) == '{"category": "answerable"}'
    assert seen["url"] == "https://router.huggingface.co/v1/chat/completions" and seen["auth"] == "Bearer hf_test"
    b = seen["body"]
    assert b["model"] == "google/gemma-4-31B-it:novita" and b["response_format"] == {"type": "json_object"}
    assert b["messages"] == [{"role": "system", "content": "rules"}, {"role": "user", "content": "q"}]


def test_hf_honours_retry_after_on_rate_limit(no_sleep):
    replies = [httpx.Response(429, headers={"retry-after": "7"}, text="rate limited"), ok("fine")]
    g = hf(lambda req: replies.pop(0))
    assert g.complete("q") == "fine" and no_sleep == [7.0]
    assert g.stats == {"requests": 2, "rate_limited": 1, "waited_s": 7.0}


def test_hf_drops_json_mode_if_the_provider_rejects_it(no_sleep):
    bodies = []

    def handler(req):
        bodies.append(_json.loads(req.content))
        if "response_format" in bodies[-1]:
            return httpx.Response(400, text="response_format is not supported")
        return ok("{}")
    g = hf(handler)
    assert g.complete("q", json_mode=True) == "{}" and "response_format" not in bodies[-1] and no_sleep == []


@pytest.mark.parametrize("status,match", [(401, "token"), (402, "credits"), (404, "HTTP 404")])
def test_hf_fails_fast_with_a_clear_message(no_sleep, status, match):
    g = hf(lambda req: httpx.Response(status, text="nope"))
    with pytest.raises(LLMError, match=match):
        g.complete("q")
    assert no_sleep == []


def test_hf_retries_server_errors_then_gives_up(no_sleep):
    g = hf(lambda req: httpx.Response(503, text="busy"), max_retries=3)
    with pytest.raises(LLMError, match="after 3 attempts"):
        g.complete("q")
    assert no_sleep == [2.0, 4.0]


def test_hf_needs_a_token_and_a_gemma_repo_id(monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    with pytest.raises(LLMError, match="HF_TOKEN"):
        GemmaHF(model="google/gemma-4-31B-it")
    with pytest.raises(ValueError):
        GemmaHF(model="meta-llama/Llama-3.1-8B-Instruct", token="t")
    with pytest.raises(LLMError, match="repo id"):
        GemmaHF(model="gemma-4-31b-it", token="t")


def test_backend_selection(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_test")
    monkeypatch.delenv("GEMMA_MODEL", raising=False)
    assert make_llm("hf", cache=False).name == "hf:google/gemma-4-31B-it"
    monkeypatch.delenv("GEMMA_BACKEND", raising=False)
    assert make_llm(cache=False).name.startswith("ollama:")   # default needs no key at all
