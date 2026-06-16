from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import sys
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
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
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9dc_define_approve_0_001_btcusdt_round_trip_canary_terms import (  # noqa: E402
    APPROVE_P9DC_DECISION,
    CANARY_QUANTITY,
    CANARY_SYMBOL,
    CONTRACT_VERSION as P9DC_CONTRACT,
    DEFAULT_OUTPUT_PARENT as P9DC_PARENT,
    MAX_GROSS_TURNOVER_USDT,
    MAX_NOTIONAL_PER_LEG_USDT,
    ORDER_TYPE,
    P9DD_GATE,
    P9DD_SCOPE,
    PRICE_COLLAR_BPS,
    TIME_IN_FORCE,
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


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9dd_execute_0_001_btcusdt_round_trip_canary.v1"
APPROVE_P9DD_DECISION = "approve_p9dd_execute_0_001_btcusdt_buy_then_reduce_only_sell_canary_only"
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/p9dd_0_001_btcusdt_round_trip_canary"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Execute P9DD: one BTCUSDT 0.001 BUY LIMIT IOC followed by one "
            "BTCUSDT 0.001 SELL LIMIT IOC reduce-only order, only after fresh "
            "remote readback and P9DC terms validation. This runner does not "
            "enter timer/supervisor/executor/candidate paths."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9dc-summary", default="")
    parser.add_argument("--remote-host", default=DEFAULT_REMOTE_HOST)
    parser.add_argument("--remote-repo", default=DEFAULT_REMOTE_REPO)
    parser.add_argument("--remote-config", default=DEFAULT_REMOTE_CONFIG)
    parser.add_argument("--remote-live-env", default=DEFAULT_REMOTE_LIVE_ENV)
    parser.add_argument("--remote-python", default=DEFAULT_REMOTE_PYTHON)
    parser.add_argument("--expected-egress-ip", default=DEFAULT_EXPECTED_EGRESS_IP)
    parser.add_argument("--ssh-connect-timeout", type=int, default=10)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9DD_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:p9dd_execute_0_001_btcusdt_buy_then_reduce_only_sell_canary",
    )
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def decimal_value(value: Any, default: str = "0") -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def fmt(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def phase_root(args: argparse.Namespace, run_id: str) -> Path:
    if str(args.output_root).strip():
        return resolve_path(args.output_root)
    return resolve_path(DEFAULT_OUTPUT_PARENT) / run_id


def latest_p9dc_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9dc_summary).strip():
        return resolve_path(args.phase9dc_summary)
    return latest_match(P9DC_PARENT, "*/summary.json")


def source_output_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("output_files") or {}).get(key) or "")
    return resolve_path(text) if text.strip() else Path("")


def p9dc_summary_ready(summary: dict[str, Any]) -> bool:
    return (
        summary.get("contract_version") == P9DC_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9dc_0_001_btcusdt_round_trip_canary_terms_ready") is True
        and summary.get("p9db_sufficient_for_p9dc_terms_gate") is True
        and summary.get("round_trip_terms_approved") is True
        and summary.get("eligible_for_future_p9dd_round_trip_canary_execution") is True
        and summary.get("live_order_submission_authorized") is True
        and summary.get("live_order_submission_performed") is False
        and summary.get("actual_live_order_submission_performed") is False
        and summary.get("authorization_scope")
        == "future_p9dd_0_001_btcusdt_buy_then_reduce_only_sell_canary_only"
        and summary.get("symbol") == CANARY_SYMBOL
        and decimal_value(summary.get("quantity_btc")) == CANARY_QUANTITY
        and decimal_value(summary.get("max_notional_per_leg_usdt")) == MAX_NOTIONAL_PER_LEG_USDT
        and decimal_value(summary.get("max_gross_turnover_usdt")) == MAX_GROSS_TURNOVER_USDT
        and int(summary.get("max_orders_total") or 0) == 2
        and int(summary.get("max_symbols_total") or 0) == 1
        and summary.get("order_type") == ORDER_TYPE
        and summary.get("time_in_force") == TIME_IN_FORCE
        and decimal_value(summary.get("price_collar_bps")) == PRICE_COLLAR_BPS
        and summary.get("market_orders_allowed") is False
        and summary.get("post_only_required") is False
        and summary.get("maker_only_required") is False
        and summary.get("taker_execution_allowed") is True
        and summary.get("sell_leg_reduce_only_required") is True
        and summary.get("emergency_reduce_only_market_fallback_allowed") is False
        and summary.get("pre_submit_fresh_readback_required_before_p9dd") is True
        and summary.get("post_position_must_equal_pre_position") is True
        and summary.get("remote_execution_performed") is False
        and summary.get("remote_sync_performed") is False
        and int_zero(summary, "remote_files_written")
        and int_zero(summary, "orders_submitted")
        and int_zero(summary, "orders_canceled")
        and int_zero(summary, "fill_count")
        and int_zero(summary, "trade_count")
        and summary.get("candidate_execution_authorized") is False
        and summary.get("target_plan_replacement_authorized") is False
        and summary.get("executor_input_mutation_authorized") is False
        and summary.get("timer_path_load_authorized") is False
        and summary.get("supervisor_invocation_authorized") is False
        and summary.get("allowed_next_gate") == P9DD_GATE
        and summary.get("allowed_next_gate_scope") == P9DD_SCOPE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
    )


