"""InsightClass 桌面应用启动器 - 带控制窗口"""

import sys
import threading
import time
import webbrowser
import socket
import os
import subprocess

# 隐藏控制台窗口
if sys.platform == 'win32':
    try:
        import ctypes
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    except Exception:
        pass

import tkinter as tk
from tkinter import messagebox


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('127.0.0.1', port))
            return False
        except OSError:
            return True


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


class ControlWindow:
    """控制窗口"""

    def __init__(self, port=8000):
        self.port = port
        self.server_thread = None
        self.server_running = False

        # 创建窗口
        self.root = tk.Tk()
        self.root.title("InsightClass 深见课堂")
        self.root.geometry("400x300")
        self.root.resizable(False, False)

        # 设置窗口图标（如果有的话）
        try:
            self.root.iconbitmap(default='')
        except Exception:
            pass

        # 居中显示
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() - 400) // 2
        y = (self.root.winfo_screenheight() - 300) // 2
        self.root.geometry(f"400x300+{x}+{y}")

        # 创建界面
        self._create_ui()

        # 绑定关闭事件
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # 启动服务器
        self._start_server()

    def _create_ui(self):
        """创建界面"""
        # 标题
        title_frame = tk.Frame(self.root, bg="#6366f1", height=80)
        title_frame.pack(fill=tk.X)
        title_frame.pack_propagate(False)

        tk.Label(
            title_frame,
            text="🎓 InsightClass",
            font=("Microsoft YaHei", 20, "bold"),
            fg="white",
            bg="#6366f1"
        ).pack(pady=10)

        tk.Label(
            title_frame,
            text="深见课堂 - 行为检测系统",
            font=("Microsoft YaHei", 10),
            fg="white",
            bg="#6366f1"
        ).pack()

        # 状态区域
        status_frame = tk.Frame(self.root, pady=20)
        status_frame.pack(fill=tk.BOTH, expand=True)

        self.status_label = tk.Label(
            status_frame,
            text="⏳ 正在启动服务...",
            font=("Microsoft YaHei", 12),
            fg="#666"
        )
        self.status_label.pack(pady=10)

        self.url_label = tk.Label(
            status_frame,
            text=f"http://127.0.0.1:{self.port}",
            font=("Microsoft YaHei", 10),
            fg="#999"
        )
        self.url_label.pack()

        # 按钮区域
        btn_frame = tk.Frame(self.root, pady=10)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)

        self.open_btn = tk.Button(
            btn_frame,
            text="🌐 打开浏览器",
            font=("Microsoft YaHei", 11),
            bg="#6366f1",
            fg="white",
            relief=tk.FLAT,
            padx=20,
            pady=8,
            state=tk.DISABLED,
            command=self._open_browser
        )
        self.open_btn.pack(pady=5)

        # 提示
        tk.Label(
            btn_frame,
            text="关闭此窗口将停止服务",
            font=("Microsoft YaHei", 9),
            fg="#999"
        ).pack(pady=5)

    def _start_server(self):
        """启动服务器"""
        def run_server():
            try:
                import uvicorn
                from insightclass.web.server import app
                uvicorn.run(
                    app,
                    host='127.0.0.1',
                    port=self.port,
                    log_level='warning',
                    access_log=False
                )
            except Exception as e:
                print(f"Server error: {e}")

        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()
        self.server_running = True

        # 等待服务器启动
        def check_server():
            if wait_for_server(self.port):
                self.status_label.config(text="✅ 服务已启动", fg="#22c55e")
                self.open_btn.config(state=tk.NORMAL)
                # 自动打开浏览器
                self._open_browser()
            else:
                self.status_label.config(text="❌ 服务启动失败", fg="#ef4444")

        threading.Thread(target=check_server, daemon=True).start()

    def _open_browser(self):
        """打开浏览器"""
        url = f"http://127.0.0.1:{self.port}"
        webbrowser.open(url)

    def _on_close(self):
        """关闭窗口时停止服务"""
        if messagebox.askokcancel("退出", "确定要退出 InsightClass 吗？\n退出后检测服务将停止。"):
            self.server_running = False
            self.root.destroy()
            # 强制退出进程
            os._exit(0)

    def run(self):
        """运行窗口"""
        self.root.mainloop()


def main():
    import argparse

    parser = argparse.ArgumentParser(description='InsightClass 桌面应用')
    parser.add_argument('--port', type=int, default=8000, help='服务端口 (默认: 8000)')
    args = parser.parse_args()

    # 检查端口是否被占用
    if is_port_in_use(args.port):
        # 尝试打开已运行的服务
        try:
            import urllib.request
            response = urllib.request.urlopen(f'http://127.0.0.1:{args.port}/', timeout=2)
            if response.status == 200:
                webbrowser.open(f'http://127.0.0.1:{args.port}/')
                return
        except Exception:
            pass
        # 端口被占用，显示错误
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("错误", f"端口 {args.port} 已被占用！\n请关闭占用该端口的程序后重试。")
        root.destroy()
        return

    # 启动控制窗口
    window = ControlWindow(port=args.port)
    window.run()


if __name__ == '__main__':
    main()
