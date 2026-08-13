[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot

function Assert-NativeCommand {
    param([string]$Step)

    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE"
    }
}

Push-Location $projectRoot
try {
    Write-Host "[1/5] Backend tests"
    python -m pytest
    Assert-NativeCommand -Step "Backend tests"

    Write-Host "[2/5] Python compile check"
    python -m compileall -q backend/app backend/tests
    Assert-NativeCommand -Step "Python compile check"

    Write-Host "[3/5] Frontend production build"
    Push-Location (Join-Path $projectRoot "frontend")
    try {
        npm run build
        Assert-NativeCommand -Step "Frontend production build"
    }
    finally {
        Pop-Location
    }

    Write-Host "[4/5] Compose configuration"
    docker compose config -q
    Assert-NativeCommand -Step "Compose configuration"

    Write-Host "[5/5] Git whitespace check"
    git diff --check -- . ':(exclude)config/*.json' ':(exclude)logs/**'
    Assert-NativeCommand -Step "Git whitespace check"

    Write-Host "All checks passed"
}
finally {
    Pop-Location
}
