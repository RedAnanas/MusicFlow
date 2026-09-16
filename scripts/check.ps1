[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"

function Assert-NativeCommand {
    param([string]$Step)

    if ($LASTEXITCODE -ne 0) {
        throw "$Step 失败，退出代码：$LASTEXITCODE"
    }
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "未找到 Windows Python 虚拟环境，请先运行 scripts\setup-windows.ps1。"
}

Push-Location $projectRoot
try {
    Write-Host "[1/5] 后端测试"
    & $venvPython -m pytest
    Assert-NativeCommand -Step "后端测试"

    Write-Host "[2/5] Python 编译检查"
    & $venvPython -m compileall -q backend/app backend/tests
    Assert-NativeCommand -Step "Python 编译检查"

    Write-Host "[3/5] 前端生产构建"
    Push-Location (Join-Path $projectRoot "frontend")
    try {
        & npm.cmd run build
        Assert-NativeCommand -Step "前端生产构建"
    }
    finally {
        Pop-Location
    }

    Write-Host "[4/5] Compose 配置检查"
    & docker.exe compose config -q
    Assert-NativeCommand -Step "Compose 配置检查"

    Write-Host "[5/5] Git 空白字符检查"
    & git.exe diff --check -- . ':(exclude)config/*.json' ':(exclude)logs/**'
    Assert-NativeCommand -Step "Git 空白字符检查"

    Write-Host "全部检查通过"
}
finally {
    Pop-Location
}
