InsightClass Web 推理服务
========================

快速启动
--------
双击「启动服务.bat」或运行：

    InsightClass.exe serve --port 8000

浏览器访问 http://localhost:8000

HTTPS 模式
----------
局域网摄像头需要 HTTPS 才能使用浏览器摄像头功能：

    InsightClass.exe serve --port 8000 --https

首次启动会自动生成自签名证书（在 configs/ssl/ 目录下）。

摄像头配置
----------
1. 打开 Web 界面 → 设置页面
2. 输入全局 RTSP 凭据（用户名、密码、端口）
3. 点击「导入摄像头」上传 CSV 文件

CSV 格式要求（海康威视导出格式）：
- 编码：GB2312/GBK/UTF-8
- 必须包含「IP地址」列

目录结构
--------
├── InsightClass.exe        主程序
├── models/best.pt          内置模型
├── configs/
│   ├── classes.yaml        类别配置（4 种行为）
│   ├── cameras.yaml        摄像头列表（通过 Web 导入）
│   └── app.yaml            应用配置
└── experiments/            可选：放入额外模型

常见问题
--------
Q: 启动后页面打不开？
A: 检查端口 8000 是否被占用，尝试 --port 8080

Q: 摄像头连接失败？
A: 1. 检查摄像头 IP 是否可达（ping 测试）
   2. 检查 RTSP 用户名密码是否正确
   3. 检查防火墙是否放行 554 端口

Q: HTTPS 模式浏览器提示不安全？
A: 自签名证书需要手动信任：点击「高级」→「继续访问」

Q: 如何添加更多模型？
A: 将 .pt 模型文件放入 experiments/ 目录，重启服务后可在 Web 界面切换

反馈与帮助
----------
项目地址: https://gitee.com/ygttygtt/InsightClass
