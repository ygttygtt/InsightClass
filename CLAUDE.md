# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

InsightClass is a classroom student behavior detection pipeline. It detects four behaviors from front-of-classroom camera footage: `phone_use` (玩手机), `talking` (交谈), `sleeping` (打瞌睡), `standing` (站立). The project follows a src-layout and is configured via YAML files.

**Conda environment**: 所有命令应在你的 conda 环境中运行（各成员环境名不同，以下用 `<your-env-name>` 代替）：
```
conda run -n <your-env-name> python ...
```

## Commands

```bash
# Install (editable, with optional extras)
pip install -e .[ultralytics,supervision,dev]
# With web frontend support
pip install -e .[ultralytics,web]

# Run tests
python -m pytest tests/

# CLI (either form works)
python -m insightclass <subcommand>
insightclass <subcommand>

# Environment check (PyTorch/CUDA/ultralytics)
python scripts/test_environment.py
```

### Packaging & Deployment

```powershell
# Build Windows .exe (PyInstaller + ZIP)
.\scripts\build_package.ps1
```

```bash
# Linux GPU server setup & training
bash scripts/server_setup.sh
bash scripts/server_train.sh [yolo11n|yolo26n] [bg]
```

### CLI Subcommands

```bash
# Data pipeline (sequential order)
insightclass create-manifest --config configs/dataset_manifest.example.yaml --output data/processed/.../manifest.yaml
insightclass extract-frames --manifest <path> --fps 1.0 --max-frames-per-video 300 --target-width 960
insightclass inspect-yolo --dataset-root <path> --class-config configs/classes.yaml --output reports/...
insightclass write-yolo-yaml --dataset-root <path> --class-config configs/classes.yaml --output <path>

# Training / inference (remote GPU for training, local CPU for inference)
insightclass train --config configs/training.ultralytics.example.yaml
insightclass validate --config <same>
insightclass predict --config configs/inference.ultralytics.example.yaml
insightclass render-first-frame --config <same>

# Experiment analysis
insightclass compare-experiments --experiments-root experiments --output reports/experiment_summary.csv

# Web servers
insightclass serve --host 0.0.0.0 --port 8000 --experiments-root experiments
insightclass serve --https  # auto-generates self-signed cert at configs/ssl/ (needed for webcam on LAN)
```

## Architecture

### Backend Pattern (Strategy + Factory)

The central extensibility point. `backends/base.py` defines `DetectorBackend` ABC with 5 abstract methods (`train`, `validate`, `predict_images_or_video`, `load_predictions_as_sv_detections`, `export_artifacts`). `backends/factory.py` has `build_backend(name)` as the registry. Two backends registered:
- `"ultralytics"` — PyTorch-based training + inference (GPU server)
- `"onnx"` — ONNX Runtime CPU-only inference (packaged exe, lightweight)

Training uses ultralytics on GPU server → exports `.onnx` → packaged exe uses onnx backend. To add a new backend: implement the ABC, register in factory.py.

### Data Pipeline

Strictly sequential, CLI-driven:

