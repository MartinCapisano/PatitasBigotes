[CmdletBinding()]
param(
    [switch]$PersistLogs
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Split-Path -Parent $scriptDir
$logsDir = Join-Path $backendDir "tmp\logs"

if (-not (Get-Command ngrok -ErrorAction SilentlyContinue)) {
    Write-Error "ngrok no esta instalado o no esta en PATH."
    Write-Error "Ejecuta: winget install --id Ngrok.Ngrok -e"
    exit 1
}

$fixedDomain = "terpenic-dampishly-reda.ngrok-free.dev"
$fixedUrl = "https://$fixedDomain"

Write-Host "Abriendo tunnel ngrok fijo hacia http://localhost:8000 ..."
Write-Host "Dominio fijo: $fixedUrl"
Write-Host "Webhook esperado: $fixedUrl/payments/webhook/mercadopago"

try {
    if ($PersistLogs) {
        New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
        $logPath = Join-Path $logsDir "ngrok.log"
        Write-Host "Persistiendo logs en $logPath"
        & ngrok http --url=$fixedUrl 8000 2>&1 | Tee-Object -FilePath $logPath -Append
    }
    else {
        ngrok http --url=$fixedUrl 8000
    }
}
catch {
    Write-Warning "Fallo con --url. Reintentando con --domain ..."
    if ($PersistLogs) {
        New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
        $logPath = Join-Path $logsDir "ngrok.log"
        & ngrok http --domain=$fixedDomain 8000 2>&1 | Tee-Object -FilePath $logPath -Append
    }
    else {
        ngrok http --domain=$fixedDomain 8000
    }
}
