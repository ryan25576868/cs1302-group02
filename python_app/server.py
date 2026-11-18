"""Local-only HTTP server for the Prism desktop application.

Serves the static Prism frontend and provides the same stateless AI proxy
contract as the original Node server. Standard library only, so it can be
bundled with PyInstaller without a runtime dependency on Python or Node.
"""

from __future__ import annotations

import json
import mimetypes
import socket
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from python_app.analysis import analyze_python

APP_VERSION = "1.0.0"
AI_TIMEOUT_SECONDS = 120
MAX_BODY_BYTES = 2 * 1024 * 1024
PROVIDERS = {"openai", "deepseek", "grok", "anthropic", "gemini"}
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; "
        "base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    ),
}


class ProviderError(Exception):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def _json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _string(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _limit(value: Any, maximum: int) -> str:
    return str(value or "")[:maximum]


def _clamp(value: Any, low: float, high: float, fallback: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return min(high, max(low, number))


def _openai_endpoint(base_url: str) -> str:
    clean = base_url.rstrip("/")
    if clean.endswith("/chat/completions"):
        return clean
    parsed = urllib.parse.urlsplit(clean)
    if not parsed.path or parsed.path == "/":
        suffix = "/v1/chat/completions" if parsed.hostname == "api.openai.com" else "/chat/completions"
        return clean + suffix
    return clean + "/chat/completions"


def _append_path(base_url: str, suffix: str) -> str:
    clean = base_url.rstrip("/")
    if clean.endswith("/" + suffix):
        return clean
    if clean.endswith("/v1") and suffix.startswith("v1/"):
        return clean + "/" + suffix[3:]
    return clean + "/" + suffix


def _extract_error(data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    error = data.get("error")
    if isinstance(error, str):
        return error
    if isinstance(error, dict) and isinstance(error.get("message"), str):
        return error["message"]
    if isinstance(data.get("message"), str):
        return data["message"]
    for key in ("errors",):
        values = data.get(key)
        if isinstance(values, list) and values and isinstance(values[0], dict):
            if isinstance(values[0].get("message"), str):
                return values[0]["message"]
    if isinstance(error, dict) and isinstance(error.get("errors"), list):
        values = error["errors"]
        if values and isinstance(values[0], dict) and isinstance(values[0].get("message"), str):
            return values[0]["message"]
    return ""


def _fetch_provider(endpoint: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        endpoint,
        data=_json_bytes(body),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=AI_TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8", errors="replace")
            status = response.status
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8", errors="replace")
        status = error.code
    except (urllib.error.URLError, socket.timeout, TimeoutError) as error:
        reason = getattr(error, "reason", error)
        raise ProviderError(
            f"Could not reach the provider at {urllib.parse.urlsplit(endpoint).netloc or 'the configured endpoint'}. "
            "Check the base URL and your network connection."
        ) from error
    try:
        data = json.loads(raw) if raw else {}
    except json.JSONDecodeError as error:
        message = "The provider returned a response that was not valid JSON."
        if status >= 400:
            message = f"The provider returned HTTP {status} with a non-JSON error body."
        raise ProviderError(message, status if 400 <= status < 600 else 502) from error
    if status < 200 or status >= 300:
        message = _extract_error(data) or f"The provider returned HTTP {status}."
        raise ProviderError(message, status)
    return data if isinstance(data, dict) else {}


def _call_openai(provider: str, base_url: str, api_key: str, model: str, system: str,
                 messages: list[dict[str, str]], temperature: float, max_tokens: int) -> dict[str, Any]:
    endpoint = _openai_endpoint(base_url)
    gpt6 = provider == "openai" and model.lower().startswith("gpt-6")
    request_messages = []
    if system:
        request_messages.append({"role": "developer" if gpt6 else "system", "content": system})
    request_messages.extend(messages)
    body: dict[str, Any] = {"model": model, "messages": request_messages, "stream": False}
    if gpt6:
        body["max_completion_tokens"] = max_tokens
    else:
        body["temperature"] = temperature
        body["max_tokens"] = max_tokens
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    data = _fetch_provider(endpoint, headers, body)
    choices = data.get("choices") if isinstance(data.get("choices"), list) else []
    content = choices[0].get("message", {}).get("content") if choices and isinstance(choices[0], dict) else ""
    if isinstance(content, list):
        content = "".join(part if isinstance(part, str) else part.get("text", "") for part in content)
    if not isinstance(content, str):
        content = choices[0].get("text", "") if choices and isinstance(choices[0], dict) else ""
    text = str(content or "").strip()
    if not text:
        raise ProviderError("The provider returned an empty response.")
    return {"text": text, "usage": data.get("usage")}


def _call_anthropic(base_url: str, api_key: str, model: str, system: str,
                    messages: list[dict[str, str]], temperature: float, max_tokens: int) -> dict[str, Any]:
    if not api_key:
        raise ProviderError("Anthropic requires an API key.", 400)
    body: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "assistant" if message["role"] == "assistant" else "user", "content": message["content"]}
            for message in messages
        ],
    }
    if system:
        body["system"] = system
    if not model.lower().startswith(("claude-fable-", "claude-mythos-")):
        body["temperature"] = temperature
    data = _fetch_provider(
        _append_path(base_url, "v1/messages"),
        {"x-api-key": api_key, "anthropic-version": "2023-06-01"},
        body,
    )
    parts = data.get("content") if isinstance(data.get("content"), list) else []
    text = "\n".join(
        str(part.get("text", "")) for part in parts
        if isinstance(part, dict) and part.get("type") == "text"
    ).strip()
    if not text:
        raise ProviderError("Anthropic returned an empty response.")
    return {"text": text, "usage": data.get("usage")}


def _call_gemini(base_url: str, api_key: str, model: str, system: str,
                 messages: list[dict[str, str]], temperature: float, max_tokens: int) -> dict[str, Any]:
    if not api_key:
        raise ProviderError("Google Gemini requires an API key.", 400)
    base = base_url.rstrip("/")
    endpoint = base if ":generateContent" in base else (
        f"{base}/v1beta/models/{urllib.parse.quote(model, safe='')}:generateContent"
        f"?key={urllib.parse.quote(api_key, safe='')}"
    )
    body: dict[str, Any] = {
        "contents": [
            {"role": "model" if message["role"] == "assistant" else "user",
             "parts": [{"text": message["content"]}]}
            for message in messages
        ],
        "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    data = _fetch_provider(endpoint, {}, body)
    candidates = data.get("candidates") if isinstance(data.get("candidates"), list) else []
    candidate = candidates[0] if candidates and isinstance(candidates[0], dict) else {}
    content = candidate.get("content") if isinstance(candidate.get("content"), dict) else {}
    parts = content.get("parts") if isinstance(content.get("parts"), list) else []
    text = "".join(
        str(part.get("text", "")) for part in parts
        if isinstance(part, dict) and not part.get("thought")
    ).strip()
    if not text:
        reason = data.get("promptFeedback", {}).get("blockReason") or candidate.get("finishReason", "")
        raise ProviderError(f"Gemini blocked the request: {reason}." if reason else "Gemini returned an empty response.")
    return {"text": text, "usage": data.get("usageMetadata")}


def _redact(text: str, secret: str) -> str:
    safe = str(text or "")
    if secret:
        safe = safe.replace(secret, "[redacted]")
    return safe[:1000]


def handle_ai(payload: dict[str, Any]) -> dict[str, Any]:
    provider = _string(payload.get("provider")) or "openai"
    if provider not in PROVIDERS:
        raise ProviderError("Unsupported AI provider. Choose openai, deepseek, grok, anthropic, or gemini.", 400)
    model = _string(payload.get("model")).strip()
    if not model:
        raise ProviderError("A model name is required.", 400)
    base_url = _string(payload.get("baseUrl")).strip()
    if not base_url:
        raise ProviderError("A provider base URL is required.", 400)
    parsed = urllib.parse.urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ProviderError("The provider base URL must be a valid http:// or https:// URL.", 400)
    raw_messages = payload.get("messages")
    messages = []
    if isinstance(raw_messages, list):
        for message in raw_messages[-20:]:
            if isinstance(message, dict) and message.get("role") in {"user", "assistant"}:
                content = message.get("content")
                if isinstance(content, str):
                    messages.append({"role": message["role"], "content": content[:60_000]})
    if not messages:
        raise ProviderError("At least one message is required.", 400)
    system = _limit(_string(payload.get("system")), 30_000)
    temperature = _clamp(payload.get("temperature"), 0, 1, 0.3)
    max_tokens = round(_clamp(payload.get("maxTokens"), 64, 8000, 2600))
    started = time.monotonic()
    try:
        if provider == "anthropic":
            result = _call_anthropic(base_url, _string(payload.get("apiKey")), model, system, messages, temperature, max_tokens)
        elif provider == "gemini":
            result = _call_gemini(base_url, _string(payload.get("apiKey")), model, system, messages, temperature, max_tokens)
        else:
            result = _call_openai(provider, base_url, _string(payload.get("apiKey")), model, system, messages, temperature, max_tokens)
    except ProviderError:
        raise
    except Exception as error:  # pragma: no cover - defensive network boundary
        raise ProviderError(_redact(str(error), _string(payload.get("apiKey")))) from error
    return {
        "text": result["text"],
        "provider": provider,
        "model": model,
        "usage": result.get("usage"),
        "elapsedMs": int((time.monotonic() - started) * 1000),
    }


class PrismHTTPRequestHandler(BaseHTTPRequestHandler):
    server_version = "PrismPython/1.0"
    root: Path

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[prism] {self.address_string()} {fmt % args}")

    def do_HEAD(self) -> None:  # noqa: N802
        self._handle(head=True)

    def do_GET(self) -> None:  # noqa: N802
        self._handle(head=False)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path not in {"/api/ai", "/api/analyze-python"}:
            self._json(HTTPStatus.NOT_FOUND, {"error": "Unknown API route."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                raise ProviderError("Request body is required.", 400)
            if length > MAX_BODY_BYTES:
                raise ProviderError("Request body is too large.", 413)
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ProviderError("Request body must be valid JSON.", 400) from error
            if not isinstance(payload, dict):
                raise ProviderError("Request body must be a JSON object.", 400)
            if parsed.path == "/api/analyze-python":
                source = payload.get("source")
                if not isinstance(source, str) or not source.strip():
                    raise ProviderError("A Python source string is required.", 400)
                if len(source) > 60_000:
                    raise ProviderError("Python source must stay under 60,000 characters.", 413)
                try:
                    result = analyze_python(source)
                except ValueError as error:
                    raise ProviderError(str(error), 400) from error
                self._json(HTTPStatus.OK, result)
            else:
                self._json(HTTPStatus.OK, handle_ai(payload))
        except ProviderError as error:
            self._json(error.status, {"error": str(error)})
        except Exception as error:  # pragma: no cover
            print(f"[prism] request failed: {error}")
            self._json(HTTPStatus.BAD_GATEWAY, {"error": "The local Python service could not complete this request."})

    def _handle(self, *, head: bool) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path == "/api/health":
            self._json(HTTPStatus.OK, {"ok": True, "app": "prism", "version": APP_VERSION, "proxy": True}, head=head)
            return
        if parsed.path.startswith("/api/"):
            self._json(HTTPStatus.NOT_FOUND, {"error": "Unknown API route."}, head=head)
            return
        if self.command not in {"GET", "HEAD"}:
            self.send_response(HTTPStatus.METHOD_NOT_ALLOWED)
            self.send_header("Allow", "GET, HEAD")
            self.end_headers()
            return
        self._serve_static(parsed.path, head=head)

    def _serve_static(self, raw_path: str, *, head: bool) -> None:
        try:
            decoded = urllib.parse.unquote(raw_path, errors="strict")
        except UnicodeDecodeError:
            self.send_response(HTTPStatus.BAD_REQUEST)
            self.end_headers()
            return
        relative = "index.html" if decoded == "/" else decoded.lstrip("/")
        root = self.root.resolve()
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            self.send_response(HTTPStatus.FORBIDDEN)
            self.end_headers()
            return
        if candidate.is_dir():
            candidate = candidate / "index.html"
        if not candidate.exists() and not Path(relative).suffix:
            candidate = root / "index.html"
        if not candidate.is_file():
            self.send_response(HTTPStatus.NOT_FOUND)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            if not head:
                self.wfile.write(b"Not found")
            return
        try:
            body = candidate.read_bytes()
        except OSError:
            self.send_response(HTTPStatus.NOT_FOUND)
            self.end_headers()
            return
        content_type = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {"application/javascript", "application/json"}:
            content_type += "; charset=utf-8"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in SECURITY_HEADERS.items():
            self.send_header(key, value)
        self.end_headers()
        if not head:
            self.wfile.write(body)

    def _json(self, status: int, payload: Any, *, head: bool = False) -> None:
        body = _json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if not head:
            self.wfile.write(body)


def create_server(root: Path, host: str = "127.0.0.1", port: int = 0) -> ThreadingHTTPServer:
    root = Path(root).resolve()
    handler = type("PrismHandler", (PrismHTTPRequestHandler,), {"root": root})
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    return server


def start_server(root: Path, host: str = "127.0.0.1", port: int = 0) -> tuple[ThreadingHTTPServer, str]:
    server = create_server(root, host, port)
    thread = threading.Thread(target=server.serve_forever, name="prism-http", daemon=True)
    thread.start()
    actual_port = server.server_address[1]
    return server, f"http://{host}:{actual_port}"


def stop_server(server: ThreadingHTTPServer) -> None:
    server.shutdown()
    server.server_close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run the Prism local server.")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument("--port", type=int, default=4173)
    args = parser.parse_args()
    srv, url = start_server(Path(args.root), port=args.port)
    print(f"Prism local app: {url}")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        stop_server(srv)
