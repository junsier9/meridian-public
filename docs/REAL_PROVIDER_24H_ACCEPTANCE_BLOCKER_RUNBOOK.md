# Real-Provider 24h Acceptance Blocker Runbook

`READY_FOR_AGENT_LAYER` remains `false`.

## 1. 鏈€灏忛樆鏂」 -> 鏍瑰洜 -> 澶勭悊鏂瑰紡

- `[Host 閰嶇疆姝ラ]` `ExecutionPermitPath` 缂哄け -> real-provider 24h acceptance 蹇呴』鏄惧紡浼犲叆鐪熷疄 permit锛涙湭浼犲叆鏃朵細钀藉埌鍗犱綅 permit 骞惰 preflight fail closed -> 鍦ㄧ洰鏍?host 涓婂噯澶囩湡瀹?permit 鏂囦欢 `<ExecutionPermitPath>`锛屽苟鍦ㄧ 6 椤瑰拰绗?7 椤瑰懡浠や腑鏄惧紡浼犲叆銆?
- `[Host 閰嶇疆姝ラ]` trust root 鏂囦欢缂哄け -> 榛樿璺緞 `C:\ProgramData\EnhengClaw\trust\allowed_signers` 涓嶅瓨鍦?-> 鍦ㄩ粯璁よ矾寰勯儴缃茬湡瀹?`allowed_signers`锛屾垨璁剧疆 `ENHENGCLAW_TRUST_ROOT_DIR=<TrustRootDir>` 鎸囧悜浠撳銆侀潪涓存椂鐩綍銆佸彧璇?trust root銆?
- `[鏈€灏忎唬鐮佷慨鏀筣` real-24h permit margin 鏈交搴曠粺涓€ -> 鐪熷疄 24h 楠屾敹璺緞蹇呴』缁熶竴浣跨敤鍚屼竴涓?permit 鍚姩鍓╀綑鏈夋晥鏈熼棬妲?-> 宸茬粺涓€涓?`86460.0`锛屽苟鍚屾鍒?real-24h acceptance銆乸reflight-only銆丳ython wrapper銆丳owerShell 鍏ュ彛銆乺un_config銆乸reflight evidence銆?
- `[鏈€灏忎唬鐮佷慨鏀?+ Host 閰嶇疆姝ラ]` Binance websocket preflight 鍦?`data_wait` 瓒呮椂 -> 鐪熷疄澶辫触鐐瑰凡瀹氫綅涓?`failure_category=timeout`銆乣transport_stage=data_wait`銆乣transport=wss`銆乣endpoint=wss://stream.binance.com:9443/ws` -> 浠ｇ爜渚т繚鐣欑粨鏋勫寲璇婃柇杈撳嚭锛沨ost 渚ч€愰」淇€?DNS銆佷唬鐞嗐€乀CP銆乀LS銆侀槻鐏銆佸湴鍩熼檺鍒躲€乄SS 鎸佺画鏀跺寘璺緞銆?

## 2. 闇€瑕佷慨鏀圭殑鏂囦欢娓呭崟

- `C:\Users\user\Documents\Claude\Projects\EnhengClaw\src\enhengclaw\orchestration\shadow_acceptance.py`
- `C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\run_controlled_shadow_soak.py`
- `C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\verify\run_real_shadow_acceptance.py`
- `C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\run_shadow_24h.ps1`
- `C:\Users\user\Documents\Claude\Projects\EnhengClaw\tests\test_real_shadow_acceptance.py`

## 3. 鍏抽敭浠ｇ爜淇敼

### a) permit margin 缁熶竴

