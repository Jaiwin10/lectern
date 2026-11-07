"""One small client for four LLM providers, using plain HTTP.

Every call goes through `complete`, which handles rate limiting, retries on
temporary failures (429 / 5xx / timeouts) and turns provider errors into one
readable `LLMError`.
"""

from __future__ import annotations

import json
import re
import threading
import time
from typing import Any, Callable

import httpx

from .config import settings


class LLMError(RuntimeError):
    """A failure the instructor can read and act on (usually: retry)."""


class _Retryable(Exception):
    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


_RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504, 529}
_rate_lock = threading.Lock()
_last_call = [0.0]


def _throttle() -> None:
    if settings.llm_rpm <= 0:
        return
    gap = 60.0 / settings.llm_rpm
    with _rate_lock:
        wait = _last_call[0] + gap - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.monotonic()


def _key() -> str:
    return {
        "gemini": settings.gemini_api_key,
        "openai": settings.openai_api_key,
        "ollama": "local",
    }.get(settings.llm_provider, "")


def is_configured() -> bool:
    return bool(_key())


def describe() -> dict[str, Any]:
    return {
        "provider": settings.llm_provider,
        "model": settings.llm_model,
        "qc_model": settings.qc_model,
        "configured": is_configured(),
    }


def _post(url: str, headers: dict[str, str], payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    try:
        resp = httpx.post(url, headers=headers, json=payload, timeout=timeout)
    except httpx.TimeoutException as exc:
        raise _Retryable("the request timed out") from exc
    except httpx.TransportError as exc:
        raise _Retryable(f"network error: {exc}") from exc
    if resp.status_code in _RETRYABLE_STATUS:
        retry_after = resp.headers.get("retry-after")
        raise _Retryable(
            f"HTTP {resp.status_code}: {_error_text(resp)}",
            float(retry_after) if retry_after and retry_after.isdigit() else None,
        )
    if resp.status_code >= 400:
        raise LLMError(f"{settings.llm_provider} rejected the request (HTTP {resp.status_code}): {_error_text(resp)}")
    return resp.json()


def _error_text(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        err = body.get("error", body)
        if isinstance(err, dict):
            return str(err.get("message") or err)[:300]
        return str(err)[:300]
    except ValueError:
        return resp.text[:300]


def _gemini(system: str, prompt: str, model: str, json_mode: bool, max_tokens: int, temperature: float) -> str:
    config: dict[str, Any] = {"maxOutputTokens": max_tokens}
    # Google advises leaving Gemini 3 at its default temperature.
    if not model.startswith("gemini-3"):
        config["temperature"] = temperature
    if json_mode:
        config["responseMimeType"] = "application/json"
    data = _post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        {"x-goog-api-key": settings.gemini_api_key},
        {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": config,
        },
        timeout=300,
    )
    candidates = data.get("candidates") or []
    if not candidates:
        reason = (data.get("promptFeedback") or {}).get("blockReason", "no reason given")
        raise LLMError(f"Gemini returned no answer ({reason}).")
    cand = candidates[0]
    if cand.get("finishReason") == "MAX_TOKENS":
        raise LLMError("The model's answer was cut off because it hit the length limit. Retry this step.")
    parts = (cand.get("content") or {}).get("parts") or []
    return "".join(p.get("text", "") for p in parts if not p.get("thought"))


def _openai(system: str, prompt: str, model: str, json_mode: bool, max_tokens: int, temperature: float) -> str:
    payload: dict[str, Any] = {
        "model": model,
        "max_completion_tokens": max_tokens,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    data = _post(
        "https://api.openai.com/v1/chat/completions",
        {"Authorization": f"Bearer {settings.openai_api_key}"},
        payload,
        timeout=300,
    )
    choice = (data.get("choices") or [{}])[0]
    if choice.get("finish_reason") == "length":
        raise LLMError("The model's answer was cut off because it hit the length limit. Retry this step.")
    return (choice.get("message") or {}).get("content") or ""


def _ollama(system: str, prompt: str, model: str, json_mode: bool, max_tokens: int, temperature: float) -> str:
    payload: dict[str, Any] = {
        "model": model,
        "stream": False,
        "think": False,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        "options": {"temperature": temperature, "num_ctx": 32768, "num_predict": max_tokens},
    }
    if json_mode:
        payload["format"] = "json"
    data = _post(f"{settings.ollama_url}/api/chat", {}, payload, timeout=1200)
    return (data.get("message") or {}).get("content") or ""


_CALLERS: dict[str, Callable[..., str]] = {
    "gemini": _gemini,
    "openai": _openai,
    "ollama": _ollama,
}


def complete(
    system: str,
    prompt: str,
    *,
    json_mode: bool = False,
    model: str | None = None,
    max_tokens: int = 32000,
    temperature: float = 0.3,
) -> str:
    provider = settings.llm_provider
    caller = _CALLERS.get(provider)
    if caller is None:
        raise LLMError(f"Unknown LLM_PROVIDER '{provider}'. Use gemini, openai or ollama.")
    if not is_configured():
        raise LLMError(f"No API key is set for {provider}. Add it to .env and restart the server.")
    model = model or settings.llm_model
    last: Exception | None = None
    for attempt in range(4):
        _throttle()
        try:
            text = caller(system, prompt, model, json_mode, max_tokens, temperature)
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
            if not text:
                raise LLMError("The model returned an empty answer. Retry this step.")
            return text
        except _Retryable as exc:
            last = exc
            if attempt < 3:
                time.sleep(min(exc.retry_after or 4 * (attempt + 1) ** 2, 45))
    raise LLMError(f"{provider} kept failing after 4 attempts ({last}). Wait a minute and retry.")


def parse_json(text: str) -> dict[str, Any]:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    for candidate in (cleaned, cleaned[cleaned.find("{") : cleaned.rfind("}") + 1]):
        if not candidate:
            continue
        try:
            value = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(value, dict):
            return value
    raise LLMError("The model's answer was not valid JSON. Retry this step.")


def complete_json(system: str, prompt: str, **kwargs: Any) -> dict[str, Any]:
    text = complete(system, prompt, json_mode=True, **kwargs)
    try:
        return parse_json(text)
    except LLMError:
        retry_prompt = prompt + "\n\nYour previous answer was not valid JSON. Reply with one valid JSON object only."
        return parse_json(complete(system, retry_prompt, json_mode=True, **kwargs))
