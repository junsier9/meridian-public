from __future__ import annotations

import argparse
import hashlib
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

from scripts.live_trading.hv_balanced_binance_usdm_pit_safe_account_proof_builder import (  # noqa: E402
    ACCOUNT_CONFIG_ENDPOINT,
    ACCOUNT_PROOF_CONTRACT_VERSION,
    ACCOUNT_V2_ENDPOINT,
    ACCOUNT_V3_ENDPOINT,
    API_RESTRICTIONS_ENDPOINT,
    BLOCKER_CAN_TRADE_FALSE,
    BLOCKER_CAN_TRADE_MISSING,
    CAN_TRADE_SOURCE,
    CONTRACT_VERSION as ACCOUNT_BUILDER_CONTRACT,
    OPEN_ORDERS_ENDPOINT,
    POSITION_MODE_ENDPOINT,
    build_pit_safe_account_proof,
)
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
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cf_review_p9ce_read_only_fresh_remote_proof_collection import (  # noqa: E402
    LIVE_ORDER_BLOCKER_ACCOUNT_CAN_TRADE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ch_pit_safe_read_only_account_proof_owner_gate import (  # noqa: E402
    CONTRACT_VERSION as P9CH_CONTRACT,
    DEFAULT_OUTPUT_PARENT as P9CH_PARENT,
    P9CI_GATE,
    P9CI_SCOPE,
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
    "hv_balanced_dth60_coinglass_phase9ci_pit_safe_read_only_account_proof_v2v3.v1"
)
APPROVE_P9CI_DECISION = (
    "approve_p9ci_execute_pit_safe_read_only_account_proof_v2v3_only_no_order_no_candidate_no_timer_no_supervisor"
)
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/p9ci_pit_safe_read_only_account_proof_v2v3"
)
P9CJ_GATE = (
    "P9CJ_review_p9ci_pit_safe_read_only_account_proof_v2v3_only_if_separately_requested"
)
P9CJ_SCOPE = (
    "review_p9ci_pit_safe_read_only_account_proof_classification_before_any_live_order_or_executor_path_change"
)
DEFAULT_HISTORY_CANARY_SYMBOL = "BTCUSDT"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Execute P9CI PIT-safe Binance USD-M v2/v3 read-only account proof. "
            "This performs stdout-only remote GET reads and local retained proof "
            "construction. It does not call order-test endpoints, submit/cancel "
            "orders, run supervisor/timer paths, execute the candidate, replace "
            "target plans, mutate executor input, remote sync, or write remote files."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9ch-summary", default="")
    parser.add_argument("--remote-host", default=DEFAULT_REMOTE_HOST)
    parser.add_argument("--remote-repo", default=DEFAULT_REMOTE_REPO)
    parser.add_argument("--remote-config", default=DEFAULT_REMOTE_CONFIG)
    parser.add_argument("--remote-live-env", default=DEFAULT_REMOTE_LIVE_ENV)
    parser.add_argument("--remote-python", default=DEFAULT_REMOTE_PYTHON)
    parser.add_argument("--expected-egress-ip", default=DEFAULT_EXPECTED_EGRESS_IP)
    parser.add_argument("--history-canary-symbol", default=DEFAULT_HISTORY_CANARY_SYMBOL)
    parser.add_argument("--max-history-symbols", type=int, default=20)
    parser.add_argument("--ssh-connect-timeout", type=int, default=10)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9CI_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:execute_pit_safe_v2v3_read_only_account_proof_no_order_no_candidate_no_timer_no_supervisor",
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


def latest_p9ch_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9ch_summary).strip():
        return resolve_path(args.phase9ch_summary)
    return latest_match(P9CH_PARENT, "*/summary.json")


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def source_output_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("output_files") or {}).get(key) or "")
    return resolve_path(text) if text.strip() else Path("")


def p9ch_summary_ready(summary: dict[str, Any]) -> bool:
    return (
        summary.get("contract_version") == P9CH_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9ch_pit_safe_read_only_account_proof_owner_gate_ready")
        is True
        and summary.get("p9cg_sufficient_for_p9ch_owner_gate") is True
        and summary.get("pit_safe_read_only_account_proof_owner_gate_approved_in_p9ch")
        is True
        and summary.get("eligible_for_future_p9ci_account_proof_execution_gate")
        is True
        and summary.get("eligible_for_future_live_order_submission") is False
        and summary.get("eligible_for_future_candidate_execution") is False
        and summary.get("eligible_for_future_pit_safe_account_proof_without_separate_request")
        is False
        and summary.get("fresh_remote_proof_collection_execution_approved_in_p9ch")
        is False
        and summary.get("pit_safe_account_proof_collection_performed_in_p9ch")
        is False
        and summary.get("fresh_remote_account_read_performed") is False
        and summary.get("fresh_order_book_read_performed") is False
        and summary.get("exchange_filter_read_performed") is False
        and summary.get("order_test_endpoint_called") is False
        and summary.get("live_order_gate_approved") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("candidate_execution_authorized") is False
        and summary.get("target_plan_replacement_authorized") is False
        and summary.get("executor_input_mutation_authorized") is False
        and summary.get("remote_execution_authorized") is False
        and summary.get("remote_sync_authorized") is False
        and summary.get("supervisor_invocation_authorized") is False
        and summary.get("timer_path_load_authorized") is False
        and summary.get("can_trade_decision_source") == CAN_TRADE_SOURCE
        and summary.get("prior_p9ce_blocker") == LIVE_ORDER_BLOCKER_ACCOUNT_CAN_TRADE
        and list(summary.get("replacement_blockers") or [])
        == [BLOCKER_CAN_TRADE_MISSING, BLOCKER_CAN_TRADE_FALSE]
        and summary.get("account_v3_canTrade_must_be_ignored_for_permission_decision")
        is True
        and summary.get("allowed_next_gate") == P9CI_GATE
        and summary.get("allowed_next_gate_scope") == P9CI_SCOPE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
        and int_zero(summary, "orders_submitted")
        and int_zero(summary, "orders_canceled")
        and int_zero(summary, "fill_count")
        and int_zero(summary, "trade_count")
    )


