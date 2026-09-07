"""Await this module's setup before entering a synchronous Stlite app script."""

from __future__ import annotations

import asyncio
import atexit
import importlib.util
import sys
import types
from urllib.parse import urlsplit

from browser_transport import (
    _bind_worker,
    runtime_ready,
    shutdown_browser_provider_runtime,
)


def install_nonstreaming_jiter_guard() -> None:
    """Supply only a fail-closed import guard when no Wasm jiter is installed.

    Pinned OpenAI imports jiter for its partial streaming JSON parser. No parser
    is emulated: invoking it always fails. The transport also rejects streaming.
    """
    if "jiter" in sys.modules or importlib.util.find_spec("jiter") is not None:
        return
    module = types.ModuleType("jiter", "Streaming JSON parsing is unavailable in this browser runtime.")

    def unavailable(*args, **kwargs):
        raise RuntimeError("Streaming JSON parsing is unavailable in this browser runtime.")

    module.from_json = unavailable
    sys.modules["jiter"] = module


async def prepare_browser_provider_runtime(worker_url: str) -> None:
    """Start and await the same-origin worker. Idempotent for app reruns.

    The runtime integration must call this with the shipped constant asset URL,
    never with a URL obtained from an app form or other untrusted input.
    """
    import js
    from pyodide.ffi import create_proxy, to_js

    if runtime_ready():
        return
    if not js.crossOriginIsolated:
        raise RuntimeError("Provider requests require cross-origin-isolated browser hosting.")
    target = urlsplit(worker_url)
    origin = urlsplit(str(js.location.origin))
    if (
        target.scheme not in {"https", "http"}
        or target.netloc != origin.netloc
        or target.scheme != origin.scheme
        or target.username
        or target.password
        or target.query
        or target.fragment
        or not target.path.endswith("/fetch-worker.js")
        or (target.scheme == "http" and target.hostname not in {"localhost", "127.0.0.1", "::1"})
    ):
        raise RuntimeError("Browser provider worker must be the shipped same-origin asset.")
    install_nonstreaming_jiter_guard()
    worker = js.Worker.new(worker_url)
    ready = asyncio.get_running_loop().create_future()

    def onmessage(event):
        data = event.data
        if not ready.done():
            if data.type == "ready" and data.protocol == 1 and data.available:
                ready.set_result(True)
            else:
                ready.set_exception(RuntimeError("Browser provider worker is unavailable."))

    def onerror(event):
        event.preventDefault()
        if not ready.done():
            ready.set_exception(RuntimeError("Browser provider worker could not start."))

    message_proxy, error_proxy = create_proxy(onmessage), create_proxy(onerror)
    worker.addEventListener("message", message_proxy)
    worker.addEventListener("error", error_proxy)
    try:
        worker.postMessage(to_js({"type": "ready"}, dict_converter=js.Object.fromEntries))
        await asyncio.wait_for(ready, timeout=10)
        _bind_worker(worker)
    except BaseException:
        worker.terminate()
        raise
    finally:
        worker.removeEventListener("message", message_proxy)
        worker.removeEventListener("error", error_proxy)
        message_proxy.destroy()
        error_proxy.destroy()
    atexit.register(shutdown_browser_provider_runtime)
