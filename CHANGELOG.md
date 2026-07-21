# 更新日志

本项目的显著变更记录在此文件中。版本号遵循语义化版本，日期使用
`YYYY-MM-DD`。

## [1.2.0] - 2026-07-21

### 新增

- 新增 InsightClass 正式品牌标志和可重复生成脚本，输出 SVG、透明 PNG 及包含
  16/24/32/48/64/128/256 像素图层的 Windows ICO。
- 将统一图标应用到 EXE、任务栏、窗口标题栏、系统托盘、启动页、前端品牌区和
  浏览器 favicon。
- 新增深色/浅色主题切换，首次跟随系统偏好，并在浏览器及桌面 WebView 中跨启动
  保存选择。

### 改进

- 启动加载页同时适配系统深浅色外观，并提前展示正式品牌标志。
- Dashboard 图表的图例、坐标文字、网格和画布边框随主题同步，补充窄屏布局。
- 为 Windows EXE 增加产品名、文件说明、版权和 `1.2.0` 文件版本信息。
- 保持 PyInstaller onedir + ZIP 便携分发，避免 onefile 每次启动的临时解压开销。

### 修复

- 修复 Python 包版本残留为 `0.1.0`、大模型 User-Agent 单独写死造成的版本漂移。
- 修复桌面 WebView 临时会话导致主题偏好和前端缓存无法跨启动保留的问题。
- 修复浅色主题在 React 初始化前短暂显示深色背景的问题。
- 修复发行版从可写配置目录读取内置类别表，导致监控台中文类别名称为空的问题。
- 新增跨 Python、npm、lockfile 和 Windows 元数据的版本一致性测试。

## [1.1.0] - 2026-07-21

### 新增

- OpenAI Chat Completions 兼容配置、连接测试和课堂统计分析。
- Windows WebView 桌面窗口、启动加载页、系统托盘保活和单实例唤醒。
- 电脑摄像头实时检测、设备释放和错误状态反馈。
- 模型后台预加载及 `loading`、`ready`、`error` 状态展示。

### 修复

- 修复图片、视频上传字段名与后端契约不一致的问题。
- 修复 RTSP 状态显示、密码更新、连接重试和多摄像头流隔离。
- 修复 `object-fit: contain` 下实时检测框偏移，以及视频框与播放帧不同步。
- 修复 Dashboard 使用模拟状态/历史、批处理重复启动和临时目录残留。
- 增加上传类型、大小、数量限制和实验/静态资源路径边界校验。

### 安全

- 设置接口不再返回 RTSP 或大模型明文密钥。
- 发行包和 RTSP 工具不再内置摄像头密码、内部 IP 或含密钥 URL 日志。

### 构建

- 统一 Python 与前端版本为 `1.1.0`。
- 提供可复现的一键 Windows 便携版构建，排除非运行时 GUI/开发依赖。

## [1.0.1] - 2026-06-05

- 提供早期 Windows 便携版和端口自动选择。
- 合并基础 FastAPI 服务与 Web 前端。

[1.2.0]: https://github.com/ygttygtt/InsightClass/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/ygttygtt/InsightClass/compare/v1.0.1...v1.1.0
[1.0.1]: https://github.com/ygttygtt/InsightClass/releases/tag/v1.0.1
