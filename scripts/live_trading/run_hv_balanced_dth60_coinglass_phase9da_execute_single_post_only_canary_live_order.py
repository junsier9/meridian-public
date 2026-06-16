from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, ROUND_FLOOR, InvalidOperation
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
    CAN_TRADE_SOURCE,
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
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ce_read_only_fresh_remote_proof_collection import (  # noqa: E402
    collector_ready as p9ce_collector_ready,
    fingerprint_delta_acceptance as p9ce_fingerprint_delta_acceptance,
    remote_identity_ready as p9ce_remote_identity_ready,
    remote_p9ce_collector_command,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ci_pit_safe_read_only_account_proof_v2v3 import (  # noqa: E402
    account_delta_acceptance,
    collector_contract_ready as p9ci_collector_ready,
    history_delta_acceptance,
    remote_identity_ready as p9ci_remote_identity_ready,
    remote_p9ci_collector_command,
    sanitized_collector as sanitize_p9ci_collector,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cz_final_owner_live_order_decision_gate import (  # noqa: E402
    CONTRACT_VERSION as P9CZ_CONTRACT,
    DEFAULT_OUTPUT_PARENT as P9CZ_PARENT,
    P9DA_GATE,
    P9DA_SCOPE,
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


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9da_single_post_only_canary_live_order.v1"
APPROVE_P9DA_DECISION = "approve_p9da_execute_single_post_only_canary_live_order_only"
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/p9da_single_post_only_canary_live_order"
P9DB_GATE = "P9DB_review_p9da_single_post_only_canary_live_order_only_if_separately_requested"
P9DB_SCOPE = (
    "review_p9da_single_post_only_canary_retained_evidence_before_any_next_live_order_or_broader_candidate_execution"
)
CANARY_SYMBOL = "BTCUSDT"
CANARY_SIDE = "BUY"
MAX_NOTIONAL_USDT = Decimal("10")
RISK_CEILING_USDT = Decimal("25")
TIME_IN_FORCE = "GTX"
ORDER_TYPE = "post_only_limit"


@dataclass(frozen=True, slots=True)
class CanaryOrderPlan:
    status: str
    blockers: list[str]
    symbol: str
    side: str
    price: str
    quantity: str
    notional_usdt: str
    best_bid: str
    best_ask: str
    tick_size: str
    step_size: str
    min_qty: str
    min_notional: str
    minimum_executable_notional_usdt: str
    limit_order_must_not_cross_spread: bool
    post_only_time_in_force: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": "hv_balanced_dth60_coinglass_phase9da_canary_order_plan.v1",
            "status": self.status,
            "blockers": self.blockers,
            "symbol": self.symbol,
            "side": self.side,
            "price": self.price,
            "quantity": self.quantity,
            "notional_usdt": self.notional_usdt,
            "best_bid": self.best_bid,
            "best_ask": self.best_ask,
            "tick_size": self.tick_size,
            "step_size": self.step_size,
            "min_qty": self.min_qty,
            "min_notional": self.min_notional,
            "minimum_executable_notional_usdt": self.minimum_executable_notional_usdt,
            "max_notional_usdt": str(MAX_NOTIONAL_USDT),
            "risk_ceiling_usdt": str(RISK_CEILING_USDT),
            "limit_order_must_not_cross_spread": self.limit_order_must_not_cross_spread,
            "order_type": ORDER_TYPE,
            "time_in_force": self.post_only_time_in_force,
            "market_orders_allowed": False,
            "post_only_required": True,
            "maker_only_required": True,
        }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Execute P9DA: one BTCUSDT BUY post-only GTX canary order only after "
            "fresh pre-submit readback. The runner fails closed if the approved "
            "10 USDT max notional cannot satisfy current exchange filters."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9cz-summary", default="")
    parser.add_argument("--remote-host", default=DEFAULT_REMOTE_HOST)
    parser.add_argument("--remote-repo", default=DEFAULT_REMOTE_REPO)
    parser.add_argument("--remote-config", default=DEFAULT_REMOTE_CONFIG)
    parser.add_argument("--remote-live-env", default=DEFAULT_REMOTE_LIVE_ENV)
    parser.add_argument("--remote-python", default=DEFAULT_REMOTE_PYTHON)
    parser.add_argument("--expected-egress-ip", default=DEFAULT_EXPECTED_EGRESS_IP)
    parser.add_argument("--canary-symbol", default=CANARY_SYMBOL)
    parser.add_argument("--canary-side", default=CANARY_SIDE)
    parser.add_argument("--max-history-symbols", type=int, default=20)
    parser.add_argument("--ssh-connect-timeout", type=int, default=10)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9DA_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:p9da_execute_single_post_only_canary_live_order_only_if_separately_requested",
    )
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def phase_root(args: argparse.Namespace, run_id: str) -> Path:
    if str(args.output_root).strip():
        return resolve_path(args.output_root)
    return resolve_path(DEFAULT_OUTPUT_PARENT) / run_id


def latest_p9cz_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9cz_summary).strip():
        return resolve_path(args.phase9cz_summary)
    return latest_match(P9CZ_PARENT, "*/summary.json")


def source_output_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("output_files") or {}).get(key) or "")
    return resolve_path(text) if text.strip() else Path("")