def p9dc_terms_ready(terms: dict[str, Any]) -> bool:
    legs = [dict(row) for row in list(terms.get("legs") or []) if isinstance(row, dict)]
    post = dict(terms.get("post_submit_acceptance") or {})
    return (
        terms.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9dc_0_001_btcusdt_round_trip_canary_terms.v1"
        and terms.get("approval_decision") == APPROVE_P9DC_DECISION
        and terms.get("symbol") == CANARY_SYMBOL
        and decimal_value(terms.get("quantity_btc")) == CANARY_QUANTITY
        and decimal_value(terms.get("max_notional_per_leg_usdt")) == MAX_NOTIONAL_PER_LEG_USDT
        and decimal_value(terms.get("max_gross_turnover_usdt")) == MAX_GROSS_TURNOVER_USDT
        and int(terms.get("max_orders_total") or 0) == 2
        and int(terms.get("max_symbols_total") or 0) == 1
        and terms.get("order_type") == ORDER_TYPE
        and terms.get("time_in_force") == TIME_IN_FORCE
        and decimal_value(terms.get("price_collar_bps")) == PRICE_COLLAR_BPS
        and terms.get("market_orders_allowed") is False
        and terms.get("post_only_required") is False
        and terms.get("maker_only_required") is False
        and terms.get("taker_execution_allowed") is True
        and terms.get("emergency_reduce_only_market_fallback_allowed") is False
        and len(legs) == 2
        and legs[0].get("side") == "BUY"
        and legs[0].get("time_in_force") == TIME_IN_FORCE
        and legs[0].get("reduce_only") is False
        and decimal_value(legs[0].get("quantity")) == CANARY_QUANTITY
        and legs[1].get("side") == "SELL"
        and legs[1].get("time_in_force") == TIME_IN_FORCE
        and legs[1].get("reduce_only") is True
        and decimal_value(legs[1].get("quantity")) == CANARY_QUANTITY
        and post.get("orders_submitted_exactly") == 2
        and post.get("orders_canceled_exactly") == 0
        and decimal_value(post.get("buy_executed_qty_exact")) == CANARY_QUANTITY
        and decimal_value(post.get("sell_executed_qty_exact")) == CANARY_QUANTITY
        and post.get("sell_reduce_only_required") is True
        and post.get("post_open_orders_zero") is True
        and post.get("post_btcusdt_position_must_equal_pre_btcusdt_position") is True
        and post.get("remote_control_boundary_unchanged") is True
        and post.get("timer_path_loaded") is False
        and post.get("supervisor_invoked") is False
        and post.get("candidate_executed") is False
        and post.get("target_plan_replaced") is False
        and post.get("executor_input_mutated") is False
        and post.get("remote_sync_performed") is False
        and int(post.get("remote_files_written") or 0) == 0
        and terms.get("allowed_next_gate") == P9DD_GATE
        and terms.get("allowed_next_gate_scope") == P9DD_SCOPE
        and terms.get("allowed_next_gate_must_be_separately_requested") is True
    )


def owner_decision_record(args: argparse.Namespace, now: datetime) -> dict[str, Any]:
    approved = str(args.owner_decision) == APPROVE_P9DD_DECISION
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9dd_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "execute_one_0_001_btcusdt_buy_then_reduce_only_sell_canary_only",
        "recorded_at_utc": iso_z(now),
        "p9dd_round_trip_execution_approved": approved,
        "symbol": CANARY_SYMBOL,
        "quantity_btc": fmt(CANARY_QUANTITY),
        "max_notional_per_leg_usdt": fmt(MAX_NOTIONAL_PER_LEG_USDT),
        "max_gross_turnover_usdt": fmt(MAX_GROSS_TURNOVER_USDT),
        "max_orders": 2 if approved else 0,
        "order_type": ORDER_TYPE,
        "time_in_force": TIME_IN_FORCE,
        "market_orders_approved": False,
        "sell_reduce_only_required": True,
        "timer_path_load_approved": False,
        "supervisor_invocation_approved": False,
        "candidate_execution_approved": False,
        "target_plan_replacement_approved": False,
        "executor_input_mutation_approved": False,
    }


