$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root

function Invoke-ToolPython {
    param([string]$Executable, [string[]]$Arguments)
    # Windows PowerShell 5.1 会把原生 stderr 当作错误记录，需保留完整输出再检查退出码。
    $ErrorActionPreference = 'Continue'
    & $Executable @Arguments 2>&1 | ForEach-Object { Write-Host $_.ToString() }
    return $LASTEXITCODE
}

try {
    $python = Join-Path $root '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python)) {
        $candidate = Get-Command py.exe -ErrorAction SilentlyContinue
        $arguments = @('-3')
        if (-not $candidate) {
            $candidate = Get-Command python.exe -ErrorAction SilentlyContinue
            $arguments = @()
        }
        if (-not $candidate) { throw '未找到 Python。请先从 python.org 安装 Python 3.12 或更新版本（包含 Tcl/Tk），然后重新双击。' }
        if ((Invoke-ToolPython -Executable $candidate.Source -Arguments ($arguments + @('-c', 'import sys; raise SystemExit(0 if sys.version_info >= (3,12) else 1)'))) -ne 0) {
            throw '需要 Python 3.12 或更新版本，请安装后重试。'
        }
        Write-Host '将在工具目录创建独立 .venv，不修改系统 Python 或 MusicFlow 环境。'
        if ((Invoke-ToolPython -Executable $candidate.Source -Arguments ($arguments + @('-m', 'venv', (Join-Path $root '.venv')))) -ne 0) {
            throw '创建工具环境失败，请将工具完整解压到可写目录后重试。'
        }
    }
    if ((Invoke-ToolPython -Executable $python -Arguments @('-c', 'import sys, tkinter; assert sys.version_info >= (3,12)')) -ne 0) {
        throw '工具环境缺少 Python 3.12+ 或 Tcl/Tk，请检查 Python 安装。'
    }
    $check = "import sys; from importlib.metadata import distributions; from pathlib import Path; installed={d.metadata['Name'].lower(): d.version for d in distributions()}; requirements=Path('prototype/requirements.txt').read_text(encoding='utf-8-sig').splitlines()+Path('requirements-server.txt').read_text(encoding='utf-8-sig').splitlines(); sys.exit(0 if all(installed.get(name.lower())==wanted for line in requirements if line.strip() and not line.startswith('#') for name,wanted in [line.split('==')]) else 1)"
    if ((Invoke-ToolPython -Executable $python -Arguments @('-c', $check)) -ne 0) {
        Write-Host '需要安装固定版本 Frida、Unicorn、pefile、cryptography 及其依赖，仅安装到工具目录 .venv。'
        $answer = Read-Host '允许联网安装这些依赖吗？输入 Y 继续，其他输入取消'
        if ($answer -ne 'Y') { throw '已取消，未读取客户端授权。' }
        if ((Invoke-ToolPython -Executable $python -Arguments @('-m', 'pip', 'install', '-r', 'prototype/requirements.txt', '-r', 'requirements-server.txt')) -ne 0) {
            throw '依赖安装失败，请检查网络后重新双击。'
        }
        if ((Invoke-ToolPython -Executable $python -Arguments @('-m', 'pip', 'check')) -ne 0) {
            throw '依赖检查未通过，请检查上述错误。'
        }
    }
    if ((Invoke-ToolPython -Executable $python -Arguments @('scripts/authorize-client.py', '--export-server')) -ne 0) {
        throw '授权工具未完成，请检查窗口提示后重试。'
    }
}
catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