def p9cz_summary_ready(summary: dict[str, Any]) -> bool:
    return (
        summary.get("contract_version") == P9CZ_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9cz_final_owner_live_order_decision_gate_ready") is True
        and summary.get("p9cz_satisfies_final_owner_live_order_decision_gate") is True
        and summary.get("final_owner_live_order_gate_approval_collected") is True
        and summary.get("explicit_final_owner_live_order_decision_collected") is True
        and summary.get("live_order_submission_authorized") is True
        and summary.get("candidate_enter_executor_target_plan_path_authorized") is True
        and summary.get("target_plan_replacement_authorized") is True
        and summary.get("candidate_execution_authorized") is True
        and summary.get("authorization_scope") == "future_p9da_single_post_only_canary_only"
        and summary.get("eligible_for_future_p9da_single_post_only_canary_execution") is True
        and summary.get("fresh_pre_submit_readback_required_before_p9da") is True
        and summary.get("allowed_next_gate") == P9DA_GATE
        and summary.get("allowed_next_gate_scope") == P9DA_SCOPE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
        and summary.get("canary_symbol") == CANARY_SYMBOL
        and summary.get("canary_side") == CANARY_SIDE
        and Decimal(str(summary.get("max_notional_usdt") or "0")) == MAX_NOTIONAL_USDT
        and Decimal(str(summary.get("risk_ceiling_usdt") or "0")) == RISK_CEILING_USDT
        and int(summary.get("max_orders_per_cycle") or 0) == 1
        and int(summary.get("max_symbols_per_cycle") or 0) == 1
        and summary.get("order_type") == ORDER_TYPE
        and summary.get("time_in_force") == TIME_IN_FORCE
        and summary.get("market_orders_allowed") is False
        and summary.get("post_only_required") is True
        and summary.get("maker_only_required") is True
        and summary.get("limit_order_must_not_cross_spread") is True
        and summary.get("only_distance_to_high_60_contribution_changed") is True
        and summary.get("actual_live_order_submission_performed") is False
        and summary.get("remote_execution_performed") is False
        and int_zero(summary, "orders_submitted")
        and int_zero(summary, "orders_canceled")
        and int_zero(summary, "fill_count")
        and int_zero(summary, "trade_count")
    )


def p9cz_terms_ready(terms: dict[str, Any], summary: dict[str, Any]) -> bool:
    return (
        terms.get("contract_version") == "hv_balanced_dth60_coinglass_phase9cz_approved_single_canary_terms.v1"
        and terms.get("symbol") == CANARY_SYMBOL
        and terms.get("side") == CANARY_SIDE
        and Decimal(str(terms.get("max_notional_usdt") or "0")) == MAX_NOTIONAL_USDT
        and Decimal(str(terms.get("risk_ceiling_usdt") or "0")) == RISK_CEILING_USDT
        and int(terms.get("max_orders_per_cycle") or 0) == 1
        and int(terms.get("max_symbols_per_cycle") or 0) == 1
        and terms.get("order_type") == ORDER_TYPE
        and terms.get("time_in_force") == TIME_IN_FORCE
        and terms.get("market_orders_allowed") is False
        and terms.get("post_only_required") is True
        and terms.get("maker_only_required") is True
        and terms.get("limit_order_must_not_cross_spread") is True
        and terms.get("candidate_delta_source") == "distance_to_high_60_contribution_only"
        and terms.get("only_distance_to_high_60_contribution_changed") is True
        and bool(terms.get("baseline_target_plan_sha256"))
        and bool(terms.get("candidate_target_plan_sha256"))
        and terms.get("candidate_target_plan_sha256") == summary.get("candidate_target_plan_sha256")
    )


def pre_submit_requirements_ready(requirements: dict[str, Any]) -> bool:
    required = set(str(item) for item in list(requirements.get("required_before_any_future_order_submission") or []))
    return (
        requirements.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cz_pre_submit_requirements_for_p9da.v1"
        and int(requirements.get("fresh_pre_submit_readback_max_age_seconds") or 0) == 30
        and int(requirements.get("order_lifetime_seconds") or 0) == 60
        and int(requirements.get("candidate_artifact_stale_after_seconds") or 0) == 60
        and requirements.get("cancel_if_not_maker_or_unexpected_delta") is True
        and {
            "fresh pre-submit account read using /fapi/v2/account.canTrade",
            "fresh pre-submit position and open-order fingerprint",
            "fresh pre-submit order/fill/trade delta fingerprint",
            "fresh order book and exchange filter readback",
            "post-only GTX limit price must not cross spread",
            "kill switch readable and rollback path documented",
            "candidate target plan hash must match approved P9CZ candidate hash",
            "executor input replacement must be scoped to one canary cycle only",
        }.issubset(required)
    )


def owner_decision_record(args: argparse.Namespace, now: datetime) -> dict[str, Any]:
    approved = str(args.owner_decision) == APPROVE_P9DA_DECISION
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9da_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "execute_single_post_only_canary_live_order_only",
        "recorded_at_utc": iso_z(now),
        "p9da_single_post_only_canary_execution_approved": approved,
        "max_orders_approved": 1 if approved else 0,
        "symbol": CANARY_SYMBOL,
        "side": CANARY_SIDE,
        "order_type": ORDER_TYPE,
        "time_in_force": TIME_IN_FORCE,
        "max_notional_usdt": str(MAX_NOTIONAL_USDT),
        "market_orders_approved": False,
        "post_only_required": True,
        "maker_only_required": True,
        "submit_even_if_exchange_filters_exceed_approved_notional": False,
        "timer_path_load_approved": False,
        "supervisor_invocation_approved": False,
        "stage_governance_change_approved": False,
    }


