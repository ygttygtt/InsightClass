# 安全策略

## 支持范围

| 版本 | 状态 |
|---|---|
| `1.2.x` | 支持 |
| `1.1.x` | 仅提供重要安全修复，建议升级 |
| `1.0.x` 及更早版本 | 不再支持 |

## 报告漏洞

请通过 GitHub 仓库的 **Security -> Report a vulnerability** 私密提交安全报告：

https://github.com/ygttygtt/InsightClass/security/advisories/new

报告中请提供受影响版本、复现条件、潜在影响和建议修复方式。请不要在公开 Issue、
日志、截图或测试数据中粘贴以下内容：

- RTSP 用户名、密码和完整摄像头 URL
- OpenAI 或兼容服务的 API Key
- 内网地址、真实课堂视频和可识别个人身份的数据
- `configs/app.yaml`、`configs/cameras.yaml` 的真实内容

维护者确认问题并准备修复前，请避免公开漏洞细节。修复完成后会在更新日志和
Release 说明中披露必要的影响与升级建议。

## 部署责任

InsightClass 默认将桌面版后端绑定到 `127.0.0.1`，但使用 CLI 绑定
`0.0.0.0` 会将服务暴露到局域网。生产部署应增加网络访问控制、反向代理认证、
HTTPS、密钥管理和日志脱敏。项目内置的自签名证书仅用于受控环境测试。
