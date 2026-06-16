[CmdletBinding()]
param(
    [string[]]$RequiredTaskKeys = @(
        "research_intake_cycle",
        "structural_research_scan",
        "quant_repo_health_guard",
        "quant_coinapi_spot_sync"
    ),
    [switch]$RepairMissingTasks,
    [bool]$RegisterStartupCatchup = $true,
    [bool]$AllowInteractiveFallback = $true
)

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $scriptRoot "..\\.."))
$helperPath = Join-Path $repoRoot "scripts\\common\\openclaw_scheduled_task_helpers.ps1"
. $helperPath

$manifest = Get-OpenClawScheduledTaskManifest -RepoRoot $repoRoot
$tasksByKey = @{}
foreach ($task in @($manifest.tasks)) {
    $tasksByKey[[string]$task.task_key] = $task
}

$results = @()
$missingAfterRepair = @()
$missingFromManifest = @()
$registeredDuringRepair = @()
$now = [DateTimeOffset]::UtcNow

foreach ($taskKey in @($RequiredTaskKeys)) {
    $key = [string]$taskKey
    if (-not $tasksByKey.ContainsKey($key)) {
        $missingFromManifest += $key
        continue
    }

    $taskEntry = $tasksByKey[$key]
    $taskName = [string]$taskEntry.task_name
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    $repaired = $false
    if ($null -eq $task -and $RepairMissingTasks) {
        Register-OpenClawScheduledTaskEntry `
            -RepoRoot $repoRoot `
            -TaskEntry $taskEntry `
            -RegisterStartupCatchup:$RegisterStartupCatchup `
            -AllowInteractiveFallback:$AllowInteractiveFallback
        $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        $repaired = ($null -ne $task)
        if ($repaired) {
            $registeredDuringRepair += $key
        }
    }

    if ($null -eq $task) {
        $missingAfterRepair += $key
    }

    $taskInfo = if ($null -ne $task) { Get-ScheduledTaskInfo -TaskName $taskName } else { $null }
    $summaryPath = Resolve-OpenClawScheduledTaskSummaryPath -TaskEntry $taskEntry
    $summary = if (-not [string]::IsNullOrWhiteSpace($summaryPath)) { Read-OpenClawScheduledTaskSummary -SummaryPath $summaryPath } else { $null }
    $summaryProducedAtUtc = if ($summary) { [string]$summary.produced_at_utc } else { $null }
    $summaryAgeHours = $null
    $summaryFresh = $null
    if (-not [string]::IsNullOrWhiteSpace($summaryProducedAtUtc)) {
        $producedAt = ConvertTo-OpenClawDateTimeOffset -Value $summaryProducedAtUtc
        $summaryAgeHours = [math]::Round(($now - $producedAt.ToUniversalTime()).TotalHours, 3)
        $summaryFresh = ([bool]$summary.success -and $summaryAgeHours -le [double]$taskEntry.freshness_budget_hours)
    }

    $results += [pscustomobject]@{
        task_key = $key
        task_name = $taskName
        scheduling_source = "windows_task_scheduler"
        cron_checked = $false
        exists = ($null -ne $task)
        repaired_during_run = $repaired
        state = if ($null -ne $task) { [string]$task.State } else { "MISSING" }
        last_task_result = if ($taskInfo) { [int]$taskInfo.LastTaskResult } else { $null }
        last_run_time = if ($taskInfo) { $taskInfo.LastRunTime.ToString("o") } else { $null }
        next_run_time = if ($taskInfo) { $taskInfo.NextRunTime.ToString("o") } else { $null }
        summary_path = $summaryPath
        summary_exists = (-not [string]::IsNullOrWhiteSpace($summaryPath) -and (Test-Path $summaryPath))
        summary_success = if ($summary) { [bool]$summary.success } else { $null }
        summary_produced_at_utc = $summaryProducedAtUtc
        summary_age_hours = $summaryAgeHours
        summary_fresh = $summaryFresh
    }
}

$status = if ($missingFromManifest.Count -gt 0 -or $missingAfterRepair.Count -gt 0) { "failed" } else { "passed" }
$warnings = @()
foreach ($entry in @($results)) {
    if (-not $entry.summary_exists) {
        $warnings += ("summary_missing:{0}" -f [string]$entry.task_key)
        continue
    }
    if ($null -eq $entry.summary_fresh) {
        $warnings += ("summary_unreadable:{0}" -f [string]$entry.task_key)
        continue
    }
    if (-not [bool]$entry.summary_fresh) {
        $warnings += ("summary_not_fresh:{0}" -f [string]$entry.task_key)
    }
}

[pscustomobject]@{
    status = $status
    generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    repo_root = $repoRoot
    scheduling_source = "windows_task_scheduler"
    repair_requested = [bool]$RepairMissingTasks
    registered_during_repair = @($registeredDuringRepair)
    missing_from_manifest = @($missingFromManifest)
    missing_after_repair = @($missingAfterRepair)
    warnings = @($warnings)
    tasks = @($results)
} | ConvertTo-Json -Depth 8
