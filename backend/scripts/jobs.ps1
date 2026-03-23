[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet('status','enable','disable','reinstall','uninstall')]
    [string]$Command,
    [string]$TaskPrefix = 'PatitasBigotes'
)

$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$installScript = Join-Path $scriptDir 'install-jobs.ps1'

$jobDefinitions = @(
    @{ Name = 'WebhookReprocess'; Frequency = 'Every 10 minutes' },
    @{ Name = 'PaymentsReconcile'; Frequency = 'Every 4 hours' },
    @{ Name = 'ExpireStockReservations'; Frequency = 'Every 15 minutes' },
    @{ Name = 'PruneAuthActionTokens'; Frequency = 'Daily' },
    @{ Name = 'PruneAuthLoginThrottles'; Frequency = 'Daily' }
)

function Get-JobStatusRows {
    $rows = @()
    foreach ($job in $jobDefinitions) {
        $taskName = "${TaskPrefix}_$($job.Name)"
        $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        $info = $null
        if ($task) {
            $info = Get-ScheduledTaskInfo -TaskName $taskName
        }

        $rows += [PSCustomObject]@{
            Job            = $job.Name
            TaskName       = $taskName
            Frequency      = $job.Frequency
            Installed      = [bool]$task
            Enabled        = [bool]($task -and $task.State -ne 'Disabled')
            State          = if ($task) { [string]$task.State } else { 'Missing' }
            LastRunTime    = if ($info) { $info.LastRunTime } else { $null }
            NextRunTime    = if ($info) { $info.NextRunTime } else { $null }
            LastTaskResult = if ($info) { $info.LastTaskResult } else { $null }
        }
    }
    return $rows
}

function Show-Status {
    $rows = Get-JobStatusRows
    $active = ($rows | Where-Object { -not $_.Installed -or -not $_.Enabled }).Count -eq 0

    if ($active) {
        Write-Host 'AUTOMATIZACION: ACTIVADA' -ForegroundColor Green
    }
    else {
        Write-Host 'AUTOMATIZACION: DESACTIVADA' -ForegroundColor Yellow
    }

    $rows |
        Select-Object Job, State, Frequency, LastRunTime, NextRunTime, LastTaskResult |
        Format-Table -AutoSize

    Write-Host ''
    Write-Host 'Comandos:'
    Write-Host "  Activar:    .\backend\scripts\jobs.ps1 enable"
    Write-Host "  Desactivar: .\backend\scripts\jobs.ps1 disable"
    Write-Host "  Desinstalar:.\backend\scripts\jobs.ps1 uninstall"
    Write-Host "  Estado:     .\backend\scripts\jobs.ps1 status"
}

switch ($Command) {
    'status' {
        Show-Status
    }
    'enable' {
        if (-not (Test-Path $installScript)) {
            throw "Missing installer script: $installScript"
        }

        & powershell -NoProfile -ExecutionPolicy Bypass -File $installScript -TaskPrefix $TaskPrefix -Force
        Show-Status
    }
    'disable' {
        foreach ($job in $jobDefinitions) {
            $taskName = "${TaskPrefix}_$($job.Name)"
            $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
            if ($task -and $task.State -ne 'Disabled') {
                Disable-ScheduledTask -TaskName $taskName | Out-Null
            }
        }
        Show-Status
    }
    'reinstall' {
        if (-not (Test-Path $installScript)) {
            throw "Missing installer script: $installScript"
        }

        & powershell -NoProfile -ExecutionPolicy Bypass -File $installScript -TaskPrefix $TaskPrefix -Force
        Show-Status
    }
    'uninstall' {
        foreach ($job in $jobDefinitions) {
            $taskName = "${TaskPrefix}_$($job.Name)"
            $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
            if ($task) {
                Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
            }
        }
        Show-Status
    }
}
