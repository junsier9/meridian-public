[CmdletBinding()]
param(
    [string]$OutputRoot,
    [string]$TaskNamePattern = "EnhengClaw|OpenClaw|Quant|hv_balanced|mainnet|binance|research",
    [string]$ClonePrefix = "Meridian Alpha "
)

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $scriptRoot "..\.."))

if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
    $OutputRoot = Join-Path $repoRoot ("artifacts\external_state_migration\windows_scheduled_tasks\{0}" -f $stamp)
}

function ConvertTo-MeridianSafeFileName {
    param([Parameter(Mandatory = $true)][string]$Value)

    $safe = [regex]::Replace($Value, "[^A-Za-z0-9._-]+", "_").Trim("_")
    if ([string]::IsNullOrWhiteSpace($safe)) {
        return "task"
    }
    return $safe
}

function Get-MeridianCloneTaskName {
    param([Parameter(Mandatory = $true)][string]$TaskName)

    if ($TaskName.StartsWith($ClonePrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $TaskName
    }
    return ("{0}{1}" -f $ClonePrefix, $TaskName)
}

function Ensure-MeridianXmlChild {
    param(
        [Parameter(Mandatory = $true)][System.Xml.XmlDocument]$Document,
        [Parameter(Mandatory = $true)][System.Xml.XmlElement]$Parent,
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$NamespaceUri
    )

    $child = $Parent.GetElementsByTagName($Name, $NamespaceUri) | Select-Object -First 1
    if ($null -eq $child) {
        $child = $Document.CreateElement($Name, $NamespaceUri)
        [void]$Parent.AppendChild($child)
    }
    return $child
}

function ConvertTo-MeridianDisabledTaskXml {
    param(
        [Parameter(Mandatory = $true)][string]$LegacyXml,
        [Parameter(Mandatory = $true)][string]$CloneTaskName,
        [Parameter(Mandatory = $true)][string]$SourceTaskName
    )

    [xml]$document = $LegacyXml
    $namespaceUri = $document.DocumentElement.NamespaceURI
    $namespace = New-Object System.Xml.XmlNamespaceManager($document.NameTable)
    $namespace.AddNamespace("t", $namespaceUri)

    $registrationInfo = $document.SelectSingleNode("/t:Task/t:RegistrationInfo", $namespace)
    if ($null -eq $registrationInfo) {
        $registrationInfo = $document.CreateElement("RegistrationInfo", $namespaceUri)
        [void]$document.DocumentElement.PrependChild($registrationInfo)
    }

    $uri = $registrationInfo.SelectSingleNode("t:URI", $namespace)
    if ($null -eq $uri) {
        $uri = $document.CreateElement("URI", $namespaceUri)
        [void]$registrationInfo.AppendChild($uri)
    }
    $uri.InnerText = ("\{0}" -f $CloneTaskName)

    $description = $registrationInfo.SelectSingleNode("t:Description", $namespace)
    if ($null -eq $description) {
        $description = $document.CreateElement("Description", $namespaceUri)
        [void]$registrationInfo.AppendChild($description)
    }
    $description.InnerText = (
        "Disabled Meridian Alpha parallel clone generated from '{0}'. " +
        "Do not enable until the external-state migration checklist passes."
    ) -f $SourceTaskName

    $settings = $document.SelectSingleNode("/t:Task/t:Settings", $namespace)
    if ($null -eq $settings) {
        $settings = $document.CreateElement("Settings", $namespaceUri)
        [void]$document.DocumentElement.AppendChild($settings)
    }

    $enabled = $settings.SelectSingleNode("t:Enabled", $namespace)
    if ($null -eq $enabled) {
        $enabled = $document.CreateElement("Enabled", $namespaceUri)
        [void]$settings.AppendChild($enabled)
    }
    $enabled.InnerText = "false"

    $writerSettings = New-Object System.Xml.XmlWriterSettings
    $writerSettings.Indent = $true
    $writerSettings.Encoding = New-Object System.Text.UTF8Encoding($false)
    $stringBuilder = New-Object System.Text.StringBuilder
    $writer = [System.Xml.XmlWriter]::Create($stringBuilder, $writerSettings)
    try {
        $document.Save($writer)
    } finally {
        $writer.Close()
    }
    return $stringBuilder.ToString()
}

function Write-MeridianText {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Content
    )

    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Content, $encoding)
}