def remote_p9dd_round_trip_order_command(
    *,
    remote_repo: str,
    remote_live_env: str,
    remote_python: str,
    remote_config: str,
    expected_egress_ip: str,
    client_order_prefix: str,
    terms: dict[str, Any],
) -> str:
    payload = {
        "expected_egress_ip": expected_egress_ip,
        "remote_config": remote_config,
        "client_order_prefix": client_order_prefix,
        "terms": terms,
    }
    return f"""
cd {shlex.quote(remote_repo)}
{shlex.quote(remote_live_env)} /usr/bin/env PYTHONNOUSERSITE=1 {shlex.quote(remote_python)} - <<'PY'
import hashlib, hmac, json, os, pathlib, subprocess, sys, time, urllib.error, urllib.parse, urllib.request
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR

CONFIG = {json.dumps(payload, sort_keys=True)!r}
CFG = json.loads(CONFIG)
TERMS = CFG["terms"]
FAPI = "https://fapi.binance.com"
REPO_PATH = pathlib.Path({remote_repo!r})

def iso_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def sha(path):
    p = pathlib.Path(path)
    if not p.exists() or not p.is_file():
        return ""
    h = hashlib.sha256()
    with p.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def public_ip():
    try:
        with urllib.request.urlopen("https://api.ipify.org", timeout=15) as response:
            return response.read().decode().strip()
    except Exception as exc:
        return "unavailable:" + type(exc).__name__

def env_secret(name):
    return os.environ.get(name, "").strip()

def sign(params, secret):
    params = dict(params)
    params.setdefault("recvWindow", "5000")
    params.setdefault("timestamp", str(int(time.time() * 1000)))
    query = urllib.parse.urlencode(params)
    params["signature"] = hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()
    return params

def request(method, path, params=None, signed=False, api_key="", api_secret=""):
    params = {{k: str(v) for k, v in dict(params or {{}}).items() if v is not None}}
    if signed:
        params = sign(params, api_secret)
    query = urllib.parse.urlencode(params)
    url = FAPI + path
    data = None
    if method == "GET" and query:
        url += "?" + query
    elif query:
        data = query.encode()
    headers = {{"User-Agent": "Meridian/P9DD-round-trip-canary"}}
    if signed:
        headers["X-MBX-APIKEY"] = api_key
    started = iso_now()
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            raw = response.read().decode()
            return {{"status": "ok", "status_code": int(response.status), "started_at_utc": started, "finished_at_utc": iso_now(), "method": method, "path": path, "payload": json.loads(raw) if raw else {{}}}}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:1200]
        return {{"status": "failed", "status_code": int(exc.code), "started_at_utc": started, "finished_at_utc": iso_now(), "method": method, "path": path, "error": body}}
    except Exception as exc:
        return {{"status": "failed", "started_at_utc": started, "finished_at_utc": iso_now(), "method": method, "path": path, "error_type": type(exc).__name__, "error": str(exc)[:1200]}}

def dec(value, default="0"):
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal(default)

def floor_step(value, step):
    if step <= 0:
        return Decimal("0")
    return (value / step).to_integral_value(rounding=ROUND_FLOOR) * step

def ceil_step(value, step):
    if step <= 0:
        return Decimal("0")
    return (value / step).to_integral_value(rounding=ROUND_CEILING) * step

def fmt(value):
    s = format(value.normalize(), "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s or "0"

def rows(payload):
    return [dict(row) for row in list(payload or []) if isinstance(row, dict)]

def filter_row(exchange):
    for row in rows(exchange.get("symbols") or []):
        if row.get("symbol") == TERMS["symbol"]:
            return row
    return {{}}

def position_amt(account_payload):
    for row in rows(dict(account_payload or {{}}).get("positions") or []):
        if row.get("symbol") == TERMS["symbol"]:
            return dec(row.get("positionAmt"))
    return Decimal("0")

def open_order_count(open_orders_result):
    payload = open_orders_result.get("payload")
    return len(payload) if isinstance(payload, list) else -1

def small_history(api_key, api_secret):
    return {{
        "all_orders": request("GET", "/fapi/v1/allOrders", {{"symbol": TERMS["symbol"], "limit": "20"}}, True, api_key, api_secret),
        "user_trades": request("GET", "/fapi/v1/userTrades", {{"symbol": TERMS["symbol"], "limit": "20"}}, True, api_key, api_secret),
    }}

def build_plan(depth_payload, exchange_payload, side):
    blockers = []
    bids = depth_payload.get("bids") or []
    asks = depth_payload.get("asks") or []
    best_bid = dec(bids[0][0] if bids else "0")
    best_ask = dec(asks[0][0] if asks else "0")
    row = filter_row(exchange_payload)
    fmap = {{str(item.get("filterType")): dict(item) for item in rows(row.get("filters") or [])}}
    pfilter = fmap.get("PRICE_FILTER", {{}})
    lfilter = fmap.get("LOT_SIZE") or fmap.get("MARKET_LOT_SIZE") or {{}}
    nfilter = fmap.get("MIN_NOTIONAL", {{}})
    tick = dec(pfilter.get("tickSize"))
    step = dec(lfilter.get("stepSize"))
    min_qty = dec(lfilter.get("minQty"))
    min_notional = dec(nfilter.get("notional") or nfilter.get("minNotional"))
    qty = dec(TERMS["quantity_btc"])
    max_leg = dec(TERMS["max_notional_per_leg_usdt"])
    collar = dec(TERMS["price_collar_bps"]) / Decimal("10000")
    if row.get("status") != "TRADING":
        blockers.append("symbol_not_trading")
    if best_bid <= 0 or best_ask <= 0 or best_bid >= best_ask:
        blockers.append(f"invalid_spread:bid={{fmt(best_bid)}}:ask={{fmt(best_ask)}}")
    if tick <= 0:
        blockers.append("missing_tick_size")
    if step <= 0:
        blockers.append("missing_step_size")
    if qty < min_qty:
        blockers.append(f"quantity_below_min_qty:{{fmt(qty)}}<{{fmt(min_qty)}}")
    if floor_step(qty, step) != qty:
        blockers.append(f"quantity_not_on_step:{{fmt(qty)}}:step={{fmt(step)}}")
    if side == "BUY":
        price = ceil_step(best_ask * (Decimal("1") + collar), tick)
    else:
        price = floor_step(best_bid * (Decimal("1") - collar), tick)
    notional = price * qty
    minimum = max(min_notional, min_qty * price)
    if price <= 0:
        blockers.append("computed_price_not_positive")
    if notional < min_notional:
        blockers.append(f"computed_notional_below_min_notional:{{fmt(notional)}}<{{fmt(min_notional)}}")
    if notional > max_leg:
        blockers.append(f"computed_notional_above_max_per_leg:{{fmt(notional)}}>{{fmt(max_leg)}}")
    return {{"status": "ready" if not blockers else "blocked", "blockers": sorted(set(blockers)), "side": side, "price": fmt(price), "quantity": fmt(qty), "notional_usdt": fmt(notional), "best_bid": fmt(best_bid), "best_ask": fmt(best_ask), "tick_size": fmt(tick), "step_size": fmt(step), "min_qty": fmt(min_qty), "min_notional": fmt(min_notional), "minimum_executable_notional_usdt": fmt(minimum)}}

def query_order(api_key, api_secret, client_id):
    return request("GET", "/fapi/v1/order", {{"symbol": TERMS["symbol"], "origClientOrderId": client_id}}, True, api_key, api_secret)

def executed_qty(order_result):
    payload = order_result.get("payload") if isinstance(order_result.get("payload"), dict) else {{}}
    return dec(payload.get("executedQty"))

def order_status(order_result):
    payload = order_result.get("payload") if isinstance(order_result.get("payload"), dict) else {{}}
    return str(payload.get("status") or "")

def order_id(order_result):
    payload = order_result.get("payload") if isinstance(order_result.get("payload"), dict) else {{}}
    return str(payload.get("orderId") or "")

def count_trades_for_orders(history, ids):
    trades = history.get("user_trades", {{}}).get("payload")
    if not isinstance(trades, list):
        return 0
    idset = set(str(item) for item in ids if str(item))
    return len([row for row in trades if str(dict(row).get("orderId") or "") in idset])

started = iso_now()
blockers = []
api_key = env_secret("Trade")
api_secret = env_secret("Secret_Key")
if not api_key:
    blockers.append("missing_api_key_env:Trade")
if not api_secret:
    blockers.append("missing_api_secret_env:Secret_Key")
identity = {{"whoami": "", "hostname": "", "repo_path": str(REPO_PATH), "config_path": CFG["remote_config"], "egress_ip": public_ip(), "expected_egress_ip": CFG["expected_egress_ip"], "config_sha256": sha(CFG["remote_config"]), "live_supervisor_sha256": sha(REPO_PATH / "src/enhengclaw/live_trading/mainnet_live_supervisor.py")}}
try:
    identity["whoami"] = subprocess.check_output(["whoami"], text=True, timeout=10).strip()
    identity["hostname"] = subprocess.check_output(["hostname"], text=True, timeout=10).strip()
except Exception as exc:
    identity["identity_error"] = type(exc).__name__ + ":" + str(exc)[:200]
if identity["egress_ip"] != CFG["expected_egress_ip"]:
    blockers.append("egress_ip_mismatch")
if TERMS.get("symbol") != "BTCUSDT":
    blockers.append("terms_symbol_not_btcusdt")
if dec(TERMS.get("quantity_btc")) != Decimal("0.001"):
    blockers.append("terms_quantity_not_0_001")
if TERMS.get("time_in_force") != "IOC" or TERMS.get("market_orders_allowed") is not False:
    blockers.append("terms_not_limit_ioc_no_market")

pre = {{}}
post = {{}}
buy_submit = {{"status": "not_attempted"}}
buy_query = {{"status": "not_attempted"}}
sell_submit = {{"status": "not_attempted"}}
sell_query = {{"status": "not_attempted"}}
buy_plan = {{"status": "not_run", "blockers": []}}
sell_plan = {{"status": "not_run", "blockers": []}}
pre_position = Decimal("0")
post_position = Decimal("0")

if not blockers:
    account_v2 = request("GET", "/fapi/v2/account", {{}}, True, api_key, api_secret)
    account_v3 = request("GET", "/fapi/v3/account", {{}}, True, api_key, api_secret)
    position_mode = request("GET", "/fapi/v1/positionSide/dual", {{}}, True, api_key, api_secret)
    open_orders = request("GET", "/fapi/v1/openOrders", {{}}, True, api_key, api_secret)
    depth = request("GET", "/fapi/v1/depth", {{"symbol": TERMS["symbol"], "limit": "5"}}, False)
    exchange = request("GET", "/fapi/v1/exchangeInfo", {{}}, False)
    pre = {{"account_v2": account_v2, "account_v3": account_v3, "position_mode": position_mode, "open_orders": open_orders, "depth": depth, "exchange_info": exchange, "history": small_history(api_key, api_secret)}}
    if account_v2.get("status") != "ok" or account_v2.get("payload", {{}}).get("canTrade") is not True:
        blockers.append("can_trade_not_true_from_fapi_v2_account")
    if position_mode.get("status") != "ok" or position_mode.get("payload", {{}}).get("dualSidePosition") is not False:
        blockers.append("position_mode_not_one_way")
    if open_orders.get("status") != "ok":
        blockers.append("open_orders_read_failed")
    elif open_order_count(open_orders) != 0:
        blockers.append(f"pre_submit_open_orders_exist:{{open_order_count(open_orders)}}")
    pre_position = position_amt(account_v2.get("payload") or {{}})
    if pre_position < 0:
        blockers.append(f"pre_btcusdt_position_negative_not_allowed:{{fmt(pre_position)}}")
    buy_plan = build_plan(depth.get("payload") or {{}}, exchange.get("payload") or {{}}, "BUY")
    blockers.extend(buy_plan["blockers"])

buy_client_id = CFG["client_order_prefix"] + "-buy"
sell_client_id = CFG["client_order_prefix"] + "-sell"
if not blockers:
    buy_submit = request("POST", "/fapi/v1/order", {{"symbol": TERMS["symbol"], "side": "BUY", "positionSide": "BOTH", "type": "LIMIT", "timeInForce": "IOC", "quantity": buy_plan["quantity"], "price": buy_plan["price"], "newClientOrderId": buy_client_id, "newOrderRespType": "RESULT"}}, True, api_key, api_secret)
    if buy_submit.get("status") != "ok":
        blockers.append("buy_order_submit_failed")
    buy_query = query_order(api_key, api_secret, buy_client_id) if buy_submit.get("status") == "ok" else {{"status": "not_attempted"}}
    if buy_submit.get("status") == "ok" and buy_query.get("status") != "ok":
        blockers.append("buy_order_query_failed")
    buy_fill = executed_qty(buy_query if buy_query.get("status") == "ok" else buy_submit)
    if buy_fill != dec(TERMS["quantity_btc"]):
        blockers.append(f"buy_executed_qty_not_exact:{{fmt(buy_fill)}}")
    if order_status(buy_query if buy_query.get("status") == "ok" else buy_submit) != "FILLED":
        blockers.append("buy_order_status_not_filled")

if not blockers:
    sell_depth = request("GET", "/fapi/v1/depth", {{"symbol": TERMS["symbol"], "limit": "5"}}, False)
    exchange2 = request("GET", "/fapi/v1/exchangeInfo", {{}}, False)
    sell_plan = build_plan(sell_depth.get("payload") or {{}}, exchange2.get("payload") or {{}}, "SELL")
    blockers.extend(sell_plan["blockers"])
    if not blockers:
        sell_submit = request("POST", "/fapi/v1/order", {{"symbol": TERMS["symbol"], "side": "SELL", "positionSide": "BOTH", "type": "LIMIT", "timeInForce": "IOC", "quantity": sell_plan["quantity"], "price": sell_plan["price"], "reduceOnly": "true", "newClientOrderId": sell_client_id, "newOrderRespType": "RESULT"}}, True, api_key, api_secret)
        if sell_submit.get("status") != "ok":
            blockers.append("sell_reduce_only_order_submit_failed")
        sell_query = query_order(api_key, api_secret, sell_client_id) if sell_submit.get("status") == "ok" else {{"status": "not_attempted"}}
        if sell_submit.get("status") == "ok" and sell_query.get("status") != "ok":
            blockers.append("sell_order_query_failed")
        sell_fill = executed_qty(sell_query if sell_query.get("status") == "ok" else sell_submit)
        if sell_fill != dec(TERMS["quantity_btc"]):
            blockers.append(f"sell_executed_qty_not_exact:{{fmt(sell_fill)}}")
        if order_status(sell_query if sell_query.get("status") == "ok" else sell_submit) != "FILLED":
            blockers.append("sell_order_status_not_filled")

if api_key and api_secret:
    post = {{"account_v2": request("GET", "/fapi/v2/account", {{}}, True, api_key, api_secret), "account_v3": request("GET", "/fapi/v3/account", {{}}, True, api_key, api_secret), "open_orders": request("GET", "/fapi/v1/openOrders", {{}}, True, api_key, api_secret), "history": small_history(api_key, api_secret)}}
    post_position = position_amt(post.get("account_v2", {{}}).get("payload") or {{}})
    if post.get("open_orders", {{}}).get("status") != "ok" or open_order_count(post.get("open_orders", {{}})) != 0:
        blockers.append("post_open_orders_not_zero")
    if post_position != pre_position:
        blockers.append(f"post_position_not_equal_pre:pre={{fmt(pre_position)}}:post={{fmt(post_position)}}")
    order_ids = [order_id(buy_query), order_id(sell_query)]
    trade_count = count_trades_for_orders(post.get("history", {{}}), order_ids)
    if buy_submit.get("status") == "ok" and sell_submit.get("status") == "ok" and trade_count < 2:
        time.sleep(2)
        post["history_retry"] = small_history(api_key, api_secret)
        trade_count = max(trade_count, count_trades_for_orders(post.get("history_retry", {{}}), order_ids))
else:
    trade_count = 0

buy_fill_final = executed_qty(buy_query if buy_query.get("status") == "ok" else buy_submit)
sell_fill_final = executed_qty(sell_query if sell_query.get("status") == "ok" else sell_submit)
orders_submitted = (1 if buy_submit.get("status") == "ok" else 0) + (1 if sell_submit.get("status") == "ok" else 0)
fill_count = (1 if buy_fill_final == dec(TERMS.get("quantity_btc")) else 0) + (1 if sell_fill_final == dec(TERMS.get("quantity_btc")) else 0)
if orders_submitted == 2 and trade_count < 2:
    blockers.append(f"trade_count_less_than_two:{{trade_count}}")
gross = dec(buy_plan.get("notional_usdt")) + dec(sell_plan.get("notional_usdt"))
if gross > dec(TERMS.get("max_gross_turnover_usdt")):
    blockers.append(f"gross_turnover_above_max:{{fmt(gross)}}>{{TERMS.get('max_gross_turnover_usdt')}}")

summary = {{"contract_version": "hv_balanced_dth60_coinglass_phase9dd_remote_round_trip_canary_submitter.v1", "started_at_utc": started, "finished_at_utc": iso_now(), "status": "ready" if not blockers and orders_submitted == 2 and fill_count == 2 and post_position == pre_position else "blocked", "blockers": sorted(set(blockers)), "remote_runner_identity_readback": identity, "symbol": TERMS["symbol"], "quantity_btc": TERMS["quantity_btc"], "max_notional_per_leg_usdt": TERMS["max_notional_per_leg_usdt"], "max_gross_turnover_usdt": TERMS["max_gross_turnover_usdt"], "buy_client_order_id": buy_client_id, "sell_client_order_id": sell_client_id, "pre_submit_readback": pre, "buy_order_plan": buy_plan, "buy_order_submission": buy_submit, "buy_order_query": buy_query, "sell_order_plan": sell_plan, "sell_order_submission": sell_submit, "sell_order_query": sell_query, "post_submit_readback": post, "pre_btcusdt_position_amt": fmt(pre_position), "post_btcusdt_position_amt": fmt(post_position), "post_position_equals_pre": post_position == pre_position, "orders_submitted": orders_submitted, "orders_canceled": 0, "buy_executed_qty": fmt(buy_fill_final), "sell_executed_qty": fmt(sell_fill_final), "fill_count": fill_count, "trade_count": trade_count, "gross_turnover_usdt": fmt(gross), "side_effects": {{"http_methods_used": ["GET", "POST"], "orders_submitted": orders_submitted, "orders_canceled": 0, "fill_count": fill_count, "trade_count": trade_count, "remote_files_written": 0, "remote_sync_performed": False, "supervisor_invoked": False, "timer_path_invoked": False, "candidate_executed": False, "executor_input_mutated": False, "target_plan_replaced": False, "order_test_endpoint_called": False}}}}
print(json.dumps(summary, indent=2, sort_keys=True))
PY
"""


