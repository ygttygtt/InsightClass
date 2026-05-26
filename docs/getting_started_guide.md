# InsightClass 项目启动指南

本指南将带你完成从零开始的完整流程：数据准备 → 标注 → 上传 Kaggle 训练 → 本地推理测试。

---

## 第一部分：本地环境准备

### 1.1 安装项目依赖

```powershell
# 进入项目目录
cd e:\QianFengStudy\PythonProject\InsightClass

# 安装项目本身（基础依赖）
pip install -e .

# 安装 YOLO 后端
pip install -e .[ultralytics]

# 安装可视化支持（可选，用于结果渲染）
pip install supervision

# 安装开发依赖（用于测试）
pip install -e .[dev]
```

### 1.2 验证安装

```powershell
# 测试 CLI 是否可用
python -m insightclass --help

# 运行单元测试
python -m pytest tests/

# 测试环境（检查 PyTorch、CUDA 等）
python test_environment.py
```

---

## 第二部分：视频数据准备

### 2.1 视频存放位置

将你的原始视频放到以下目录：

```
InsightClass/
└─ data/
   └─ raw_videos/          ← 把视频放这里
      ├─ video_001.mp4
      ├─ video_002.mp4
      └─ ...
```

**创建目录：**
```powershell
mkdir -p data/raw_videos
```

### 2.2 支持的视频格式

项目支持以下格式（无需转换）：
- `.mp4` （推荐）
- `.avi`
- `.mov`
- `.mkv`
- `.wmv`
- `.flv`

**建议：**
- 如果视频格式不在上述列表，使用 FFmpeg 转换：
  ```powershell
  ffmpeg -i input.xxx -c:v libx264 output.mp4
  ```
- 视频分辨率不需要统一，抽帧时会保持原始分辨率
- 建议每个视频时长 1-10 分钟，太长可以切分

### 2.3 视频命名建议

```
data/raw_videos/
├─ class_a_001.mp4    # 可以按类别/场景命名
├─ class_a_002.mp4
├─ class_b_001.mp4
└─ random_name.mp4    # 任意命名也可以
```

---

## 第三部分：数据预处理（本地执行）

### 3.1 生成数据集清单

这一步会自动扫描 `data/raw_videos/` 目录，生成 train/val/test 切分。

```powershell
python -m insightclass create-manifest `
  --config configs/dataset_manifest.example.yaml `
  --output data/processed/classroom_behavior_v1/manifest.yaml
```

**执行后会生成：**
```
data/processed/classroom_behavior_v1/
└─ manifest.yaml    # 数据集清单，记录视频列表和切分信息
```

### 3.2 视频抽帧

从视频中按固定频率提取图片帧：

```powershell
python -m insightclass extract-frames `
  --manifest data/processed/classroom_behavior_v1/manifest.yaml `
  --fps 1.0 `
  --max-frames-per-video 300
```

**参数说明：**
- `--fps 1.0`：每秒提取 1 帧（可根据需要调整，0.5-2.0 都可以）
- `--max-frames-per-video 300`：每个视频最多提取 300 帧（防止太长的视频产生太多图片）

**执行后会生成：**
```
data/processed/classroom_behavior_v1/
├─ manifest.yaml
├─ frame_index.csv          # 帧索引记录
└─ images/
   ├─ train/
   │  ├─ video_001_f000000.jpg
   │  ├─ video_001_f000030.jpg
   │  └─ ...
   ├─ val/
   │  └─ ...
   └─ test/
      └─ ...
