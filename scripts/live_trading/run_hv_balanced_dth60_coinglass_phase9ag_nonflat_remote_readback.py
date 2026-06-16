from __future__ import annotations

import argparse
import json
import posixpath
import shlex
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ac_remote_runner_p9aa_readback import (  # noqa: E402
    DEFAULT_EXPECTED_EGRESS_IP,
    DEFAULT_REMOTE_CONFIG,
    DEFAULT_REMOTE_HOST,
    DEFAULT_REMOTE_LIVE_ENV,
    DEFAULT_REMOTE_REPO,
    REMOTE_SYNC_FILES,
    CommandResult,
    CommandRunner,
    json_from_command,
    local_command_runner,
    p9aa_ready,
    remote_preflight_command,
    remote_prepare_sync_command,
    remote_sha_command,
    remote_snapshot_script,
    scp_args,
    scp_from_args,
    snapshot_boundary_ok,
    ssh_args,
    timer_state_digest,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9af_nonflat_execution_owner_gate import (  # noqa: E402
    CONTRACT_VERSION as P9AF_CONTRACT,
    P9AG_GATE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    evidence_file,
    file_sha256,
    latest_match,
    load_optional,
    resolve_path,
    write_json,
)


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9ag_nonflat_remote_readback.v1"
APPROVE_P9AG_DECISION = "approve_p9ag_execute_nonflat_remote_runner_no_order_p9aa_readback_only"
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9ag_nonflat_remote_readback"
PHASE9AF_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9af_nonflat_execution_owner_gate"
DEFAULT_REMOTE_PROOF_PARENT = "/root/meridian_alpha_live_runner/proof_artifacts/p9ag"
DEFAULT_REMOTE_PYTHON = "/root/meridian_alpha_live_runner/venv/bin/python"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Execute P9AG: non-flat remote-runner no-order P9AA readback with "
            "fresh account proof, pre/post position fingerprints, zero "
            "order/fill/trade deltas, baseline-only executor input, and "
            "candidate shadow-only output. Live order submission remains "
            "forbidden."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--phase9af-summary", default="")
    parser.add_argument("--phase9z-summary", default="")
    parser.add_argument("--remote-host", default=DEFAULT_REMOTE_HOST)
    parser.add_argument("--remote-repo", default=DEFAULT_REMOTE_REPO)
    parser.add_argument("--remote-config", default=DEFAULT_REMOTE_CONFIG)
    parser.add_argument("--remote-live-env", default=DEFAULT_REMOTE_LIVE_ENV)
    parser.add_argument("--remote-python", default=DEFAULT_REMOTE_PYTHON)
    parser.add_argument("--remote-proof-parent", default=DEFAULT_REMOTE_PROOF_PARENT)
    parser.add_argument("--expected-egress-ip", default=DEFAULT_EXPECTED_EGRESS_IP)
    parser.add_argument("--shadow-cycles", type=int, default=3)
    parser.add_argument("--ssh-connect-timeout", type=int, default=10)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9AG_DECISION)
    parser.add_argument("--owner-decision-source", default="user_chat:execute_p9ag_nonflat_remote_readback")
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def owner_decision_record(args: argparse.Namespace, generated_at: datetime) -> dict[str, Any]:
    approved = args.owner_decision == APPROVE_P9AG_DECISION
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ag_owner_decision.v1",
        "recorded_at_utc": iso_z(generated_at),
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "execute_nonflat_remote_runner_no_order_p9aa_readback_only",
        "decision_effect": "execute_p9ag_nonflat_remote_no_order_readback" if approved else "none",
        "p9ag_execution_approved": approved,
        "remote_sync_approved": approved,
        "remote_execution_approved": approved,
        "fresh_remote_account_read_proof_required": True,
        "position_fingerprint_required": True,
        "pit_safe_nonflat_position_reference_fixture_approved": approved,
        "position_reference_fixture_source": "same_run_pre_position_fingerprint_only",
        "position_reference_fixture_artifact_scope": "proof_artifacts_only",
        "generated_no_order_config_required": True,
        "consecutive_cycles_required": 3,
        "candidate_execution_approved": False,
        "candidate_live_order_submission_approved": False,
        "live_order_submission_approved": False,
        "target_plan_replacement_approved": False,
        "executor_input_mutation_approved": False,
        "live_config_mutation_approved": False,
        "operator_state_mutation_approved": False,
        "timer_or_service_mutation_approved": False,
        "production_timer_service_load_approved": False,
        "repo_stage_change_approved": False,
    }


