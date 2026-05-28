# 项目指导文档（开发者向）

## 1. 项目目标

InsightClass 用于教室前方摄像头场景下的学生行为检测，首期目标建立可复用、可比较、可扩展的基线闭环：

- 从原始视频整理成统一数据集
- 以单帧检测方式识别 `玩手机 / 交谈 / 打瞌睡`
- 模型后端与公共流程解耦，后续可替换 YOLO、RT-DETR、MMDetection 等

## 2. 首期范围与非范围

### 首期范围

- 视频级数据切分
- 抽帧
- YOLO 数据集格式
- Ultralytics 基线训练
- 单视频离线推理
- 统一实验记录

### 非首期范围

- 实时摄像头接入
- 在线服务部署
- 时序行为识别
- 音视频多模态融合

## 3. 环境职责分工

| 环境 | 职责 |
|------|------|
| 本机 (`<your-env-name>`) | 视频整理、数据集构建、质检、离线推理、可视化、实验汇总 |
| 远端 GPU (Colab/Kaggle) | 模型训练、验证、权重导出 |

## 4. 目录规范

```text
InsightClass/
├─ configs/
├─ docs/
├─ src/insightclass/
├─ tests/
├─ data/
│  ├─ raw_videos/       # 原始视频 & RTSP 录制输出
│  └─ processed/        # 按版本组织的数据集
├─ experiments/         # 训练产物
└─ reports/             # 质检报告、实验汇总
```

## 5. 类别命名规范

训练类别使用英文稳定 ID，中文展示名通过 `configs/classes.yaml` 维护：

| 训练ID | 中文 |
|--------|------|
| `phone_use` | 玩手机 |
| `talking` | 交谈 |
| `sleeping` | 打瞌睡 |

扩类时只新增英文 ID 和展示名，不修改已有类别 ID。如需重命名，应视为新数据版本。

## 6. 数据流水线设计要点

### 视频级切分（防泄漏）

必须先按视频切分 train/val/test，再抽帧。同一视频不能同时出现在多个 split。如果一个完整课时被拆成多个短视频，这些视频应视为一个泄漏风险组。

### 抽帧策略

首期默认 1 fps，可按课堂事件密度调整。保留 `video_id / timestamp / frame_index` 元信息，对应 `frame_index.csv`。

### 标注原则

- 只标三类异常行为学生（`phone_use`, `talking`, `sleeping`）
- 正常听课学生不标，作为负样本背景
- 首期统一采用"行为主体框"（以上半身为主，不是只框手机或脸）

详细规则见 [05_标注规范.md](05_标注规范.md)。

## 7. 后端扩展（策略 + 工厂模式）

后端扩展点在：

- `src/insightclass/backends/base.py` — `DetectorBackend` ABC
- `src/insightclass/backends/factory.py` — `build_backend(name)` 注册表

当前只注册了 `"ultralytics"`。新增后端步骤：

1. 实现 `DetectorBackend` 的 5 个抽象方法（`train`, `validate`, `predict_images_or_video`, `load_predictions_as_sv_detections`, `export_artifacts`）
2. 在 `factory.py` 中注册
3. 数据准备、质检、可视化、实验汇总代码不需任何改动

## 8. 实验管理

### 命名规范

`{stage}_{backend}_{weights}_{dataVersion}_{imgsz}_{epochs}_{tag}`

### 每次实验记录的内容

- 实验ID、时间、模型权重、数据版本、类别表
- 训练参数、核心指标（mAP50-95、各类别召回/精确）
- 失败现象、主观观察、是否进入下一轮

### 比较实验

```bash
python -m insightclass compare-experiments \
  --experiments-root experiments \
  --output reports/experiment_summary.csv
```

## 9. 新增行为类别

1. 更新 `configs/classes.yaml`
2. 更新 `docs/05_标注规范.md`
3. 对新类别补充标注
4. 重新运行质检
5. 重新生成 `yolo_dataset.yaml`
6. 启动新一轮实验

## 10. 常见问题

### Q1: 为什么不先做 person + behavior？

首期目标是快速验证数据、标签体系和基线可学性。person + behavior 会增加标注成本和代码复杂度，首轮不划算。

### Q2: 什么时候应该升级到二阶段或时序方案？

- `talking` 长期误检高、召回低
- `sleeping` 和"低头写字"分不开
- 需要按每个学生稳定统计全班状态
- 需要持续时间判断而非单帧快照

### Q3: 本机没有 GPU，为什么保留本机推理？

本机承担结果回放、标注质检、小规模验证、实验分析，CPU 即可完成。

## 参考文档

| 文档 | 面向 | 内容 |
|------|------|------|
| [01_快速上手.md](01_快速上手.md) | 使用者 | 环境搭建与快速体验 |
| [02_录制操作手册.md](02_录制操作手册.md) | 录制者 | RTSP 多路录制 |
| [03_视频处理手册.md](03_视频处理手册.md) | 数据处理 | 录制视频抽帧 |
| [04_X-AnyLabeling操作手册.md](04_X-AnyLabeling操作手册.md) | 标注者 | 标注工具使用 |
| [05_标注规范.md](05_标注规范.md) | 标注者 | 正反例定义、框选规则 |
| [06_实验手册.md](06_实验手册.md) | 实验者 | 实验设计与判断标准 |