```python
# src/enhengclaw/orchestration/shadow_acceptance.py
REAL_24H_DURATION_SECONDS = 24 * 60 * 60
REAL_24H_MIN_PERMIT_MARGIN_SECONDS = float(REAL_24H_DURATION_SECONDS + 60)

def _required_permit_margin_seconds(config: PreflightConfig) -> float:
    if config.simulation_profile == "real" and config.duration_seconds >= REAL_24H_DURATION_SECONDS:
        return max(config.min_permit_margin_seconds, REAL_24H_MIN_PERMIT_MARGIN_SECONDS)
    return max(config.min_permit_margin_seconds, float(config.duration_seconds) + 60.0)

if remaining_seconds < _required_permit_margin_seconds(config):
    raise ValueError(
        f"execution permit expires too soon for the requested soak window: {remaining_seconds:.1f}s remaining"
    )

return {
    "minimum_required_seconds": _required_permit_margin_seconds(config),
}
```

```python
# scripts/run_controlled_shadow_soak.py
parser.add_argument("--min-permit-margin-seconds", type=float, default=None)

def _effective_min_permit_margin_seconds(args: argparse.Namespace) -> float:
    requested_margin = (
        DEFAULT_PERMIT_MARGIN_SECONDS
        if args.min_permit_margin_seconds is None
        else float(args.min_permit_margin_seconds)
    )
    if args.require_real_24h_ready and args.simulation_profile == "real" and args.duration_seconds >= REAL_24H_DURATION_SECONDS:
        return max(requested_margin, REAL_24H_MIN_PERMIT_MARGIN_SECONDS)
    return requested_margin
```

```python
# scripts/verify/run_real_shadow_acceptance.py
parser.add_argument("--min-permit-margin-seconds", type=float, default=(24 * 60 * 60) + 60.0)
```

```powershell
# scripts/run_shadow_24h.ps1
[double]$MinPermitMarginSeconds = 86460
```

### b) Binance preflight 缁撴瀯鍖栬瘖鏂寮?

```python
# src/enhengclaw/orchestration/shadow_acceptance.py
@dataclass(frozen=True, slots=True)
class BinanceProbeError(Exception):
    failure_category: str
    transport_stage: str
    endpoint: str
    transport: str
    host: str | None
    port: int | None
    path: str
    exception_type: str
    exception_message: str
    exception_repr: str
    exception_chain: list[dict[str, Any]]
```

```python
def probe_binance_preflight(*, websocket_url: str, timeout_seconds: float, api_key_env_var: str) -> dict[str, Any]:
    ...
    except BinanceProbeError as exc:
        failure = exc.to_payload()
        return {
            "status": "failed",
            "minimum_permission_model": "public_stream_only",
            "credential_check": secret_check,
            "message": f"Binance websocket probe failed: {exc}",
            **failure,
        }
```

```python
async def _probe_binance_websocket(websocket_url: str, *, timeout_seconds: float) -> dict[str, Any]:
    transport_stage = "connect"
    try:
        async with websockets.connect(
            websocket_url,
            ping_interval=None,
            ping_timeout=None,
            open_timeout=timeout_seconds,
            close_timeout=min(timeout_seconds, 5.0),
        ) as websocket:
            transport_stage = "subscribe_send"
            await websocket.send(...)
            ...
            transport_stage = "data_wait" if acknowledged else "subscription_ack_wait"
            raw_message = await asyncio.wait_for(websocket.recv(), timeout=remaining)
            transport_stage = "payload_parse"
            payload = json.loads(raw_message)
    except Exception as exc:
        raise _build_binance_probe_error(
            exc,
            websocket_url=websocket_url,
            transport_stage=transport_stage,
        ) from exc
```

Stable evidence fields:

- `failure_category`
- `transport_stage`
- `endpoint`
- `transport`
- `host`
- `port`
- `exception_type`
- `exception_message`
- `exception_chain`

## 4. 鐩爣 host 閰嶇疆姝ラ

### 鐪熷疄 permit 鏀剧疆瑕佹眰

```powershell
$ExecutionPermitPath = "<瀹為檯 permit 璺緞>"
if (-not (Test-Path $ExecutionPermitPath)) { throw "missing execution permit: $ExecutionPermitPath" }
```

