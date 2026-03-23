[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Split-Path -Parent $scriptDir
$repoDir = Split-Path -Parent $backendDir
$frontendDir = Join-Path $repoDir "frontend"
$packageJsonPath = Join-Path $frontendDir "package.json"

if (-not (Test-Path $packageJsonPath)) {
    Write-Error "No se encontro frontend/package.json."
    exit 1
}

if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue) -and -not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Error "No se encontro npm en PATH."
    exit 1
}

Write-Host "Iniciando frontend en http://localhost:5173 ..."
Write-Host "Comando: npm run dev"
Push-Location $frontendDir
try {
    if (Get-Command npm.cmd -ErrorAction SilentlyContinue) {
        & npm.cmd run dev
    }
    else {
        & npm run dev
    }
}
finally {
    Pop-Location
}
