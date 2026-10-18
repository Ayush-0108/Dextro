"""Gemma model clients.

Interchangeable backends, all serving Google Gemma (open weights):
  * GemmaOllama - Gemma 4 running locally through Ollama (free, fully local; default for reproduction)
  * GemmaHF     - Gemma 4 31B through Hugging Face Inference Providers (OpenAI-compatible router, HF token)
  * GemmaAPI    - Gemma 4 through the Gemini API (not used for this event: the jury ruled out Google AI Studio)
Model inference is kept separate from data storage and query execution (Snowflake).
Responses are cached on disk so evaluation reruns are reproducible and cheap on rate limits.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Callable

import httpx


class LLMError(RuntimeError):
    pass


def require_gemma(model: str) -> str:
    """Hackathon rule: the central AI task must be performed by a Google Gemma model."""
    if "gemma" not in model.lower():
        raise ValueError(f"DataMind must run on a Google Gemma model; got {model!r}")
    return model


class LLM:
    name: str = "llm"

    def complete(self, prompt: str, system: str | None = None, temperature: float = 0.0,
                 thinking: bool = False, json_mode: bool = False, sample: int = 0) -> str:
        raise NotImplementedError


class GemmaAPI(LLM):
    def __init__(self, model: str | None = None, api_key: str | None = None, max_retries: int = 5,
                 timeout_s: float | None = None, client: Any = None):
        self.model = require_gemma(model or os.getenv("GEMMA_MODEL", "gemma-4-31b-it"))
        self.name = f"gemini-api:{self.model}"
        self.max_retries = max_retries
        self.timeout_s = float(timeout_s or os.getenv("GEMMA_TIMEOUT_S", "120"))
        if client is None:
            key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            if not key:
                raise LLMError("set GEMINI_API_KEY (free key from https://aistudio.google.com/apikey)")
            from google import genai
            from google.genai import types
            # without a timeout a stalled request would hang the app indefinitely
            client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=int(self.timeout_s * 1000)))
        self.client = client
        self._fold_system = False       # set if the API rejects system instructions for this model
        self._thinking_config = True    # set to False if the model rejects thinking settings
        # measured, not assumed: free-tier limits are recorded in every eval report (audit C5)
        self.stats = {"requests": 0, "rate_limited": 0, "waited_s": 0.0}

    def complete(self, prompt: str, system: str | None = None, temperature: float = 0.0,
                 thinking: bool = False, json_mode: bool = False, sample: int = 0) -> str:
        from google.genai import types
        delay, last = 2.0, ""
        for attempt in range(self.max_retries):
            # thinking tokens share the output budget, so leave room for the reasoning and the answer
            cfg: dict[str, Any] = {"temperature": temperature, "max_output_tokens": 8192}
            contents = prompt
            if system and self._fold_system:
                contents = f"{system}\n\n{prompt}"
            elif system:
                cfg["system_instruction"] = system
            if self._thinking_config:
                cfg["thinking_config"] = types.ThinkingConfig(thinking_level="high" if thinking else "minimal")
            try:
                self.stats["requests"] += 1
                resp = self.client.models.generate_content(
                    model=self.model, contents=contents, config=types.GenerateContentConfig(**cfg))
                text = resp.text or ""
                if not text.strip():
                    raise LLMError("empty response")
                return text
            except Exception as e:  # rate limits and transient server errors are retried
                last = str(e)
                low = last.lower()
                if system and not self._fold_system and _rejects_system_instruction(low):
                    self._fold_system = True      # Gemma models have rejected system instructions before
                    continue
                if self._thinking_config and "thinking" in low:
                    self._thinking_config = False
                    continue
                if not any(s in low for s in _RETRYABLE) or attempt == self.max_retries - 1:
                    raise LLMError(f"Gemma API call failed: {last[:300]}") from e
                wait = min(60.0, max(delay, _retry_delay(last)))
                if "429" in low or "resource_exhausted" in low:
                    self.stats["rate_limited"] += 1
                self.stats["waited_s"] = round(self.stats["waited_s"] + wait, 1)
                time.sleep(wait)
                delay *= 2
        raise LLMError(f"Gemma API call failed after {self.max_retries} attempts: {last[:300]}")


_RETRYABLE = ("429", "resource_exhausted", "500", "502", "503", "504", "unavailable", "deadline",
              "empty response", "timed out", "timeout", "temporarily", "connection reset")


def _rejects_system_instruction(low: str) -> bool:
    return "developer instruction" in low or (
        ("system instruction" in low or "system_instruction" in low)
        and any(s in low for s in ("not enabled", "not supported", "unsupported", "invalid")))


def _retry_delay(message: str) -> float:
    """Seconds the API asked us to wait (Gemini puts 'retryDelay': '17s' in 429 errors), else 0."""
    m = re.search(r"retry[_ ]?delay['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)s", message, re.I) or \
        re.search(r"retry in (\d+(?:\.\d+)?)\s*s", message, re.I)
    return float(m.group(1)) if m else 0.0


class GemmaHF(LLM):
    """Gemma served by Hugging Face Inference Providers through the OpenAI-compatible router.

    The model id is the Hugging Face repo (default google/gemma-4-31B-it). HF_PROVIDER pins a provider
    (e.g. novita, deepinfra); without it Hugging Face picks one. Needs HF_TOKEN with the
    "Make calls to Inference Providers" permission; usage is billed to that account's credits.
    """

    def __init__(self, model: str | None = None, token: str | None = None, provider: str | None = None,
                 max_retries: int = 5, timeout_s: float | None = None, transport: httpx.BaseTransport | None = None):
        self.model = require_gemma(model or os.getenv("GEMMA_MODEL", "google/gemma-4-31B-it"))
        if "/" not in self.model:
            raise LLMError(f"GEMMA_MODEL for the hf backend is a Hugging Face repo id like google/gemma-4-31B-it, "
                           f"got {self.model!r}")
        provider = provider or os.getenv("HF_PROVIDER")
        self.route = f"{self.model}:{provider}" if provider else self.model
        self.name = f"hf:{self.route}"
        tok = token or os.getenv("HF_TOKEN")
        if not tok:
            raise LLMError("set HF_TOKEN (https://huggingface.co/settings/tokens, permission "
                           "'Make calls to Inference Providers')")
        self.base = os.getenv("HF_BASE_URL", "https://router.huggingface.co/v1").rstrip("/")
        self.max_retries = max_retries
        timeout = float(timeout_s or os.getenv("GEMMA_TIMEOUT_S", "120"))
        self.http = httpx.Client(timeout=timeout, transport=transport,
                                 headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
        self._json_mode = True   # set to False if the provider rejects response_format
        self.stats = {"requests": 0, "rate_limited": 0, "waited_s": 0.0}

    def complete(self, prompt: str, system: str | None = None, temperature: float = 0.0,
                 thinking: bool = False, json_mode: bool = False, sample: int = 0) -> str:
        messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
        delay, last = 2.0, ""
        for attempt in range(self.max_retries):
            body: dict[str, Any] = {"model": self.route, "messages": messages, "temperature": temperature,
                                    "max_tokens": 8192}
            if json_mode and self._json_mode:
                body["response_format"] = {"type": "json_object"}
            self.stats["requests"] += 1
            try:
                r = self.http.post(f"{self.base}/chat/completions", json=body)
            except httpx.HTTPError as e:   # timeouts and dropped connections are retried
                last, status, retry_after = f"{type(e).__name__}: {e}", 0, 0.0
            else:
                if r.status_code < 400:
                    try:
                        text = r.json()["choices"][0]["message"].get("content") or ""
                    except (ValueError, KeyError, IndexError, TypeError):
                        text = ""
                    if text.strip():
                        return text
                    last, status, retry_after = "empty response", 0, 0.0
                else:
                    last, status = f"HTTP {r.status_code}: {r.text[:300]}", r.status_code
                    try:
                        retry_after = float(r.headers.get("retry-after", 0))
                    except ValueError:
                        retry_after = 0.0
                    if status == 400 and "response_format" in body and "response_format" in r.text.lower():
                        self._json_mode = False   # provider without JSON mode: the prompt still asks for JSON
                        continue
                    if status in (401, 403):
                        raise LLMError(f"Hugging Face rejected the token ({status}); check HF_TOKEN and its "
                                       "Inference Providers permission")
                    if status == 402:
                        raise LLMError("Hugging Face Inference Providers credits are exhausted (402); add credits "
                                       "or switch GEMMA_BACKEND=ollama")
                    if status not in (408, 409, 429) and status < 500:
                        raise LLMError(f"Gemma (Hugging Face) call failed: {last}")
            if attempt == self.max_retries - 1:
                break
            wait = min(60.0, max(delay, retry_after))
            if status == 429:
                self.stats["rate_limited"] += 1
            self.stats["waited_s"] = round(self.stats["waited_s"] + wait, 1)
            time.sleep(wait)
            delay *= 2
        raise LLMError(f"Gemma (Hugging Face) call failed after {self.max_retries} attempts: {last[:300]}")


class GemmaOllama(LLM):
    def __init__(self, model: str | None = None, host: str | None = None, timeout: float = 300,
                 transport: httpx.BaseTransport | None = None):
        self.model = require_gemma(model or os.getenv("GEMMA_MODEL", "gemma4:12b"))
        self.host = (host or os.getenv("OLLAMA_HOST", "http://localhost:11434")).rstrip("/")
        self.name = f"ollama:{self.model}"
        self.timeout = float(os.getenv("GEMMA_TIMEOUT_S", timeout))
        self.http = httpx.Client(timeout=self.timeout, transport=transport)
        self.stats = {"requests": 0, "rate_limited": 0, "waited_s": 0.0}

    def complete(self, prompt: str, system: str | None = None, temperature: float = 0.0,
                 thinking: bool = False, json_mode: bool = False, sample: int = 0) -> str:
        messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
        # Gemma 4 on Ollama thinks unless told not to, and nothing else bounds the reply: an uncapped call measured
        # 2,892 tokens / 233 s for a one-line plan. So `think` is always explicit and the reply length is capped.
        cap = int(os.getenv("GEMMA_MAX_TOKENS", "4096" if thinking else "1536"))
        body: dict[str, Any] = {"model": self.model, "messages": messages, "stream": False, "think": bool(thinking),
                                "options": {"temperature": temperature, "seed": 7 + sample, "num_ctx": 16384,
                                            "num_predict": cap}}
        if json_mode:
            body["format"] = "json"
        try:
            self.stats["requests"] += 1
            r = self.http.post(f"{self.host}/api/chat", json=body)
            if r.status_code >= 400 and "think" in r.text.lower():   # model without a thinking switch
                body.pop("think")
                r = self.http.post(f"{self.host}/api/chat", json=body)
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPError as e:
            raise LLMError(f"Ollama call failed ({self.host}): {e}") from e
        text = (data.get("message") or {}).get("content") or ""
        if not text.strip():
            why = "the reply hit the length cap" if data.get("done_reason") == "length" else "empty reply"
            raise LLMError(f"Ollama returned no answer ({why}); raise GEMMA_MAX_TOKENS or set GEMMA_THINKING=0")
        return text


class CachedLLM(LLM):
    """Disk cache keyed by the full request, so identical prompts are never re-sent."""

    def __init__(self, inner: LLM, cache_dir: str | Path = ".cache/llm", enabled: bool = True):
        self.inner = inner
        self.name = inner.name
        self.dir = Path(cache_dir)
        self.enabled = enabled
        self.hits = 0
        self.calls = 0

    @property
    def stats(self) -> dict[str, Any]:
        return {"cache_hits": self.hits, "model_calls": self.calls, **getattr(self.inner, "stats", {})}

    def complete(self, prompt: str, system: str | None = None, temperature: float = 0.0,
                 thinking: bool = False, json_mode: bool = False, sample: int = 0) -> str:
        key = hashlib.sha256(json.dumps([self.inner.name, system, prompt, temperature, thinking, json_mode, sample])
                             .encode()).hexdigest()
        path = self.dir / key[:2] / f"{key}.json"
        if self.enabled and path.exists():
            self.hits += 1
            return json.loads(path.read_text(encoding="utf-8"))["text"]
        self.calls += 1
        text = self.inner.complete(prompt, system=system, temperature=temperature, thinking=thinking,
                                   json_mode=json_mode, sample=sample)
        if self.enabled:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"model": self.inner.name, "text": text}), encoding="utf-8")
        return text


class ScriptedLLM(LLM):
    """Deterministic stand-in for tests: a function maps (task, prompt) to a reply."""

    def __init__(self, handler: Callable[[str, str, dict[str, Any]], str], name: str = "gemma-scripted"):
        self.handler = handler
        self.name = name
        self.log: list[tuple[str, str]] = []

    def complete(self, prompt: str, system: str | None = None, temperature: float = 0.0,
                 thinking: bool = False, json_mode: bool = False, sample: int = 0) -> str:
        m = re.search(r"\[task:(\w+)\]", system or "") or re.search(r"\[task:(\w+)\]", prompt)
        task = m.group(1) if m else "unknown"
        self.log.append((task, prompt))
        return self.handler(task, prompt, {"temperature": temperature, "sample": sample})


def make_llm(backend: str | None = None, model: str | None = None, cache: bool = True) -> LLM:
    backend = (backend or os.getenv("GEMMA_BACKEND", "ollama")).lower()
    if backend in ("hf", "huggingface", "hugging-face"):
        inner: LLM = GemmaHF(model)
    elif backend in ("api", "gemini", "gemini-api"):
        inner = GemmaAPI(model)
    elif backend == "ollama":
        inner = GemmaOllama(model)
    else:
        raise ValueError(f"unknown GEMMA_BACKEND {backend!r} (use 'ollama' or 'hf')")
    return CachedLLM(inner, os.getenv("DATAMIND_CACHE_DIR", ".cache/llm"), enabled=cache)


# ---------------------------------------------------------------------------- JSON parsing
_FENCED_JSON = re.compile(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", re.S)


def parse_json(text: str) -> Any:
    """Extract the first JSON object from a model reply (tolerates fences and chatter)."""
    text = text.strip()
    for candidate in _candidates(text):
        for fix in (lambda s: s, lambda s: re.sub(r",\s*([}\]])", r"\1", s)):
            try:
                return json.loads(fix(candidate))
            except json.JSONDecodeError:
                continue
    raise LLMError(f"model did not return valid JSON: {text[:200]!r}")


def _candidates(text: str):
    yield text
    for m in _FENCED_JSON.finditer(text):
        yield m.group(1)
    start = text.find("{")
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    yield text[start:i + 1]
                    break
        start = text.find("{", start + 1)
