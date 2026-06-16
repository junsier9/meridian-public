[CmdletBinding()]
param(
    [string]$AsOf = "",
    [string]$WeekOf = "",
    [switch]$Catchup
)

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $scriptRoot "..\\.."))
$helperPath = Join-Path $repoRoot "scripts\\common\\openclaw_scheduled_task_helpers.ps1"
. $helperPath
$taskEntry = Get-OpenClawScheduledTaskEntry -RepoRoot $repoRoot -TaskKey "quant_strategy_proposal_cycle"
$runnerRoot = Join-Path $env:LOCALAPPDATA "EnhengClaw\\quant_research"
$logRoot = Join-Path $runnerRoot "proposal_runner_logs"
$lockPath = Join-Path $runnerRoot "quant_strategy_proposal.lock"
$cycleWrapper = Join-Path $repoRoot "scripts\\quant_research\\run_quant_strategy_proposal_cycle.py"
$binanceOhlcvRoot = Join-Path $env:LOCALAPPDATA "EnhengClaw\\market_history\\binance_ohlcv"
$coinApiSpotRoot = Join-Path $env:LOCALAPPDATA "EnhengClaw\\market_history\\coinapi_ohlcv"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logPath = Join-Path $logRoot ("openclaw_quant_strategy_proposal_runner_{0}.log" -f $stamp)

New-Item -ItemType Directory -Path $logRoot -Force | Out-Null

function Write-Log {
    param([string]$Message)
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Write-Host $line
    Add-Content -LiteralPath $logPath -Value $line
}

Write-Log "runner_status=LEGACY_SURFACE_FROZEN"
Write-Log "error_code=legacy_quant_surface_frozen"
exit 78

if (-not (Test-Path $cycleWrapper)) {
    throw "proposal cycle wrapper not found: $cycleWrapper"
}

try {
    $lockStream = [System.IO.File]::Open($lockPath, [System.IO.FileMode]::OpenOrCreate, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
} catch {
    Write-Log "runner_status=SKIPPED_ALREADY_RUNNING"
    exit 0
}

try {
    $effectiveWeekOf = $WeekOf
    if ([string]::IsNullOrWhiteSpace($AsOf) -and -not [string]::IsNullOrWhiteSpace($effectiveWeekOf)) {
        $AsOf = $effectiveWeekOf
    }
    if ([string]::IsNullOrWhiteSpace($AsOf)) {
        $AsOf = (Get-Date).ToString("yyyy-MM-dd")
    }
    if ($Catchup) {
        $summaryPath = Resolve-OpenClawScheduledTaskSummaryPath -TaskEntry $taskEntry
        $catchupDecision = Get-OpenClawScheduledTaskCatchupDecision -TaskEntry $taskEntry -SummaryPath $summaryPath
        Write-Log ("catchup_reason={0}" -f $catchupDecision.reason)
        if (-not $catchupDecision.should_run) {
            Write-Log "runner_status=SKIPPED_CATCHUP_NOT_REQUIRED"
            exit 0
        }
        $upstreamStatus = Test-OpenClawScheduledTaskUpstreamFreshness -RepoRoot $repoRoot -TaskEntry $taskEntry
        Write-Log ("upstream_status={0}" -f $upstreamStatus.status)
        foreach ($blocker in @($upstreamStatus.blockers)) {
            Write-Log ("upstream_blocker={0}" -f $blocker)
        }
        if ($upstreamStatus.status -ne "ready") {
            Write-Log "runner_status=RETRY_UPSTREAM_NOT_READY"
            exit 75
        }
    }
    try {
        $pythonExe = Assert-OpenClawScientificPythonRuntime -RepoRoot $repoRoot
    } catch {
        Write-Log $_.Exception.Message
        exit 86
    }
    $stdoutCapturePath = Join-Path $runnerRoot "quant_strategy_proposal.stdout.tmp"
    $stderrCapturePath = Join-Path $runnerRoot "quant_strategy_proposal.stderr.tmp"
    Remove-Item -LiteralPath $stdoutCapturePath, $stderrCapturePath -Force -ErrorAction SilentlyContinue

    Write-Log "task=openclaw_quant_exploration_daily_full_cycle"
    Write-Log "repo_root=$repoRoot"
    Write-Log "as_of=$AsOf"
    if (-not [string]::IsNullOrWhiteSpace($effectiveWeekOf)) {
        Write-Log "week_of_alias=$effectiveWeekOf"
    }
    Write-Log "wrapper=$cycleWrapper"
    Write-Log "python_executable=$pythonExe"
    Write-Log "ohlcv_external_root=$binanceOhlcvRoot"
    Write-Log "spot_ohlcv_external_root=$coinApiSpotRoot"

    $process = Start-Process `
        -FilePath $pythonExe `
        -ArgumentList @(
            $cycleWrapper,
            "--as-of",
            $AsOf,
            "--compiler-backend",
            "deterministic",
            "--ohlcv-external-root",
            $binanceOhlcvRoot,
            "--spot-ohlcv-external-root",
            $coinApiSpotRoot
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
    $summaryPath = Write-OpenClawScheduledTaskSummary `
        -RepoRoot $repoRoot `
        -TaskEntry $taskEntry `
        -RunnerRoot $runnerRoot `
        -ExitCode $process.ExitCode `
        -LogPath $logPath `
        -StdoutPath $stdoutCapturePath
    Write-Log "summary_path=$summaryPath"
    Remove-Item -LiteralPath $stdoutCapturePath, $stderrCapturePath -Force -ErrorAction SilentlyContinue

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
