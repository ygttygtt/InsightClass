# 项目指导文档

## 1. 项目目标

本项目用于教室前方摄像头场景下的学生行为检测，首期目标是建立一个可复用、可比较、可扩展的基线闭环：

- 从原始视频整理成统一数据集
- 以单帧检测方式识别 `玩手机 / 交谈 / 打瞌睡`
- 在远端 GPU 环境完成训练
- 在本机 `QF_DL` 环境完成质检、回放、可视化和结果分析
- 把模型后端与公共流程解耦，后续可替换 YOLO、RT-DETR、MMDetection 等

## 2. 首期范围与非范围

### 首期范围

- 视频级数据切分
- 抽帧
- 标注规范
- YOLO 数据集格式
- Ultralytics 基线训练
- 单视频离线推理演示
- 统一实验记录

### 非首期范围

- 实时摄像头接入
- 在线服务部署
- 时序行为识别
- 音视频多模态融合
- 自动告警规则系统

## 3. 环境职责分工

### 本机环境

当前推荐使用 `conda` 环境 `QF_DL`，职责如下：

- 原始视频整理
- 数据集 manifest 生成
- 抽帧
- 标注后质检
- 导出 YOLO 数据配置
- 加载训练好的权重做离线视频推理
- 使用 `supervision` 做可视化回放
- 汇总实验结果

### 远端 GPU 环境

推荐优先支持：

- Google Colab
- Kaggle Notebook

职责如下：

- 模型训练
- 模型验证
- 推理结果生成
- 权重和指标产物导出

## 4. 目录规范

建议项目目录如下：

```text
InsightClass/
├─ configs/
├─ docs/
├─ src/insightclass/
├─ tests/
├─ data/
│  ├─ raw_videos/
│  └─ processed/
├─ experiments/
├─ reports/
└─ demo/
```

推荐数据目录：

```text
data/
├─ raw_videos/
│  ├─ class_a_001.mp4
│  ├─ class_a_002.mp4
│  └─ ...
└─ processed/
   └─ classroom_behavior_v1/
      ├─ manifest.yaml
      ├─ frame_index.csv
      ├─ images/
      │  ├─ train/
      │  ├─ val/
      │  └─ test/
      ├─ labels/
      │  ├─ train/
      │  ├─ val/
      │  └─ test/
      └─ yolo_dataset.yaml
```

## 5. 类别命名规范

训练类别建议使用英文稳定 ID：

- `phone_use`
- `talking`
- `sleeping`

中文展示名通过 [classes.yaml](/E:/QianFengStudy/PythonProject/InsightClass/configs/classes.yaml) 维护：

- `phone_use` => 玩手机
- `talking` => 交谈
- `sleeping` => 打瞌睡

扩类时只新增英文 ID 和展示名，不要直接改历史类名。

## 6. 原始视频切分原则

- 必须先按视频切分 train / val / test，再抽帧。
- 同一视频不能同时出现在多个 split。
- 如果一个完整课时被拆成多个短视频，这些视频最好仍视作一个泄漏风险组。
- 首批标注开始后，不再随意改 split。

生成 manifest 命令：

```powershell
python -m insightclass create-manifest `
  --config configs/dataset_manifest.example.yaml `
  --output data/processed/classroom_behavior_v1/manifest.yaml
```

## 7. 抽帧策略

首期建议：

- 默认 `1 fps` 或按课堂事件密度调整
- 对小规模试验可加 `--max-frames-per-video`
- 保留 `video_id / timestamp / frame_index` 元信息

命令：

```powershell
python -m insightclass extract-frames `
  --manifest data/processed/classroom_behavior_v1/manifest.yaml `
  --fps 1.0 `
  --max-frames-per-video 300
```

执行后会生成 `frame_index.csv`。

## 8. 标注流程

建议使用现成标注工具，例如：

- CVAT
- Label Studio
- Roboflow

推荐流程：

1. 先完成视频切分和抽帧
2. 只对 `images/train`、`images/val`、`images/test` 中的图像标注
3. 导出 YOLO 检测格式标签
4. 将标签按 split 放到 `labels/train|val|test`

判定边界详见 [annotation_spec.md](/E:/QianFengStudy/PythonProject/InsightClass/docs/annotation_spec.md)。

## 9. 数据质检流程

本项目当前质检脚本支持：

- 空标签检查
- 缺失标签检查
- 类别 ID 检查
- 框越界检查
- 极小框检查
- 类别分布统计
- 每个 split 的样例图列表

命令：

```powershell
python -m insightclass inspect-yolo `
  --dataset-root data/processed/classroom_behavior_v1 `
  --class-config configs/classes.yaml `
  --output reports/dataset_inspection.json
```

建议每轮标注后都运行一次，再抽样人工复核。

## 10. 生成 YOLO 数据集配置

命令：

```powershell
python -m insightclass write-yolo-yaml `
  --dataset-root data/processed/classroom_behavior_v1 `
  --class-config configs/classes.yaml `
  --output data/processed/classroom_behavior_v1/yolo_dataset.yaml
