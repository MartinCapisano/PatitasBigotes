[CmdletBinding()]
param(
    [switch]$SkipVenv,
    [switch]$SkipInstall,
    [switch]$SkipMigrations,
    [switch]$SeedDemo,
    [Alias('InstallJobs')]
    [switch]$EnableJobs,
    [switch]$NoJobs,
    [switch]$ForceJobs,
    [switch]$StartApp
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
$seedDemoScript = Join-Path $scriptDir 'seed-demo.ps1'
$startAppScript = Join-Path $scriptDir 'start-app.ps1'

Write-Host "Repo:    $repoDir"
Write-Host "Backend: $backendDir"

if ($EnableJobs -and $NoJobs) {
    throw 'Use only one of -EnableJobs/-InstallJobs or -NoJobs.'
}

if ($ForceJobs -and -not $EnableJobs) {
    throw '-ForceJobs requires -EnableJobs or -InstallJobs.'
}

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
else {
    Write-Step 'Skipping database migrations'
}

if ($SeedDemo) {
    if (-not (Test-Path $seedDemoScript)) {
        throw "Missing demo seed script: $seedDemoScript"
    }
    if ($SkipMigrations) {
        Write-Step 'Demo seed requested with -SkipMigrations'
        Write-Host 'Assuming the target database schema is already up to date.'
    }

    Write-Step 'Loading demo seed data'
    & powershell -NoProfile -ExecutionPolicy Bypass -File $seedDemoScript
}
else {
    Write-Step 'Skipping demo seed (use -SeedDemo to load demo data)'
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
elseif ($NoJobs) {
    Write-Step 'Skipping scheduled jobs by explicit choice (-NoJobs)'
}
else {
    Write-Step 'Skipping scheduled jobs (use -InstallJobs or -EnableJobs to install, or -NoJobs to make it explicit)'
}

if ($StartApp) {
    if (-not (Test-Path $startAppScript)) {
        throw "Missing app start script: $startAppScript"
    }
    Write-Step 'Starting backend and frontend'
    & powershell -NoProfile -ExecutionPolicy Bypass -File $startAppScript
}

Write-Step 'Bootstrap completed'
if ($StartApp) {
    Write-Host 'App launch requested via -StartApp.'
}
else {
    Write-Host 'Next step: run backend/scripts/start-backend.ps1'
}