def p9af_ready_for_p9ag(summary: dict[str, Any]) -> bool:
    matrix = load_optional(resolve_path(dict(summary.get("output_files") or {}).get("execution_decision_matrix", "")))
    requirements = dict(matrix.get("p9ag_acceptance_requirements") or {})
    authorizations = dict(matrix.get("current_gate_authorizations") or {})
    gates = dict(summary.get("gates") or {})
    return (
        summary.get("contract_version") == P9AF_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9af_nonflat_execution_owner_gate_ready") is True
        and summary.get("review_scope_discusses_actual_execution") is True
        and summary.get("eligible_for_future_p9ag_nonflat_readback_execution_gate") is True
        and summary.get("allowed_next_gate") == P9AG_GATE
        and summary.get("nonflat_remote_no_order_readback_execution_authorized") is False
        and summary.get("p9ag_execution_authorized") is False
        and summary.get("remote_sync_authorized") is False
        and summary.get("remote_execution_authorized") is False
        and int(summary.get("orders_submitted") or 0) == 0
        and int(summary.get("fill_count") or 0) == 0
        and matrix.get("allowed_next_gate") == P9AG_GATE
        and matrix.get("p9ag_must_follow_p9ad_and_p9ae_contracts") is True
        and requirements.get("fresh_remote_account_read_same_run") is True
        and requirements.get("position_fingerprint_stability") is True
        and requirements.get("zero_open_orders_pre_and_post") is True
        and requirements.get("orders_submitted_delta") == 0
        and requirements.get("orders_canceled_delta") == 0
        and requirements.get("fills_delta") == 0
        and requirements.get("account_trade_delta") == 0
        and requirements.get("baseline_only_executor_input") is True
        and requirements.get("candidate_shadow_artifact_only") is True
        and requirements.get("remote_control_boundary_unchanged") is True
        and requirements.get("production_timer_service_loaded_or_modified") is False
        and authorizations.get("p9ag_execution") is False
        and authorizations.get("remote_sync") is False
        and authorizations.get("remote_execution") is False
        and authorizations.get("candidate_execution") is False
        and authorizations.get("live_order_submission") is False
        and gates.get("p9ae_owner_gate_ready") is True
        and gates.get("p9ag_execution_not_authorized_in_p9af") is True
        and gates.get("remote_sync_not_authorized_in_p9af") is True
        and gates.get("remote_execution_not_authorized_in_p9af") is True
    )


def side_effects_zero(summary: dict[str, Any]) -> bool:
    side_effects = dict(summary.get("side_effects") or {})
    return (
        side_effects.get("orders_submitted") == 0
        and side_effects.get("orders_canceled") == 0
        and side_effects.get("order_test_calls", 0) == 0
        and side_effects.get("only_http_get_endpoints") is True
    )


def nonflat_account_read_ready(summary: dict[str, Any]) -> bool:
    blockers = set(str(item) for item in summary.get("blockers") or [])
    nonflat_blockers = [item for item in blockers if item.startswith("mainnet_open_positions_exist:")]
    disallowed = sorted(item for item in blockers if item not in nonflat_blockers)
    return (
        summary.get("account_readable") is True
        and summary.get("can_trade") is True
        and summary.get("position_mode") == "one_way"
        and str(summary.get("egress_ip") or "") == str(summary.get("expected_egress_ip") or "")
        and int(summary.get("open_order_count") or 0) == 0
        and int(summary.get("open_position_count") or 0) > 0
        and bool(nonflat_blockers)
        and not disallowed
        and side_effects_zero(summary)
    )


def position_fingerprint_ready(summary: dict[str, Any]) -> bool:
    return (
        summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("account_readable") is True
        and summary.get("position_mode") == "one_way"
        and int(summary.get("open_order_count") or 0) == 0
        and int(summary.get("open_position_count") or 0) > 0
        and side_effects_zero(summary)
        and bool(dict(summary.get("position_fingerprint") or {}).get("stable_hash"))
        and bool(dict(summary.get("order_history_fingerprint") or {}).get("history_hash"))
        and bool(dict(summary.get("trade_history_fingerprint") or {}).get("history_hash"))
    )


def position_fingerprints_stable(pre: dict[str, Any], post: dict[str, Any]) -> bool:
    pre_pos = dict(pre.get("position_fingerprint") or {})
    post_pos = dict(post.get("position_fingerprint") or {})
    pre_orders = dict(pre.get("order_history_fingerprint") or {})
    post_orders = dict(post.get("order_history_fingerprint") or {})
    pre_trades = dict(pre.get("trade_history_fingerprint") or {})
    post_trades = dict(post.get("trade_history_fingerprint") or {})
    return (
        position_fingerprint_ready(pre)
        and position_fingerprint_ready(post)
        and pre_pos.get("stable_hash") == post_pos.get("stable_hash")
        and pre_pos.get("stable_rows") == post_pos.get("stable_rows")
        and pre_orders.get("history_hash") == post_orders.get("history_hash")
        and pre_trades.get("history_hash") == post_trades.get("history_hash")
        and int(pre.get("open_order_count") or 0) == 0
        and int(post.get("open_order_count") or 0) == 0
        and int(pre.get("open_position_count") or 0) == int(post.get("open_position_count") or -1)
    )


def order_fill_trade_delta_zero(pre_fingerprint: dict[str, Any], post_fingerprint: dict[str, Any], p9aa_summary: dict[str, Any]) -> bool:
    return (
        position_fingerprints_stable(pre_fingerprint, post_fingerprint)
        and int(p9aa_summary.get("orders_submitted") or 0) == 0
        and int(p9aa_summary.get("fill_count") or 0) == 0
        and dict(pre_fingerprint.get("order_history_fingerprint") or {}).get("history_hash")
        == dict(post_fingerprint.get("order_history_fingerprint") or {}).get("history_hash")
        and dict(pre_fingerprint.get("trade_history_fingerprint") or {}).get("history_hash")
        == dict(post_fingerprint.get("trade_history_fingerprint") or {}).get("history_hash")
    )


