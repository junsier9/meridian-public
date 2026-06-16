[CmdletBinding()]
param(
    [switch]$IncludeStartupCatchup = $true,
    [System.Management.Automation.PSCredential]$Credential
)

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $scriptRoot "..\\.."))
$helperPath = Join-Path $repoRoot "scripts\\common\\openclaw_scheduled_task_helpers.ps1"
. $helperPath

$manifest = Get-OpenClawScheduledTaskManifest -RepoRoot $repoRoot
$tasks = @($manifest.tasks)
if ($tasks.Count -eq 0) {
    throw "no scheduled tasks declared in manifest."
}

$passwordTasks = @($tasks | Where-Object {
    (Get-OpenClawScheduledTaskRegistration -TaskEntry $_).principal_mode -eq "password"
})

$resolvedCredential = $Credential
if ($passwordTasks.Count -gt 0 -and $null -eq $resolvedCredential) {
    $defaultUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $resolvedCredential = Get-Credential -UserName $defaultUser -Message "Enter Windows credentials for OpenClaw scheduled tasks."
}

$results = foreach ($taskEntry in $tasks) {
    Register-OpenClawScheduledTaskEntry `
        -RepoRoot $repoRoot `
        -TaskEntry $taskEntry `
        -Credential $resolvedCredential `
        -RegisterStartupCatchup:$IncludeStartupCatchup

    $task = Get-ScheduledTask -TaskName ([string]$taskEntry.task_name)
    $taskInfo = Get-ScheduledTaskInfo -TaskName ([string]$taskEntry.task_name)
    $startupName = Get-OpenClawStartupCatchupTaskName -TaskEntry $taskEntry
    $startupTask = Get-ScheduledTask -TaskName $startupName -ErrorAction SilentlyContinue
    [pscustomobject]@{
        task_name = $task.TaskName
        next_run_time = $taskInfo.NextRunTime.ToString("o")
        startup_catchup_task = if ($null -ne $startupTask) { $startupTask.TaskName } else { $null }
    }
}

$results | ConvertTo-Json -Depth 5