permit constraints:

- permit 鏂囦欢蹇呴』鍦ㄤ粨搴撳
- permit 鏂囦欢蹇呴』涓嶅湪涓存椂鐩綍涓?
- 鍚姩鏃跺墿浣欐湁鏁堟湡蹇呴』 `>= 86460.0`
- permit 蹇呴』鍏佽 `cli.shadow_ingest.run`
- scope 蹇呴』瑕嗙洊 `shadow_ingestion`
- capabilities 蹇呴』瑕嗙洊 `CAP_CLI_SHADOW_INGEST`銆乣CAP_PROVIDER_STREAM`銆乣CAP_PROVIDER_TRANSPORT`

### trust root 閮ㄧ讲瑕佹眰

```powershell
$TrustRootDir = "C:\ProgramData\EnhengClaw\trust"
New-Item -ItemType Directory -Force -Path $TrustRootDir | Out-Null
Copy-Item "<鐪熷疄 allowed_signers 婧愭枃浠?" (Join-Path $TrustRootDir "allowed_signers") -Force
```

If using explicit trust root:

```powershell
$TrustRootDir = "<TrustRootDir>"
$env:ENHENGCLAW_TRUST_ROOT_DIR = $TrustRootDir
```

trust root constraints:

- `allowed_signers` 蹇呴』瀛樺湪
- 璺緞蹇呴』鍦ㄤ粨搴撳
- 璺緞蹇呴』涓嶅湪涓存椂鐩綍涓?
- 涓嶅彲鍐欐潈闄愮户缁綔涓?host-side 鎿嶄綔鍓嶆彁

### 鏉冮檺瑕佹眰

```powershell
icacls $TrustRootDir /inheritance:r
icacls $TrustRootDir /grant:r "<RuntimeUser>:(RX)" "Administrators:(F)" "SYSTEM:(F)"
icacls (Join-Path $TrustRootDir "allowed_signers") /inheritance:r
icacls (Join-Path $TrustRootDir "allowed_signers") /grant:r "<RuntimeUser>:(R)" "Administrators:(F)" "SYSTEM:(F)"
```

### Binance WSS 璺緞妫€鏌ユ楠?

```powershell
Resolve-DnsName stream.binance.com
```

```powershell
netsh winhttp show proxy
Get-ChildItem Env:HTTP_PROXY,Env:HTTPS_PROXY,Env:ALL_PROXY,Env:NO_PROXY,Env:WS_PROXY,Env:WSS_PROXY -ErrorAction SilentlyContinue
```

```powershell
Test-NetConnection stream.binance.com -Port 9443 -InformationLevel Detailed
```

```powershell
python -c "import socket,ssl; s=socket.create_connection(('stream.binance.com',9443),10); t=ssl.create_default_context().wrap_socket(s,server_hostname='stream.binance.com'); print(t.version()); print(t.cipher()); t.close()"
```

```powershell
@'
import asyncio, json, websockets

async def main():
    async with websockets.connect(
        "wss://stream.binance.com:9443/ws",
        open_timeout=10,
        ping_interval=None,
        ping_timeout=None,
        close_timeout=5,
    ) as ws:
        await ws.send(json.dumps({"method":"SUBSCRIBE","params":["btcusdt@trade"],"id":1}, separators=(",", ":")))
        for _ in range(10):
            msg = await asyncio.wait_for(ws.recv(), timeout=15)
            print(msg)
            if '"stream":"btcusdt@trade"' in msg.lower():
                return
        raise SystemExit(2)

asyncio.run(main())
'@ | python -
```

Firewall / geo constraints:

- 蹇呴』鍏佽鍑虹珯鍒?`stream.binance.com:9443`
- 濡傛灉 DNS銆乀CP銆乀LS 閮介€氳繃锛屼絾 WSS 浠嶅湪 `data_wait` 瓒呮椂锛屾寜 WSS 闀胯繛鎺ユ敹鍖呰闄愬埗澶勭悊

