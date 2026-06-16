from __future__ import annotations

import argparse
import json
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
    CommandResult,
    CommandRunner,
    json_from_command,
    local_command_runner,
    remote_snapshot_script,
    snapshot_boundary_ok,
    ssh_args,
    timer_state_digest,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ag_nonflat_remote_readback import (  # noqa: E402
    DEFAULT_REMOTE_PYTHON,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cb_fresh_remote_proof_collection_review_package import (  # noqa: E402
    CANARY_SIDE,
    CANARY_SYMBOL,
    DEFAULT_MAX_NOTIONAL_USDT,
    DEFAULT_MAX_ORDERS_PER_CYCLE,
    DEFAULT_MAX_SYMBOLS_PER_CYCLE,
    DEFAULT_ORDER_TYPE,
    DEFAULT_RISK_CEILING_USDT,
    DEFAULT_TIME_IN_FORCE,
    EXPECTED_FORBIDDEN_ACTIONS,
    EXPECTED_PROOFS,
    TARGET_DEPLOY_ROOT_HINT,
    TARGET_RUNNER_IDENTITY_HINT,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cd_read_only_fresh_remote_proof_collection_owner_gate import (  # noqa: E402
    CONTRACT_VERSION as P9CD_CONTRACT,
    DEFAULT_OUTPUT_PARENT as P9CD_PARENT,
    P9CE_GATE,
    P9CE_SCOPE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    evidence_file,
    latest_match,
    load_optional,
    resolve_path,
    write_json,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9tuv_proof_only_corridor import (  # noqa: E402
    PROJECT_PROFILE,
)


CONTRACT_VERSION = (
    "hv_balanced_dth60_coinglass_phase9ce_read_only_fresh_remote_proof_collection.v1"
)
APPROVE_P9CE_DECISION = (
    "approve_p9ce_execute_read_only_fresh_remote_proof_collection_only_no_order_no_candidate_no_timer_no_supervisor_no_executor_mutation"
)
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/p9ce_read_only_fresh_remote_proof_collection"
P9CF_GATE = (
    "P9CF_review_p9ce_read_only_fresh_remote_proof_collection_only_if_separately_requested"
)
P9CF_SCOPE = (
    "review_p9ce_fresh_remote_read_only_proof_collection_before_any_live_order_or_executor_path_change"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Execute P9CE read-only fresh remote proof collection. This runner "
            "uses SSH only for read-only stdout collection and local retained "
            "artifacts. It does not remote sync, write remote files, run "
            "supervisor/timer paths, mutate config/operator/executor state, "
            "execute the candidate, replace target plans, or submit/cancel orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9cd-summary", default="")
    parser.add_argument("--remote-host", default=DEFAULT_REMOTE_HOST)
    parser.add_argument("--remote-repo", default=DEFAULT_REMOTE_REPO)
    parser.add_argument("--remote-config", default=DEFAULT_REMOTE_CONFIG)
    parser.add_argument("--remote-live-env", default=DEFAULT_REMOTE_LIVE_ENV)
    parser.add_argument("--remote-python", default=DEFAULT_REMOTE_PYTHON)
    parser.add_argument("--expected-egress-ip", default=DEFAULT_EXPECTED_EGRESS_IP)
    parser.add_argument("--canary-symbol", default=CANARY_SYMBOL)
    parser.add_argument("--max-history-symbols", type=int, default=20)
    parser.add_argument("--ssh-connect-timeout", type=int, default=10)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9CE_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:p9ce_execute_read_only_fresh_remote_proof_collection",
    )
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def phase_root(args: argparse.Namespace, run_id: str) -> Path:
    if str(args.output_root).strip():
        return resolve_path(args.output_root)
    return resolve_path(DEFAULT_OUTPUT_PARENT) / run_id


def latest_p9cd_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9cd_summary).strip():
        return resolve_path(args.phase9cd_summary)
    return latest_match(P9CD_PARENT, "*/summary.json")


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def source_output_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("output_files") or {}).get(key) or "")
    return resolve_path(text) if text.strip() else Path("")


def p9cd_summary_ready(summary: dict[str, Any]) -> bool:
    return (
        summary.get("contract_version") == P9CD_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9cd_read_only_fresh_remote_proof_collection_owner_gate_ready")
        is True
        and summary.get("p9cc_sufficient_for_p9cd_owner_gate") is True
        and summary.get("read_only_fresh_remote_proof_collection_owner_gate_approved_in_p9cd")
        is True
        and summary.get("eligible_for_future_p9ce_read_only_collection_execution_gate")
        is True
        and summary.get("eligible_for_future_fresh_remote_proof_collection_without_separate_request")
        is False
        and summary.get("eligible_for_future_live_order_submission") is False
        and summary.get("fresh_remote_proof_collection_execution_approved_in_p9cd")
        is False
        and summary.get("fresh_remote_proof_collection_performed_in_p9cd") is False
        and summary.get("fresh_proofs_collected_in_p9cd") is False
        and summary.get("fresh_remote_account_read_performed") is False
        and summary.get("fresh_order_book_read_performed") is False
        and summary.get("exchange_filter_read_performed") is False
        and summary.get("target_runner_identity_hint") == TARGET_RUNNER_IDENTITY_HINT
        and summary.get("target_deploy_root_hint") == TARGET_DEPLOY_ROOT_HINT
        and summary.get("target_runner_identity_proven_in_p9cd") is False
        and summary.get("target_deploy_root_proven_in_p9cd") is False
        and summary.get("live_order_gate_approved") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("candidate_execution_authorized") is False
        and summary.get("target_plan_replacement_authorized") is False
        and summary.get("executor_input_mutation_authorized") is False
        and summary.get("remote_sync_authorized") is False
        and summary.get("remote_execution_authorized") is False
        and summary.get("allowed_next_gate") == P9CE_GATE
        and summary.get("allowed_next_gate_scope") == P9CE_SCOPE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
        and summary.get("canary_symbol") == CANARY_SYMBOL
        and summary.get("canary_side") == CANARY_SIDE
        and float(summary.get("risk_ceiling_usdt") or 0) == DEFAULT_RISK_CEILING_USDT
        and float(summary.get("max_notional_usdt") or 0) == DEFAULT_MAX_NOTIONAL_USDT
        and int(summary.get("max_orders_per_cycle") or 0)
        == DEFAULT_MAX_ORDERS_PER_CYCLE
        and int(summary.get("max_symbols_per_cycle") or 0)
        == DEFAULT_MAX_SYMBOLS_PER_CYCLE
        and summary.get("order_type") == DEFAULT_ORDER_TYPE
        and summary.get("time_in_force") == DEFAULT_TIME_IN_FORCE
        and summary.get("market_orders_allowed") is False
        and int(summary.get("required_fresh_proof_count") or 0)
        == len(EXPECTED_PROOFS)
        and summary.get("only_distance_to_high_60_contribution_changed") is True
        and int_zero(summary, "orders_submitted")
        and int_zero(summary, "orders_canceled")
        and int_zero(summary, "fill_count")
        and int_zero(summary, "trade_count")
    )


def p9cd_terms_ready(terms: dict[str, Any]) -> bool:
    proof_rows = {
        str(row.get("proof_id")): dict(row)
        for row in list(terms.get("required_proofs") or [])
    }
    deltas = dict(terms.get("delta_acceptance") or {})
    staleness = dict(terms.get("staleness_policy") or {})
    hashes = dict(terms.get("hash_binding_required") or {})
    return (
        terms.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cd_collection_gate_terms.v1"
        and terms.get("owner_gate_only") is True
        and terms.get("allowed_next_gate") == P9CE_GATE
        and terms.get("allowed_next_gate_scope") == P9CE_SCOPE
        and terms.get("allowed_next_gate_must_be_separately_requested") is True
        and terms.get("read_only_fresh_remote_proof_collection_may_be_requested_next")
        is True
        and terms.get("read_only_collection_execution_performed_in_p9cd") is False
        and terms.get("target_runner_identity_hint") == TARGET_RUNNER_IDENTITY_HINT
        and terms.get("target_deploy_root_hint") == TARGET_DEPLOY_ROOT_HINT
        and terms.get("target_runner_identity_proven_in_p9cd") is False
        and terms.get("target_deploy_root_proven_in_p9cd") is False
        and set(proof_rows) == set(EXPECTED_PROOFS)
        and all(
            int(proof_rows[key].get("max_age_seconds") or 0) == max_age
            and proof_rows[key].get("required") is True
            and proof_rows[key].get("point_in_time_safe_required") is True
            and proof_rows[key].get("collection_status_in_p9cd") == "not_collected"
            and proof_rows[key].get("future_collection_status")
            == "pending_separate_p9ce_request"
            and proof_rows[key].get("future_collection_channel") == "remote_read_only"
            for key, max_age in EXPECTED_PROOFS.items()
        )
        and set(terms.get("forbidden_future_actions_during_proof_collection") or [])
        == set(EXPECTED_FORBIDDEN_ACTIONS)
        and all(
            int(deltas.get(key) or 0) == 0
            for key in (
                "order_delta_must_equal",
                "cancel_delta_must_equal",
                "fill_delta_must_equal",
                "trade_delta_must_equal",
                "position_delta_must_equal",
                "balance_delta_must_equal",
            )
        )
        and staleness.get("missing_proof_fails_closed") is True
        and staleness.get("stale_proof_fails_closed") is True
        and staleness.get("future_timestamp_fails_closed") is True
        and staleness.get("future_fill_or_stale_fill_evidence_must_fail_closed")
        is True
        and hashes.get("candidate_target_plan_hash") is True
        and hashes.get("baseline_target_plan_hash") is True
        and hashes.get("baseline_candidate_distance_to_high_60_only_diff") is True
        and hashes.get("proof_artifact_manifest_hash") is True
        and terms.get("only_distance_to_high_60_contribution_changed") is True
        and int_zero(terms, "orders_submitted")
        and int_zero(terms, "orders_canceled")
        and int_zero(terms, "fill_count")
        and int_zero(terms, "trade_count")
    )


