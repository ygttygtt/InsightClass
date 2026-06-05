"""InsightClass 桌面应用启动器 - 带控制窗口"""

import sys
import threading
import time
import webbrowser
import socket
import os
import subprocess
import random

# 隐藏控制台窗口
if sys.platform == 'win32':
    try:
        import ctypes
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    except Exception:
        pass

import tkinter as tk
from tkinter import messagebox, ttk
from pathlib import Path

# 常用端口列表
COMMON_PORTS = [8000, 8001, 8002, 8080, 8888, 9000]

# configs/app.yaml 路径（与 server.py 保持一致，cwd 为项目根目录）
_CONFIG_PATH = Path.cwd() / "configs" / "app.yaml"


def _load_app_yaml() -> dict:
    if not _CONFIG_PATH.exists():
        return {}
    try:
        import yaml
        with _CONFIG_PATH.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _save_app_yaml(data: dict):
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        import yaml
        with _CONFIG_PATH.open("w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
    except Exception:
        pass


def _get_saved_port() -> int | None:
    cfg = _load_app_yaml()
    port = cfg.get("launcher_port")
    return int(port) if port else None


def _save_port(port: int):
    cfg = _load_app_yaml()
    cfg["launcher_port"] = port
    _save_app_yaml(cfg)


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('127.0.0.1', port))
            return False
        except OSError:
            return True


def find_available_port(preferred: int | None = None) -> int:
    """查找可用端口：优先用记忆端口，再试常用端口，最后随机冷门端口"""
    if preferred and not is_port_in_use(preferred):
        return preferred
    for port in COMMON_PORTS:
        if port != preferred and not is_port_in_use(port):
            return port
    for _ in range(50):
        port = random.randint(10000, 60000)
        if not is_port_in_use(port):
            return port
    return 0


def check_server_running(port: int) -> bool:
    try:
        import urllib.request
        response = urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=2)
        return response.status == 200
    except Exception:
        return False


def wait_for_server(port: int, timeout: int = 30) -> bool:
    import urllib.request
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=1)
            if response.status == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def _relaunch(port: int):
    """保存端口，启动新进程，退出当前进程"""
    _save_port(port)
    subprocess.Popen([sys.executable, __file__, '--port', str(port)])
    time.sleep(0.3)
    os._exit(0)


