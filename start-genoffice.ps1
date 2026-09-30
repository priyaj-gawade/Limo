<#
.SYNOPSIS
    Starts the Limo GenOffice Desktop & Office Workspace Engine.

.DESCRIPTION
    Checks Node.js / npm dependencies in engines/office and launches the
    full GenOffice development suite and Electron shell (npm run dev).

.EXAMPLE
    .\start-genoffice.ps1
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$OfficeDir = Join-Path $ScriptDir "engines\office"

# Set window title if in a console host
try {
    $Host.UI.RawUI.WindowTitle = "Limo GenOffice (Office Suite & Shell)"
} catch {
    # Ignore if not supported in current host
}

Write-Host "============================================================" -ForegroundColor Magenta
Write-Host "     Starting Limo GenOffice (Workspace & Electron Shell)   " -ForegroundColor Magenta
Write-Host "============================================================" -ForegroundColor Magenta

if (-not (Test-Path $OfficeDir)) {
    Write-Error "GenOffice directory not found at '$OfficeDir'."
    exit 1
}

# Check if Node.js is installed
try {
    $nodeVer = & node -v
    Write-Host "Node.js:           $nodeVer" -ForegroundColor Gray
} catch {
    Write-Error "Node.js is not found on PATH. Please install Node.js (v22+) to run GenOffice."
    exit 1
}

$NodeModules = Join-Path $OfficeDir "node_modules"
if (-not (Test-Path $NodeModules)) {
    Write-Host "Dependencies not found. Running 'npm install' in engines/office..." -ForegroundColor Yellow
    Push-Location $OfficeDir
    try {
        & npm install
    } catch {
        Write-Error "Failed to install GenOffice dependencies: $_"
        exit 1
    }
    Pop-Location
}

Write-Host "Working Directory: $OfficeDir" -ForegroundColor Gray
Write-Host "Engine:            GenOffice Multi-App Shell (Docs, Sheets, Slides, PDF, MD, HTML)" -ForegroundColor Gray
Write-Host "Press Ctrl+C to stop the office engine." -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Magenta
Write-Host ""

Set-Location $OfficeDir

try {
    & npm run dev
} catch {
    Write-Error "Failed to start GenOffice: $_"
    exit 1
}