def remote_position_fingerprint_command(
    *,
    remote_repo: str,
    remote_live_env: str,
    remote_config: str,
    expected_egress_ip: str,
    output_path: str,
) -> str:
    return f"""
cd {shlex.quote(remote_repo)}
mkdir -p {shlex.quote(posixpath.dirname(output_path))}
set +e
{shlex.quote(remote_live_env)} python3 - <<'PY' > {shlex.quote(output_path)}
import hashlib, hmac, json, os, pathlib, sys, time, urllib.parse, urllib.request, urllib.error

FAPI = "https://fapi.binance.com"
EXPECTED_EGRESS_IP = {expected_egress_ip!r}
CONFIG_PATH = pathlib.Path({remote_config!r})

def env_secret(name):
    return os.environ.get(name, "").strip()

def public_ip():
    try:
        with urllib.request.urlopen("https://api.ipify.org", timeout=15) as response:
            return response.read().decode("utf-8").strip()
    except Exception:
        return "unavailable"

def signed_get(path, *, params=None, api_key, api_secret):
    query_params = dict(params or {{}})
    query_params["recvWindow"] = "5000"
    query_params["timestamp"] = str(int(time.time() * 1000))
    query = urllib.parse.urlencode(query_params)
    sig = hmac.new(api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()
    url = f"{{FAPI.rstrip('/')}}{{path}}?{{query}}&signature={{sig}}"
    req = urllib.request.Request(url, headers={{"X-MBX-APIKEY": api_key, "User-Agent": "Meridian/P9AG-readonly-proof"}})
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            raw = response.read().decode("utf-8")
            return {{"path": path, "status": "ok", "status_code": int(response.status), "payload": json.loads(raw) if raw else {{}}}}
    except urllib.error.HTTPError as exc:
        return {{"path": path, "status": "failed", "status_code": int(exc.code), "error": exc.read().decode("utf-8", errors="replace")[:500]}}
    except Exception as exc:
        return {{"path": path, "status": "failed", "error_type": type(exc).__name__, "error": str(exc)[:500]}}

def payload(endpoint_results, name, default):
    item = endpoint_results.get(name) or {{}}
    return item.get("payload", default) if item.get("status") == "ok" else default

def norm(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).strip()

def digest(payload_obj):
    return hashlib.sha256(json.dumps(payload_obj, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

def config_symbols():
    symbols = []
    try:
        text = CONFIG_PATH.read_text(encoding="utf-8")
    except Exception:
        return symbols
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("symbols:"):
            raw = stripped.split(":", 1)[1]
            symbols.extend(item.strip().upper() for item in raw.split(",") if item.strip())
    return sorted(set(symbols))

def latest_rows(rows, fields):
    normalized = []
    for row in list(rows or []):
        if not isinstance(row, dict):
            continue
        normalized.append({{field: norm(row.get(field)) for field in fields}})
    return sorted(normalized, key=lambda item: json.dumps(item, sort_keys=True))

started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
api_key = env_secret("Trade")
api_secret = env_secret("Secret_Key")
blockers = []
if not api_key:
    blockers.append("missing_api_key_env:Trade")
if not api_secret:
    blockers.append("missing_api_secret_env:Secret_Key")

endpoint_results = {{}}
if not blockers:
    endpoint_results["account"] = signed_get("/fapi/v3/account", api_key=api_key, api_secret=api_secret)
    endpoint_results["open_orders"] = signed_get("/fapi/v1/openOrders", api_key=api_key, api_secret=api_secret)
    endpoint_results["position_mode"] = signed_get("/fapi/v1/positionSide/dual", api_key=api_key, api_secret=api_secret)

for name, item in endpoint_results.items():
    if item.get("status") != "ok":
        blockers.append(f"read_only_endpoint_failed:{{name}}:{{item.get('status_code', item.get('error_type'))}}")

account = payload(endpoint_results, "account", {{}})
open_orders = payload(endpoint_results, "open_orders", [])
position_mode_payload = payload(endpoint_results, "position_mode", {{}})
dual_side = position_mode_payload.get("dualSidePosition")
position_mode = "hedge" if dual_side is True else "one_way" if dual_side is False else None
positions = [row for row in list(account.get("positions") or []) if isinstance(row, dict)]
stable_fields = ["symbol", "positionSide", "positionAmt", "entryPrice", "breakEvenPrice", "isolated", "isolatedWallet"]
stable_rows = []
for row in positions:
    try:
        amount = float(row.get("positionAmt") or 0.0)
    except Exception:
        amount = 0.0
    if abs(amount) > 1e-12:
        stable_rows.append({{field: norm(row.get(field)) for field in stable_fields}})
stable_rows = sorted(stable_rows, key=lambda item: (item.get("symbol", ""), item.get("positionSide", "")))
proof_symbols = sorted(set(config_symbols()) | set(row.get("symbol", "") for row in stable_rows if row.get("symbol")))

egress_ip = public_ip()
if EXPECTED_EGRESS_IP and egress_ip != EXPECTED_EGRESS_IP:
    blockers.append(f"egress_ip_mismatch:expected={{EXPECTED_EGRESS_IP}}:actual={{egress_ip}}")
if position_mode != "one_way":
    blockers.append(f"position_mode_mismatch:expected=one_way:actual={{position_mode}}")
if len(open_orders or []) != 0:
    blockers.append(f"mainnet_open_orders_exist:{{len(open_orders or [])}}")
if len(stable_rows) == 0:
    blockers.append("mainnet_open_positions_missing_for_nonflat_contract")

order_history = {{}}
trade_history = {{}}
order_fields = ["symbol", "orderId", "clientOrderId", "status", "side", "positionSide", "type", "origQty", "executedQty", "updateTime", "time"]
trade_fields = ["symbol", "id", "orderId", "side", "positionSide", "qty", "price", "realizedPnl", "commission", "time"]
for symbol in proof_symbols:
    orders = signed_get("/fapi/v1/allOrders", params={{"symbol": symbol, "limit": "10"}}, api_key=api_key, api_secret=api_secret)
    trades = signed_get("/fapi/v1/userTrades", params={{"symbol": symbol, "limit": "10"}}, api_key=api_key, api_secret=api_secret)
    if orders.get("status") != "ok":
        blockers.append(f"read_only_endpoint_failed:allOrders:{{symbol}}:{{orders.get('status_code', orders.get('error_type'))}}")
    if trades.get("status") != "ok":
        blockers.append(f"read_only_endpoint_failed:userTrades:{{symbol}}:{{trades.get('status_code', trades.get('error_type'))}}")
    order_history[symbol] = latest_rows(orders.get("payload") if orders.get("status") == "ok" else [], order_fields)
    trade_history[symbol] = latest_rows(trades.get("payload") if trades.get("status") == "ok" else [], trade_fields)

position_fingerprint = {{"stable_fields": stable_fields, "stable_rows": stable_rows, "stable_hash": digest(stable_rows)}}
order_history_fingerprint = {{"proof_symbols": proof_symbols, "history": order_history, "history_hash": digest(order_history)}}
trade_history_fingerprint = {{"proof_symbols": proof_symbols, "history": trade_history, "history_hash": digest(trade_history)}}
status = "ready" if not blockers else "blocked"
summary = {{
    "contract_version": "hv_balanced_dth60_coinglass_phase9ag_position_fingerprint.v1",
    "started_at_utc": started,
    "finished_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "status": status,
    "blockers": sorted(set(blockers)),
    "account_readable": bool(account),
    "egress_ip": egress_ip,
    "expected_egress_ip": EXPECTED_EGRESS_IP,
    "position_mode": position_mode,
    "open_order_count": len(open_orders or []),
    "open_position_count": len(stable_rows),
    "proof_symbol_count": len(proof_symbols),
    "proof_symbols": proof_symbols,
    "position_fingerprint": position_fingerprint,
    "order_history_fingerprint": order_history_fingerprint,
    "trade_history_fingerprint": trade_history_fingerprint,
    "endpoint_results": {{
        name: {{key: item.get(key) for key in ("path", "status", "status_code", "error_type", "error") if key in item}}
        for name, item in endpoint_results.items()
    }},
    "side_effects": {{
        "orders_submitted": 0,
        "orders_canceled": 0,
        "order_test_calls": 0,
        "only_http_get_endpoints": True,
    }},
}}
print(json.dumps(summary, indent=2, sort_keys=True))
sys.exit(0 if status == "ready" else 2)
PY
rc=$?
cat {shlex.quote(output_path)}
exit $rc
"""


