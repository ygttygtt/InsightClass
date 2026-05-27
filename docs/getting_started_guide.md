# InsightClass 快速上手指南

本指南面向首期 baseline 落地，目标是尽快打通一条可复用闭环：

1. 本地整理原始视频
2. 抽帧并标注三类目标行为
3. 导出 YOLO 数据集
4. 在有显卡的电脑上训练首个基线模型
5. 把权重下载回本机做离线视频推理和结果回放

这份文档特别回答三个核心问题：

- 学生行为能不能先用 YOLO 这种框标注方案做
- 正常听课的学生要不要标
- 首期标注到底怎么打才更稳

## 0. 当前项目状态

> **更新于 2026-05-27**

已完成：

- [x] 12 个课堂视频抽帧（每个视频 25 帧，共 300 张）
- [x] 使用 X-AnyLabeling 完成全部 300 张图片的标注
- [x] 数据集整理脚本 `scripts/prepare_dataset.py`（按视频级别随机切分，90% 训练 / 10% 测试）
- [x] 训练配置 `configs/training.yaml` 已就绪

数据集概况：

| 项目 | 数值 |
|------|------|
| 总帧数 | 300 |
| 训练集 | 275 帧（11 个视频） |
| 测试集 | 25 帧（1 个视频，随机选取） |
| phone_use 框数 | 193 (32.5%) |
| talking 框数 | 343 (57.8%) |
| sleeping 框数 | 57 (9.6%) |

