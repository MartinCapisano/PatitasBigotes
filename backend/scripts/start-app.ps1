[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$startBackendScript = Join-Path $scriptDir "start-backend.ps1"
$startFrontendScript = Join-Path $scriptDir "start-frontend.ps1"

if (-not (Test-Path $startBackendScript)) {
    throw "Missing backend start script: $startBackendScript"
}

if (-not (Test-Path $startFrontendScript)) {
    throw "Missing frontend start script: $startFrontendScript"
}

Write-Host "Abriendo backend y frontend en ventanas separadas..."

Start-Process powershell.exe -ArgumentList @(
    '-NoExit',
    '-NoProfile',
    '-ExecutionPolicy', 'Bypass',
    '-File', $startBackendScript
) | Out-Null

Start-Process powershell.exe -ArgumentList @(
    '-NoExit',
    '-NoProfile',
    '-ExecutionPolicy', 'Bypass',
    '-File', $startFrontendScript
) | Out-Null

Write-Host "Backend:  http://localhost:8000"
Write-Host "Frontend: http://localhost:5173"