def build_canary_order_plan(
    fresh_book: dict[str, Any],
    exchange_filters: dict[str, Any],
    terms: dict[str, Any],
) -> CanaryOrderPlan:
    blockers: list[str] = []
    book = dict(fresh_book.get("book") or {})
    best_bid = _book_price(book.get("best_bid"))
    best_ask = _book_price(book.get("best_ask"))
    symbol_row = _symbol_filter_row(exchange_filters, CANARY_SYMBOL)
    filter_map = {
        str(item.get("filterType")): dict(item)
        for item in list(symbol_row.get("filters") or [])
        if isinstance(item, dict)
    }
    price_filter = filter_map.get("PRICE_FILTER", {})
    lot_filter = filter_map.get("LOT_SIZE") or filter_map.get("MARKET_LOT_SIZE") or {}
    min_notional_filter = filter_map.get("MIN_NOTIONAL", {})
    tick = _decimal(price_filter.get("tickSize"), "0")
    min_price = _decimal(price_filter.get("minPrice"), "0")
    step = _decimal(lot_filter.get("stepSize"), "0")
    min_qty = _decimal(lot_filter.get("minQty"), "0")
    min_notional = _decimal(min_notional_filter.get("notional") or min_notional_filter.get("minNotional"), "0")
    max_notional = Decimal(str(terms.get("max_notional_usdt") or MAX_NOTIONAL_USDT))

    if fresh_book.get("status") != "ready":
        blockers.append("fresh_order_book_not_ready")
    if exchange_filters.get("status") != "ready":
        blockers.append("exchange_filter_readback_not_ready")
    if not symbol_row:
        blockers.append("canary_symbol_missing_from_exchange_filters")
    if symbol_row and symbol_row.get("status") != "TRADING":
        blockers.append(f"canary_symbol_not_trading:{symbol_row.get('status')}")
    if best_bid <= 0 or best_ask <= 0:
        blockers.append("best_bid_or_ask_missing")
    if best_bid >= best_ask:
        blockers.append(f"invalid_or_locked_spread:bid={best_bid}:ask={best_ask}")
    if tick <= 0:
        blockers.append("missing_price_tick_size")
    if step <= 0:
        blockers.append("missing_lot_step_size")
    if min_qty <= 0:
        blockers.append("missing_lot_min_qty")

    price = floor_to_step(best_bid, tick) if tick > 0 else Decimal("0")
    if price <= 0:
        blockers.append("computed_canary_price_not_positive")
    if min_price > 0 and price < min_price:
        blockers.append(f"computed_canary_price_below_min_price:{price}<{min_price}")
    if best_ask > 0 and price >= best_ask:
        blockers.append(f"computed_buy_price_crosses_spread:{price}>={best_ask}")
    raw_qty = max_notional / price if price > 0 else Decimal("0")
    quantity = floor_to_step(raw_qty, step) if step > 0 else Decimal("0")
    notional = price * quantity
    minimum_executable_notional = max(min_notional, min_qty * price)
    if minimum_executable_notional > max_notional:
        blockers.append(
            "canary_minimum_notional_exceeds_authorized_max:"
            f"required={format_decimal(minimum_executable_notional)}:"
            f"max={format_decimal(max_notional)}"
        )
    if quantity < min_qty:
        blockers.append(
            f"computed_quantity_below_min_qty:{format_decimal(quantity)}<{format_decimal(min_qty)}"
        )
    if min_notional > 0 and notional < min_notional:
        blockers.append(
            f"computed_notional_below_min_notional:{format_decimal(notional)}<{format_decimal(min_notional)}"
        )
    if notional > max_notional:
        blockers.append(
            f"computed_notional_above_approved_max:{format_decimal(notional)}>{format_decimal(max_notional)}"
        )
    if Decimal(str(terms.get("risk_ceiling_usdt") or "0")) != RISK_CEILING_USDT:
        blockers.append("risk_ceiling_terms_mismatch")
    if str(terms.get("time_in_force") or "") != TIME_IN_FORCE:
        blockers.append("time_in_force_terms_mismatch")

    status = "ready" if not blockers else "blocked"
    return CanaryOrderPlan(
        status=status,
        blockers=sorted(set(blockers)),
        symbol=CANARY_SYMBOL,
        side=CANARY_SIDE,
        price=format_decimal(price),
        quantity=format_decimal(quantity),
        notional_usdt=format_decimal(notional),
        best_bid=format_decimal(best_bid),
        best_ask=format_decimal(best_ask),
        tick_size=format_decimal(tick),
        step_size=format_decimal(step),
        min_qty=format_decimal(min_qty),
        min_notional=format_decimal(min_notional),
        minimum_executable_notional_usdt=format_decimal(minimum_executable_notional),
        limit_order_must_not_cross_spread=not blockers and price < best_ask,
        post_only_time_in_force=TIME_IN_FORCE,
    )