```

该文件会被 Ultralytics 训练直接读取。

## 11. 本机依赖安装建议

如果 `QF_DL` 缺少依赖，可按需安装：

```powershell
pip install -e .
pip install supervision
```

如果只想跑 YOLO 后端：

```powershell
pip install -e .[ultralytics]
```

如果需要本机回放和统一 `sv.Detections`：

```powershell
pip install -e .[ultralytics,supervision]
```

## 12. Colab 训练流程

### 推荐步骤

1. 上传或挂载数据集
2. 安装依赖
3. 把项目代码同步到运行环境
4. 用统一配置启动训练
5. 下载 `experiments/<run_name>` 产物目录

### Colab 安装示例

```python
!git clone <your-repo-url>
%cd InsightClass
!pip install -e .[ultralytics]
```

### 启动训练

```python
!python -m insightclass train --config configs/training.ultralytics.example.yaml
```

### 训练完成后下载

重点下载：

- `weights/best.pt`
- `weights/last.pt`
- `results.csv`
- `results.png`
- `confusion_matrix.png`
- `experiment_record.json`

## 13. Kaggle 训练流程

### 推荐步骤

1. 新建 Notebook
2. 将数据集作为 Input 挂载
3. 将项目代码上传或从 git 拉取
4. 安装依赖
5. 修改配置中的数据路径和输出路径
6. 执行统一命令训练

### Kaggle 安装示例

```python
!git clone <your-repo-url>
%cd InsightClass
!pip install -e .[ultralytics]
```

### 启动训练

```python
!python -m insightclass train --config configs/training.ultralytics.example.yaml
```

Kaggle 的输出目录建议指向 `/kaggle/working/experiments`。

## 14. 训练产物回本机

训练完成后，把整个 run 目录下载回本机，例如：

```text
experiments/
└─ baseline_yolo11n_v0_1_e80/
   ├─ weights/
   ├─ results.csv
   ├─ experiment_record.json
   └─ ...
```

只要权重和实验记录在，本机就可以继续做推理和比较。

## 15. 本机单视频推理

编辑 [inference.ultralytics.example.yaml](/E:/QianFengStudy/PythonProject/InsightClass/configs/inference.ultralytics.example.yaml)，把：

- `weights_path` 改成下载回来的权重
- `source` 改成待测试视频
- `output_dir` 改成输出目录

执行：

```powershell
python -m insightclass predict --config configs/inference.ultralytics.example.yaml
```

## 16. supervision 可视化回放

安装 `supervision` 后，可以将推理结果转成统一 `sv.Detections` 并渲染：

```powershell
python -m insightclass render-first-frame `
  --config configs/inference.ultralytics.example.yaml
```

当前脚手架先提供首帧渲染能力，后续可以继续扩展为整段视频统一渲染、跟踪和事件统计。

## 17. 读取实验结果并横向比较

每次训练结束后，后端会在对应 run 目录保存 `experiment_record.json`。

导出汇总表命令：

```powershell
python -m insightclass compare-experiments `
  --experiments-root experiments `
  --output reports/experiment_summary.csv
```

汇总表适合后续在 Excel、Pandas 或可视化工具中继续分析。

## 18. 如何新增一个行为类别

1. 更新 [classes.yaml](/E:/QianFengStudy/PythonProject/InsightClass/configs/classes.yaml)
2. 更新 [annotation_spec.md](/E:/QianFengStudy/PythonProject/InsightClass/docs/annotation_spec.md)
3. 对新类别补充标注
4. 重新运行质检
5. 重新生成 `yolo_dataset.yaml`
6. 启动新一轮实验

不要直接改已有类别 ID；如确实需要重命名，应视为新数据版本。

## 19. 如何新增一个模型后端

后端扩展点在：

- [base.py](/E:/QianFengStudy/PythonProject/InsightClass/src/insightclass/backends/base.py)
- [factory.py](/E:/QianFengStudy/PythonProject/InsightClass/src/insightclass/backends/factory.py)

新增模型时：

1. 新建一个实现 `DetectorBackend` 的后端类
2. 实现：
   - `train`
   - `validate`
   - `predict_images_or_video`
   - `load_predictions_as_sv_detections`
   - `export_artifacts`
3. 在 `factory.py` 注册
4. 保持公共数据结构和实验记录格式不变

这样数据准备、质检、可视化、实验汇总都不需要改。

## 20. 常见问题

### Q1: 本机没有 GPU，为什么还要保留本机推理能力？

因为本机主要承担：

- 结果回放
- 标注质检
- 小规模验证
- 实验分析

这些任务用 CPU 也能完成。

### Q2: `supervision` 没装会怎样？

不影响 manifest、抽帧、YOLO 质检、训练和基础推理。
会影响：

- 统一 `sv.Detections`
- 基于 `supervision` 的可视化渲染

### Q3: `talking` 和 `sleeping` 为什么不直接做时序模型？

因为首期目标是快速建立可比较的工程基线。等单帧检测的上限清楚后，再决定是否升级成：

- 人检测 + 行为分类
- 跟踪 + 时序识别
- 视频片段模型

### Q4: 第一阶段精度不高怎么办？

优先排查顺序：

1. 标注是否稳定
2. 类别定义是否过于模糊
3. 小目标是否需要更高 `imgsz`
4. 数据量是否不足
5. 是否该把复杂行为升级到二阶段方案
