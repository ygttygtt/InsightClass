# Legacy Cleanup Plan — Jinja2 → React 迁移遗留问题

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all stale references from the Jinja2 → React migration. 3 个崩溃 Bug、2 个过时依赖、4 个过时文档，共 9 个问题。

**Architecture:** 精准外科手术式修改，不新增功能。

---

## 问题清单

### 崩溃 Bug（运行/打包会直接报错）

| # | 文件 | 行号 | 问题 |
|---|------|------|------|
| 1 | `src/insightclass/web/server.py` | 46, 466 | `_STATIC_DIR` + `app.mount("/static", ...)` 引用已删除的 `web/static/` 目录，启动时 RuntimeError |
| 2 | `InsightClass.spec` | 8 | `datas` 打包 `web/templates` 和 `web/static`（不存在），且缺少 `frontend/dist` |
| 3 | `scripts/build_package.ps1` | 36 | 引用 `InsightClass-Web.spec`（不存在），实际文件是 `InsightClass.spec` |

### 过时依赖

| # | 文件 | 行号 | 问题 |
|---|------|------|------|
| 4 | `pyproject.toml` | 32 | `jinja2>=3.1` — 项目中已无任何文件 import jinja2 |
| 5 | `pyproject.toml` | 34 | `PySide6>=6.5` — launcher 用的是 tkinter，不是 PySide6 |

### 过时文档

| # | 文件 | 问题 |
|---|------|------|
| 6 | `CLAUDE.md` | 描述已删除的 3 应用 Jinja2 架构、`view-experiments`/`demo` 命令 |
| 7 | `README.md` | 引用已删除的 `view-experiments` 和 `demo` CLI 命令 |
| 8 | `docs/项目整体架构文档.md` | 大量过时内容：列出已删除文件、旧 CLI 命令、旧 API 结构 |
| 9 | `docs/09_打包与发行.md` | 引用不存在的 `InsightClass-Web.spec`、PySide6 WebEngine、不支持的脚本参数 |

---

## Task 1: 修复 server.py 崩溃 Bug

**文件:** `src/insightclass/web/server.py`

- [ ] **Step 1: 删除 `_STATIC_DIR` 定义（第 46 行）**

删除：
```python
_STATIC_DIR = Path(__file__).parent / "static"
```

- [ ] **Step 2: 删除死代码 `/static` mount（第 466 行）**

删除：
```python
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
```

- [ ] **Step 3: 验证服务器启动**

```bash
conda run -n QF_DL python -c "from insightclass.web.server import app; print('OK')"
```
预期：输出 OK，无 RuntimeError

- [ ] **Step 4: 提交**

```bash
git add src/insightclass/web/server.py
git commit -m "fix: remove dead _STATIC_DIR and /static mount referencing deleted directory"
```

---

## Task 2: 修复 PyInstaller spec

**文件:** `InsightClass.spec`

- [ ] **Step 1: 更新 datas 列表（第 8 行）**

替换为：
```python
datas=[
    ('configs/classes.yaml', 'configs'),
    ('frontend/dist', 'frontend/dist'),
    ('models/*.pt', 'models'),
],
```

说明：
- `frontend/dist/` 替代旧的 `web/templates` 和 `web/static`
- `models/*.pt` 用 glob 模式替代硬编码实验路径
- 若 `models/` 不存在，PyInstaller 会跳过

- [ ] **Step 2: 添加 PIL hidden import**

在 `hiddenimports` 列表中添加 `'PIL'`（server.py 第 27 行 import 了 PIL）。

- [ ] **Step 3: 提交**

```bash
git add InsightClass.spec
git commit -m "fix: update PyInstaller spec — bundle frontend/dist, remove stale paths, add PIL"
```

---

## Task 3: 修复打包脚本

**文件:** `scripts/build_package.ps1`

- [ ] **Step 1: 修复 spec 文件引用（第 36 行）**

```powershell
# 旧
python -m PyInstaller InsightClass-Web.spec --clean --noconfirm
# 新
python -m PyInstaller InsightClass.spec --clean --noconfirm
```

- [ ] **Step 2: 添加 React 前端构建步骤**

