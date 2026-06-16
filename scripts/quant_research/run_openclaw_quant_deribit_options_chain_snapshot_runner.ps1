[CmdletBinding()]
param(
    [string]$AsOf = "",
    [switch]$Catchup
)

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $scriptRoot "..\.."))
$helperPath = Join-Path $repoRoot "scripts\common\openclaw_scheduled_task_helpers.ps1"
. $helperPath
$taskEntry = Get-OpenClawScheduledTaskEntry -RepoRoot $repoRoot -TaskKey "quant_deribit_options_chain_snapshot"
$runnerRoot = Join-Path $env:LOCALAPPDATA "EnhengClaw\quant_research"
$logRoot = Join-Path $runnerRoot "deribit_options_chain_snapshot_runner_logs"
$lockPath = Join-Path $runnerRoot "quant_deribit_options_chain_snapshot.lock"
$cycleWrapper = Join-Path $repoRoot "scripts\quant_research\run_quant_deribit_options_chain_snapshot_cycle.py"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logPath = Join-Path $logRoot ("openclaw_quant_deribit_options_chain_snapshot_runner_{0}.log" -f $stamp)

New-Item -ItemType Directory -Path $logRoot -Force | Out-Null

function Write-Log {
    param([string]$Message)
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Write-Host $line
    Add-Content -LiteralPath $logPath -Value $line
}

if (-not (Test-Path $cycleWrapper)) {
    throw "Deribit options snapshot wrapper not found: $cycleWrapper"
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
    }
    try {
        $pythonExe = Assert-OpenClawScientificPythonRuntime -RepoRoot $repoRoot
    } catch {
        Write-Log $_.Exception.Message
        exit 86
    }
    $stdoutCapturePath = Join-Path $runnerRoot "quant_deribit_options_chain_snapshot.stdout.tmp"
    $stderrCapturePath = Join-Path $runnerRoot "quant_deribit_options_chain_snapshot.stderr.tmp"
    Remove-Item -LiteralPath $stdoutCapturePath, $stderrCapturePath -Force -ErrorAction SilentlyContinue

    Write-Log "task=openclaw_quant_deribit_options_chain_snapshot"
    Write-Log "repo_root=$repoRoot"
    Write-Log "as_of=$effectiveAsOf"
    Write-Log "wrapper=$cycleWrapper"
    Write-Log "python_executable=$pythonExe"

    $process = Start-Process `
        -FilePath $pythonExe `
        -ArgumentList @(
            $cycleWrapper
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
