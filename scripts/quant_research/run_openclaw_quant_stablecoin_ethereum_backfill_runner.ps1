[CmdletBinding()]
param(
    [int]$WindowDays = 30,
    [int]$BatchDays = 1,
    [string]$Providers = "eth_rpc_logs,alchemy_transfers",
    [string]$Symbols = "USDT,USDC,DAI"
)

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $scriptRoot "..\.."))
$helperPath = Join-Path $repoRoot "scripts\common\openclaw_scheduled_task_helpers.ps1"
. $helperPath
$runnerRoot = Join-Path $env:LOCALAPPDATA "EnhengClaw\quant_research"
$logRoot = Join-Path $runnerRoot "stablecoin_ethereum_backfill_runner_logs"
$lockPath = Join-Path $runnerRoot "quant_stablecoin_ethereum_sync.lock"
$wrapperPath = Join-Path $repoRoot "scripts\quant_research\run_quant_stablecoin_ethereum_backfill.py"
$summaryPath = Join-Path $runnerRoot "quant_stablecoin_ethereum_backfill.last_run_summary.json"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logPath = Join-Path $logRoot ("openclaw_quant_stablecoin_ethereum_backfill_runner_{0}.log" -f $stamp)

New-Item -ItemType Directory -Path $logRoot -Force | Out-Null

function Write-Log {
    param([string]$Message)
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Write-Host $line
    Add-Content -LiteralPath $logPath -Value $line
}

if (-not (Test-Path $wrapperPath)) {
    throw "stablecoin backfill wrapper not found: $wrapperPath"
}

try {
    $lockStream = [System.IO.File]::Open($lockPath, [System.IO.FileMode]::OpenOrCreate, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
} catch {
    Write-Log "runner_status=SKIPPED_ALREADY_RUNNING"
    exit 0
}

try {
    try {
        $pythonExe = Assert-OpenClawScientificPythonRuntime -RepoRoot $repoRoot
    } catch {
        Write-Log $_.Exception.Message
        exit 86
    }

    $stdoutCapturePath = Join-Path $runnerRoot "quant_stablecoin_ethereum_backfill.stdout.tmp"
    $stderrCapturePath = Join-Path $runnerRoot "quant_stablecoin_ethereum_backfill.stderr.tmp"
    Remove-Item -LiteralPath $stdoutCapturePath, $stderrCapturePath -Force -ErrorAction SilentlyContinue

    Write-Log "task=openclaw_quant_stablecoin_ethereum_backfill"
    Write-Log "repo_root=$repoRoot"
    Write-Log "wrapper=$wrapperPath"
    Write-Log "python_executable=$pythonExe"
    Write-Log "window_days=$WindowDays"
    Write-Log "batch_days=$BatchDays"
    Write-Log "providers=$Providers"
    Write-Log "symbols=$Symbols"

    $process = Start-Process `
        -FilePath $pythonExe `
        -ArgumentList @(
            $wrapperPath,
            "--window-days", "$WindowDays",
            "--batch-days", "$BatchDays",
            "--providers", $Providers,
            "--symbols", $Symbols
        ) `
        -WorkingDirectory $repoRoot `
        -NoNewWindow `
        -Wait `
        -PassThru `
        -RedirectStandardOutput $stdoutCapturePath `
        -RedirectStandardError $stderrCapturePath

    foreach ($capturePath in @($stdoutCapturePath, $stderrCapturePath)) {
        if (Test-Path $capturePath) {
            foreach ($line in Get-Content -LiteralPath $capturePath) {
                Write-Log $line
            }
        }
    }

    $summary = [ordered]@{
        task = "openclaw_quant_stablecoin_ethereum_backfill"
        success = ($process.ExitCode -eq 0)
        exit_code = $process.ExitCode
        generated_at = (Get-Date).ToString("o")
        window_days = $WindowDays
        batch_days = $BatchDays
        providers = $Providers
        symbols = $Symbols
        log_path = $logPath
        stdout_path = $stdoutCapturePath
        stderr_path = $stderrCapturePath
    }
    $summary | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $summaryPath -Encoding UTF8
    Write-Log "summary_path=$summaryPath"

    if ($process.ExitCode -ne 0) {
        Write-Log ("runner_status=FAIL exit_code={0}" -f $process.ExitCode)
        exit $process.ExitCode
    }

    Write-Log "runner_status=PASS"
    exit 0
} finally {
    if ($lockStream) {
        $lockStream.Dispose()
    }
    Remove-Item -LiteralPath $lockPath -Force -ErrorAction SilentlyContinue
}
