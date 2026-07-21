# 项目指南（开发者向）

> 适用于 InsightClass `1.2.x`，最后更新：2026-07-21。

## 1. 项目定位

InsightClass 是课堂行为视觉分析应用，目标是提供从数据采集、标注、训练、评估
到桌面端实时推理的完整闭环。当前稳定识别 `phone_use`、`talking`、
`sleeping`、`standing` 四类行为。

当前产品范围：

- RTSP 和电脑摄像头实时监看与检测
- 图片、视频和批量视频离线检测
- 摄像头管理、在线状态、趋势统计和报表
- OpenAI 兼容大模型对统计结果进行总结
- ONNX Runtime 便携版推理
- Ultralytics 模型训练、验证、导出和实验比较
- Windows WebView 窗口、系统托盘和单实例生命周期
- 深色/浅色主题、统一品牌图标和 WebView 本地偏好缓存

当前不提供：

- 用户登录、租户隔离和细粒度权限
- 持久化数据库与跨设备统计同步
- 基于身份的人脸识别或学生个体追踪
- 可直接用于教学处分的自动决策

## 2. 设计原则

### 稳定类别 ID

训练和 API 使用英文 ID，中文仅用于展示：

| ID | 中文 |
|---|---|
| `phone_use` | 玩手机 |
| `talking` | 交谈 |
| `sleeping` | 打瞌睡 |
| `standing` | 站立 |

`configs/classes.yaml` 是类别定义的唯一来源。重命名或调整顺序会改变模型输出
语义，必须作为数据集和模型版本变更处理。

### 视频级数据划分

必须先按原始视频划分 train/val/test，再抽帧。同一课堂片段或同源连续视频不能
跨集合，否则相邻帧会造成数据泄漏并虚高评估指标。

### 后端分工

- `UltralyticsBackend`：开发和训练环境使用，支持 `.pt` 训练、验证和推理。
- `OnnxBackend`：Windows 发行版默认使用，避免携带 PyTorch/Ultralytics。
- `build_backend()`：通过名称延迟加载后端，保持核心工具依赖轻量。

新增后端时，应实现 `DetectorBackend` 抽象接口并在 `backends/factory.py` 注册，
不得让数据、评估和 Web 层直接依赖具体框架。

### 同源 Web 架构

React 生产文件由 FastAPI 托管，前端使用 `/api` 相对路径访问后端。桌面版只在
`127.0.0.1` 启动服务，并通过 pywebview 显示同一 Web 应用。开发模式的 Vite
代理指向本地 FastAPI 服务。

## 3. 目录与所有权

```text
configs/                  类别、训练模板和本地运行配置
assets/                   品牌母版、Windows ICO/版本资源和托盘图
data/                     原始视频与处理数据（不进入 Git）
docs/                     面向用户和开发者的正式文档
experiments/              训练产物（不进入 Git）
frontend/                 React、类型和 API 客户端
models/                   可跟踪的预训练与 ONNX 模型
scripts/                  录制、诊断、训练和打包工具
src/insightclass/
  backends/               推理/训练策略实现
  data/                   Manifest、抽帧与 YOLO 数据集工具
  evaluation/             实验记录与汇总
  utils/                  配置、路径和序列化工具
  visualization/          图片/视频标注渲染
  web/                    FastAPI、模型缓存、大模型客户端和桌面启动器
tests/                    Python 自动化测试
```

运行时可写文件位于应用目录：

- `configs/app.yaml`：默认模型、RTSP 凭据和大模型设置
- `configs/cameras.yaml`：用户摄像头列表
- `experiments/`：用户实验数据

以上文件均不应提交，也不应打入包含真实配置的 Release。
桌面 WebView 的主题和浏览器缓存位于 `configs/webview/`，同样属于可删除、不可提交
的本机运行数据。

## 4. 关键数据流

### 实时检测

```text
RTSP/Webcam -> 最新帧 -> /api/detect/* -> 模型推理 -> 检测框
                                             |
                                             +-> Dashboard 内存统计
```

每台 RTSP 摄像头拥有独立 `RtspStreamManager`。停止或切换摄像头时必须释放
`VideoCapture`；Webcam 切换来源时必须停止浏览器 `MediaStreamTrack`。

### 视频检测

服务端按视频帧生成带 `frame_index` 的结果，前端根据播放器当前时间换算帧号并
选择最近且不晚于当前帧的检测结果。不得按网络返回时机直接覆盖检测框。

### 大模型分析

Dashboard 将聚合统计和 24 小时趋势作为 JSON 上下文发送给
`/api/llm/analyze`。服务端使用固定系统约束，要求模型只依据提供的数据回答。
大模型不直接读取摄像头视频，也不参与检测框生成。

## 5. 安全边界

- 桌面后端只绑定 `127.0.0.1`；CLI 的 `0.0.0.0` 模式需要部署者自行加访问控制。
- RTSP 密码和 API Key 不通过 GET 返回明文，只返回是否已配置和尾部掩码。
- 摄像头、实验、模型和静态资源路径必须限制在允许目录内。
- 上传接口必须同时校验扩展名、解码结果、文件大小、像素数和批量数量。
- 日志不得打印含用户名/密码的完整 RTSP URL。
- Release 不得包含 `configs/app.yaml` 的真实内容、内部 IP、数据集或课堂视频。

## 6. 开发流程

安装开发依赖：

```powershell
python -m pip install -e ".[web,dev]"
Push-Location frontend
npm ci
Pop-Location
```

质量门槛：

```powershell
python -m pytest -q
ruff check src scripts tests
Push-Location frontend
npm run build
Pop-Location
```

涉及依赖或发行时增加 `npm audit --omit=dev --audit-level=high` 和 Windows 包冒烟
测试。测试规模应随风险扩大：共享 API、文件安全、进程生命周期和跨模块契约必须
补自动化测试。

## 7. 提交与版本

维护分支为 `main`，小改动验证成功后立即提交并推送。提交格式使用英文类型和
中文摘要，例如：

```text
fix: 修复 RTSP 停止后设备未释放
docs: 同步前端功能与 API 文档
build: 更新 Windows 便携版构建流程
```

Python 包、前端包、Git 标签和 Release 使用同一版本号。发布前更新
`CHANGELOG.md`，构建全新 ZIP，并验证附件校验值和 Release 指向的提交。

## 8. 相关文档

| 文档 | 适用场景 |
|---|---|
| [快速上手](01_快速上手.md) | 安装、体验与完整数据闭环 |
| [录制操作手册](02_录制操作手册.md) | 安全采集 RTSP 视频 |
| [标注规范](05_标注规范.md) | 四类行为的统一标签口径 |
| [实验手册](06_实验手册.md) | 可复现训练和模型比较 |
| [前端使用手册](08_前端使用手册.md) | Web/桌面操作与故障排查 |
| [打包与发行](09_打包与发行.md) | Windows Release 流程 |
| [整体架构](项目整体架构文档.md) | 模块、接口和运行时生命周期 |