def remote_p9da_order_command(
    *,
    remote_repo: str,
    remote_live_env: str,
    remote_python: str,
    remote_config: str,
    expected_egress_ip: str,
    symbol: str,
    side: str,
    client_order_id: str,
    max_notional_usdt: str,
    order_lifetime_seconds: int,
) -> str:
    payload = {
        "expected_egress_ip": expected_egress_ip,
        "remote_config": remote_config,
        "symbol": symbol,
        "side": side,
        "client_order_id": client_order_id,
        "max_notional_usdt": max_notional_usdt,
        "order_lifetime_seconds": int(order_lifetime_seconds),
    }
    return f"""
cd {shlex.quote(remote_repo)}
{shlex.quote(remote_live_env)} /usr/bin/env PYTHONNOUSERSITE=1 {shlex.quote(remote_python)} - <<'PY'
import hashlib, hmac, json, os, pathlib, subprocess, sys, time, urllib.error, urllib.parse, urllib.request
from decimal import Decimal, ROUND_FLOOR

CONFIG = {json.dumps(payload, sort_keys=True)!r}
CFG = json.loads(CONFIG)
FAPI = "https://fapi.binance.com"
SAPI = "https://api.binance.com"
REPO_PATH = pathlib.Path({remote_repo!r})

def iso_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def digest(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def public_ip():
    try:
        with urllib.request.urlopen("https://api.ipify.org", timeout=15) as response:
            return response.read().decode().strip()
    except Exception as exc:
        return "unavailable:" + type(exc).__name__

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

def sign(params, secret):
    params = dict(params)
    params.setdefault("recvWindow", "5000")
    params.setdefault("timestamp", str(int(time.time() * 1000)))
    query = urllib.parse.urlencode(params)
    params["signature"] = hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()
    return params

def request(base, method, path, params=None, signed=False, api_key="", api_secret=""):
    params = {{k: str(v) for k, v in dict(params or {{}}).items() if v is not None}}
    if signed:
        params = sign(params, api_secret)
    query = urllib.parse.urlencode(params)
    url = base + path
    data = None
    if method == "GET" and query:
        url += "?" + query
    elif query:
        data = query.encode()
    headers = {{"User-Agent": "Meridian/P9DA-single-canary"}}
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

def fmt(value):
    s = format(value.normalize(), "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s or "0"

def filter_row(exchange):
    for row in list(exchange.get("symbols") or []):
        if isinstance(row, dict) and row.get("symbol") == CFG["symbol"]:
            return row
    return {{}}

def order_plan(depth_payload, exchange_payload):
    blockers = []
    bids = depth_payload.get("bids") or []
    asks = depth_payload.get("asks") or []
    best_bid = dec(bids[0][0] if bids else "0")
    best_ask = dec(asks[0][0] if asks else "0")
    row = filter_row(exchange_payload)
    fmap = {{str(item.get("filterType")): dict(item) for item in list(row.get("filters") or []) if isinstance(item, dict)}}
    pfilter = fmap.get("PRICE_FILTER", {{}})
    lfilter = fmap.get("LOT_SIZE") or fmap.get("MARKET_LOT_SIZE") or {{}}
    nfilter = fmap.get("MIN_NOTIONAL", {{}})
    tick = dec(pfilter.get("tickSize"))
    step = dec(lfilter.get("stepSize"))
    min_qty = dec(lfilter.get("minQty"))
    min_notional = dec(nfilter.get("notional") or nfilter.get("minNotional"))
    max_notional = dec(CFG["max_notional_usdt"])
    price = floor_step(best_bid, tick)
    qty = floor_step(max_notional / price, step) if price > 0 else Decimal("0")
    notional = price * qty
    minimum = max(min_notional, min_qty * price)
    if row.get("status") != "TRADING":
        blockers.append("canary_symbol_not_trading")
    if best_bid <= 0 or best_ask <= 0 or best_bid >= best_ask:
        blockers.append("invalid_spread")
    if price >= best_ask:
        blockers.append("computed_buy_price_crosses_spread")
    if minimum > max_notional:
        blockers.append(f"canary_minimum_notional_exceeds_authorized_max:required={{fmt(minimum)}}:max={{fmt(max_notional)}}")
    if qty < min_qty:
        blockers.append(f"computed_quantity_below_min_qty:{{fmt(qty)}}<{{fmt(min_qty)}}")
    if min_notional > 0 and notional < min_notional:
        blockers.append(f"computed_notional_below_min_notional:{{fmt(notional)}}<{{fmt(min_notional)}}")
    return {{"status": "ready" if not blockers else "blocked", "blockers": sorted(set(blockers)), "price": fmt(price), "quantity": fmt(qty), "notional_usdt": fmt(notional), "best_bid": fmt(best_bid), "best_ask": fmt(best_ask), "min_qty": fmt(min_qty), "min_notional": fmt(min_notional), "minimum_executable_notional_usdt": fmt(minimum), "time_in_force": "GTX"}}

def small_history(api_key, api_secret):
    return {{
        "all_orders": request(FAPI, "GET", "/fapi/v1/allOrders", {{"symbol": CFG["symbol"], "limit": "20"}}, True, api_key, api_secret),
        "user_trades": request(FAPI, "GET", "/fapi/v1/userTrades", {{"symbol": CFG["symbol"], "limit": "20"}}, True, api_key, api_secret),
    }}

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
pre = {{}}
post = {{}}
submit = {{"status": "not_attempted"}}
query = {{"status": "not_attempted"}}
cancel = {{"status": "not_attempted"}}
if not blockers:
    account_v2 = request(FAPI, "GET", "/fapi/v2/account", {{}}, True, api_key, api_secret)
    account_v3 = request(FAPI, "GET", "/fapi/v3/account", {{}}, True, api_key, api_secret)
    open_orders = request(FAPI, "GET", "/fapi/v1/openOrders", {{}}, True, api_key, api_secret)
    depth = request(FAPI, "GET", "/fapi/v1/depth", {{"symbol": CFG["symbol"], "limit": "5"}}, False)
    exchange = request(FAPI, "GET", "/fapi/v1/exchangeInfo", {{}}, False)
    pre = {{"account_v2": account_v2, "account_v3": account_v3, "open_orders": open_orders, "depth": depth, "exchange_info": exchange, "history": small_history(api_key, api_secret)}}
    if account_v2.get("status") != "ok" or account_v2.get("payload", {{}}).get("canTrade") is not True:
        blockers.append("can_trade_not_true_from_fapi_v2_account")
    if open_orders.get("status") != "ok":
        blockers.append("open_orders_read_failed")
    elif len(open_orders.get("payload") or []) != 0:
        blockers.append(f"pre_submit_open_orders_exist:{{len(open_orders.get('payload') or [])}}")
    plan = order_plan(depth.get("payload") or {{}}, exchange.get("payload") or {{}})
    blockers.extend(plan["blockers"])
else:
    plan = {{"status": "blocked", "blockers": list(blockers)}}
if not blockers:
    params = {{"symbol": CFG["symbol"], "side": CFG["side"], "positionSide": "BOTH", "type": "LIMIT", "timeInForce": "GTX", "quantity": plan["quantity"], "price": plan["price"], "newClientOrderId": CFG["client_order_id"], "newOrderRespType": "ACK"}}
    submit = request(FAPI, "POST", "/fapi/v1/order", params, True, api_key, api_secret)
    if submit.get("status") != "ok":
        blockers.append("canary_order_submit_failed")
    else:
        query = request(FAPI, "GET", "/fapi/v1/order", {{"symbol": CFG["symbol"], "origClientOrderId": CFG["client_order_id"]}}, True, api_key, api_secret)
        executed = dec((query.get("payload") or submit.get("payload") or {{}}).get("executedQty"))
        status = str((query.get("payload") or submit.get("payload") or {{}}).get("status") or "")
        if executed != 0:
            blockers.append(f"unexpected_canary_fill_qty:{{fmt(executed)}}")
        if status in {{"NEW", "PARTIALLY_FILLED"}}:
            cancel = request(FAPI, "DELETE", "/fapi/v1/order", {{"symbol": CFG["symbol"], "origClientOrderId": CFG["client_order_id"]}}, True, api_key, api_secret)
            if cancel.get("status") != "ok":
                blockers.append("canary_cancel_failed")
if api_key and api_secret:
    post = {{"account_v2": request(FAPI, "GET", "/fapi/v2/account", {{}}, True, api_key, api_secret), "account_v3": request(FAPI, "GET", "/fapi/v3/account", {{}}, True, api_key, api_secret), "open_orders": request(FAPI, "GET", "/fapi/v1/openOrders", {{}}, True, api_key, api_secret), "history": small_history(api_key, api_secret)}}
submitted_count = 1 if submit.get("status") == "ok" else 0
canceled_count = 1 if cancel.get("status") == "ok" else 0
query_payload = query.get("payload") if isinstance(query.get("payload"), dict) else {{}}
fill_qty = dec(query_payload.get("executedQty"))
summary = {{"contract_version": "hv_balanced_dth60_coinglass_phase9da_remote_single_post_only_canary_submitter.v1", "started_at_utc": started, "finished_at_utc": iso_now(), "status": "ready" if not blockers and submitted_count == 1 and fill_qty == 0 else "blocked", "blockers": sorted(set(blockers)), "remote_runner_identity_readback": identity, "client_order_id": CFG["client_order_id"], "canary_order_plan": plan, "pre_submit_readback": pre, "order_submission": submit, "order_query": query, "order_cancel": cancel, "post_submit_readback": post, "orders_submitted": submitted_count, "orders_canceled": canceled_count, "fill_count": 1 if fill_qty != 0 else 0, "trade_count": 0, "side_effects": {{"http_methods_used": ["GET", "POST"] + (["DELETE"] if canceled_count else []), "orders_submitted": submitted_count, "orders_canceled": canceled_count, "fill_count": 1 if fill_qty != 0 else 0, "trade_count": 0, "remote_files_written": 0, "remote_sync_performed": False, "supervisor_invoked": False, "timer_path_invoked": False, "candidate_executed": False, "executor_input_mutated": False, "target_plan_replaced": False}}}}
print(json.dumps(summary, indent=2, sort_keys=True))
PY
"""


