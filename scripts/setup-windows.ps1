[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$venvDir = Join-Path $projectRoot ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"

Push-Location $projectRoot
try {
    $python312 = & py -3.12 -c "import sys; print(sys.executable)" 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $python312) {
        throw "未找到 Python 3.12，请先安装后重试。"
    }
    if (-not (Get-Command node.exe -ErrorAction SilentlyContinue)) {
        throw "未找到 Node.js，请先安装 Node.js 18 或更高版本。"
    }
    if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
        throw "未找到 npm。"
    }

    if (Test-Path -LiteralPath $venvDir) {
        if (-not (Test-Path -LiteralPath $venvPython)) {
            throw "现有 .venv 不是 Windows 虚拟环境，请先将其移走后重新运行。"
        }
    }
    else {
        & ($python312.Trim()) -m venv $venvDir
        if ($LASTEXITCODE -ne 0) {
            throw "创建 Python 虚拟环境失败。"
        }
    }

    & $venvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "升级 pip 失败。" }
    & $venvPython -m pip install -r backend/requirements-dev.txt
    if ($LASTEXITCODE -ne 0) { throw "安装后端依赖失败。" }

    Push-Location (Join-Path $projectRoot "frontend")
    try {
        & npm.cmd ci
        if ($LASTEXITCODE -ne 0) { throw "安装前端依赖失败。" }
    }
    finally {
        Pop-Location
    }

    Write-Host "Windows 开发依赖已准备完成，可运行 .\scripts\musicflow.ps1 start 启动项目。"
}
finally {
    Pop-Location
}