def p9cd_non_authorization_ready(matrix: dict[str, Any]) -> bool:
    authorizations = dict(matrix.get("authorizations") or {})
    return (
        matrix.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cd_non_authorization.v1"
        and authorizations.get("allow_future_p9ce_read_only_collection_gate_request")
        is True
        and authorizations.get("execute_read_only_fresh_remote_proof_collection_in_p9cd")
        is False
        and authorizations.get("fresh_remote_proof_collection") is False
        and authorizations.get("fresh_remote_account_read") is False
        and authorizations.get("fresh_order_book_read") is False
        and authorizations.get("exchange_filter_read") is False
        and authorizations.get("live_order_gate_approval") is False
        and authorizations.get("actual_candidate_executor_target_path_entry") is False
        and authorizations.get("candidate_execution") is False
        and authorizations.get("live_order_submission") is False
        and authorizations.get("actual_target_plan_replacement") is False
        and authorizations.get("actual_executor_input_mutation") is False
        and authorizations.get("live_config_mutation") is False
        and authorizations.get("operator_state_mutation") is False
        and authorizations.get("timer_or_service_mutation") is False
        and authorizations.get("timer_path_load") is False
        and authorizations.get("production_timer_service_load") is False
        and authorizations.get("supervisor_invocation") is False
        and authorizations.get("remote_sync") is False
        and authorizations.get("remote_execution") is False
        and authorizations.get("stage_governance_change") is False
    )


def p9cd_control_ready(control: dict[str, Any]) -> bool:
    return (
        control.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cd_control_boundary.v1"
        and control.get("scope") == "read_only_fresh_remote_proof_collection_owner_gate_only"
        and control.get("ssh_invoked") is False
        and control.get("remote_network_connection_performed") is False
        and control.get("fresh_remote_account_read_performed") is False
        and control.get("fresh_order_book_read_performed") is False
        and control.get("exchange_filter_read_performed") is False
        and control.get("fresh_proofs_collected") is False
        and control.get("entered_timer_path") is False
        and control.get("ran_supervisor") is False
        and control.get("remote_sync_performed") is False
        and control.get("remote_execution_performed") is False
        and control.get("candidate_execution_performed") is False
        and control.get("candidate_entered_actual_executor_target_plan_path")
        is False
        and control.get("live_order_submission_performed") is False
        and control.get("target_plan_replaced") is False
        and control.get("executor_input_changed") is False
        and control.get("live_config_changed") is False
        and control.get("operator_state_changed") is False
        and control.get("timer_state_changed") is False
        and int_zero(control, "orders_submitted")
        and int_zero(control, "orders_canceled")
        and int_zero(control, "fill_count")
        and int_zero(control, "trade_count")
    )


