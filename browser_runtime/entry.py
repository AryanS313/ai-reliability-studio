"""Run after the browser loader has prepared the provider worker asynchronously."""

# ruff: noqa: E402
import os
import runpy
import sys
from pathlib import Path

sys.path[:0] = ["/app/browser_runtime", "/app", "/providers"]
os.environ.update(
    {
        "AUTH_MODE": "public-session",
        "APP_ENV": "browser",
        "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false",
    }
)
snapshot = Path("/app/browser-source-sha256.txt")
if snapshot.is_file():
    os.environ["STUDIO_BROWSER_SOURCE_SHA256"] = snapshot.read_text().strip()

from browser_execution import install_browser_execution
from browser_transport import install_browser_provider_clients

install_browser_execution()
install_browser_provider_clients()
runpy.run_path("/app/app.py", run_name="__main__")