## 5. verify 鍛戒护

```powershell
python -m unittest `
  tests.test_real_shadow_acceptance.RealShadowAcceptanceTests.test_binance_preflight_failure_emits_transport_diagnostics `
  tests.test_real_shadow_acceptance.RealShadowAcceptanceTests.test_real_acceptance_wrapper_real_24h_preflight_fail_closed `
  -v
```

## 6. 淇鍚庣殑 preflight-only 鍛戒护

```powershell
$ErrorActionPreference = "Stop"

$ExecutionPermitPath = "<瀹為檯 permit 璺緞>"
$ArtifactsRoot = "<瀹為檯 artifacts 鏍圭洰褰?"
$Label = "<鏈 preflight 鐨勬柊 label>"
$TrustRootDir = "<濡傞渶鏄惧紡鎸囧畾鍒欑粰鍑?"
$Real24hPermitMarginSeconds = 86460.0

if (-not [string]::IsNullOrWhiteSpace($TrustRootDir)) {
    $env:ENHENGCLAW_TRUST_ROOT_DIR = $TrustRootDir
}

$env:EXECUTION_PERMIT_PATH = $ExecutionPermitPath
$env:ARTIFACTS_ROOT = $ArtifactsRoot
$env:LABEL = $Label
$env:REAL_24H_PERMIT_MARGIN_SECONDS = [string]$Real24hPermitMarginSeconds

@'
import json, os, sys, tempfile
from pathlib import Path

repo = Path(r"C:\Users\user\Documents\Claude\Projects\EnhengClaw").resolve()
sys.path.insert(0, str(repo / "src"))

from enhengclaw.core.execution_control import TRUST_ROOT_DIR_ENV, default_trust_root_dir, resolve_allowed_signers_path
from enhengclaw.orchestration.shadow_acceptance import (
    DEFAULT_CLOCK_SKEW_THRESHOLD_SECONDS,
    DEFAULT_MAX_TOTAL_LOG_BYTES,
    DEFAULT_MIN_FREE_DISK_MB,
    DEFAULT_PROVIDER_PROBE_TIMEOUT_SECONDS,
    PreflightConfig,
    build_provider_health_snapshot,
    run_preflight,
    write_json,
)
from enhengclaw.orchestration.worker_operations import default_ingestion_audit_root

def path_is_under(path: Path, root: Path) -> bool:
    path_text = os.path.normcase(str(path.resolve()))
    root_text = os.path.normcase(str(root.resolve())).rstrip("\\/")
    return path_text == root_text or path_text.startswith(root_text + os.sep)

execution_permit_path = Path(os.environ["EXECUTION_PERMIT_PATH"]).resolve()
artifacts_root = Path(os.environ["ARTIFACTS_ROOT"]).resolve()
label = os.environ["LABEL"]
real_24h_permit_margin_seconds = float(os.environ["REAL_24H_PERMIT_MARGIN_SECONDS"])
temp_root = Path(tempfile.gettempdir()).resolve()

evidence_root = artifacts_root / "preflight_only" / label
run_root = evidence_root / "run_artifacts"
audit_root = default_ingestion_audit_root(run_root)

run_config_path = evidence_root / "run_config.json"
preflight_path = evidence_root / "preflight_result.json"
provider_health_path = evidence_root / "provider_health_snapshot.json"
assertions_path = evidence_root / "preflight_assertions.json"

alchemy_key = os.getenv("ALCHEMY_API_KEY", "").strip()
alchemy_endpoint = (
    f"https://eth-mainnet.g.alchemy.com/v2/{alchemy_key}"
    if alchemy_key else
    "https://eth-mainnet.g.alchemy.com/v2/<missing>"
)

