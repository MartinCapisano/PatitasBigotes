[CmdletBinding()]
param(
    [switch]$PersistLogs
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Split-Path -Parent $scriptDir
$repoDir = Split-Path -Parent $backendDir
$venvPython = Join-Path $repoDir ".venv\Scripts\python.exe"
$logsDir = Join-Path $backendDir "tmp\logs"

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

Write-Host "Iniciando backend en http://localhost:8000 ..."
Write-Host "Comando: $pythonExe -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload"
Push-Location $backendDir
try {
    if ($PersistLogs) {
        New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
        $logPath = Join-Path $logsDir "uvicorn.log"
        Write-Host "Persistiendo logs en $logPath"
        & $pythonExe -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload 2>&1 |
            Tee-Object -FilePath $logPath -Append
    }
    else {
        & $pythonExe -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
    }
}
finally {
    Pop-Location
}