def remote_p9ce_collector_command(
    *,
    remote_repo: str,
    remote_live_env: str,
    remote_python: str,
    remote_config: str,
    expected_egress_ip: str,
    canary_symbol: str,
    max_history_symbols: int,
) -> str:
    return f"""
cd {shlex.quote(remote_repo)}
{shlex.quote(remote_live_env)} /usr/bin/env PYTHONNOUSERSITE=1 {shlex.quote(remote_python)} - <<'PY'
import hashlib
import hmac
import json
import os
import pathlib
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

FAPI = "https://fapi.binance.com"
SAPI = "https://api.binance.com"
EXPECTED_EGRESS_IP = {expected_egress_ip!r}
CONFIG_PATH = pathlib.Path({remote_config!r})
REPO_PATH = pathlib.Path({remote_repo!r})
CANARY_SYMBOL = {canary_symbol!r}
MAX_HISTORY_SYMBOLS = int({int(max_history_symbols)})

def iso_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def norm(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).strip()

def digest(payload):
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def sha(path):
    p = pathlib.Path(path)
    if not p.exists() or not p.is_file():
        return ""
    h = hashlib.sha256()
    with p.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def env_secret(name):
    return os.environ.get(name, "").strip()

def public_ip():
    try:
        with urllib.request.urlopen("https://api.ipify.org", timeout=15) as response:
            return response.read().decode("utf-8").strip()
    except Exception as exc:
        return "unavailable:" + type(exc).__name__

def get_json(url, *, headers=None):
    req = urllib.request.Request(
        url,
        headers=dict(headers or {{"User-Agent": "Meridian/P9CE-readonly-proof"}}),
        method="GET",
    )
    started = iso_now()
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            raw = response.read().decode("utf-8")
            payload = json.loads(raw) if raw else {{}}
            return {{
                "status": "ok",
                "status_code": int(response.status),
                "started_at_utc": started,
                "finished_at_utc": iso_now(),
                "payload": payload,
            }}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        return {{
            "status": "failed",
            "status_code": int(exc.code),
            "started_at_utc": started,
            "finished_at_utc": iso_now(),
            "error": body,
        }}
    except Exception as exc:
        return {{
            "status": "failed",
            "started_at_utc": started,
            "finished_at_utc": iso_now(),
            "error_type": type(exc).__name__,
            "error": str(exc)[:500],
        }}

def signed_get(base, path, *, params=None, api_key, api_secret):
    query_params = dict(params or {{}})
    query_params["recvWindow"] = "5000"
    query_params["timestamp"] = str(int(time.time() * 1000))
    query = urllib.parse.urlencode(query_params)
    sig = hmac.new(
        api_secret.encode("utf-8"),
        query.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    url = f"{{base.rstrip('/')}}{{path}}?{{query}}&signature={{sig}}"
    result = get_json(url, headers={{"X-MBX-APIKEY": api_key}})
    result["path"] = path
    result["method"] = "GET"
    result.pop("payload", None) if result.get("status") != "ok" else None
    if result.get("status") == "ok":
        result["payload"] = result.get("payload", {{}})
    return result

def public_get(base, path, *, params=None):
    query = urllib.parse.urlencode(dict(params or {{}}))
    url = f"{{base.rstrip('/')}}{{path}}" + (f"?{{query}}" if query else "")
    result = get_json(url)
    result["path"] = path
    result["method"] = "GET"
    return result

def payload(result, default):
    return result.get("payload", default) if result.get("status") == "ok" else default

def config_symbols():
    symbols = []
    try:
        lines = CONFIG_PATH.read_text(encoding="utf-8").splitlines()
    except Exception:
        return symbols
    in_symbols = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if stripped.startswith("symbols:"):
            raw = stripped.split(":", 1)[1].strip()
            in_symbols = not bool(raw)
            if raw:
                raw = raw.strip("[]")
                symbols.extend(item.strip().strip("'\\\"").upper() for item in raw.split(",") if item.strip())
            continue
        if in_symbols:
            if stripped.startswith("-"):
                symbols.append(stripped[1:].strip().strip("'\\\"").upper())
            elif stripped and not line.startswith((" ", "\\t")):
                in_symbols = False
    return sorted(set(item for item in symbols if item))

def stable_rows(rows, fields):
    normalized = []
    for row in list(rows or []):
        if not isinstance(row, dict):
            continue
        normalized.append({{field: norm(row.get(field)) for field in fields}})
    return sorted(normalized, key=lambda item: json.dumps(item, sort_keys=True))

def systemd(unit):
    keys = ["LoadState", "UnitFileState", "ActiveState", "SubState", "FragmentPath"]
    out = {{}}
    try:
        proc = subprocess.run(
            ["systemctl", "show", unit, "--no-pager"] + [f"-p{{key}}" for key in keys],
            text=True,
            capture_output=True,
            timeout=15,
        )
        out["returncode"] = proc.returncode
        for line in proc.stdout.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                out[key] = value
        if proc.stderr.strip():
            out["stderr_tail"] = proc.stderr.strip()[-500:]
    except Exception as exc:
        out = {{"error_type": type(exc).__name__, "error": str(exc)[:500]}}
    return out

def operator_state_readback():
    sqlite_path = REPO_PATH / "artifacts/live_trading/hv_balanced_binance_usdm_live_2x_full_balance_candidate/state/live_trading.sqlite3"
    state = {{}}
    if sqlite_path.exists():
        try:
            with sqlite3.connect(str(sqlite_path)) as conn:
                rows = conn.execute("SELECT key, value, updated_at_utc FROM operator_state ORDER BY key").fetchall()
            state = {{str(k): {{"value": str(v), "updated_at_utc": str(t)}} for k, v, t in rows}}
        except Exception as exc:
            state = {{"_error_type": type(exc).__name__, "_error": str(exc)[:500]}}
    units = [
        "meridian-alpha-mainnet-supervisor-live.timer",
        "meridian-alpha-mainnet-supervisor-live.service",
        "meridian-alpha-mainnet-health-monitor.timer",
        "meridian-alpha-mainnet-health-monitor.service",
    ]
    return {{
        "sqlite_path": str(sqlite_path),
        "operator_state": state,
        "systemd_units": {{unit: systemd(unit) for unit in units}},
    }}

def build_account_snapshot(endpoint_results, egress_ip):
    account = payload(endpoint_results.get("account", {{}}), {{}})
    account_config = payload(endpoint_results.get("account_config", {{}}), {{}})
    position_mode_payload = payload(endpoint_results.get("position_mode", {{}}), {{}})
    open_orders = payload(endpoint_results.get("open_orders", {{}}), [])
    api_restrictions = payload(endpoint_results.get("api_restrictions", {{}}), {{}})
    dual_side = position_mode_payload.get("dualSidePosition")
    position_mode = "hedge" if dual_side is True else "one_way" if dual_side is False else None
    positions = [row for row in list(account.get("positions") or []) if isinstance(row, dict)]
    position_fields = [
        "symbol",
        "positionSide",
        "positionAmt",
        "entryPrice",
        "breakEvenPrice",
        "isolated",
        "isolatedWallet",
    ]
    position_rows = []
    for row in positions:
        try:
            amount = float(row.get("positionAmt") or 0.0)
        except Exception:
            amount = 0.0
        if abs(amount) > 1e-12:
            position_rows.append({{field: norm(row.get(field)) for field in position_fields}})
    position_rows = sorted(position_rows, key=lambda item: (item.get("symbol", ""), item.get("positionSide", "")))
    balance_fields = ["asset", "walletBalance", "crossWalletBalance"]
    balances = stable_rows(account.get("assets") or [], balance_fields)
    order_fields = [
        "symbol",
        "orderId",
        "clientOrderId",
        "status",
        "side",
        "positionSide",
        "type",
        "origQty",
        "executedQty",
        "updateTime",
        "time",
    ]
    open_order_rows = stable_rows(open_orders, order_fields)
    blockers = []
    if egress_ip != EXPECTED_EGRESS_IP:
        blockers.append(f"egress_ip_mismatch:expected={{EXPECTED_EGRESS_IP}}:actual={{egress_ip}}")
    if not account:
        blockers.append("account_read_missing")
    future_live_order_readiness_blockers = []
    if account.get("canTrade") is not True:
        future_live_order_readiness_blockers.append("account_can_trade_false_or_missing")
    if position_mode != "one_way":
        blockers.append(f"position_mode_mismatch:expected=one_way:actual={{position_mode}}")
    if len(open_order_rows) != 0:
        blockers.append(f"mainnet_open_orders_exist:{{len(open_order_rows)}}")
    return {{
        "account_readable": bool(account),
        "can_trade": account.get("canTrade") is True,
        "position_mode": position_mode,
        "open_order_count": len(open_order_rows),
        "open_position_count": len(position_rows),
        "egress_ip": egress_ip,
        "expected_egress_ip": EXPECTED_EGRESS_IP,
        "account_config": {{
            "dual_side_position": dual_side,
            "fee_tier": account_config.get("feeTier"),
            "multi_assets_margin": account_config.get("multiAssetsMargin"),
            "trade_group_id": account_config.get("tradeGroupId"),
        }},
        "api_restrictions_summary": {{
            "ip_restrict": api_restrictions.get("ipRestrict"),
            "enable_futures": api_restrictions.get("enableFutures"),
            "enable_reading": api_restrictions.get("enableReading"),
            "enable_withdrawals": api_restrictions.get("enableWithdrawals"),
            "permits_universal_transfer": api_restrictions.get("permitsUniversalTransfer"),
        }},
        "blockers": sorted(set(blockers)),
        "future_live_order_readiness_blockers": sorted(set(future_live_order_readiness_blockers)),
        "position_fingerprint": {{
            "stable_fields": position_fields,
            "stable_rows": position_rows,
            "stable_hash": digest(position_rows),
        }},
        "open_order_fingerprint": {{
            "stable_fields": order_fields,
            "stable_rows": open_order_rows,
            "stable_hash": digest(open_order_rows),
        }},
        "balance_fingerprint": {{
            "stable_fields": balance_fields,
            "stable_rows": balances,
            "stable_hash": digest(balances),
        }},
    }}

def collect_account_side(label, api_key, api_secret):
    endpoint_results = {{
        "account": signed_get(FAPI, "/fapi/v3/account", api_key=api_key, api_secret=api_secret),
        "account_config": signed_get(FAPI, "/fapi/v1/accountConfig", api_key=api_key, api_secret=api_secret),
        "position_mode": signed_get(FAPI, "/fapi/v1/positionSide/dual", api_key=api_key, api_secret=api_secret),
        "open_orders": signed_get(FAPI, "/fapi/v1/openOrders", api_key=api_key, api_secret=api_secret),
        "api_restrictions": signed_get(SAPI, "/sapi/v1/account/apiRestrictions", api_key=api_key, api_secret=api_secret),
    }}
    blockers = []
    for name, item in endpoint_results.items():
        if item.get("status") != "ok":
            blockers.append(f"read_only_endpoint_failed:{{name}}:{{item.get('status_code', item.get('error_type', 'unknown'))}}")
    egress_ip = public_ip()
    snapshot = build_account_snapshot(endpoint_results, egress_ip)
    blockers.extend(snapshot["blockers"])
    snapshot["label"] = label
    snapshot["endpoint_results"] = {{
        name: {{
            "path": item.get("path"),
            "method": item.get("method"),
            "status": item.get("status"),
            "status_code": item.get("status_code"),
            "started_at_utc": item.get("started_at_utc"),
            "finished_at_utc": item.get("finished_at_utc"),
            "error_type": item.get("error_type"),
            "error": item.get("error"),
        }}
        for name, item in endpoint_results.items()
    }}
    snapshot["started_at_utc"] = min(
        [item.get("started_at_utc") for item in endpoint_results.values() if item.get("started_at_utc")]
        or [iso_now()]
    )
    snapshot["finished_at_utc"] = iso_now()
    snapshot["status"] = "ready" if not blockers else "blocked"
    snapshot["blockers"] = sorted(set(blockers))
    return snapshot

def collect_history_fingerprint(proof_symbols, api_key, api_secret):
    order_fields = ["symbol", "orderId", "clientOrderId", "status", "side", "positionSide", "type", "origQty", "executedQty", "updateTime", "time"]
    trade_fields = ["symbol", "id", "orderId", "side", "positionSide", "qty", "price", "realizedPnl", "commission", "time"]
    order_history = {{}}
    trade_history = {{}}
    endpoint_results = []
    blockers = []
    for symbol in proof_symbols[:MAX_HISTORY_SYMBOLS]:
        orders = signed_get(FAPI, "/fapi/v1/allOrders", params={{"symbol": symbol, "limit": "10"}}, api_key=api_key, api_secret=api_secret)
        trades = signed_get(FAPI, "/fapi/v1/userTrades", params={{"symbol": symbol, "limit": "10"}}, api_key=api_key, api_secret=api_secret)
        endpoint_results.append({{"symbol": symbol, "endpoint": "allOrders", "status": orders.get("status"), "status_code": orders.get("status_code"), "error_type": orders.get("error_type"), "error": orders.get("error")}})
        endpoint_results.append({{"symbol": symbol, "endpoint": "userTrades", "status": trades.get("status"), "status_code": trades.get("status_code"), "error_type": trades.get("error_type"), "error": trades.get("error")}})
        if orders.get("status") != "ok":
            blockers.append(f"read_only_endpoint_failed:allOrders:{{symbol}}:{{orders.get('status_code', orders.get('error_type', 'unknown'))}}")
        if trades.get("status") != "ok":
            blockers.append(f"read_only_endpoint_failed:userTrades:{{symbol}}:{{trades.get('status_code', trades.get('error_type', 'unknown'))}}")
        order_history[symbol] = stable_rows(payload(orders, []), order_fields)
        trade_history[symbol] = stable_rows(payload(trades, []), trade_fields)
    return {{
        "status": "ready" if not blockers else "blocked",
        "blockers": sorted(set(blockers)),
        "started_at_utc": iso_now(),
        "finished_at_utc": iso_now(),
        "proof_symbols": proof_symbols[:MAX_HISTORY_SYMBOLS],
        "history_symbol_count": len(proof_symbols[:MAX_HISTORY_SYMBOLS]),
        "order_history_fingerprint": {{
            "stable_fields": order_fields,
            "history": order_history,
            "history_hash": digest(order_history),
        }},
        "trade_history_fingerprint": {{
            "stable_fields": trade_fields,
            "history": trade_history,
            "history_hash": digest(trade_history),
        }},
        "endpoint_results": endpoint_results,
    }}

def collect_public_reads(proof_symbols):
    depth = public_get(FAPI, "/fapi/v1/depth", params={{"symbol": CANARY_SYMBOL, "limit": "5"}})
    exchange = public_get(FAPI, "/fapi/v1/exchangeInfo")
    blockers = []
    if depth.get("status") != "ok":
        blockers.append(f"read_only_endpoint_failed:depth:{{depth.get('status_code', depth.get('error_type', 'unknown'))}}")
    if exchange.get("status") != "ok":
        blockers.append(f"read_only_endpoint_failed:exchangeInfo:{{exchange.get('status_code', exchange.get('error_type', 'unknown'))}}")
    depth_payload = payload(depth, {{}})
    bids = depth_payload.get("bids") or []
    asks = depth_payload.get("asks") or []
    book_rows = {{
        "symbol": CANARY_SYMBOL,
        "last_update_id": depth_payload.get("lastUpdateId"),
        "best_bid": bids[0] if bids else [],
        "best_ask": asks[0] if asks else [],
        "top_bids": bids[:5],
        "top_asks": asks[:5],
    }}
    exchange_payload = payload(exchange, {{}})
    symbols = []
    proof_set = set(proof_symbols) | {{CANARY_SYMBOL}}
    for row in list(exchange_payload.get("symbols") or []):
        if not isinstance(row, dict) or row.get("symbol") not in proof_set:
            continue
        symbols.append({{
            "symbol": row.get("symbol"),
            "status": row.get("status"),
            "contractType": row.get("contractType"),
            "pricePrecision": row.get("pricePrecision"),
            "quantityPrecision": row.get("quantityPrecision"),
            "filters": row.get("filters") or [],
        }})
    symbols = sorted(symbols, key=lambda item: item.get("symbol") or "")
    return {{
        "status": "ready" if not blockers else "blocked",
        "blockers": sorted(set(blockers)),
        "fresh_order_book": {{
            "status": "ready" if depth.get("status") == "ok" else "blocked",
            "symbol": CANARY_SYMBOL,
            "started_at_utc": depth.get("started_at_utc"),
            "finished_at_utc": depth.get("finished_at_utc"),
            "book": book_rows,
            "book_hash": digest(book_rows),
            "endpoint": "/fapi/v1/depth",
            "method": "GET",
        }},
        "exchange_filter_readback": {{
            "status": "ready" if exchange.get("status") == "ok" else "blocked",
            "started_at_utc": exchange.get("started_at_utc"),
            "finished_at_utc": exchange.get("finished_at_utc"),
            "symbols": symbols,
            "symbol_count": len(symbols),
            "filters_hash": digest(symbols),
            "endpoint": "/fapi/v1/exchangeInfo",
            "method": "GET",
        }},
    }}

started_at = iso_now()
blockers = []
api_key = env_secret("Trade")
api_secret = env_secret("Secret_Key")
if not api_key:
    blockers.append("missing_api_key_env:Trade")
if not api_secret:
    blockers.append("missing_api_secret_env:Secret_Key")

remote_identity = {{
    "started_at_utc": started_at,
    "whoami": "",
    "hostname": "",
    "cwd": str(pathlib.Path.cwd()),
    "repo_path": str(REPO_PATH),
    "config_path": str(CONFIG_PATH),
    "python_executable": sys.executable,
    "python_version": sys.version.split()[0],
    "egress_ip": public_ip(),
    "config_sha256": sha(CONFIG_PATH),
    "live_supervisor_sha256": sha(REPO_PATH / "src/enhengclaw/live_trading/mainnet_live_supervisor.py"),
    "hook_sha256": sha(REPO_PATH / "src/enhengclaw/live_trading/dth60_observe_only_shadow_hook.py"),
}}
try:
    remote_identity["whoami"] = subprocess.check_output(["whoami"], text=True, timeout=10).strip()
except Exception as exc:
    remote_identity["whoami_error"] = type(exc).__name__ + ":" + str(exc)[:200]
try:
    remote_identity["hostname"] = subprocess.check_output(["hostname"], text=True, timeout=10).strip()
except Exception as exc:
    remote_identity["hostname_error"] = type(exc).__name__ + ":" + str(exc)[:200]

pre_account = {{}}
post_account = {{}}
pre_history = {{}}
post_history = {{}}
public_reads = {{}}
operator_control = operator_state_readback()
if not blockers:
    pre_account = collect_account_side("pre", api_key, api_secret)
    proof_symbols = sorted(
        set(config_symbols())
        | set(row.get("symbol", "") for row in pre_account.get("position_fingerprint", {{}}).get("stable_rows", []) if row.get("symbol"))
        | {{CANARY_SYMBOL}}
    )
    pre_history = collect_history_fingerprint(proof_symbols, api_key, api_secret)
    public_reads = collect_public_reads(proof_symbols)
    post_account = collect_account_side("post", api_key, api_secret)
    post_history = collect_history_fingerprint(proof_symbols, api_key, api_secret)

for source in (pre_account, post_account, pre_history, post_history, public_reads):
    blockers.extend(list(source.get("blockers") or []))

side_effects = {{
    "orders_submitted": 0,
    "orders_canceled": 0,
    "order_test_calls": 0,
    "http_methods_used": ["GET"],
    "only_http_get_endpoints": True,
    "remote_files_written": 0,
    "remote_sync_performed": False,
    "supervisor_invoked": False,
    "timer_path_invoked": False,
    "candidate_executed": False,
    "executor_input_mutated": False,
    "target_plan_replaced": False,
}}

position_stable = (
    pre_account.get("position_fingerprint", {{}}).get("stable_hash")
    == post_account.get("position_fingerprint", {{}}).get("stable_hash")
    and pre_account.get("position_fingerprint", {{}}).get("stable_rows")
    == post_account.get("position_fingerprint", {{}}).get("stable_rows")
)
open_order_stable = (
    pre_account.get("open_order_fingerprint", {{}}).get("stable_hash")
    == post_account.get("open_order_fingerprint", {{}}).get("stable_hash")
    and pre_account.get("open_order_fingerprint", {{}}).get("stable_rows")
    == post_account.get("open_order_fingerprint", {{}}).get("stable_rows")
)
balance_stable = (
    pre_account.get("balance_fingerprint", {{}}).get("stable_hash")
    == post_account.get("balance_fingerprint", {{}}).get("stable_hash")
    and pre_account.get("balance_fingerprint", {{}}).get("stable_rows")
    == post_account.get("balance_fingerprint", {{}}).get("stable_rows")
)
fill_trade_stable = (
    pre_history.get("order_history_fingerprint", {{}}).get("history_hash")
    == post_history.get("order_history_fingerprint", {{}}).get("history_hash")
    and pre_history.get("trade_history_fingerprint", {{}}).get("history_hash")
    == post_history.get("trade_history_fingerprint", {{}}).get("history_hash")
)
if pre_account and not position_stable:
    blockers.append("position_fingerprint_changed")
if pre_account and not open_order_stable:
    blockers.append("open_order_fingerprint_changed")
if pre_account and not balance_stable:
    blockers.append("balance_fingerprint_changed")
if pre_history and not fill_trade_stable:
    blockers.append("fill_trade_fingerprint_changed")

finished_at = iso_now()
summary = {{
    "contract_version": "hv_balanced_dth60_coinglass_phase9ce_remote_stdout_collector.v1",
    "started_at_utc": started_at,
    "finished_at_utc": finished_at,
    "status": "ready" if not blockers else "blocked",
    "blockers": sorted(set(blockers)),
    "remote_runner_identity_readback": remote_identity,
    "fresh_remote_account_read": {{
        "status": "ready" if pre_account and post_account and not pre_account.get("blockers") and not post_account.get("blockers") else "blocked",
        "pre": {{
            "started_at_utc": pre_account.get("started_at_utc"),
            "finished_at_utc": pre_account.get("finished_at_utc"),
            "account_readable": pre_account.get("account_readable"),
            "can_trade": pre_account.get("can_trade"),
            "position_mode": pre_account.get("position_mode"),
            "open_order_count": pre_account.get("open_order_count"),
            "open_position_count": pre_account.get("open_position_count"),
            "egress_ip": pre_account.get("egress_ip"),
            "expected_egress_ip": pre_account.get("expected_egress_ip"),
            "account_config": pre_account.get("account_config"),
            "api_restrictions_summary": pre_account.get("api_restrictions_summary"),
            "future_live_order_readiness_blockers": pre_account.get("future_live_order_readiness_blockers"),
            "endpoint_results": pre_account.get("endpoint_results"),
        }},
        "post": {{
            "started_at_utc": post_account.get("started_at_utc"),
            "finished_at_utc": post_account.get("finished_at_utc"),
            "account_readable": post_account.get("account_readable"),
            "can_trade": post_account.get("can_trade"),
            "position_mode": post_account.get("position_mode"),
            "open_order_count": post_account.get("open_order_count"),
            "open_position_count": post_account.get("open_position_count"),
            "egress_ip": post_account.get("egress_ip"),
            "expected_egress_ip": post_account.get("expected_egress_ip"),
            "account_config": post_account.get("account_config"),
            "api_restrictions_summary": post_account.get("api_restrictions_summary"),
            "future_live_order_readiness_blockers": post_account.get("future_live_order_readiness_blockers"),
            "endpoint_results": post_account.get("endpoint_results"),
        }},
        "side_effects": side_effects,
    }},
    "pre_position_fingerprint": pre_account.get("position_fingerprint", {{}}),
    "post_position_fingerprint": post_account.get("position_fingerprint", {{}}),
    "pre_open_order_fingerprint": pre_account.get("open_order_fingerprint", {{}}),
    "post_open_order_fingerprint": post_account.get("open_order_fingerprint", {{}}),
    "pre_balance_fingerprint": pre_account.get("balance_fingerprint", {{}}),
    "post_balance_fingerprint": post_account.get("balance_fingerprint", {{}}),
    "pre_fill_trade_fingerprint": {{
        "order_history_fingerprint": pre_history.get("order_history_fingerprint", {{}}),
        "trade_history_fingerprint": pre_history.get("trade_history_fingerprint", {{}}),
        "endpoint_results": pre_history.get("endpoint_results", []),
    }},
    "post_fill_trade_fingerprint": {{
        "order_history_fingerprint": post_history.get("order_history_fingerprint", {{}}),
        "trade_history_fingerprint": post_history.get("trade_history_fingerprint", {{}}),
        "endpoint_results": post_history.get("endpoint_results", []),
    }},
    "fresh_order_book": public_reads.get("fresh_order_book", {{}}),
    "exchange_filter_readback": public_reads.get("exchange_filter_readback", {{}}),
    "operator_control_readback": operator_control,
    "fingerprint_stability": {{
        "position_fingerprint_stable": position_stable,
        "open_order_fingerprint_stable": open_order_stable,
        "balance_fingerprint_stable": balance_stable,
        "fill_trade_fingerprint_stable": fill_trade_stable,
    }},
    "side_effects": side_effects,
}}
print(json.dumps(summary, indent=2, sort_keys=True))
PY
"""


