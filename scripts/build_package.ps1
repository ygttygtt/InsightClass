# InsightClass Web 打包脚本
# 用法: .\scripts\build_package.ps1
#
# 输出:
#   1. 安装版文件夹: dist\InsightClass-Web\
#   2. 安装程序: installer_output\InsightClass-Setup.exe (需要 Inno Setup)
#   3. ZIP 压缩包: InsightClass-Web.zip

$ErrorActionPreference = "Stop"

Write-Host "=== InsightClass Web 打包脚本 ===" -ForegroundColor Cyan

# 1. 检查必要文件
Write-Host "`n[1/5] 检查必要文件..." -ForegroundColor Yellow
$requiredFiles = @(
    "src\insightclass\web\launcher.pyw",
    "configs\classes.yaml",
    "experiments\baseline_yolo11n_v2_e80-2\weights\best.pt"
)
foreach ($f in $requiredFiles) {
    if (-not (Test-Path $f)) {
        Write-Host "错误: 找不到必要文件 $f" -ForegroundColor Red
        exit 1
    }
}
Write-Host "  所有必要文件存在" -ForegroundColor Green

# 2. 安装依赖
Write-Host "`n[2/5] 安装依赖..." -ForegroundColor Yellow
pip install -e ".[web,ultralytics]" --quiet
pip install cryptography pyinstaller --quiet
Write-Host "  依赖安装完成" -ForegroundColor Green

# 3. 运行 PyInstaller
Write-Host "`n[3/5] 运行 PyInstaller..." -ForegroundColor Yellow
python -m PyInstaller InsightClass-Web.spec --clean --noconfirm
if ($LASTEXITCODE -ne 0) {
    Write-Host "错误: PyInstaller 构建失败" -ForegroundColor Red
    exit 1
}
Write-Host "  PyInstaller 构建完成" -ForegroundColor Green

# 4. 复制补充文件
Write-Host "`n[4/5] 复制补充文件..." -ForegroundColor Yellow
$distDir = "dist\InsightClass-Web"

# 创建配置目录和文件
$configsDir = "$distDir\configs"
if (-not (Test-Path $configsDir)) {
    New-Item -ItemType Directory -Path $configsDir -Force | Out-Null
}
if (-not (Test-Path "$configsDir\cameras.yaml")) {
    Set-Content -Path "$configsDir\cameras.yaml" -Value "cameras: []" -Encoding UTF8
}
if (-not (Test-Path "$configsDir\app.yaml")) {
    Set-Content -Path "$configsDir\app.yaml" -Value "{}" -Encoding UTF8
}

# 创建 experiments 目录
New-Item -ItemType Directory -Path "$distDir\experiments" -Force | Out-Null

# 复制 README
Copy-Item "packaging\README.txt" "$distDir\" -Force -ErrorAction SilentlyContinue

Write-Host "  补充文件已复制" -ForegroundColor Green

# 5. 创建 ZIP 压缩包
Write-Host "`n[5/5] 创建 ZIP 压缩包..." -ForegroundColor Yellow
$zipPath = "InsightClass-Web.zip"
if (Test-Path $zipPath) {
    Remove-Item $zipPath -Force
}
Compress-Archive -Path "$distDir\*" -DestinationPath $zipPath -CompressionLevel Optimal
Write-Host "  ZIP 压缩包已创建: $zipPath" -ForegroundColor Green

# 完成
Write-Host "`n=== 打包完成 ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "输出文件:" -ForegroundColor White
Write-Host "  1. 安装版文件夹: $distDir\" -ForegroundColor White
Write-Host "  2. ZIP 压缩包: $zipPath" -ForegroundColor White
Write-Host ""

# 检查 Inno Setup
$innoSetup = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if (Test-Path $innoSetup) {
    Write-Host "检测到 Inno Setup，是否生成安装程序？(Y/N)" -ForegroundColor Yellow
    $response = Read-Host
    if ($response -eq 'Y' -or $response -eq 'y') {
        Write-Host "正在生成安装程序..." -ForegroundColor Yellow
        & $innoSetup installer.iss
        if ($LASTEXITCODE -eq 0) {
            Write-Host "安装程序已生成: installer_output\InsightClass-Setup.exe" -ForegroundColor Green
        } else {
            Write-Host "安装程序生成失败" -ForegroundColor Red
        }
    }
} else {
    Write-Host "提示: 安装 Inno Setup 6 后可生成安装程序 (.exe)" -ForegroundColor Gray
    Write-Host "下载地址: https://jrsoftware.org/isinfo.php" -ForegroundColor Gray
}
