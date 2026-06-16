function ConvertFrom-OpenClawJson {
    param(
        [Parameter(Mandatory = $true)][string]$Json,
        [int]$Depth = 8
    )

    $command = Get-Command ConvertFrom-Json -ErrorAction Stop
    if ($command.Parameters.ContainsKey("Depth")) {
        return ($Json | ConvertFrom-Json -Depth $Depth)
    }
    return ($Json | ConvertFrom-Json)
}

function Get-OpenClawScheduledTaskManifest {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot
    )

    $manifestPath = Join-Path $RepoRoot "config\\scheduled_tasks\\manifest.json"
    if (-not (Test-Path $manifestPath)) {
        throw "scheduled task manifest not found: $manifestPath"
    }
    return (ConvertFrom-OpenClawJson -Json (Get-Content -LiteralPath $manifestPath -Raw) -Depth 12)
}

function Get-OpenClawScheduledTaskEntry {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [Parameter(Mandatory = $true)][string]$TaskKey
    )

    $manifest = Get-OpenClawScheduledTaskManifest -RepoRoot $RepoRoot
    foreach ($task in $manifest.tasks) {
        if ($task.task_key -eq $TaskKey) {
            return $task
        }
    }
    throw "scheduled task entry not found for task_key=$TaskKey"
}

function Get-OpenClawScheduledTaskRegistration {
    param(
        [Parameter(Mandatory = $true)]$TaskEntry
    )

    $registration = if ($TaskEntry.registration) { $TaskEntry.registration } else { @{} }
    $principalMode = [string]$registration.principal_mode
    if ([string]::IsNullOrWhiteSpace($principalMode)) {
        $principalMode = "interactive"
    }
    $runLevel = [string]$registration.run_level
    if ([string]::IsNullOrWhiteSpace($runLevel)) {
        $runLevel = "limited"
    }
    return [pscustomobject]@{
        principal_mode = $principalMode.ToLowerInvariant()
        run_level = $runLevel
    }
}

function Get-OpenClawScheduledTaskResilience {
    param(
        [Parameter(Mandatory = $true)]$TaskEntry
    )

    $resilience = if ($TaskEntry.resilience) { $TaskEntry.resilience } else { @{} }
    return [pscustomobject]@{
        wake_to_run = [bool]$resilience.wake_to_run
        restart_count = if ($null -ne $resilience.restart_count) { [int]$resilience.restart_count } else { 0 }
        restart_interval_minutes = if ($null -ne $resilience.restart_interval_minutes) { [int]$resilience.restart_interval_minutes } else { 0 }
        startup_catchup_enabled = [bool]$resilience.startup_catchup_enabled
        startup_delay_minutes = if ($null -ne $resilience.startup_delay_minutes) { [int]$resilience.startup_delay_minutes } else { 0 }
    }
}

function New-OpenClawScheduledTaskTriggers {
    param(
        [Parameter(Mandatory = $true)]$TaskEntry
    )

    $schedule = $TaskEntry.schedule
    switch ($schedule.type) {
        "daily" {
            return @(New-ScheduledTaskTrigger -Daily -At $schedule.time)
        }
        "weekly" {
            return @(New-ScheduledTaskTrigger -Weekly -WeeksInterval ([int]$schedule.weeks_interval) -DaysOfWeek $schedule.days_of_week -At $schedule.time)
        }
        "once_repeating" {
            $start = Get-Date -Hour ([int]$schedule.start_time.Split(":")[0]) -Minute ([int]$schedule.start_time.Split(":")[1]) -Second 0
            $triggers = @(
                New-ScheduledTaskTrigger `
                    -Once `
                    -At $start `
                    -RepetitionInterval (New-TimeSpan -Minutes ([int]$schedule.repeat_minutes)) `
                    -RepetitionDuration (New-TimeSpan -Days ([int]$schedule.repeat_duration_days))
            )
            foreach ($extraTime in @($schedule.extra_daily_times)) {
                if (-not [string]::IsNullOrWhiteSpace([string]$extraTime)) {
                    $triggers += New-ScheduledTaskTrigger -Daily -At ([string]$extraTime)
                }
            }
            return $triggers
        }
        default {
            throw "unsupported scheduled task type: $($schedule.type)"
        }
    }
}