**下一步：上传到有显卡的电脑训练。** 参见 [第 11 节](#11-上传到有显卡的电脑训练)。

### 快速命令（当前阶段）

```bash
# 1. 整理数据集（已执行过，如需重新整理可再跑）
conda run -n QF_DL python scripts/prepare_dataset.py

# 2. 训练（在有显卡的电脑上执行）
pip install -e .[ultralytics]
python -m insightclass train --config configs/training.yaml
```

## 1. 先回答你的关键疑问

### 1.1 学生行为检测能先用 YOLO 做吗

可以，但要明确它是首期 baseline，不是最终答案。

YOLO 本质上是目标检测模型，最擅长学“哪里有一个具有可见视觉模式的目标”。它不只适合杯子、手机、人脸这类物体，也可以学习“带有相对稳定外观特征的行为状态”，前提是这个行为在单帧里能被看出来。

对你这个项目来说：

- `phone_use` 最适合先做单帧检测，因为通常能看到手机、手部和低头注视关系。
- `sleeping` 可以先做单帧检测 baseline，因为趴桌、闭眼、头部下垂通常有稳定姿态特征。
- `talking` 能做，但会比前两类更难，因为它更接近时序行为，单帧里容易和“转头”“张嘴”“看同学”混淆。

所以首期建议不是“YOLO 一定能完美解决行为识别”，而是：

- 先把它当成最低成本、最快能形成比较基线的方案
- 用统一的框标注把数据和实验体系搭起来
- 跑完第一轮后再判断哪些类别需要升级成二阶段或时序方案

### 1.2 首期应该怎么框

不是框手机本身，也不是只框脸。

首期统一采用“行为主体框”：

- 以学生上半身为主
- 尽量把头、肩、手，以及与行为强相关的局部一起包进去
- 如果是 `phone_use`，尽量把手机也包含进框里

也就是说，标注的对象是“正在表现某种行为的学生”，不是单独的物品。

### 1.3 就按三个名字直接标吗

首期是的。

建议直接按这三个训练类 ID 标注：

- `phone_use`
- `talking`
- `sleeping`

中文业务含义分别对应：

- 玩手机
- 交谈
- 打瞌睡

这和当前项目配置 [classes.yaml](/E:/QianFengStudy/PythonProject/InsightClass/configs/classes.yaml) 一致，后续训练、推理、实验记录也都按这套类名走。

### 1.4 正常听课的学生要不要标

首期默认不标成一个检测类别。

原因很简单：

- 你当前项目更像“异常行为检测 baseline”，不是“所有状态闭集分类”。
- `认真听课` 的视觉边界很模糊，很容易和“发呆、低头记笔记、看书、看老师、短暂转头”混在一起。
- 如果把 `认真听课` 当成一个检测类，首批数据很容易把标签体系搞乱，反而拖慢三类异常行为的可学性。

首期推荐规则：

- 图里只有正常学生，没有目标异常行为：这张图保留为负样本，不给行为框。
- 图里既有正常学生，也有异常行为学生：只框异常行为学生。
- 不需要给每个正常学生都打一个 `attentive` 或 `normal` 框。

### 1.5 那正常学生完全没用吗

不是。

正常学生在首期里是“背景和负样本”的重要组成部分：

- 它们帮助模型学会“不是所有学生都属于异常行为”
- 它们帮助降低误检
- 它们是必须保留在训练图像里的

只是它们暂时不需要作为一个显式检测类去打框。

### 1.6 什么时候才需要加 `认真听课`

只有当你的目标变成下面这类需求时，才建议认真考虑：

- 统计全班多少人在认真听课
- 做“认真 / 不认真”的闭集状态识别
- 每个人都必须被分到某个状态

如果后续真的要做这件事，更合理的方向通常不是“直接加一个 `attentive` 检测类”，而是：

1. 先做人检测或人跟踪
2. 再对每个人做状态分类

也就是“检测人”与“判断行为/状态”分成两步。

## 2. 本地环境准备

当前建议使用 `conda` 环境 `QF_DL`。

### 2.1 安装项目依赖

```powershell
cd E:\QianFengStudy\PythonProject\InsightClass

pip install -e .
pip install -e .[ultralytics]
pip install -e .[dev]
pip install supervision
```

说明：

- `ultralytics` 用于训练与推理后端
- `supervision` 用于统一可视化和后处理
- 如果暂时不做可视化，`supervision` 可以后装

### 2.2 验证环境

```powershell
$env:PYTHONPATH="src"
python -m insightclass --help
python -m unittest discover -s tests -v
python test_environment.py
```

## 3. 原始视频准备

把原始视频放到：

```text
data/raw_videos/
```

支持格式：

- `.mp4`
- `.avi`
- `.mov`
- `.mkv`
- `.wmv`
- `.flv`

如需创建目录：

```powershell
New-Item -ItemType Directory -Force data\raw_videos | Out-Null
```

建议：

- 先用 5 到 10 个视频跑通流程
- 一个视频尽量只对应一个连续场景
- 如果一个课时被拆成多个片段，后续切分时要避免泄漏到不同 split

## 4. 生成 manifest 和视频级切分

先按视频切分 train / val / test，再抽帧。

```powershell
python -m insightclass create-manifest `
  --config configs/dataset_manifest.example.yaml `
  --output data/processed/classroom_behavior_v1/manifest.yaml
```

生成后会得到：

```text
data/processed/classroom_behavior_v1/manifest.yaml
```

这一步很重要，因为它固定了视频级 split，避免同一视频不同帧同时落到训练集和验证集。

## 5. 抽帧

```powershell
python -m insightclass extract-frames `
  --manifest data/processed/classroom_behavior_v1/manifest.yaml `
  --fps 1.0 `
  --max-frames-per-video 300
```

建议起步参数：

- `fps=1.0`
- `max_frames_per_video=200~300`

执行后会生成：

```text
data/processed/classroom_behavior_v1/
├─ frame_index.csv
└─ images/
   ├─ train/
   ├─ val/
   └─ test/
```

## 6. 标注策略

### 6.1 首期标什么

只标三类目标行为学生：

- `phone_use`
- `talking`
- `sleeping`

### 6.2 首期不标什么

首期不单独标：

- `normal`
- `attentive`
- `person`
- `student`

也不建议一开始同时做：

- 一套 `person` 框
- 一套行为框

那会明显增加标注成本和歧义，首轮 baseline 不划算。

### 6.3 单张图如何判断

- 图中只有正常学生：保留图片，不画行为框。
- 图中一个学生玩手机：框这个学生，类别 `phone_use`。
- 图中一个学生趴桌睡觉：框这个学生，类别 `sleeping`。
- 图中两个学生明显交谈：各自框选，类别都为 `talking`。
- 图中一个学生既低头看手机又与旁边人说话：首期只保留主行为，默认优先 `phone_use`。

### 6.4 标注框到底框哪里

统一采用“行为主体框”：

- 以上半身为核心
- 尽量包含头、肩、手
- `phone_use` 尽量把手机一起框入
- 不要只框手机
- 不要只框脸
- 不要过松把邻座大面积带进去

详细规则见 [annotation_spec.md](/E:/QianFengStudy/PythonProject/InsightClass/docs/annotation_spec.md)。

## 7. 推荐标注工具与流程

推荐工具：

- Roboflow
- CVAT
- Label Studio

如果你用 Roboflow，建议流程如下。

### 7.1 创建项目

- Project Type 选择 `Object Detection`
- 类别只建这三个：
  - `phone_use`
  - `talking`
  - `sleeping`

### 7.2 上传数据

不要只上传 `train`。

建议把以下三个目录都上传并保留 split 概念：

- `images/train`
- `images/val`
- `images/test`

如果平台不方便直接保留 split，就至少在本地记录好哪些图属于哪个 split，导出后再按原 split 放回本地目录。

### 7.3 标注顺序建议

建议按这个顺序来：

1. 先抽样 50 到 100 张图试标
2. 统一一轮判定标准
3. 再扩大到第一批正式标注
4. 跑首个 YOLO baseline
5. 用 baseline 结果辅助后续半自动预标注

### 7.4 标注注意事项

- 宁缺勿滥，不确定先不标
- `talking` 最容易漂，务必严格
- 后排小目标和遮挡样本要重点复查
- 如果某张图没有三类目标行为，不要删图，保留为负样本

## 8. 标注导出后的本地目录

导出 YOLO 标签后，运行 `scripts/prepare_dataset.py` 自动整理成：

```text
data/processed/classroom_behavior_v1/
├─ images/
│  ├─ train/    (275 张)
│  └─ test/     (25 张)
├─ labels/
│  ├─ train/    (275 个 txt)
│  └─ test/     (25 个 txt)
└─ yolo_dataset.yaml
```

> 注意：当前数据集只有 train 和 test 两个 split，没有 val。
> Ultralytics 训练时会自动从 train 中划分一部分作为 val。

YOLO 标签格式示例：

```text
0 0.500000 0.420000 0.260000 0.410000
1 0.270000 0.500000 0.220000 0.380000
```

说明：

- 每一行表示一个行为目标框
- 格式为 `class_id x_center y_center width height`
- 数值相对图片宽高归一化到 `0~1`

### 8.1 没有目标行为的图片怎么处理

这类图应该保留。

做法取决于你的标注平台导出方式：

- 有些平台会导出空 `.txt` 文件
- 有些平台不会生成对应标签文件

对当前项目来说，两种情况都可以接受，但更推荐保留空标签文件，便于后续管理。

## 9. 运行质检

```powershell
python -m insightclass inspect-yolo `
  --dataset-root data/processed/classroom_behavior_v1 `
  --class-config configs/classes.yaml `
  --output reports/dataset_inspection.json
```

重点看这些问题：

- 缺失标签文件
- 空标签文件
- 类别 ID 异常
- 框越界
- 极小框过多
- 类别分布明显失衡

如果 `talking` 的数量很多但质量不稳，宁可先删掉一部分模糊样本，也不要为了数量硬保留。

## 10. 生成 YOLO 数据配置

```powershell
python -m insightclass write-yolo-yaml `
  --dataset-root data/processed/classroom_behavior_v1 `
  --class-config configs/classes.yaml `
  --output data/processed/classroom_behavior_v1/yolo_dataset.yaml
```

## 11. 上传到有显卡的电脑训练

### 11.1 需要上传的文件

只需上传以下文件到训练机器：

```text
InsightClass/
├── configs/
│   ├── classes.yaml
│   └── training.yaml
├── data/
│   └── processed/
│       └── classroom_behavior_v1/
│           ├── images/
│           │   ├── train/   (275 张 jpg)
│           │   └── test/    (25 张 jpg)
│           ├── labels/
│           │   ├── train/   (275 个 txt)
│           │   └── test/    (25 个 txt)
│           └── yolo_dataset.yaml
├── src/
│   └── insightclass/
├── pyproject.toml
└── scripts/
```

不需要上传：`data/raw_videos/`、`data/annotation_batch_01/`、`data/labels_01/`、`experiments/`。

### 11.2 打包数据

在 PowerShell 下可以直接压缩：

```powershell
Compress-Archive `
  -Path data\processed\classroom_behavior_v1 `
  -DestinationPath data\processed\classroom_behavior_v1.zip `
  -Force
```

或打包整个项目（排除视频和临时文件）：

```powershell
# 先在 .gitignore 确认 data/raw_videos/ 已排除
git archive -o insightclass.zip HEAD
# 然后把 data/processed/ 单独加进去
```

### 11.3 在训练机器上安装和运行

```bash
# 1. 克隆项目
git clone https://gitee.com/ygttygtt/InsightClass.git
cd InsightClass

# 2. 安装依赖
pip install -e .[ultralytics]

# 3. 环境检查
python -m insightclass --help

# 4. 开始训练
python -m insightclass train --config configs/training.yaml
```

### 11.4 训练参数说明

当前配置 `configs/training.yaml`：

| 参数 | 值 | 说明 |
|------|------|------|
| model_weights | yolo11n.pt | YOLO11 nano，轻量快速 |
| image_size | 960 | 输入图片尺寸 |
| epochs | 80 | 训练轮数 |
| batch_size | 16 | 批次大小（显存不够可改 8） |
| device | 0 | GPU 编号 |
| patience | 30 | 早停轮数 |

如果显存不足（如 4GB 以下），修改 `configs/training.yaml`：

```yaml
batch_size: 8      # 或 4
image_size: 640    # 降低分辨率
```

### 11.5 Kaggle / Colab 训练

也可以上传到 Kaggle 或 Colab：

1. 新建 Dataset，上传 `classroom_behavior_v1.zip`
2. 新建 Notebook，开启 GPU
3. 克隆项目并安装依赖
4. 修改 `training.yaml` 中的 `data_config_path` 为 Kaggle 路径
5. 运行训练命令

## 12. 训练基线模型

直接用项目配置：

```bash
python -m insightclass train --config configs/training.yaml
```

当前配置（`configs/training.yaml`）：

- 模型：`yolo11n.pt`（YOLO11 nano，轻量快速）
- `imgsz=960`
- `epochs=80`
- `batch_size=16`
- `patience=30`（早停）

Kaggle 上需要把 `data_config_path` 改为 Kaggle 路径：

## 13. 下载训练结果

重点下载：

- `weights/best.pt`
- `weights/last.pt`
- `results.csv`
- `results.png`
- `confusion_matrix.png`
- `experiment_record.json`

建议保留完整 run 目录，方便后续实验比较。

## 14. 本机离线推理

修改 [inference.ultralytics.example.yaml](/E:/QianFengStudy/PythonProject/InsightClass/configs/inference.ultralytics.example.yaml)：

- `weights_path` 指向下载回来的 `best.pt`
- `source` 指向你的测试视频
- `output_dir` 指向输出目录

执行：

```powershell
python -m insightclass predict --config configs/inference.ultralytics.example.yaml
```

如果装了 `supervision`，还可以渲染首帧预览：

```powershell
python -m insightclass render-first-frame `
  --config configs/inference.ultralytics.example.yaml
```

## 15. 结果怎么判断

首期不要只盯着总 `mAP`。

更应该重点看：

- `phone_use` 是否已经能稳定抓到
- `sleeping` 是否和“低头写字”混淆严重
- `talking` 是否误检很多普通转头
- 后排小目标是否几乎全漏
- 演示视频主观效果是否可接受

也就是说，首期验收以“闭环跑通 + 类别行为有初步可学性”为主，不要过早设死精度线。

## 16. 下一步怎么升级

如果首轮结果显示：

- `phone_use` 效果不错
- `sleeping` 中等可用
- `talking` 很差

这并不奇怪。

推荐升级顺序：

1. 先继续优化标注质量和数据量
2. 调整 `imgsz`、模型规模、训练强度
3. 对 `talking` 重新收紧标注边界
4. 如果仍然差，再考虑二阶段方案

更重的二阶段方案通常是：

- 先做人检测 / 跟踪
- 再做人行为分类
- 或直接改成时序视频模型

## 17. 快速检查清单

开始前：

- [x] `QF_DL` 环境可用
- [x] `python -m insightclass --help` 正常
- [x] 视频已放到 `data/raw_videos`

数据准备后：

- [x] 抽帧完成（300 张，12 个视频各 25 帧）
- [x] 标注完成（使用 X-AnyLabeling）
- [x] 数据集已整理（`scripts/prepare_dataset.py`，按视频级别随机切分）
- [x] split 已固定（train=275, test=25）

训练后：

- [ ] 上传到有显卡的电脑
- [ ] `python -m insightclass train --config configs/training.yaml`
- [ ] `best.pt` 已保存
- [ ] 下载权重回本机
- [ ] 已完成本机离线推理

## 18. 常见问题

### Q1: `talking` 很难标，先不做行不行

可以。

如果第一轮你发现 `talking` 定义很飘，可以先只做：

- `phone_use`
- `sleeping`

等两类 baseline 稳定后，再把 `talking` 单独拉回来。

### Q2: 没有 `认真听课` 类别，会不会导致模型把所有人都预测成异常

不会自动这样。

只要训练图中包含大量正常学生背景，而这些学生没有被标成目标框，模型就会学到“不是所有学生都有目标行为”。

### Q3: 为什么不先做 `person + behavior`

因为首期你最需要的是快速验证数据、标签体系和基线可学性。

`person + behavior` 更强，但它会显著增加：

- 标注成本
- 代码复杂度
- 数据歧义

### Q4: 什么情况下应该放弃单帧 YOLO，改做二阶段或时序

如果出现下面这些情况，就该认真考虑升级：

- `talking` 长期误检高、召回低
- `sleeping` 和“低头写字”分不开
- 你需要按“每个学生”稳定统计全班状态
- 你需要做持续时间判断，而不是单帧状态判断

## 19. 配套文档

- [项目总指南](project_guide.md)
- [标注规范](annotation_spec.md)
- [实验手册](experiment_playbook.md)