def side_effects_zero(payload: dict[str, Any]) -> bool:
    side_effects = dict(payload.get("side_effects") or {})
    return (
        side_effects.get("orders_submitted") == 0
        and side_effects.get("orders_canceled") == 0
        and side_effects.get("order_test_calls") == 0
        and side_effects.get("only_http_get_endpoints") is True
        and side_effects.get("remote_files_written") == 0
        and side_effects.get("remote_sync_performed") is False
        and side_effects.get("supervisor_invoked") is False
        and side_effects.get("timer_path_invoked") is False
        and side_effects.get("candidate_executed") is False
        and side_effects.get("executor_input_mutated") is False
        and side_effects.get("target_plan_replaced") is False
    )


def remote_account_read_ready(account: dict[str, Any]) -> bool:
    pre = dict(account.get("pre") or {})
    post = dict(account.get("post") or {})
    return (
        account.get("status") == "ready"
        and pre.get("account_readable") is True
        and post.get("account_readable") is True
        and pre.get("position_mode") == "one_way"
        and post.get("position_mode") == "one_way"
        and int(pre.get("open_order_count") or 0) == 0
        and int(post.get("open_order_count") or 0) == 0
        and pre.get("egress_ip") == pre.get("expected_egress_ip")
        and post.get("egress_ip") == post.get("expected_egress_ip")
        and side_effects_zero(account)
    )


