# ONNX 推理 + 前端优化 + CSV 导入计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 ONNX Runtime 替换 PyTorch 推理（包体从 1.7GB 降到 ~300MB），删除实验页面，优化仪表盘响应式，优化启动速度，适配海康 CSV 导入，清理项目目录结构。

**Architecture:** 推理和训练分离。训练仍用 PyTorch（GPU 服务器），打包只含 ONNX Runtime（CPU 推理）。前端删除实验页面，优化仪表盘。启动器显示加载页面而非白屏等待。

**Tech Stack:** onnxruntime (CPU inference), opencv (pre/post processing), React + Chart.js (frontend), pywebview (launcher)

---

## 调查结论

### 模型排名（按 mAP50-95）

| 排名 | 实验 | mAP50-95 | mAP50 | 模型 | 说明 |
|------|------|----------|-------|------|------|
| 1 | baseline_yolo11n_v1_e80 | 0.4753 | 0.6694 | yolo11n | v1 数据集，**仅 3 类**（无 standing）|
| **2** | **baseline_yolo11n_v2_e80-2** | **0.2813** | **0.5062** | **yolo11n** | **v2 数据集，4 类，主力模型** |
| **3** | **yolo11n_v2_e150** | **0.2121** | **0.4058** | **yolo11n** | **v2 数据集，150 epoch** |
| 4 | yolo26n_v2_e80 | 0.2292 | 0.4023 | yolo26n | 早停 48 epoch |
| 5 | yolo26n_v2_e150 | 0.1978 | 0.3576 | yolo26n | 早停 70 epoch |

**选择打包的模型（仅 v2，4 类）：**
1. `baseline_yolo11n_v2_e80-2` — 主力模型（4 类：phone_use, talking, sleeping, standing）
2. `yolo11n_v2_e150` — 备选模型

**注意：v1 模型不打包**——只有 3 类（缺少 standing），与当前系统不兼容。

### ONNX Runtime 大小对比

| | PyTorch | ONNX Runtime |
|---|---|---|
| 包体 | ~800MB | ~43MB |
| CPU 推理 | 慢 | 快 2-3 倍 |

### 海康 CSV 格式

文件编码：GB2312/GBK。列结构：
```
名称, 添加模式, 地址, 端口, 设备信息(序列号), 用户名, 密码, 离线添加, 导入至分组, 通道数, 报警输入数, TLS
```
- 第 0 列：IP 地址（如 `10.8.14.8`）
- 第 3 列：端口（`8000` 是 HTTP 管理端口，**RTSP 端口固定 554**）
- 第 4 列：设备序列号（如 `DS-2CD3325-I20190104AACHC85285861`）
- 第 5 列：用户名（如 `admin`）
- 第 6 列：密码（如 `1000phone`）
- 共 32 行数据

**重要：** CSV 中的端口 8000 是海康 Web 管理端口。RTSP 流连接端口是 **554**，用户名 `admin`，密码 `1000phone`（参考 `scripts/rtsp_preview.py` 和 `scripts/record_multi_rtsp.py`）。

---

## 文件结构

### 新建目录
- `models/` — 模型目录（预训练权重 + ONNX 模型）
- `models/onnx/` — ONNX 模型子目录

### 新建文件
- `src/insightclass/backends/onnx_backend.py` — ONNX 推理后端
- `frontend/src/components/dashboard/Dashboard.module.css` — 仪表盘样式（已有，需优化）

### 移动文件
- `yolo11n.pt` → `models/yolo11n.pt`
- `yolo26n.pt` → `models/yolo26n.pt`
- `test_environment.py` → `scripts/test_environment.py`
- `evaluation/experiments.py` → `utils/experiments.py`
- `visualization/pipeline.py` → `utils/pipeline.py`

### 删除文件
- `launcher.log`
- `docs/项目整体架构文档.pdf`（保留 MD 版本）
- `evaluation/` 目录（合并到 utils）
- `visualization/` 目录（合并到 utils）

### 修改文件
- `src/insightclass/web/server.py` — 改用 ONNX 后端，改进 CSV 导入
- `src/insightclass/web/model_cache.py` — 支持 ONNX 模型加载
- `src/insightclass/web/launcher.pyw` — 优化启动体验
- `frontend/src/App.tsx` — 删除实验路由
- `frontend/src/pages/Dashboard.tsx` + CSS — 响应式优化
- `InsightClass.spec` — 排除 PyTorch，包含 ONNX Runtime
- `pyproject.toml` — 添加 onnxruntime 依赖

