# InsightClass 深见课堂

AI 赋能的智慧校园视觉中台，通过高精度行为特征检索重塑教与学的数字化洞察。

检测四类课堂行为：`phone_use`（玩手机）、`talking`（交谈）、`sleeping`（打瞌睡）、`standing`（站立）。

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
> **HTTPS 模式**：局域网摄像头需要 HTTPS 才能使用浏览器摄像头，加 `--https` 参数自动生成自签名证书。
>
> **摄像头配置**：`configs/cameras.yaml` 和 `configs/app.yaml` 由 Web 界面自动创建和管理，无需手动配置。

### Windows 桌面便携版

```powershell
# 构建前端、后端和 Windows 桌面窗口，并生成 ZIP
.\scripts\build_package.ps1

# 已安装依赖时可跳过 pip 安装
.\scripts\build_package.ps1 -SkipDeps
```

构建结果为 `dist/InsightClass-Web/InsightClass.exe` 和
`InsightClass-Web.zip`。程序启动时会先显示加载界面，随后在同一窗口打开
Web 应用；关闭窗口仅隐藏到系统托盘，后端会继续运行。双击托盘图标或再次
运行 EXE 可唤醒窗口，使用托盘菜单中的“退出”才会结束后端。

运行桌面版需要 Windows 10/11 和 Microsoft Edge WebView2 Runtime（多数系统已
预装）。完整构建说明见 [09 打包与发行](docs/09_打包与发行.md)。

## 功能

- **RTSP 实时监控**：连接教室摄像头，实时查看画面（MJPEG 流）
- **目标检测**：在监控画面上叠加 AI 检测框，识别玩手机/交谈/打瞌睡/站立
- **摄像头检测**：从 RTSP 摄像头抓帧实时检测
- **图片/视频检测**：上传图片或视频文件进行离线分析
- **批量视频检测**：同时上传多个视频，后台异步处理，支持导出 CSV/JSON
- **摄像头管理**：Web 界面添加/删除/编辑/测试摄像头连通性
- **模型管理**：支持多模型切换，可设默认模型
- **Dashboard 统计**：各摄像头检测数据统计，支持导出报告
- **大模型分析**：支持 OpenAI 兼容的 Chat Completions API，可在设置中配置服务地址、模型和 API Key
- **桌面应用**：无控制台窗口，支持加载页、系统托盘保活和单实例唤醒

## CLI 命令

```bash
# 数据处理
insightclass create-manifest --config ... --output ...   # 创建数据集清单
insightclass extract-frames --manifest ... --fps 1.0     # 视频抽帧
insightclass inspect-yolo --dataset-root ... --output .. # 检查标注质量
insightclass write-yolo-yaml --dataset-root ... --output # 生成训练配置

# 训练推理
insightclass train --config configs/training.yaml        # 训练模型
insightclass validate --config ...                       # 验证模型
insightclass predict --config configs/inference.yaml     # 推理预测
insightclass render-first-frame --config ...             # 可视化第一帧

# 实验管理
insightclass compare-experiments --experiments-root experiments --output reports/summary.csv

# Web 服务
insightclass serve --host 0.0.0.0 --port 8000            # 主服务（摄像头+Dashboard）
insightclass serve --host 0.0.0.0 --port 8000 --https    # HTTPS 模式
```

## 项目结构

```
InsightClass/
├── configs/              # 配置文件
│   ├── classes.yaml      #   类别定义（4 种行为）
│   ├── cameras.yaml      #   摄像头配置（运行时生成）
│   └── app.yaml          #   应用配置（运行时生成）
├── data/                 # 数据集（gitignored）
├── docs/                 # 项目文档
├── experiments/          # 训练产物（gitignored）
├── scripts/              # 独立工具脚本
└── src/insightclass/     # 源代码
    ├── backends/         #   可替换检测后端（Strategy + Factory）
    ├── data/             #   数据处理模块
    ├── evaluation/       #   实验管理模块
    ├── visualization/    #   可视化模块
    ├── web/              #   Web 服务模块
    │   ├── server.py     #     FastAPI REST API（合并了旧 demo/experiment_viewer）
    │   ├── launcher.pyw  #     Windows 桌面启动器（WebView + 系统托盘）
    │   ├── model_cache.py#     模型缓存
    │   └── schemas.py    #     API 响应数据结构（Pydantic）
    └── utils/            #   工具函数
├── frontend/             # React 前端（TypeScript + Vite）
│   ├── src/
│   │   ├── pages/        #   Detection, Dashboard, Experiments
│   │   ├── components/   #   UI 组件
│   │   ├── api/          #   API 客户端
│   │   └── types/        #   TypeScript 类型
│   └── dist/             #   构建产物（gitignored）
```

## 文档

| 文档 | 用途 |
|------|------|
| [00 项目指南](docs/00_project_guide.md) | 架构与设计决策 |
| [01 快速上手](docs/01_快速上手.md) | 数据→标注→训练→推理全流程 |
| [02 录制操作手册](docs/02_录制操作手册.md) | 摄像头录制指南 |
| [03 视频处理手册](docs/03_视频处理手册.md) | 视频抽帧流程 |
| [04 标注工具手册](docs/04_X-AnyLabeling操作手册.md) | 标注工具使用指南 |
| [05 标注规范](docs/05_标注规范.md) | 标准化标注规则 |
| [06 实验手册](docs/06_实验手册.md) | 实验设计指南 |
| [07 服务器训练手册](docs/07_服务器训练手册.md) | GPU 服务器训练流程 |
| [08 前端使用手册](docs/08_前端使用手册.md) | Web 前端功能说明 |
| [项目整体架构文档](docs/项目整体架构文档.md) | 完整架构详解 |
