[CmdletBinding()]
param(
    [switch]$SkipVenv,
    [switch]$SkipInstall,
    [switch]$SkipMigrations,
    [switch]$EnableJobs,
    [switch]$ForceJobs
)

$ErrorActionPreference = 'Stop'

function Write-Step {
    param([string]$Message)
    Write-Host "`n==> $Message"
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Split-Path -Parent $scriptDir
$repoDir = Split-Path -Parent $backendDir

$venvDir = Join-Path $repoDir '.venv'
$venvPython = Join-Path $venvDir 'Scripts\python.exe'
$requirementsPath = Join-Path $backendDir 'requirements.txt'
$requirementsDevPath = Join-Path $backendDir 'requirements-dev.txt'
$envPath = Join-Path $backendDir '.env'
$installJobsScript = Join-Path $scriptDir 'install-jobs.ps1'

Write-Host "Repo:    $repoDir"
Write-Host "Backend: $backendDir"

if (-not $SkipVenv) {
    if (-not (Test-Path $venvPython)) {
        Write-Step 'Creating .venv'
        if (Get-Command py -ErrorAction SilentlyContinue) {
            & py -3 -m venv $venvDir
        }
        elseif (Get-Command python -ErrorAction SilentlyContinue) {
            & python -m venv $venvDir
        }
        else {
            throw 'Python launcher not found (py/python). Install Python first.'
        }
    }
    else {
        Write-Step '.venv already exists'
    }
}

if (-not (Test-Path $venvPython)) {
    throw "Python executable not found at $venvPython. Run bootstrap without -SkipVenv or create .venv manually."
}

if (-not $SkipInstall) {
    if (-not (Test-Path $requirementsPath)) {
        throw "requirements file not found: $requirementsPath"
    }
    Write-Step 'Installing dependencies from backend/requirements.txt'
    & $venvPython -m pip install --upgrade pip
    & $venvPython -m pip install -r $requirementsPath
    if (Test-Path $requirementsDevPath) {
        Write-Step 'Installing development tools from backend/requirements-dev.txt'
        & $venvPython -m pip install -r $requirementsDevPath
    }
}

if (-not (Test-Path $envPath)) {
    throw "Missing backend/.env at $envPath. Create it before running migrations."
}

if (-not $SkipMigrations) {
    Write-Step 'Applying database migrations via Alembic'
    Push-Location $backendDir
    try {
        & $venvPython -m alembic upgrade head
    }
    finally {
        Pop-Location
    }
}

if ($EnableJobs) {
    if (-not (Test-Path $installJobsScript)) {
        throw "Missing jobs installer script: $installJobsScript"
    }
    Write-Step 'Installing scheduled jobs'
    if ($ForceJobs) {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $installJobsScript -Force
    }
    else {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $installJobsScript
    }
}
else {
    Write-Step 'Skipping scheduled jobs (use -EnableJobs to install)'
}

Write-Step 'Bootstrap completed'
Write-Host 'Next step: run backend/scripts/start-backend.ps1'
