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

if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "ygttygtt.InsightClass"
        )
        if getattr(sys, "frozen", False):
            ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    except Exception:
        pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("launcher")


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path.cwd()


def _resource_path(*parts: str) -> Path:
    """Resolve read-only assets in both source and PyInstaller layouts."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS).joinpath(*parts)
    return Path(__file__).resolve().parents[3].joinpath(*parts)


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
            from PIL import Image
        except ImportError:
            logger.warning("pystray is unavailable; tray behavior is disabled")
            return

        icon_path = _resource_path("assets", "insightclass-tray.png")
        try:
            with Image.open(icon_path) as source:
                image = source.convert("RGBA")
        except OSError:
            logger.exception("Unable to load tray icon from %s", icon_path)
            return
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
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="color-scheme" content="dark light"><style>
:root{color-scheme:dark;--bg:#0b0f17;--panel:#111722;--panel-2:#171e2b;--line:#273142;--text:#edf2f7;--muted:#8d99aa;--accent:#22c1a3;--accent-soft:#173d39;--skeleton:#202a39;--danger:#ff6b6b}
@media(prefers-color-scheme:light){:root{color-scheme:light;--bg:#f3f6f8;--panel:#fff;--panel-2:#f8fafb;--line:#dce3e8;--text:#17212b;--muted:#687684;--accent:#087f6d;--accent-soft:#dff4ef;--skeleton:#e5eaee;--danger:#c83d4b}}
*{box-sizing:border-box}html,body{margin:0;width:100%;height:100%;overflow:hidden}body{background:var(--bg);color:var(--text);font:14px 'Segoe UI',system-ui,sans-serif;letter-spacing:0}
.startup-shell{display:grid;grid-template-columns:208px minmax(0,1fr);height:100vh}.sidebar{border-right:1px solid var(--line);background:var(--panel);padding:18px 14px}.brand{display:flex;align-items:center;gap:10px;padding:0 7px 20px;font-size:16px;font-weight:650}.logo{width:30px;height:30px;flex:none}.nav{display:grid;gap:7px}.nav-row{height:38px;border-radius:6px;background:var(--panel-2);display:flex;align-items:center;gap:10px;padding:0 11px;color:var(--muted)}.nav-row.active{background:var(--accent-soft);color:var(--accent)}.nav-icon{width:15px;height:15px;border:2px solid currentColor;border-radius:3px}.nav-line{height:7px;width:82px;border-radius:3px;background:currentColor;opacity:.42}
.page{display:grid;grid-template-rows:58px minmax(0,1fr);min-width:0}.toolbar{display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--line);background:var(--panel);padding:0 20px}.toolbar-title{font-size:15px;font-weight:600}.toolbar-actions{display:flex;gap:9px}.tool{width:32px;height:32px;border:1px solid var(--line);border-radius:6px;background:var(--panel-2)}
.content{display:grid;grid-template-columns:minmax(0,1fr) 260px;gap:16px;padding:16px;min-height:0}.monitor{position:relative;display:flex;align-items:center;justify-content:center;min-height:0;border:1px solid var(--line);border-radius:8px;background:var(--panel)}.screen-skeleton{position:absolute;inset:14px;overflow:hidden;border-radius:5px;background:var(--panel-2)}.screen-skeleton:after{content:'';position:absolute;inset:0;transform:translateX(-100%);background:linear-gradient(90deg,transparent,color-mix(in srgb,var(--skeleton) 65%,transparent),transparent);animation:shimmer 1.6s ease-in-out infinite}.screen-bar{position:absolute;left:18px;right:18px;bottom:18px;height:9px;border-radius:4px;background:var(--skeleton)}
.startup-state{position:relative;z-index:1;width:min(390px,calc(100% - 40px));padding:22px;border:1px solid var(--line);border-radius:8px;background:color-mix(in srgb,var(--panel) 94%,transparent);box-shadow:0 12px 36px rgba(0,0,0,.18)}.state-head{display:flex;gap:13px;align-items:center}.spinner{width:30px;height:30px;flex:none;border:3px solid var(--line);border-top-color:var(--accent);border-radius:50%;animation:spin .8s linear infinite}.startup-state.error .spinner{animation:none;border-color:var(--danger);position:relative}.startup-state.error .spinner:after{content:'!';position:absolute;inset:0;display:grid;place-items:center;color:var(--danger);font-weight:700}.startup-state h1{margin:0 0 4px;font-size:17px;font-weight:650}.startup-state p{margin:0;color:var(--muted);line-height:1.45}.progress{height:4px;margin:18px 0 14px;overflow:hidden;border-radius:2px;background:var(--line)}.progress-fill{width:12%;height:100%;background:var(--accent);transition:width .3s ease}.steps{display:flex;justify-content:space-between;color:var(--muted);font-size:12px}.step.active{color:var(--accent)}
.camera-panel{display:grid;grid-template-rows:auto 150px 1fr;gap:12px;padding:14px;border:1px solid var(--line);border-radius:8px;background:var(--panel)}.panel-title{font-weight:600}.camera-preview{border-radius:6px;background:var(--panel-2);position:relative;overflow:hidden}.camera-preview:before,.camera-preview:after{content:'';position:absolute;background:var(--skeleton);border-radius:4px}.camera-preview:before{width:56px;height:56px;left:calc(50% - 28px);top:35px}.camera-preview:after{width:110px;height:8px;left:calc(50% - 55px);bottom:24px}.metric-list{display:grid;align-content:start;gap:10px}.metric{height:54px;padding:12px;border:1px solid var(--line);border-radius:6px;background:var(--panel-2)}.metric-line{height:7px;border-radius:3px;background:var(--skeleton)}.metric-line.short{width:45%;margin-top:10px}
@keyframes spin{to{transform:rotate(360deg)}}@keyframes shimmer{to{transform:translateX(100%)}}@media(max-width:850px){.startup-shell{grid-template-columns:72px minmax(0,1fr)}.brand span,.nav-line{display:none}.brand{justify-content:center}.nav-row{justify-content:center}.content{grid-template-columns:minmax(0,1fr)}.camera-panel{display:none}}@media(prefers-reduced-motion:reduce){.spinner,.screen-skeleton:after{animation:none}}
</style></head><body><div class="startup-shell">
<aside class="sidebar"><div class="brand"><svg class="logo" viewBox="0 0 256 256" aria-label="InsightClass"><defs><linearGradient id="g" x1="12" y1="12" x2="244" y2="244" gradientUnits="userSpaceOnUse"><stop stop-color="#4f46e5"/><stop offset="1" stop-color="#06b6d4"/></linearGradient></defs><rect x="12" y="12" width="232" height="232" rx="54" fill="url(#g)"/><path fill="#fff" fill-rule="evenodd" d="M57 128C92 74 164 74 199 128C164 182 92 182 57 128ZM77 128C103 98 153 98 179 128C153 158 103 158 77 128Z"/><circle cx="128" cy="128" r="25" fill="#fff"/><circle cx="128" cy="128" r="12" fill="#1e2959"/><circle cx="124" cy="124" r="3.5" fill="#fff"/></svg><span>InsightClass</span></div><div class="nav"><div class="nav-row active"><i class="nav-icon"></i><i class="nav-line"></i></div><div class="nav-row"><i class="nav-icon"></i><i class="nav-line"></i></div><div class="nav-row"><i class="nav-icon"></i><i class="nav-line"></i></div></div></aside>
<section class="page"><header class="toolbar"><div class="toolbar-title">课堂行为监控</div><div class="toolbar-actions"><i class="tool"></i><i class="tool"></i></div></header><main class="content"><section class="monitor"><div class="screen-skeleton"><i class="screen-bar"></i></div><div class="startup-state" id="startup-state"><div class="state-head"><div class="spinner"></div><div><h1>正在打开 InsightClass</h1><p id="status" aria-live="polite">正在准备应用窗口...</p></div></div><div class="progress"><div class="progress-fill" id="progress-fill"></div></div><div class="steps"><span class="step active" data-stage="window">窗口</span><span class="step" data-stage="service">服务</span><span class="step" data-stage="api">界面</span><span class="step" data-stage="ready">完成</span></div></div></section><aside class="camera-panel"><div class="panel-title">摄像头</div><div class="camera-preview"></div><div class="metric-list"><div class="metric"><div class="metric-line"></div><div class="metric-line short"></div></div><div class="metric"><div class="metric-line"></div><div class="metric-line short"></div></div></div></aside></main></section>
</div><script>
const startupOrder=['window','service','api','ready'];
window.__setStartupStage=function(stage,message){const index=startupOrder.indexOf(stage);document.getElementById('status').textContent=message;document.getElementById('progress-fill').style.width=((index+1)/startupOrder.length*100)+'%';document.querySelectorAll('.step').forEach((item,itemIndex)=>item.classList.toggle('active',itemIndex<=index));};
window.__showStartupError=function(message){document.getElementById('startup-state').classList.add('error');document.getElementById('status').textContent=message;document.querySelector('.startup-state h1').textContent='InsightClass 启动失败';};
</script></body></html>"""


