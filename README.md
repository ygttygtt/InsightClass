<p align="center">
  <img src="assets/insightclass-mark.svg" width="96" height="96" alt="InsightClass 深见课堂标志">
</p>

# InsightClass 深见课堂

[![Release](https://img.shields.io/github/v/release/ygttygtt/InsightClass?display_name=tag)](https://github.com/ygttygtt/InsightClass/releases/latest)
[![License](https://img.shields.io/github/license/ygttygtt/InsightClass)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![Platform](https://img.shields.io/badge/Desktop-Windows%2010%2F11-0078D4?logo=windows)](docs/09_打包与发行.md)

InsightClass 是面向课堂场景的开源视觉分析应用，提供 RTSP/电脑摄像头实时检测、
图片与视频分析、监控统计和 OpenAI 兼容大模型总结能力。Windows 便携版将 React
前端、FastAPI 后端、ONNX 推理和桌面窗口打包在一起，无需单独安装 Python。

当前识别四类课堂行为：

| 类别 ID | 展示名称 |
|---|---|
| `phone_use` | 玩手机 |
| `talking` | 交谈 |
| `sleeping` | 打瞌睡 |
| `standing` | 站立 |

## 功能

- RTSP 摄像头监看、连接状态、断线重连和实时检测框
- 电脑摄像头实时检测，并在停止时释放媒体设备
- 图片、单视频和多视频批量检测，支持结果回放与 CSV/JSON 导出
- 真实摄像头在线状态、行为计数、24 小时内存趋势和报表导出
- ONNX Runtime 发行版推理，以及开发环境中的 Ultralytics 训练/验证
- OpenAI Chat Completions 兼容配置、连接测试和课堂统计分析
- Windows WebView 独立窗口、快速加载页、系统托盘保活和单实例唤醒
- 深色/浅色主题、系统主题首次跟随和跨启动偏好保存
- 统一的 EXE、任务栏、标题栏、托盘及 Web 品牌图标
- 上传大小/类型限制、路径边界校验和凭据脱敏

## 获取应用

Windows 用户可从 [GitHub Releases](https://github.com/ygttygtt/InsightClass/releases/latest)
下载 `InsightClass-Windows-x64-v<版本>.zip`（当前为
`InsightClass-Windows-x64-v1.2.1.zip`）：

1. 将 ZIP 完整解压到可写目录。
2. 双击 `InsightClass.exe`。
3. 可右键 EXE 选择“发送到 -> 桌面快捷方式”，不要把 EXE 单独移出发行目录。
4. 首次使用时，在设置中填写 RTSP 凭据；应用不内置任何摄像头密码。

当前只维护这一种 Windows 桌面便携包。旧 Release 中的 `InsightClass.zip` 和
`InsightClass-Web.zip` 是不同时期的旧命名，不是“普通版”和“Web 版”两套产品；
桌面窗口始终复用同一套 React Web 页面和本地 FastAPI 后端。

运行要求为 Windows 10/11 和 Microsoft Edge WebView2 Runtime。关闭主窗口只会
隐藏到系统托盘；从托盘选择“退出”才会结束后端。发行版采用 onedir 目录模式，
启动时无需先把依赖解压到临时目录；`_internal/` 是必需的运行资源。
双击后先显示 WebView 窗口和监控台骨架，再异步启动托盘、本地服务和推理模块；
API 就绪即进入主界面，模型继续在后台加载并显示真实状态。

## 从源码运行

### Web 应用

```powershell
git clone https://github.com/ygttygtt/InsightClass.git
Set-Location InsightClass

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[web]"

Push-Location frontend
npm ci
npm run build
Pop-Location

insightclass serve --host 127.0.0.1 --port 8000
```

浏览器访问 `http://127.0.0.1:8000`。如需局域网访问，可使用 `--host 0.0.0.0`；
非 localhost 环境使用浏览器摄像头时需要 HTTPS，可增加 `--https` 生成本地自签名
证书。

### 训练与离线推理

```powershell
python -m pip install -e ".[ultralytics,web]"

insightclass train --config configs/training.ultralytics.example.yaml
insightclass validate --config configs/training.ultralytics.example.yaml
insightclass predict --config configs/inference.ultralytics.example.yaml
```

数据准备、标注和训练流程见 [快速上手](docs/01_快速上手.md)。

## 大模型配置

在“设置 -> 大模型分析”中填写兼容 OpenAI Chat Completions 的 Base URL、模型名、
API Key 和超时，并使用“测试连接”验证。配置成功后，可在监控大屏点击“AI 分析”
对当前统计和 24 小时趋势生成总结。

也可使用环境变量覆盖本机配置：

```powershell
$env:OPENAI_BASE_URL = "https://api.openai.com/v1"
$env:OPENAI_MODEL = "your-model"
$env:OPENAI_API_KEY = "your-api-key"
```

API Key 和 RTSP 密码保存在应用目录的 `configs/app.yaml`。该文件已被 Git 忽略，
设置接口只向前端返回脱敏状态。请勿把真实密钥提交到仓库或发布附件。

## 架构

```text
React + TypeScript
        |
        | HTTP / MJPEG
        v
FastAPI API + 静态资源托管
        |
        +-- ONNX Runtime / Ultralytics
        +-- OpenCV RTSP 与媒体处理
        +-- OpenAI 兼容分析客户端
        |
pywebview 桌面窗口 + pystray 系统托盘
```

详细模块、配置和 API 契约见 [项目整体架构文档](docs/项目整体架构文档.md)。

## 项目结构

```text
InsightClass/
|-- configs/                 # 类别、训练模板和本地运行配置
|-- assets/                  # Logo、ICO、托盘图和 Windows 版本信息
|-- docs/                    # 使用、训练、架构与发行文档
|-- frontend/                # React + TypeScript 前端
|-- models/onnx/             # 发行版内置 ONNX 模型
|-- scripts/                 # RTSP、训练和打包工具
|-- src/insightclass/        # Python 包、推理后端和 Web 服务
|-- tests/                   # Python 自动化测试
|-- InsightClass.spec        # PyInstaller 配置
`-- pyproject.toml           # Python 包和依赖定义
```

## 开发与验证

```powershell
python -m pip install -e ".[web,dev]"
python -m pytest -q
ruff check src scripts tests

Push-Location frontend
npm ci --no-audit --no-fund
npm audit --omit=dev --audit-level=high
npm run build
Pop-Location
```

构建 Windows 便携版：

```powershell
.\scripts\build_package.ps1
# 已安装依赖时：.\scripts\build_package.ps1 -SkipDeps
```

品牌资产由 `python scripts/generate_brand_assets.py` 从确定性几何统一生成，不要只
手工替换某一个 PNG/ICO，否则桌面与 Web 图标会失去一致性。

完整发布检查见 [打包与发行](docs/09_打包与发行.md)。

## 文档

| 文档 | 内容 |
|---|---|
| [项目指南](docs/00_project_guide.md) | 开发范围、设计约束与质量门槛 |
| [快速上手](docs/01_快速上手.md) | 安装、数据、训练、推理和 Web 使用 |
| [录制操作手册](docs/02_录制操作手册.md) | 安全配置并录制 RTSP 摄像头 |
| [视频处理手册](docs/03_视频处理手册.md) | 视频切分、抽帧与元数据 |
| [X-AnyLabeling 手册](docs/04_X-AnyLabeling操作手册.md) | 标注工具与辅助模型配置 |
| [标注规范](docs/05_标注规范.md) | 四类行为定义和质检规则 |
| [实验手册](docs/06_实验手册.md) | 可复现实验设计与比较 |
| [服务器训练手册](docs/07_服务器训练手册.md) | GPU 服务器训练流程 |
| [前端使用手册](docs/08_前端使用手册.md) | 检测、监控台、设置和故障排查 |
| [打包与发行](docs/09_打包与发行.md) | Windows 便携版构建与发布 |
| [整体架构](docs/项目整体架构文档.md) | 系统组件、数据流、API 和安全边界 |

## 贡献与安全

提交 Issue 或 Pull Request 前请阅读 [贡献指南](CONTRIBUTING.md)。安全问题不要公开
披露，请按 [安全策略](SECURITY.md) 提交私密报告。版本变化记录在
[CHANGELOG.md](CHANGELOG.md)。

## 许可证

本项目采用 [MIT License](LICENSE)。你可以在保留版权和许可声明的前提下使用、
复制、修改和分发本软件。

课堂视频可能包含个人信息。部署者应遵守所在地关于告知、授权、数据最小化、
保存期限和访问控制的法律及组织制度；检测或大模型输出不能替代人工判断。
