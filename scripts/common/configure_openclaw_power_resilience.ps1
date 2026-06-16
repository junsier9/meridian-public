[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

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

& powercfg /SETACVALUEINDEX SCHEME_CURRENT SUB_SLEEP RTCWAKE 1
if ($LASTEXITCODE -ne 0) {
    throw "failed to set AC RTCWAKE=enabled"
}
& powercfg /SETDCVALUEINDEX SCHEME_CURRENT SUB_SLEEP RTCWAKE 0
if ($LASTEXITCODE -ne 0) {
    throw "failed to set DC RTCWAKE=disabled"
}
& powercfg /SETACTIVE SCHEME_CURRENT | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "failed to activate current power scheme after RTCWAKE update"
}

$indices = Get-CurrentWakeTimerIndices
[pscustomobject]@{
    rtcwake_ac = $indices.ac
    rtcwake_dc = $indices.dc
    policy = "AC enabled / DC disabled"
} | ConvertTo-Json -Depth 3
