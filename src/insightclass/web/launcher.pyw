"""Windows desktop launcher for the InsightClass web application.

The webview is created before importing the inference server so users see a
loading page immediately. Closing the window hides it to the system tray;
only the tray exit action stops the backend.
"""
from __future__ import annotations

import json
import logging
import socket
import threading
import urllib.request
from pathlib import Path

import sys

if sys.platform == "win32" and getattr(sys, "frozen", False):
    try:
        import ctypes
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    except Exception:
        pass

from insightclass.web._server_utils import fix_windows_event_loop

fix_windows_event_loop()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("launcher")


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path.cwd()


def _config_dir() -> Path:
    directory = _get_base_dir() / "configs"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _read_port(name: str) -> int | None:
    path = _config_dir() / name
    try:
        value = int(path.read_text(encoding="utf-8").strip())
        return value if 1 <= value <= 65535 else None
    except (OSError, ValueError):
        return None


def _write_port(name: str, port: int) -> None:
    (_config_dir() / name).write_text(str(port), encoding="utf-8")


def _remove_port(name: str, port: int | None) -> None:
    if port is None:
        return
    path = _config_dir() / name
    try:
        if _read_port(name) == port:
            path.unlink(missing_ok=True)
    except OSError:
        pass


def _is_server_running(port: int) -> bool:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/system/status", timeout=1
        ) as response:
            return response.status == 200
    except Exception:
        return False


def _find_available_port(preferred: int = 8000) -> int:
    candidates = [preferred, 8000, 8001, 8002, 8080, 8888, 9000]
    for port in dict.fromkeys(candidates):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _send_activation(control_port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", control_port), timeout=1) as sock:
            sock.sendall(b"show\n")
            return sock.recv(16).strip() == b"ok"
    except OSError:
        return False


class ActivationServer:
    """Small localhost-only command socket used for single-instance wake-up."""

    def __init__(self, on_show):
        self._on_show = on_show
        self._stop = threading.Event()
        self._socket: socket.socket | None = None
        self.port: int | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> int:
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind(("127.0.0.1", 0))
        self._socket.listen(4)
        self._socket.settimeout(0.5)
        self.port = int(self._socket.getsockname()[1])
        _write_port(".control", self.port)
        self._thread = threading.Thread(target=self._serve, daemon=True, name="insightclass-activation")
        self._thread.start()
        return self.port

    def _serve(self) -> None:
        while not self._stop.is_set() and self._socket:
            try:
                client, _address = self._socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with client:
                try:
                    command = client.recv(32).decode("ascii", errors="ignore").strip()
                    if command == "show":
                        self._on_show()
                        client.sendall(b"ok\n")
                    else:
                        client.sendall(b"error\n")
                except OSError:
                    pass

    def stop(self) -> None:
        self._stop.set()
        if self._socket:
            try:
                self._socket.close()
            except OSError:
                pass
        if self._thread:
            self._thread.join(timeout=1)
        _remove_port(".control", self.port)


class TrayController:
    def __init__(self, on_show, on_exit):
        self._on_show = on_show
        self._on_exit = on_exit
        self._icon = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        try:
            import pystray
            from PIL import Image, ImageDraw
        except ImportError:
            logger.warning("pystray is unavailable; tray behavior is disabled")
            return

        image = Image.new("RGBA", (64, 64), "#6366f1")
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((8, 8, 56, 56), radius=10, fill="#111827")
        draw.text((16, 21), "IC", fill="#f8fafc")
        self._icon = pystray.Icon(
            "InsightClass",
            image,
            "InsightClass",
            pystray.Menu(
                pystray.MenuItem("打开 InsightClass", lambda _icon, _item: self._on_show(), default=True),
                pystray.MenuItem("退出", lambda _icon, _item: self._on_exit()),
            ),
        )
        self._thread = threading.Thread(target=self._icon.run, daemon=True, name="insightclass-tray")
        self._thread.start()

    def stop(self) -> None:
        if self._icon:
            self._icon.stop()
        if self._thread:
            self._thread.join(timeout=2)


_LOADING_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><style>
body{margin:0;display:flex;align-items:center;justify-content:center;height:100vh;background:#0a0e1a;color:#e2e8f0;font:14px 'Segoe UI',system-ui,sans-serif}
.loader{text-align:center}.spinner{width:40px;height:40px;margin:0 auto 20px;border:4px solid #334155;border-top-color:#6366f1;border-radius:50%;animation:spin 1s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}h2{margin:0 0 8px;font-weight:600}p{color:#94a3b8}
</style></head><body><div class="loader"><div class="spinner"></div><h2>InsightClass</h2><p id="status">正在启动服务...</p></div>
<script>const messages=['正在启动服务...','正在加载推理引擎...','正在初始化模型...'];let index=0;setInterval(()=>{index=(index+1)%messages.length;document.getElementById('status').textContent=messages[index]},1800)</script>
</body></html>"""


def main() -> None:
    import webview

    saved_port = _read_port(".port")
    saved_control = _read_port(".control")
    if saved_control and _send_activation(saved_control):
        return
    if saved_port and _is_server_running(saved_port):
        # A legacy launcher may not expose activation yet; do not start a
        # second backend against its already-running service.
        return

    port = _find_available_port(saved_port or 8000)
    _write_port(".port", port)
    window = webview.create_window(
        "InsightClass",
        html=_LOADING_HTML,
        width=1280,
        height=800,
        min_size=(960, 600),
    )
    state = {"quitting": False, "server": None}

    def show_window():
        try:
            window.show()
            if hasattr(window, "restore"):
                window.restore()
        except Exception:
            logger.exception("Unable to show desktop window")

    def request_exit():
        state["quitting"] = True
        server = state.get("server")
        if server:
            server.should_exit = True
        try:
            window.destroy()
        except Exception:
            pass

    def on_closing():
        if state["quitting"]:
            return True
        window.hide()
        return False

    window.events.closing += on_closing
    activation = ActivationServer(show_window)
    activation.start()
    tray = TrayController(show_window, request_exit)
    tray.start()

    def start_server():
        from insightclass.web._server_utils import start_server_thread, wait_for_server

        logger.info("Starting server on port %d", port)
        _thread, server = start_server_thread(host="127.0.0.1", port=port)
        state["server"] = server
        if wait_for_server(port, timeout=60):
            window.load_url(f"http://127.0.0.1:{port}")
        else:
            logger.error("Server did not become ready within 60 seconds")
            message = json.dumps("服务器启动超时，请检查日志或端口占用")
            window.evaluate_js(f"document.body.innerHTML='<h2 style=\\\"color:#ef4444\\\">'+{message}+'</h2>'")

    threading.Thread(target=start_server, daemon=True, name="insightclass-server-start").start()
    try:
        webview.start(debug=False)
    finally:
        state["quitting"] = True
        server = state.get("server")
        if server:
            server.should_exit = True
        tray.stop()
        activation.stop()
        _remove_port(".port", port)


if __name__ == "__main__":
    main()
