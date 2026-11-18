"""Optional AI provider calls for the native Prism app.

The desktop app talks to the selected provider directly. API keys are used
only for the request the user explicitly starts and are never written to logs.
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

TIMEOUT = 120

PROVIDERS: dict[str, dict[str, str]] = {
    "openai": {
        "name": "OpenAI / compatible",
        "base": "https://api.openai.com/v1",
        "model": "gpt-6.1-terra",
    },
    "deepseek": {
        "name": "DeepSeek",
        "base": "https://api.deepseek.com/v1",
        "model": "deepseek-flash",
    },
    "grok": {
        "name": "Grok (xAI)",
        "base": "https://api.x.ai/v1",
        "model": "grok-4.7",
    },
    "anthropic": {
        "name": "Anthropic",
        "base": "https://api.anthropic.com",
        "model": "claude-fable-5-2",
    },
    "gemini": {
        "name": "Google Gemini",
        "base": "https://generativelanguage.googleapis.com",
        "model": "gemini-4-hydrogen",
    },
}


@dataclass
class AISettings:
    provider: str = "openai"
    base_url: str = PROVIDERS["openai"]["base"]
    model: str = PROVIDERS["openai"]["model"]
    api_key: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.base_url.strip() and self.model.strip())

    def provider_name(self) -> str:
        return PROVIDERS.get(self.provider, {}).get("name", self.provider)


class AIError(Exception):
    pass


def _json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _endpoint(base: str, suffix: str) -> str:
    clean = base.rstrip("/")
    if clean.endswith("/" + suffix):
        return clean
    if clean.endswith("/v1") and suffix.startswith("v1/"):
        return clean + "/" + suffix[3:]
    return clean + "/" + suffix


def _openai_endpoint(base: str) -> str:
    clean = base.rstrip("/")
    if clean.endswith("/chat/completions"):
        return clean
    parsed = urllib.parse.urlsplit(clean)
    if not parsed.path or parsed.path == "/":
        suffix = "/v1/chat/completions" if parsed.hostname == "api.openai.com" else "/chat/completions"
        return clean + suffix
    return clean + "/chat/completions"


def _post(endpoint: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        endpoint,
        data=_json_bytes(body),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            raw = response.read().decode("utf-8", "replace")
            status = response.status
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8", "replace")
        status = error.code
    except (urllib.error.URLError, socket.timeout, TimeoutError) as error:
        raise AIError("The provider could not be reached. Check the base URL and network.") from error
    try:
        data = json.loads(raw) if raw else {}
    except json.JSONDecodeError as error:
        raise AIError(f"The provider returned HTTP {status} with a non-JSON response.") from error
    if status < 200 or status >= 300:
        message = ""
        if isinstance(data, dict):
            error = data.get("error")
            if isinstance(error, str):
                message = error
            elif isinstance(error, dict):
                message = str(error.get("message", ""))
            message = message or str(data.get("message", ""))
        raise AIError(message or f"The provider returned HTTP {status}.")
    return data if isinstance(data, dict) else {}


def _check(settings: AISettings) -> None:
    if settings.provider not in PROVIDERS:
        raise AIError("Choose a supported AI provider.")
    if not settings.model.strip():
        raise AIError("A model name is required.")
    parsed = urllib.parse.urlsplit(settings.base_url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise AIError("The base URL must start with http:// or https://.")


def _openai(settings: AISettings, system: str, messages: list[dict[str, str]], max_tokens: int) -> str:
    body = {
        "model": settings.model.strip(),
        "messages": ([{"role": "system", "content": system}] if system else []) + messages,
        "temperature": 0.3,
        "max_tokens": max_tokens,
    }
    headers = {"Authorization": f"Bearer {settings.api_key}"} if settings.api_key else {}
    data = _post(_openai_endpoint(settings.base_url), headers, body)
    choices = data.get("choices")
    content = choices[0].get("message", {}).get("content") if isinstance(choices, list) and choices else ""
    if isinstance(content, list):
        content = "".join(part if isinstance(part, str) else part.get("text", "") for part in content)
    if not isinstance(content, str) or not content.strip():
        raise AIError("The provider returned an empty response.")
    return content.strip()


def _anthropic(settings: AISettings, system: str, messages: list[dict[str, str]], max_tokens: int) -> str:
    if not settings.api_key:
        raise AIError("Anthropic requires an API key.")
    body = {
        "model": settings.model.strip(),
        "max_tokens": max_tokens,
        "temperature": 0.3,
        "messages": messages,
    }
    if system:
        body["system"] = system
    data = _post(
        _endpoint(settings.base_url, "v1/messages"),
        {"x-api-key": settings.api_key, "anthropic-version": "2023-06-01"},
        body,
    )
    parts = data.get("content")
    text = "\n".join(
        str(part.get("text", "")) for part in parts
        if isinstance(parts, list) and isinstance(part, dict) and part.get("type") == "text"
    ) if isinstance(parts, list) else ""
    if not text.strip():
        raise AIError("Anthropic returned an empty response.")
    return text.strip()


def _gemini(settings: AISettings, system: str, messages: list[dict[str, str]], max_tokens: int) -> str:
    if not settings.api_key:
        raise AIError("Google Gemini requires an API key.")
    base = settings.base_url.rstrip("/")
    model = urllib.parse.quote(settings.model.strip(), safe="")
    endpoint = base if ":generateContent" in base else (
        f"{base}/v1beta/models/{model}:generateContent?key={urllib.parse.quote(settings.api_key, safe='')}"
    )
    body = {
        "contents": [
            {"role": "model" if message["role"] == "assistant" else "user",
             "parts": [{"text": message["content"]}]}
            for message in messages
        ],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": max_tokens},
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    data = _post(endpoint, {}, body)
    candidates = data.get("candidates")
    candidate = candidates[0] if isinstance(candidates, list) and candidates else {}
    content = candidate.get("content", {}) if isinstance(candidate, dict) else {}
    parts = content.get("parts", []) if isinstance(content, dict) else []
    text = "".join(
        str(part.get("text", "")) for part in parts
        if isinstance(part, dict) and not part.get("thought")
    ) if isinstance(parts, list) else ""
    if not text.strip():
        raise AIError("Gemini returned an empty response.")
    return text.strip()


def complete(settings: AISettings, system: str, messages: list[dict[str, str]], max_tokens: int = 1800) -> str:
    _check(settings)
    if settings.provider == "anthropic":
        return _anthropic(settings, system, messages, max_tokens)
    if settings.provider == "gemini":
        return _gemini(settings, system, messages, max_tokens)
    return _openai(settings, system, messages, max_tokens)


def test_connection(settings: AISettings) -> str:
    return complete(
        settings,
        "You are a connectivity check.",
        [{"role": "user", "content": "Reply with exactly PRISM_OK and nothing else."}],
        max_tokens=20,
    )