def fingerprint_hash(payload: dict[str, Any], *keys: str) -> str:
    item: Any = payload
    for key in keys:
        item = dict(item or {}).get(key)
    return str(item or "")


def collector_ready(collector: dict[str, Any]) -> bool:
    stability = dict(collector.get("fingerprint_stability") or {})
    return (
        collector.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9ce_remote_stdout_collector.v1"
        and collector.get("status") == "ready"
        and not collector.get("blockers")
        and remote_account_read_ready(dict(collector.get("fresh_remote_account_read") or {}))
        and dict(collector.get("fresh_order_book") or {}).get("status") == "ready"
        and dict(collector.get("exchange_filter_readback") or {}).get("status")
        == "ready"
        and stability.get("position_fingerprint_stable") is True
        and stability.get("open_order_fingerprint_stable") is True
        and stability.get("balance_fingerprint_stable") is True
        and stability.get("fill_trade_fingerprint_stable") is True
        and side_effects_zero(collector)
        and bool(
            fingerprint_hash(collector, "pre_position_fingerprint", "stable_hash")
        )
        and bool(
            fingerprint_hash(collector, "pre_open_order_fingerprint", "stable_hash")
        )
        and bool(
            fingerprint_hash(
                collector,
                "pre_fill_trade_fingerprint",
                "order_history_fingerprint",
                "history_hash",
            )
        )
        and bool(
            fingerprint_hash(
                collector,
                "pre_fill_trade_fingerprint",
                "trade_history_fingerprint",
                "history_hash",
            )
        )
    )


def remote_identity_ready(
    identity: dict[str, Any],
    *,
    remote_host: str,
    remote_repo: str,
    remote_config: str,
    expected_egress_ip: str,
) -> bool:
    return (
        remote_host == TARGET_RUNNER_IDENTITY_HINT
        and identity.get("whoami") == "root"
        and identity.get("repo_path") == remote_repo
        and identity.get("config_path") == remote_config
        and identity.get("egress_ip") == expected_egress_ip
        and bool(identity.get("config_sha256"))
        and bool(identity.get("live_supervisor_sha256"))
    )


def fingerprint_delta_acceptance(collector: dict[str, Any]) -> dict[str, Any]:
    pre_account = dict(
        dict(collector.get("fresh_remote_account_read") or {}).get("pre") or {}
    )
    post_account = dict(
        dict(collector.get("fresh_remote_account_read") or {}).get("post") or {}
    )
    stability = dict(collector.get("fingerprint_stability") or {})
    order_history_pre = fingerprint_hash(
        collector,
        "pre_fill_trade_fingerprint",
        "order_history_fingerprint",
        "history_hash",
    )
    order_history_post = fingerprint_hash(
        collector,
        "post_fill_trade_fingerprint",
        "order_history_fingerprint",
        "history_hash",
    )
    trade_history_pre = fingerprint_hash(
        collector,
        "pre_fill_trade_fingerprint",
        "trade_history_fingerprint",
        "history_hash",
    )
    trade_history_post = fingerprint_hash(
        collector,
        "post_fill_trade_fingerprint",
        "trade_history_fingerprint",
        "history_hash",
    )
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ce_delta_acceptance.v1",
        "position_fingerprint_stable": stability.get("position_fingerprint_stable")
        is True,
        "open_order_fingerprint_stable": stability.get("open_order_fingerprint_stable")
        is True,
        "balance_fingerprint_stable": stability.get("balance_fingerprint_stable")
        is True,
        "fill_trade_fingerprint_stable": stability.get("fill_trade_fingerprint_stable")
        is True,
        "open_order_count_pre": int(pre_account.get("open_order_count") or 0),
        "open_order_count_post": int(post_account.get("open_order_count") or 0),
        "open_position_count_pre": int(pre_account.get("open_position_count") or 0),
        "open_position_count_post": int(post_account.get("open_position_count") or 0),
        "order_history_hash_pre": order_history_pre,
        "order_history_hash_post": order_history_post,
        "trade_history_hash_pre": trade_history_pre,
        "trade_history_hash_post": trade_history_post,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
        "order_cancel_fill_trade_delta_zero": (
            stability.get("open_order_fingerprint_stable") is True
            and stability.get("fill_trade_fingerprint_stable") is True
            and order_history_pre == order_history_post
            and trade_history_pre == trade_history_post
        ),
        "position_delta_zero_or_stable": stability.get("position_fingerprint_stable")
        is True,
        "balance_delta_zero_or_stable": stability.get("balance_fingerprint_stable")
        is True,
    }