def remote_python_invocation(*, remote_repo: str, remote_live_env: str, remote_python: str) -> str:
    python_path = remote_python.rstrip("/")
    venv_root = posixpath.dirname(posixpath.dirname(python_path)) if "/bin/" in python_path else ""
    env_parts = [
        shlex.quote(remote_live_env),
        "/usr/bin/env",
        shlex.quote(f"PYTHONPATH={remote_repo.rstrip('/')}/src"),
        "PYTHONNOUSERSITE=1",
    ]
    if venv_root:
        env_parts.append(shlex.quote(f"VIRTUAL_ENV={venv_root}"))
        env_parts.append(
            shlex.quote(
                f"PATH={venv_root}/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
            )
        )
    env_parts.append(shlex.quote(python_path))
    return " ".join(env_parts)


def remote_p9ag_p9aa_command(
    *,
    remote_repo: str,
    remote_live_env: str,
    remote_python: str,
    remote_p9z_summary: str,
    remote_config: str,
    remote_p9aa_output: str,
    remote_position_reference_source: str,
    shadow_cycles: int,
) -> str:
    stdout_log = f"{remote_p9aa_output.rstrip('/')}/p9aa_cli_stdout.log"
    stderr_log = f"{remote_p9aa_output.rstrip('/')}/p9aa_cli_stderr.log"
    python_cmd = remote_python_invocation(
        remote_repo=remote_repo,
        remote_live_env=remote_live_env,
        remote_python=remote_python,
    )
    return f"""
cd {shlex.quote(remote_repo)}
mkdir -p {shlex.quote(remote_p9aa_output)}
set +e
{python_cmd} scripts/live_trading/run_hv_balanced_dth60_coinglass_phase9aa_timer_path_shadow_cycles.py \\
  --phase9z-summary {shlex.quote(remote_p9z_summary)} \\
  --base-config {shlex.quote(remote_config)} \\
  --output-root {shlex.quote(remote_p9aa_output)} \\
  --position-reference-source {shlex.quote(remote_position_reference_source)} \\
  --shadow-cycles {int(shadow_cycles)} > {shlex.quote(stdout_log)} 2> {shlex.quote(stderr_log)}
rc=$?
cat {shlex.quote(remote_p9aa_output)}/summary.json 2>/dev/null || true
exit $rc
"""


