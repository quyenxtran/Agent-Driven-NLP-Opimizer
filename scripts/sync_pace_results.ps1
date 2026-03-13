param(
    [string]$RemoteHost = "qtran47@login-phoenix-gnr-1",
    [string]$RemoteRepo = "/storage/home/hcoda1/4/qtran47/AutoResearch-SMB",
    [string]$LocalRepo = (Split-Path -Parent $PSScriptRoot),
    [string]$SyncRoot = "",
    [switch]$IncludeLogs,
    [switch]$StageRunsOnly
)

$ErrorActionPreference = "Stop"

if (-not $SyncRoot) {
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $SyncRoot = Join-Path $LocalRepo "artifacts\pace_sync\$timestamp"
}

$scp = Get-Command scp -ErrorAction SilentlyContinue
if (-not $scp) {
    throw "scp not found on PATH. Install or enable OpenSSH client first."
}

$items = @("artifacts/smb_stage_runs")
if (-not $StageRunsOnly) {
    $items += "artifacts/agent_runs"
}
if ($IncludeLogs) {
    $items += "logs"
}

New-Item -ItemType Directory -Force -Path $SyncRoot | Out-Null

foreach ($item in $items) {
    $localTarget = Join-Path $SyncRoot ($item -replace "/", "\")
    $localParent = Split-Path -Parent $localTarget
    New-Item -ItemType Directory -Force -Path $localParent | Out-Null
    Write-Host "Syncing $item -> $localTarget"
    & $scp.Source -r "${RemoteHost}:${RemoteRepo}/${item}" "$localParent"
}

Write-Host ""
Write-Host "PACE sync complete."
Write-Host "Local sync root: $SyncRoot"