function Resolve-OpenClawScheduledTaskSummaryPath {
    param(
        [Parameter(Mandatory = $true)]$TaskEntry
    )

    $command = [string]$TaskEntry.success_discovery_command
    if ([string]::IsNullOrWhiteSpace($command)) {
        return $null
    }
    $match = [regex]::Match($command, 'Get-Content\s+"([^"]+)"')
    if (-not $match.Success) {
        return $null
    }
    return (Expand-OpenClawEnvironmentPath -Value $match.Groups[1].Value)
}

function Get-OpenClawEnvironmentVariableValue {
    param(
        [Parameter(Mandatory = $true)][string]$Name
    )

    foreach ($scope in @("Process", "User", "Machine")) {
        $value = if ($scope -eq "Process") {
            [Environment]::GetEnvironmentVariable($Name)
        } else {
            [Environment]::GetEnvironmentVariable($Name, $scope)
        }
        if (-not [string]::IsNullOrWhiteSpace($value)) {
            return $value
        }
    }
    return $null
}

function Expand-OpenClawEnvironmentPath {
    param(
        [Parameter(Mandatory = $true)][string]$Value
    )

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $Value
    }
    $expanded = [regex]::Replace(
        $Value,
        '\$env:([A-Za-z_][A-Za-z0-9_]*)|\$\{env:([A-Za-z_][A-Za-z0-9_]*)\}',
        {
            param($match)
            $variableName = if ($match.Groups[1].Success) { $match.Groups[1].Value } else { $match.Groups[2].Value }
            $resolved = Get-OpenClawEnvironmentVariableValue -Name $variableName
            if ([string]::IsNullOrWhiteSpace($resolved)) {
                return $match.Value
            }
            return $resolved
        }
    )
    return [Environment]::ExpandEnvironmentVariables($expanded)
}

function Read-OpenClawScheduledTaskSummary {
    param(
        [Parameter(Mandatory = $true)][string]$SummaryPath
    )

    if (-not (Test-Path $SummaryPath)) {
        return $null
    }
    $raw = Get-Content -LiteralPath $SummaryPath -Raw
    if ([string]::IsNullOrWhiteSpace($raw)) {
        return $null
    }
    return (ConvertFrom-OpenClawJson -Json $raw -Depth 12)
}

function ConvertTo-OpenClawDateTimeOffset {
    param(
        [Parameter(Mandatory = $true)][string]$Value
    )

    return [DateTimeOffset]::Parse($Value, [System.Globalization.CultureInfo]::InvariantCulture)
}

function Get-OpenClawSuccessfulProducedAtLocal {
    param(
        $Summary
    )

    if ($null -eq $Summary) {
        return $null
    }
    if (-not [bool]$Summary.success) {
        return $null
    }
    $producedAt = [string]$Summary.produced_at_utc
    if ([string]::IsNullOrWhiteSpace($producedAt)) {
        return $null
    }
    return (ConvertTo-OpenClawDateTimeOffset -Value $producedAt).ToLocalTime().DateTime
}

