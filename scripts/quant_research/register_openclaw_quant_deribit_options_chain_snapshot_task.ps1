[CmdletBinding()]
param(
    [System.Management.Automation.PSCredential]$Credential,
    [switch]$RegisterStartupCatchup = $true,
    [switch]$AllowInteractiveFallback
)

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $scriptRoot "..\.."))
$helperPath = Join-Path $repoRoot "scripts\common\openclaw_scheduled_task_helpers.ps1"
. $helperPath
$taskEntry = Get-OpenClawScheduledTaskEntry -RepoRoot $repoRoot -TaskKey "quant_deribit_options_chain_snapshot"
$taskName = [string]$taskEntry.task_name
$runnerPath = Join-Path $repoRoot "scripts\quant_research\run_openclaw_quant_deribit_options_chain_snapshot_runner.ps1"

if (-not (Test-Path $runnerPath)) {
    throw "runner not found: $runnerPath"
}

Register-OpenClawScheduledTaskEntry `
    -RepoRoot $repoRoot `
    -TaskEntry $taskEntry `
    -Credential $Credential `
    -RegisterStartupCatchup:$RegisterStartupCatchup `
    -AllowInteractiveFallback:$AllowInteractiveFallback

$task = Get-ScheduledTask -TaskName $taskName
$taskInfo = Get-ScheduledTaskInfo -TaskName $taskName
$startupTaskName = Get-OpenClawStartupCatchupTaskName -TaskEntry $taskEntry
$startupTaskInfo = Get-ScheduledTaskInfo -TaskName $startupTaskName -ErrorAction SilentlyContinue

Write-Output ("task_name={0}" -f $task.TaskName)
Write-Output ("runner_path={0}" -f $runnerPath)
Write-Output ("status={0}" -f $task.State)
Write-Output ("last_task_result={0}" -f $taskInfo.LastTaskResult)
Write-Output ("next_run_time={0}" -f $taskInfo.NextRunTime.ToString("o"))
if ($startupTaskInfo) {
    Write-Output ("startup_catchup_task_name={0}" -f $startupTaskName)
    Write-Output ("startup_catchup_next_run_time={0}" -f $startupTaskInfo.NextRunTime.ToString("o"))
}