class ControlWindow:
    """控制窗口"""

    def __init__(self, port=8000):
        self.port = port
        self.server_thread = None
        self.server_running = False

        self.root = tk.Tk()
        self.root.title(f"InsightClass 深见课堂 - 端口 {port}")
        self.root.geometry("420x400")
        self.root.resizable(False, False)

        try:
            self.root.iconbitmap(default='')
        except Exception:
            pass

        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() - 420) // 2
        y = (self.root.winfo_screenheight() - 400) // 2
        self.root.geometry(f"420x400+{x}+{y}")

        self._create_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._start_server()

    def _create_ui(self):
        # ---- 标题栏 ----
        title_frame = tk.Frame(self.root, bg="#6366f1", height=80)
        title_frame.pack(fill=tk.X)
        title_frame.pack_propagate(False)

        tk.Label(
            title_frame, text="🎓 InsightClass",
            font=("Microsoft YaHei", 20, "bold"),
            fg="white", bg="#6366f1"
        ).pack(pady=10)

        tk.Label(
            title_frame, text="深见课堂 - 行为检测系统",
            font=("Microsoft YaHei", 10), fg="white", bg="#6366f1"
        ).pack()

        # ---- 状态区域 ----
        status_frame = tk.Frame(self.root, pady=10)
        status_frame.pack(fill=tk.BOTH, expand=True)

        self.status_label = tk.Label(
            status_frame, text="⏳ 正在启动服务...",
            font=("Microsoft YaHei", 12), fg="#666"
        )
        self.status_label.pack(pady=5)

        self.url_label = tk.Label(
            status_frame, text=f"http://127.0.0.1:{self.port}",
            font=("Microsoft YaHei", 10), fg="#999"
        )
        self.url_label.pack()

        # 端口选择
        port_frame = tk.Frame(status_frame)
        port_frame.pack(pady=8)

        tk.Label(port_frame, text="端口:", font=("Microsoft YaHei", 10)).pack(side=tk.LEFT, padx=(0, 5))

        self.port_var = tk.StringVar(value=str(self.port))
        self.port_combo = ttk.Combobox(
            port_frame, textvariable=self.port_var,
            values=[str(p) for p in COMMON_PORTS],
            width=8, font=("Microsoft YaHei", 10)
        )
        self.port_combo.pack(side=tk.LEFT)

        # 错误信息（初始隐藏）
        self.error_label = tk.Label(
            status_frame, text="", font=("Microsoft YaHei", 9),
            fg="#ef4444", wraplength=380
        )

        # ---- 按钮区域 ----
        btn_frame = tk.Frame(self.root, pady=8)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)

        btn_row1 = tk.Frame(btn_frame)
        btn_row1.pack(pady=4)

        self.open_btn = tk.Button(
            btn_row1, text="🌐 打开浏览器",
            font=("Microsoft YaHei", 11), bg="#6366f1", fg="white",
            relief=tk.FLAT, padx=15, pady=6,
            state=tk.DISABLED, command=self._open_browser
        )
        self.open_btn.pack(side=tk.LEFT, padx=5)

        self.restart_btn = tk.Button(
            btn_row1, text="🔄 重新启动",
            font=("Microsoft YaHei", 11), bg="#f59e0b", fg="white",
            relief=tk.FLAT, padx=15, pady=6,
            command=self._restart
        )
        self.restart_btn.pack(side=tk.LEFT, padx=5)

        btn_row2 = tk.Frame(btn_frame)
        btn_row2.pack(pady=4)

        self.config_btn = tk.Button(
            btn_row2, text="📁 打开配置目录",
            font=("Microsoft YaHei", 10), bg="#64748b", fg="white",
            relief=tk.FLAT, padx=15, pady=4,
            command=self._open_config_dir
        )
        self.config_btn.pack(side=tk.LEFT, padx=5)

        self.retry_btn = tk.Button(
            btn_row2, text="🔁 重试",
            font=("Microsoft YaHei", 10), bg="#ef4444", fg="white",
            relief=tk.FLAT, padx=15, pady=4,
            command=self._retry, state=tk.DISABLED
        )
        self.retry_btn.pack(side=tk.LEFT, padx=5)

        tk.Label(
            btn_frame, text="关闭此窗口将停止服务",
            font=("Microsoft YaHei", 9), fg="#999"
        ).pack(pady=4)

    def _start_server(self):
        """启动服务器"""
        def run_server():
            try:
                import uvicorn
                from insightclass.web.server import app
                uvicorn.run(
                    app, host='127.0.0.1', port=self.port,
                    log_level='warning', access_log=False
                )
            except Exception as e:
                self.root.after(0, self._show_error, str(e))

        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()
        self.server_running = True

        def check_server():
            if wait_for_server(self.port):
                self.root.after(0, self._on_server_ready)
            else:
                self.root.after(0, self._show_error, "服务启动超时，请检查端口是否被占用")

        threading.Thread(target=check_server, daemon=True).start()

    def _on_server_ready(self):
        self.status_label.config(text="✅ 服务已启动", fg="#22c55e")
        self.url_label.config(text=f"http://127.0.0.1:{self.port}")
        self.open_btn.config(state=tk.NORMAL)
        self.retry_btn.config(state=tk.DISABLED)
        self.error_label.pack_forget()
        _save_port(self.port)
        self._open_browser()

    def _show_error(self, msg: str):
        self.status_label.config(text="❌ 服务启动失败", fg="#ef4444")
        self.error_label.config(text=msg)
        self.error_label.pack(pady=5)
        self.retry_btn.config(state=tk.NORMAL)

    def _open_browser(self):
        webbrowser.open(f"http://127.0.0.1:{self.port}")

    def _open_config_dir(self):
        config_dir = str(_CONFIG_PATH.parent)
        if sys.platform == 'win32':
            os.startfile(config_dir)
        else:
            subprocess.Popen(['xdg-open', config_dir])

    def _restart(self):
        """重新启动"""
        try:
            new_port = int(self.port_var.get())
        except ValueError:
            messagebox.showerror("错误", "请输入有效的端口号")
            return
        _relaunch(new_port)

    def _retry(self):
        """重试：用当前选择的端口重新启动"""
        try:
            new_port = int(self.port_var.get())
        except ValueError:
            messagebox.showerror("错误", "请输入有效的端口号")
            return
        _relaunch(new_port)

    def _on_close(self):
        if messagebox.askokcancel("退出", "确定要退出 InsightClass 吗？\n退出后检测服务将停止。"):
            self.server_running = False
            self.root.destroy()
            os._exit(0)

    def run(self):
        self.root.mainloop()


def main():
    import argparse
    parser = argparse.ArgumentParser(description='InsightClass 桌面应用')
    parser.add_argument('--port', type=int, default=0, help='服务端口 (默认: 自动选择)')
    args = parser.parse_args()

    if args.port:
        port = args.port
        # 重启场景：端口可能短暂被旧进程占用，等待释放
        for _ in range(10):
            if not is_port_in_use(port):
                break
            if check_server_running(port):
                webbrowser.open(f'http://127.0.0.1:{port}/')
                return
            time.sleep(0.3)
        else:
            if check_server_running(port):
                webbrowser.open(f'http://127.0.0.1:{port}/')
                return
            # 仍然被占用，自动选其他端口
            port = find_available_port()
    else:
        saved = _get_saved_port()
        port = find_available_port(preferred=saved)
        # 检查记忆端口是否已有服务在运行
        if saved and is_port_in_use(saved) and check_server_running(saved):
            webbrowser.open(f'http://127.0.0.1:{saved}/')
            return

    window = ControlWindow(port=port)
    window.run()


if __name__ == '__main__':
    main()
