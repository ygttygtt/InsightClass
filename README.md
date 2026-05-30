# InsightClass 深见课堂

AI 赋能的智慧校园视觉中台，通过高精度行为特征检索重塑教与学的数字化洞察。

检测三类课堂行为：`phone_use`（玩手机）、`talking`（交谈）、`sleeping`（打瞌睡）。

## 快速开始

```bash
# 1. 克隆项目
git clone <repo-url>
cd InsightClass

# 2. 安装依赖（含 Web 前端）
pip install -e .[ultralytics,web]

# 3. 启动 Web 服务
insightclass serve --host 0.0.0.0 --port 8080
# 浏览器打开 http://localhost:8080
```

> **端口说明**：默认端口 8000。若 8000 被占用（如海康摄像头后台），改用 `--port 8080`。
>
> **摄像头配置**：`configs/cameras.yaml` 和 `configs/app.yaml` 由 Web 界面自动创建和管理，无需手动配置。

## 功能

- **RTSP 实时监控**：连接教室摄像头，实时查看画面
- **目标检测**：在监控画面上叠加 AI 检测框，识别玩手机/交谈/打瞌睡
- **图片/视频检测**：上传图片或视频文件进行离线分析
- **摄像头管理**：Web 界面添加/删除/测试摄像头连通性
- **模型管理**：支持多模型切换，可设默认模型

## 项目结构

```
configs/          # 配置文件（classes.yaml, 训练/推理模板）
data/             # 数据集（gitignored）
docs/             # 文档
experiments/      # 训练产物（gitignored）
src/insightclass/ # 源代码
  backends/       # 可替换检测后端（Strategy + Factory）
  web/            # FastAPI Web 前端
```

## 文档

| 文档 | 用途 |
|------|------|
| [00 项目指南](docs/00_project_guide.md) | 架构与设计决策 |
| [01 快速上手](docs/01_快速上手.md) | 数据→标注→训练→推理全流程 |
| [08 本地测试](docs/08_本地Demo测试.md) | 本地 Demo 验证 |
| [09 前端手册](docs/09_前端使用手册.md) | Web 前端功能说明 |
