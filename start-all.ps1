<#
.SYNOPSIS
    Starts the full Limo Application (FastAPI Backend + Vite Frontend).

.DESCRIPTION
    Orchestrates startup of both the backend and frontend services.
    By default, opens two dedicated PowerShell windows for live log viewing.
    Optionally supports running inline as background jobs or auto-opening the browser.

.PARAMETER BackendPort
    Port for the backend server (default: 8000).

.PARAMETER FrontendPort
    Port for the frontend server (default: 5190).

.PARAMETER OpenBrowser
    Automatically open http://localhost:<FrontendPort> in the default browser once started.

.PARAMETER Inline
    Run both services in the current console session instead of opening new windows.

.EXAMPLE
    .\start-all.ps1
    Starts both services in separate console windows.

.EXAMPLE
    .\start-all.ps1 -OpenBrowser
    Starts both services and automatically opens the browser.

.EXAMPLE
    .\start-all.ps1 -Inline
    Runs both services as background jobs within the current terminal.
#>
[CmdletBinding()]
param(
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5190,
    [switch]$OpenBrowser,
    [switch]$Inline
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendScript = Join-Path $ScriptDir "start-backend.ps1"
$FrontendScript = Join-Path $ScriptDir "start-frontend.ps1"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "             Starting Full Limo Application                 " -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# Validate scripts exist
if (-not (Test-Path $BackendScript)) {
    Write-Error "Backend start script not found at '$BackendScript'."
    exit 1
}
if (-not (Test-Path $FrontendScript)) {
    Write-Error "Frontend start script not found at '$FrontendScript'."
    exit 1
}

if ($Inline) {
    Write-Host "[Mode] Running in current terminal (Inline Jobs)..." -ForegroundColor Yellow
    Write-Host "Press Ctrl+C at any time to stop both servers." -ForegroundColor Yellow
    Write-Host ""

    $backendJob = Start-Job -Name "LimoBackend" -ScriptBlock {
        param($ScriptPath, $Port)
        & powershell.exe -ExecutionPolicy Bypass -File $ScriptPath -Port $Port
    } -ArgumentList $BackendScript, $BackendPort

    $frontendJob = Start-Job -Name "LimoFrontend" -ScriptBlock {
        param($ScriptPath, $Port)
        & powershell.exe -ExecutionPolicy Bypass -File $ScriptPath -Port $Port
    } -ArgumentList $FrontendScript, $FrontendPort

    try {
        Start-Sleep -Seconds 3

        Write-Host "============================================================" -ForegroundColor Green
        Write-Host "  Backend API:  http://127.0.0.1:$BackendPort" -ForegroundColor Cyan
        Write-Host "  Swagger Docs: http://127.0.0.1:$BackendPort/docs" -ForegroundColor Cyan
        Write-Host "  Frontend UI:  http://localhost:$FrontendPort" -ForegroundColor Green
        Write-Host "============================================================" -ForegroundColor Green

        if ($OpenBrowser) {
            Start-Process "http://localhost:$FrontendPort"
        }

        while ($true) {
            $bOut = Receive-Job -Job $backendJob
            if ($bOut) { $bOut | ForEach-Object { Write-Host "[BACKEND]  $_" -ForegroundColor Cyan } }
            
            $fOut = Receive-Job -Job $frontendJob
            if ($fOut) { $fOut | ForEach-Object { Write-Host "[FRONTEND] $_" -ForegroundColor Green } }

            if ($backendJob.State -ne "Running" -and $frontendJob.State -ne "Running") {
                Write-Host "Both jobs have stopped." -ForegroundColor Red
                break
            }
            Start-Sleep -Milliseconds 500
        }
    } finally {
        Write-Host ""
        Write-Host "Stopping Limo services..." -ForegroundColor Yellow
        Stop-Job -Job $backendJob -ErrorAction SilentlyContinue
        Remove-Job -Job $backendJob -Force -ErrorAction SilentlyContinue
        Stop-Job -Job $frontendJob -ErrorAction SilentlyContinue
        Remove-Job -Job $frontendJob -Force -ErrorAction SilentlyContinue
        Write-Host "All services stopped." -ForegroundColor Gray
    }
} else {
    Write-Host "[Mode] Launching in dedicated console windows..." -ForegroundColor Yellow
    Write-Host ""

    # Start Backend in dedicated window
    Write-Host "  -> Launching Backend on port $BackendPort..." -ForegroundColor Cyan
    Start-Process powershell.exe -ArgumentList @(
        "-ExecutionPolicy", "Bypass",
        "-NoExit",
        "-File", "`"$BackendScript`"",
        "-Port", "$BackendPort"
    )

    # Start Frontend in dedicated window
    Write-Host "  -> Launching Frontend on port $FrontendPort..." -ForegroundColor Green
    Start-Process powershell.exe -ArgumentList @(
        "-ExecutionPolicy", "Bypass",
        "-NoExit",
        "-File", "`"$FrontendScript`"",
        "-Port", "$FrontendPort"
    )

    # Brief pause to allow listeners to bind
    Start-Sleep -Seconds 2

    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host "              Limo App Successfully Launched!               " -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host "  * Frontend UI:       http://localhost:$FrontendPort" -ForegroundColor White
    Write-Host "  * Backend API:       http://127.0.0.1:$BackendPort" -ForegroundColor White
    Write-Host "  * API Documentation: http://127.0.0.1:$BackendPort/docs" -ForegroundColor White
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host "Two dedicated PowerShell windows have been opened." -ForegroundColor Gray
    Write-Host "To shut down a service, simply close its terminal window or press Ctrl+C inside it." -ForegroundColor Gray
    Write-Host ""

    if ($OpenBrowser) {
        Write-Host "Opening browser at http://localhost:$FrontendPort..." -ForegroundColor Cyan
        Start-Process "http://localhost:$FrontendPort"
    }
}