```

---

## 第四部分：数据标注

### 4.1 推荐工具：Roboflow

**为什么推荐 Roboflow：**
- 在线平台，无需部署
- 有免费额度（每月 1000 张图片）
- 支持导出 YOLO 格式
- 界面友好，适合新手
- 网址：https://roboflow.com

### 4.2 标注流程

#### 步骤 1：注册 Roboflow 账号
访问 https://roboflow.com 注册免费账号

#### 步骤 2：创建项目
1. 点击 "Create New Project"
2. 项目类型选择 "Object Detection"
3. 命名为 `InsightClass-Behavior`
4. 添加类别：
   - `phone_use`（玩手机）
   - `talking`（交谈）
   - `sleeping`（打瞌睡）

#### 步骤 3：上传图片
1. 将 `data/processed/classroom_behavior_v1/images/train/` 目录下的图片上传
2. 建议先上传 50-100 张进行试标

#### 步骤 4：开始标注
按照 [annotation_spec.md](annotation_spec.md) 的规范进行标注：
- 框选学生上半身
- 选择对应的类别
- 同一学生同一帧只标一个主行为

#### 步骤 5：导出标注
1. 标注完成后，点击 "Export"
2. 格式选择 "YOLO"
3. 下载压缩包

### 4.3 标注规范摘要

| 类别 | 说明 | 正例 | 反例 |
|------|------|------|------|
| `phone_use` | 玩手机 | 手机可见且学生正在操作 | 手机在桌上/口袋里 |
| `talking` | 交谈 | 明显侧头交流、嘴部动作 | 单纯转头/打哈欠 |
| `sleeping` | 打瞌睡 | 趴桌、闭眼、头部下垂 | 低头写字 |

**标注原则：宁缺勿滥，不确定不标**

### 4.4 标注后目录结构

将导出的标注文件放到对应位置：

```
data/processed/classroom_behavior_v1/
├─ images/
│  ├─ train/
│  │  ├─ video_001_f000000.jpg
│  │  └─ ...
│  ├─ val/
│  └─ test/
├─ labels/                  ← 标注文件放这里
│  ├─ train/
│  │  ├─ video_001_f000000.txt    ← 与图片同名的 .txt 文件
│  │  └─ ...
│  ├─ val/
│  └─ test/
└─ manifest.yaml
```

**YOLO 标注格式（每个 .txt 文件）：**
```
0 0.5 0.4 0.2 0.3    # class_id x_center y_center width height
1 0.3 0.6 0.15 0.25
```

---

## 第五部分：数据质检

### 5.1 运行质检脚本

```powershell
python -m insightclass inspect-yolo `
  --dataset-root data/processed/classroom_behavior_v1 `
  --class-config configs/classes.yaml `
  --output reports/dataset_inspection.json
```

**质检内容：**
- 空标签检查
- 缺失标签检查
- 类别 ID 检查
- 框越界检查
- 极小框检查
- 类别分布统计

### 5.2 查看质检报告

```powershell
# 查看报告内容
cat reports/dataset_inspection.json
```

**重点关注：**
- `missing_labels`：有图片但没有对应标注文件
- `empty_labels`：标注文件存在但内容为空
- `out_of_bounds`：标注框超出图片边界
- `class_distribution`：各类别标注数量是否均衡

### 5.3 生成 YOLO 数据集配置

```powershell
python -m insightclass write-yolo-yaml `
  --dataset-root data/processed/classroom_behavior_v1 `
  --class-config configs/classes.yaml `
  --output data/processed/classroom_behavior_v1/yolo_dataset.yaml
```

**执行后会生成：**
```
data/processed/classroom_behavior_v1/
└─ yolo_dataset.yaml    # Kaggle 训练时需要的配置文件
```

---

## 第六部分：打包上传到 Kaggle

### 6.1 创建 Kaggle 数据集

#### 步骤 1：打包数据
```powershell
# 进入数据目录
cd data/processed

# 打包成 zip（Windows 可以用压缩工具）
tar -a -c -f classroom_behavior_v1.zip classroom_behavior_v1
```

或者直接用文件资源管理器压缩 `classroom_behavior_v1` 文件夹。

#### 步骤 2：上传到 Kaggle
1. 访问 https://www.kaggle.com/datasets
2. 点击 "New Dataset"
3. 上传 `classroom_behavior_v1.zip`
4. 命名为 `classroom-behavior-v1`
5. 设置为 Private（仅自己可见）
6. 点击 "Create"

### 6.2 创建 Kaggle Notebook

1. 访问 https://www.kaggle.com/code
2. 点击 "New Notebook"
3. 在右侧 "Settings" 中：
   - **Accelerator**: 选择 GPU（T4 或 P100）
   - **Data Sources**: 添加刚才上传的数据集

---

## 第七部分：Kaggle 训练

### 7.1 Notebook 代码

在 Kaggle Notebook 中按顺序执行以下代码：

#### Cell 1: 安装依赖
```python
!pip install ultralytics
```

#### Cell 2: 加载数据
```python
import os

# Kaggle 数据路径
DATASET_PATH = "/kaggle/input/classroom-behavior-v1/classroom_behavior_v1"
print(f"数据集路径: {DATASET_PATH}")
print(f"文件列表: {os.listdir(DATASET_PATH)}")
```

#### Cell 3: 训练模型
```python
from ultralytics import YOLO

# 加载预训练模型
model = YOLO("yolo11n.pt")