---

## Task 0: 清理项目目录结构 ✅

**目标：** 精简根目录，合并单文件子目录，删除冗余文件。

- [x] **Step 1: 移动预训练权重到 `models/` 目录**
```bash
mkdir -p models
mv yolo11n.pt models/
mv yolo26n.pt models/
```

- [x] **Step 2: 删除临时文件**
```bash
rm launcher.log
```

- [x] **Step 3: 移动测试脚本到 `scripts/`**
```bash
mv test_environment.py scripts/
```

- [x] **Step 4: 删除重复的 PDF 文档**
```bash
rm docs/项目整体架构文档.pdf
```

- [x] **Step 5: 合并单文件子目录到 `utils/`**
```bash
mv src/insightclass/evaluation/experiments.py src/insightclass/utils/
mv src/insightclass/visualization/pipeline.py src/insightclass/utils/
rm -rf src/insightclass/evaluation/
rm -rf src/insightclass/visualization/
```

- [x] **Step 6: 更新 import 引用**

搜索并替换所有引用：
- `from insightclass.evaluation.experiments` → `from insightclass.utils.experiments`
- `from insightclass.visualization.pipeline` → `from insightclass.utils.pipeline`

- [x] **Step 7: 更新 `.gitignore`**
```gitignore
# 添加
launcher.log
models/*.pt

# 移除
!yolo11n.pt
!yolo26n.pt
```

- [x] **Step 8: 提交**
```bash
git add -A
git commit -m "refactor: clean up project structure — move weights to models/, merge single-file modules"
```

---

## Task 1: 导出 ONNX 模型 ✅

- [x] **Step 1: 创建 models/onnx 目录**
```bash
mkdir -p models/onnx
```

- [x] **Step 2: 导出 v2 模型（4 类，仅导出 v2 数据集训练的）**
```bash
conda run -n QF_DL python -c "
from ultralytics import YOLO
import shutil, os
models = [
    ('experiments/baseline_yolo11n_v2_e80-2/weights/best.pt', 'models/onnx/yolo11n_v2.onnx'),
    ('experiments/yolo11n_v2_e150/weights/best.pt', 'models/onnx/yolo11n_v2_e150.onnx'),
]
for pt, onnx in models:
    print(f'Exporting {pt} -> {onnx}')
    model = YOLO(pt)
    model.export(format='onnx', imgsz=960)
    src = pt.replace('.pt', '.onnx')
    shutil.move(src, onnx)
    print(f'  Done: {os.path.getsize(onnx) / 1024 / 1024:.1f} MB')
"
```
**注意：不导出 v1 模型**——只有 3 类（缺 standing），与系统不兼容。

- [x] **Step 3: 验证 ONNX 模型可用**
```bash
conda run -n QF_DL python -c "
import onnxruntime as ort
import numpy as np
session = ort.InferenceSession('models/onnx/yolo11n_v1.onnx')
print(f'Input: {session.get_inputs()[0].name}, shape: {session.get_inputs()[0].shape}')
print(f'Output: {session.get_outputs()[0].name}, shape: {session.get_outputs()[0].shape}')
dummy = np.random.randn(1, 3, 960, 960).astype(np.float32)
result = session.run(None, {session.get_inputs()[0].name: dummy})
print(f'Inference OK, output shape: {result[0].shape}')
"
```

- [x] **Step 4: 提交**
```bash
git add models/onnx/
git commit -m "feat: export 3 best models to ONNX format"
```

---

## Task 2: 实现 ONNX 推理后端 ✅

**创建:** `src/insightclass/backends/onnx_backend.py`

- [x] **Step 1: 创建 ONNX 后端**

