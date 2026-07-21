[CmdletBinding()]
param(
    [switch]$SkipDeps,
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$frontendDir = Join-Path $projectRoot "frontend"
$pyInstallerDir = Join-Path $projectRoot "dist\InsightClass"
$packageDir = Join-Path $projectRoot "dist\InsightClass-Web"
$zipPath = Join-Path $projectRoot "InsightClass-Web.zip"

function Invoke-Native {
    param(
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments
    )
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed ($LASTEXITCODE): $Command $($Arguments -join ' ')"
    }
}

function Write-Utf8NoBom {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Content
    )
    [System.IO.File]::WriteAllText($Path, $Content, [System.Text.UTF8Encoding]::new($false))
}

Push-Location $projectRoot
try {
    Write-Host "=== InsightClass Windows package build ===" -ForegroundColor Cyan

    foreach ($required in @(
        "InsightClass.spec",
        "pyproject.toml",
        "src\insightclass\web\launcher.pyw",
        "configs\classes.yaml",
        "models\onnx\yolo11n_v2.onnx",
        "frontend\package-lock.json"
    )) {
        if (-not (Test-Path -LiteralPath (Join-Path $projectRoot $required))) {
            throw "Required file is missing: $required"
        }
    }
    Get-Command $Python -ErrorAction Stop | Out-Null
    Get-Command npm -ErrorAction Stop | Out-Null

    if (-not $SkipDeps) {
        Write-Host "[1/5] Installing Python web and packaging dependencies..." -ForegroundColor Yellow
        Invoke-Native -Command $Python -Arguments @(
            "-m", "pip", "install", "--disable-pip-version-check", "-e", ".[web]", "pyinstaller"
        )
    } else {
        Write-Host "[1/5] Skipping dependency installation." -ForegroundColor DarkGray
    }

    Write-Host "[2/5] Building React frontend..." -ForegroundColor Yellow
    Push-Location $frontendDir
    try {
        Invoke-Native -Command "npm" -Arguments @("ci", "--no-audit", "--no-fund")
        Invoke-Native -Command "npm" -Arguments @("run", "build")
    } finally {
        Pop-Location
    }

    Write-Host "[3/5] Building windowed application..." -ForegroundColor Yellow
    Invoke-Native -Command $Python -Arguments @(
        "-m", "PyInstaller", "--clean", "--noconfirm", "InsightClass.spec"
    )
    $exePath = Join-Path $pyInstallerDir "InsightClass.exe"
    if (-not (Test-Path -LiteralPath $exePath)) {
        throw "PyInstaller did not produce $exePath"
    }

    Write-Host "[4/5] Assembling portable application..." -ForegroundColor Yellow
    if (Test-Path -LiteralPath $packageDir) {
        Remove-Item -LiteralPath $packageDir -Recurse -Force
    }
    New-Item -ItemType Directory -Path $packageDir | Out-Null
    Copy-Item -Path (Join-Path $pyInstallerDir "*") -Destination $packageDir -Recurse -Force

    $runtimeConfigDir = Join-Path $packageDir "configs"
    New-Item -ItemType Directory -Path $runtimeConfigDir -Force | Out-Null
    Write-Utf8NoBom (Join-Path $runtimeConfigDir "app.yaml") "{}$([Environment]::NewLine)"
    Write-Utf8NoBom (Join-Path $runtimeConfigDir "cameras.yaml") "cameras: []$([Environment]::NewLine)"
    New-Item -ItemType Directory -Path (Join-Path $packageDir "experiments") -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $projectRoot "README.md") -Destination $packageDir -Force
    Copy-Item -LiteralPath (Join-Path $projectRoot "LICENSE") -Destination $packageDir -Force

    Write-Host "[5/5] Creating portable ZIP..." -ForegroundColor Yellow
    if (Test-Path -LiteralPath $zipPath) {
        Remove-Item -LiteralPath $zipPath -Force
    }
    Compress-Archive -LiteralPath $packageDir -DestinationPath $zipPath -CompressionLevel Optimal

    $zipSizeMiB = [Math]::Round((Get-Item -LiteralPath $zipPath).Length / 1MB, 1)
    Write-Host "Build complete." -ForegroundColor Green
    Write-Host "Application: $packageDir"
    Write-Host "Executable:  $(Join-Path $packageDir 'InsightClass.exe')"
    Write-Host "Archive:     $zipPath ($zipSizeMiB MiB)"
} finally {
    Pop-Location
}