# 开始训练
results = model.train(
    data=f"{DATASET_PATH}/yolo_dataset.yaml",
    imgsz=960,
    epochs=80,
    batch=16,
    device=0,  # 使用 GPU
    project="/kaggle/working/experiments",
    name="baseline_yolo11n_v0_1_e80",
    pretrained=True,
    patience=30,
    plots=True,
)
```

#### Cell 4: 验证模型
```python
# 在验证集上评估
metrics = model.val()
print(f"mAP50: {metrics.box.map50:.4f}")
print(f"mAP50-95: {metrics.box.map:.4f}")
```

#### Cell 5: 测试推理
```python
# 用测试图片测试
import glob

test_images = glob.glob(f"{DATASET_PATH}/images/test/*.jpg")[:5]
if test_images:
    results = model.predict(
        source=test_images[0],
        conf=0.25,
        save=True,
        project="/kaggle/working/predictions",
        name="test",
    )
    print(f"预测完成，结果保存在 /kaggle/working/predictions/test/")
```

### 7.2 训练时间参考

| GPU | 数据量 | Epochs | 预计时间 |
|-----|--------|--------|----------|
| T4 | 500 张 | 80 | 15-30 分钟 |
| T4 | 2000 张 | 80 | 1-2 小时 |
| P100 | 500 张 | 80 | 10-20 分钟 |

---

## 第八部分：下载训练结果

### 8.1 下载内容

训练完成后，从 Kaggle 下载以下文件：

```
experiments/baseline_yolo11n_v0_1_e80/
├─ weights/
│  ├─ best.pt           ← 最佳模型权重（必须下载）
│  └─ last.pt           ← 最后一轮权重
├─ results.csv          ← 训练指标
├─ results.png          ← 训练曲线图
├─ confusion_matrix.png ← 混淆矩阵
└─ args.yaml            ← 训练参数
```

### 8.2 放到本地项目

```
InsightClass/
└─ experiments/
   └─ baseline_yolo11n_v0_1_e80/
      └─ weights/
         └─ best.pt    ← 放到这里
```

---

## 第九部分：本地推理测试

### 9.1 修改推理配置

编辑 `configs/inference.ultralytics.example.yaml`：

```yaml
backend: ultralytics
weights_path: experiments/baseline_yolo11n_v0_1_e80/weights/best.pt  # 指向下载的权重
source: demo/input/test_video.mp4  # 你的测试视频
output_dir: demo/output/test_result
confidence: 0.25
iou: 0.45
image_size: 960
device: cpu  # 本地用 CPU
save_frames: false
save_video: true
class_names:
  - phone_use
  - talking
  - sleeping
```

### 9.2 执行推理

```powershell
python -m insightclass predict --config configs/inference.ultralytics.example.yaml
```

### 9.3 可视化结果（可选）

```powershell
python -m insightclass render-first-frame --config configs/inference.ultralytics.example.yaml
```

---

## 快速检查清单

开始前确认：

- [ ] Python 3.10+ 已安装
- [ ] 项目依赖已安装（`pip install -e .[ultralytics]`）
- [ ] 视频已放到 `data/raw_videos/` 目录
- [ ] 视频格式为 mp4/avi/mov/mkv/wmv/flv

数据准备阶段：

- [ ] `create-manifest` 执行成功
- [ ] `extract-frames` 执行成功，图片已生成
- [ ] 图片已上传到 Roboflow 并完成标注
- [ ] 标注文件已放到 `labels/` 目录
- [ ] `inspect-yolo` 质检通过
- [ ] `write-yolo-yaml` 生成配置文件

Kaggle 训练阶段：

- [ ] 数据集已上传到 Kaggle
- [ ] Notebook 已创建并配置 GPU
- [ ] 训练完成，mAP50 达到预期（建议 > 0.5）
- [ ] `best.pt` 已下载到本地

本地测试阶段：

- [ ] 推理配置已修改
- [ ] 推理命令执行成功
- [ ] 输出视频/图片已生成

---

## 常见问题

### Q1: 视频太多怎么办？
可以先用少量视频（5-10 个）跑通流程，再逐步增加数据。

### Q2: 标注太慢怎么办？
- 先标注 100-200 张，训练一个初始模型
- 用初始模型预测未标注图片，人工修正
- 逐步扩大数据集

### Q3: mAP 太低怎么办？
- 增加标注数据量
- 检查标注质量（质检报告）
- 尝试更大的模型（yolo11s.pt, yolo11m.pt）
- 调整超参数（epochs, image_size）

### Q4: Kaggle 训练超时怎么办？
- 减少 epochs 数量
- 减小 image_size（960 → 640）
- 增大 batch_size（如果 GPU 显存足够）

---

## 技术支持

如有问题，请参考：
- [项目指导文档](project_guide.md)
- [标注规范](annotation_spec.md)
- [实验手册](experiment_playbook.md)
