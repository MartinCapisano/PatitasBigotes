[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('webhook_reprocess','payments_reconcile','expire_stock_reservations','prune_auth_action_tokens','prune_auth_login_throttles')]
    [string]$Job,
    [string]$PythonExe = ''
)

$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Split-Path -Parent $scriptDir
$repoDir = Split-Path -Parent $backendDir

if ([string]::IsNullOrWhiteSpace($PythonExe)) {
    $venvPython = Join-Path $repoDir '.venv\Scripts\python.exe'
    if (Test-Path $venvPython) {
        $PythonExe = $venvPython
    }
    else {
        $PythonExe = 'python'
    }
}

switch ($Job) {
    'webhook_reprocess' {
        $jobArgs = @(
            '-m', 'source.jobs.reprocess_failed_webhooks_job',
            '--once'
        )
    }
    'payments_reconcile' {
        $jobArgs = @(
            '-m', 'source.jobs.reconcile_pending_payments_job',
            '--once'
        )
    }
    'expire_stock_reservations' {
        $jobArgs = @(
            '-m', 'source.jobs.expire_stock_reservations_job',
            '--once'
        )
    }
    'prune_auth_action_tokens' {
        $jobArgs = @(
            '-m', 'source.jobs.prune_auth_action_tokens_job',
            '--once'
        )
    }
    'prune_auth_login_throttles' {
        $jobArgs = @(
            '-m', 'source.jobs.prune_auth_login_throttles_job',
            '--once'
        )
    }
    default {
        throw "Unsupported job: $Job"
    }
}

Write-Host "Running job '$Job' with: $PythonExe $($jobArgs -join ' ')"
Push-Location $backendDir
try {
    & $PythonExe @jobArgs
    $exitCode = $LASTEXITCODE
    if ($null -ne $exitCode -and $exitCode -ne 0) {
        exit $exitCode
    }
}
finally {
    Pop-Location
}