run_config = {
    "acceptance_profile": "real_24h_preflight_only",
    "simulation_profile": "real",
    "duration_seconds": 86400,
    "execution_permit": str(execution_permit_path),
    "explicit_execution_permit_supplied": True,
    "binance_websocket_url": "wss://stream.binance.com:9443/ws",
    "alchemy_endpoint_url": alchemy_endpoint,
    "clock_reference_url": "https://api.binance.com/api/v3/time",
    "min_free_disk_mb": DEFAULT_MIN_FREE_DISK_MB,
    "max_total_log_bytes": DEFAULT_MAX_TOTAL_LOG_BYTES,
    "clock_skew_threshold_seconds": DEFAULT_CLOCK_SKEW_THRESHOLD_SECONDS,
    "provider_probe_timeout_seconds": DEFAULT_PROVIDER_PROBE_TIMEOUT_SECONDS,
    "min_permit_margin_seconds": real_24h_permit_margin_seconds,
}
write_json(run_config_path, run_config)

preflight = run_preflight(
    PreflightConfig(
        execution_permit_path=execution_permit_path,
        artifacts_root=run_root,
        soak_root=evidence_root,
        audit_root=audit_root,
        duration_seconds=86400,
        simulation_profile="real",
        binance_websocket_url="wss://stream.binance.com:9443/ws",
        alchemy_endpoint_url=alchemy_endpoint,
        alchemy_include_block_details=True,
        clock_reference_url="https://api.binance.com/api/v3/time",
        min_free_disk_mb=DEFAULT_MIN_FREE_DISK_MB,
        max_total_log_bytes=DEFAULT_MAX_TOTAL_LOG_BYTES,
        clock_skew_threshold_seconds=DEFAULT_CLOCK_SKEW_THRESHOLD_SECONDS,
        provider_probe_timeout_seconds=DEFAULT_PROVIDER_PROBE_TIMEOUT_SECONDS,
        min_permit_margin_seconds=real_24h_permit_margin_seconds,
        require_explicit_real_permit=True,
    )
)
write_json(preflight_path, preflight)

provider_health = build_provider_health_snapshot(
    artifacts_root=run_root,
    shadow_summary={"subjects": {}, "stability": {}},
    run_root=None,
    preflight=preflight,
)
write_json(provider_health_path, provider_health)

trust_root_candidate = (Path(os.getenv(TRUST_ROOT_DIR_ENV) or default_trust_root_dir()).resolve() / "allowed_signers").resolve()
trust_root_path_exists = trust_root_candidate.exists()
trust_root_path_outside_repo = not path_is_under(trust_root_candidate, repo)
trust_root_path_not_temp = not path_is_under(trust_root_candidate, temp_root)
trust_root_code_validation_ok = False
trust_root_error = None
try:
    resolved_allowed_signers = resolve_allowed_signers_path().resolve()
    trust_root_code_validation_ok = os.path.normcase(str(resolved_allowed_signers)) == os.path.normcase(str(trust_root_candidate))
except Exception as exc:
    trust_root_error = str(exc)

permit_minimum_required_seconds = preflight.get("checks", {}).get("permit", {}).get("minimum_required_seconds")

assertions = {
    "execution_permit_path_exists": execution_permit_path.exists(),
    "explicit_execution_permit_supplied": True,
    "execution_permit_path_outside_repo": not path_is_under(execution_permit_path, repo),
    "execution_permit_path_not_temp": not path_is_under(execution_permit_path, temp_root),
    "permit_minimum_margin_seconds_ok": permit_minimum_required_seconds == real_24h_permit_margin_seconds,
    "trust_root_ok": (
        trust_root_path_exists
        and trust_root_path_outside_repo
        and trust_root_path_not_temp
        and trust_root_code_validation_ok
    ),
    "binance_preflight_passed": preflight.get("checks", {}).get("provider_binance", {}).get("status") == "passed",
    "alchemy_preflight_passed": preflight.get("checks", {}).get("provider_alchemy", {}).get("status") == "passed",
    "run_config_min_permit_margin_seconds_ok": run_config["min_permit_margin_seconds"] == real_24h_permit_margin_seconds,
    "preflight_minimum_required_seconds_ok": permit_minimum_required_seconds == real_24h_permit_margin_seconds,
    "key_evidence_files_exist": False,
    "preflight_status_passed": preflight.get("status") == "passed",
}