1. **create-manifest** — scans `data/raw_videos/`, does VIDEO-level train/val/test split (fixed seed), outputs `manifest.yaml`
2. **extract-frames** — cv2 reads each video, samples at given FPS, resizes to `target_width` (default 960), saves JPGs to `images/{split}/`, writes `frame_index.csv`. Uses seek-based extraction (doesn't decode every frame). Supports `max_frames_per_video` with uniform random sampling.
3. **[manual annotation]** — external tool (Roboflow/CVAT/Label Studio), outputs YOLO format `.txt` to `labels/{split}/`
4. **inspect-yolo** — quality checks on labels (missing, empty, out-of-bounds, tiny boxes, class distribution)
5. **write-yolo-yaml** — generates Ultralytics-compatible dataset config
6. **train/validate/predict** — via selected backend, saves `experiment_record.json`
7. **compare-experiments** — flattens all experiment records into CSV

Video-level splitting is a key design decision to prevent data leakage. Same video must not appear in multiple splits.

Implementation lives in `data/manifest.py` (discovery, split, manifest CRUD), `data/video_ops.py` (frame extraction), `data/yolo.py` (label inspection, YAML generation).

### Optional Dependencies

Lazy-loaded via `optional.py` (`has_package` / `require_package` using `importlib.util.find_spec`). Core package works with just numpy + PyYAML + opencv-python. ultralytics and supervision are optional extras.

### Web Frontend (`web/` + `frontend/`)

Single FastAPI app (`web/server.py`) serving a React SPA built with Vite.

| Layer | Technology | Purpose |
|---|---|---|
| Backend | FastAPI + Python | REST API for detection, cameras, dashboard |
| Frontend | React 18 + TypeScript + Vite | SPA with 2 pages: Detection, Dashboard |
| Styling | CSS Modules + dark theme | Component-scoped styles with shared CSS variables |
| Charts | Chart.js + react-chartjs-2 | Dashboard charts |
| Desktop | pywebview | Native window wrapping the web UI |

**Development:** `cd frontend && npm run dev` (Vite on :5173) + `insightclass serve` (API on :8000). Vite proxies `/api` to backend.

**Production:** `cd frontend && npm run build` → `frontend/dist/`. FastAPI serves the built SPA with catch-all routing for React Router.

**Desktop:** `src/insightclass/web/launcher.pyw` — pywebview launcher that starts FastAPI in a background thread and opens a native window. The launcher shows a loading animation immediately, then navigates to the app once the server is ready.

**Main server capabilities** (`insightclass serve`):
- **Camera detection**: `getUserMedia` → `POST /api/detect/frame` → Canvas overlay
- **Video upload**: `POST /api/detect/upload` → full inference → synced playback
- **RTSP streaming**: Persistent `RtspStreamManager` with auto-reconnect, MJPEG streaming (`/api/stream/rtsp`), and detection overlay (`/api/detect/rtsp`)
- **Batch detection**: Upload multiple videos → background worker → JSON/CSV export (`/api/detect/batch/*`)
- **Dashboard**: In-memory `DashboardStats` tracking per-camera counts, report export, simulated 24h history
- **Camera management**: CRUD APIs (`/api/cameras/*`) backed by `cameras.yaml`, CSV import for Hikvision format
- **RTSP credentials**: Global username/password/port stored in `app.yaml` via `/api/settings/rtsp-credentials`

Model caching via `model_cache.py` — supports both PyTorch (YOLO) and ONNX models. ONNX models are loaded with `onnxruntime` (CPU-only). The `_find_default_weights()` function prefers `.onnx` over `.pt` for faster startup. Weights path is validated to restrict file access (`_validate_weights_path`).

`web/schemas.py` defines Pydantic API models (`DetectionOut`, `FrameDetectionResponse`, `BatchJob`, etc.) — separate from the core `schemas.py` which uses dataclasses.

### Key Schemas (`schemas.py`)

All `@dataclass(slots=True)` with `to_dict()`: `DatasetManifest`, `TrainingConfig`, `InferenceConfig`, `ExperimentRecord`, `DetectionRecord`, `FramePrediction`.

### Config Files (`configs/`)

- `classes.yaml` — canonical class IDs (4 classes: `phone_use`, `talking`, `sleeping`, `standing`) and Chinese display names
- `dataset_manifest.example.yaml` — template for manifest creation (raw_videos_dir, split ratios, class config path)
- `training.ultralytics.example.yaml` — template for training (backend, weights, imgsz, epochs, batch, device)
- `inference.ultralytics.example.yaml` — template for inference (weights_path, source, confidence, IoU)
- `cameras.yaml` — persisted camera list (IP, name, group); managed via web UI
- `app.yaml` — persisted app settings (default_model path, rtsp_credentials)
- `ssl/` — self-signed certificate directory (auto-generated on `serve --https`)
- `inference.yaml`, `training.yaml` — actual working configs (not examples)
- `inference_baseline.yaml`, `training_v2_*` — experiment-specific configs

### Exceptions (`exceptions.py`)

Custom hierarchy: `InsightClassError` → `ConfigError`, `DependencyMissingError`. Used for config validation and optional dependency checks.

### Scripts (`scripts/`)

Standalone scripts outside the package, not installed:
- `record_multi_rtsp.py` — multi-camera RTSP recording with front/rear view grouping
- `rtsp_preview.py` — interactive RTSP camera preview (main/sub stream toggle)
- `sample_for_annotation.py` — random sampling from train images for external annotation

### Packaging

`InsightClass.spec` — PyInstaller spec for building a standalone Windows `.exe`. Resources (`configs/`, `models/onnx/`, `frontend/dist/`) are bundled as data files. PyTorch is excluded from the package (ONNX Runtime used instead). The `releases/` directory holds published versions.

**Build command:** `.\scripts\build_package.ps1` (or with flags: `-SkipDeps`, `-BuildInstaller`)

**Architecture:** pywebview native window → FastAPI (background thread) → ONNX Runtime inference. No browser needed, no PyTorch needed at runtime.

## Conventions

- Class IDs are always English (`phone_use`, `talking`, `sleeping`, `standing`); display names are Chinese, maintained in `classes.yaml`
- All experiment/run directories follow naming: `{stage}_{backend}_{weights}_{dataVersion}_{imgsz}_{epochs}_{tag}`
- Model weights (`*.pt`, `*.pth`), data directories, and experiment outputs are gitignored
- Tests use `unittest.TestCase` with `tempfile.TemporaryDirectory` for isolation
- No linter/formatter is currently configured

## 行为约束 (Core Constraints)
1. Think Before Coding (动手前先思考): 
   - 明确说出你的假设。如果需求不明确，必须停下来提问，不允许瞎猜。
   - 如果有多种方案，列出优缺点，不要默默帮用户做决定。

2. Simplicity First (至简至上): 
   - 只写能解决当前问题的最少代码，绝对禁止过度设计。
   - 没被要求的功能和可配置项一律不加。能用 50 行写完，就别写 200 行。

3. Surgical Changes (外科手术式修改): 
   - 像手术一样精准，只碰任务要求的代码。
   - 绝对不要去“顺手优化”或重构旁边没坏的代码，保持现有代码风格。

4. Goal-Driven Execution (目标驱动执行): 
   - 拒绝模糊指令，把任务变成可验证的目标。
   - 优先选择“先写一个能复现Bug的测试，再写代码让测试通过”的流程。

5. 给用户的说明性或询问性输出用中文