def build_phase9da(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
    command_runner: CommandRunner = local_command_runner,
) -> tuple[dict[str, Any], int]:
    started_at = now_fn()
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9da" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    p9cz_path = latest_p9cz_summary(args)
    p9cz = load_optional(p9cz_path)
    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)
    terms_path = source_output_path(p9cz, "approved_single_canary_terms")
    requirements_path = source_output_path(p9cz, "pre_submit_requirements_for_p9da")
    final_decision_path = source_output_path(p9cz, "final_owner_live_order_decision")
    terms = load_optional(terms_path)
    requirements = load_optional(requirements_path)
    final_decision = load_optional(final_decision_path)

    owner_record = owner_decision_record(args, started_at)
    write_json(root / "owner_decision_record.json", owner_record)
    pre_checks = {
        "owner_decision_p9da_execute_single_canary_recorded": str(args.owner_decision)
        == APPROVE_P9DA_DECISION,
        "project_profile_exists": bool(project_profile),
        "current_stage_is_stage3": str(project_profile.get("current_stage") or "")
        == "stage_3_human_approved_execution",
        "p9cz_summary_exists": bool(p9cz),
        "p9cz_summary_ready_for_p9da": p9cz_summary_ready(p9cz),
        "p9cz_terms_ready": p9cz_terms_ready(terms, p9cz),
        "p9cz_pre_submit_requirements_ready": pre_submit_requirements_ready(requirements),
        "p9cz_final_decision_loaded": bool(final_decision),
        "remote_host_matches_expected_runner": str(args.remote_host) == DEFAULT_REMOTE_HOST,
        "remote_repo_matches_expected_runner": str(args.remote_repo) == DEFAULT_REMOTE_REPO,
        "canary_symbol_matches_p9cz": str(args.canary_symbol) == CANARY_SYMBOL,
        "canary_side_matches_p9cz": str(args.canary_side) == CANARY_SIDE,
    }
    blockers = [key for key, value in pre_checks.items() if not value]

    command_records: list[dict[str, Any]] = []
    pre_snapshot: dict[str, Any] = {}
    post_snapshot: dict[str, Any] = {}
    account_collector: dict[str, Any] = {}
    account_sanitized: dict[str, Any] = {}
    account_proof: dict[str, Any] = {}
    market_collector: dict[str, Any] = {}
    order_submission: dict[str, Any] = {}
    canary_plan = CanaryOrderPlan(
        status="not_run",
        blockers=[],
        symbol=CANARY_SYMBOL,
        side=CANARY_SIDE,
        price="0",
        quantity="0",
        notional_usdt="0",
        best_bid="0",
        best_ask="0",
        tick_size="0",
        step_size="0",
        min_qty="0",
        min_notional="0",
        minimum_executable_notional_usdt="0",
        limit_order_must_not_cross_spread=False,
        post_only_time_in_force=TIME_IN_FORCE,
    )

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
            ssh_args(args.remote_host, args.ssh_connect_timeout, remote_snapshot_script(args.remote_repo, args.remote_config)),
        )
        pre_snapshot = json_from_command(pre_result)
        write_json(root / "pre_control_snapshot.json", pre_snapshot)
        if pre_result.returncode != 0:
            blockers.append("pre_control_snapshot_failed")

    if not blockers:
        account_result = run_record(
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
                    history_canary_symbol=args.canary_symbol,
                    max_history_symbols=int(args.max_history_symbols or 0),
                ),
            ),
        )
        account_collector = json_from_command(account_result)
        account_sanitized = sanitize_p9ci_collector(account_collector)
        write_json(root / "remote_stdout_account_collector_sanitized.json", account_sanitized)
        if account_result.returncode != 0:
            blockers.append("remote_stdout_pit_safe_v2v3_account_collector_failed")
        if not p9ci_collector_ready(account_collector):
            blockers.append("remote_stdout_pit_safe_v2v3_account_collector_not_ready")
        fixture = {
            "expected_egress_ip": args.expected_egress_ip,
            "pre_egress_ip": account_collector.get("pre_egress_ip"),
            "post_egress_ip": account_collector.get("post_egress_ip"),
            "pre_endpoint_results": dict(account_collector.get("pre_endpoint_results") or {}),
            "post_endpoint_results": dict(account_collector.get("post_endpoint_results") or {}),
            "side_effects": dict(account_collector.get("side_effects") or {}),
        }
        account_proof = build_pit_safe_account_proof(fixture, generated_at=started_at)

    if not blockers:
        market_result = run_record(
            "remote_stdout_market_and_fingerprint_collector",
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
        market_collector = json_from_command(market_result)
        write_json(root / "remote_stdout_market_collector.json", market_collector)
        if market_result.returncode != 0:
            blockers.append("remote_stdout_market_and_fingerprint_collector_failed")
        if not p9ce_collector_ready(market_collector):
            blockers.append("remote_stdout_market_and_fingerprint_collector_not_ready")

    account_delta = account_delta_acceptance(account_proof) if account_proof else {}
    history_delta = history_delta_acceptance(account_collector) if account_collector else {}
    market_delta = p9ce_fingerprint_delta_acceptance(market_collector) if market_collector else {}
    fresh_book = dict(market_collector.get("fresh_order_book") or {})
    filters = dict(market_collector.get("exchange_filter_readback") or {})
    account_identity = dict(account_collector.get("remote_runner_identity_readback") or {})
    market_identity = dict(market_collector.get("remote_runner_identity_readback") or {})

    if account_proof and account_proof.get("pit_safe_read_only_account_proof_ready") is not True:
        blockers.append("pit_safe_v2v3_account_proof_not_ready")
    if account_proof and account_proof.get("can_trade_source") != CAN_TRADE_SOURCE:
        blockers.append("can_trade_source_not_fapi_v2_account")
    if account_proof and (account_proof.get("can_trade_pre") is not True or account_proof.get("can_trade_post") is not True):
        blockers.append("can_trade_v2_false_or_missing_before_canary")
    if account_delta and account_delta.get("open_order_count_zero_pre_post") is not True:
        blockers.append("open_order_count_not_zero_pre_post")
    if history_delta and history_delta.get("order_cancel_fill_trade_delta_zero") is not True:
        blockers.append("account_history_order_cancel_fill_trade_delta_not_zero")
    if market_delta and market_delta.get("order_cancel_fill_trade_delta_zero") is not True:
        blockers.append("market_order_cancel_fill_trade_delta_not_zero")
    if account_collector and not p9ci_remote_identity_ready(
        account_identity,
        remote_host=args.remote_host,
        remote_repo=args.remote_repo,
        remote_config=args.remote_config,
        expected_egress_ip=args.expected_egress_ip,
    ):
        blockers.append("account_collector_remote_runner_identity_not_ready")
    if market_collector and not p9ce_remote_identity_ready(
        market_identity,
        remote_host=args.remote_host,
        remote_repo=args.remote_repo,
        remote_config=args.remote_config,
        expected_egress_ip=args.expected_egress_ip,
    ):
        blockers.append("market_collector_remote_runner_identity_not_ready")

    if fresh_book and filters:
        canary_plan = build_canary_order_plan(fresh_book, filters, terms)
        if canary_plan.status != "ready":
            blockers.extend(canary_plan.blockers)
            blockers.append("canary_order_plan_not_ready")

    client_order_id = f"p9da-{started_at.strftime('%Y%m%d%H%M%S')}-{sha256_text(str(root))[:8]}"
    if not blockers:
        order_result = run_record(
            "remote_single_post_only_canary_order_submitter",
            ssh_args(
                args.remote_host,
                args.ssh_connect_timeout,
                remote_p9da_order_command(
                    remote_repo=args.remote_repo,
                    remote_live_env=args.remote_live_env,
                    remote_python=args.remote_python,
                    remote_config=args.remote_config,
                    expected_egress_ip=args.expected_egress_ip,
                    symbol=CANARY_SYMBOL,
                    side=CANARY_SIDE,
                    client_order_id=client_order_id,
                    max_notional_usdt=str(MAX_NOTIONAL_USDT),
                    order_lifetime_seconds=int(requirements.get("order_lifetime_seconds") or 60),
                ),
            ),
        )
        order_submission = json_from_command(order_result)
        write_json(root / "remote_single_post_only_canary_order_submission.json", order_submission)
        if order_result.returncode != 0:
            blockers.append("remote_single_post_only_canary_order_submitter_failed")
        if order_submission.get("status") != "ready":
            blockers.append("remote_single_post_only_canary_order_submitter_not_ready")
        if int(order_submission.get("orders_submitted") or 0) != 1:
            blockers.append("orders_submitted_not_exactly_one")
        if int(order_submission.get("fill_count") or 0) != 0:
            blockers.append("canary_fill_count_not_zero")

    if pre_snapshot:
        post_result = run_record(
            "post_control_snapshot",
            ssh_args(args.remote_host, args.ssh_connect_timeout, remote_snapshot_script(args.remote_repo, args.remote_config)),
        )
        post_snapshot = json_from_command(post_result)
        write_json(root / "post_control_snapshot.json", post_snapshot)
        if post_result.returncode != 0:
            blockers.append("post_control_snapshot_failed")
        if not snapshot_boundary_ok(pre_snapshot, post_snapshot):
            blockers.append("remote_control_boundary_changed")

    remote_control_unchanged = bool(pre_snapshot and post_snapshot) and snapshot_boundary_ok(pre_snapshot, post_snapshot)
    orders_submitted = int(order_submission.get("orders_submitted") or 0)
    orders_canceled = int(order_submission.get("orders_canceled") or 0)
    fill_count = int(order_submission.get("fill_count") or 0)
    trade_count = int(order_submission.get("trade_count") or 0)
    status = "ready" if not blockers and orders_submitted == 1 and fill_count == 0 else "blocked"
    blockers = sorted(set(blockers))

    control = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9da_control_boundary.v1",
        "scope": "single_post_only_canary_live_order_only",
        "ssh_invoked": bool(command_records),
        "remote_network_connection_performed": bool(account_collector or market_collector or order_submission),
        "fresh_remote_account_read_performed": bool(account_proof),
        "fresh_order_book_read_performed": bool(fresh_book),
        "exchange_filter_read_performed": bool(filters),
        "order_test_endpoint_called": False,
        "live_order_submission_performed": orders_submitted == 1,
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
        "contract_version": "hv_balanced_dth60_coinglass_phase9da_non_authorization.v1",
        "authorizations": {
            "single_post_only_canary_live_order": str(args.owner_decision) == APPROVE_P9DA_DECISION,
            "max_orders": 1,
            "symbol": CANARY_SYMBOL,
            "side": CANARY_SIDE,
            "max_notional_usdt": str(MAX_NOTIONAL_USDT),
            "market_order": False,
            "unbounded_live_order_submission": False,
            "additional_symbols": False,
            "additional_orders": False,
            "timer_path_load": False,
            "supervisor_invocation": False,
            "stage_governance_change": False,
        },
    }
    proof_files = {
        "remote_runner_identity_readback": proof_root / "remote_runner_identity_readback.json",
        "pit_safe_v2v3_account_proof": proof_root / "pit_safe_v2v3_account_proof.json",
        "account_delta_acceptance": proof_root / "account_delta_acceptance.json",
        "account_history_delta_acceptance": proof_root / "account_history_delta_acceptance.json",
        "remote_stdout_market_collector": proof_root / "remote_stdout_market_collector.json",
        "market_proof_collection_delta_acceptance": proof_root / "market_proof_collection_delta_acceptance.json",
        "fresh_order_book": proof_root / "fresh_order_book.json",
        "exchange_filter_readback": proof_root / "exchange_filter_readback.json",
        "canary_order_plan": proof_root / "canary_order_plan.json",
        "remote_single_post_only_canary_order_submission": proof_root / "remote_single_post_only_canary_order_submission.json",
        "control_boundary_readback": proof_root / "control_boundary_readback.json",
        "non_authorization": proof_root / "non_authorization.json",
        "proof_artifact_manifest": proof_root / "proof_artifact_manifest.json",
    }
    combined_identity = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9da_remote_identity_readback.v1",
        "account_collector_identity": account_identity,
        "market_collector_identity": market_identity,
        "account_collector_identity_ready": bool(account_collector)
        and p9ci_remote_identity_ready(
            account_identity,
            remote_host=args.remote_host,
            remote_repo=args.remote_repo,
            remote_config=args.remote_config,
            expected_egress_ip=args.expected_egress_ip,
        ),
        "market_collector_identity_ready": bool(market_collector)
        and p9ce_remote_identity_ready(
            market_identity,
            remote_host=args.remote_host,
            remote_repo=args.remote_repo,
            remote_config=args.remote_config,
            expected_egress_ip=args.expected_egress_ip,
        ),
    }
    write_json(proof_files["remote_runner_identity_readback"], combined_identity)
    write_json(proof_files["pit_safe_v2v3_account_proof"], account_proof)
    write_json(proof_files["account_delta_acceptance"], account_delta)
    write_json(proof_files["account_history_delta_acceptance"], history_delta)
    write_json(proof_files["remote_stdout_market_collector"], market_collector)
    write_json(proof_files["market_proof_collection_delta_acceptance"], market_delta)
    write_json(proof_files["fresh_order_book"], fresh_book)
    write_json(proof_files["exchange_filter_readback"], filters)
    write_json(proof_files["canary_order_plan"], canary_plan.to_dict())
    write_json(proof_files["remote_single_post_only_canary_order_submission"], order_submission)
    write_json(proof_files["control_boundary_readback"], control)
    write_json(proof_files["non_authorization"], non_auth)
    manifest = write_proof_manifest(proof_root, proof_files)
    write_json(root / "command_records.json", {"commands": command_records})

    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "status": status,
        "blockers": blockers,
        "p9da_single_post_only_canary_live_order_ready": status == "ready",
        "p9cz_sufficient_for_p9da_execution": p9cz_summary_ready(p9cz),
        "fresh_pre_submit_readback_performed": bool(account_proof and fresh_book and filters),
        "fresh_remote_account_read_performed": bool(account_proof),
        "fresh_order_book_read_performed": bool(fresh_book),
        "exchange_filter_read_performed": bool(filters),
        "pit_safe_v2v3_account_proof_ready": account_proof.get("pit_safe_read_only_account_proof_ready") is True,
        "can_trade_decision_source": account_proof.get("can_trade_source") or CAN_TRADE_SOURCE,
        "can_trade_pre": account_proof.get("can_trade_pre"),
        "can_trade_post": account_proof.get("can_trade_post"),
        "order_test_endpoint_called": False,
        "canary_order_plan_ready": canary_plan.status == "ready",
        "canary_minimum_executable_notional_usdt": canary_plan.minimum_executable_notional_usdt,
        "canary_price": canary_plan.price,
        "canary_quantity": canary_plan.quantity,
        "canary_notional_usdt": canary_plan.notional_usdt,
        "live_order_submission_authorized": True,
        "live_order_submission_performed": orders_submitted == 1,
        "actual_live_order_submission_performed": orders_submitted == 1,
        "orders_submitted": orders_submitted,
        "orders_canceled": orders_canceled,
        "fill_count": fill_count,
        "trade_count": trade_count,
        "remote_control_boundary_unchanged": remote_control_unchanged,
        "candidate_target_plan_sha256": terms.get("candidate_target_plan_sha256") or p9cz.get("candidate_target_plan_sha256"),
        "baseline_target_plan_sha256": terms.get("baseline_target_plan_sha256") or p9cz.get("baseline_target_plan_sha256"),
        "only_distance_to_high_60_contribution_changed": terms.get("only_distance_to_high_60_contribution_changed") is True,
        "actual_candidate_executor_target_path_entry_performed": False,
        "actual_target_plan_replacement_performed": False,
        "actual_executor_input_mutation_performed": False,
        "actual_candidate_execution_performed": False,
        "timer_path_load_authorized": False,
        "supervisor_invocation_authorized": False,
        "remote_files_written": 0,
        "remote_sync_performed": False,
        "canary_symbol": CANARY_SYMBOL,
        "canary_side": CANARY_SIDE,
        "risk_ceiling_usdt": float(RISK_CEILING_USDT),
        "max_notional_usdt": float(MAX_NOTIONAL_USDT),
        "max_orders_per_cycle": 1,
        "max_symbols_per_cycle": 1,
        "order_type": ORDER_TYPE,
        "time_in_force": TIME_IN_FORCE,
        "market_orders_allowed": False,
        "post_only_required": True,
        "maker_only_required": True,
        "limit_order_must_not_cross_spread": True,
        "allowed_next_gate": P9DB_GATE,
        "allowed_next_gate_scope": P9DB_SCOPE,
        "allowed_next_gate_must_be_separately_requested": True,
        "source_evidence": {
            "phase9cz_summary": evidence_file(p9cz_path),
            "phase9cz_approved_single_canary_terms": evidence_file(terms_path),
            "phase9cz_pre_submit_requirements": evidence_file(requirements_path),
            "phase9cz_final_owner_live_order_decision": evidence_file(final_decision_path),
            "project_profile": evidence_file(project_profile_path),
        },
        "gates": {
            **pre_checks,
            "remote_stdout_pit_safe_v2v3_account_collector_ready": p9ci_collector_ready(account_collector),
            "remote_stdout_market_and_fingerprint_collector_ready": p9ce_collector_ready(market_collector),
            "pit_safe_v2v3_account_proof_ready": account_proof.get("pit_safe_read_only_account_proof_ready") is True,
            "canary_order_plan_ready": canary_plan.status == "ready",
            "single_canary_order_submitted_exactly_once": orders_submitted == 1,
            "canary_fill_count_zero": fill_count == 0,
            "remote_control_boundary_unchanged": remote_control_unchanged,
        },
        "output_files": {
            "summary": str(root / "summary.json"),
            "owner_decision_record": str(root / "owner_decision_record.json"),
            "command_records": str(root / "command_records.json"),
            "pre_control_snapshot": str(root / "pre_control_snapshot.json"),
            "post_control_snapshot": str(root / "post_control_snapshot.json"),
            "report": str(root / "p9da_single_post_only_canary_live_order.md"),
            "proof_artifact_manifest": str(proof_files["proof_artifact_manifest"]),
            **{key: str(path) for key, path in proof_files.items() if key != "proof_artifact_manifest"},
        },
    }
    write_json(root / "summary.json", summary)
    (root / "p9da_single_post_only_canary_live_order.md").write_text(render_markdown(summary), encoding="utf-8")
    return summary, 0 if status == "ready" else 2


