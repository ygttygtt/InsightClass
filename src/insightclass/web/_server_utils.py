"""Shared utilities for starting the InsightClass server."""
from __future__ import annotations

import asyncio
import sys
import threading
import time
import urllib.request
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uvicorn


def fix_windows_event_loop() -> None:
    """Set WindowsSelectorEventLoopPolicy on Windows to avoid crashes."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def start_server_thread(
    host: str = "127.0.0.1",
    port: int = 8000,
    log_level: str = "warning",
) -> tuple[threading.Thread, "uvicorn.Server"]:
    """Start uvicorn in a daemon thread. Returns (thread, server) for control."""
    import uvicorn
    from insightclass.web.server import app

    config = uvicorn.Config(
        app, host=host, port=port,
        log_level=log_level, access_log=False,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    return thread, server


def wait_for_server(port: int, timeout: float = 30.0) -> bool:
    """Poll until the server responds or timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/settings/ui-defaults", timeout=1
            )
            return True
        except Exception:
            time.sleep(0.5)
    return False
