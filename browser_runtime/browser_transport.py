"""Bounded, nonstreaming HTTPX bridge for an initialized Pyodide worker.

No sockets, proxy fallback, configurable provider URL, or fixture mode exists here.
The companion worker independently checks the same policy before calling fetch.
"""

from __future__ import annotations

import json
import math
from typing import Any

import httpx

MAX_BYTES = 1024 * 1024
CONTROL_BYTES = 20
MAX_TIMEOUT_MS = 30_000
MODELS = {
    "openai": frozenset({"gpt-4o-mini", "gpt-4.1-mini"}),
    "anthropic": frozenset({"claude-sonnet-5", "claude-haiku-4-5"}),
    "gemini": frozenset({"gemini-3.5-flash", "gemini-3.5-flash-lite"}),
}
ENDPOINTS = {
    "https://api.openai.com/v1/chat/completions": "openai",
    "https://api.anthropic.com/v1/messages": "anthropic",
    **{
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent": "gemini"
        for model in MODELS["gemini"]
    },
}
_worker: Any = None
_active = False
_sequence = 0


def _bind_worker(worker: Any) -> None:
    global _worker
    if _worker is not None:
        raise RuntimeError("Browser provider worker is already initialized.")
    _worker = worker


def runtime_ready() -> bool:
    return _worker is not None


def shutdown_browser_provider_runtime() -> None:
    """Terminate the dedicated worker; reinitialization requires an async handshake."""
    global _worker
    worker, _worker = _worker, None
    if worker is not None:
        worker.terminate()


def _validated_request(request: httpx.Request) -> tuple[str, str, dict[str, str]]:
    url = str(request.url)
    provider = ENDPOINTS.get(url)
    if request.method != "POST" or provider is None:
        raise httpx.UnsupportedProtocol("Provider endpoint is not allowed.", request=request)
    # Read incrementally so a streaming upload cannot allocate an unbounded body.
    chunks: list[bytes] = []
    size = 0
    for chunk in request.stream:
        size += len(chunk)
        if size > MAX_BYTES:
            raise httpx.TransportError("Provider request exceeds the size limit.", request=request)
        chunks.append(chunk)
    try:
        body = b"".join(chunks).decode("utf-8")
        payload = json.loads(body)
    except (ValueError, UnicodeError):
        raise httpx.TransportError("Provider request must be valid JSON.", request=request) from None
    if not isinstance(payload, dict) or payload.get("stream", False) is not False:
        raise httpx.TransportError("Only nonstreaming provider requests are supported.", request=request)
    if provider != "gemini" and payload.get("model") not in MODELS[provider]:
        raise httpx.TransportError("Provider model is not allowed.", request=request)
    # Browser fetch supplies Host/Content-Length. No SDK telemetry, cookies,
    # organization/project, forwarded credentials, or arbitrary headers survive.
    key_header = {"openai": "authorization", "anthropic": "x-api-key", "gemini": "x-goog-api-key"}[provider]
    key = request.headers.get(key_header, "")
    if (
        not key
        or len(key) > 8192
        or any(ord(char) < 32 or ord(char) > 126 for char in key)
        or (provider == "openai" and (not key.startswith("Bearer ") or not key[7:].strip()))
    ):
        raise httpx.TransportError("A valid provider credential header is required.", request=request)
    headers = {"content-type": "application/json", "accept": "application/json", key_header: key}
    if provider == "anthropic":
        headers.update({"anthropic-version": "2023-06-01", "anthropic-dangerous-direct-browser-access": "true"})
    return url, body, headers


def _timeout_ms(request: httpx.Request) -> int:
    values = request.extensions.get("timeout", {})
    read = values.get("read") if isinstance(values, dict) else None
    if read is None:
        return MAX_TIMEOUT_MS
    if isinstance(read, bool) or not isinstance(read, int | float) or not math.isfinite(read) or read <= 0:
        raise httpx.ReadTimeout("Provider request has no positive timeout budget.", request=request)
    return min(MAX_TIMEOUT_MS, max(1, int(read * 1000)))


