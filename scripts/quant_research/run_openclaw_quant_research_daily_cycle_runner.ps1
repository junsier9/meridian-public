[CmdletBinding()]
param(
    [string]$AsOf = "",
    [switch]$Catchup
)

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $scriptRoot "..\\.."))
$helperPath = Join-Path $repoRoot "scripts\\common\\openclaw_scheduled_task_helpers.ps1"
. $helperPath
$taskEntry = Get-OpenClawScheduledTaskEntry -RepoRoot $repoRoot -TaskKey "quant_research_daily_cycle"
$runnerRoot = Join-Path $env:LOCALAPPDATA "EnhengClaw\\quant_research"
$logRoot = Join-Path $runnerRoot "runner_logs"
$lockPath = Join-Path $runnerRoot "quant_research.lock"
$cycleWrapper = Join-Path $repoRoot "scripts\\quant_research\\run_quant_research_cycle.py"
$binanceOhlcvRoot = Join-Path $env:LOCALAPPDATA "EnhengClaw\\market_history\\binance_ohlcv"
$coinApiSpotRoot = Join-Path $env:LOCALAPPDATA "EnhengClaw\\market_history\\coinapi_ohlcv"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logPath = Join-Path $logRoot ("openclaw_quant_research_runner_{0}.log" -f $stamp)

New-Item -ItemType Directory -Path $logRoot -Force | Out-Null

function Write-Log {
    param([string]$Message)
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Write-Host $line
    Add-Content -LiteralPath $logPath -Value $line
}

if (-not (Test-Path $cycleWrapper)) {
    throw "quant cycle wrapper not found: $cycleWrapper"
}

try {
    $lockStream = [System.IO.File]::Open($lockPath, [System.IO.FileMode]::OpenOrCreate, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
} catch {
    Write-Log "runner_status=SKIPPED_ALREADY_RUNNING"
    exit 0
}

try {
    $effectiveAsOf = $AsOf
    if ([string]::IsNullOrWhiteSpace($effectiveAsOf)) {
        $effectiveAsOf = (Get-Date).ToString("yyyy-MM-dd")
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
    $stdoutCapturePath = Join-Path $runnerRoot "quant_research.stdout.tmp"
    $stderrCapturePath = Join-Path $runnerRoot "quant_research.stderr.tmp"
    $childSummaryPath = Join-Path $logRoot ("openclaw_quant_research_runner_{0}.child_summary.json" -f $stamp)
    $failureSummaryPath = Join-Path $logRoot ("openclaw_quant_research_runner_{0}.failure_summary.json" -f $stamp)
    Remove-Item -LiteralPath $stdoutCapturePath, $stderrCapturePath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $childSummaryPath, $failureSummaryPath -Force -ErrorAction SilentlyContinue

    Write-Log "task=openclaw_quant_monitoring_daily_cycle"
    Write-Log "repo_root=$repoRoot"
    Write-Log "as_of=$effectiveAsOf"
    Write-Log "wrapper=$cycleWrapper"
    Write-Log "python_executable=$pythonExe"
    Write-Log "ohlcv_external_root=$binanceOhlcvRoot"
    Write-Log "spot_ohlcv_external_root=$coinApiSpotRoot"

    $process = Start-Process `
        -FilePath $pythonExe `
        -ArgumentList @(
            $cycleWrapper,
            "--as-of",
            $effectiveAsOf,
            "--compiler-backend",
            "deterministic",
            "--ohlcv-external-root",
            $binanceOhlcvRoot,
            "--spot-ohlcv-external-root",
            $coinApiSpotRoot,
            "--summary-out",
            $childSummaryPath,
            "--failure-summary-out",
            $failureSummaryPath
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
        -StdoutPath $stdoutCapturePath `
        -ChildSummaryPath $childSummaryPath `
        -FailureSummaryPath $failureSummaryPath
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