```python
"""ONNX Runtime inference backend for YOLO models."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from insightclass.backends.base import DetectorBackend
from insightclass.schemas import DetectionRecord, FramePrediction, InferenceConfig


class OnnxBackend(DetectorBackend):
    name = "onnx"

    def __init__(self):
        self._session = None
        self._input_name = None
        self._model_path = None

    def _load_model(self, weights_path: str):
        """Load ONNX model lazily."""
        if self._model_path == weights_path and self._session is not None:
            return
        import onnxruntime as ort

        # Prefer CPU provider (no GPU needed for inference)
        self._session = ort.InferenceSession(
            weights_path,
            providers=["CPUExecutionProvider"],
        )
        self._input_name = self._session.get_inputs()[0].name
        self._model_path = weights_path

    def _preprocess(self, img: np.ndarray, imgsz: int = 960) -> tuple[np.ndarray, tuple[float, float]]:
        """Preprocess image for YOLO input. Returns (blob, (ratio_w, ratio_h))."""
        h, w = img.shape[:2]
        r = imgsz / max(h, w)
        if r != 1:
            img = cv2.resize(img, (int(w * r), int(h * r)), interpolation=cv2.INTER_LINEAR)

        # Pad to imgsz x imgsz
        new_h, new_w = img.shape[:2]
        dw = (imgsz - new_w) / 2
        dh = (imgsz - new_h) / 2
        top, bottom = int(round(dh - 0.1)), int(round(dh + 0.1))
        left, right = int(round(dw - 0.1)), int(round(dw + 0.1))
        img = cv2.copyMakeBorder(img, top, bottom, left, right,
                                 cv2.BORDER_CONSTANT, value=(114, 114, 114))

        # HWC -> CHW, BGR -> RGB, normalize
        img = img[:, :, ::-1].transpose(2, 0, 1).astype(np.float32) / 255.0
        return np.expand_dims(img, 0), (r, r)

    def _postprocess(self, output: np.ndarray, ratio: tuple[float, float],
                     conf_threshold: float, iou_threshold: float,
                     imgsz: int = 960) -> list[dict]:
        """Post-process YOLO output to detections."""
        # output shape: (1, num_classes+4, num_boxes) -> transpose to (num_boxes, num_classes+4)
        preds = output[0].T  # (num_boxes, 4+num_classes)

        # Extract boxes and scores
        boxes = preds[:, :4]  # cx, cy, w, h
        scores = preds[:, 4:]  # class scores

        # Get max score per box
        max_scores = scores.max(axis=1)
        class_ids = scores.argmax(axis=1)

        # Filter by confidence
        mask = max_scores > conf_threshold
        boxes = boxes[mask]
        max_scores = max_scores[mask]
        class_ids = class_ids[mask]

        if len(boxes) == 0:
            return []

        # Convert cx,cy,w,h -> x1,y1,x2,y2
        x1 = boxes[:, 0] - boxes[:, 2] / 2
        y1 = boxes[:, 1] - boxes[:, 3] / 2
        x2 = boxes[:, 0] + boxes[:, 2] / 2
        y2 = boxes[:, 1] + boxes[:, 3] / 2
        xyxy = np.stack([x1, y1, x2, y2], axis=1)

        # NMS
        indices = cv2.dnn.NMSBoxes(
            xyxy.tolist(), max_scores.tolist(),
            conf_threshold, iou_threshold,
        )
        if len(indices) == 0:
            return []
        indices = indices.flatten()

        results = []
        for i in indices:
            results.append({
                "xyxy": xyxy[i].tolist(),
                "confidence": float(max_scores[i]),
                "class_id": int(class_ids[i]),
            })
        return results

    def predict_images_or_video(self, config: InferenceConfig) -> DetectionRecord:
        raise NotImplementedError("Use predict_frame for ONNX backend")

    def predict_frame(self, frame: np.ndarray, weights_path: str,
                      confidence: float = 0.5, iou: float = 0.45,
                      imgsz: int = 960) -> list[dict]:
        """Run inference on a single frame. Returns list of detections."""
        self._load_model(weights_path)
        blob, ratio = self._preprocess(frame, imgsz)
        output = self._session.run(None, {self._input_name: blob})[0]
        return self._postprocess(output, ratio, confidence, iou, imgsz)
```

- [x] **Step 2: 注册 ONNX 后端到工厂**

修改 `src/insightclass/backends/factory.py`：
```python
def build_backend(name: str) -> DetectorBackend:
    normalized = name.strip().lower()
    if normalized in {"ultralytics", "yolo", "ultralytics-yolo"}:
        from insightclass.backends.ultralytics_backend import UltralyticsBackend
        return UltralyticsBackend()
    if normalized in {"onnx"}:
        from insightclass.backends.onnx_backend import OnnxBackend
        return OnnxBackend()
    raise ValueError(f"Unsupported backend: {name}")
```

注意：将 `UltralyticsBackend` 的 import 移到函数内部（延迟导入），避免 import factory 就加载 PyTorch。

- [x] **Step 3: 提交**
```bash
git add src/insightclass/backends/onnx_backend.py src/insightclass/backends/factory.py
git commit -m "feat: add ONNX inference backend for CPU-only deployment"
```

