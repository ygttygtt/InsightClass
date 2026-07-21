"""InsightClass desktop launcher using pywebview.

Starts the FastAPI server in a background thread and opens a native window.
"""
from __future__ import annotations

# Hide console window as early as possible on Windows (frozen builds)
import sys
if sys.platform == "win32" and getattr(sys, "frozen", False):
    try:
        import ctypes
        ctypes.windll.user32.ShowWindow(
            ctypes.windll.kernel32.GetConsoleWindow(), 0
        )
    except Exception:
        pass

import logging
import os
import socket
import time
from pathlib import Path

# Ensure pywebview is detected by PyInstaller
import webview  # noqa: F401

from insightclass.web._server_utils import fix_windows_event_loop

fix_windows_event_loop()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("launcher")


def _get_base_dir() -> Path:
    """Return the exe directory (frozen) or CWD (dev)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path.cwd()


def _find_available_port(preferred: int = 8000) -> int:
    """Find an available port, trying preferred first then alternatives."""
    candidates = [preferred, 8001, 8002, 8080, 8888, 9000]
    for port in candidates:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    # Random port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _save_port(port: int) -> None:
    """Save the port to a simple text file."""
    port_file = _get_base_dir() / "configs" / ".port"
    port_file.parent.mkdir(parents=True, exist_ok=True)
    port_file.write_text(str(port), encoding="utf-8")


def _load_saved_port() -> int | None:
    """Load previously saved port."""
    port_file = _get_base_dir() / "configs" / ".port"
    if port_file.exists():
        try:
            return int(port_file.read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            pass
    return None


_LOADING_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  body { margin:0; display:flex; justify-content:center; align-items:center;
         height:100vh; background:#0a0e1a; color:#e2e8f0;
         font-family:'Segoe UI',system-ui,sans-serif; }
  .loader { text-align:center; }
  .spinner { width:40px; height:40px; border:4px solid #334155;
             border-top-color:#6366f1; border-radius:50%;
             animation:spin 1s linear infinite; margin:0 auto 20px; }
  @keyframes spin { to { transform:rotate(360deg); } }
  h2 { margin:0 0 8px; font-weight:500; }
  p { color:#94a3b8; font-size:14px; transition:opacity 0.3s; }
</style></head><body>
<div class="loader">
  <div class="spinner"></div>
  <h2>InsightClass</h2>
  <p id="status">正在加载推理引擎...</p>
</div>
<script>
  var msgs = ['正在加载推理引擎...', '正在初始化模型...', '正在启动服务...'];
  var i = 0;
  setInterval(function() {
    i = (i + 1) % msgs.length;
    var el = document.getElementById('status');
    el.style.opacity = '0';
    setTimeout(function() { el.textContent = msgs[i]; el.style.opacity = '1'; }, 300);
  }, 2000);
</script>
</body></html>"""


def main() -> None:
    import webview

    # Determine port
    saved = _load_saved_port()
    port = _find_available_port(saved or 8000)
    _save_port(port)

    # Create window FIRST with loading page (appears immediately)
    window = webview.create_window(
        title="InsightClass",
        html=_LOADING_HTML,
        width=1280,
        height=800,
        min_size=(960, 600),
    )

    # Start server AFTER window is created (heavy imports happen here)
    def _start_server():
        from insightclass.web._server_utils import start_server_thread, wait_for_server

        logger.info("Starting server on port %d", port)
        _thread, server = start_server_thread(host="127.0.0.1", port=port)

        if wait_for_server(port, timeout=60):
            logger.info("Server ready at http://127.0.0.1:%d", port)
            window.load_url(f"http://127.0.0.1:{port}")
        else:
            logger.error("Server failed to start within 60 seconds")
            window.evaluate_js(
                "document.body.innerHTML='<h2 style=\"color:#ef4444\">"
                "启动失败</h2><p>服务器未能在 60 秒内启动</p>'"
            )

        def on_closed():
            server.should_exit = True

        window.events.closed += on_closed

    import threading
    threading.Thread(target=_start_server, daemon=True).start()

    # Start the GUI (blocks until window is closed)
    webview.start(debug=False)


if __name__ == "__main__":
    main()
