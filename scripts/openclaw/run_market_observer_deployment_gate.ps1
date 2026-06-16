param(
    [string]$ExternalRoot = "",
    [string]$RetainRoot = "",
    [string]$TrustRootDir = "",
    [int]$ExpiresAfterHours = 24
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = if ($env:PYTHON -and -not [string]::IsNullOrWhiteSpace($env:PYTHON)) { $env:PYTHON } else { "python" }
$Args = @(
    (Join-Path $ScriptDir "run_market_observer_deployment_gate.py"),
    "--expires-after-hours",
    [string]$ExpiresAfterHours
)

if (-not [string]::IsNullOrWhiteSpace($ExternalRoot)) {
    $Args += @("--external-root", $ExternalRoot)
}
if (-not [string]::IsNullOrWhiteSpace($RetainRoot)) {
    $Args += @("--retain-root", $RetainRoot)
}
if (-not [string]::IsNullOrWhiteSpace($TrustRootDir)) {
    $Args += @("--trust-root-dir", $TrustRootDir)
}

& $Python @Args
exit $LASTEXITCODE