def write_proof_manifest(proof_root: Path, files: dict[str, Path]) -> dict[str, Any]:
    entries = {name: evidence_file(path) for name, path in sorted(files.items()) if name != "proof_artifact_manifest"}
    manifest = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9da_proof_artifact_manifest.v1",
        "artifact_count": len(entries),
        "artifacts": entries,
    }
    manifest_path = proof_root / "proof_artifact_manifest.json"
    write_json(manifest_path, manifest)
    manifest["self"] = evidence_file(manifest_path)
    write_json(manifest_path, manifest)
    return manifest


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9DA Single Post-Only Canary Live Order",
        "",
        f"`Status: {summary['status']}`",
        "",
        "P9DA is scoped to one BTCUSDT BUY post-only GTX canary order after fresh pre-submit readback. It fails closed when the approved 10 USDT max notional cannot satisfy current exchange filters.",
        "",
        "## Boundary",
        "",
        "```text",
        f"fresh_pre_submit_readback_performed = {str(bool(summary['fresh_pre_submit_readback_performed'])).lower()}",
        f"canary_order_plan_ready = {str(bool(summary['canary_order_plan_ready'])).lower()}",
        f"canary_minimum_executable_notional_usdt = {summary['canary_minimum_executable_notional_usdt']}",
        f"max_notional_usdt = {summary['max_notional_usdt']}",
        f"live_order_submission_performed = {str(bool(summary['live_order_submission_performed'])).lower()}",
        f"orders_submitted = {summary['orders_submitted']}",
        f"orders_canceled = {summary['orders_canceled']}",
        f"fill_count = {summary['fill_count']}",
        f"trade_count = {summary['trade_count']}",
        f"remote_control_boundary_unchanged = {str(bool(summary['remote_control_boundary_unchanged'])).lower()}",
        "timer_path_load_authorized = false",
        "supervisor_invocation_authorized = false",
        "```",
        "",
        "## Blockers",
        "",
        *[f"- {item}" for item in list(summary.get("blockers") or [])],
        "",
        "## Next Gate",
        "",
        str(summary.get("allowed_next_gate") or ""),
    ]
    return "\n".join(lines).rstrip() + "\n"


def _book_price(value: Any) -> Decimal:
    if isinstance(value, (list, tuple)) and value:
        return _decimal(value[0], "0")
    return _decimal(value, "0")


def _symbol_filter_row(exchange_filters: dict[str, Any], symbol: str) -> dict[str, Any]:
    for row in list(exchange_filters.get("symbols") or []):
        if isinstance(row, dict) and str(row.get("symbol") or "") == symbol:
            return row
    return {}


def _decimal(value: Any, default: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def floor_to_step(value: Decimal, step: Decimal) -> Decimal:
    if step <= 0:
        return Decimal("0")
    return (value / step).to_integral_value(rounding=ROUND_FLOOR) * step


def format_decimal(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_phase9da(parse_args(argv))
    print(
        "p9da_single_post_only_canary_live_order_ready="
        + str(bool(summary["p9da_single_post_only_canary_live_order_ready"])).lower()
    )
    print("orders_submitted=" + str(int(summary["orders_submitted"])))
    print("fill_count=" + str(int(summary["fill_count"])))
    print("summary=" + str(summary["output_files"]["summary"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