payload = {
    "all_green": False,
    "assertions": assertions,
    "details": {
        "execution_permit_path": str(execution_permit_path),
        "trust_root_candidate_path": str(trust_root_candidate),
        "trust_root_path_exists": trust_root_path_exists,
        "trust_root_path_outside_repo": trust_root_path_outside_repo,
        "trust_root_path_not_temp": trust_root_path_not_temp,
        "trust_root_code_validation_ok": trust_root_code_validation_ok,
        "trust_root_error": trust_root_error,
        "real_24h_permit_margin_seconds": real_24h_permit_margin_seconds,
        "permit_minimum_required_seconds": permit_minimum_required_seconds,
        "run_config_path": str(run_config_path),
        "preflight_result_path": str(preflight_path),
        "provider_health_snapshot_path": str(provider_health_path),
    },
}
write_json(assertions_path, payload)

required_files = [
    run_config_path,
    preflight_path,
    provider_health_path,
    assertions_path,
]
payload["assertions"]["key_evidence_files_exist"] = all(path.exists() for path in required_files)
payload["all_green"] = (
    payload["assertions"]["preflight_status_passed"] is True
    and all(payload["assertions"].values())
)
write_json(assertions_path, payload)

result = {
    "evidence_root": str(evidence_root),
    "run_config_path": str(run_config_path),
    "preflight_result_path": str(preflight_path),
    "provider_health_snapshot_path": str(provider_health_path),
    "preflight_assertions_path": str(assertions_path),
    "all_green": payload["all_green"],
    "assertions": payload["assertions"],
}
print(json.dumps(result, indent=2, sort_keys=True))
raise SystemExit(0 if payload["all_green"] else 1)
'@ | python -
```

## 7. real-24h rerun 鍛戒护

- Only run when section 6 output has `all_green = true`.
- `Label` must differ from `PreflightLabel`.
- New rerun evidence dir is fixed to `<ArtifactsRoot>\soak_runs\<Label>`.

```powershell
$ErrorActionPreference = "Stop"

$ExecutionPermitPath = "<瀹為檯 permit 璺緞>"
$ArtifactsRoot = "<瀹為檯 artifacts 鏍圭洰褰?"
$PreflightLabel = "<绗?6 椤逛娇鐢ㄧ殑 preflight label>"
$Label = "<鏈 rerun 鐨勬柊 label>"
$TrustRootDir = "<濡傞渶鏄惧紡鎸囧畾鍒欑粰鍑?"
$PreflightAssertionsPath = Join-Path $ArtifactsRoot "preflight_only\$PreflightLabel\preflight_assertions.json"
$EvidenceDir = Join-Path $ArtifactsRoot "soak_runs\$Label"

if ($Label -eq $PreflightLabel) { throw "rerun label must differ from preflight label" }
if (-not (Test-Path $PreflightAssertionsPath)) { throw "missing $PreflightAssertionsPath" }

$preflightPayload = Get-Content -Raw $PreflightAssertionsPath | ConvertFrom-Json
if ($preflightPayload.all_green -ne $true) { throw "preflight all_green is not true: $PreflightAssertionsPath" }
if (Test-Path $EvidenceDir) { throw "rerun evidence dir already exists: $EvidenceDir" }

if (-not [string]::IsNullOrWhiteSpace($TrustRootDir)) {
    $env:ENHENGCLAW_TRUST_ROOT_DIR = $TrustRootDir
}