def _set_startup_stage(window, stage: str, message: str) -> None:
    try:
        window.evaluate_js(
            "window.__setStartupStage("
            f"{json.dumps(stage)}, {json.dumps(message, ensure_ascii=False)})"
        )
    except Exception:
        logger.debug("Unable to update startup stage", exc_info=True)


def _show_startup_error(window, message: str) -> None:
    try:
        window.evaluate_js(
            f"window.__showStartupError({json.dumps(message, ensure_ascii=False)})"
        )
    except Exception:
        logger.debug("Unable to show startup error", exc_info=True)


def main() -> None:
    saved_port = _read_port(".port")
    saved_control = _read_port(".control")
    if saved_control and _send_activation(saved_control):
        return
    if saved_port and _is_server_running(saved_port):
        # A legacy launcher may not expose activation yet; do not start a
        # second backend against its already-running service.
        return

    # Importing the GUI runtime is unnecessary when a running instance can be
    # activated. Keep it out of the second-launch path.
    import webview

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

    def start_server():
        from insightclass.web._server_utils import (
            fix_windows_event_loop,
            start_server_thread,
            wait_for_server,
        )

        _set_startup_stage(window, "service", "正在启动本地服务...")
        fix_windows_event_loop()
        logger.info("Starting server on port %d", port)
        _thread, server = start_server_thread(host="127.0.0.1", port=port)
        state["server"] = server
        _set_startup_stage(window, "api", "正在准备分析界面...")
        if wait_for_server(port, timeout=60):
            _set_startup_stage(
                window,
                "ready",
                "界面已就绪，分析模型将在后台继续加载",
            )
            window.load_url(f"http://127.0.0.1:{port}")
        else:
            logger.error("Server did not become ready within 60 seconds")
            _show_startup_error(window, "服务器启动超时，请检查日志或端口占用")

    def start_after_window_shown():
        # pywebview invokes this callback after its GUI loop is running. Heavy
        # tray and server imports therefore cannot delay the first window.
        tray.start()
        threading.Thread(
            target=start_server,
            daemon=True,
            name="insightclass-server-start",
        ).start()

    try:
        webview.start(
            func=start_after_window_shown,
            debug=False,
            icon=str(_resource_path("assets", "insightclass.ico")),
            private_mode=False,
            storage_path=str(_config_dir() / "webview"),
        )
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
