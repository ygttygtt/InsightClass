# 贡献指南

感谢参与 InsightClass。提交变更前，请先确认改动边界清晰、没有包含课堂视频、
摄像头地址、账号、密码、API Key 或其他个人/组织敏感信息。

## 开发环境

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[web,dev]"

Push-Location frontend
npm ci
Pop-Location
```

## 工作方式

- 仓库维护分支为 `main`。维护者的小步改动直接在 `main` 上按验证结果提交。
- 外部贡献者应从个人 Fork 创建短期分支，通过 Pull Request 合入 `main`；不需要
  在上游仓库长期保留额外开发分支。
- 一次提交只处理一个可验证的问题，避免混入无关格式化或生成文件。
- 不提交 `build/`、`dist/`、`experiments/`、数据集、运行时配置或发布 ZIP。

## 提交说明

使用“英文类型 + 清晰中文摘要”的 Conventional Commits 格式：

```text
feat: 增加课堂统计的大模型分析
fix: 修复视频检测框与播放帧不同步
docs: 更新 Windows 打包和托盘使用说明
test: 补充 RTSP 凭据脱敏测试
build: 精简 PyInstaller 发行依赖
```

必要时在正文中说明原因、行为变化、兼容性和验证命令。摘要应让后续开发者无需
打开差异就能判断改动目的；避免使用“更新代码”“修复问题”等模糊表述。

## 质量检查

提交前至少运行：

```powershell
python -m pytest -q
ruff check src scripts tests

Push-Location frontend
npm run build
Pop-Location
```

涉及依赖或发行时还应运行 `npm audit --omit=dev --audit-level=high` 和完整 Windows
打包冒烟测试。涉及摄像头时应覆盖连接、失败、停止、重连和资源释放。

## UI 与品牌资产

- 深色和浅色主题必须同时检查，不能用只适合单一背景的硬编码文字/网格颜色。
- 修改 Logo 时编辑 `scripts/generate_brand_assets.py`，运行脚本后一起提交 `assets/`
  和 `frontend/public/` 的全部生成结果。
- `assets/insightclass.ico` 必须保留 16/24/32/48/64/128/256 七档尺寸；发行前检查
  EXE、任务栏、标题栏、托盘和 favicon 的实际显示。
- 调整发行版本时同步 Python、前端、lockfile 和 Windows 版本资源，并运行版本一致
  性测试。

## Pull Request

PR 描述应包括：

- 问题和预期行为
- 实现范围及明确未处理的范围
- 测试命令和结果
- UI 变更截图（如适用）
- 配置、迁移或兼容性影响

安全问题请勿提交公开 Issue，改用 [安全策略](SECURITY.md) 中的私密渠道。
