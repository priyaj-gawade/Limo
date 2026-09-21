<#
.SYNOPSIS
    Starts the Limo Turbo Worker and Cloudflare Tunnel for Live Heavy Compute (Infographics & Video).

.DESCRIPTION
    Launches:
    1. Limo Turbo Worker daemon (FastAPI on http://127.0.0.1:8005)
    2. Cloudflare Tunnel (exposing http://127.0.0.1:8005 to turbo.limo-ai.online)
    This allows the live deployment at https://app.limo-ai.online to offload heavy rendering
    (Prismo Infographics & OpenMontage Video) to your workstation.

.EXAMPLE
    .\start-worker.ps1
#>
[CmdletBinding()]
param(
    [int]$Port = 8005,
    [string]$HostAddress = "127.0.0.1"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $ScriptDir "backend"
$TunnelConfig = Join-Path $ScriptDir "limo-turbo-tunnel.yml"

try {
    $Host.UI.RawUI.WindowTitle = "Limo Turbo Worker (Port $Port) + Cloudflare Tunnel"
} catch {}

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "         Starting Limo Turbo Worker & Cloudflare Tunnel     " -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# 1. Resolve Python / Uvicorn
$VenvPython = Join-Path $BackendDir ".venv\Scripts\python.exe"
$VenvUvicorn = Join-Path $BackendDir ".venv\Scripts\uvicorn.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Error "Virtualenv Python not found at '$VenvPython'. Please set up backend venv first."
    exit 1
}

# 2. Resolve Cloudflared
$CloudflaredBin = "cloudflared"
$CommonCloudflaredPaths = @(
    "C:\Users\Admin\cloudflared\cloudflared.exe",
    "C:\Program Files\cloudflared\cloudflared.exe"
)
foreach ($p in $CommonCloudflaredPaths) {
    if (Test-Path $p) {
        $CloudflaredBin = $p
        break
    }
}

Write-Host "[1/2] Starting Turbo Worker daemon on http://$($HostAddress):$Port..." -ForegroundColor Green
$workerProcess = Start-Process -FilePath $VenvUvicorn -ArgumentList "backend.worker.turbo_worker:app", "--host", $HostAddress, "--port", $Port, "--reload" -WorkingDirectory $ScriptDir -PassThru

Start-Sleep -Seconds 2

if (Test-Path $TunnelConfig) {
    Write-Host "[2/2] Starting Cloudflare Tunnel (turbo.limo-ai.online)..." -ForegroundColor Green
    $tunnelProcess = Start-Process -FilePath $CloudflaredBin -ArgumentList "tunnel", "--config", $TunnelConfig, "run" -WorkingDirectory $ScriptDir -PassThru
} else {
    Write-Host "[WARNING] Cloudflare tunnel config not found at '$TunnelConfig'. Worker running locally only." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  Turbo Worker:      http://$($HostAddress):$Port" -ForegroundColor Cyan
Write-Host "  Cloudflare Domain: https://turbo.limo-ai.online" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Green
Write-Host "Press Ctrl+C or close this window to stop the worker & tunnel." -ForegroundColor Yellow

try {
    while ($true) {
        if ($workerProcess.HasExited) {
            Write-Host "Turbo Worker process exited." -ForegroundColor Red
            break
        }
        Start-Sleep -Seconds 1
    }
} finally {
    Write-Host "Stopping Turbo Worker and Cloudflare Tunnel..." -ForegroundColor Yellow
    if ($workerProcess -and -not $workerProcess.HasExited) { Stop-Process -Id $workerProcess.Id -Force -ErrorAction SilentlyContinue }
    if ($tunnelProcess -and -not $tunnelProcess.HasExited) { Stop-Process -Id $tunnelProcess.Id -Force -ErrorAction SilentlyContinue }
}