在 PyInstaller 步骤之前插入：
```powershell
# 2.5 构建 React 前端
Write-Host "`n[2.5/5] 构建 React 前端..." -ForegroundColor Yellow
Push-Location frontend
npm install --silent
if ($LASTEXITCODE -ne 0) {
    Write-Host "错误: npm install 失败" -ForegroundColor Red
    exit 1
}
npm run build
if ($LASTEXITCODE -ne 0) {
    Write-Host "错误: React 前端构建失败" -ForegroundColor Red
    exit 1
}
Pop-Location
Write-Host "  React 前端构建完成" -ForegroundColor Green
```

- [ ] **Step 3: 更新必要文件检查**

移除硬编码模型路径（第 18 行）：
```powershell
$requiredFiles = @(
    "src\insightclass\web\launcher.pyw",
    "configs\classes.yaml"
)
```

- [ ] **Step 4: 提交**

```bash
git add scripts/build_package.ps1
git commit -m "fix: build script — correct spec name, add React build step, remove hardcoded model"
```

---

## Task 4: 清理过时依赖

**文件:** `pyproject.toml`

- [ ] **Step 1: 移除 jinja2（第 32 行）**

```toml
# 删除这行
"jinja2>=3.1",
```

- [ ] **Step 2: 移除 PySide6（第 34 行）**

```toml
# 删除这行
"PySide6>=6.5",
```

- [ ] **Step 3: 添加 pywebview 依赖**

```toml
# 替换上面两行
"pywebview>=5.0",
```

说明：后续桌面壳阶段会用 pywebview，提前加入依赖。

- [ ] **Step 4: 验证安装**

```bash
conda run -n QF_DL pip install -e ".[web,ultralytics]"
```

- [ ] **Step 5: 提交**

```bash
git add pyproject.toml
git commit -m "fix: remove stale jinja2/PySide6 deps, add pywebview"
```

---

## Task 5: 更新 CLAUDE.md

**文件:** `CLAUDE.md`

- [ ] **Step 1: 更新 CLI Subcommands 部分**

删除已不存在的命令：
```
insightclass view-experiments --experiments-root experiments --port 8001
insightclass demo --experiments-root experiments --port 8000
```

保留：
```
insightclass serve --host 0.0.0.0 --port 8000 --experiments-root experiments
insightclass serve --https  # auto-generates self-signed cert at configs/ssl/ (needed for webcam on LAN)
```

- [ ] **Step 2: 更新 Web Frontend 部分**

替换旧的 3 应用表格为：
```markdown
### Web Frontend (`web/` + `frontend/`)

Single FastAPI app (`web/server.py`) serving a React SPA built with Vite.

| Layer | Technology | Purpose |
|---|---|---|
| Backend | FastAPI + Python | REST API for detection, cameras, dashboard, experiments |
| Frontend | React 18 + TypeScript + Vite | SPA with 3 pages: Detection, Dashboard, Experiments |
| Styling | CSS Modules + dark theme | Component-scoped styles with shared CSS variables |
| Charts | Chart.js + react-chartjs-2 | Dashboard charts, experiment training curves |

**Development:** `cd frontend && npm run dev` (Vite on :5173) + `insightclass serve` (API on :8000). Vite proxies `/api` to backend.

**Production:** `cd frontend && npm run build` → `frontend/dist/`. FastAPI serves the built SPA with catch-all routing for React Router.
```

- [ ] **Step 3: 更新 Packaging 部分**

```
Resources (`configs/`, `models/`, `frontend/dist/`) are bundled as data files.
```

- [ ] **Step 4: 提交**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md to reflect React SPA architecture"
```

---

## Task 6: 更新 README.md

**文件:** `README.md`

- [ ] **Step 1: 删除过时 CLI 命令（第 56、61 行）**

删除：
```
insightclass view-experiments --experiments-root experiments --port 8001
```
和：
```
insightclass demo --port 8000
```

- [ ] **Step 2: 更新项目结构（第 64-80 行）**

将 `src/insightclass/` 下的 web 模块部分更新为：
```
    └── web/                       #   Web 服务模块
        ├── server.py              #     FastAPI REST API（合并了旧 demo/experiment_viewer）
        ├── launcher.pyw           #     Windows 桌面启动器（tkinter）
        ├── model_cache.py         #     模型缓存
        └── schemas.py             #     API 响应数据结构（Pydantic）
```

添加前端目录：
```
├── frontend/                # React 前端（TypeScript + Vite）
│   ├── src/
│   │   ├── pages/           #   三个页面：Detection, Dashboard, Experiments
│   │   ├── components/      #   UI 组件
│   │   ├── api/             #   API 客户端
│   │   └── types/           #   TypeScript 类型定义
│   └── dist/                #   构建产物（gitignored）
```

