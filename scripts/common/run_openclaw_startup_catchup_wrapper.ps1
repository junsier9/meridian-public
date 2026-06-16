[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$RunnerPath,
    [int]$DelayMinutes = 0
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $RunnerPath)) {
    throw "runner not found: $RunnerPath"
}

if ($DelayMinutes -gt 0) {
    Start-Sleep -Seconds ($DelayMinutes * 60)
}

& $RunnerPath -Catchup
exit $LASTEXITCODE