---

## Task 3: 更新 model_cache 支持 ONNX ✅

**修改:** `src/insightclass/web/model_cache.py`

- [x] **Step 1: 添加 ONNX 模型支持**

```python
from __future__ import annotations

_model_cache: dict[str, object] = {}


def _is_onnx_model(path: str) -> bool:
    return path.lower().endswith('.onnx')


def get_model(weights_path: str):
    """Load model (ONNX or PyTorch) with caching."""
    path = str(weights_path)
    if path in _model_cache:
        return _model_cache[path]

    if _is_onnx_model(path):
        import onnxruntime as ort
        session = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
        _model_cache[path] = session
    else:
        from insightclass.optional import require_package
        require_package("ultralytics", "Web inference")
        from ultralytics import YOLO
        _model_cache[path] = YOLO(path)

    return _model_cache[path]


def preload_model(weights_path: str) -> None:
    get_model(weights_path)


def clear_cache() -> None:
    _model_cache.clear()
```

- [x] **Step 2: 提交**
```bash
git add src/insightclass/web/model_cache.py
git commit -m "feat: model_cache supports ONNX and PyTorch models"
```

---

## Task 4: 更新 server.py 推理逻辑 ✅

**修改:** `src/insightclass/web/server.py`

- [x] **Step 1: 修改 `_find_default_weights` 优先找 ONNX 模型**

```python
def _find_default_weights() -> str | None:
    """Return best model: prefer ONNX (lightweight), then PyTorch."""
    # 优先使用内置 ONNX 模型
    onnx_dir = _RESOURCE_DIR / "models" / "onnx"
    if onnx_dir.exists():
        onnx_files = sorted(onnx_dir.glob("*.onnx"))
        if onnx_files:
            return str(onnx_files[0])
    # 其次使用内置 .pt 模型
    bundled = _RESOURCE_DIR / "models" / "best.pt"
    if bundled.exists():
        return str(bundled)
    # 最后使用 experiments 中的最佳模型
    candidates = sorted(EXPERIMENTS_ROOT.glob("*/weights/best.pt"))
    return str(candidates[0]) if candidates else None
```

- [x] **Step 2: 修改推理端点支持 ONNX**

在 `POST /api/detect/frame` 和 `POST /api/detect/rtsp` 中，根据模型类型选择推理方式：

```python
# 在推理端点中
if _is_onnx_model(weights_path):
    # ONNX 推理
    from insightclass.backends.onnx_backend import OnnxBackend
    onnx = OnnxBackend()
    detections_raw = onnx.predict_frame(frame, weights_path, confidence, iou)
    detections = []
    for det in detections_raw:
        class_name = CLASS_NAMES.get(det["class_id"], str(det["class_id"]))
        detections.append(DetectionOut(
            xyxy=det["xyxy"],
            confidence=det["confidence"],
            class_id=det["class_id"],
            class_name=class_name,
            display_name=DISPLAY_NAMES.get(class_name, class_name),
        ))
else:
    # PyTorch 推理 (原有逻辑)
    yolo = get_model(weights_path)
    ...
```

添加辅助函数：
```python
def _is_onnx_model(path: str) -> bool:
    return path.lower().endswith('.onnx')
```

- [x] **Step 3: 提交**
```bash
git add src/insightclass/web/server.py
git commit -m "feat: server supports ONNX inference, prefer ONNX models"
```

---

## Task 5: 更新 PyInstaller spec — 排除 PyTorch ✅

**修改:** `InsightClass.spec`

- [x] **Step 1: 排除 PyTorch 和相关大库**

```python
excludes=[
    'PyQt5', 'PyQt6', 'PySide2', 'PySide6',
    'torch', 'torchvision', 'torchaudio',
    'ultralytics',
],
```

- [x] **Step 2: 确保 ONNX Runtime 被包含**

在 hiddenimports 中：
- 移除 `'ultralytics'`
- 保留 `'onnxruntime'`（如果需要）
- 保留 `'PIL'`, `'cv2'`, `'yaml'`

- [x] **Step 3: 更新 datas 包含 ONNX 模型**

```python
_datas = [
    ('configs/classes.yaml', 'configs'),
    ('frontend/dist', 'frontend/dist'),
]
# Bundle ONNX models
import glob as _glob
for _f in _glob.glob('models/onnx/*.onnx'):
    _datas.append((_f, 'models/onnx'))
# Bundle .pt models as fallback
for _f in _glob.glob('models/*.pt'):
    _datas.append((_f, 'models'))
for _f in _glob.glob('experiments/*/weights/*.pt'):
    _datas.append((_f, 'models'))
```

