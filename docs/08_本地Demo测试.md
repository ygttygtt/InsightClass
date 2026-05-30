# 本地 Demo 测试教程

训练完成后，将模型权重下载到本地 Windows 笔记本，验证推理效果。

## 前置条件

- 服务器训练已完成，`best.pt` 已生成
- 本地已安装 Python 3.10+（conda 环境名：`insightclass`）
- 本地已克隆项目仓库并安装依赖

```bash
cd InsightClass
pip install -e .[ultralytics,web]
```

---

## 1. 下载模型权重

### 方法一：scp

```bash
# 在本地终端执行（Windows PowerShell / Git Bash 均可）
scp lb@服务器IP:/home/lb/GXQ/InsightClass/experiments/baseline_yolo11n_v2_e80/weights/best.pt ./best.pt
```

路径根据实际实验目录调整，可通过 SSH 查看：

```bash
ssh lb@服务器IP "ls /home/lb/GXQ/InsightClass/experiments/"
```

### 方法二：WinSCP / FileZilla

1. 连接服务器，导航到 `experiments/<实验名>/weights/`
2. 将 `best.pt` 拖拽到本地项目目录
3. 建议放到 `experiments/` 或 `demo/weights/` 下，路径不要含中文

---

## 2. 准备推理配置

复制模板并修改：

```bash
cp configs/inference.ultralytics.example.yaml configs/inference.demo.yaml
```

编辑 `configs/inference.demo.yaml`：

```yaml
backend: ultralytics
weights_path: best.pt                  # 改为本地 best.pt 的实际路径
source: demo/input/your_image.jpg      # 推理来源（图片/视频/目录）
output_dir: demo/output/               # 输出目录
confidence: 0.25
iou: 0.45
image_size: 960
device: cpu                            # 本地无 GPU，用 CPU
save_frames: false
save_video: true                       # 视频推理时改为 true
class_names:
  - phone_use
  - talking
  - sleeping
  - standing
extra_args: {}
```

准备测试素材：

```bash
# 创建输入目录，放入测试图片或视频
mkdir -p demo/input
# 将测试图片或视频复制到 demo/input/
```

---

## 3. 图片推理

```bash
python -m insightclass predict --config configs/inference.demo.yaml
```

结果保存在 `demo/output/`，包含标注后的图片。

---

## 4. 视频推理

修改配置文件中的 `source` 为视频路径：

```yaml
source: demo/input/classroom_clip.mp4
save_video: true
```

运行：

```bash
python -m insightclass predict --config configs/inference.demo.yaml
```

输出视频保存在 `demo/output/`。

---

## 5. 渲染预览

快速查看第一帧检测效果，无需跑完整推理：

```bash
python -m insightclass render-first-frame --config configs/inference.demo.yaml
```

会在 `demo/output/` 生成一张带标注框的预览图。

---

## 6. Web UI Demo（可选）

启动本地 Web 服务器：

```bash
python -m insightclass serve --host 0.0.0.0 --port 8080
```

> **端口说明**：默认端口 8000。若被占用（如海康摄像头后台），改用 `--port 8080`。

浏览器打开 `http://localhost:8080`，支持四种模式：

- **RTSP 实时监控**：连接教室摄像头，实时查看画面并叠加检测框
- **电脑摄像头**：使用笔记本摄像头实时检测
- **图片检测**：上传图片进行离线分析
- **视频检测**：上传视频文件，服务端推理后同步播放带标注的结果

> **摄像头配置**：`configs/cameras.yaml` 和 `configs/app.yaml` 由 Web 界面自动管理，点击左侧「添加摄像头」即可配置，无需手动编辑文件。

---

## 7. 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| 推理速度很慢 | CPU 推理本身就慢，正常现象 | demo 验证用 CPU 够用，批量处理请用 GPU |
| `FileNotFoundError: best.pt` | 权重路径写错 | 检查 `weights_path` 是否为相对于项目根目录的正确路径 |
| `ModuleNotFoundError: ultralytics` | 未安装可选依赖 | `pip install -e .[ultralytics]` |
| 标注框类别显示为数字而非中文 | `class_names` 未配置 | 确保配置文件中 `class_names` 包含 `standing`（V2 数据集新增） |
| 视频推理没有输出 | `save_video` 为 false | 改为 `true` |
| Web UI 摄像头打不开 | 浏览器权限问题 | 确保浏览器允许摄像头访问，建议用 Chrome |

---

**文档版本：** v1.0
**更新日期：** 2026-05-29
**适用数据集：** classroom_behavior_v2