function Get-OpenClawScheduledTaskCatchupDecision {
    param(
        [Parameter(Mandatory = $true)]$TaskEntry,
        [string]$SummaryPath,
        [datetime]$Now = (Get-Date)
    )

    $summary = $null
    if (-not [string]::IsNullOrWhiteSpace($SummaryPath)) {
        $summary = Read-OpenClawScheduledTaskSummary -SummaryPath $SummaryPath
    }
    $successfulProducedAtLocal = Get-OpenClawSuccessfulProducedAtLocal -Summary $summary

    if ([string]$TaskEntry.expected_interval -eq "hourly") {
        if ($null -eq $summary) {
            return [pscustomobject]@{ should_run = $true; reason = "summary_missing" }
        }
        if ($null -eq $successfulProducedAtLocal) {
            return [pscustomobject]@{ should_run = $true; reason = "last_run_not_successful" }
        }
        $ageHours = (([DateTimeOffset]$Now.ToUniversalTime()) - (ConvertTo-OpenClawDateTimeOffset -Value ([string]$summary.produced_at_utc)).ToUniversalTime()).TotalHours
        $freshnessBudget = [double]$TaskEntry.freshness_budget_hours
        if ($ageHours -gt $freshnessBudget) {
            return [pscustomobject]@{ should_run = $true; reason = "stale_summary" }
        }
        return [pscustomobject]@{ should_run = $false; reason = "summary_fresh" }
    }

    $scheduleType = [string]$TaskEntry.schedule.type
    if ($scheduleType -eq "daily") {
        $timeParts = ([string]$TaskEntry.schedule.time).Split(":")
        $scheduledAt = Get-Date -Year $Now.Year -Month $Now.Month -Day $Now.Day -Hour ([int]$timeParts[0]) -Minute ([int]$timeParts[1]) -Second 0
        if ($Now -lt $scheduledAt) {
            return [pscustomobject]@{ should_run = $false; reason = "scheduled_time_not_reached" }
        }
        if ($null -ne $successfulProducedAtLocal -and $successfulProducedAtLocal.Date -eq $Now.Date) {
            return [pscustomobject]@{ should_run = $false; reason = "already_succeeded_today" }
        }
        return [pscustomobject]@{ should_run = $true; reason = "scheduled_window_missed" }
    }

    if ($scheduleType -eq "weekly") {
        $timeParts = ([string]$TaskEntry.schedule.time).Split(":")
        $weekStart = $Now.Date.AddDays(-((([int]$Now.DayOfWeek + 6) % 7)))
        $dueTimes = @()
        foreach ($dayName in @($TaskEntry.schedule.days_of_week)) {
            $offset = switch ([string]$dayName) {
                "Monday" { 0 }
                "Tuesday" { 1 }
                "Wednesday" { 2 }
                "Thursday" { 3 }
                "Friday" { 4 }
                "Saturday" { 5 }
                "Sunday" { 6 }
                default { $null }
            }
            if ($null -ne $offset) {
                $dueTimes += (Get-Date -Year $weekStart.Year -Month $weekStart.Month -Day $weekStart.Day -Hour ([int]$timeParts[0]) -Minute ([int]$timeParts[1]) -Second 0).AddDays([int]$offset)
            }
        }
        $latestDueThisWeek = $dueTimes | Where-Object { $_ -le $Now } | Sort-Object | Select-Object -Last 1
        if ($null -eq $latestDueThisWeek) {
            return [pscustomobject]@{ should_run = $false; reason = "scheduled_weekly_window_not_reached" }
        }
        if ($null -ne $successfulProducedAtLocal -and $successfulProducedAtLocal -ge $weekStart) {
            return [pscustomobject]@{ should_run = $false; reason = "already_succeeded_this_week" }
        }
        return [pscustomobject]@{ should_run = $true; reason = "scheduled_weekly_window_missed" }
    }

    return [pscustomobject]@{ should_run = $false; reason = "unsupported_catchup_schedule" }
}

function Test-OpenClawScheduledTaskUpstreamFreshness {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [Parameter(Mandatory = $true)]$TaskEntry,
        [datetime]$Now = (Get-Date)
    )

    $manifest = Get-OpenClawScheduledTaskManifest -RepoRoot $RepoRoot
    $tasksByKey = @{}
    foreach ($task in @($manifest.tasks)) {
        $tasksByKey[[string]$task.task_key] = $task
    }

    $dependencyStatus = @{}
    $blockers = New-Object System.Collections.Generic.List[string]
    $overallStatus = "ready"
    foreach ($dependencyKey in @($TaskEntry.upstream_dependencies)) {
        $key = [string]$dependencyKey
        if (-not $tasksByKey.ContainsKey($key)) {
            $dependencyStatus[$key] = "missing"
            $blockers.Add("upstream task missing from manifest: $key")
            $overallStatus = "missing"
            continue
        }
        $dependencyEntry = $tasksByKey[$key]
        $summaryPath = Resolve-OpenClawScheduledTaskSummaryPath -TaskEntry $dependencyEntry
        if ([string]::IsNullOrWhiteSpace($summaryPath) -or -not (Test-Path $summaryPath)) {
            $dependencyStatus[$key] = "missing"
            $blockers.Add("upstream summary missing: $key")
            $overallStatus = "missing"
            continue
        }
        $summary = Read-OpenClawScheduledTaskSummary -SummaryPath $summaryPath
        if ($null -eq $summary -or -not [bool]$summary.success) {
            $dependencyStatus[$key] = "stale"
            $blockers.Add("upstream summary not successful: $key")
            if ($overallStatus -ne "missing") {
                $overallStatus = "stale"
            }
            continue
        }
        $producedAt = ConvertTo-OpenClawDateTimeOffset -Value ([string]$summary.produced_at_utc)
        $ageHours = (([DateTimeOffset]$Now.ToUniversalTime()) - $producedAt.ToUniversalTime()).TotalHours
        if ($ageHours -gt [double]$dependencyEntry.freshness_budget_hours) {
            $dependencyStatus[$key] = "stale"
            $blockers.Add(("upstream summary stale: {0} age_hours={1:N3}" -f $key, $ageHours))
            if ($overallStatus -ne "missing") {
                $overallStatus = "stale"
            }
            continue
        }
        $dependencyStatus[$key] = "ready"
    }

    return [pscustomobject]@{
        status = $overallStatus
        blockers = @($blockers)
        dependency_status = $dependencyStatus
    }
}