- [x] **Step 4: 提交**
```bash
git add InsightClass.spec
git commit -m "feat: spec excludes PyTorch, includes ONNX Runtime — reduced package size"
```

---

## Task 6: 更新依赖 ✅

**修改:** `pyproject.toml`

- [x] **Step 1: 添加 onnxruntime 依赖**

在 `web` 依赖中添加：
```
"onnxruntime>=1.17",
```

- [x] **Step 2: 提交**
```bash
git add pyproject.toml
git commit -m "feat: add onnxruntime dependency"
```

---

## Task 7: 删除实验页面 ✅

**修改:** `frontend/src/App.tsx`

- [x] **Step 1: 删除实验路由和导航**

```tsx
import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import Detection from './pages/Detection'
import Dashboard from './pages/Dashboard'
import './App.css'

function App() {
  return (
    <BrowserRouter>
      <div className="app">
        <nav className="app-nav">
          <NavLink to="/" end>检测</NavLink>
          <NavLink to="/dashboard">仪表盘</NavLink>
        </nav>
        <main className="app-main">
          <Routes>
            <Route path="/" element={<Detection />} />
            <Route path="/dashboard" element={<Dashboard />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}

export default App
```

- [x] **Step 2: 提交**
```bash
git add frontend/src/App.tsx
git commit -m "feat: remove Experiments page from navigation and routing"
```

---

## Task 8: 优化仪表盘响应式 ✅

**修改:** `frontend/src/pages/Dashboard.tsx` + `frontend/src/components/dashboard/Dashboard.module.css`

- [x] **Step 1: 添加 pywebview 窗口适配**

在 Dashboard.module.css 中添加针对小窗口的媒体查询：
```css
/* pywebview window adaptation */
@media (max-width: 1200px) {
  .chartGrid { grid-template-columns: 1fr 1fr; }
  .cameraGrid { grid-template-columns: repeat(3, 1fr); }
}
@media (max-width: 900px) {
  .chartGrid { grid-template-columns: 1fr; }
  .cameraGrid { grid-template-columns: repeat(2, 1fr); }
  .summaryCards { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 600px) {
  .cameraGrid { grid-template-columns: 1fr; }
  .summaryCards { grid-template-columns: 1fr; }
}
```

- [x] **Step 2: 确保图表和卡片不溢出**

检查 Chart.js 图表是否需要 `responsive: true` 和 `maintainAspectRatio: false`。

- [x] **Step 3: 提交**
```bash
git add frontend/src/pages/Dashboard.tsx frontend/src/components/dashboard/Dashboard.module.css
git commit -m "fix: improve Dashboard responsive design for pywebview window"
```

---

## Task 9: 优化启动体验 ✅

**修改:** `src/insightclass/web/launcher.pyw`

- [x] **Step 1: 添加进度提示到加载页面**

在 `_LOADING_HTML` 中添加动态状态文字：
```javascript
const steps = ['正在加载推理引擎...', '正在初始化模型...', '正在启动服务...'];
let i = 0;
setInterval(() => {
  document.getElementById('status').textContent = steps[i % steps.length];
  i++;
}, 2000);
```

- [x] **Step 2: 减少等待超时**

将 `wait_for_server` 的超时从 60 秒改为 30 秒（ONNX 加载更快）。

- [x] **Step 3: 提交**
```bash
git add src/insightclass/web/launcher.pyw
git commit -m "fix: improve launcher loading animation with progress steps"
```

---

## Task 10: 适配海康 CSV 导入 ✅

**修改:** `src/insightclass/web/server.py` — `import_cameras_csv` 函数

- [x] **Step 1: 改进 CSV 解析逻辑**

替换现有的 `import_cameras_csv` 函数，提取更多信息：

