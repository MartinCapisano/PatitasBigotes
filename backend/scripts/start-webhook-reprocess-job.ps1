[CmdletBinding()]
param(
    [switch]$Once,
    [int]$IntervalMinutes = 0,
    [int]$BatchSize = 0,
    [int]$MaxAttempts = 0,
    [int]$BaseDelayMinutes = 0,
    [int]$MaxDelayMinutes = 0
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Split-Path -Parent $scriptDir
$repoDir = Split-Path -Parent $backendDir
$venvPython = Join-Path $repoDir ".venv\Scripts\python.exe"

$jobArgs = @("-m", "source.jobs.reprocess_failed_webhooks_job")
if ($Once) {
    $jobArgs += "--once"
}
if ($IntervalMinutes -gt 0) {
    $jobArgs += @("--interval-minutes", "$IntervalMinutes")
}
if ($BatchSize -gt 0) {
    $jobArgs += @("--batch-size", "$BatchSize")
}
if ($MaxAttempts -gt 0) {
    $jobArgs += @("--max-attempts", "$MaxAttempts")
}
if ($BaseDelayMinutes -gt 0) {
    $jobArgs += @("--base-delay-minutes", "$BaseDelayMinutes")
}
if ($MaxDelayMinutes -gt 0) {
    $jobArgs += @("--max-delay-minutes", "$MaxDelayMinutes")
}

if (Test-Path $venvPython) {
    $pythonExe = $venvPython
}
elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonExe = "python"
}
else {
    Write-Error "No se encontro Python ni la .venv del proyecto."
    exit 1
}

Write-Host "Iniciando worker de reproceso de webhooks failed..."
Write-Host "Comando: $pythonExe $($jobArgs -join ' ')"
Push-Location $backendDir
try {
    & $pythonExe @jobArgs
}
finally {
    Pop-Location
}