function Resolve-OpenClawScheduledTaskCredential {
    param(
        [Parameter(Mandatory = $true)]$TaskEntry,
        [System.Management.Automation.PSCredential]$Credential,
        [switch]$AllowInteractiveFallback
    )

    $registration = Get-OpenClawScheduledTaskRegistration -TaskEntry $TaskEntry
    if ($registration.principal_mode -ne "password") {
        return $Credential
    }
    if ($AllowInteractiveFallback -and $null -eq $Credential) {
        return $null
    }
    if ($null -ne $Credential) {
        return $Credential
    }
    $defaultUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    return (Get-Credential -UserName $defaultUser -Message "Enter Windows credentials for OpenClaw scheduled task registration.")
}

function New-OpenClawScheduledTaskSettings {
    param(
        [Parameter(Mandatory = $true)]$TaskEntry
    )

    $resilience = Get-OpenClawScheduledTaskResilience -TaskEntry $TaskEntry
    $settingsArgs = @{
        AllowStartIfOnBatteries = $true
        DontStopIfGoingOnBatteries = $true
        MultipleInstances = "IgnoreNew"
        StartWhenAvailable = $true
    }
    if ($resilience.wake_to_run) {
        $settingsArgs["WakeToRun"] = $true
    }
    if ($resilience.restart_count -gt 0 -and $resilience.restart_interval_minutes -gt 0) {
        $settingsArgs["RestartCount"] = $resilience.restart_count
        $settingsArgs["RestartInterval"] = (New-TimeSpan -Minutes $resilience.restart_interval_minutes)
    }
    return (New-ScheduledTaskSettingsSet @settingsArgs)
}

function Get-OpenClawStartupCatchupTaskName {
    param(
        [Parameter(Mandatory = $true)]$TaskEntry
    )

    return ("{0} Startup Catch-up" -f ([string]$TaskEntry.task_name))
}

function Get-OpenClawScheduledTaskLauncherRoot {
    return (Join-Path $env:LOCALAPPDATA "EnhengClaw\\scheduled_task_launchers")
}

function New-OpenClawScheduledTaskLauncher {
    param(
        [Parameter(Mandatory = $true)][string]$TaskKey,
        [Parameter(Mandatory = $true)][string]$ScriptPath,
        [string[]]$Arguments = @(),
        [string]$Suffix = ""
    )

    $launcherRoot = Get-OpenClawScheduledTaskLauncherRoot
    New-Item -ItemType Directory -Path $launcherRoot -Force | Out-Null
    $safeTaskKey = ([regex]::Replace($TaskKey, '[^A-Za-z0-9._-]', '_'))
    $launcherPath = Join-Path $launcherRoot ("{0}{1}.ps1" -f $safeTaskKey, $Suffix)
    $escapedScriptPath = $ScriptPath.Replace("'", "''")
    $argumentText = (
        @($Arguments) |
            ForEach-Object { "'{0}'" -f ([string]$_).Replace("'", "''") }
    ) -join " "
    $content = if ([string]::IsNullOrWhiteSpace($argumentText)) {
        "& '$escapedScriptPath'"
    } else {
        "& '$escapedScriptPath' $argumentText"
    }
    Set-Content -LiteralPath $launcherPath -Value $content -Encoding UTF8
    return $launcherPath
}

