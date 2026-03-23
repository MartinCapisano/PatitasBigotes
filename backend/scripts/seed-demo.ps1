[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Split-Path -Parent $scriptDir
$repoDir = Split-Path -Parent $backendDir
$venvPython = Join-Path $repoDir ".venv\Scripts\python.exe"
$envPath = Join-Path $backendDir ".env"

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

if (-not (Test-Path $envPath)) {
    Write-Error "Falta backend/.env. Copia backend/.env.example y completa la configuracion antes de correr la demo seed."
    exit 1
}

Write-Host "Cargando demo data..."
Push-Location $backendDir
try {
    & $pythonExe -m source.seed_demo
}
finally {
    Pop-Location
}