function ConvertTo-MeridianRelativePath {
    param(
        [Parameter(Mandatory = $true)][string]$BasePath,
        [Parameter(Mandatory = $true)][string]$Path
    )

    $baseFull = [System.IO.Path]::GetFullPath($BasePath).TrimEnd("\") + "\"
    $pathFull = [System.IO.Path]::GetFullPath($Path)
    $baseUri = New-Object System.Uri($baseFull)
    $pathUri = New-Object System.Uri($pathFull)
    return ([System.Uri]::UnescapeDataString($baseUri.MakeRelativeUri($pathUri).ToString()).Replace("/", "\"))
}

$legacyXmlRoot = Join-Path $OutputRoot "legacy_xml"
$cloneXmlRoot = Join-Path $OutputRoot "meridian_disabled_xml"
New-Item -ItemType Directory -Path $legacyXmlRoot -Force | Out-Null
New-Item -ItemType Directory -Path $cloneXmlRoot -Force | Out-Null

$tasks = Get-ScheduledTask | Where-Object {
    ($_.TaskName -match $TaskNamePattern -or $_.TaskPath -match $TaskNamePattern) -and
    (-not $_.TaskName.StartsWith($ClonePrefix, [System.StringComparison]::OrdinalIgnoreCase))
} | Sort-Object TaskPath, TaskName

if (@($tasks).Count -eq 0) {
    throw "no matching scheduled tasks found for pattern: $TaskNamePattern"
}

$inventory = @()

foreach ($task in @($tasks)) {
    $safeName = ConvertTo-MeridianSafeFileName -Value (($task.TaskPath.Trim("\") + "_" + $task.TaskName).Trim("_"))
    $legacyXmlPath = Join-Path $legacyXmlRoot ("{0}.xml" -f $safeName)
    $cloneTaskName = Get-MeridianCloneTaskName -TaskName ([string]$task.TaskName)
    $cloneSafeName = ConvertTo-MeridianSafeFileName -Value (($task.TaskPath.Trim("\") + "_" + $cloneTaskName).Trim("_"))
    $cloneXmlPath = Join-Path $cloneXmlRoot ("{0}.xml" -f $cloneSafeName)

    $legacyXml = Export-ScheduledTask -TaskName $task.TaskName -TaskPath $task.TaskPath
    Write-MeridianText -Path $legacyXmlPath -Content $legacyXml

    $cloneXml = ConvertTo-MeridianDisabledTaskXml `
        -LegacyXml $legacyXml `
        -CloneTaskName $cloneTaskName `
        -SourceTaskName ([string]$task.TaskName)
    Write-MeridianText -Path $cloneXmlPath -Content $cloneXml

    $taskInfo = Get-ScheduledTaskInfo -TaskName $task.TaskName -TaskPath $task.TaskPath -ErrorAction SilentlyContinue
    $actions = @($task.Actions | ForEach-Object { (($_.Execute, $_.Arguments) -join " ").Trim() })
    $triggers = @($task.Triggers | ForEach-Object { $_.ToString() })

    $inventory += [pscustomobject]@{
        task_path = [string]$task.TaskPath
        legacy_task_name = [string]$task.TaskName
        clone_task_name = $cloneTaskName
        legacy_state = [string]$task.State
        legacy_xml = ConvertTo-MeridianRelativePath -BasePath $OutputRoot -Path $legacyXmlPath
        clone_disabled_xml = ConvertTo-MeridianRelativePath -BasePath $OutputRoot -Path $cloneXmlPath
        last_run_time = if ($null -ne $taskInfo -and $taskInfo.LastRunTime) { $taskInfo.LastRunTime.ToString("o") } else { $null }
        last_task_result = if ($null -ne $taskInfo) { $taskInfo.LastTaskResult } else { $null }
        next_run_time = if ($null -ne $taskInfo -and $taskInfo.NextRunTime) { $taskInfo.NextRunTime.ToString("o") } else { $null }
        actions = @($actions)
        triggers = @($triggers)
    }
}

$manifest = [pscustomobject]@{
    package_kind = "meridian_alpha_windows_scheduled_task_parallel_migration"
    generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    repo_root = $repoRoot
    output_root = [System.IO.Path]::GetFullPath($OutputRoot)
    task_name_pattern = $TaskNamePattern
    clone_prefix = $ClonePrefix
    mutates_windows_task_scheduler = $false
    task_count = @($inventory).Count
    tasks = @($inventory)
}

$manifestPath = Join-Path $OutputRoot "manifest.json"
Write-MeridianText -Path $manifestPath -Content ($manifest | ConvertTo-Json -Depth 10)

$registerScript = @'
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [switch]$ForceExistingMeridianClones
)

$ErrorActionPreference = "Stop"

$packageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$manifest = Get-Content -LiteralPath (Join-Path $packageRoot "manifest.json") -Raw | ConvertFrom-Json

foreach ($entry in @($manifest.tasks)) {
    $taskPath = [string]$entry.task_path
    $cloneTaskName = [string]$entry.clone_task_name
    $cloneXmlPath = Join-Path $packageRoot ([string]$entry.clone_disabled_xml)
    $existing = Get-ScheduledTask -TaskName $cloneTaskName -TaskPath $taskPath -ErrorAction SilentlyContinue

    if ($null -ne $existing -and -not $ForceExistingMeridianClones) {
        Write-Host "SKIP existing Meridian clone: $taskPath$cloneTaskName"
        continue
    }

    if ($null -ne $existing -and $ForceExistingMeridianClones) {
        if ($PSCmdlet.ShouldProcess("$taskPath$cloneTaskName", "Unregister existing Meridian clone")) {
            Unregister-ScheduledTask -TaskName $cloneTaskName -TaskPath $taskPath -Confirm:$false
        }
    }

    $xml = Get-Content -LiteralPath $cloneXmlPath -Raw
    if ($PSCmdlet.ShouldProcess("$taskPath$cloneTaskName", "Register disabled Meridian clone")) {
        Register-ScheduledTask -TaskName $cloneTaskName -TaskPath $taskPath -Xml $xml | Out-Null
        Disable-ScheduledTask -TaskName $cloneTaskName -TaskPath $taskPath | Out-Null
        Write-Host "REGISTERED DISABLED: $taskPath$cloneTaskName"
    }
}
'@
Write-MeridianText -Path (Join-Path $OutputRoot "register_disabled_meridian_clones.ps1") -Content $registerScript

$rollbackScript = @'
[CmdletBinding(SupportsShouldProcess = $true)]
param()

$ErrorActionPreference = "Stop"

$packageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$manifest = Get-Content -LiteralPath (Join-Path $packageRoot "manifest.json") -Raw | ConvertFrom-Json

foreach ($entry in @($manifest.tasks)) {
    $taskPath = [string]$entry.task_path
    $cloneTaskName = [string]$entry.clone_task_name
    $existing = Get-ScheduledTask -TaskName $cloneTaskName -TaskPath $taskPath -ErrorAction SilentlyContinue
    if ($null -eq $existing) {
        Write-Host "MISSING Meridian clone: $taskPath$cloneTaskName"
        continue
    }
    if ($PSCmdlet.ShouldProcess("$taskPath$cloneTaskName", "Disable Meridian clone")) {
        Disable-ScheduledTask -TaskName $cloneTaskName -TaskPath $taskPath | Out-Null
        Write-Host "DISABLED: $taskPath$cloneTaskName"
    }
}
'@
Write-MeridianText -Path (Join-Path $OutputRoot "rollback_disable_meridian_clones.ps1") -Content $rollbackScript

$readmeLines = @(
    "# Meridian Alpha Windows Scheduled Task Migration Package",
    "",
    "Generated at UTC: $($manifest.generated_at_utc)",
    "",
    "This package is intentionally parallel and reversible.",
    "",
    "- legacy_xml/ contains read-only XML exports of the current legacy tasks.",
    "- meridian_disabled_xml/ contains Meridian-named clone XML with <Enabled>false</Enabled>.",
    "- register_disabled_meridian_clones.ps1 registers only Meridian clone names, then disables them.",
    "- rollback_disable_meridian_clones.ps1 disables Meridian clone names only.",
    "",
    "The package builder did not register, enable, disable, replace, or delete any Windows scheduled task.",
    "",
    "Recommended first proof target: Meridian Alpha OpenClaw Quant Universe Input Producer.",
    "",
    "Task count: $(@($inventory).Count)",
    "",
    "## Tasks",
    ""
)

foreach ($entry in @($inventory)) {
    $readmeLines += ("- {0} -> {1}; legacy_state={2}; last_result={3}" -f `
        $entry.legacy_task_name, `
        $entry.clone_task_name, `
        $entry.legacy_state, `
        $entry.last_task_result)
}

Write-MeridianText -Path (Join-Path $OutputRoot "README.md") -Content ($readmeLines -join [Environment]::NewLine)

$manifest