function Get-OpenClawInteractiveScheduledTaskUser {
    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    if ($identity -match "\\") {
        return ($identity -split "\\")[-1]
    }
    return $identity
}

function Register-OpenClawScheduledTaskViaSchTasks {
    param(
        [Parameter(Mandatory = $true)][string]$TaskName,
        [Parameter(Mandatory = $true)][string]$LauncherPath,
        [Parameter(Mandatory = $true)]$TaskEntry,
        [switch]$StartupTrigger
    )

    $triggerArgs = @()
    if ($StartupTrigger) {
        $triggerArgs = @("/SC", "ONSTART")
    } else {
        $scheduleType = [string]$TaskEntry.schedule.type
        switch ($scheduleType) {
            "daily" {
                $triggerArgs = @("/SC", "DAILY", "/ST", [string]$TaskEntry.schedule.time)
            }
            "weekly" {
                $days = @($TaskEntry.schedule.days_of_week) | ForEach-Object {
                    switch ([string]$_) {
                        "Monday" { "MON" }
                        "Tuesday" { "TUE" }
                        "Wednesday" { "WED" }
                        "Thursday" { "THU" }
                        "Friday" { "FRI" }
                        "Saturday" { "SAT" }
                        "Sunday" { "SUN" }
                        default { $null }
                    }
                } | Where-Object { $_ } 
                if (-not $days) {
                    throw "schtasks fallback requires at least one weekly day."
                }
                $triggerArgs = @("/SC", "WEEKLY", "/D", ($days -join ","), "/ST", [string]$TaskEntry.schedule.time)
            }
            "once_repeating" {
                $triggerArgs = @(
                    "/SC", "MINUTE",
                    "/MO", ([int]$TaskEntry.schedule.repeat_minutes).ToString(),
                    "/ST", [string]$TaskEntry.schedule.start_time
                )
            }
            default {
                throw "schtasks fallback does not support schedule type: $scheduleType"
            }
        }
    }

    $commandText = ("powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"{0}`"" -f $LauncherPath)
    $userName = Get-OpenClawInteractiveScheduledTaskUser
    $arguments = @(
        "/Create",
        "/F",
        "/TN", $TaskName,
        "/TR", $commandText,
        "/IT",
        "/RU", $userName
    ) + $triggerArgs

    & schtasks.exe @arguments | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw ("schtasks registration failed for task '{0}' with exit code {1}" -f $TaskName, $LASTEXITCODE)
    }
}

function Get-OpenClawQuantRuntimeBootstrapPath {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot
    )

    return (Join-Path $RepoRoot "scripts\\quant_research\\bootstrap_quant_runtime.py")
}

function Get-OpenClawRepoVenvPythonExecutable {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot
    )

    $venvPython = Join-Path $RepoRoot ".venv\\Scripts\\python.exe"
    if (-not (Test-Path $venvPython)) {
        $bootstrapPath = Get-OpenClawQuantRuntimeBootstrapPath -RepoRoot $RepoRoot
        throw ("python_runtime_missing: repo .venv is unavailable at {0}; run {1}" -f $venvPython, $bootstrapPath)
    }
    return $venvPython
}

function Assert-OpenClawScientificPythonRuntime {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot
    )

    $bootstrapPath = Get-OpenClawQuantRuntimeBootstrapPath -RepoRoot $RepoRoot
    try {
        $venvPython = Get-OpenClawRepoVenvPythonExecutable -RepoRoot $RepoRoot
    } catch {
        throw ("scientific_python_runtime_missing: repo .venv is unavailable; run {0}" -f $bootstrapPath)
    }
    try {
        $null = & $venvPython -c "import numpy, pandas, sklearn" 2>$null
        if ($LASTEXITCODE -eq 0) {
            return $venvPython
        }
    } catch {
    }
    throw ("scientific_python_runtime_missing: repo .venv is missing numpy/pandas/scikit-learn; run {0}" -f $bootstrapPath)
}

function Invoke-OpenClawScheduledTaskRegistration {
    param(
        [Parameter(Mandatory = $true)][string]$TaskName,
        [Parameter(Mandatory = $true)]$Action,
        [Parameter(Mandatory = $true)]$Triggers,
        [Parameter(Mandatory = $true)]$Settings,
        [Parameter(Mandatory = $true)]$TaskEntry,
        [System.Management.Automation.PSCredential]$Credential,
        [switch]$AllowInteractiveFallback
    )

    $registration = Get-OpenClawScheduledTaskRegistration -TaskEntry $TaskEntry
    if ($registration.principal_mode -eq "password" -and $null -ne $Credential) {
        $password = $Credential.GetNetworkCredential().Password
        Register-ScheduledTask `
            -TaskName $TaskName `
            -Action $Action `
            -Trigger $Triggers `
            -Settings $Settings `
            -User $Credential.UserName `
            -Password $password `
            -RunLevel $registration.run_level `
            -Force | Out-Null
    } else {
        if ($registration.principal_mode -eq "password" -and $null -eq $Credential -and -not $AllowInteractiveFallback) {
            throw "credential is required for password-based scheduled task registration."
        }
        $principal = New-ScheduledTaskPrincipal `
            -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
            -LogonType Interactive `
            -RunLevel $registration.run_level
        Register-ScheduledTask `
            -TaskName $TaskName `
            -Action $Action `
            -Trigger $Triggers `
            -Settings $Settings `
            -Principal $principal `
            -Force | Out-Null
    }

    Enable-ScheduledTask -TaskName $TaskName | Out-Null
}

function Register-OpenClawScheduledTaskEntry {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [Parameter(Mandatory = $true)]$TaskEntry,
        [System.Management.Automation.PSCredential]$Credential,
        [switch]$RegisterStartupCatchup,
        [switch]$AllowInteractiveFallback
    )

    $runnerPath = Join-Path $RepoRoot ([string]$TaskEntry.runner_script)
    if (-not (Test-Path $runnerPath)) {
        throw "runner not found: $runnerPath"
    }

    $resolvedCredential = Resolve-OpenClawScheduledTaskCredential `
        -TaskEntry $TaskEntry `
        -Credential $Credential `
        -AllowInteractiveFallback:$AllowInteractiveFallback
    $usedSchTasksFallback = $false
    $mainAction = New-ScheduledTaskAction `
        -Execute "powershell.exe" `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$runnerPath`""
    $mainTriggers = New-OpenClawScheduledTaskTriggers -TaskEntry $TaskEntry
    $settings = New-OpenClawScheduledTaskSettings -TaskEntry $TaskEntry
    try {
        Invoke-OpenClawScheduledTaskRegistration `
            -TaskName ([string]$TaskEntry.task_name) `
            -Action $mainAction `
            -Triggers $mainTriggers `
            -Settings $settings `
            -TaskEntry $TaskEntry `
            -Credential $resolvedCredential `
            -AllowInteractiveFallback:$AllowInteractiveFallback
    } catch {
        $canFallbackToSchTasks = (
            $AllowInteractiveFallback -and
            $null -eq $resolvedCredential -and
            $_.Exception.Message -match "Access is denied"
        )
        if (-not $canFallbackToSchTasks) {
            throw
        }
        $launcherPath = New-OpenClawScheduledTaskLauncher `
            -TaskKey ([string]$TaskEntry.task_key) `
            -ScriptPath $runnerPath
        Register-OpenClawScheduledTaskViaSchTasks `
            -TaskName ([string]$TaskEntry.task_name) `
            -LauncherPath $launcherPath `
            -TaskEntry $TaskEntry
        $usedSchTasksFallback = $true
    }

    $resilience = Get-OpenClawScheduledTaskResilience -TaskEntry $TaskEntry
    $startupTaskName = Get-OpenClawStartupCatchupTaskName -TaskEntry $TaskEntry
    if ($RegisterStartupCatchup -and $resilience.startup_catchup_enabled) {
        $catchupWrapperPath = Join-Path $RepoRoot "scripts\\common\\run_openclaw_startup_catchup_wrapper.ps1"
        if (-not (Test-Path $catchupWrapperPath)) {
            throw "startup catch-up wrapper not found: $catchupWrapperPath"
        }
        if ($usedSchTasksFallback) {
            $startupLauncherPath = New-OpenClawScheduledTaskLauncher `
                -TaskKey ([string]$TaskEntry.task_key) `
                -ScriptPath $catchupWrapperPath `
                -Arguments @("-RunnerPath", $runnerPath, "-DelayMinutes", [string]$resilience.startup_delay_minutes) `
                -Suffix ".startup"
            Register-OpenClawScheduledTaskViaSchTasks `
                -TaskName $startupTaskName `
                -LauncherPath $startupLauncherPath `
                -TaskEntry $TaskEntry `
                -StartupTrigger
        } else {
            $startupAction = New-ScheduledTaskAction `
                -Execute "powershell.exe" `
                -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$catchupWrapperPath`" -RunnerPath `"$runnerPath`" -DelayMinutes $($resilience.startup_delay_minutes)"
            $startupTrigger = @(New-ScheduledTaskTrigger -AtStartup)
            Invoke-OpenClawScheduledTaskRegistration `
                -TaskName $startupTaskName `
                -Action $startupAction `
                -Triggers $startupTrigger `
                -Settings $settings `
                -TaskEntry $TaskEntry `
                -Credential $resolvedCredential `
                -AllowInteractiveFallback:$AllowInteractiveFallback
        }
    } elseif (Get-ScheduledTask -TaskName $startupTaskName -ErrorAction SilentlyContinue) {
        Disable-ScheduledTask -TaskName $startupTaskName -ErrorAction SilentlyContinue | Out-Null
        Unregister-ScheduledTask -TaskName $startupTaskName -Confirm:$false -ErrorAction SilentlyContinue
    }
}