def remote_submission_ready(submission: dict[str, Any]) -> bool:
    side_effects = dict(submission.get("side_effects") or {})
    return (
        submission.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9dd_remote_round_trip_canary_submitter.v1"
        and submission.get("status") == "ready"
        and not submission.get("blockers")
        and submission.get("symbol") == CANARY_SYMBOL
        and decimal_value(submission.get("quantity_btc")) == CANARY_QUANTITY
        and decimal_value(submission.get("max_notional_per_leg_usdt")) == MAX_NOTIONAL_PER_LEG_USDT
        and decimal_value(submission.get("max_gross_turnover_usdt")) == MAX_GROSS_TURNOVER_USDT
        and decimal_value(submission.get("buy_executed_qty")) == CANARY_QUANTITY
        and decimal_value(submission.get("sell_executed_qty")) == CANARY_QUANTITY
        and submission.get("post_position_equals_pre") is True
        and int(submission.get("orders_submitted") or 0) == 2
        and int(submission.get("orders_canceled") or 0) == 0
        and int(submission.get("fill_count") or 0) == 2
        and int(submission.get("trade_count") or 0) >= 2
        and decimal_value(submission.get("gross_turnover_usdt")) <= MAX_GROSS_TURNOVER_USDT
        and set(str(item).upper() for item in list(side_effects.get("http_methods_used") or []))
        == {"GET", "POST"}
        and int(side_effects.get("remote_files_written") or 0) == 0
        and side_effects.get("remote_sync_performed") is False
        and side_effects.get("supervisor_invoked") is False
        and side_effects.get("timer_path_invoked") is False
        and side_effects.get("candidate_executed") is False
        and side_effects.get("executor_input_mutated") is False
        and side_effects.get("target_plan_replaced") is False
        and side_effects.get("order_test_endpoint_called") is False
    )


