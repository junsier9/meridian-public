[CmdletBinding()]
param(
    [ValidateSet("auto", "refresh", "bootstrap")]
    [string]$Mode = "auto",
    [switch]$Catchup
)

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $scriptRoot "..\\.."))
$helperPath = Join-Path $repoRoot "scripts\\common\\openclaw_scheduled_task_helpers.ps1"
. $helperPath
$taskEntry = Get-OpenClawScheduledTaskEntry -RepoRoot $repoRoot -TaskKey "binance_ohlcv_sync"
$workbenchRoot = Join-Path $repoRoot "artifacts\\research_workbench"
$syncWrapper = Join-Path $repoRoot "scripts\\market_data\\sync_binance_ohlcv.py"
$runnerRoot = Join-Path $env:LOCALAPPDATA "EnhengClaw\\market_history\\binance_ohlcv"
$logRoot = Join-Path $runnerRoot "sync_runner_logs"
$lockPath = Join-Path $runnerRoot "sync_runner.lock"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logPath = Join-Path $logRoot ("openclaw_binance_ohlcv_sync_runner_{0}.log" -f $stamp)

New-Item -ItemType Directory -Path $logRoot -Force | Out-Null

function Write-Log {
    param([string]$Message)
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Write-Host $line
    Add-Content -LiteralPath $logPath -Value $line
}

function Get-PythonExecutable {
    $venvPython = Join-Path $repoRoot ".venv\\Scripts\\python.exe"
    if (Test-Path $venvPython) {
        return $venvPython
    }
    return "python"
}

function Resolve-Mode {
    param([string]$RequestedMode)
    if ($RequestedMode -ne "auto") {
        return $RequestedMode
    }
    $now = Get-Date
    if ($now.Hour -eq 2 -and $now.Minute -ge 25 -and $now.Minute -le 40) {
        return "bootstrap"
    }
    return "refresh"
}

Write-Log "task=openclaw_binance_ohlcv_sync_runner"
Write-Log "repo_root=$repoRoot"
Write-Log "workbench_root=$workbenchRoot"
Write-Log "sync_wrapper=$syncWrapper"
Write-Log "log_path=$logPath"

if (-not (Test-Path $syncWrapper)) {
    Write-Log "runner_status=FAIL_MISSING_WRAPPER"
    throw "binance OHLCV sync wrapper not found: $syncWrapper"
}

try {
    $lockStream = [System.IO.File]::Open($lockPath, [System.IO.FileMode]::OpenOrCreate, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
} catch {
    Write-Log "runner_status=SKIPPED_ALREADY_RUNNING"
    exit 0
}

try {
    $lockStream.SetLength(0)
    $lockWriter = New-Object System.IO.StreamWriter($lockStream)
    $lockWriter.AutoFlush = $true
    $lockWriter.WriteLine("pid=$PID")
    $lockWriter.WriteLine("started_at=$(Get-Date -Format o)")
    $lockWriter.WriteLine("log_path=$logPath")

    if ($Catchup) {
        $summaryPath = Resolve-OpenClawScheduledTaskSummaryPath -TaskEntry $taskEntry
        $catchupDecision = Get-OpenClawScheduledTaskCatchupDecision -TaskEntry $taskEntry -SummaryPath $summaryPath
        Write-Log ("catchup_reason={0}" -f $catchupDecision.reason)
        if (-not $catchupDecision.should_run) {
            Write-Log "runner_status=SKIPPED_CATCHUP_NOT_REQUIRED"
            exit 0
        }
    }

    $pythonExe = Get-PythonExecutable
    $effectiveMode = if ($Catchup) { "refresh" } else { Resolve-Mode -RequestedMode $Mode }
    Write-Log "python_executable=$pythonExe"
    Write-Log "effective_mode=$effectiveMode"

    $stdoutCapturePath = Join-Path $runnerRoot "sync_runner.stdout.tmp"
    $stderrCapturePath = Join-Path $runnerRoot "sync_runner.stderr.tmp"
    Remove-Item -LiteralPath $stdoutCapturePath, $stderrCapturePath -Force -ErrorAction SilentlyContinue

    $process = Start-Process `
        -FilePath $pythonExe `
        -ArgumentList @(
            $syncWrapper,
            "--mode",
            $effectiveMode,
            "--markets",
            "spot,usdm_perp",
            "--intervals",
            "1h,4h,1d",
            "--workbench-root",
            $workbenchRoot
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
    $exitCode = $process.ExitCode
    Remove-Item -LiteralPath $stdoutCapturePath, $stderrCapturePath -Force -ErrorAction SilentlyContinue

    if ($exitCode -ne 0) {
        Write-Log ("runner_status=FAIL exit_code={0}" -f $exitCode)
        exit $exitCode
    }

    Write-Log "runner_status=PASS"
    exit 0
} finally {
    if ($lockWriter) {
        $lockWriter.Dispose()
    }
    if ($lockStream) {
        $lockStream.Dispose()
    }
    Remove-Item -LiteralPath $lockPath -Force -ErrorAction SilentlyContinue
}