- [ ] **Step 3: 提交**

```bash
git add README.md
git commit -m "docs: update README — remove stale commands, add frontend structure"
```

---

## Task 7: 更新项目整体架构文档

**文件:** `docs/项目整体架构文档.md`

此文件改动最多，需要系统性更新。

- [ ] **Step 1: 更新技术栈表格（第 44 行）**

```
| Web 框架 | FastAPI + uvicorn | REST API 后端 |
| 前端 | React 18 + TypeScript + Vite | SPA 单页应用 |
```

- [ ] **Step 2: 更新目录结构（第 104-117 行）**

替换 `web/` 部分：
```
│       ├── web/                       #     Web 服务模块
│       │   ├── server.py              #       FastAPI REST API（单一应用）
│       │   ├── launcher.pyw           #       Windows 桌面启动器
│       │   ├── model_cache.py         #       模型缓存
│       │   └── schemas.py             #       API 响应数据结构
```

添加 `frontend/` 目录：
```
├── frontend/                          # React 前端
│   ├── src/
│   │   ├── pages/                     #   Detection, Dashboard, Experiments
│   │   ├── components/                #   UI 组件
│   │   ├── api/                       #   API 客户端
│   │   └── types/                     #   TypeScript 类型
│   ├── package.json                   #   依赖配置
│   └── vite.config.ts                 #   Vite 配置（含 API 代理）
```

- [ ] **Step 3: 更新 CLI 命令部分（第 236-240 行）**

删除：
```
insightclass view-experiments --experiments-root experiments --port 8001
insightclass demo --experiments-root experiments --port 8000
```

- [ ] **Step 4: 更新 Web 服务流程描述（第 243-290 行）**

将"三个独立的 Web 应用"改为"单一 FastAPI 应用服务 React SPA"。

更新流程图，去掉 Jinja2 模板渲染，改为：
```
浏览器(Vite dev / 生产环境)    FastAPI REST API           YOLO 模型
  │                            │                            │
  │  GET /api/settings/...     │                            │
  │───────────────────────────▶│  返回配置 JSON             │
  │◀───────────────────────────│                            │
  │                            │                            │
  │  POST /api/detect/frame    │                            │
  │───────────────────────────▶│  YOLO 推理                 │
  │                            │───────────────────────────▶│
  │  返回检测结果 JSON         │                            │
  │◀───────────────────────────│◀───────────────────────────│
```

- [ ] **Step 5: 更新 CLI 命令表格（第 321、328 行）**

从实验管理命令表中删除 `view-experiments` 行。
从 Web 服务命令表中删除 `demo` 行。

- [ ] **Step 6: 更新最后更新日期**

```
> 最后更新：2026-06-10
```

- [ ] **Step 7: 提交**

```bash
git add docs/项目整体架构文档.md
git commit -m "docs: update architecture doc — React SPA replaces Jinja2 templates"
```

---

## Task 8: 更新打包文档

**文件:** `docs/09_打包与发行.md`

- [ ] **Step 1: 更新 spec 文件引用（第 43 行）**

```bash
# 旧
pyinstaller InsightClass-Web.spec
# 新
pyinstaller InsightClass.spec
```

- [ ] **Step 2: 更新命令行打包示例（第 52-59 行）**

更新为正确的入口文件路径和参数。

- [ ] **Step 3: 更新 4.2 节（第 97-103 行）**

将标题从 "InsightClass-Web.spec" 改为 "InsightClass.spec"，更新描述。

- [ ] **Step 4: 移除 PySide6 WebEngine 相关内容（第 122-126 行）**

项目不再使用 PySide6，删除相关 FAQ。

- [ ] **Step 5: 更新自动化构建脚本描述（第 190-200 行）**

移除不存在的 `-PackageOnly` 和 `-Version` 参数说明。

- [ ] **Step 6: 提交**

```bash
git add docs/09_打包与发行.md
git commit -m "docs: update packaging doc — correct spec name, remove PySide6 refs"
```

---

## 验证清单

所有 Task 完成后，执行最终验证：

- [ ] `conda run -n QF_DL python -c "from insightclass.web.server import app; print('OK')"` — 无崩溃
- [ ] `conda run -n QF_DL python -m pytest tests/ -v` — 测试通过
- [ ] `cd frontend && npm run build` — 前端构建成功
- [ ] `git log --oneline -5` — 提交历史干净
- [ ] `git status` — 工作区干净