class BrowserFetchTransport(httpx.BaseTransport):
    """One synchronous request at a time; the bootstrap owns the shared worker."""

    def __init__(self) -> None:
        self.closed = False

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        global _active, _sequence
        if self.closed:
            raise httpx.TransportError("Browser transport is closed.", request=request)
        if _worker is None:
            raise httpx.TransportError("Browser provider runtime is not ready.", request=request)
        if _active:
            raise httpx.TransportError("A browser provider request is already active.", request=request)
        url, body, headers = _validated_request(request)
        timeout_ms = _timeout_ms(request)
        import js
        from pyodide.ffi import to_js

        _sequence += 1
        request_id = _sequence
        buffer = js.SharedArrayBuffer.new(MAX_BYTES + CONTROL_BYTES)
        control = js.Int32Array.new(buffer, 0, 5)
        data = js.Uint8Array.new(buffer, CONTROL_BYTES)
        worker = _worker
        _active = True
        completed = False
        try:
            worker.postMessage(
                to_js(
                    {
                        "type": "request",
                        "id": request_id,
                        "buffer": buffer,
                        "url": url,
                        "method": "POST",
                        "headers": headers,
                        "body": body,
                        "timeoutMs": timeout_ms,
                    },
                    dict_converter=js.Object.fromEntries,
                )
            )
            # A worker failure cannot leave Python waiting indefinitely. A timed
            # out bridge is terminated before another request can start.
            wait = js.Atomics.wait(control, 0, 0, timeout_ms + 1000)
            if wait == "timed-out":
                shutdown_browser_provider_runtime()
                raise httpx.ReadTimeout("Browser provider worker timed out; reload is required.", request=request)
            completed = True
            state = int(control[0])
            if state == -2:
                raise httpx.ReadTimeout("Browser provider request timed out.", request=request)
            if state != 1:
                message = {
                    -3: "Provider response exceeds the size limit.",
                    -4: "Provider request failed endpoint or request validation.",
                    -5: "Browser provider request was cancelled.",
                    -6: "A browser provider request is already active.",
                    -7: "Provider returned an invalid response format.",
                }.get(state, "Provider connection failed browser network, CORS, or redirect checks.")
                raise httpx.ConnectError(message, request=request)
            length, status, retry_after = (int(control[index]) for index in (1, 2, 3))
            if not 0 <= length <= MAX_BYTES or not 100 <= status <= 599:
                raise httpx.TransportError("Browser provider worker returned an invalid result.", request=request)
            response_headers = {"content-type": "application/json"}
            if 0 <= retry_after <= 600:
                response_headers["retry-after"] = str(retry_after)
            elif retry_after == -2:
                # Safe sentinel, not the raw provider header. The common
                # provider adapter suppresses waits outside its accepted range.
                response_headers["retry-after"] = "601"
            content = bytes(data.slice(0, length).to_py())
            return httpx.Response(status, headers=response_headers, content=content, request=request)
        except (httpx.HTTPError, KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            raise httpx.ConnectError("Browser provider transport failed.", request=request) from None
        finally:
            if not completed and _worker is not None:
                # Avoid keeping credentials or an unobserved request alive after
                # interruption. No synchronous caller can await an abort ack.
                shutdown_browser_provider_runtime()
            data.fill(0)
            control.fill(0)
            _active = False
            body = ""
            headers.clear()

    def close(self) -> None:
        self.closed = True


def browser_http_client(*, transport: httpx.BaseTransport | None = None) -> httpx.Client:
    if transport is not None:
        raise ValueError("Custom transports are not allowed by the browser provider adapter.")
    return httpx.Client(
        transport=BrowserFetchTransport(),
        timeout=httpx.Timeout(30, connect=10),
        trust_env=False,
        follow_redirects=False,
    )


def install_browser_provider_clients() -> None:
    """Replace only HTTP transport; preserve src.llm_client serialization/parsing."""
    if not runtime_ready():
        raise RuntimeError("Initialize the browser provider runtime asynchronously first.")
    from src import llm_client

    llm_client._http_client = browser_http_client
