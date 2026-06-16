param(
    [string]$ArtifactsRoot = (Join-Path (Split-Path -Parent $PSScriptRoot) "artifacts"),
    [string]$ExecutionPermitPath = $env:ENHENGCLAW_EXECUTION_PERMIT_PATH,
    [string]$Label = ("real-24h-" + (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")),
    [int]$DurationSeconds = 86400,
    [string]$ClockReferenceUrl = "https://api.binance.com/api/v3/time",
    [string]$BinanceWebsocketUrl = "wss://stream.binance.com:9443/ws",
    [string]$AlchemyEndpointUrl = "",
    [int]$MinFreeDiskMb = 1024,
    [long]$MaxTotalLogBytes = 134217728,
    [double]$ClockSkewThresholdSeconds = 30,
    [double]$ProviderProbeTimeoutSeconds = 10,
    [double]$MinPermitMarginSeconds = 86460,
    [switch]$AllowExistingLabel,
    [ValidateSet("DEBUG", "INFO", "WARNING", "ERROR")]
    [string]$LogLevel = "INFO"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$command = @(
    (Join-Path $repoRoot "scripts\verify\run_real_shadow_acceptance.py"),
    "--mode", "real-24h",
    "--artifacts-root", [System.IO.Path]::GetFullPath($ArtifactsRoot),
    "--duration-seconds", $DurationSeconds,
    "--label", $Label,
    "--clock-reference-url", $ClockReferenceUrl,
    "--binance-websocket-url", $BinanceWebsocketUrl,
    "--min-free-disk-mb", $MinFreeDiskMb,
    "--max-total-log-bytes", $MaxTotalLogBytes,
    "--clock-skew-threshold-seconds", $ClockSkewThresholdSeconds,
    "--provider-probe-timeout-seconds", $ProviderProbeTimeoutSeconds,
    "--min-permit-margin-seconds", $MinPermitMarginSeconds,
    "--log-level", $LogLevel
)

if (-not [string]::IsNullOrWhiteSpace($ExecutionPermitPath)) {
    $command += @("--execution-permit", [System.IO.Path]::GetFullPath($ExecutionPermitPath))
}
if (-not [string]::IsNullOrWhiteSpace($AlchemyEndpointUrl)) {
    $command += @("--alchemy-endpoint-url", $AlchemyEndpointUrl)
}
if ($AllowExistingLabel.IsPresent) {
    $command += "--allow-existing-label"
}

& python @command
exit $LASTEXITCODE
