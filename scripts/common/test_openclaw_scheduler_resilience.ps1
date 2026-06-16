[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $scriptRoot "..\\.."))
$helperPath = Join-Path $repoRoot "scripts\\common\\openclaw_scheduled_task_helpers.ps1"
. $helperPath

function Get-CurrentWakeTimerIndices {
    $raw = & powercfg /Q SCHEME_CURRENT SUB_SLEEP RTCWAKE
    if ($LASTEXITCODE -ne 0) {
        throw "failed to inspect RTCWAKE settings"
    }
    $text = ($raw | Out-String)
    $matches = [regex]::Matches($text, "0x([0-9A-Fa-f]{8})")
    return [pscustomobject]@{
        ac = if ($matches.Count -ge 2) { [string]$matches[$matches.Count - 2].Groups[1].Value } else { $null }
        dc = if ($matches.Count -ge 1) { [string]$matches[$matches.Count - 1].Groups[1].Value } else { $null }
    }
}

$manifest = Get-OpenClawScheduledTaskManifest -RepoRoot $repoRoot
$taskSummaries = foreach ($taskEntry in @($manifest.tasks)) {
    $taskName = [string]$taskEntry.task_name
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    $resilience = Get-OpenClawScheduledTaskResilience -TaskEntry $taskEntry
    $startupName = Get-OpenClawStartupCatchupTaskName -TaskEntry $taskEntry
    $startupTask = Get-ScheduledTask -TaskName $startupName -ErrorAction SilentlyContinue
    [pscustomobject]@{
        task_name = $taskName
        exists = ($null -ne $task)
        logon_type = if ($null -ne $task) { [string]$task.Principal.LogonType } else { $null }
        wake_to_run = if ($null -ne $task) { [bool]$task.Settings.WakeToRun } else { $null }
        start_when_available = if ($null -ne $task) { [bool]$task.Settings.StartWhenAvailable } else { $null }
        restart_count = if ($null -ne $task) { [int]$task.Settings.RestartCount } else { $null }
        restart_interval = if ($null -ne $task) { [string]$task.Settings.RestartInterval } else { $null }
        startup_catchup_enabled = [bool]$resilience.startup_catchup_enabled
        startup_catchup_task_exists = ($null -ne $startupTask)
    }
}

$wakeTimers = Get-CurrentWakeTimerIndices
[pscustomobject]@{
    generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    rtcwake_ac = $wakeTimers.ac
    rtcwake_dc = $wakeTimers.dc
    tasks = $taskSummaries
} | ConvertTo-Json -Depth 6