def p9ch_terms_ready(terms: dict[str, Any]) -> bool:
    side_effects = dict(terms.get("required_future_side_effect_contract") or {})
    return (
        terms.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9ch_account_proof_execution_gate_terms.v1"
        and terms.get("owner_gate_only") is True
        and terms.get("allowed_next_gate") == P9CI_GATE
        and terms.get("allowed_next_gate_scope") == P9CI_SCOPE
        and terms.get("allowed_next_gate_must_be_separately_requested") is True
        and terms.get("pit_safe_read_only_account_proof_may_be_requested_next") is True
        and terms.get("pit_safe_account_proof_collection_performed_in_p9ch") is False
        and set(terms.get("required_read_only_endpoints") or [])
        >= {
            ACCOUNT_V2_ENDPOINT,
            ACCOUNT_V3_ENDPOINT,
            ACCOUNT_CONFIG_ENDPOINT,
            POSITION_MODE_ENDPOINT,
            OPEN_ORDERS_ENDPOINT,
            API_RESTRICTIONS_ENDPOINT,
        }
        and terms.get("account_proof_contract") == ACCOUNT_PROOF_CONTRACT_VERSION
        and terms.get("account_proof_builder_contract") == ACCOUNT_BUILDER_CONTRACT
        and terms.get("can_trade_decision_source") == CAN_TRADE_SOURCE
        and terms.get("account_v3_canTrade_must_be_ignored_for_permission_decision")
        is True
        and list(terms.get("replacement_blockers") or [])
        == [BLOCKER_CAN_TRADE_MISSING, BLOCKER_CAN_TRADE_FALSE]
        and side_effects.get("http_methods_allowed") == ["GET"]
        and int(side_effects.get("remote_files_written_must_equal") or 0) == 0
        and side_effects.get("remote_sync_performed_must_equal") is False
        and int(side_effects.get("order_test_calls_must_equal") or 0) == 0
        and int(side_effects.get("orders_submitted_must_equal") or 0) == 0
        and int(side_effects.get("orders_canceled_must_equal") or 0) == 0
        and int(side_effects.get("fill_count_must_equal") or 0) == 0
        and int(side_effects.get("trade_count_must_equal") or 0) == 0
    )


def p9ch_future_contract_ready(contract: dict[str, Any]) -> bool:
    must = dict(contract.get("p9ci_must_fail_closed_unless") or {})
    report = dict(contract.get("p9ci_must_report") or {})
    forbidden = set(str(item) for item in list(contract.get("p9ci_does_not_authorize") or []))
    return (
        contract.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9ch_future_p9ci_acceptance_contract.v1"
        and contract.get("future_gate") == P9CI_GATE
        and contract.get("future_gate_scope") == P9CI_SCOPE
        and contract.get("future_gate_must_be_separately_requested") is True
        and all(value is True for value in must.values())
        and report.get("canTrade_missing_from_endpoint") == BLOCKER_CAN_TRADE_MISSING
        and report.get("canTrade_false") == BLOCKER_CAN_TRADE_FALSE
        and report.get("canTrade_true_clears_prior_false_or_missing_only_after_review")
        is True
        and {
            "live order submission",
            "candidate execution",
            "target-plan replacement",
            "executor-input mutation",
            "supervisor/timer invocation",
            "remote sync",
            "live config/operator/timer mutation",
            "stage governance change",
        }.issubset(forbidden)
    )


