param(
    [string]$ArtifactsRoot = "",
    [string]$RunRoot = "",
    [int]$DurationSeconds = 1800,
    [double]$AlchemyPollIntervalSeconds = 5.0,
    [double]$BinanceMaxBackoffSeconds = 30.0,
    [int]$WatchdogPollIntervalSeconds = 60,
    [ValidateSet("DEBUG", "INFO", "WARNING", "ERROR")]
    [string]$LogLevel = "INFO",
    [switch]$DisableWatchdog
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-JsonFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [object]$Data
    )

    $json = $Data | ConvertTo-Json -Depth 12
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $json, $utf8NoBom)
}

function Write-JsonLine {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [object]$Data
    )

    $json = $Data | ConvertTo-Json -Compress -Depth 12
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::AppendAllText($Path, $json + [Environment]::NewLine, $utf8NoBom)
}

function Get-FileLength {
    param([string]$Path)
    if (Test-Path -LiteralPath $Path) {
        return (Get-Item -LiteralPath $Path).Length
    }
    return 0
}

function Get-TextCount {
    param(
        [string]$Text,
        [string]$Pattern
    )
    return ([regex]::Matches($Text, [regex]::Escape($Pattern))).Count
}

function Read-SharedText {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        return ""
    }

    $stream = [System.IO.File]::Open(
        $Path,
        [System.IO.FileMode]::Open,
        [System.IO.FileAccess]::Read,
        [System.IO.FileShare]::ReadWrite
    )
    try {
        $reader = New-Object System.IO.StreamReader($stream, [System.Text.Encoding]::UTF8, $true)
        try {
            return $reader.ReadToEnd()
        } finally {
            $reader.Dispose()
        }
    } finally {
        $stream.Dispose()
    }
}

function Join-ProcessArguments {
    param([string[]]$Arguments)
    return (($Arguments | ForEach-Object {
        '"' + ($_ -replace '"', '\"') + '"'
    }) -join " ")
}

function Write-WatchdogEvent {
    param(
        [string]$Severity,
        [string]$CheckName,
        [string]$Action,
        [string]$Reason,
        [object]$Metrics
    )

    Write-JsonLine -Path $watchdogEventsPath -Data ([ordered]@{
        generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
        severity = $Severity
        segment_id = "day3_warmup_test_segment"
        check_name = $CheckName
        action = $Action
        reason = $Reason
        metrics = $Metrics
        process_id = $script:ShadowProcessId
    })
}

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not $RunRoot) {
    $RunRoot = Join-Path $repoRoot "artifacts\runtime_evidence\day3\test_segment"
}
$RunRoot = [System.IO.Path]::GetFullPath($RunRoot)
if (-not $ArtifactsRoot) {
    $ArtifactsRoot = Join-Path $RunRoot "artifacts"
}
$ArtifactsRoot = [System.IO.Path]::GetFullPath($ArtifactsRoot)

$stdoutLog = Join-Path $RunRoot "shadow_ingest.stdout.log"
$stderrLog = Join-Path $RunRoot "shadow_ingest.stderr.log"
$runConfigPath = Join-Path $RunRoot "run_config.json"
$exitStatusPath = Join-Path $RunRoot "exit_status.json"
$watchdogEventsPath = Join-Path $RunRoot "watchdog_events.jsonl"
$watchdogSummaryPath = Join-Path $RunRoot "watchdog_summary.json"
$collectorOutputPath = Join-Path $RunRoot "collector_output.json"
$watchdogStopPath = Join-Path $RunRoot "watchdog.stop"

New-Item -ItemType Directory -Force -Path $RunRoot | Out-Null