function Get-OpenClawSourceCommitSha {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot
    )

    if (-not [string]::IsNullOrWhiteSpace($env:GITHUB_SHA)) {
        return $env:GITHUB_SHA
    }
    if (-not [string]::IsNullOrWhiteSpace($env:SOURCE_COMMIT_SHA)) {
        return $env:SOURCE_COMMIT_SHA
    }
    try {
        $sha = (& git -C $RepoRoot rev-parse HEAD 2>$null)
        if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($sha)) {
            return ([string]$sha).Trim()
        }
    } catch {
    }
    return $null
}

function Read-OpenClawChildSummary {
    param(
        [Parameter(Mandatory = $true)][string]$StdoutPath,
        [string]$ChildSummaryPath
    )

    if (-not [string]::IsNullOrWhiteSpace($ChildSummaryPath) -and (Test-Path $ChildSummaryPath)) {
        try {
            return (ConvertFrom-OpenClawJson -Json (Get-Content -LiteralPath $ChildSummaryPath -Raw) -Depth 12)
        } catch {
        }
    }
    if (-not (Test-Path $StdoutPath)) {
        return $null
    }
    $raw = Get-Content -LiteralPath $StdoutPath -Raw
    if ([string]::IsNullOrWhiteSpace($raw)) {
        return $null
    }
    try {
        return ConvertFrom-OpenClawJson -Json $raw -Depth 12
    } catch {
    }
    foreach ($line in ($raw -split "`r?`n")) {
        if ($line -match "=(.+\.json)$") {
            $candidatePath = $Matches[1].Trim()
            if (Test-Path $candidatePath) {
                try {
                    return (ConvertFrom-OpenClawJson -Json (Get-Content -LiteralPath $candidatePath -Raw) -Depth 12)
                } catch {
                }
            }
        }
    }
    return $null
}