def p9ch_non_authorization_ready(matrix: dict[str, Any]) -> bool:
    authorizations = dict(matrix.get("authorizations") or {})
    return (
        matrix.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9ch_non_authorization.v1"
        and authorizations.get("allow_future_p9ci_account_proof_gate_request") is True
        and authorizations.get("execute_pit_safe_read_only_account_proof_in_p9ch")
        is False
        and authorizations.get("pit_safe_account_proof_collection") is False
        and authorizations.get("fresh_remote_account_read") is False
        and authorizations.get("fresh_order_book_read") is False
        and authorizations.get("exchange_filter_read") is False
        and authorizations.get("order_test_endpoint") is False
        and authorizations.get("live_order_gate_approval") is False
        and authorizations.get("actual_candidate_executor_target_path_entry")
        is False
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


def p9ch_control_ready(control: dict[str, Any]) -> bool:
    return (
        control.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9ch_control_boundary.v1"
        and control.get("scope") == "pit_safe_read_only_account_proof_owner_gate_only"
        and control.get("ssh_invoked") is False
        and control.get("remote_network_connection_performed") is False
        and control.get("fresh_remote_account_read_performed") is False
        and control.get("fresh_order_book_read_performed") is False
        and control.get("exchange_filter_read_performed") is False
        and control.get("order_test_endpoint_called") is False
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


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def remote_p9ci_collector_command(
    *,
    remote_repo: str,
    remote_live_env: str,
    remote_python: str,
    remote_config: str,
    expected_egress_ip: str,
    history_canary_symbol: str,
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
HISTORY_CANARY_SYMBOL = {history_canary_symbol!r}
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
        headers=dict(headers or {{"User-Agent": "Meridian/P9CI-v2v3-readonly-proof"}}),
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
    if result.get("status") != "ok":
        result.pop("payload", None)
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

def collect_account_side(label, api_key, api_secret):
    endpoint_results = {{
        "account_v2": signed_get(FAPI, "/fapi/v2/account", api_key=api_key, api_secret=api_secret),
        "account_v3": signed_get(FAPI, "/fapi/v3/account", api_key=api_key, api_secret=api_secret),
        "account_config": signed_get(FAPI, "/fapi/v1/accountConfig", api_key=api_key, api_secret=api_secret),
        "position_mode": signed_get(FAPI, "/fapi/v1/positionSide/dual", api_key=api_key, api_secret=api_secret),
        "open_orders": signed_get(FAPI, "/fapi/v1/openOrders", api_key=api_key, api_secret=api_secret),
        "api_restrictions": signed_get(SAPI, "/sapi/v1/account/apiRestrictions", api_key=api_key, api_secret=api_secret),
    }}
    blockers = []
    for name, item in endpoint_results.items():
        if item.get("status") != "ok":
            blockers.append(f"read_only_endpoint_failed:{{name}}:{{item.get('status_code', item.get('error_type', 'unknown'))}}")
    return {{
        "label": label,
        "egress_ip": public_ip(),
        "endpoint_results": endpoint_results,
        "status": "ready" if not blockers else "blocked",
        "blockers": sorted(set(blockers)),
    }}

def open_position_symbols(endpoint_results):
    account_v3 = payload(endpoint_results.get("account_v3", {{}}), {{}})
    account_v2 = payload(endpoint_results.get("account_v2", {{}}), {{}})
    positions = account_v3.get("positions") or account_v2.get("positions") or []
    symbols = []
    for row in list(positions or []):
        if not isinstance(row, dict):
            continue
        try:
            amount = float(row.get("positionAmt") or 0.0)
        except Exception:
            amount = 0.0
        if abs(amount) > 1e-12 and row.get("symbol"):
            symbols.append(str(row.get("symbol")).upper())
    return symbols

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
        endpoint_results.append({{"symbol": symbol, "endpoint": "allOrders", "path": "/fapi/v1/allOrders", "method": "GET", "status": orders.get("status"), "status_code": orders.get("status_code"), "error_type": orders.get("error_type"), "error": orders.get("error")}})
        endpoint_results.append({{"symbol": symbol, "endpoint": "userTrades", "path": "/fapi/v1/userTrades", "method": "GET", "status": trades.get("status"), "status_code": trades.get("status_code"), "error_type": trades.get("error_type"), "error": trades.get("error")}})
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
            "history_hash": digest(order_history),
        }},
        "trade_history_fingerprint": {{
            "stable_fields": trade_fields,
            "history_hash": digest(trade_history),
        }},
        "endpoint_results": endpoint_results,
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
operator_control = operator_state_readback()
proof_symbols = []
if not blockers:
    pre_account = collect_account_side("pre", api_key, api_secret)
    proof_symbols = sorted(
        set(config_symbols())
        | set(open_position_symbols(pre_account.get("endpoint_results", {{}})))
        | {{HISTORY_CANARY_SYMBOL}}
    )
    pre_history = collect_history_fingerprint(proof_symbols, api_key, api_secret)
    post_account = collect_account_side("post", api_key, api_secret)
    proof_symbols = sorted(
        set(proof_symbols)
        | set(open_position_symbols(post_account.get("endpoint_results", {{}})))
    )
    post_history = collect_history_fingerprint(proof_symbols, api_key, api_secret)

for source in (pre_account, post_account, pre_history, post_history):
    blockers.extend(list(source.get("blockers") or []))

side_effects = {{
    "orders_submitted": 0,
    "orders_canceled": 0,
    "order_test_calls": 0,
    "fill_count": 0,
    "trade_count": 0,
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

order_history_stable = (
    pre_history.get("order_history_fingerprint", {{}}).get("history_hash")
    == post_history.get("order_history_fingerprint", {{}}).get("history_hash")
)
trade_history_stable = (
    pre_history.get("trade_history_fingerprint", {{}}).get("history_hash")
    == post_history.get("trade_history_fingerprint", {{}}).get("history_hash")
)
if pre_history and not order_history_stable:
    blockers.append("order_history_fingerprint_changed")
if pre_history and not trade_history_stable:
    blockers.append("trade_history_fingerprint_changed")

summary = {{
    "contract_version": "hv_balanced_dth60_coinglass_phase9ci_remote_stdout_v2v3_account_collector.v1",
    "started_at_utc": started_at,
    "finished_at_utc": iso_now(),
    "status": "ready" if not blockers else "blocked",
    "blockers": sorted(set(blockers)),
    "remote_runner_identity_readback": remote_identity,
    "pre_egress_ip": pre_account.get("egress_ip"),
    "post_egress_ip": post_account.get("egress_ip"),
    "pre_endpoint_results": pre_account.get("endpoint_results", {{}}),
    "post_endpoint_results": post_account.get("endpoint_results", {{}}),
    "proof_symbols": proof_symbols[:MAX_HISTORY_SYMBOLS],
    "pre_history_fingerprint": pre_history,
    "post_history_fingerprint": post_history,
    "history_delta": {{
        "order_history_fingerprint_stable": order_history_stable,
        "trade_history_fingerprint_stable": trade_history_stable,
        "order_history_hash_pre": pre_history.get("order_history_fingerprint", {{}}).get("history_hash"),
        "order_history_hash_post": post_history.get("order_history_fingerprint", {{}}).get("history_hash"),
        "trade_history_hash_pre": pre_history.get("trade_history_fingerprint", {{}}).get("history_hash"),
        "trade_history_hash_post": post_history.get("trade_history_fingerprint", {{}}).get("history_hash"),
    }},
    "operator_control_readback": operator_control,
    "side_effects": side_effects,
}}
print(json.dumps(summary, indent=2, sort_keys=True))
PY
"""


def endpoint_meta(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": result.get("path"),
        "method": result.get("method"),
        "status": result.get("status"),
        "status_code": result.get("status_code"),
        "started_at_utc": result.get("started_at_utc"),
        "finished_at_utc": result.get("finished_at_utc"),
        "error_type": result.get("error_type"),
        "error": result.get("error"),
    }


def sanitized_endpoint_results(results: dict[str, Any]) -> dict[str, Any]:
    return {str(key): endpoint_meta(dict(value or {})) for key, value in results.items()}


def sanitized_collector(collector: dict[str, Any]) -> dict[str, Any]:
    return {
        "contract_version": collector.get("contract_version"),
        "started_at_utc": collector.get("started_at_utc"),
        "finished_at_utc": collector.get("finished_at_utc"),
        "status": collector.get("status"),
        "blockers": list(collector.get("blockers") or []),
        "remote_runner_identity_readback": dict(
            collector.get("remote_runner_identity_readback") or {}
        ),
        "pre_egress_ip": collector.get("pre_egress_ip"),
        "post_egress_ip": collector.get("post_egress_ip"),
        "pre_endpoint_results": sanitized_endpoint_results(
            dict(collector.get("pre_endpoint_results") or {})
        ),
        "post_endpoint_results": sanitized_endpoint_results(
            dict(collector.get("post_endpoint_results") or {})
        ),
        "proof_symbols": list(collector.get("proof_symbols") or []),
        "pre_history_fingerprint": dict(collector.get("pre_history_fingerprint") or {}),
        "post_history_fingerprint": dict(collector.get("post_history_fingerprint") or {}),
        "history_delta": dict(collector.get("history_delta") or {}),
        "operator_control_readback": dict(collector.get("operator_control_readback") or {}),
        "side_effects": dict(collector.get("side_effects") or {}),
    }


def side_effects_zero(side_effects: dict[str, Any]) -> bool:
    methods = set(str(item).upper() for item in list(side_effects.get("http_methods_used") or []))
    return (
        (not methods or methods == {"GET"})
        and side_effects.get("only_http_get_endpoints") is True
        and int_zero(side_effects, "remote_files_written")
        and side_effects.get("remote_sync_performed") is False
        and side_effects.get("supervisor_invoked") is False
        and side_effects.get("timer_path_invoked") is False
        and side_effects.get("candidate_executed") is False
        and side_effects.get("executor_input_mutated") is False
        and side_effects.get("target_plan_replaced") is False
        and int_zero(side_effects, "orders_submitted")
        and int_zero(side_effects, "orders_canceled")
        and int_zero(side_effects, "order_test_calls")
        and int_zero(side_effects, "fill_count")
        and int_zero(side_effects, "trade_count")
    )


def collector_contract_ready(collector: dict[str, Any]) -> bool:
    return (
        collector.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9ci_remote_stdout_v2v3_account_collector.v1"
        and collector.get("status") == "ready"
        and not collector.get("blockers")
        and side_effects_zero(dict(collector.get("side_effects") or {}))
        and bool(dict(collector.get("pre_endpoint_results") or {}).get("account_v2"))
        and bool(dict(collector.get("pre_endpoint_results") or {}).get("account_v3"))
        and bool(dict(collector.get("post_endpoint_results") or {}).get("account_v2"))
        and bool(dict(collector.get("post_endpoint_results") or {}).get("account_v3"))
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
        remote_host == DEFAULT_REMOTE_HOST
        and identity.get("whoami") == "root"
        and identity.get("repo_path") == remote_repo
        and identity.get("config_path") == remote_config
        and identity.get("egress_ip") == expected_egress_ip
        and bool(identity.get("config_sha256"))
        and bool(identity.get("live_supervisor_sha256"))
    )


def history_delta_acceptance(collector: dict[str, Any]) -> dict[str, Any]:
    delta = dict(collector.get("history_delta") or {})
    side_effects = dict(collector.get("side_effects") or {})
    order_stable = delta.get("order_history_fingerprint_stable") is True
    trade_stable = delta.get("trade_history_fingerprint_stable") is True
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ci_history_delta_acceptance.v1",
        "proof_symbols": list(collector.get("proof_symbols") or []),
        "order_history_fingerprint_stable": order_stable,
        "trade_history_fingerprint_stable": trade_stable,
        "order_history_hash_pre": delta.get("order_history_hash_pre"),
        "order_history_hash_post": delta.get("order_history_hash_post"),
        "trade_history_hash_pre": delta.get("trade_history_hash_pre"),
        "trade_history_hash_post": delta.get("trade_history_hash_post"),
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
        "order_cancel_fill_trade_delta_zero": (
            order_stable and trade_stable and side_effects_zero(side_effects)
        ),
    }


def account_delta_acceptance(proof: dict[str, Any]) -> dict[str, Any]:
    checks = dict(proof.get("checks") or {})
    pre = dict(proof.get("pre") or {})
    post = dict(proof.get("post") or {})
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ci_account_delta_acceptance.v1",
        "position_fingerprint_stable": checks.get("position_fingerprint_stable") is True,
        "open_order_fingerprint_stable": checks.get("open_order_fingerprint_stable")
        is True,
        "balance_fingerprint_stable": checks.get("balance_fingerprint_stable") is True,
        "open_order_count_zero_pre_post": checks.get("open_order_count_zero_pre_post")
        is True,
        "side_effects_zero": checks.get("side_effects_zero") is True,
        "open_position_count_pre": int(pre.get("open_position_count") or 0),
        "open_position_count_post": int(post.get("open_position_count") or 0),
        "open_order_count_pre": int(pre.get("open_order_count") or 0),
        "open_order_count_post": int(post.get("open_order_count") or 0),
        "position_delta_zero_or_stable": checks.get("position_fingerprint_stable")
        is True,
        "open_order_delta_zero_or_stable": checks.get("open_order_fingerprint_stable")
        is True,
        "balance_delta_zero_or_stable": checks.get("balance_fingerprint_stable")
        is True,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
    }


def proof_manifest(proof_root: Path, files: dict[str, Path]) -> dict[str, Any]:
    entries = {
        key: evidence_file(path)
        for key, path in sorted(files.items())
        if path.name != "proof_artifact_manifest.json"
    }
    manifest = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ci_proof_manifest.v1",
        "artifact_count": len(entries),
        "artifacts": entries,
    }
    manifest_path = proof_root / "proof_artifact_manifest.json"
    write_json(manifest_path, manifest)
    manifest["self"] = evidence_file(manifest_path)
    write_json(manifest_path, manifest)
    return manifest


def owner_decision_record(args: argparse.Namespace, now: datetime) -> dict[str, Any]:
    approved = str(args.owner_decision) == APPROVE_P9CI_DECISION
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ci_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "execute_pit_safe_v2v3_read_only_account_proof_only_no_order_no_candidate_no_timer_no_supervisor",
        "decision_effect": (
            "execute_p9ci_pit_safe_v2v3_read_only_account_proof"
            if approved
            else "none"
        ),
        "recorded_at_utc": iso_z(now),
        "p9ci_pit_safe_read_only_account_proof_approved": approved,
        "remote_stdout_read_only_account_collection_approved": approved,
        "remote_files_written_approved": False,
        "remote_sync_approved": False,
        "order_test_endpoint_approved": False,
        "supervisor_invocation_approved": False,
        "timer_path_load_approved": False,
        "candidate_execution_approved": False,
        "target_plan_replacement_approved": False,
        "executor_input_mutation_approved": False,
        "live_order_submission_approved": False,
    }


def build_phase9ci(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
    command_runner: CommandRunner = local_command_runner,
) -> tuple[dict[str, Any], int]:
    started_at = now_fn()
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9ci" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    p9ch_path = latest_p9ch_summary(args)
    p9ch = load_optional(p9ch_path)
    terms_path = source_output_path(p9ch, "account_proof_execution_gate_terms")
    future_contract_path = source_output_path(p9ch, "future_p9ci_acceptance_contract")
    p9ch_non_auth_path = source_output_path(p9ch, "non_authorization")
    p9ch_control_path = source_output_path(p9ch, "control_boundary_readback")
    terms = load_optional(terms_path)
    future_contract = load_optional(future_contract_path)
    p9ch_non_auth = load_optional(p9ch_non_auth_path)
    p9ch_control = load_optional(p9ch_control_path)
    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)
    owner_record = owner_decision_record(args, started_at)
    write_json(root / "owner_decision_record.json", owner_record)

    pre_checks = {
        "owner_decision_p9ci_execute_read_only_recorded": str(args.owner_decision)
        == APPROVE_P9CI_DECISION,
        "project_profile_exists": bool(project_profile),
        "current_stage_is_stage3": str(project_profile.get("current_stage") or "")
        == "stage_3_human_approved_execution",
        "p9ch_summary_exists": bool(p9ch),
        "p9ch_summary_ready_for_p9ci": p9ch_summary_ready(p9ch),
        "p9ch_terms_ready_for_p9ci": p9ch_terms_ready(terms),
        "p9ch_future_contract_ready": p9ch_future_contract_ready(future_contract),
        "p9ch_non_authorization_ready": p9ch_non_authorization_ready(p9ch_non_auth),
        "p9ch_control_boundary_ready": p9ch_control_ready(p9ch_control),
        "remote_host_matches_expected_runner": str(args.remote_host)
        == DEFAULT_REMOTE_HOST,
        "remote_repo_matches_expected_runner": str(args.remote_repo)
        == DEFAULT_REMOTE_REPO,
    }
    blockers = [key for key, value in pre_checks.items() if not value]
    command_records: list[dict[str, Any]] = []
    pre_snapshot: dict[str, Any] = {}
    post_snapshot: dict[str, Any] = {}
    collector: dict[str, Any] = {}
    sanitized: dict[str, Any] = {}
    proof: dict[str, Any] = {}

    def run_record(label: str, cmd: Sequence[str]) -> CommandResult:
        result = command_runner(cmd)
        command_records.append(
            {
                "label": label,
                "args": list(cmd),
                "returncode": result.returncode,
                "stdout_sha256": sha256_text(result.stdout),
                "stdout_bytes": len(result.stdout.encode("utf-8")),
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
            "remote_stdout_pit_safe_v2v3_account_collector",
            ssh_args(
                args.remote_host,
                args.ssh_connect_timeout,
                remote_p9ci_collector_command(
                    remote_repo=args.remote_repo,
                    remote_live_env=args.remote_live_env,
                    remote_python=args.remote_python,
                    remote_config=args.remote_config,
                    expected_egress_ip=args.expected_egress_ip,
                    history_canary_symbol=args.history_canary_symbol,
                    max_history_symbols=int(args.max_history_symbols or 0),
                ),
            ),
        )
        collector = json_from_command(collector_result)
        if collector_result.returncode != 0:
            blockers.append("remote_stdout_pit_safe_v2v3_account_collector_failed")
        if not collector_contract_ready(collector):
            blockers.append("remote_stdout_pit_safe_v2v3_account_collector_not_ready")
        sanitized = sanitized_collector(collector)
        write_json(root / "remote_stdout_collector_sanitized.json", sanitized)
        fixture = {
            "expected_egress_ip": args.expected_egress_ip,
            "pre_egress_ip": collector.get("pre_egress_ip"),
            "post_egress_ip": collector.get("post_egress_ip"),
            "pre_endpoint_results": dict(collector.get("pre_endpoint_results") or {}),
            "post_endpoint_results": dict(collector.get("post_endpoint_results") or {}),
            "side_effects": dict(collector.get("side_effects") or {}),
        }
        proof = build_pit_safe_account_proof(fixture, generated_at=started_at)

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

    history_delta = history_delta_acceptance(collector) if collector else {}
    account_delta = account_delta_acceptance(proof) if proof else {}
    identity = dict(collector.get("remote_runner_identity_readback") or {})
    if collector and not remote_identity_ready(
        identity,
        remote_host=args.remote_host,
        remote_repo=args.remote_repo,
        remote_config=args.remote_config,
        expected_egress_ip=args.expected_egress_ip,
    ):
        blockers.append("remote_runner_identity_readback_not_ready")
    if proof and proof.get("pit_safe_read_only_account_proof_ready") is not True:
        blockers.append("pit_safe_read_only_account_proof_not_ready")
    if proof and proof.get("can_trade_source") != CAN_TRADE_SOURCE:
        blockers.append("can_trade_source_not_fapi_v2_account")
    if proof and proof.get("account_v3_canTrade_ignored_for_permission_decision") is not True:
        blockers.append("account_v3_canTrade_not_ignored")
    if proof and account_delta.get("open_order_count_zero_pre_post") is not True:
        blockers.append("open_order_count_not_zero_pre_post")
    if collector and history_delta.get("order_cancel_fill_trade_delta_zero") is not True:
        blockers.append("order_cancel_fill_trade_delta_not_zero_or_unproven")
    if proof and account_delta.get("position_delta_zero_or_stable") is not True:
        blockers.append("position_delta_not_zero_or_unstable")
    if proof and account_delta.get("balance_delta_zero_or_stable") is not True:
        blockers.append("balance_delta_not_zero_or_unstable")

    control = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ci_control_boundary.v1",
        "scope": "pit_safe_v2v3_read_only_account_proof_stdout_only",
        "ssh_invoked": bool(command_records),
        "remote_network_connection_performed": bool(collector),
        "remote_execution_scope": "stdout_pit_safe_v2v3_read_only_account_collector_only",
        "remote_files_written": 0,
        "remote_sync_performed": False,
        "fresh_remote_account_read_performed": bool(proof),
        "fresh_order_book_read_performed": False,
        "exchange_filter_read_performed": False,
        "order_test_endpoint_called": False,
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
    non_auth = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ci_non_authorization.v1",
        "authorizations": {
            "p9ci_pit_safe_v2v3_read_only_account_proof": str(args.owner_decision)
            == APPROVE_P9CI_DECISION,
            "remote_stdout_read_only_account_collection": str(args.owner_decision)
            == APPROVE_P9CI_DECISION,
            "fresh_order_book_read": False,
            "exchange_filter_read": False,
            "order_test_endpoint": False,
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

    proof_files = {
        "remote_runner_identity_readback": proof_root / "remote_runner_identity_readback.json",
        "remote_stdout_collector_sanitized": proof_root / "remote_stdout_collector_sanitized.json",
        "pit_safe_account_proof": proof_root / "pit_safe_account_proof.json",
        "account_delta_acceptance": proof_root / "account_delta_acceptance.json",
        "history_delta_acceptance": proof_root / "history_delta_acceptance.json",
        "non_authorization": proof_root / "non_authorization.json",
        "control_boundary_readback": proof_root / "control_boundary_readback.json",
        "proof_artifact_manifest": proof_root / "proof_artifact_manifest.json",
    }
    write_json(proof_files["remote_runner_identity_readback"], identity)
    write_json(proof_files["remote_stdout_collector_sanitized"], sanitized)
    write_json(proof_files["pit_safe_account_proof"], proof)
    write_json(proof_files["account_delta_acceptance"], account_delta)
    write_json(proof_files["history_delta_acceptance"], history_delta)
    write_json(proof_files["non_authorization"], non_auth)
    write_json(proof_files["control_boundary_readback"], control)
    manifest = proof_manifest(proof_root, proof_files)
    write_json(root / "command_records.json", {"commands": command_records})

    gates = {
        **pre_checks,
        "pre_control_snapshot_ready": bool(pre_snapshot)
        and "parse_failed" != pre_snapshot.get("status"),
        "remote_stdout_pit_safe_v2v3_account_collector_ready": collector_contract_ready(collector),
        "remote_runner_identity_ready": bool(collector)
        and remote_identity_ready(
            identity,
            remote_host=args.remote_host,
            remote_repo=args.remote_repo,
            remote_config=args.remote_config,
            expected_egress_ip=args.expected_egress_ip,
        ),
        "pit_safe_read_only_account_proof_ready": proof.get(
            "pit_safe_read_only_account_proof_ready"
        )
        is True,
        "can_trade_source_is_fapi_v2_account": proof.get("can_trade_source")
        == CAN_TRADE_SOURCE,
        "account_v3_canTrade_ignored": proof.get(
            "account_v3_canTrade_ignored_for_permission_decision"
        )
        is True,
        "position_fingerprint_stable": account_delta.get("position_fingerprint_stable")
        is True,
        "open_order_fingerprint_stable": account_delta.get(
            "open_order_fingerprint_stable"
        )
        is True,
        "balance_fingerprint_stable": account_delta.get("balance_fingerprint_stable")
        is True,
        "open_order_count_zero_pre_post": account_delta.get(
            "open_order_count_zero_pre_post"
        )
        is True,
        "order_cancel_fill_trade_delta_zero": history_delta.get(
            "order_cancel_fill_trade_delta_zero"
        )
        is True,
        "remote_control_boundary_unchanged": bool(pre_snapshot and post_snapshot)
        and snapshot_boundary_ok(pre_snapshot, post_snapshot),
        "proof_artifact_manifest_ready": bool(manifest.get("self", {}).get("sha256")),
        "remote_files_written_zero": control.get("remote_files_written") == 0,
        "remote_sync_not_performed": control.get("remote_sync_performed") is False,
        "order_test_endpoint_not_called": control.get("order_test_endpoint_called")
        is False,
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
    live_order_readiness_blockers = list(proof.get("live_order_readiness_blockers") or [])
    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "status": status,
        "blockers": blockers,
        "p9ci_pit_safe_read_only_account_proof_v2v3_ready": status == "ready",
        "p9ch_sufficient_for_p9ci_execution": p9ch_summary_ready(p9ch),
        "fresh_remote_account_read_performed": bool(proof),
        "pit_safe_v2v3_account_proof_executed": bool(proof),
        "fresh_order_book_read_performed": False,
        "exchange_filter_read_performed": False,
        "order_test_endpoint_called": False,
        "remote_execution_scope": "stdout_pit_safe_v2v3_read_only_account_collector_only",
        "remote_files_written": 0,
        "remote_sync_performed": False,
        "remote_execution_performed": bool(collector),
        "target_runner_identity_proven_in_p9ci": gates["remote_runner_identity_ready"],
        "target_deploy_root_proven_in_p9ci": gates["remote_runner_identity_ready"],
        "remote_host": args.remote_host,
        "remote_repo": args.remote_repo,
        "remote_config": args.remote_config,
        "remote_python": args.remote_python,
        "expected_egress_ip": args.expected_egress_ip,
        "remote_egress_ip": identity.get("egress_ip"),
        "can_trade_decision_source": proof.get("can_trade_source") or CAN_TRADE_SOURCE,
        "can_trade_pre": proof.get("can_trade_pre"),
        "can_trade_post": proof.get("can_trade_post"),
        "account_v2_has_canTrade_pre": proof.get("account_v2_has_canTrade_pre"),
        "account_v2_has_canTrade_post": proof.get("account_v2_has_canTrade_post"),
        "account_v3_has_canTrade_pre": proof.get("account_v3_has_canTrade_pre"),
        "account_v3_has_canTrade_post": proof.get("account_v3_has_canTrade_post"),
        "account_v3_canTrade_ignored_for_permission_decision": proof.get(
            "account_v3_canTrade_ignored_for_permission_decision"
        )
        is True,
        "replacement_blockers": [
            BLOCKER_CAN_TRADE_MISSING,
            BLOCKER_CAN_TRADE_FALSE,
        ],
        "live_order_readiness_blockers": live_order_readiness_blockers,
        "eligible_to_clear_p9cf_account_can_trade_blocker": proof.get(
            "eligible_to_clear_p9cf_account_can_trade_blocker"
        )
        is True,
        "prior_p9ce_blocker_reclassification": proof.get(
            "prior_p9ce_blocker_reclassification"
        ),
        "eligible_for_future_live_order_submission": False,
        "eligible_for_future_candidate_execution": False,
        "live_order_gate_approved": False,
        "live_order_submission_authorized": False,
        "candidate_execution_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "supervisor_invocation_authorized": False,
        "timer_path_load_authorized": False,
        "position_fingerprint_stable": gates["position_fingerprint_stable"],
        "open_order_fingerprint_stable": gates["open_order_fingerprint_stable"],
        "balance_fingerprint_stable": gates["balance_fingerprint_stable"],
        "open_order_count_zero_pre_post": gates["open_order_count_zero_pre_post"],
        "order_cancel_fill_trade_delta_zero": gates[
            "order_cancel_fill_trade_delta_zero"
        ],
        "remote_control_boundary_unchanged": gates["remote_control_boundary_unchanged"],
        "open_position_count_pre": account_delta.get("open_position_count_pre"),
        "open_position_count_post": account_delta.get("open_position_count_post"),
        "open_order_count_pre": account_delta.get("open_order_count_pre"),
        "open_order_count_post": account_delta.get("open_order_count_post"),
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
        "allowed_next_gate": P9CJ_GATE,
        "allowed_next_gate_scope": P9CJ_SCOPE,
        "allowed_next_gate_must_be_separately_requested": True,
        "source_evidence": {
            "phase9ch_summary": evidence_file(p9ch_path),
            "phase9ch_account_proof_execution_gate_terms": evidence_file(terms_path),
            "phase9ch_future_p9ci_acceptance_contract": evidence_file(future_contract_path),
            "phase9ch_non_authorization": evidence_file(p9ch_non_auth_path),
            "phase9ch_control_boundary": evidence_file(p9ch_control_path),
            "project_profile": evidence_file(project_profile_path),
        },
        "gates": gates,
        "output_files": {
            "summary": str(root / "summary.json"),
            "owner_decision_record": str(root / "owner_decision_record.json"),
            "command_records": str(root / "command_records.json"),
            "pre_control_snapshot": str(root / "pre_control_snapshot.json"),
            "post_control_snapshot": str(root / "post_control_snapshot.json"),
            "report": str(root / "p9ci_pit_safe_read_only_account_proof_v2v3.md"),
            "proof_artifact_manifest": str(proof_files["proof_artifact_manifest"]),
            **{key: str(path) for key, path in proof_files.items() if key != "proof_artifact_manifest"},
        },
    }
    write_json(root / "summary.json", summary)
    (root / "p9ci_pit_safe_read_only_account_proof_v2v3.md").write_text(
        render_markdown(summary),
        encoding="utf-8",
    )
    return summary, 0 if status == "ready" else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9CI PIT-Safe v2/v3 Account Proof",
        "",
        f"`Status: {summary['status']}`",
        "",
        "P9CI executes a PIT-safe v2/v3 read-only account proof through a remote stdout collector and local proof builder. It does not call order-test endpoints, write remote files, remote sync, invoke supervisor/timer paths, mutate live config/operator/executor state, execute the candidate, replace target plans, cancel orders, or submit orders.",
        "",
        "## Proof Result",
        "",
        "```text",
        "p9ci_pit_safe_read_only_account_proof_v2v3_ready = "
        f"{str(bool(summary['p9ci_pit_safe_read_only_account_proof_v2v3_ready'])).lower()}",
        "fresh_remote_account_read_performed = "
        f"{str(bool(summary['fresh_remote_account_read_performed'])).lower()}",
        "can_trade_decision_source = "
        f"{summary['can_trade_decision_source']}",
        "can_trade_pre = "
        f"{summary['can_trade_pre']}",
        "can_trade_post = "
        f"{summary['can_trade_post']}",
        "live_order_readiness_blockers = "
        + ",".join(summary["live_order_readiness_blockers"]),
        "eligible_to_clear_p9cf_account_can_trade_blocker = "
        f"{str(bool(summary['eligible_to_clear_p9cf_account_can_trade_blocker'])).lower()}",
        "prior_p9ce_blocker_reclassification = "
        f"{summary['prior_p9ce_blocker_reclassification']}",
        "```",
        "",
        "## No-Order Boundary",
        "",
        "```text",
        "order_test_endpoint_called = false",
        "remote_files_written = 0",
        "remote_sync_performed = false",
        "fresh_order_book_read_performed = false",
        "exchange_filter_read_performed = false",
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
        "## Allowed Next Gate",
        "",
        "```text",
        str(summary["allowed_next_gate"]),
        str(summary["allowed_next_gate_scope"]),
        "allowed_next_gate_must_be_separately_requested = true",
        "```",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_phase9ci(parse_args(argv))
    print(f"status={summary['status']}")
    print(f"summary={summary['output_files']['summary']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    print(
        "p9ci_pit_safe_read_only_account_proof_v2v3_ready="
        + str(bool(summary["p9ci_pit_safe_read_only_account_proof_v2v3_ready"])).lower()
    )
    print(f"can_trade_decision_source={summary['can_trade_decision_source']}")
    print(f"can_trade_pre={summary['can_trade_pre']}")
    print(f"can_trade_post={summary['can_trade_post']}")
    print(
        "live_order_readiness_blockers="
        + ",".join(summary["live_order_readiness_blockers"])
    )
    print("order_test_endpoint_called=false")
    print("orders_submitted=0")
    print("fill_count=0")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
