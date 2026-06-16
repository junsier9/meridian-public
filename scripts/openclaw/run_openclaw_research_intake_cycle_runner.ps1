[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $scriptRoot "..\\.."))
$helperPath = Join-Path $repoRoot "scripts\\common\\openclaw_scheduled_task_helpers.ps1"
. $helperPath
$taskEntry = Get-OpenClawScheduledTaskEntry -RepoRoot $repoRoot -TaskKey "research_intake_cycle"
$workbenchRoot = Join-Path $repoRoot "artifacts\\research_workbench"
$intakeWrapper = Join-Path $repoRoot "scripts\\openclaw\\run_openclaw_research_intake_cycle.py"
$runnerRoot = Join-Path $env:LOCALAPPDATA "EnhengClaw\\openclaw_research_workbench"
$logRoot = Join-Path $runnerRoot "intake_runner_logs"
$lockPath = Join-Path $runnerRoot "intake_runner.lock"
$stdoutCapturePath = Join-Path $runnerRoot "intake_runner.stdout.tmp"
$stderrCapturePath = Join-Path $runnerRoot "intake_runner.stderr.tmp"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logPath = Join-Path $logRoot ("openclaw_research_intake_runner_{0}.log" -f $stamp)

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

function Ensure-OpenClaw {
    if (-not [string]::IsNullOrWhiteSpace($env:OPENCLAW)) {
        return
    }
    $userOpenClaw = [Environment]::GetEnvironmentVariable("OPENCLAW", "User")
    if (-not [string]::IsNullOrWhiteSpace($userOpenClaw)) {
        $env:OPENCLAW = $userOpenClaw
        return
    }
    $machineOpenClaw = [Environment]::GetEnvironmentVariable("OPENCLAW", "Machine")
    if (-not [string]::IsNullOrWhiteSpace($machineOpenClaw)) {
        $env:OPENCLAW = $machineOpenClaw
        return
    }
    throw "OPENCLAW is not available in process, user, or machine environment."
}

Write-Log "task=openclaw_research_intake_cycle"
Write-Log "repo_root=$repoRoot"
Write-Log "workbench_root=$workbenchRoot"
Write-Log "intake_wrapper=$intakeWrapper"
Write-Log "log_path=$logPath"

if (-not (Test-Path $intakeWrapper)) {
    Write-Log "runner_status=FAIL_MISSING_WRAPPER"
    throw "research intake wrapper not found: $intakeWrapper"
}

try {
    $lockStream = [System.IO.File]::Open($lockPath, [System.IO.FileMode]::OpenOrCreate, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
} catch {
    Write-Log "runner_status=SKIPPED_ALREADY_RUNNING"
    $summaryPath = Write-OpenClawScheduledTaskImmediateSummary `
        -RepoRoot $repoRoot `
        -TaskEntry $taskEntry `
        -RunnerRoot $runnerRoot `
        -ExitCode 0 `
        -LogPath $logPath `
        -StdoutPath $stdoutCapturePath
    Write-Log "summary_path=$summaryPath"
    exit 0
}

try {
    Remove-Item -LiteralPath $stdoutCapturePath, $stderrCapturePath -Force -ErrorAction SilentlyContinue
    $upstreamStatus = Test-OpenClawScheduledTaskUpstreamFreshness -RepoRoot $repoRoot -TaskEntry $taskEntry
    Write-Log ("upstream_status={0}" -f $upstreamStatus.status)
    foreach ($blocker in @($upstreamStatus.blockers)) {
        Write-Log ("upstream_blocker={0}" -f $blocker)
    }
    if ($upstreamStatus.status -ne "ready") {
        Write-Log "runner_status=RETRY_UPSTREAM_NOT_READY"
        $summaryPath = Write-OpenClawScheduledTaskImmediateSummary `
            -RepoRoot $repoRoot `
            -TaskEntry $taskEntry `
            -RunnerRoot $runnerRoot `
            -ExitCode 75 `
            -LogPath $logPath `
            -StdoutPath $stdoutCapturePath
        Write-Log "summary_path=$summaryPath"
        exit 75
    }
    Ensure-OpenClaw
    $pythonExe = Get-PythonExecutable
    Write-Log "python_executable=$pythonExe"

    $process = Start-Process `
        -FilePath $pythonExe `
        -ArgumentList @(
            $intakeWrapper,
            "--workbench-root",
            $workbenchRoot,
            "--compiler-backend",
            "live"
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