```python
@app.post("/api/cameras/import")
async def import_cameras_csv(file: UploadFile = File(...)):
    """上传 CSV 文件批量导入摄像头（支持海康威视导出格式）。

    海康 CSV 格式（GB2312/GBK 编码）：
    名称, 添加模式, 地址, 端口, 设备信息(序列号), 用户名, 密码, ...
    """
    try:
        contents = await file.read()

        # 尝试多种编码解码
        text = None
        for encoding in ['gb18030', 'gbk', 'gb2312', 'utf-8-sig', 'utf-8']:
            try:
                text = contents.decode(encoding)
                break
            except (UnicodeDecodeError, LookupError):
                continue
        if text is None:
            return JSONResponse({"error": "无法解码文件，请确保是 GB2312/GBK/UTF-8 编码的 CSV"}, status_code=400)

        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
        if len(rows) < 2:
            return JSONResponse({"error": "CSV 文件为空或只有表头"}, status_code=400)

        header = rows[0]

        # 自动检测列索引（兼容多种格式）
        ip_col, port_col, name_col, user_col, pass_col = _detect_csv_columns(header)

        if ip_col is None:
            return JSONResponse({"error": "CSV 中找不到 IP 地址列"}, status_code=400)

        existing_cameras = _load_custom_cameras()
        existing_ips = {c["ip"] for c in existing_cameras}
        imported = 0
        skipped = 0
        errors = []

        for row_idx, row in enumerate(rows[1:], start=2):
            if len(row) <= ip_col:
                continue
            ip = row[ip_col].strip()
            if not ip:
                continue
            if not re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ip):
                errors.append(f"第 {row_idx} 行: 无效 IP '{ip}'")
                continue
            if ip in existing_ips:
                skipped += 1
                continue

            # 提取额外信息
            # CSV 中的端口是 HTTP 管理端口(8000)，RTSP 端口固定 554
            device_name = row[name_col].strip() if name_col is not None and len(row) > name_col else ""
            username = row[user_col].strip() if user_col is not None and len(row) > user_col else ""
            password = row[pass_col].strip() if pass_col is not None and len(row) > pass_col else ""

            existing_cameras.append({
                "ip": ip,
                "name": device_name or ip,
                "group": "custom",
                "group_label": "自定义",
                "note": f"RTSP:554 用户:{username}" if username else "RTSP:554",
            })
            existing_ips.add(ip)
            imported += 1

        _save_custom_cameras(existing_cameras)
        return JSONResponse({
            "ok": True,
            "imported": imported,
            "skipped": skipped,
            "errors": errors[:10],
            "total": len(rows) - 1,
        })
    except Exception as e:
        logger.exception("CSV import error")
        return JSONResponse({"error": str(e)}, status_code=500)
```

- [x] **Step 2: 添加列检测辅助函数**

```python
def _detect_csv_columns(header: list[str]) -> tuple:
    """Detect column indices for IP, port, name, username, password.

    Returns (ip_col, port_col, name_col, user_col, pass_col).
    Any may be None if not found.
    """
    ip_col = port_col = name_col = user_col = pass_col = None

    for i, col in enumerate(header):
        col_s = col.strip().lower()
        if col_s in ('ip地址', 'ip', 'ip地址', '地址'):
            ip_col = i
        elif col_s in ('端口', 'port'):
            port_col = i
        elif col_s in ('名称', '设备名称', '设备信息'):
            name_col = i
        elif col_s in ('用户名', 'user', 'username'):
            user_col = i
        elif col_s in ('密码', 'password', 'pwd'):
            pass_col = i

    # Fallback: 海康格式 — IP 在第 0 列，端口在第 3 列
    if ip_col is None and len(header) >= 3:
        ip_col = 0  # 名称列就是 IP
    if port_col is None and len(header) >= 4:
        port_col = 3
    if name_col is None and len(header) >= 5:
        name_col = 4  # 设备序列号作为名称
    if user_col is None and len(header) >= 6:
        user_col = 5
    if pass_col is None and len(header) >= 7:
        pass_col = 6

    return ip_col, port_col, name_col, user_col, pass_col
```

- [x] **Step 3: 提交**
```bash
git add src/insightclass/web/server.py
git commit -m "feat: improve Hikvision CSV import — extract port, name, credentials"
```

---

## 验证清单

- [x] ONNX 模型导出成功（1 个 v2 .onnx 文件在 models/onnx/）
- [x] ONNX 推理端点工作正常
- [x] PyInstaller 打包成功（不含 PyTorch，包含 ONNX Runtime）
- [ ] 包体大小 < 500MB（需打包验证）
- [ ] exe 启动 < 10 秒（需打包验证）
- [x] 实验页面已删除
- [x] 仪表盘响应式正常
- [x] 海康 CSV 导入正常（提取 IP、端口、设备名、用户名）
- [ ] 所有测试通过（需运行测试验证）