function Read-OpenClawFailureSummary {
    param(
        [string]$FailureSummaryPath
    )

    if ([string]::IsNullOrWhiteSpace($FailureSummaryPath) -or -not (Test-Path $FailureSummaryPath)) {
        return $null
    }
    try {
        return (ConvertFrom-OpenClawJson -Json (Get-Content -LiteralPath $FailureSummaryPath -Raw) -Depth 12)
    } catch {
    }
    return $null
}

function Write-OpenClawScheduledTaskSummary {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [Parameter(Mandatory = $true)]$TaskEntry,
        [Parameter(Mandatory = $true)][string]$RunnerRoot,
        [Parameter(Mandatory = $true)][int]$ExitCode,
        [Parameter(Mandatory = $true)][string]$LogPath,
        [Parameter(Mandatory = $true)][string]$StdoutPath,
        [string]$ChildSummaryPath,
        [string]$FailureSummaryPath
    )

    $childSummary = Read-OpenClawChildSummary -StdoutPath $StdoutPath -ChildSummaryPath $ChildSummaryPath
    $failureSummary = Read-OpenClawFailureSummary -FailureSummaryPath $FailureSummaryPath
    $upstreamVersions = [ordered]@{
        upstream_dependencies = @($TaskEntry.upstream_dependencies)
    }
    if ($childSummary -and $childSummary.upstream_versions) {
        if ($childSummary.upstream_versions -is [System.Collections.IDictionary]) {
            foreach ($key in $childSummary.upstream_versions.Keys) {
                $upstreamVersions[$key] = $childSummary.upstream_versions[$key]
            }
        } else {
            foreach ($property in $childSummary.upstream_versions.PSObject.Properties) {
                if ($property.MemberType -like "*Property") {
                    $upstreamVersions[$property.Name] = $property.Value
                }
            }
        }
    }
    $summary = [ordered]@{
        task_key = [string]$TaskEntry.task_key
        task_name = [string]$TaskEntry.task_name
        exit_status = $ExitCode
        success = ($ExitCode -eq 0)
        produced_at_utc = (Get-Date).ToUniversalTime().ToString("o")
        source_commit_sha = Get-OpenClawSourceCommitSha -RepoRoot $RepoRoot
        artifact_family = if ($childSummary -and $childSummary.artifact_family) { [string]$childSummary.artifact_family } else { [string]$TaskEntry.produces_artifact_family }
        contract_version = if ($childSummary -and $childSummary.contract_version) { [string]$childSummary.contract_version } else { "scheduled_runner_summary.v1" }
        runner_script = [string]$TaskEntry.runner_script
        log_path = $LogPath
        child_summary_path = if ([string]::IsNullOrWhiteSpace($ChildSummaryPath)) { $null } else { $ChildSummaryPath }
        failure_summary_path = if ([string]::IsNullOrWhiteSpace($FailureSummaryPath)) { $null } else { $FailureSummaryPath }
        input_watermarks = if ($childSummary -and $childSummary.input_watermarks) { $childSummary.input_watermarks } else { @{} }
        upstream_versions = $upstreamVersions
        child_summary = $childSummary
        failure_summary = $failureSummary
    }
    $summaryPath = Join-Path $RunnerRoot ("{0}.last_run_summary.json" -f $TaskEntry.task_key)
    $json = $summary | ConvertTo-Json -Depth 12
    Set-Content -LiteralPath $summaryPath -Value $json -Encoding UTF8
    return $summaryPath
}