def build_phase9ag(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
    command_runner: CommandRunner = local_command_runner,
) -> tuple[dict[str, Any], int]:
    generated_at = now_fn()
    run_id = generated_at.strftime("%Y%m%dT%H%M%SZ")
    root = resolve_path(args.output_root) if str(args.output_root).strip() else resolve_path(DEFAULT_OUTPUT_PARENT) / run_id
    root.mkdir(parents=True, exist_ok=True)
    readback_root = root / "remote_readback"
    readback_root.mkdir(parents=True, exist_ok=True)
    phase9af_path = (
        resolve_path(args.phase9af_summary)
        if str(args.phase9af_summary).strip()
        else latest_match(PHASE9AF_PARENT, "*/summary.json")
    )
    p9af = load_optional(phase9af_path)
    phase9z_path = resolve_path(args.phase9z_summary) if str(args.phase9z_summary).strip() else latest_match(
        "artifacts/live_trading/hv_balanced_dth60_p9z_timer_path_readback_owner_gate",
        "*/summary.json",
    )
    decision = owner_decision_record(args, generated_at)
    write_json(root / "owner_decision_record.json", decision)

    pre_gates = {
        "owner_decision_p9ag_execute_only": args.owner_decision == APPROVE_P9AG_DECISION,
        "p9af_owner_gate_ready": p9af_ready_for_p9ag(p9af),
        "phase9z_summary_exists": phase9z_path.exists(),
        "requested_shadow_cycles_at_least_three": int(args.shadow_cycles or 0) >= 3,
    }
    blockers = [key for key, value in pre_gates.items() if not value]
    command_records: list[dict[str, Any]] = []
    remote_root = f"{str(args.remote_proof_parent).rstrip('/')}/{run_id}"
    remote_inputs = f"{remote_root}/inputs"
    remote_backup = f"{remote_root}/backups"
    remote_p9z = f"{remote_inputs}/phase9z_summary.json"
    remote_preflight_pre = f"{remote_root}/fresh_remote_account_read_pre.json"
    remote_preflight_post = f"{remote_root}/fresh_remote_account_read_post.json"
    remote_fingerprint_pre = f"{remote_root}/position_fingerprint_pre.json"
    remote_fingerprint_post = f"{remote_root}/position_fingerprint_post.json"
    remote_p9aa_output = f"{remote_root}/p9aa"
    remote_readback_tarball = f"{remote_root}.tar.gz"

    def run_record(label: str, cmd: Sequence[str]) -> CommandResult:
        result = command_runner(cmd)
        command_records.append(
            {
                "label": label,
                "args": list(cmd),
                "returncode": result.returncode,
                "stdout_tail": result.stdout[-4000:],
                "stderr_tail": result.stderr[-4000:],
            }
        )
        return result

    pre_snapshot: dict[str, Any] = {}
    post_snapshot: dict[str, Any] = {}
    preflight_pre: dict[str, Any] = {}
    preflight_post: dict[str, Any] = {}
    fingerprint_pre: dict[str, Any] = {}
    fingerprint_post: dict[str, Any] = {}
    p9aa_summary: dict[str, Any] = {}
    sync_records: list[dict[str, Any]] = []

    if not blockers:
        run_record(
            "remote_mkdir",
            ssh_args(
                args.remote_host,
                args.ssh_connect_timeout,
                f"mkdir -p {shlex.quote(remote_inputs)} {shlex.quote(remote_backup)} {shlex.quote(remote_p9aa_output)}",
            ),
        )
        pre_snapshot_result = run_record(
            "pre_control_snapshot",
            ssh_args(args.remote_host, args.ssh_connect_timeout, remote_snapshot_script(args.remote_repo, args.remote_config)),
        )
        pre_snapshot = json_from_command(pre_snapshot_result)
        write_json(root / "pre_control_snapshot.json", pre_snapshot)

    if not blockers:
        preflight_pre_result = run_record(
            "fresh_remote_account_read_pre",
            ssh_args(
                args.remote_host,
                args.ssh_connect_timeout,
                remote_preflight_command(args.remote_repo, args.remote_live_env, args.expected_egress_ip, remote_preflight_pre),
            ),
        )
        preflight_pre = json_from_command(preflight_pre_result)
        write_json(root / "fresh_remote_account_read_pre.json", preflight_pre)
        if not nonflat_account_read_ready(preflight_pre):
            blockers.append("fresh_remote_account_read_pre_nonflat_failed")

    if not blockers:
        fingerprint_pre_result = run_record(
            "position_fingerprint_pre",
            ssh_args(
                args.remote_host,
                args.ssh_connect_timeout,
                remote_position_fingerprint_command(
                    remote_repo=args.remote_repo,
                    remote_live_env=args.remote_live_env,
                    remote_config=args.remote_config,
                    expected_egress_ip=args.expected_egress_ip,
                    output_path=remote_fingerprint_pre,
                ),
            ),
        )
        fingerprint_pre = json_from_command(fingerprint_pre_result)
        write_json(root / "position_fingerprint_pre.json", fingerprint_pre)
        if not position_fingerprint_ready(fingerprint_pre):
            blockers.append("position_fingerprint_pre_failed")

    if not blockers:
        p9z_copy = run_record("copy_phase9z_summary", scp_args(args.remote_host, args.ssh_connect_timeout, phase9z_path, remote_p9z))
        if p9z_copy.returncode != 0:
            blockers.append("phase9z_remote_copy_failed")
        for rel in REMOTE_SYNC_FILES:
            local_path = resolve_path(rel)
            if not local_path.exists():
                sync_records.append({"path": rel, "status": "missing_local"})
                blockers.append(f"sync_file_missing_local:{rel}")
                continue
            local_sha = file_sha256(local_path)
            remote_sha_before = run_record(
                f"sync_pre_sha:{rel}",
                ssh_args(args.remote_host, args.ssh_connect_timeout, remote_sha_command(args.remote_repo, rel)),
            )
            remote_sha_before_text = remote_sha_before.stdout.strip().splitlines()[-1] if remote_sha_before.stdout.strip() else ""
            if remote_sha_before_text == local_sha:
                sync_records.append(
                    {
                        "path": rel,
                        "status": "already_matching",
                        "local_sha256": local_sha,
                        "remote_sha256": remote_sha_before_text,
                        "copy_returncode": None,
                    }
                )
                continue
            prep = run_record(
                f"sync_prepare:{rel}",
                ssh_args(args.remote_host, args.ssh_connect_timeout, remote_prepare_sync_command(args.remote_repo, remote_backup, rel)),
            )
            if prep.returncode != 0:
                sync_records.append({"path": rel, "status": "prepare_failed", "returncode": prep.returncode})
                blockers.append(f"sync_prepare_failed:{rel}")
                continue
            dest = f"{str(args.remote_repo).rstrip('/')}/{rel}"
            copy = run_record(f"sync_copy:{rel}", scp_args(args.remote_host, args.ssh_connect_timeout, local_path, dest))
            remote_sha = run_record(
                f"sync_sha:{rel}",
                ssh_args(args.remote_host, args.ssh_connect_timeout, remote_sha_command(args.remote_repo, rel)),
            )
            remote_sha_text = remote_sha.stdout.strip().splitlines()[-1] if remote_sha.stdout.strip() else ""
            record = {
                "path": rel,
                "status": "synced" if copy.returncode == 0 and remote_sha_text == local_sha else "blocked",
                "local_sha256": local_sha,
                "remote_sha256": remote_sha_text,
                "copy_returncode": copy.returncode,
            }
            sync_records.append(record)
            if record["status"] != "synced":
                blockers.append(f"sync_sha_mismatch_or_copy_failed:{rel}")
        write_json(root / "remote_sync_manifest.json", {"remote_root": remote_root, "files": sync_records})

    if not blockers:
        remote_py = remote_python_invocation(
            remote_repo=args.remote_repo,
            remote_live_env=args.remote_live_env,
            remote_python=args.remote_python,
        )
        compile_result = run_record(
            "remote_py_compile_p9aa",
            ssh_args(
                args.remote_host,
                args.ssh_connect_timeout,
                (
                    f"cd {shlex.quote(args.remote_repo)} && "
                    f"{remote_py} -m py_compile "
                    "scripts/live_trading/run_hv_balanced_dth60_coinglass_phase9aa_timer_path_shadow_cycles.py "
                    "scripts/live_trading/run_hv_balanced_dth60_coinglass_phase9z_timer_path_readback_owner_gate.py "
                    "src/enhengclaw/live_trading/dth60_observe_only_shadow_hook.py"
                ),
            ),
        )
        if compile_result.returncode != 0:
            blockers.append("remote_py_compile_failed")

    if not blockers:
        p9aa_result = run_record(
            "remote_p9aa_no_order_readback",
            ssh_args(
                args.remote_host,
                args.ssh_connect_timeout,
                remote_p9ag_p9aa_command(
                    remote_repo=args.remote_repo,
                    remote_live_env=args.remote_live_env,
                    remote_python=args.remote_python,
                    remote_p9z_summary=remote_p9z,
                    remote_config=args.remote_config,
                    remote_p9aa_output=remote_p9aa_output,
                    remote_position_reference_source=remote_fingerprint_pre,
                    shadow_cycles=int(args.shadow_cycles or 0),
                ),
            ),
        )
        p9aa_summary = json_from_command(p9aa_result)
        write_json(root / "remote_p9aa_summary_inline.json", p9aa_summary)
        if not p9aa_ready(p9aa_summary):
            blockers.append("remote_p9aa_no_order_readback_failed")

    if preflight_pre or fingerprint_pre or p9aa_summary:
        fingerprint_post_result = run_record(
            "position_fingerprint_post",
            ssh_args(
                args.remote_host,
                args.ssh_connect_timeout,
                remote_position_fingerprint_command(
                    remote_repo=args.remote_repo,
                    remote_live_env=args.remote_live_env,
                    remote_config=args.remote_config,
                    expected_egress_ip=args.expected_egress_ip,
                    output_path=remote_fingerprint_post,
                ),
            ),
        )
        fingerprint_post = json_from_command(fingerprint_post_result)
        write_json(root / "position_fingerprint_post.json", fingerprint_post)
        if fingerprint_pre and not position_fingerprints_stable(fingerprint_pre, fingerprint_post):
            blockers.append("position_fingerprint_changed")

        preflight_post_result = run_record(
            "fresh_remote_account_read_post",
            ssh_args(
                args.remote_host,
                args.ssh_connect_timeout,
                remote_preflight_command(args.remote_repo, args.remote_live_env, args.expected_egress_ip, remote_preflight_post),
            ),
        )
        preflight_post = json_from_command(preflight_post_result)
        write_json(root / "fresh_remote_account_read_post.json", preflight_post)
        if not nonflat_account_read_ready(preflight_post):
            blockers.append("fresh_remote_account_read_post_nonflat_failed")

    if pre_snapshot:
        post_snapshot_result = run_record(
            "post_control_snapshot",
            ssh_args(args.remote_host, args.ssh_connect_timeout, remote_snapshot_script(args.remote_repo, args.remote_config)),
        )
        post_snapshot = json_from_command(post_snapshot_result)
        write_json(root / "post_control_snapshot.json", post_snapshot)
        if not snapshot_boundary_ok(pre_snapshot, post_snapshot):
            blockers.append("remote_control_boundary_changed")

    if preflight_pre or p9aa_summary:
        fetch_result = run_record(
            "fetch_remote_readback",
            scp_from_args(args.remote_host, args.ssh_connect_timeout, remote_root, readback_root),
        )
        if fetch_result.returncode != 0:
            tar_result = run_record(
                "fetch_remote_readback_tar_create",
                ssh_args(
                    args.remote_host,
                    args.ssh_connect_timeout,
                    (
                        f"tar -C {shlex.quote(posixpath.dirname(remote_root))} "
                        f"-czf {shlex.quote(remote_readback_tarball)} {shlex.quote(posixpath.basename(remote_root))}"
                    ),
                ),
            )
            tar_fetch = run_record(
                "fetch_remote_readback_tarball",
                scp_from_args(args.remote_host, args.ssh_connect_timeout, remote_readback_tarball, root / "remote_readback.tar.gz"),
            )
            if tar_result.returncode != 0 or tar_fetch.returncode != 0:
                blockers.append("remote_readback_fetch_failed")

    write_json(root / "command_records.json", {"commands": command_records})
    status = "ready" if not blockers else "blocked"
    sync_statuses = {str(row.get("status")) for row in sync_records}
    copied_sync_count = sum(1 for row in sync_records if row.get("status") == "synced")
    command_returncodes = {str(item.get("label")): int(item.get("returncode") or 0) for item in command_records}
    zero_delta = order_fill_trade_delta_zero(fingerprint_pre, fingerprint_post, p9aa_summary) if p9aa_summary else False
    gates = {
        **pre_gates,
        "fresh_remote_account_read_pre_nonflat_ready": nonflat_account_read_ready(preflight_pre),
        "position_fingerprint_pre_ready": position_fingerprint_ready(fingerprint_pre),
        "remote_sync_all_files_ready": bool(sync_records)
        and sync_statuses.issubset({"already_matching", "synced"})
        and len(sync_records) == len(REMOTE_SYNC_FILES),
        "remote_py_compile_passed": command_returncodes.get("remote_py_compile_p9aa") == 0
        if "remote_py_compile_p9aa" in command_returncodes
        else False,
        "remote_p9aa_no_order_readback_ready": p9aa_ready(p9aa_summary),
        "pit_safe_position_reference_fixture_ready": (
            p9aa_summary.get("position_reference_fixture_requested") is True
            and p9aa_summary.get("position_reference_fixture_ready") is True
            and dict(p9aa_summary.get("position_reference_fixture_summary") or {}).get("source_created_before_p9aa") is True
            and dict(p9aa_summary.get("position_reference_fixture_summary") or {}).get("read_only") is True
            and dict(p9aa_summary.get("position_reference_fixture_summary") or {}).get("proof_artifacts_only") is True
        ),
        "position_fingerprint_post_ready": position_fingerprint_ready(fingerprint_post),
        "position_fingerprint_stable": bool(fingerprint_pre and fingerprint_post)
        and position_fingerprints_stable(fingerprint_pre, fingerprint_post),
        "fresh_remote_account_read_post_nonflat_ready": nonflat_account_read_ready(preflight_post),
        "zero_order_cancel_fill_trade_delta": zero_delta,
        "remote_control_boundary_unchanged": bool(pre_snapshot and post_snapshot)
        and snapshot_boundary_ok(pre_snapshot, post_snapshot),
        "shadow_cycles_at_least_three": int(p9aa_summary.get("completed_shadow_cycles") or 0) >= 3,
        "fresh_proof_each_cycle": p9aa_summary.get("fresh_proof_each_cycle") is True,
        "same_risk_no_order_config_each_cycle": p9aa_summary.get("same_risk_no_order_config_each_cycle") is True,
        "baseline_only_executor_input": p9aa_ready(p9aa_summary),
        "candidate_shadow_only": p9aa_ready(p9aa_summary),
        "candidate_execution_forbidden": True,
        "live_order_submission_forbidden": True,
        "target_plan_replacement_forbidden": True,
        "executor_input_mutation_forbidden": True,
        "production_timer_service_not_loaded_or_modified": (
            p9aa_summary.get("production_timer_service_loaded_or_modified") is False if p9aa_summary else True
        ),
    }
    if not gates["zero_order_cancel_fill_trade_delta"] and p9aa_summary:
        blockers.append("order_cancel_fill_trade_delta_not_zero_or_unproven")
    if not gates["pit_safe_position_reference_fixture_ready"] and p9aa_summary:
        blockers.append("pit_safe_position_reference_fixture_not_ready")
    status = "ready" if not sorted(set(blockers)) else "blocked"
    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(generated_at),
        "status": status,
        "blockers": sorted(set(blockers)),
        "owner_decision": decision,
        "p9ag_nonflat_remote_no_order_readback_ready": status == "ready",
        "remote_host": args.remote_host,
        "remote_repo": args.remote_repo,
        "remote_config": args.remote_config,
        "remote_python": args.remote_python,
        "remote_proof_root": remote_root,
        "remote_sync_authorized": True,
        "remote_execution_authorized": True,
        "remote_sync_performed": copied_sync_count > 0,
        "remote_sync_files_copied": copied_sync_count,
        "remote_execution_performed": bool(p9aa_summary),
        "fresh_remote_account_read_pre": evidence_file(root / "fresh_remote_account_read_pre.json"),
        "position_fingerprint_pre": evidence_file(root / "position_fingerprint_pre.json"),
        "remote_p9aa_summary": evidence_file(root / "remote_p9aa_summary_inline.json"),
        "position_fingerprint_post": evidence_file(root / "position_fingerprint_post.json"),
        "fresh_remote_account_read_post": evidence_file(root / "fresh_remote_account_read_post.json"),
        "pre_control_snapshot": evidence_file(root / "pre_control_snapshot.json"),
        "post_control_snapshot": evidence_file(root / "post_control_snapshot.json"),
        "remote_sync_manifest": evidence_file(root / "remote_sync_manifest.json"),
        "source_evidence": {
            "phase9af_summary": evidence_file(phase9af_path),
            "phase9z_summary": evidence_file(phase9z_path),
        },
        "remote_runner": {
            "expected_egress_ip": args.expected_egress_ip,
            "pre_egress_ip": preflight_pre.get("egress_ip"),
            "post_egress_ip": preflight_post.get("egress_ip"),
        },
        "open_position_count_pre": int(preflight_pre.get("open_position_count") or 0),
        "open_position_count_post": int(preflight_post.get("open_position_count") or 0),
        "open_order_count_pre": int(preflight_pre.get("open_order_count") or 0),
        "open_order_count_post": int(preflight_post.get("open_order_count") or 0),
        "position_fingerprint_stable": gates["position_fingerprint_stable"],
        "pit_safe_position_reference_fixture_ready": gates["pit_safe_position_reference_fixture_ready"],
        "position_reference_fixture": p9aa_summary.get("position_reference_fixture"),
        "order_cancel_fill_trade_delta_zero": gates["zero_order_cancel_fill_trade_delta"],
        "completed_shadow_cycles": int(p9aa_summary.get("completed_shadow_cycles") or 0),
        "fresh_proof_each_cycle": p9aa_summary.get("fresh_proof_each_cycle") is True,
        "same_risk_no_order_config_each_cycle": p9aa_summary.get("same_risk_no_order_config_each_cycle") is True,
        "baseline_only_executor_input": gates["baseline_only_executor_input"],
        "candidate_shadow_only": gates["candidate_shadow_only"],
        "candidate_execution_authorized": False,
        "candidate_live_order_submission_authorized": False,
        "live_order_submission_authorized": False,
        "target_plan_replaced": False,
        "executor_input_mutated": False,
        "orders_submitted": int(p9aa_summary.get("orders_submitted") or 0),
        "fill_count": int(p9aa_summary.get("fill_count") or 0),
        "production_timer_service_loaded_or_modified": p9aa_summary.get("production_timer_service_loaded_or_modified") if p9aa_summary else False,
        "live_config_changed": bool(pre_snapshot and post_snapshot)
        and pre_snapshot.get("remote_live_config_sha256") != post_snapshot.get("remote_live_config_sha256"),
        "operator_state_changed": bool(pre_snapshot and post_snapshot)
        and pre_snapshot.get("operator_state") != post_snapshot.get("operator_state"),
        "timer_state_changed": bool(pre_snapshot and post_snapshot)
        and timer_state_digest(pre_snapshot) != timer_state_digest(post_snapshot),
        "gates": gates,
        "output_files": {
            "summary": str(root / "summary.json"),
            "owner_decision_record": str(root / "owner_decision_record.json"),
            "command_records": str(root / "command_records.json"),
            "remote_sync_manifest": str(root / "remote_sync_manifest.json"),
            "remote_readback": str(readback_root),
            "remote_readback_tarball": str(root / "remote_readback.tar.gz"),
        },
    }
    write_json(root / "summary.json", summary)
    return summary, 0 if status == "ready" else 2


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_phase9ag(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
