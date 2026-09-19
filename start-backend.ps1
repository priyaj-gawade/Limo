<#
.SYNOPSIS
    Starts the Limo FastAPI Backend Server.

.DESCRIPTION
    Launches Uvicorn with auto-reload, using the local virtual environment (.venv)
    or the system Python interpreter.

.PARAMETER Port
    Port to bind the backend server (default: 8000).

.PARAMETER HostAddress
    Host interface to bind (default: 127.0.0.1).

.PARAMETER NoReload
    Disable auto-reload mode.
#>
[CmdletBinding()]
param(
    [int]$Port = 8000,
    [string]$HostAddress = "127.0.0.1",
    [switch]$NoReload
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $ScriptDir "backend"

# Set window title if in a console host
try {
    $Host.UI.RawUI.WindowTitle = "Limo Backend (Port $Port)"
} catch {
    # Ignore if not supported in current host
}

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "             Starting Limo Backend (FastAPI)                " -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

if (-not (Test-Path $BackendDir)) {
    Write-Error "Backend directory not found at '$BackendDir'."
    exit 1
}

# Check if port is already in use
try {
    $existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Host "[WARNING] Port $Port is currently in use by PID $($existing.OwningProcess)!" -ForegroundColor Yellow
        Write-Host "If another Limo backend instance is already running, please terminate it first." -ForegroundColor Yellow
        Write-Host ""
    }
} catch {
    # Ignore NetTCPConnection errors on non-elevated or restricted environments
}

# Resolve Python / Uvicorn executable
$VenvPython = Join-Path $BackendDir ".venv\Scripts\python.exe"
$VenvUvicorn = Join-Path $BackendDir ".venv\Scripts\uvicorn.exe"

$PythonCmd = if (Test-Path $VenvPython) { $VenvPython } else { "python" }
$UvicornCmd = if (Test-Path $VenvUvicorn) { $VenvUvicorn } else { $null }

Write-Host "Python:            $PythonCmd" -ForegroundColor Gray
Write-Host "Working Directory: $BackendDir" -ForegroundColor Gray
Write-Host "Backend API:       http://${HostAddress}:${Port}" -ForegroundColor Green
Write-Host "API Documentation: http://${HostAddress}:${Port}/docs" -ForegroundColor Green
Write-Host "Auto-Reload:       $(-not $NoReload)" -ForegroundColor Gray
Write-Host "Press Ctrl+C to stop the server." -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

Set-Location $BackendDir

$argsList = @("app.main:app", "--host", $HostAddress, "--port", "$Port")
if (-not $NoReload) {
    $argsList += "--reload"
}

try {
    if ($UvicornCmd -and (Test-Path $UvicornCmd)) {
        & $UvicornCmd @argsList
    } else {
        & $PythonCmd -m uvicorn @argsList
    }
} catch {
    Write-Error "Failed to start backend: $_"
    exit 1
}