powershell -File scripts\run_shadow_24h.ps1 `
  -ExecutionPermitPath $ExecutionPermitPath `
  -ArtifactsRoot $ArtifactsRoot `
  -Label $Label `
  -MinPermitMarginSeconds 86460

Write-Output "RERUN_LABEL=$Label"
Write-Output "RERUN_EVIDENCE_DIR=$EvidenceDir"
```

## 8. rerun 瀹屾垚鍚庣殑楠屾敹瑙勫垯

- Only read the new evidence for the rerun label.
- Never read old `verify`, `smoke`, or `preflight_only` directories.
- Only read `<ArtifactsRoot>\soak_runs\<Label>`.
- Required files:
  - `go_no_go.json`
  - `soak_summary.json`
  - `provider_health_snapshot.json`
  - `audit_record.json`
- Required outputs:
  - `READY_FOR_REAL_24H_SHADOW`
  - `READY_FOR_AGENT_LAYER`
  - `hard_failures`
  - `soft_failures`
  - `audit_status`
  - `soak_violations`

```powershell
$ErrorActionPreference = "Stop"

$ArtifactsRoot = "<瀹為檯 artifacts 鏍圭洰褰?"
$PreflightLabel = "<绗?6 椤逛娇鐢ㄧ殑 preflight label>"
$Label = "<鏈 rerun 鐨勬柊 label>"

if ($Label -eq $PreflightLabel) { throw "rerun label must differ from preflight label" }

$EvidenceDir = Join-Path $ArtifactsRoot "soak_runs\$Label"
if ($EvidenceDir -like "*\preflight_only\*") { throw "invalid evidence dir: $EvidenceDir" }

$GoNoGoPath = Join-Path $EvidenceDir "go_no_go.json"
$SoakSummaryPath = Join-Path $EvidenceDir "soak_summary.json"
$ProviderHealthPath = Join-Path $EvidenceDir "provider_health_snapshot.json"
$AuditRecordPath = Join-Path $EvidenceDir "audit_record.json"

if (-not (Test-Path $GoNoGoPath)) { throw "missing $GoNoGoPath" }
if (-not (Test-Path $SoakSummaryPath)) { throw "missing $SoakSummaryPath" }
if (-not (Test-Path $ProviderHealthPath)) { throw "missing $ProviderHealthPath" }
if (-not (Test-Path $AuditRecordPath)) { throw "missing $AuditRecordPath" }

$go = Get-Content -Raw $GoNoGoPath | ConvertFrom-Json
$summary = Get-Content -Raw $SoakSummaryPath | ConvertFrom-Json
$provider = Get-Content -Raw $ProviderHealthPath | ConvertFrom-Json
$audit = Get-Content -Raw $AuditRecordPath | ConvertFrom-Json

$auditStatus = $audit.status
$soakViolations = @($summary.violations)
$hardFailures = @($go.hard_failures)
$softFailures = @($go.soft_failures)
$readyForReal = $go.READY_FOR_REAL_24H_SHADOW
$readyForAgent = $go.READY_FOR_AGENT_LAYER

$result = [pscustomobject]@{
    EvidenceDir = $EvidenceDir
    READY_FOR_REAL_24H_SHADOW = $readyForReal
    READY_FOR_AGENT_LAYER = $readyForAgent
    hard_failures = $hardFailures
    soft_failures = $softFailures
    audit_status = $auditStatus
    soak_violations = $soakViolations
}

$result | ConvertTo-Json -Depth 6

if ($readyForReal -ne $true) { throw "READY_FOR_REAL_24H_SHADOW is not true" }
if ($hardFailures.Count -ne 0) { throw "hard_failures is not empty" }
if ($softFailures.Count -ne 0) { throw "soft_failures is not empty" }
if ($auditStatus -ne "completed") { throw "audit_record.status is not completed" }
if ($soakViolations.Count -ne 0) { throw "soak_summary.violations is not empty" }
```