if ((Test-Path -LiteralPath $ArtifactsRoot) -and $ArtifactsRoot.StartsWith($RunRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    Remove-Item -LiteralPath $ArtifactsRoot -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $ArtifactsRoot | Out-Null

foreach ($path in @($stdoutLog, $stderrLog, $runConfigPath, $exitStatusPath, $watchdogEventsPath, $watchdogSummaryPath, $collectorOutputPath, $watchdogStopPath)) {
    if (Test-Path -LiteralPath $path) {
        Remove-Item -LiteralPath $path -Force
    }
}

$runnerArgs = @(
    "--artifacts-root", $ArtifactsRoot,
    "--run-seconds", "$DurationSeconds",
    "--log-level", $LogLevel,
    "--alchemy-poll-interval-seconds", "$AlchemyPollIntervalSeconds",
    "--binance-max-backoff-seconds", "$BinanceMaxBackoffSeconds"
)
$startedAtUtc = (Get-Date).ToUniversalTime().ToString("o")
Write-JsonFile -Path $runConfigPath -Data ([ordered]@{
    launched_at_utc = $startedAtUtc
    repo_root = $repoRoot
    artifacts_root = $ArtifactsRoot
    run_root = $RunRoot
    command = "shadow-ingest"
    arguments = $runnerArgs
    stdout_log = $stdoutLog
    stderr_log = $stderrLog
    duration_seconds = $DurationSeconds
    watchdog = [ordered]@{
        enabled = -not $DisableWatchdog
        poll_interval_seconds = $WatchdogPollIntervalSeconds
        restart_enabled = $false
        events_path = $watchdogEventsPath
        summary_path = $watchdogSummaryPath
    }
    fault_injection = [ordered]@{
        enabled = $false
    }
})

$script:WatchdogJob = $null
$script:ShadowProcessId = $null

if (-not $DisableWatchdog) {
    $script:WatchdogJob = Start-Job -ScriptBlock {
        param(
            [string]$StdoutLog,
            [string]$StderrLog,
            [string]$EventsPath,
            [string]$StopPath,
            [int]$PollIntervalSeconds
        )

        function Append-JsonLine {
            param([string]$Path, [object]$Data)
            $json = $Data | ConvertTo-Json -Compress -Depth 12
            $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
            [System.IO.File]::AppendAllText($Path, $json + [Environment]::NewLine, $utf8NoBom)
        }

        function File-Length {
            param([string]$Path)
            if (Test-Path -LiteralPath $Path) {
                return (Get-Item -LiteralPath $Path).Length
            }
            return 0
        }

        function Read-Shared {
            param([string]$Path)
            if (-not (Test-Path -LiteralPath $Path)) {
                return ""
            }
            $stream = [System.IO.File]::Open($Path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
            try {
                $reader = New-Object System.IO.StreamReader($stream, [System.Text.Encoding]::UTF8, $true)
                try {
                    return $reader.ReadToEnd()
                } finally {
                    $reader.Dispose()
                }
            } finally {
                $stream.Dispose()
            }
        }

        function Count-Text {
            param([string]$Text, [string]$Pattern)
            return ([regex]::Matches($Text, [regex]::Escape($Pattern))).Count
        }

        function Event {
            param([string]$Severity, [string]$CheckName, [string]$Action, [string]$Reason, [object]$Metrics)
            Append-JsonLine -Path $EventsPath -Data ([ordered]@{
                generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
                severity = $Severity
                segment_id = "day3_warmup_test_segment"
                check_name = $CheckName
                action = $Action
                reason = $Reason
                metrics = $Metrics
                process_id = $null
            })
        }

        Event -Severity "P3" -CheckName "process_liveness" -Action "observe" -Reason "watchdog_started_restart_disabled" -Metrics ([ordered]@{
            restart_enabled = $false
            poll_interval_seconds = $PollIntervalSeconds
        })
        $lastStdoutLength = File-Length -Path $StdoutLog
        $lastStderrLength = File-Length -Path $StderrLog
        $lastAlchemyRetryCount = 0
        $lastBinanceReconnectCount = 0
        $lastLineCount = 0
        $consecutiveNoGrowthPolls = 0

        while (-not (Test-Path -LiteralPath $StopPath)) {
            Start-Sleep -Seconds $PollIntervalSeconds
            $stdoutLength = File-Length -Path $StdoutLog
            $stderrLength = File-Length -Path $StderrLog
            $totalGrowth = ($stdoutLength - $lastStdoutLength) + ($stderrLength - $lastStderrLength)
            if ($totalGrowth -le 0) {
                $consecutiveNoGrowthPolls += 1
            } else {
                $consecutiveNoGrowthPolls = 0
            }

            $combinedLogs = (Read-Shared -Path $StdoutLog) + "`n" + (Read-Shared -Path $StderrLog)
            $alchemyRetryCount = Count-Text -Text $combinedLogs -Pattern "Alchemy RPC transient failure"
            $binanceReconnectCount = Count-Text -Text $combinedLogs -Pattern "Binance WebSocket disconnected; reconnect attempt"
            $lineCount = if ($combinedLogs.Length -eq 0) { 0 } else { ($combinedLogs -split "`r?`n").Count }
            $retryDelta = ($alchemyRetryCount - $lastAlchemyRetryCount) + ($binanceReconnectCount - $lastBinanceReconnectCount)
            $lineDelta = $lineCount - $lastLineCount

            if ($consecutiveNoGrowthPolls -ge 10) {
                Event -Severity "P1" -CheckName "log_growth" -Action "alert" -Reason "no_log_growth_for_10_watchdog_polls" -Metrics ([ordered]@{
                    consecutive_no_growth_polls = $consecutiveNoGrowthPolls
                    stdout_length = $stdoutLength
                    stderr_length = $stderrLength
                })
            }
            if ($retryDelta -gt 50) {
                Event -Severity "P1" -CheckName "retry_growth" -Action "alert" -Reason "retry_delta_exceeded_threshold" -Metrics ([ordered]@{
                    retry_delta = $retryDelta
                    alchemy_retry_count = $alchemyRetryCount
                    binance_reconnect_count = $binanceReconnectCount
                })
            }
            if ($lineDelta -gt 2000) {
                Event -Severity "P1" -CheckName "busy_loop" -Action "alert" -Reason "log_line_delta_exceeded_busy_loop_threshold" -Metrics ([ordered]@{
                    line_delta = $lineDelta
                    poll_interval_seconds = $PollIntervalSeconds
                })
            }

            $lastStdoutLength = $stdoutLength
            $lastStderrLength = $stderrLength
            $lastAlchemyRetryCount = $alchemyRetryCount
            $lastBinanceReconnectCount = $binanceReconnectCount
            $lastLineCount = $lineCount
        }
    } -ArgumentList $stdoutLog, $stderrLog, $watchdogEventsPath, $watchdogStopPath, $WatchdogPollIntervalSeconds
}

$shadowProcess = Start-Process `
    -FilePath "shadow-ingest" `
    -ArgumentList $runnerArgs `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog `
    -PassThru `
    -Wait
$processExitCode = $shadowProcess.ExitCode
$script:ShadowProcessId = $shadowProcess.Id

if (-not $DisableWatchdog) {
    New-Item -ItemType File -Force -Path $watchdogStopPath | Out-Null
    Wait-Job -Id $script:WatchdogJob.Id -Timeout ($WatchdogPollIntervalSeconds + 10) | Out-Null
    Receive-Job -Id $script:WatchdogJob.Id -ErrorAction SilentlyContinue | Out-Null
    Remove-Job -Id $script:WatchdogJob.Id -Force
}
$endedAtUtc = (Get-Date).ToUniversalTime().ToString("o")

if (-not $DisableWatchdog) {
    $severity = if ($processExitCode -eq 0) { "P3" } else { "P0" }
    $action = if ($processExitCode -eq 0) { "observe" } else { "fail" }
    Write-WatchdogEvent -Severity $severity -CheckName "process_liveness" -Action $action -Reason "process_exited" -Metrics ([ordered]@{
        exit_code = $processExitCode
        restart_enabled = $false
    })
}

$summaryCounts = @{
    P0 = 0
    P1 = 0
    P2 = 0
    P3 = 0
}
if (Test-Path -LiteralPath $watchdogEventsPath) {
    foreach ($line in Get-Content -LiteralPath $watchdogEventsPath) {
        if (-not $line.Trim()) {
            continue
        }
        $event = $line | ConvertFrom-Json
        if ($summaryCounts.ContainsKey($event.severity)) {
            $summaryCounts[$event.severity] += 1
        }
    }
}

Write-JsonFile -Path $watchdogSummaryPath -Data ([ordered]@{
    generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    enabled = -not $DisableWatchdog
    restart_enabled = $false
    p0_count = $summaryCounts["P0"]
    p1_count = $summaryCounts["P1"]
    p2_count = $summaryCounts["P2"]
    p3_count = $summaryCounts["P3"]
    events_path = $watchdogEventsPath
})

Write-JsonFile -Path $exitStatusPath -Data ([ordered]@{
    started_at_utc = $startedAtUtc
    ended_at_utc = $endedAtUtc
    exit_code = $processExitCode
    process_id = $script:ShadowProcessId
    stdout_log = $stdoutLog
    stderr_log = $stderrLog
})

Write-Output "run_root: $RunRoot"
Write-Output "artifacts_root: $ArtifactsRoot"
Write-Output "watchdog_events: $watchdogEventsPath"
Write-Output "watchdog_summary: $watchdogSummaryPath"
exit $processExitCode