function Write-OpenClawScheduledTaskImmediateSummary {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [Parameter(Mandatory = $true)]$TaskEntry,
        [Parameter(Mandatory = $true)][string]$RunnerRoot,
        [Parameter(Mandatory = $true)][int]$ExitCode,
        [Parameter(Mandatory = $true)][string]$LogPath,
        [string]$StdoutPath
    )

    $effectiveStdoutPath = $StdoutPath
    if ([string]::IsNullOrWhiteSpace($effectiveStdoutPath)) {
        $effectiveStdoutPath = Join-Path $RunnerRoot ("{0}.stdout.immediate.tmp" -f [string]$TaskEntry.task_key)
    }
    $stdoutParent = Split-Path -Parent $effectiveStdoutPath
    if (-not [string]::IsNullOrWhiteSpace($stdoutParent)) {
        New-Item -ItemType Directory -Path $stdoutParent -Force | Out-Null
    }
    if (-not (Test-Path $effectiveStdoutPath)) {
        Set-Content -LiteralPath $effectiveStdoutPath -Value "" -Encoding UTF8
    }
    return (Write-OpenClawScheduledTaskSummary `
        -RepoRoot $RepoRoot `
        -TaskEntry $TaskEntry `
        -RunnerRoot $RunnerRoot `
        -ExitCode $ExitCode `
        -LogPath $LogPath `
        -StdoutPath $effectiveStdoutPath)
}
