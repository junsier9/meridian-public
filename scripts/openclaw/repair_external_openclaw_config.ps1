[CmdletBinding()]
param(
    [string]$OpenClawRoot = "\\wsl.localhost\Ubuntu-24.04\root\.openclaw"
)

$ErrorActionPreference = "Stop"

function Read-JsonObject {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [int]$Depth = 20
    )

    $raw = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
    $command = Get-Command ConvertFrom-Json -ErrorAction Stop
    if ($command.Parameters.ContainsKey("Depth")) {
        return ($raw | ConvertFrom-Json -Depth $Depth)
    }
    return ($raw | ConvertFrom-Json)
}

function ConvertTo-HashtableDeep {
    param(
        [Parameter(Mandatory = $true)]$InputObject
    )

    if ($null -eq $InputObject) {
        return $null
    }
    if ($InputObject -is [System.Collections.IDictionary]) {
        $hash = [ordered]@{}
        foreach ($key in $InputObject.Keys) {
            $hash[$key] = ConvertTo-HashtableDeep -InputObject $InputObject[$key]
        }
        return $hash
    }
    if ($InputObject -is [System.Collections.IEnumerable] -and -not ($InputObject -is [string])) {
        $items = @()
        foreach ($item in $InputObject) {
            $items += ,(ConvertTo-HashtableDeep -InputObject $item)
        }
        return $items
    }
    $psObjectProperties = $InputObject.PSObject.Properties
    if ($psObjectProperties.Count -gt 0) {
        $hash = [ordered]@{}
        foreach ($property in $psObjectProperties) {
            $hash[$property.Name] = ConvertTo-HashtableDeep -InputObject $property.Value
        }
        return $hash
    }
    return $InputObject
}

function Merge-OrderedHashtable {
    param(
        [Parameter(Mandatory = $true)][System.Collections.IDictionary]$Base,
        [Parameter(Mandatory = $true)][System.Collections.IDictionary]$Overlay
    )

    foreach ($key in $Overlay.Keys) {
        $overlayValue = $Overlay[$key]
        if (
            $null -ne $Base[$key] -and
            $Base[$key] -is [System.Collections.IDictionary] -and
            $overlayValue -is [System.Collections.IDictionary]
        ) {
            $Base[$key] = Merge-OrderedHashtable `
                -Base (ConvertTo-HashtableDeep -InputObject $Base[$key]) `
                -Overlay (ConvertTo-HashtableDeep -InputObject $overlayValue)
            continue
        }
        $Base[$key] = ConvertTo-HashtableDeep -InputObject $overlayValue
    }
    return $Base
}

function Get-FileSha256 {
    param(
        [Parameter(Mandatory = $true)][string]$Path
    )

    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

$configPath = Join-Path $OpenClawRoot "openclaw.json"
$backupPath = Join-Path $OpenClawRoot "openclaw.json.bak"
$auditPath = Join-Path $OpenClawRoot "logs\config-audit.jsonl"

if (-not (Test-Path $configPath)) {
    throw "openclaw.json not found: $configPath"
}
if (-not (Test-Path $backupPath)) {
    throw "openclaw.json.bak not found: $backupPath"
}

$current = ConvertTo-HashtableDeep -InputObject (Read-JsonObject -Path $configPath)
$baseline = ConvertTo-HashtableDeep -InputObject (Read-JsonObject -Path $backupPath)
$timestamp = Get-Date -Format "yyyyMMddTHHmmssZ"
$preRepairBackupPath = Join-Path $OpenClawRoot ("openclaw.json.pre-repair-{0}.bak" -f $timestamp)
Copy-Item -LiteralPath $configPath -Destination $preRepairBackupPath -Force

$repaired = ConvertTo-HashtableDeep -InputObject $baseline
if ($null -ne $current["plugins"]) {
    $currentPlugins = ConvertTo-HashtableDeep -InputObject $current["plugins"]
    if ($null -ne $repaired["plugins"] -and $repaired["plugins"] -is [System.Collections.IDictionary]) {
        $repaired["plugins"] = Merge-OrderedHashtable `
            -Base (ConvertTo-HashtableDeep -InputObject $repaired["plugins"]) `
            -Overlay (ConvertTo-HashtableDeep -InputObject $currentPlugins)
    } else {
        $repaired["plugins"] = $currentPlugins
    }
}
if ($null -eq $repaired["meta"] -or -not ($repaired["meta"] -is [System.Collections.IDictionary])) {
    $repaired["meta"] = [ordered]@{}
}
$repaired["meta"]["lastTouchedAt"] = (Get-Date).ToUniversalTime().ToString("o")
$repaired["meta"]["lastTouchedVersion"] = ("{0}.{1}.{2}" -f (Get-Date).Year, (Get-Date).Month, (Get-Date).Day)

$beforeHash = Get-FileSha256 -Path $configPath
$beforeBytes = (Get-Item -LiteralPath $configPath).Length
$json = $repaired | ConvertTo-Json -Depth 20
Set-Content -LiteralPath $configPath -Value $json -Encoding UTF8
$afterHash = Get-FileSha256 -Path $configPath
$afterBytes = (Get-Item -LiteralPath $configPath).Length

$auditEntry = [ordered]@{
    ts = (Get-Date).ToUniversalTime().ToString("o")
    source = "codex-repair"
    event = "config.repair"
    configPath = "/root/.openclaw/openclaw.json"
    baselinePath = "/root/.openclaw/openclaw.json.bak"
    preRepairBackupPath = ("/root/.openclaw/{0}" -f (Split-Path -Leaf $preRepairBackupPath))
    previousHash = $beforeHash
    nextHash = $afterHash
    previousBytes = $beforeBytes
    nextBytes = $afterBytes
    preservedPaths = @("plugins")
    note = "Rebuilt openclaw.json from the latest backup baseline and preserved current plugin entries after the suspicious gateway size-drop event."
}
Add-Content -LiteralPath $auditPath -Value ($auditEntry | ConvertTo-Json -Compress) -Encoding UTF8

[pscustomobject]@{
    status = "success"
    openclaw_root = $OpenClawRoot
    config_path = $configPath
    baseline_path = $backupPath
    pre_repair_backup_path = $preRepairBackupPath
    preserved_paths = @("plugins")
    previous_hash = $beforeHash
    next_hash = $afterHash
} | ConvertTo-Json -Depth 6