def write_proof_manifest(proof_root: Path, files: dict[str, Path]) -> dict[str, Any]:
    entries = {
        key: evidence_file(path)
        for key, path in sorted(files.items())
        if path.name != "proof_artifact_manifest.json"
    }
    manifest = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ce_proof_manifest.v1",
        "artifact_count": len(entries),
        "artifacts": entries,
    }
    manifest_path = proof_root / "proof_artifact_manifest.json"
    write_json(manifest_path, manifest)
    manifest["self"] = evidence_file(manifest_path)
    write_json(manifest_path, manifest)
    return manifest


def owner_decision_record(args: argparse.Namespace, now: datetime) -> dict[str, Any]:
    approved = str(args.owner_decision) == APPROVE_P9CE_DECISION
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ce_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "execute_read_only_fresh_remote_proof_collection_only",
        "decision_effect": "execute_p9ce_read_only_collection" if approved else "none",
        "recorded_at_utc": iso_z(now),
        "p9ce_read_only_fresh_remote_proof_collection_approved": approved,
        "remote_read_only_account_and_market_data_collection_approved": approved,
        "remote_files_written_approved": False,
        "remote_sync_approved": False,
        "supervisor_invocation_approved": False,
        "timer_path_load_approved": False,
        "candidate_execution_approved": False,
        "target_plan_replacement_approved": False,
        "executor_input_mutation_approved": False,
        "live_order_submission_approved": False,
    }


