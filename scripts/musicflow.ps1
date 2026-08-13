[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("start", "stop", "restart", "status")]
    [string]$Action = "status"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeDir = Join-Path $projectRoot "temp\run"
$logDir = Join-Path $projectRoot "logs"
$bindAddress = "127.0.0.1"

$services = @{
    backend = @{
        Port = 8082
        Url = "http://127.0.0.1:8082/docs"
        StateFile = Join-Path $runtimeDir "backend.json"
    }
    frontend = @{
        Port = 3000
        Url = "http://127.0.0.1:3000"
        StateFile = Join-Path $runtimeDir "frontend.json"
    }
}

function Get-ListeningProcessId {
    param([int]$Port)

    $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($connection) {
        return [int]$connection.OwningProcess
    }
    return $null
}

function Test-MusicFlowListener {
    param(
        [string]$Name,
        [int]$ProcessId
    )

    $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
    if (-not $processInfo -or -not $processInfo.CommandLine) {
        return $false
    }

    if ($Name -eq "backend") {
        return $processInfo.CommandLine -match "(?i)-m\s+uvicorn\s+app\.main:app" -and
            $processInfo.CommandLine -match "(?i)--port\s+8082"
    }

    $frontendRoot = Join-Path $projectRoot "frontend"
    return $processInfo.CommandLine.Contains($frontendRoot) -and
        $processInfo.CommandLine -match "(?i)vite" -and
        $processInfo.CommandLine -match "(?i)--port\s+3000"
}

function Save-ProcessState {
    param(
        [System.Diagnostics.Process]$Process,
        [string]$StateFile
    )

    New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
    @{
        pid = $Process.Id
        start_ticks = $Process.StartTime.ToUniversalTime().Ticks
    } | ConvertTo-Json | Set-Content -LiteralPath $StateFile -Encoding UTF8
}

function Stop-ProcessTree {
    param([int]$ProcessId)

    $children = Get-CimInstance Win32_Process -Filter "ParentProcessId=$ProcessId" -ErrorAction SilentlyContinue
    foreach ($child in $children) {
        Stop-ProcessTree -ProcessId $child.ProcessId
    }
    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
}

function Stop-RecordedProcess {
    param([string]$StateFile)

    if (-not (Test-Path -LiteralPath $StateFile)) {
        return
    }

    try {
        $state = Get-Content -LiteralPath $StateFile -Raw | ConvertFrom-Json
        $process = Get-Process -Id $state.pid -ErrorAction SilentlyContinue
        if ($process -and $process.StartTime.ToUniversalTime().Ticks -eq $state.start_ticks) {
            Stop-ProcessTree -ProcessId $process.Id
        }
    }
    finally {
        Remove-Item -LiteralPath $StateFile -Force -ErrorAction SilentlyContinue
    }
}

function Wait-ForPort {
    param(
        [int]$Port,
        [bool]$Listening,
        [int]$TimeoutSeconds = 30
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $isListening = $null -ne (Get-ListeningProcessId -Port $Port)
        if ($isListening -eq $Listening) {
            return $true
        }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)

    return $false
}

function Start-MusicFlowService {
    param([string]$Name)

    $service = $services[$Name]
    $listenerPid = Get-ListeningProcessId -Port $service.Port
    if ($null -ne $listenerPid) {
        if (Test-MusicFlowListener -Name $Name -ProcessId $listenerPid) {
            Write-Host "$Name is already running on port $($service.Port)"
            return
        }
        throw "Port $($service.Port) is occupied by another process; $Name was not started"
    }

    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    if ($Name -eq "backend") {
        $process = Start-Process -FilePath "python" `
            -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", $bindAddress, "--port", "8082", "--reload") `
            -WorkingDirectory (Join-Path $projectRoot "backend") `
            -RedirectStandardOutput (Join-Path $logDir "backend-dev.out.log") `
            -RedirectStandardError (Join-Path $logDir "backend-dev.err.log") `
            -WindowStyle Hidden `
            -PassThru
    }
    else {
        $process = Start-Process -FilePath "npm.cmd" `
            -ArgumentList @("run", "dev", "--", "--host", $bindAddress, "--port", "3000") `
            -WorkingDirectory (Join-Path $projectRoot "frontend") `
            -RedirectStandardOutput (Join-Path $logDir "frontend-dev.out.log") `
            -RedirectStandardError (Join-Path $logDir "frontend-dev.err.log") `
            -WindowStyle Hidden `
            -PassThru
    }

    Save-ProcessState -Process $process -StateFile $service.StateFile
    if (-not (Wait-ForPort -Port $service.Port -Listening $true)) {
        throw "$Name startup timed out; check logs in $logDir"
    }
    Write-Host "$Name started: http://$bindAddress`:$($service.Port)"
}

function Stop-MusicFlowService {
    param([string]$Name)

    $service = $services[$Name]
    Stop-RecordedProcess -StateFile $service.StateFile

    $listenerPid = Get-ListeningProcessId -Port $service.Port
    if ($null -ne $listenerPid) {
        if (-not (Test-MusicFlowListener -Name $Name -ProcessId $listenerPid)) {
            throw "Port $($service.Port) belongs to another process; refusing to stop it"
        }
        Stop-ProcessTree -ProcessId $listenerPid
    }

    if (-not (Wait-ForPort -Port $service.Port -Listening $false -TimeoutSeconds 15)) {
        throw "$Name did not stop within the expected time"
    }
    Write-Host "$Name stopped"
}

function Show-MusicFlowStatus {
    foreach ($name in @("backend", "frontend")) {
        $service = $services[$name]
        $listenerPid = Get-ListeningProcessId -Port $service.Port
        if ($null -eq $listenerPid) {
            Write-Host ("{0}: stopped" -f $name)
            continue
        }
        if (-not (Test-MusicFlowListener -Name $name -ProcessId $listenerPid)) {
            Write-Host ("{0}: port {1} is occupied by another process" -f $name, $service.Port)
            continue
        }

        try {
            $response = Invoke-WebRequest -Uri $service.Url -UseBasicParsing -TimeoutSec 5
            Write-Host ("{0}: running, HTTP {1}, PID {2}" -f $name, $response.StatusCode, $listenerPid)
        }
        catch {
            Write-Host ("{0}: listening but HTTP check failed, PID {1}" -f $name, $listenerPid)
        }
    }
}

switch ($Action) {
    "start" {
        Start-MusicFlowService -Name "backend"
        Start-MusicFlowService -Name "frontend"
        Show-MusicFlowStatus
    }
    "stop" {
        Stop-MusicFlowService -Name "frontend"
        Stop-MusicFlowService -Name "backend"
        Show-MusicFlowStatus
    }
    "restart" {
        Stop-MusicFlowService -Name "frontend"
        Stop-MusicFlowService -Name "backend"
        Start-MusicFlowService -Name "backend"
        Start-MusicFlowService -Name "frontend"
        Show-MusicFlowStatus
    }
    "status" {
        Show-MusicFlowStatus
    }
}
