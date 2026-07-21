# pywebview 桌面壳 + 打包精简计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 pywebview 替换 tkinter launcher，精简代码，完善 PyInstaller 打包。

**Architecture:** pywebview 开原生窗口加载 FastAPI URL，后台线程运行 uvicorn。提取共享代码消除重复。

---

## 精简清单

| 精简项 | 原因 |
|--------|------|
| tkinter 整套 GUI | pywebview 替代，代码量从 400 行降到 ~80 行 |
| `_restart()`/`_retry()` 重复 | 合并为一个方法 |
| 子进程重启端口 | 改为 uvicorn in-process 重启 |
| `Path.cwd()` 配置路径 bug | 用 `_get_base_dir()` 替代 |
| `_open_config_dir` 平台分支 | 直接用 `os.startfile()` |
| YAML 读写端口 | 用简单文本文件 |
| launcher/cli 重复的 asyncio 修复 | 提取共享模块 |
| launcher/cli 重复的服务器启动 | 提取共享函数 |
| spec 中 `insightclass.utils.paths` | 不需要，删除 |
| spec 中 `torch` | 可删除（ultralytics 传递依赖） |
| build 脚本 `Read-Host` | 改为参数 `-BuildInstaller` |

---

## Task 1: 安装 pywebview

- [ ] **Step 1: 安装**
```bash
conda run -n QF_DL pip install pywebview
```

- [ ] **Step 2: 验证**
```bash
conda run -n QF_DL python -c "import webview; print(webview.__version__)"
```

- [ ] **Step 3: 不提交**（依赖已在 pyproject.toml 中声明）

---

## Task 2: 提取共享模块

**创建:** `src/insightclass/web/_server_utils.py`

将 launcher 和 CLI 共用的逻辑提取到一个模块：

```python
"""Shared utilities for starting the InsightClass server."""
from __future__ import annotations

import asyncio
import sys
import threading
from pathlib import Path
from typing import Optional


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
    import urllib.request
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/settings/ui-defaults", timeout=1)
            return True
        except Exception:
            time.sleep(0.5)
    return False
```

- [ ] **Step 1: 创建文件**
- [ ] **Step 2: 提交**
```bash
git add src/insightclass/web/_server_utils.py
git commit -m "refactor: extract shared server utilities for launcher and CLI"
```

---

## Task 3: 重写 launcher（pywebview 替换 tkinter）

**重写:** `src/insightclass/web/launcher.pyw`

将 403 行 tkinter 代码替换为 ~80 行 pywebview 代码：

```python
"""InsightClass desktop launcher using pywebview."""
from __future__ import annotations

import logging
import sys
import threading
import time
from pathlib import Path

from insightclass.web._server_utils import (
    fix_windows_event_loop,
    start_server_thread,
    wait_for_server,
)

fix_windows_event_loop()

logger = logging.getLogger(__name__)


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path.cwd()


def _find_available_port(preferred: int = 8000) -> int:
    """Find an available port, trying preferred first then alternatives."""
    import socket

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


def main() -> None:
    import webview

    # Determine port
    saved = _load_saved_port()
    port = _find_available_port(saved or 8000)
    _save_port(port)

    # Start server
    logger.info("Starting server on port %d", port)
    _thread, server = start_server_thread(host="127.0.0.1", port=port)

    # Wait for server to be ready
    if not wait_for_server(port, timeout=30):
        logger.error("Server failed to start within 30 seconds")
        sys.exit(1)

    logger.info("Server ready at http://127.0.0.1:%d", port)

    # Create native window
    window = webview.create_window(
        title="InsightClass",
        url=f"http://127.0.0.1:{port}",
        width=1280,
        height=800,
        min_size=(960, 600),
    )

    # When window closes, stop server
    def on_closed():
        server.should_exit = True

    window.events.closed += on_closed

    # Start the GUI (blocks until window is closed)
    webview.start(debug=False)


if __name__ == "__main__":
    main()
```

- [ ] **Step 1: 重写 launcher.pyw**
- [ ] **Step 2: 验证 pywebview 能启动**（在有显示器的环境中）
- [ ] **Step 3: 提交**
```bash
git add src/insightclass/web/launcher.pyw
git commit -m "refactor: rewrite launcher with pywebview, replace 400-line tkinter with 80 lines"
```

---

## Task 4: 更新 CLI 使用共享模块

**修改:** `src/insightclass/cli.py`

- [ ] **Step 1: 替换 asyncio 修复代码**

将 `cli.py` 开头的：
```python
import asyncio
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
```
替换为：
```python
from insightclass.web._server_utils import fix_windows_event_loop
fix_windows_event_loop()
```

- [ ] **Step 2: 提交**
```bash
git add src/insightclass/cli.py
git commit -m "refactor: CLI uses shared _server_utils for event loop fix"
```

---

## Task 5: 精简 PyInstaller spec

**修改:** `InsightClass.spec`

- [ ] **Step 1: 删除不需要的 hidden imports**

从 hiddenimports 中删除：
- `insightclass.utils.paths`（web 模块不使用）
- `torch`（通过 ultralytics 传递，不需要显式声明）

保留 `insightclass.backends.ultralytics_backend`（安全网）。

- [ ] **Step 2: 添加 pywebview hidden import**

添加 `'webview'` 到 hiddenimports。

- [ ] **Step 3: 提交**
```bash
git add InsightClass.spec
git commit -m "refactor: clean up spec — remove unused hidden imports, add webview"
```

---

## Task 6: 精简打包脚本

**修改:** `scripts/build_package.ps1`

- [ ] **Step 1: 添加 `-BuildInstaller` 参数**

替换 `Read-Host` 交互式提示为脚本参数：
```powershell
param(
    [switch]$BuildInstaller,
    [switch]$SkipDeps
)
```

- [ ] **Step 2: 用 `-SkipDeps` 控制依赖安装**

```powershell
if (-not $SkipDeps) {
    pip install -e ".[web,ultralytics]" --quiet
    pip install cryptography pyinstaller --quiet
}
```

- [ ] **Step 3: 用 `-BuildInstaller` 控制 Inno Setup**

```powershell
if ($BuildInstaller) {
    # Run Inno Setup
}
```

- [ ] **Step 4: 提交**
```bash
git add scripts/build_package.ps1
git commit -m "refactor: build script — add -BuildInstaller and -SkipDeps params"
```

---

## Task 7: 更新打包文档

**修改:** `docs/09_打包与发行.md`

- [ ] **Step 1: 更新 launcher 描述**

将 tkinter 相关描述改为 pywebview：
- "tkinter 控制窗口" → "pywebview 原生窗口"
- "webbrowser.open()" → "WebView 内嵌浏览器"

- [ ] **Step 2: 更新自动化构建脚本说明**

添加新参数说明：
```powershell
.\scripts\build_package.ps1                    # 完整构建
.\scripts\build_package.ps1 -SkipDeps          # 跳过依赖安装
.\scripts\build_package.ps1 -BuildInstaller    # 同时生成安装程序
```

- [ ] **Step 3: 提交**
```bash
git add docs/09_打包与发行.md
git commit -m "docs: update packaging doc for pywebview launcher"
```

---

## 验证清单

- [ ] `conda run -n QF_DL python -c "from insightclass.web.server import app; print('OK')"` — 无崩溃
- [ ] `conda run -n QF_DL python -m pytest tests/ -v` — 测试通过
- [ ] `cd frontend && npm run build` — 前端构建成功
- [ ] launcher 代码量从 403 行降到 ~80 行
- [ ] 无重复代码（asyncio fix、server startup）
