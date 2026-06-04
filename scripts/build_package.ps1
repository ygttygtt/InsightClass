# InsightClass Web 打包脚本
# 用法: .\scripts\build_package.ps1 [-Variant onedir|onefile]
#   -Variant onedir: 安装版（文件夹形式，默认）
#   -Variant onefile: 便携版（单文件 exe）

param(
    [ValidateSet("onedir", "onefile")]
    [string]$Variant = "onedir"
)

$ErrorActionPreference = "Stop"

Write-Host "=== InsightClass Web 打包脚本 ===" -ForegroundColor Cyan
Write-Host "模式: $Variant" -ForegroundColor Cyan

# 1. 检查必要文件
$requiredFiles = @(
    "src\insightclass\__main__.py",
    "configs\classes.yaml",
    "experiments\baseline_yolo11n_v2_e80-2\weights\best.pt"
)
foreach ($f in $requiredFiles) {
    if (-not (Test-Path $f)) {
        Write-Host "错误: 找不到必要文件 $f" -ForegroundColor Red
        exit 1
    }
}

# 2. 安装依赖
Write-Host "`n[1/4] 安装依赖..." -ForegroundColor Yellow
pip install -e ".[web,ultralytics]" --quiet
pip install cryptography pyinstaller --quiet

# 3. 选择 spec 文件
if ($Variant -eq "onefile") {
    $specFile = "InsightClass-Web-Portable.spec"
    $distDir = "dist\InsightClass-Web-Portable"
} else {
    $specFile = "InsightClass-Web.spec"
    $distDir = "dist\InsightClass-Web"
}

# 4. 运行 PyInstaller
Write-Host "`n[2/4] 运行 PyInstaller ($Variant)..." -ForegroundColor Yellow
pyinstaller $specFile --clean --noconfirm

if ($LASTEXITCODE -ne 0) {
    Write-Host "错误: PyInstaller 构建失败" -ForegroundColor Red
    exit 1
}

# 5. 复制补充文件到输出目录
Write-Host "`n[3/4] 复制补充文件..." -ForegroundColor Yellow

if ($Variant -eq "onedir") {
    # 安装版：创建初始配置文件
    $configsDir = "$distDir\configs"
    if (-not (Test-Path $configsDir)) {
        New-Item -ItemType Directory -Path $configsDir -Force | Out-Null
    }
    # classes.yaml 已通过 PyInstaller datas 打包，创建空的 cameras.yaml 和 app.yaml
    if (-not (Test-Path "$configsDir\cameras.yaml")) {
        Set-Content -Path "$configsDir\cameras.yaml" -Value "cameras: []" -Encoding UTF8
    }
    if (-not (Test-Path "$configsDir\app.yaml")) {
        Set-Content -Path "$configsDir\app.yaml" -Value "{}" -Encoding UTF8
    }
    # 创建 experiments 目录
    New-Item -ItemType Directory -Path "$distDir\experiments" -Force | Out-Null
}

# 6. 验证
Write-Host "`n[4/4] 验证..." -ForegroundColor Yellow
if (Test-Path "$distDir\InsightClass.exe") {
    Write-Host "构建成功!" -ForegroundColor Green
    Write-Host "输出目录: $distDir" -ForegroundColor Green

    # 显示文件大小
    if ($Variant -eq "onefile") {
        $exeSize = (Get-Item "$distDir\InsightClass-Web-Portable.exe").Length / 1MB
        Write-Host "exe 大小: $([math]::Round($exeSize, 1)) MB" -ForegroundColor Green
    } else {
        $totalSize = (Get-ChildItem $distDir -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB
        Write-Host "总大小: $([math]::Round($totalSize, 1)) MB" -ForegroundColor Green
    }
} else {
    Write-Host "错误: 找不到输出文件" -ForegroundColor Red
    exit 1
}

Write-Host "`n=== 打包完成 ===" -ForegroundColor Cyan
if ($Variant -eq "onedir") {
    Write-Host "安装版输出: $distDir" -ForegroundColor Cyan
    Write-Host "如需生成安装程序，运行: iscc installer.iss" -ForegroundColor Cyan
} else {
    Write-Host "便携版输出: $distDir\InsightClass-Web-Portable.exe" -ForegroundColor Cyan
}
