<#
.SYNOPSIS
    Starts the full Limo Application (FastAPI Backend + Vite Frontend + GenOffice Suite).

.DESCRIPTION
    Orchestrates startup of the backend, frontend, and GenOffice desktop engine.
    By default, opens dedicated PowerShell windows for live log viewing.
    Optionally supports running inline as background jobs or auto-opening the browser.

.PARAMETER BackendPort
    Port for the backend server (default: 8000).

.PARAMETER FrontendPort
    Port for the frontend server (default: 5190).

.PARAMETER NoGenOffice
    Skip launching the GenOffice desktop suite and Electron shell.

.PARAMETER OpenBrowser
    Automatically open http://localhost:<FrontendPort> in the default browser once started.

.PARAMETER Inline
    Run all services in the current console session instead of opening new windows.

.EXAMPLE
    .\start-all.ps1
    Starts Backend, Frontend, and GenOffice in separate console windows.

.EXAMPLE
    .\start-all.ps1 -NoGenOffice
    Starts only Backend and Frontend (web-only mode).

.EXAMPLE
    .\start-all.ps1 -OpenBrowser
    Starts all services and automatically opens the browser.

.EXAMPLE
    .\start-all.ps1 -Inline
    Runs services as background jobs within the current terminal.
#>
[CmdletBinding()]
param(
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5190,
    [switch]$NoGenOffice,
    [switch]$OpenBrowser,
    [switch]$Inline
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendScript = Join-Path $ScriptDir "start-backend.ps1"
$FrontendScript = Join-Path $ScriptDir "start-frontend.ps1"
$GenOfficeScript = Join-Path $ScriptDir "start-genoffice.ps1"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "         Starting Full Limo Application + GenOffice         " -ForegroundColor Cyan
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
if (-not $NoGenOffice -and -not (Test-Path $GenOfficeScript)) {
    Write-Error "GenOffice start script not found at '$GenOfficeScript'."
    exit 1
}

if ($Inline) {
    Write-Host "[Mode] Running in current terminal (Inline Jobs)..." -ForegroundColor Yellow
    Write-Host "Press Ctrl+C at any time to stop all servers." -ForegroundColor Yellow
    Write-Host ""

    $backendJob = Start-Job -Name "LimoBackend" -ScriptBlock {
        param($ScriptPath, $Port)
        & powershell.exe -ExecutionPolicy Bypass -File $ScriptPath -Port $Port
    } -ArgumentList $BackendScript, $BackendPort

    $frontendJob = Start-Job -Name "LimoFrontend" -ScriptBlock {
        param($ScriptPath, $Port)
        & powershell.exe -ExecutionPolicy Bypass -File $ScriptPath -Port $Port
    } -ArgumentList $FrontendScript, $FrontendPort

    $genofficeJob = $null
    if (-not $NoGenOffice) {
        $genofficeJob = Start-Job -Name "LimoGenOffice" -ScriptBlock {
            param($ScriptPath)
            & powershell.exe -ExecutionPolicy Bypass -File $ScriptPath
        } -ArgumentList $GenOfficeScript
    }

    try {
        Start-Sleep -Seconds 3

        Write-Host "============================================================" -ForegroundColor Green
        Write-Host "  Backend API:      http://127.0.0.1:$BackendPort" -ForegroundColor Cyan
        Write-Host "  Swagger Docs:     http://127.0.0.1:$BackendPort/docs" -ForegroundColor Cyan
        Write-Host "  Frontend UI:      http://localhost:$FrontendPort" -ForegroundColor Green
        if (-not $NoGenOffice) {
            Write-Host "  GenOffice Engine: Active (Electron Shell & Workspace)" -ForegroundColor Magenta
        }
        Write-Host "============================================================" -ForegroundColor Green

        if ($OpenBrowser) {
            Start-Process "http://localhost:$FrontendPort"
        }

        while ($true) {
            $bOut = Receive-Job -Job $backendJob
            if ($bOut) { $bOut | ForEach-Object { Write-Host "[BACKEND]   $_" -ForegroundColor Cyan } }
            
            $fOut = Receive-Job -Job $frontendJob
            if ($fOut) { $fOut | ForEach-Object { Write-Host "[FRONTEND]  $_" -ForegroundColor Green } }

            if ($genofficeJob) {
                $gOut = Receive-Job -Job $genofficeJob
                if ($gOut) { $gOut | ForEach-Object { Write-Host "[GENOFFICE] $_" -ForegroundColor Magenta } }
            }

            $allStopped = ($backendJob.State -ne "Running" -and $frontendJob.State -ne "Running")
            if ($genofficeJob -and $genofficeJob.State -eq "Running") {
                $allStopped = $false
            }

            if ($allStopped) {
                Write-Host "All background jobs have stopped." -ForegroundColor Red
                break
            }
            Start-Sleep -Milliseconds 500
        }
    } finally {
        Write-Host ""
        Write-Host "Stopping Limo & GenOffice services..." -ForegroundColor Yellow
        Stop-Job -Job $backendJob -ErrorAction SilentlyContinue
        Remove-Job -Job $backendJob -Force -ErrorAction SilentlyContinue
        Stop-Job -Job $frontendJob -ErrorAction SilentlyContinue
        Remove-Job -Job $frontendJob -Force -ErrorAction SilentlyContinue
        if ($genofficeJob) {
            Stop-Job -Job $genofficeJob -ErrorAction SilentlyContinue
            Remove-Job -Job $genofficeJob -Force -ErrorAction SilentlyContinue
        }
        Write-Host "All services stopped." -ForegroundColor Gray
    }
} else {
    Write-Host "[Mode] Launching in dedicated console windows..." -ForegroundColor Yellow
    Write-Host ""

    # 1. Start Backend in dedicated window
    Write-Host "  -> Launching Backend on port $BackendPort..." -ForegroundColor Cyan
    Start-Process powershell.exe -ArgumentList @(
        "-ExecutionPolicy", "Bypass",
        "-NoExit",
        "-File", "`"$BackendScript`"",
        "-Port", "$BackendPort"
    )

    # 2. Start Frontend in dedicated window
    Write-Host "  -> Launching Frontend on port $FrontendPort..." -ForegroundColor Green
    Start-Process powershell.exe -ArgumentList @(
        "-ExecutionPolicy", "Bypass",
        "-NoExit",
        "-File", "`"$FrontendScript`"",
        "-Port", "$FrontendPort"
    )

    # 3. Start GenOffice in dedicated window
    if (-not $NoGenOffice) {
        Write-Host "  -> Waiting for web listeners to bind..." -ForegroundColor Gray
        Start-Sleep -Seconds 2
        Write-Host "  -> Launching GenOffice Desktop Suite & Shell..." -ForegroundColor Magenta
        Start-Process powershell.exe -ArgumentList @(
            "-ExecutionPolicy", "Bypass",
            "-NoExit",
            "-File", "`"$GenOfficeScript`""
        )
    }

    # Final brief pause to confirm initialization
    Start-Sleep -Seconds 1

    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host "          Limo + GenOffice Successfully Launched!           " -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host "  * Frontend UI:       http://localhost:$FrontendPort" -ForegroundColor White
    Write-Host "  * Backend API:       http://127.0.0.1:$BackendPort" -ForegroundColor White
    Write-Host "  * API Documentation: http://127.0.0.1:$BackendPort/docs" -ForegroundColor White
    if (-not $NoGenOffice) {
        Write-Host "  * GenOffice Suite:   Running (Electron Shell + Workspace)" -ForegroundColor White
    }
    Write-Host "============================================================" -ForegroundColor Green
    
    $winCount = if ($NoGenOffice) { "Two" } else { "Three" }
    Write-Host "$winCount dedicated PowerShell windows have been opened." -ForegroundColor Gray
    Write-Host "To shut down a service, simply close its terminal window or press Ctrl+C inside it." -ForegroundColor Gray
    Write-Host ""

    if ($OpenBrowser) {
        Write-Host "Opening browser at http://localhost:$FrontendPort..." -ForegroundColor Cyan
        Start-Process "http://localhost:$FrontendPort"
    }
}
