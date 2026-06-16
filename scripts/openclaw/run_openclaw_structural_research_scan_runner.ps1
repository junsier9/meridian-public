[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $scriptRoot "..\\.."))
$helperPath = Join-Path $repoRoot "scripts\\common\\openclaw_scheduled_task_helpers.ps1"
. $helperPath
$taskEntry = Get-OpenClawScheduledTaskEntry -RepoRoot $repoRoot -TaskKey "structural_research_scan"
$workbenchRoot = Join-Path $repoRoot "artifacts\\research_workbench"
$scanInputRoot = Join-Path $workbenchRoot "_scan_inputs"
$scanWrapper = Join-Path $repoRoot "scripts\\openclaw\\run_openclaw_research_scan.py"
$runnerRoot = Join-Path $env:LOCALAPPDATA "EnhengClaw\\openclaw_research_workbench"
$logRoot = Join-Path $runnerRoot "scan_runner_logs"
$lockPath = Join-Path $runnerRoot "scan_runner.lock"
$stdoutCapturePath = Join-Path $runnerRoot "scan_runner.stdout.tmp"
$stderrCapturePath = Join-Path $runnerRoot "scan_runner.stderr.tmp"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logPath = Join-Path $logRoot ("openclaw_structural_research_scan_runner_{0}.log" -f $stamp)

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

function Get-ScanMetadata {
    param(
        [Parameter(Mandatory = $true)]
        [System.IO.FileInfo]$ScanFile
    )

    try {
        $payload = Get-Content -LiteralPath $ScanFile.FullName -Raw | ConvertFrom-Json -ErrorAction Stop
    } catch {
        throw "invalid market scan JSON: $($ScanFile.FullName) :: $($_.Exception.Message)"
    }

    $scanId = [string]$payload.scan_id
    if ([string]::IsNullOrWhiteSpace($scanId)) {
        throw "market scan is missing required scan_id: $($ScanFile.FullName)"
    }

    $scanSummaryPath = Join-Path $workbenchRoot "_scan_runs\\$scanId\\scan_summary.json"
    return [pscustomobject]@{
        ScanPath = $ScanFile.FullName
        ScanName = $ScanFile.Name
        ScanId = $scanId
        ScanSummaryPath = $scanSummaryPath
    }
}

function Get-NextUnconsumedScan {
    if (-not (Test-Path $scanInputRoot)) {
        return $null
    }

    $scanFiles = Get-ChildItem -LiteralPath $scanInputRoot -Filter "*.market_scan.json" -File |
        Sort-Object LastWriteTime, Name

    foreach ($scanFile in $scanFiles) {
        $metadata = Get-ScanMetadata -ScanFile $scanFile
        if (Test-Path $metadata.ScanSummaryPath) {
            Write-Log ("scan_status=SKIPPED_ALREADY_CONSUMED market_scan={0} scan_id={1}" -f $metadata.ScanPath, $metadata.ScanId)
            continue
        }
        return $metadata
    }

    return $null
}

Write-Log "task=openclaw_structural_research_scan_runner"
Write-Log "repo_root=$repoRoot"
Write-Log "workbench_root=$workbenchRoot"
Write-Log "scan_input_root=$scanInputRoot"
Write-Log "scan_wrapper=$scanWrapper"
Write-Log "log_path=$logPath"

if (-not (Test-Path $scanWrapper)) {
    Write-Log "runner_status=FAIL_MISSING_WRAPPER"
    throw "research scan wrapper not found: $scanWrapper"
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
    $lockStream.SetLength(0)
    $lockWriter = New-Object System.IO.StreamWriter($lockStream)
    $lockWriter.AutoFlush = $true
    $lockWriter.WriteLine("pid=$PID")
    $lockWriter.WriteLine("started_at=$(Get-Date -Format o)")
    $lockWriter.WriteLine("log_path=$logPath")

    $pythonExe = Get-PythonExecutable
    Write-Log "python_executable=$pythonExe"
    Remove-Item -LiteralPath $stdoutCapturePath, $stderrCapturePath -Force -ErrorAction SilentlyContinue

    $selectedScan = Get-NextUnconsumedScan
    if ($null -eq $selectedScan) {
        Write-Log "runner_status=SKIPPED_NO_NEW_MARKET_SCAN"
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

    Write-Log ("selected_market_scan={0}" -f $selectedScan.ScanPath)
    Write-Log ("selected_scan_id={0}" -f $selectedScan.ScanId)
    Write-Log ("expected_scan_summary={0}" -f $selectedScan.ScanSummaryPath)

    $process = Start-Process `
        -FilePath $pythonExe `
        -ArgumentList @(
            $scanWrapper,
            "--market-scan",
            $selectedScan.ScanPath,
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

    if (Test-Path $selectedScan.ScanSummaryPath) {
        Write-Log ("scan_summary_path={0}" -f $selectedScan.ScanSummaryPath)
    }

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
