<#
.SYNOPSIS
    Starts the Limo Vite Frontend Development Server.

.DESCRIPTION
    Checks Node.js / npm dependencies and launches the Vite dev server.

.PARAMETER Port
    Port to bind the frontend dev server (default: 5190).

.PARAMETER NoHost
    Do not expose to local network interfaces.
#>
[CmdletBinding()]
param(
    [int]$Port = 5190,
    [switch]$NoHost
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$FrontendDir = Join-Path $ScriptDir "frontend"

# Set window title if in a console host
try {
    $Host.UI.RawUI.WindowTitle = "Limo Frontend (Port $Port)"
} catch {
    # Ignore if not supported in current host
}

Write-Host "============================================================" -ForegroundColor Green
Write-Host "         Starting Limo Frontend (Vite + React)              " -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green

if (-not (Test-Path $FrontendDir)) {
    Write-Error "Frontend directory not found at '$FrontendDir'."
    exit 1
}

# Check if Node.js is installed
try {
    $nodeVer = & node -v
    Write-Host "Node.js:           $nodeVer" -ForegroundColor Gray
} catch {
    Write-Error "Node.js is not found on PATH. Please install Node.js (v18+) to run the frontend."
    exit 1
}

# Check if port is already in use
try {
    $existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Host "[WARNING] Port $Port is currently in use by PID $($existing.OwningProcess)!" -ForegroundColor Yellow
        Write-Host "If another frontend instance is already running, please terminate it first." -ForegroundColor Yellow
        Write-Host ""
    }
} catch {
    # Ignore NetTCPConnection errors on non-elevated or restricted environments
}

$NodeModules = Join-Path $FrontendDir "node_modules"
if (-not (Test-Path $NodeModules)) {
    Write-Host "Dependencies not found. Running 'npm install'..." -ForegroundColor Yellow
    Push-Location $FrontendDir
    try {
        & npm install
    } catch {
        Write-Error "Failed to install frontend dependencies: $_"
        exit 1
    }
    Pop-Location
}

Write-Host "Working Directory: $FrontendDir" -ForegroundColor Gray
Write-Host "Frontend URL:      http://localhost:$Port" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop the server." -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""

Set-Location $FrontendDir

if ($Port -ne 5190 -or $NoHost) {
    $argsList = @("run", "dev", "--", "--port", "$Port")
    if (-not $NoHost) {
        $argsList += "--host"
    }
} else {
    $argsList = @("run", "dev")
}

try {
    & npm @argsList
} catch {
    Write-Error "Failed to start frontend: $_"
    exit 1
}
