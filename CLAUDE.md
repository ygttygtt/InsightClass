# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

InsightClass is a classroom student behavior detection pipeline. It detects three behaviors from front-of-classroom camera footage: `phone_use` (玩手机), `talking` (交谈), `sleeping` (打瞌睡). The project follows a src-layout and is configured via YAML files.

**Conda environment**: `QF_DL` — all commands should run in this environment:
```
conda run -n QF_DL python ...
```

## Commands

```bash
# Install (editable, with optional extras)
pip install -e .[ultralytics,supervision,dev]

# Run tests
python -m pytest tests/

# CLI (either form works)
python -m insightclass <subcommand>
insightclass <subcommand>

# Environment check (PyTorch/CUDA/ultralytics)
python test_environment.py
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
```

## Architecture

### Backend Pattern (Strategy + Factory)

The central extensibility point. `backends/base.py` defines `DetectorBackend` ABC with 5 abstract methods (`train`, `validate`, `predict_images_or_video`, `load_predictions_as_sv_detections`, `export_artifacts`). `backends/factory.py` has `build_backend(name)` as the registry. Currently only `"ultralytics"` is registered. To add a new backend: implement the ABC, register in factory.py — data/evaluation/visualization code stays unchanged.

### Data Pipeline

Strictly sequential, CLI-driven:

1. **create-manifest** — scans `data/raw_videos/`, does VIDEO-level train/val/test split (fixed seed), outputs `manifest.yaml`
2. **extract-frames** — cv2 reads each video, samples at given FPS, resizes to `target_width` (default 960), saves JPGs to `images/{split}/`, writes `frame_index.csv`
3. **[manual annotation]** — external tool (Roboflow/CVAT/Label Studio), outputs YOLO format `.txt` to `labels/{split}/`
4. **inspect-yolo** — quality checks on labels (missing, empty, out-of-bounds, tiny boxes, class distribution)
5. **write-yolo-yaml** — generates Ultralytics-compatible dataset config
6. **train/validate/predict** — via selected backend, saves `experiment_record.json`
7. **compare-experiments** — flattens all experiment records into CSV

Video-level splitting is a key design decision to prevent data leakage. Same video must not appear in multiple splits.

### Optional Dependencies

Lazy-loaded via `optional.py` (`has_package` / `require_package` using `importlib.util.find_spec`). Core package works with just numpy + PyYAML + opencv-python. ultralytics and supervision are optional extras.

### Key Schemas (`schemas.py`)

All `@dataclass(slots=True)` with `to_dict()`: `DatasetManifest`, `TrainingConfig`, `InferenceConfig`, `ExperimentRecord`, `DetectionRecord`, `FramePrediction`.

### Config Files (`configs/`)

- `classes.yaml` — canonical class IDs and Chinese display names
- `dataset_manifest.example.yaml` — template for manifest creation (raw_videos_dir, split ratios, class config path)
- `training.ultralytics.example.yaml` — template for training (backend, weights, imgsz, epochs, batch, device)
- `inference.ultralytics.example.yaml` — template for inference (weights_path, source, confidence, IoU)

## Conventions

- Class IDs are always English (`phone_use`, `talking`, `sleeping`); display names are Chinese, maintained in `classes.yaml`
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