def build_phase9dd(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
    command_runner: CommandRunner = local_command_runner,
) -> tuple[dict[str, Any], int]:
    started_at = now_fn()
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9dd" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    p9dc_path = latest_p9dc_summary(args)
    p9dc = load_optional(p9dc_path)
    terms_path = source_output_path(p9dc, "approved_round_trip_terms")
    terms = load_optional(terms_path)
    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)
    owner_record = owner_decision_record(args, started_at)
    write_json(root / "owner_decision_record.json", owner_record)

    gates = {
        "owner_decision_p9dd_execution_recorded": str(args.owner_decision) == APPROVE_P9DD_DECISION,
        "project_profile_exists": bool(project_profile),
        "current_stage_is_stage3": str(project_profile.get("current_stage") or "")
        == "stage_3_human_approved_execution",
        "p9dc_summary_exists": bool(p9dc),
        "p9dc_summary_ready_for_p9dd": p9dc_summary_ready(p9dc),
        "p9dc_terms_ready_for_p9dd": p9dc_terms_ready(terms),
        "remote_host_matches_expected_runner": str(args.remote_host) == DEFAULT_REMOTE_HOST,
        "remote_repo_matches_expected_runner": str(args.remote_repo) == DEFAULT_REMOTE_REPO,
    }
    blockers = [key for key, value in gates.items() if not value]
    command_records: list[dict[str, Any]] = []
    pre_snapshot: dict[str, Any] = {}
    post_snapshot: dict[str, Any] = {}
    submission: dict[str, Any] = {}

    def run_record(label: str, cmd: Sequence[str]) -> CommandResult:
        result = command_runner(cmd)
        command_records.append(
            {
                "label": label,
                "args": list(cmd),
                "returncode": int(result.returncode),
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

    client_prefix = f"p9dd-{started_at.strftime('%Y%m%d%H%M%S')}-{sha256_text(str(root))[:8]}"
    if not blockers:
        order_result = run_record(
            "remote_round_trip_canary_order_submitter",
            ssh_args(
                args.remote_host,
                args.ssh_connect_timeout,
                remote_p9dd_round_trip_order_command(
                    remote_repo=args.remote_repo,
                    remote_live_env=args.remote_live_env,
                    remote_python=args.remote_python,
                    remote_config=args.remote_config,
                    expected_egress_ip=args.expected_egress_ip,
                    client_order_prefix=client_prefix,
                    terms=terms,
                ),
            ),
        )
        submission = json_from_command(order_result)
        write_json(root / "remote_round_trip_canary_order_submission.json", submission)
        if order_result.returncode != 0:
            blockers.append("remote_round_trip_canary_order_submitter_failed")
        if not remote_submission_ready(submission):
            blockers.append("remote_round_trip_canary_order_submitter_not_ready")

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

    remote_control_unchanged = bool(pre_snapshot and post_snapshot) and snapshot_boundary_ok(
        pre_snapshot, post_snapshot
    )
    if pre_snapshot and post_snapshot and timer_state_digest(pre_snapshot) != timer_state_digest(post_snapshot):
        blockers.append("timer_state_changed")

    orders_submitted = int(submission.get("orders_submitted") or 0)
    orders_canceled = int(submission.get("orders_canceled") or 0)
    fill_count = int(submission.get("fill_count") or 0)
    trade_count = int(submission.get("trade_count") or 0)
    if remote_control_unchanged is not True and pre_snapshot and post_snapshot:
        blockers.append("remote_control_boundary_not_unchanged")
    status = "ready" if not blockers and remote_submission_ready(submission) and remote_control_unchanged else "blocked"
    blockers = sorted(set(blockers + list(submission.get("blockers") or [])))

    control = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9dd_control_boundary.v1",
        "scope": "0_001_btcusdt_limit_ioc_round_trip_canary_only",
        "ssh_invoked": bool(command_records),
        "remote_network_connection_performed": bool(command_records),
        "fresh_remote_account_read_performed": bool(submission.get("pre_submit_readback")),
        "fresh_order_book_read_performed": bool(
            dict(submission.get("pre_submit_readback") or {}).get("depth")
        ),
        "exchange_filter_read_performed": bool(
            dict(submission.get("pre_submit_readback") or {}).get("exchange_info")
        ),
        "order_test_endpoint_called": False,
        "live_order_submission_performed": orders_submitted == 2,
        "orders_submitted": orders_submitted,
        "orders_canceled": orders_canceled,
        "fill_count": fill_count,
        "trade_count": trade_count,
        "entered_timer_path": False,
        "ran_supervisor": False,
        "timer_path_loaded": False,
        "candidate_execution_performed": False,
        "target_plan_replaced": False,
        "executor_input_changed": False,
        "live_config_changed": bool(pre_snapshot and post_snapshot)
        and pre_snapshot.get("remote_live_config_sha256") != post_snapshot.get("remote_live_config_sha256"),
        "operator_state_changed": bool(pre_snapshot and post_snapshot)
        and pre_snapshot.get("operator_state") != post_snapshot.get("operator_state"),
        "timer_state_changed": bool(pre_snapshot and post_snapshot)
        and timer_state_digest(pre_snapshot) != timer_state_digest(post_snapshot),
        "remote_files_written": 0,
        "remote_sync_performed": False,
    }
    non_auth = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9dd_non_authorization.v1",
        "authorizations": {
            "0_001_btcusdt_round_trip_canary": str(args.owner_decision) == APPROVE_P9DD_DECISION,
            "symbol": CANARY_SYMBOL,
            "quantity_btc": fmt(CANARY_QUANTITY),
            "max_orders": 2,
            "max_notional_per_leg_usdt": fmt(MAX_NOTIONAL_PER_LEG_USDT),
            "max_gross_turnover_usdt": fmt(MAX_GROSS_TURNOVER_USDT),
            "market_order": False,
            "emergency_market_fallback": False,
            "additional_symbols": False,
            "additional_orders": False,
            "timer_path_load": False,
            "supervisor_invocation": False,
            "candidate_execution": False,
            "target_plan_replacement": False,
            "executor_input_mutation": False,
            "stage_governance_change": False,
        },
    }

    proof_files = {
        "approved_round_trip_terms": terms_path,
        "remote_round_trip_canary_order_submission": root
        / "remote_round_trip_canary_order_submission.json",
        "control_boundary_readback": proof_root / "control_boundary_readback.json",
        "non_authorization": proof_root / "non_authorization.json",
        "owner_decision_record": root / "owner_decision_record.json",
    }
    write_json(proof_files["control_boundary_readback"], control)
    write_json(proof_files["non_authorization"], non_auth)
    write_json(root / "command_records.json", {"commands": command_records})
    manifest_path = proof_root / "proof_artifact_manifest.json"
    manifest = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9dd_proof_artifact_manifest.v1",
        "artifact_count": len(proof_files),
        "artifacts": {key: evidence_file(path) for key, path in sorted(proof_files.items())},
    }
    write_json(manifest_path, manifest)
    manifest["self"] = evidence_file(manifest_path)
    write_json(manifest_path, manifest)

    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "status": status,
        "blockers": blockers,
        "p9dd_0_001_btcusdt_round_trip_canary_ready": status == "ready",
        "p9dc_sufficient_for_p9dd_execution": p9dc_summary_ready(p9dc)
        and p9dc_terms_ready(terms),
        "fresh_pre_submit_readback_performed": bool(submission.get("pre_submit_readback")),
        "fresh_remote_account_read_performed": bool(
            dict(submission.get("pre_submit_readback") or {}).get("account_v2")
        ),
        "fresh_order_book_read_performed": control["fresh_order_book_read_performed"],
        "exchange_filter_read_performed": control["exchange_filter_read_performed"],
        "can_trade_decision_source": "/fapi/v2/account.canTrade",
        "live_order_submission_authorized": True,
        "live_order_submission_performed": orders_submitted == 2,
        "actual_live_order_submission_performed": orders_submitted == 2,
        "orders_submitted": orders_submitted,
        "orders_canceled": orders_canceled,
        "buy_executed_qty": submission.get("buy_executed_qty", "0"),
        "sell_executed_qty": submission.get("sell_executed_qty", "0"),
        "fill_count": fill_count,
        "trade_count": trade_count,
        "pre_btcusdt_position_amt": submission.get("pre_btcusdt_position_amt", ""),
        "post_btcusdt_position_amt": submission.get("post_btcusdt_position_amt", ""),
        "post_position_equals_pre": submission.get("post_position_equals_pre") is True,
        "gross_turnover_usdt": submission.get("gross_turnover_usdt", "0"),
        "max_notional_per_leg_usdt": float(MAX_NOTIONAL_PER_LEG_USDT),
        "max_gross_turnover_usdt": float(MAX_GROSS_TURNOVER_USDT),
        "quantity_btc": float(CANARY_QUANTITY),
        "symbol": CANARY_SYMBOL,
        "order_type": ORDER_TYPE,
        "time_in_force": TIME_IN_FORCE,
        "market_orders_allowed": False,
        "sell_leg_reduce_only_required": True,
        "remote_control_boundary_unchanged": remote_control_unchanged,
        "remote_sync_performed": False,
        "remote_files_written": 0,
        "order_test_endpoint_called": False,
        "candidate_execution_performed": False,
        "target_plan_replaced": False,
        "executor_input_mutated": False,
        "timer_path_loaded": False,
        "supervisor_invoked": False,
        "source_evidence": {
            "phase9dc_summary": evidence_file(p9dc_path),
            "phase9dc_terms": evidence_file(terms_path),
            "project_profile": evidence_file(project_profile_path),
        },
        "gates": gates,
        "output_files": {
            "summary": str(root / "summary.json"),
            "report": str(root / "p9dd_0_001_btcusdt_round_trip_canary.md"),
            "command_records": str(root / "command_records.json"),
            "pre_control_snapshot": str(root / "pre_control_snapshot.json"),
            "post_control_snapshot": str(root / "post_control_snapshot.json"),
            "proof_artifact_manifest": str(manifest_path),
            **{key: str(path) for key, path in proof_files.items()},
        },
    }
    write_json(root / "summary.json", summary)
    (root / "p9dd_0_001_btcusdt_round_trip_canary.md").write_text(
        render_markdown(summary), encoding="utf-8"
    )
    return summary, 0 if status == "ready" else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9DD 0.001 BTCUSDT Round-Trip Canary",
        "",
        f"`Status: {summary['status']}`",
        "",
        "P9DD is scoped to one 0.001 BTCUSDT buy and one 0.001 BTCUSDT reduce-only sell using LIMIT IOC orders.",
        "",
        "```text",
        f"fresh_pre_submit_readback_performed = {str(bool(summary['fresh_pre_submit_readback_performed'])).lower()}",
        f"orders_submitted = {summary['orders_submitted']}",
        f"buy_executed_qty = {summary['buy_executed_qty']}",
        f"sell_executed_qty = {summary['sell_executed_qty']}",
        f"fill_count = {summary['fill_count']}",
        f"trade_count = {summary['trade_count']}",
        f"pre_btcusdt_position_amt = {summary['pre_btcusdt_position_amt']}",
        f"post_btcusdt_position_amt = {summary['post_btcusdt_position_amt']}",
        f"post_position_equals_pre = {str(bool(summary['post_position_equals_pre'])).lower()}",
        f"remote_control_boundary_unchanged = {str(bool(summary['remote_control_boundary_unchanged'])).lower()}",
        "timer_path_loaded = false",
        "supervisor_invoked = false",
        "candidate_execution_performed = false",
        "target_plan_replaced = false",
        "executor_input_mutated = false",
        "```",
        "",
        "## Blockers",
        "",
    ]
    blockers = list(summary.get("blockers") or [])
    lines.extend([f"- `{item}`" for item in blockers] if blockers else ["- none"])
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_phase9dd(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
