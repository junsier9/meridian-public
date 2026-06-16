[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$compatRunner = Join-Path $scriptRoot "run_openclaw_research_intake_cycle_runner.ps1"

if (-not (Test-Path $compatRunner)) {
    throw "intake runner not found: $compatRunner"
}

& $compatRunner
exit $LASTEXITCODE