def build_phase9ce(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
    command_runner: CommandRunner = local_command_runner,
) -> tuple[dict[str, Any], int]:
    started_at = now_fn()
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9ce" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    p9cd_path = latest_p9cd_summary(args)
    p9cd = load_optional(p9cd_path)
    terms_path = source_output_path(p9cd, "read_only_collection_gate_terms")
    non_auth_path = source_output_path(p9cd, "non_authorization")
    control_path = source_output_path(p9cd, "control_boundary_readback")
    terms = load_optional(terms_path)
    p9cd_matrix = load_optional(non_auth_path)
    p9cd_control = load_optional(control_path)
    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)
    owner_record = owner_decision_record(args, started_at)
    write_json(root / "owner_decision_record.json", owner_record)

    pre_checks = {
        "owner_decision_p9ce_execute_read_only_recorded": str(args.owner_decision)
        == APPROVE_P9CE_DECISION,
        "project_profile_exists": bool(project_profile),
        "current_stage_is_stage3": str(project_profile.get("current_stage") or "")
        == "stage_3_human_approved_execution",
        "p9cd_summary_exists": bool(p9cd),
        "p9cd_summary_ready_for_p9ce": p9cd_summary_ready(p9cd),
        "p9cd_terms_ready_for_read_only_collection": p9cd_terms_ready(terms),
        "p9cd_non_authorization_ready": p9cd_non_authorization_ready(p9cd_matrix),
        "p9cd_control_boundary_ready": p9cd_control_ready(p9cd_control),
        "remote_host_matches_p9cd_hint": str(args.remote_host)
        == TARGET_RUNNER_IDENTITY_HINT,
        "remote_repo_matches_p9cd_hint": str(args.remote_repo)
        == TARGET_DEPLOY_ROOT_HINT,
        "canary_symbol_matches_p9cd": str(args.canary_symbol) == CANARY_SYMBOL,
    }
    blockers = [key for key, value in pre_checks.items() if not value]
    command_records: list[dict[str, Any]] = []
    pre_snapshot: dict[str, Any] = {}
    post_snapshot: dict[str, Any] = {}
    collector: dict[str, Any] = {}

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

    if not blockers:
        pre_result = run_record(
            "pre_control_snapshot",
            ssh_args(
                args.remote_host,
                args.ssh_connect_timeout,
                remote_snapshot_script(args.remote_repo, args.remote_config),
            ),
        )
        pre_snapshot = json_from_command(pre_result)
        write_json(root / "pre_control_snapshot.json", pre_snapshot)
        if pre_result.returncode != 0:
            blockers.append("pre_control_snapshot_failed")

    if not blockers:
        collector_result = run_record(
            "remote_stdout_read_only_collector",
            ssh_args(
                args.remote_host,
                args.ssh_connect_timeout,
                remote_p9ce_collector_command(
                    remote_repo=args.remote_repo,
                    remote_live_env=args.remote_live_env,
                    remote_python=args.remote_python,
                    remote_config=args.remote_config,
                    expected_egress_ip=args.expected_egress_ip,
                    canary_symbol=args.canary_symbol,
                    max_history_symbols=int(args.max_history_symbols or 0),
                ),
            ),
        )
        collector = json_from_command(collector_result)
        write_json(root / "remote_stdout_collector_raw.json", collector)
        if collector_result.returncode != 0:
            blockers.append("remote_stdout_read_only_collector_failed")
        if not collector_ready(collector):
            blockers.append("remote_stdout_collector_not_ready")

    if pre_snapshot:
        post_result = run_record(
            "post_control_snapshot",
            ssh_args(
                args.remote_host,
                args.ssh_connect_timeout,
                remote_snapshot_script(args.remote_repo, args.remote_config),
            ),
        )
        post_snapshot = json_from_command(post_result)
        write_json(root / "post_control_snapshot.json", post_snapshot)
        if post_result.returncode != 0:
            blockers.append("post_control_snapshot_failed")
        if not snapshot_boundary_ok(pre_snapshot, post_snapshot):
            blockers.append("remote_control_boundary_changed")

    delta = fingerprint_delta_acceptance(collector) if collector else {}
    if collector and not dict(delta).get("order_cancel_fill_trade_delta_zero"):
        blockers.append("order_cancel_fill_trade_delta_not_zero_or_unproven")
    if collector and not dict(delta).get("position_delta_zero_or_stable"):
        blockers.append("position_delta_not_zero_or_unstable")
    if collector and not dict(delta).get("balance_delta_zero_or_stable"):
        blockers.append("balance_delta_not_zero_or_unstable")

    identity = dict(collector.get("remote_runner_identity_readback") or {})
    if collector and not remote_identity_ready(
        identity,
        remote_host=args.remote_host,
        remote_repo=args.remote_repo,
        remote_config=args.remote_config,
        expected_egress_ip=args.expected_egress_ip,
    ):
        blockers.append("remote_runner_identity_readback_not_ready")

    fresh_account = dict(collector.get("fresh_remote_account_read") or {})
    future_live_order_readiness_blockers = sorted(
        set(
            list(dict(fresh_account.get("pre") or {}).get("future_live_order_readiness_blockers") or [])
            + list(dict(fresh_account.get("post") or {}).get("future_live_order_readiness_blockers") or [])
        )
    )
    fresh_book = dict(collector.get("fresh_order_book") or {})
    filters = dict(collector.get("exchange_filter_readback") or {})
    operator_control = dict(collector.get("operator_control_readback") or {})
    p9bu_acceptance = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ce_p9bu_terms_operator_acceptance.v1",
        "source_p9cd_terms": evidence_file(terms_path),
        "risk_ceiling_usdt": p9cd.get("risk_ceiling_usdt"),
        "max_notional_usdt": p9cd.get("max_notional_usdt"),
        "max_orders_per_cycle": p9cd.get("max_orders_per_cycle"),
        "max_symbols_per_cycle": p9cd.get("max_symbols_per_cycle"),
        "order_type": p9cd.get("order_type"),
        "time_in_force": p9cd.get("time_in_force"),
        "market_orders_allowed": p9cd.get("market_orders_allowed"),
        "final_owner_live_order_gate_approval": False,
        "live_order_gate_approved": False,
        "candidate_execution_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
    }
    hash_binding = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ce_target_plan_hash_binding.v1",
        "baseline_target_plan_sha256": p9cd.get("baseline_target_plan_sha256"),
        "candidate_target_plan_sha256": p9cd.get("candidate_target_plan_sha256"),
        "candidate_not_in_executor_path": True,
        "executor_input_remains_baseline_only": True,
        "target_plan_replacement_performed": False,
    }
    plan_diff = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ce_baseline_candidate_plan_diff.v1",
        "only_distance_to_high_60_contribution_changed": p9cd.get(
            "only_distance_to_high_60_contribution_changed"
        )
        is True,
        "baseline_target_plan_sha256": p9cd.get("baseline_target_plan_sha256"),
        "candidate_target_plan_sha256": p9cd.get("candidate_target_plan_sha256"),
        "executor_consumes_baseline_only": True,
        "candidate_shadow_only": True,
    }
    kill_switch = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ce_kill_switch_readback.v1",
        "operator_control_readback": operator_control,
        "pre_control_snapshot": evidence_file(root / "pre_control_snapshot.json"),
        "post_control_snapshot": evidence_file(root / "post_control_snapshot.json"),
        "remote_control_boundary_unchanged": bool(pre_snapshot and post_snapshot)
        and snapshot_boundary_ok(pre_snapshot, post_snapshot),
        "kill_switch_or_operator_state_mutated_by_p9ce": False,
    }
    rollback = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ce_rollback_command_readback.v1",
        "rollback_context": "no live mutation performed; rollback is no-op for P9CE",
        "remote_sync_performed": False,
        "remote_files_written": 0,
        "supervisor_invoked": False,
        "timer_path_invoked": False,
        "candidate_executed": False,
        "executor_input_mutated": False,
        "target_plan_replaced": False,
    }
    non_auth = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ce_non_authorization.v1",
        "authorizations": {
            "p9ce_read_only_fresh_remote_proof_collection": str(args.owner_decision)
            == APPROVE_P9CE_DECISION,
            "remote_stdout_read_only_collection": str(args.owner_decision)
            == APPROVE_P9CE_DECISION,
            "remote_files_written": False,
            "remote_sync": False,
            "supervisor_invocation": False,
            "timer_path_load": False,
            "production_timer_service_load": False,
            "candidate_execution": False,
            "live_order_submission": False,
            "target_plan_replacement": False,
            "executor_input_mutation": False,
            "live_config_mutation": False,
            "operator_state_mutation": False,
            "timer_or_service_mutation": False,
            "stage_governance_change": False,
        },
    }
    control = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ce_control_boundary.v1",
        "scope": "read_only_fresh_remote_proof_collection_stdout_only",
        "ssh_invoked": bool(command_records),
        "remote_network_connection_performed": bool(collector),
        "remote_files_written": 0,
        "remote_sync_performed": False,
        "fresh_remote_account_read_performed": bool(fresh_account),
        "fresh_order_book_read_performed": bool(fresh_book),
        "exchange_filter_read_performed": bool(filters),
        "entered_timer_path": False,
        "ran_supervisor": False,
        "candidate_execution_performed": False,
        "candidate_entered_actual_executor_target_plan_path": False,
        "live_order_submission_performed": False,
        "target_plan_replaced": False,
        "executor_input_changed": False,
        "live_config_changed": bool(pre_snapshot and post_snapshot)
        and pre_snapshot.get("remote_live_config_sha256")
        != post_snapshot.get("remote_live_config_sha256"),
        "operator_state_changed": bool(pre_snapshot and post_snapshot)
        and pre_snapshot.get("operator_state") != post_snapshot.get("operator_state"),
        "timer_state_changed": bool(pre_snapshot and post_snapshot)
        and timer_state_digest(pre_snapshot) != timer_state_digest(post_snapshot),
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
    }

    proof_files = {
        "remote_runner_identity_readback": proof_root / "remote_runner_identity_readback.json",
        "fresh_remote_account_read": proof_root / "fresh_remote_account_read.json",
        "pre_position_fingerprint": proof_root / "pre_position_fingerprint.json",
        "pre_open_order_fingerprint": proof_root / "pre_open_order_fingerprint.json",
        "pre_fill_trade_fingerprint": proof_root / "pre_fill_trade_fingerprint.json",
        "fresh_order_book": proof_root / "fresh_order_book.json",
        "exchange_filter_readback": proof_root / "exchange_filter_readback.json",
        "p9bu_terms_operator_acceptance": proof_root / "p9bu_terms_operator_acceptance.json",
        "candidate_target_plan_hash_binding": proof_root / "candidate_target_plan_hash_binding.json",
        "baseline_candidate_plan_diff": proof_root / "baseline_candidate_plan_diff.json",
        "kill_switch_readback": proof_root / "kill_switch_readback.json",
        "rollback_command_readback": proof_root / "rollback_command_readback.json",
        "post_position_fingerprint": proof_root / "post_position_fingerprint.json",
        "post_open_order_fingerprint": proof_root / "post_open_order_fingerprint.json",
        "post_fill_trade_fingerprint": proof_root / "post_fill_trade_fingerprint.json",
        "proof_collection_delta_acceptance": proof_root / "proof_collection_delta_acceptance.json",
        "non_authorization": proof_root / "non_authorization.json",
        "control_boundary_readback": proof_root / "control_boundary_readback.json",
        "proof_artifact_manifest": proof_root / "proof_artifact_manifest.json",
    }
    write_json(proof_files["remote_runner_identity_readback"], identity)
    write_json(proof_files["fresh_remote_account_read"], fresh_account)
    write_json(
        proof_files["pre_position_fingerprint"],
        dict(collector.get("pre_position_fingerprint") or {}),
    )
    write_json(
        proof_files["pre_open_order_fingerprint"],
        dict(collector.get("pre_open_order_fingerprint") or {}),
    )
    write_json(
        proof_files["pre_fill_trade_fingerprint"],
        dict(collector.get("pre_fill_trade_fingerprint") or {}),
    )
    write_json(proof_files["fresh_order_book"], fresh_book)
    write_json(proof_files["exchange_filter_readback"], filters)
    write_json(proof_files["p9bu_terms_operator_acceptance"], p9bu_acceptance)
    write_json(proof_files["candidate_target_plan_hash_binding"], hash_binding)
    write_json(proof_files["baseline_candidate_plan_diff"], plan_diff)
    write_json(proof_files["kill_switch_readback"], kill_switch)
    write_json(proof_files["rollback_command_readback"], rollback)
    write_json(
        proof_files["post_position_fingerprint"],
        dict(collector.get("post_position_fingerprint") or {}),
    )
    write_json(
        proof_files["post_open_order_fingerprint"],
        dict(collector.get("post_open_order_fingerprint") or {}),
    )
    write_json(
        proof_files["post_fill_trade_fingerprint"],
        dict(collector.get("post_fill_trade_fingerprint") or {}),
    )
    write_json(proof_files["proof_collection_delta_acceptance"], delta)
    write_json(proof_files["non_authorization"], non_auth)
    write_json(proof_files["control_boundary_readback"], control)
    manifest = write_proof_manifest(proof_root, proof_files)

    write_json(root / "command_records.json", {"commands": command_records})
    gates = {
        **pre_checks,
        "pre_control_snapshot_ready": bool(pre_snapshot)
        and "parse_failed" != pre_snapshot.get("status"),
        "remote_stdout_collector_ready": collector_ready(collector),
        "remote_runner_identity_ready": bool(collector)
        and remote_identity_ready(
            identity,
            remote_host=args.remote_host,
            remote_repo=args.remote_repo,
            remote_config=args.remote_config,
            expected_egress_ip=args.expected_egress_ip,
        ),
        "fresh_remote_account_read_ready": remote_account_read_ready(fresh_account),
        "fresh_order_book_ready": fresh_book.get("status") == "ready",
        "exchange_filter_readback_ready": filters.get("status") == "ready",
        "position_fingerprint_stable": delta.get("position_delta_zero_or_stable")
        is True,
        "open_order_fingerprint_stable": delta.get("open_order_fingerprint_stable")
        is True,
        "balance_fingerprint_stable": delta.get("balance_delta_zero_or_stable")
        is True,
        "fill_trade_fingerprint_stable": delta.get("fill_trade_fingerprint_stable")
        is True,
        "order_cancel_fill_trade_delta_zero": delta.get(
            "order_cancel_fill_trade_delta_zero"
        )
        is True,
        "remote_control_boundary_unchanged": bool(pre_snapshot and post_snapshot)
        and snapshot_boundary_ok(pre_snapshot, post_snapshot),
        "proof_artifact_manifest_ready": bool(manifest.get("self", {}).get("sha256")),
        "remote_files_written_zero": control.get("remote_files_written") == 0,
        "remote_sync_not_performed": control.get("remote_sync_performed") is False,
        "supervisor_not_invoked": control.get("ran_supervisor") is False,
        "timer_path_not_loaded": control.get("entered_timer_path") is False,
        "candidate_not_executed": control.get("candidate_execution_performed") is False,
        "executor_input_not_mutated": control.get("executor_input_changed") is False,
        "target_plan_not_replaced": control.get("target_plan_replaced") is False,
        "zero_orders_fills_trades": control.get("orders_submitted") == 0
        and control.get("orders_canceled") == 0
        and control.get("fill_count") == 0
        and control.get("trade_count") == 0,
    }
    blockers.extend(key for key, value in gates.items() if not value and key not in blockers)
    blockers = sorted(set(blockers))
    status = "ready" if not blockers else "blocked"
    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "status": status,
        "blockers": blockers,
        "p9ce_read_only_fresh_remote_proof_collection_ready": status == "ready",
        "fresh_remote_proof_collection_performed_in_p9ce": bool(collector),
        "fresh_remote_account_read_performed": bool(fresh_account),
        "fresh_order_book_read_performed": bool(fresh_book),
        "exchange_filter_read_performed": bool(filters),
        "target_runner_identity_hint": TARGET_RUNNER_IDENTITY_HINT,
        "target_deploy_root_hint": TARGET_DEPLOY_ROOT_HINT,
        "target_runner_identity_proven_in_p9ce": gates["remote_runner_identity_ready"],
        "target_deploy_root_proven_in_p9ce": gates["remote_runner_identity_ready"],
        "remote_host": args.remote_host,
        "remote_repo": args.remote_repo,
        "remote_config": args.remote_config,
        "remote_python": args.remote_python,
        "expected_egress_ip": args.expected_egress_ip,
        "remote_egress_ip": identity.get("egress_ip"),
        "remote_sync_performed": False,
        "remote_files_written": 0,
        "remote_execution_performed": bool(collector),
        "remote_execution_scope": "stdout_read_only_collector_only",
        "supervisor_invocation_authorized": False,
        "timer_path_load_authorized": False,
        "production_timer_service_load_authorized": False,
        "live_order_gate_approved": False,
        "live_order_submission_authorized": False,
        "candidate_enter_executor_target_plan_path_authorized": False,
        "candidate_execution_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "live_config_mutation_authorized": False,
        "operator_state_mutation_authorized": False,
        "timer_or_service_mutation_authorized": False,
        "position_fingerprint_stable": gates["position_fingerprint_stable"],
        "open_order_fingerprint_stable": gates["open_order_fingerprint_stable"],
        "balance_fingerprint_stable": gates["balance_fingerprint_stable"],
        "fill_trade_fingerprint_stable": gates["fill_trade_fingerprint_stable"],
        "order_cancel_fill_trade_delta_zero": gates[
            "order_cancel_fill_trade_delta_zero"
        ],
        "remote_control_boundary_unchanged": gates[
            "remote_control_boundary_unchanged"
        ],
        "open_position_count_pre": delta.get("open_position_count_pre"),
        "open_position_count_post": delta.get("open_position_count_post"),
        "open_order_count_pre": delta.get("open_order_count_pre"),
        "open_order_count_post": delta.get("open_order_count_post"),
        "account_can_trade_pre": dict(fresh_account.get("pre") or {}).get("can_trade"),
        "account_can_trade_post": dict(fresh_account.get("post") or {}).get("can_trade"),
        "future_live_order_readiness_blockers": future_live_order_readiness_blockers,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
        "canary_symbol": CANARY_SYMBOL,
        "canary_side": CANARY_SIDE,
        "risk_ceiling_usdt": DEFAULT_RISK_CEILING_USDT,
        "max_notional_usdt": DEFAULT_MAX_NOTIONAL_USDT,
        "max_orders_per_cycle": DEFAULT_MAX_ORDERS_PER_CYCLE,
        "max_symbols_per_cycle": DEFAULT_MAX_SYMBOLS_PER_CYCLE,
        "order_type": DEFAULT_ORDER_TYPE,
        "time_in_force": DEFAULT_TIME_IN_FORCE,
        "market_orders_allowed": False,
        "baseline_target_plan_sha256": p9cd.get("baseline_target_plan_sha256"),
        "candidate_target_plan_sha256": p9cd.get("candidate_target_plan_sha256"),
        "only_distance_to_high_60_contribution_changed": p9cd.get(
            "only_distance_to_high_60_contribution_changed"
        ),
        "allowed_next_gate": P9CF_GATE,
        "allowed_next_gate_scope": P9CF_SCOPE,
        "allowed_next_gate_must_be_separately_requested": True,
        "eligible_for_future_live_order_submission": False,
        "eligible_for_future_candidate_execution": False,
        "source_evidence": {
            "phase9cd_summary": evidence_file(p9cd_path),
            "phase9cd_terms": evidence_file(terms_path),
            "phase9cd_non_authorization": evidence_file(non_auth_path),
            "phase9cd_control_boundary": evidence_file(control_path),
            "project_profile": evidence_file(project_profile_path),
        },
        "gates": gates,
        "output_files": {
            "summary": str(root / "summary.json"),
            "owner_decision_record": str(root / "owner_decision_record.json"),
            "command_records": str(root / "command_records.json"),
            "remote_stdout_collector_raw": str(root / "remote_stdout_collector_raw.json"),
            "pre_control_snapshot": str(root / "pre_control_snapshot.json"),
            "post_control_snapshot": str(root / "post_control_snapshot.json"),
            "proof_artifact_manifest": str(proof_files["proof_artifact_manifest"]),
            "report": str(root / "p9ce_read_only_fresh_remote_proof_collection.md"),
            **{key: str(path) for key, path in proof_files.items() if key != "proof_artifact_manifest"},
        },
    }
    write_json(root / "summary.json", summary)
    (root / "p9ce_read_only_fresh_remote_proof_collection.md").write_text(
        render_markdown(summary),
        encoding="utf-8",
    )
    return summary, 0 if status == "ready" else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9CE Read-Only Fresh Remote Proof Collection",
        "",
        f"`Status: {summary['status']}`",
        "",
        "P9CE executes a fresh remote proof collection through a read-only stdout collector. It does not write remote files, remote sync, invoke supervisor/timer paths, mutate live config/operator/executor state, execute the candidate, replace target plans, cancel orders, or submit orders.",
        "",
        "## Proof Boundary",
        "",
        "```text",
        "p9ce_read_only_fresh_remote_proof_collection_ready = "
        f"{str(bool(summary['p9ce_read_only_fresh_remote_proof_collection_ready'])).lower()}",
        "target_runner_identity_proven_in_p9ce = "
        f"{str(bool(summary['target_runner_identity_proven_in_p9ce'])).lower()}",
        "fresh_remote_account_read_performed = "
        f"{str(bool(summary['fresh_remote_account_read_performed'])).lower()}",
        "fresh_order_book_read_performed = "
        f"{str(bool(summary['fresh_order_book_read_performed'])).lower()}",
        "exchange_filter_read_performed = "
        f"{str(bool(summary['exchange_filter_read_performed'])).lower()}",
        "remote_files_written = 0",
        "remote_sync_performed = false",
        "live_order_submission_authorized = false",
        "candidate_execution_authorized = false",
        "target_plan_replacement_authorized = false",
        "executor_input_mutation_authorized = false",
        "orders_submitted = 0",
        "orders_canceled = 0",
        "fill_count = 0",
        "trade_count = 0",
        "```",
        "",
        "## Delta Acceptance",
        "",
        "```text",
        "position_fingerprint_stable = "
        f"{str(bool(summary['position_fingerprint_stable'])).lower()}",
        "open_order_fingerprint_stable = "
        f"{str(bool(summary['open_order_fingerprint_stable'])).lower()}",
        "balance_fingerprint_stable = "
        f"{str(bool(summary['balance_fingerprint_stable'])).lower()}",
        "fill_trade_fingerprint_stable = "
        f"{str(bool(summary['fill_trade_fingerprint_stable'])).lower()}",
        "order_cancel_fill_trade_delta_zero = "
        f"{str(bool(summary['order_cancel_fill_trade_delta_zero'])).lower()}",
        "remote_control_boundary_unchanged = "
        f"{str(bool(summary['remote_control_boundary_unchanged'])).lower()}",
        "```",
        "",
        "## Blockers",
        "",
    ]
    blockers = list(summary.get("blockers") or [])
    if blockers:
        lines.extend(f"- `{item}`" for item in blockers)
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Allowed Next Gate",
            "",
            "```text",
            str(summary["allowed_next_gate"]),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_phase9ce(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
