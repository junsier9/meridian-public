from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from scripts.live_trading.hv_balanced_binance_usdm_pit_safe_account_proof_builder import (  # noqa: E402
    CAN_TRADE_SOURCE,
    build_pit_safe_account_proof,
)
from scripts.live_trading.run_hv_balanced_12factor_p10h_owner_gate_single_cycle_live_delta_canary_terms import (  # noqa: E402
    CONTRACT_VERSION as P10H_CONTRACT,
    P10I_GATE,
    p10g_ready,
    stable_payload_sha256,
    terms_valid as p10h_terms_valid,
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
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    latest_match,
    load_optional,
    resolve_path,
    write_json,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9tuv_proof_only_corridor import (  # noqa: E402
    PROJECT_PROFILE,
)


CONTRACT_VERSION = "hv_balanced_12factor_p10i_execute_single_cycle_live_delta_canary.v1"
REMOTE_SUBMITTER_CONTRACT = "hv_balanced_12factor_p10i_remote_single_cycle_live_delta_canary_submitter.v1"
APPROVE_P10I_DECISION = "approve_p10i_execute_single_cycle_live_delta_canary_only"
DEFAULT_P10H_PARENT = "artifacts/live_trading/proof_artifacts/p10h_live_delta_canary_terms"
DEFAULT_P10G_PARENT = "artifacts/live_trading/proof_artifacts/p10g_replacement_dry_run"
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/proof_artifacts/p10i_single_cycle_live_delta_canary"
P10J_GATE = "P10J_review_p10i_single_cycle_live_delta_canary_only_if_separately_requested"
P10J_SCOPE = (
    "review_p10i_retained_evidence_before_any_limited_live_delta_or_continuous_candidate_execution_discussion"
)
CANARY_SYMBOL = "BTCUSDT"
MAX_NOTIONAL_USDT = Decimal("75")
TIME_IN_FORCE = "GTX"
ORDER_TYPE = "post_only_limit"


@dataclass(frozen=True, slots=True)
class CandidateDelta:
    status: str
    blockers: list[str]
    symbol: str
    side: str
    baseline_target_notional_usdt: str
    candidate_target_notional_usdt: str
    target_notional_delta_usdt: str
    approved_notional_cap_usdt: str
    canary_notional_usdt: str
    target_plan_diff_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": "hv_balanced_12factor_p10i_candidate_delta_binding.v1",
            "status": self.status,
            "blockers": self.blockers,
            "symbol": self.symbol,
            "side": self.side,
            "baseline_target_notional_usdt": self.baseline_target_notional_usdt,
            "candidate_target_notional_usdt": self.candidate_target_notional_usdt,
            "target_notional_delta_usdt": self.target_notional_delta_usdt,
            "approved_notional_cap_usdt": self.approved_notional_cap_usdt,
            "canary_notional_usdt": self.canary_notional_usdt,
            "target_plan_diff_sha256": self.target_plan_diff_sha256,
            "side_source": "P10G.target_plan_diff.target_notional_delta_usdt",
        }


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

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": "hv_balanced_12factor_p10i_canary_order_plan.v1",
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
            "max_notional_usdt": format_decimal(MAX_NOTIONAL_USDT),
            "limit_order_must_not_cross_spread": self.limit_order_must_not_cross_spread,
            "order_type": ORDER_TYPE,
            "time_in_force": TIME_IN_FORCE,
            "market_orders_allowed": False,
            "post_only_required": True,
            "maker_only_required": True,
        }


@dataclass(frozen=True, slots=True)
class CanaryPositionRollbackContract:
    status: str
    blockers: list[str]
    symbol: str
    candidate_side: str
    pre_position_amt: str
    post_position_amt: str
    rollback_mode: str
    reduce_only_restoration_possible_if_filled: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": "hv_balanced_12factor_p10i_canary_position_rollback_contract.v1",
            "status": self.status,
            "blockers": self.blockers,
            "symbol": self.symbol,
            "candidate_side": self.candidate_side,
            "pre_position_amt": self.pre_position_amt,
            "post_position_amt": self.post_position_amt,
            "rollback_mode": self.rollback_mode,
            "reduce_only_restoration_possible_if_filled": self.reduce_only_restoration_possible_if_filled,
            "non_reduce_only_restoration_authorized": False,
        }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "P10I: execute exactly one BTCUSDT post-only GTX live_delta canary, "
            "only after P10H terms, P10G hash binding, and fresh remote account/"
            "market proof are green. This does not enter timer/supervisor paths "
            "or enable continuous automation."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--p10h-summary", default="")
    parser.add_argument("--p10g-summary", default="")
    parser.add_argument("--remote-host", default=DEFAULT_REMOTE_HOST)
    parser.add_argument("--remote-repo", default=DEFAULT_REMOTE_REPO)
    parser.add_argument("--remote-config", default=DEFAULT_REMOTE_CONFIG)
    parser.add_argument("--remote-live-env", default=DEFAULT_REMOTE_LIVE_ENV)
    parser.add_argument("--remote-python", default=DEFAULT_REMOTE_PYTHON)
    parser.add_argument("--expected-egress-ip", default=DEFAULT_EXPECTED_EGRESS_IP)
    parser.add_argument("--max-history-symbols", type=int, default=20)
    parser.add_argument("--ssh-connect-timeout", type=int, default=10)
    parser.add_argument("--order-lifetime-seconds", type=int, default=15)
    parser.add_argument("--maker-buffer-ticks", type=int, default=1)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P10I_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:p10i_execute_single_cycle_live_delta_canary_only_if_separately_requested",
    )
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def phase_root(args: argparse.Namespace, run_id: str) -> Path:
    if str(args.output_root).strip():
        return resolve_path(args.output_root)
    return resolve_path(DEFAULT_OUTPUT_PARENT) / run_id


def latest_summary(parent: str, explicit: str) -> Path:
    if str(explicit).strip():
        return resolve_path(explicit)
    return latest_match(parent, "*/summary.json")


def source_output_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("output_files") or {}).get(key) or "")
    return resolve_path(text) if text.strip() else Path("")


def p10h_summary_ready(summary: dict[str, Any]) -> bool:
    return (
        summary.get("contract_version") == P10H_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p10h_owner_gate_single_cycle_live_delta_canary_terms_ready") is True
        and summary.get("future_p10i_single_cycle_canary_authorized_if_separately_requested") is True
        and summary.get("fresh_remote_proof_required_before_execution") is True
        and summary.get("allowed_next_gate") == P10I_GATE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
        and Decimal(str(summary.get("approved_max_notional_usdt") or "0")) == MAX_NOTIONAL_USDT
        and summary.get("approved_symbol") == CANARY_SYMBOL
        and summary.get("approved_order_type") == ORDER_TYPE
        and summary.get("approved_time_in_force") == TIME_IN_FORCE
        and int(summary.get("approved_cycles") or 0) == 1
        and summary.get("continuous_automation") is False
        and summary.get("candidate_plan_hash_binding_ready") is True
        and summary.get("baseline_fallback_ready") is True
        and summary.get("kill_switch_ready") is True
        and summary.get("rollback_ready") is True
        and summary.get("execute_canary_inside_p10h") is False
        and summary.get("candidate_execution_authorized_now") is False
        and summary.get("live_order_submission_authorized_now") is False
        and int(summary.get("orders_submitted") or 0) == 0
        and int(summary.get("fill_count") or 0) == 0
        and bool(summary.get("candidate_plan_hash"))
    )


def p10h_terms_ready(terms: dict[str, Any], summary: dict[str, Any]) -> bool:
    return (
        terms.get("contract_version") == "hv_balanced_12factor_p10h_single_cycle_live_delta_canary_terms.v1"
        and p10h_terms_valid(terms).get("max_notional_usdt_is_75") is True
        and all(p10h_terms_valid(terms).values())
        and terms.get("side") == "derive_from_fresh_candidate_delta"
        and terms.get("candidate_plan_hash") == summary.get("candidate_plan_hash")
    )


def candidate_scope_account_proof_ready(
    *,
    account_proof: dict[str, Any],
    account_delta: dict[str, Any],
    history_delta: dict[str, Any],
    market_delta: dict[str, Any],
) -> bool:
    return (
        bool(account_proof)
        and account_proof.get("can_trade_source") == CAN_TRADE_SOURCE
        and account_proof.get("can_trade_pre") is True
        and account_proof.get("can_trade_post") is True
        and account_delta.get("open_order_count_zero_pre_post") is True
        and account_delta.get("open_order_delta_zero_or_stable") is True
        and account_delta.get("side_effects_zero") is True
        and int(account_delta.get("orders_submitted") or 0) == 0
        and int(account_delta.get("orders_canceled") or 0) == 0
        and int(account_delta.get("fill_count") or 0) == 0
        and int(account_delta.get("trade_count") or 0) == 0
        and history_delta.get("order_cancel_fill_trade_delta_zero") is True
        and history_delta.get("order_history_fingerprint_stable") is True
        and history_delta.get("trade_history_fingerprint_stable") is True
        and market_delta.get("open_order_fingerprint_stable") is True
        and market_delta.get("position_delta_zero_or_stable") is True
        and market_delta.get("balance_delta_zero_or_stable") is True
        and market_delta.get("order_cancel_fill_trade_delta_zero") is True
        and int(market_delta.get("orders_submitted") or 0) == 0
        and int(market_delta.get("orders_canceled") or 0) == 0
        and int(market_delta.get("fill_count") or 0) == 0
        and int(market_delta.get("trade_count") or 0) == 0
    )


def _position_amt_from_account_snapshot(snapshot: dict[str, Any], symbol: str) -> Decimal:
    raw_rows = dict(snapshot.get("position_fingerprint") or {}).get("stable_rows") or []
    if isinstance(raw_rows, dict):
        rows = list(raw_rows.values())
    elif isinstance(raw_rows, list):
        rows = raw_rows
    else:
        rows = []
    total = Decimal("0")
    for row in rows:
        if not isinstance(row, dict) or str(row.get("symbol") or "") != symbol:
            continue
        total += _decimal(row.get("positionAmt"), "0")
    return total


def canary_position_rollback_contract(
    *,
    account_proof: dict[str, Any],
    candidate_delta: CandidateDelta,
) -> CanaryPositionRollbackContract:
    blockers: list[str] = []
    pre_amt = _position_amt_from_account_snapshot(dict(account_proof.get("pre") or {}), CANARY_SYMBOL)
    post_amt = _position_amt_from_account_snapshot(dict(account_proof.get("post") or {}), CANARY_SYMBOL)
    side = candidate_delta.side
    reduce_only_restoration_possible = True
    if side == "SELL" and pre_amt > 0:
        reduce_only_restoration_possible = False
        blockers.append("nonflat_long_plus_sell_would_require_non_reduce_only_buy_restoration")
    elif side == "BUY" and pre_amt < 0:
        reduce_only_restoration_possible = False
        blockers.append("nonflat_short_plus_buy_would_require_non_reduce_only_sell_restoration")
    if pre_amt != post_amt:
        blockers.append("account_proof_position_amt_not_stable_pre_post")
    if candidate_delta.status != "ready":
        blockers.append("candidate_delta_binding_not_ready")
    status = "ready" if not blockers else "blocked"
    return CanaryPositionRollbackContract(
        status=status,
        blockers=sorted(set(blockers)),
        symbol=CANARY_SYMBOL,
        candidate_side=side,
        pre_position_amt=format_decimal(pre_amt),
        post_position_amt=format_decimal(post_amt),
        rollback_mode="cancel_open_order_then_reduce_only_close_only_if_filled",
        reduce_only_restoration_possible_if_filled=reduce_only_restoration_possible and status == "ready",
    )


def static_control_boundary_ok(pre: dict[str, Any], post: dict[str, Any]) -> bool:
    return (
        bool(pre and post)
        and pre.get("remote_live_config_sha256") == post.get("remote_live_config_sha256")
        and pre.get("live_supervisor_sha256") == post.get("live_supervisor_sha256")
        and pre.get("hook_sha256") == post.get("hook_sha256")
        and pre.get("operator_state") == post.get("operator_state")
    )


def owner_decision_record(args: argparse.Namespace, now: datetime) -> dict[str, Any]:
    approved = str(args.owner_decision) == APPROVE_P10I_DECISION
    return {
        "contract_version": "hv_balanced_12factor_p10i_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "recorded_at_utc": iso_z(now),
        "decision_question": "execute_single_cycle_live_delta_canary_only",
        "p10i_single_cycle_live_delta_canary_execution_approved": approved,
        "max_orders_approved": 1 if approved else 0,
        "symbol": CANARY_SYMBOL,
        "max_notional_usdt": format_decimal(MAX_NOTIONAL_USDT),
        "order_type": ORDER_TYPE,
        "time_in_force": TIME_IN_FORCE,
        "market_orders_approved": False,
        "post_only_required": True,
        "maker_only_required": True,
        "timer_path_load_approved": False,
        "supervisor_invocation_approved": False,
        "continuous_automation_approved": False,
    }


def derive_candidate_delta(p10g: dict[str, Any], p10h: dict[str, Any]) -> CandidateDelta:
    blockers: list[str] = []
    diff_path = source_output_path(p10g, "target_plan_diff")
    diff = load_optional(diff_path)
    rows = [dict(row) for row in list(diff.get("rows") or []) if isinstance(row, dict)]
    row = next((item for item in rows if str(item.get("symbol") or "") == CANARY_SYMBOL), {})
    candidate_hash = str(p10g.get("candidate_target_plan_sha256") or "")
    if not p10g_ready(p10g):
        blockers.append("p10g_replacement_dry_run_not_ready")
    if not diff:
        blockers.append("p10g_target_plan_diff_missing")
    if not row:
        blockers.append("btcusdt_delta_row_missing_from_p10g_diff")
    if candidate_hash != str(p10h.get("candidate_plan_hash") or ""):
        blockers.append("p10h_candidate_hash_mismatch_with_p10g")
    delta = _decimal(row.get("target_notional_delta_usdt"), "0")
    baseline = _decimal(row.get("baseline_target_notional_usdt"), "0")
    candidate = _decimal(row.get("candidate_target_notional_usdt"), "0")
    if delta == 0:
        blockers.append("btcusdt_candidate_delta_is_zero")
        side = ""
    else:
        side = "BUY" if delta > 0 else "SELL"
    notional = min(abs(delta), MAX_NOTIONAL_USDT)
    if notional <= 0:
        blockers.append("candidate_delta_notional_not_positive")
    status = "ready" if not blockers else "blocked"
    return CandidateDelta(
        status=status,
        blockers=sorted(set(blockers)),
        symbol=CANARY_SYMBOL,
        side=side,
        baseline_target_notional_usdt=format_decimal(baseline),
        candidate_target_notional_usdt=format_decimal(candidate),
        target_notional_delta_usdt=format_decimal(delta),
        approved_notional_cap_usdt=format_decimal(MAX_NOTIONAL_USDT),
        canary_notional_usdt=format_decimal(notional),
        target_plan_diff_sha256=evidence_file(diff_path).get("sha256", ""),
    )


def build_canary_order_plan(
    fresh_book: dict[str, Any],
    exchange_filters: dict[str, Any],
    candidate_delta: CandidateDelta,
    *,
    maker_buffer_ticks: int = 1,
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
    max_notional = _decimal(candidate_delta.canary_notional_usdt, "0")
    side = candidate_delta.side
    buffer_ticks = max(1, int(maker_buffer_ticks or 1))

    if candidate_delta.status != "ready":
        blockers.append("candidate_delta_binding_not_ready")
    if fresh_book.get("status") != "ready":
        blockers.append("fresh_order_book_not_ready")
    if exchange_filters.get("status") != "ready":
        blockers.append("exchange_filter_readback_not_ready")
    if not symbol_row:
        blockers.append("canary_symbol_missing_from_exchange_filters")
    if symbol_row and symbol_row.get("status") != "TRADING":
        blockers.append(f"canary_symbol_not_trading:{symbol_row.get('status')}")
    if side not in {"BUY", "SELL"}:
        blockers.append(f"candidate_delta_side_not_supported:{side}")
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

    if side == "SELL":
        price = ceil_to_step(best_ask + (tick * buffer_ticks), tick) if tick > 0 else Decimal("0")
    else:
        price = floor_to_step(best_bid - (tick * buffer_ticks), tick) if tick > 0 else Decimal("0")
    raw_qty = max_notional / price if price > 0 else Decimal("0")
    quantity = floor_to_step(raw_qty, step) if step > 0 else Decimal("0")
    notional = price * quantity
    minimum_executable_notional = max(min_notional, min_qty * price)

    if price <= 0:
        blockers.append("computed_canary_price_not_positive")
    if min_price > 0 and price < min_price:
        blockers.append(f"computed_canary_price_below_min_price:{format_decimal(price)}<{format_decimal(min_price)}")
    if side == "BUY" and best_ask > 0 and price >= best_ask:
        blockers.append(f"computed_buy_price_crosses_spread:{format_decimal(price)}>={format_decimal(best_ask)}")
    if side == "SELL" and best_bid > 0 and price <= best_bid:
        blockers.append(f"computed_sell_price_crosses_spread:{format_decimal(price)}<={format_decimal(best_bid)}")
    if minimum_executable_notional > max_notional:
        blockers.append(
            "canary_minimum_notional_exceeds_authorized_max:"
            f"required={format_decimal(minimum_executable_notional)}:"
            f"max={format_decimal(max_notional)}"
        )
    if quantity < min_qty:
        blockers.append(f"computed_quantity_below_min_qty:{format_decimal(quantity)}<{format_decimal(min_qty)}")
    if min_notional > 0 and notional < min_notional:
        blockers.append(f"computed_notional_below_min_notional:{format_decimal(notional)}<{format_decimal(min_notional)}")
    if notional > MAX_NOTIONAL_USDT:
        blockers.append(f"computed_notional_above_approved_max:{format_decimal(notional)}>{format_decimal(MAX_NOTIONAL_USDT)}")

    status = "ready" if not blockers else "blocked"
    if side == "SELL":
        non_crossing = price > best_bid
    else:
        non_crossing = price < best_ask
    return CanaryOrderPlan(
        status=status,
        blockers=sorted(set(blockers)),
        symbol=CANARY_SYMBOL,
        side=side,
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
        limit_order_must_not_cross_spread=status == "ready" and non_crossing,
    )


def remote_p10i_order_command(
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
    maker_buffer_ticks: int = 1,
) -> str:
    payload = {
        "expected_egress_ip": expected_egress_ip,
        "remote_config": remote_config,
        "symbol": symbol,
        "side": side,
        "client_order_id": client_order_id,
        "max_notional_usdt": max_notional_usdt,
        "order_lifetime_seconds": int(order_lifetime_seconds),
        "maker_buffer_ticks": max(1, int(maker_buffer_ticks or 1)),
    }
    return f"""
cd {shlex.quote(remote_repo)}
{shlex.quote(remote_live_env)} /usr/bin/env PYTHONNOUSERSITE=1 {shlex.quote(remote_python)} - <<'PY'
import hashlib, hmac, json, os, pathlib, subprocess, time, urllib.error, urllib.parse, urllib.request
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR

CONFIG = {json.dumps(payload, sort_keys=True)!r}
CFG = json.loads(CONFIG)
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
    params.setdefault("recvWindow", "30000")
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
    if method in {{"GET", "DELETE"}} and query:
        url += "?" + query
    elif query:
        data = query.encode()
    headers = {{"User-Agent": "Meridian/P10I-live-delta-canary"}}
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
    side = CFG["side"]
    buffer_ticks = max(1, int(CFG.get("maker_buffer_ticks") or 1))
    price = ceil_step(best_ask + (tick * buffer_ticks), tick) if side == "SELL" else floor_step(best_bid - (tick * buffer_ticks), tick)
    qty = floor_step(max_notional / price, step) if price > 0 else Decimal("0")
    notional = price * qty
    minimum = max(min_notional, min_qty * price)
    if row.get("status") != "TRADING":
        blockers.append("canary_symbol_not_trading")
    if side not in {{"BUY", "SELL"}}:
        blockers.append("side_not_supported")
    if best_bid <= 0 or best_ask <= 0 or best_bid >= best_ask:
        blockers.append("invalid_spread")
    if side == "BUY" and price >= best_ask:
        blockers.append("computed_buy_price_crosses_spread")
    if side == "SELL" and price <= best_bid:
        blockers.append("computed_sell_price_crosses_spread")
    if minimum > max_notional:
        blockers.append(f"canary_minimum_notional_exceeds_authorized_max:required={{fmt(minimum)}}:max={{fmt(max_notional)}}")
    if qty < min_qty:
        blockers.append(f"computed_quantity_below_min_qty:{{fmt(qty)}}<{{fmt(min_qty)}}")
    if min_notional > 0 and notional < min_notional:
        blockers.append(f"computed_notional_below_min_notional:{{fmt(notional)}}<{{fmt(min_notional)}}")
    return {{"status": "ready" if not blockers else "blocked", "blockers": sorted(set(blockers)), "side": side, "price": fmt(price), "quantity": fmt(qty), "notional_usdt": fmt(notional), "best_bid": fmt(best_bid), "best_ask": fmt(best_ask), "min_qty": fmt(min_qty), "min_notional": fmt(min_notional), "minimum_executable_notional_usdt": fmt(minimum), "time_in_force": "GTX"}}

def small_history(api_key, api_secret):
    return {{
        "all_orders": request("GET", "/fapi/v1/allOrders", {{"symbol": CFG["symbol"], "limit": "20"}}, True, api_key, api_secret),
        "user_trades": request("GET", "/fapi/v1/userTrades", {{"symbol": CFG["symbol"], "limit": "20"}}, True, api_key, api_secret),
    }}

def position_amt(position_risk):
    total = Decimal("0")
    for row in list(position_risk or []):
        if isinstance(row, dict) and row.get("symbol") == CFG["symbol"]:
            total += dec(row.get("positionAmt"))
    return total

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
plan = {{"status": "blocked", "blockers": list(blockers)}}
if not blockers:
    account_v2 = request("GET", "/fapi/v2/account", {{}}, True, api_key, api_secret)
    account_v3 = request("GET", "/fapi/v3/account", {{}}, True, api_key, api_secret)
    position_mode = request("GET", "/fapi/v1/positionSide/dual", {{}}, True, api_key, api_secret)
    position_risk = request("GET", "/fapi/v2/positionRisk", {{"symbol": CFG["symbol"]}}, True, api_key, api_secret)
    open_orders = request("GET", "/fapi/v1/openOrders", {{}}, True, api_key, api_secret)
    depth = request("GET", "/fapi/v1/depth", {{"symbol": CFG["symbol"], "limit": "5"}}, False)
    exchange = request("GET", "/fapi/v1/exchangeInfo", {{}}, False)
    pre = {{"account_v2": account_v2, "account_v3": account_v3, "position_mode": position_mode, "position_risk": position_risk, "open_orders": open_orders, "depth": depth, "exchange_info": exchange, "history": small_history(api_key, api_secret)}}
    if account_v2.get("status") != "ok" or account_v2.get("payload", {{}}).get("canTrade") is not True:
        blockers.append("can_trade_not_true_from_fapi_v2_account")
    if position_mode.get("status") != "ok" or position_mode.get("payload", {{}}).get("dualSidePosition") is not False:
        blockers.append("position_mode_not_one_way")
    if position_risk.get("status") != "ok":
        blockers.append("position_risk_read_failed")
    else:
        pre_amt = position_amt(position_risk.get("payload") or [])
        if CFG["side"] == "SELL" and pre_amt > 0:
            blockers.append("nonflat_long_plus_sell_would_require_non_reduce_only_buy_restoration")
        if CFG["side"] == "BUY" and pre_amt < 0:
            blockers.append("nonflat_short_plus_buy_would_require_non_reduce_only_sell_restoration")
    if open_orders.get("status") != "ok":
        blockers.append("open_orders_read_failed")
    elif len(open_orders.get("payload") or []) != 0:
        blockers.append(f"pre_submit_open_orders_exist:{{len(open_orders.get('payload') or [])}}")
    plan = order_plan(depth.get("payload") or {{}}, exchange.get("payload") or {{}})
    blockers.extend(plan["blockers"])
if not blockers:
    params = {{"symbol": CFG["symbol"], "side": CFG["side"], "positionSide": "BOTH", "type": "LIMIT", "timeInForce": "GTX", "quantity": plan["quantity"], "price": plan["price"], "newClientOrderId": CFG["client_order_id"], "newOrderRespType": "ACK"}}
    submit = request("POST", "/fapi/v1/order", params, True, api_key, api_secret)
    if submit.get("status") != "ok":
        blockers.append("canary_order_submit_failed")
    else:
        if int(CFG["order_lifetime_seconds"]) > 0:
            time.sleep(min(int(CFG["order_lifetime_seconds"]), 30))
        query = request("GET", "/fapi/v1/order", {{"symbol": CFG["symbol"], "origClientOrderId": CFG["client_order_id"]}}, True, api_key, api_secret)
        if query.get("status") != "ok":
            blockers.append("canary_order_query_failed")
            cancel = request("DELETE", "/fapi/v1/order", {{"symbol": CFG["symbol"], "origClientOrderId": CFG["client_order_id"]}}, True, api_key, api_secret)
            if cancel.get("status") != "ok":
                blockers.append("canary_cancel_after_query_failed_failed")
        else:
            payload = query.get("payload") if isinstance(query.get("payload"), dict) else {{}}
            executed = dec(payload.get("executedQty"))
            status = str(payload.get("status") or "")
            if status in {{"NEW", "PARTIALLY_FILLED"}}:
                cancel = request("DELETE", "/fapi/v1/order", {{"symbol": CFG["symbol"], "origClientOrderId": CFG["client_order_id"]}}, True, api_key, api_secret)
                if cancel.get("status") != "ok":
                    blockers.append("canary_cancel_failed")
            if executed != 0:
                blockers.append(f"unexpected_canary_fill_qty:{{fmt(executed)}}")
if api_key and api_secret:
    post = {{"account_v2": request("GET", "/fapi/v2/account", {{}}, True, api_key, api_secret), "account_v3": request("GET", "/fapi/v3/account", {{}}, True, api_key, api_secret), "position_risk": request("GET", "/fapi/v2/positionRisk", {{"symbol": CFG["symbol"]}}, True, api_key, api_secret), "open_orders": request("GET", "/fapi/v1/openOrders", {{}}, True, api_key, api_secret), "history": small_history(api_key, api_secret)}}
submitted_count = 1 if submit.get("status") == "ok" else 0
canceled_count = 1 if cancel.get("status") == "ok" else 0
query_payload = query.get("payload") if isinstance(query.get("payload"), dict) else {{}}
fill_qty = dec(query_payload.get("executedQty"))
summary = {{"contract_version": "{REMOTE_SUBMITTER_CONTRACT}", "started_at_utc": started, "finished_at_utc": iso_now(), "status": "ready" if not blockers and submitted_count == 1 and fill_qty == 0 else "blocked", "blockers": sorted(set(blockers)), "remote_runner_identity_readback": identity, "client_order_id": CFG["client_order_id"], "canary_order_plan": plan, "pre_submit_readback": pre, "order_submission": submit, "order_query": query, "order_cancel": cancel, "post_submit_readback": post, "orders_submitted": submitted_count, "orders_canceled": canceled_count, "fill_count": 1 if fill_qty != 0 else 0, "trade_count": 0, "side_effects": {{"http_methods_used": ["GET"] + (["POST"] if submitted_count else []) + (["DELETE"] if canceled_count else []), "orders_submitted": submitted_count, "orders_canceled": canceled_count, "fill_count": 1 if fill_qty != 0 else 0, "trade_count": 0, "remote_files_written": 0, "remote_sync_performed": False, "supervisor_invoked": False, "timer_path_invoked": False, "candidate_executed": False, "executor_input_mutated": False, "target_plan_replaced": False, "continuous_automation_enabled": False}}}}
print(json.dumps(summary, indent=2, sort_keys=True))
PY
"""


def build_p10i(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
    command_runner: CommandRunner = local_command_runner,
) -> tuple[dict[str, Any], int]:
    started_at = now_fn()
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof"
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    p10h_path = latest_summary(DEFAULT_P10H_PARENT, args.p10h_summary)
    p10h = load_optional(p10h_path)
    p10g_path = latest_summary(DEFAULT_P10G_PARENT, args.p10g_summary) if str(args.p10g_summary).strip() else resolve_path(
        dict(p10h.get("source_evidence") or {}).get("p10g_summary", {}).get("path") or latest_summary(DEFAULT_P10G_PARENT, "")
    )
    p10g = load_optional(p10g_path)
    p10h_terms_path = source_output_path(p10h, "terms")
    p10h_terms = load_optional(p10h_terms_path)
    candidate_plan_path = source_output_path(p10g, "candidate_target_plan")
    candidate_plan = load_optional(candidate_plan_path)
    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)
    candidate_delta = derive_candidate_delta(p10g, p10h) if p10g and p10h else CandidateDelta(
        status="blocked",
        blockers=["p10g_or_p10h_missing"],
        symbol=CANARY_SYMBOL,
        side="",
        baseline_target_notional_usdt="0",
        candidate_target_notional_usdt="0",
        target_notional_delta_usdt="0",
        approved_notional_cap_usdt=format_decimal(MAX_NOTIONAL_USDT),
        canary_notional_usdt="0",
        target_plan_diff_sha256="",
    )

    owner_record = owner_decision_record(args, started_at)
    write_json(root / "owner_decision_record.json", owner_record)
    pre_checks = {
        "owner_decision_p10i_execute_single_cycle_canary_recorded": str(args.owner_decision) == APPROVE_P10I_DECISION,
        "project_profile_exists": bool(project_profile),
        "current_stage_is_stage3": str(project_profile.get("current_stage") or "") == "stage_3_human_approved_execution",
        "p10h_summary_exists": bool(p10h),
        "p10h_summary_ready_for_p10i": p10h_summary_ready(p10h),
        "p10h_terms_ready": p10h_terms_ready(p10h_terms, p10h),
        "p10g_summary_exists": bool(p10g),
        "p10g_summary_ready": p10g_ready(p10g),
        "candidate_plan_file_hash_matches_p10g": bool(candidate_plan)
        and stable_payload_sha256(candidate_plan) == str(p10g.get("candidate_target_plan_sha256") or ""),
        "candidate_delta_binding_ready": candidate_delta.status == "ready",
        "remote_host_matches_expected_runner": str(args.remote_host) == DEFAULT_REMOTE_HOST,
        "remote_repo_matches_expected_runner": str(args.remote_repo) == DEFAULT_REMOTE_REPO,
        "continuous_automation_not_enabled": True,
    }
    blockers = [key for key, value in pre_checks.items() if not value]
    blockers.extend(candidate_delta.blockers if candidate_delta.status != "ready" else [])

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
        side=candidate_delta.side,
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
    )
    rollback_contract = CanaryPositionRollbackContract(
        status="not_run",
        blockers=[],
        symbol=CANARY_SYMBOL,
        candidate_side=candidate_delta.side,
        pre_position_amt="0",
        post_position_amt="0",
        rollback_mode="cancel_open_order_then_reduce_only_close_only_if_filled",
        reduce_only_restoration_possible_if_filled=False,
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
                    history_canary_symbol=CANARY_SYMBOL,
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
        if account_proof and candidate_delta.status == "ready":
            rollback_contract = canary_position_rollback_contract(
                account_proof=account_proof,
                candidate_delta=candidate_delta,
            )
            if rollback_contract.status != "ready":
                blockers.extend(rollback_contract.blockers)

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
                    canary_symbol=CANARY_SYMBOL,
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
    candidate_account_ready = candidate_scope_account_proof_ready(
        account_proof=account_proof,
        account_delta=account_delta,
        history_delta=history_delta,
        market_delta=market_delta,
    )
    fresh_book = dict(market_collector.get("fresh_order_book") or {})
    filters = dict(market_collector.get("exchange_filter_readback") or {})
    account_identity = dict(account_collector.get("remote_runner_identity_readback") or {})
    market_identity = dict(market_collector.get("remote_runner_identity_readback") or {})

    if account_proof and not candidate_account_ready:
        blockers.append("candidate_scope_account_proof_not_ready")
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
        canary_plan = build_canary_order_plan(
            fresh_book,
            filters,
            candidate_delta,
            maker_buffer_ticks=int(args.maker_buffer_ticks or 1),
        )
        if canary_plan.status != "ready":
            blockers.extend(canary_plan.blockers)
            blockers.append("canary_order_plan_not_ready")

    client_order_id = f"p10i-{started_at.strftime('%Y%m%d%H%M%S')}-{sha256_text(str(root))[:8]}"
    if not blockers:
        order_result = run_record(
            "remote_single_cycle_live_delta_canary_order_submitter",
            ssh_args(
                args.remote_host,
                args.ssh_connect_timeout,
                remote_p10i_order_command(
                    remote_repo=args.remote_repo,
                    remote_live_env=args.remote_live_env,
                    remote_python=args.remote_python,
                    remote_config=args.remote_config,
                    expected_egress_ip=args.expected_egress_ip,
                    symbol=CANARY_SYMBOL,
                    side=candidate_delta.side,
                    client_order_id=client_order_id,
                    max_notional_usdt=candidate_delta.canary_notional_usdt,
                    order_lifetime_seconds=int(args.order_lifetime_seconds or 0),
                    maker_buffer_ticks=int(args.maker_buffer_ticks or 1),
                ),
            ),
        )
        order_submission = json_from_command(order_result)
        write_json(root / "remote_single_cycle_live_delta_canary_order_submission.json", order_submission)
        if order_result.returncode != 0:
            blockers.append("remote_single_cycle_live_delta_canary_order_submitter_failed")
        if order_submission.get("status") != "ready":
            blockers.append("remote_single_cycle_live_delta_canary_order_submitter_not_ready")
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
        if not static_control_boundary_ok(pre_snapshot, post_snapshot):
            blockers.append("remote_control_boundary_changed")

    remote_control_unchanged = static_control_boundary_ok(pre_snapshot, post_snapshot)
    orders_submitted = int(order_submission.get("orders_submitted") or 0)
    orders_canceled = int(order_submission.get("orders_canceled") or 0)
    fill_count = int(order_submission.get("fill_count") or 0)
    trade_count = int(order_submission.get("trade_count") or 0)
    status = "ready" if not blockers and orders_submitted == 1 and fill_count == 0 else "blocked"
    blockers = sorted(set(blockers))

    control = {
        "contract_version": "hv_balanced_12factor_p10i_control_boundary.v1",
        "scope": "single_cycle_live_delta_canary_only",
        "ssh_invoked": bool(command_records),
        "remote_network_connection_performed": bool(account_collector or market_collector or order_submission),
        "fresh_remote_account_read_performed": bool(account_proof),
        "fresh_order_book_read_performed": bool(fresh_book),
        "exchange_filter_read_performed": bool(filters),
        "live_order_submission_performed": orders_submitted == 1,
        "orders_submitted": orders_submitted,
        "orders_canceled": orders_canceled,
        "fill_count": fill_count,
        "trade_count": trade_count,
        "entered_timer_path": False,
        "ran_supervisor": False,
        "timer_path_loaded": False,
        "candidate_execution_performed": orders_submitted == 1,
        "target_plan_replaced": False,
        "executor_input_changed": False,
        "continuous_automation_enabled": False,
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
        "contract_version": "hv_balanced_12factor_p10i_non_authorization.v1",
        "authorizations": {
            "single_cycle_live_delta_canary_order": str(args.owner_decision) == APPROVE_P10I_DECISION,
            "max_orders": 1,
            "symbol": CANARY_SYMBOL,
            "side": candidate_delta.side,
            "max_notional_usdt": format_decimal(MAX_NOTIONAL_USDT),
            "market_order": False,
            "additional_symbols": False,
            "additional_orders": False,
            "timer_path_load": False,
            "supervisor_invocation": False,
            "continuous_automation": False,
            "stage_governance_change": False,
        },
    }
    proof_files = {
        "remote_runner_identity_readback": proof_root / "remote_runner_identity_readback.json",
        "candidate_delta_binding": proof_root / "candidate_delta_binding.json",
        "pit_safe_v2v3_account_proof": proof_root / "pit_safe_v2v3_account_proof.json",
        "account_delta_acceptance": proof_root / "account_delta_acceptance.json",
        "account_history_delta_acceptance": proof_root / "account_history_delta_acceptance.json",
        "remote_stdout_market_collector": proof_root / "remote_stdout_market_collector.json",
        "market_proof_collection_delta_acceptance": proof_root / "market_proof_collection_delta_acceptance.json",
        "fresh_order_book": proof_root / "fresh_order_book.json",
        "exchange_filter_readback": proof_root / "exchange_filter_readback.json",
        "canary_position_rollback_contract": proof_root / "canary_position_rollback_contract.json",
        "canary_order_plan": proof_root / "canary_order_plan.json",
        "remote_single_cycle_live_delta_canary_order_submission": proof_root / "remote_single_cycle_live_delta_canary_order_submission.json",
        "control_boundary_readback": proof_root / "control_boundary_readback.json",
        "non_authorization": proof_root / "non_authorization.json",
        "proof_artifact_manifest": proof_root / "proof_artifact_manifest.json",
    }
    combined_identity = {
        "contract_version": "hv_balanced_12factor_p10i_remote_identity_readback.v1",
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
    write_json(proof_files["candidate_delta_binding"], candidate_delta.to_dict())
    write_json(proof_files["pit_safe_v2v3_account_proof"], account_proof)
    write_json(proof_files["account_delta_acceptance"], account_delta)
    write_json(proof_files["account_history_delta_acceptance"], history_delta)
    write_json(proof_files["remote_stdout_market_collector"], market_collector)
    write_json(proof_files["market_proof_collection_delta_acceptance"], market_delta)
    write_json(proof_files["fresh_order_book"], fresh_book)
    write_json(proof_files["exchange_filter_readback"], filters)
    write_json(proof_files["canary_position_rollback_contract"], rollback_contract.to_dict())
    write_json(proof_files["canary_order_plan"], canary_plan.to_dict())
    write_json(proof_files["remote_single_cycle_live_delta_canary_order_submission"], order_submission)
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
        "p10i_single_cycle_live_delta_canary_ready": status == "ready",
        "p10h_sufficient_for_p10i_execution": p10h_summary_ready(p10h),
        "p10g_hash_bound_to_p10h": str(p10g.get("candidate_target_plan_sha256") or "") == str(p10h.get("candidate_plan_hash") or ""),
        "candidate_delta_binding_ready": candidate_delta.status == "ready",
        "candidate_delta_side": candidate_delta.side,
        "candidate_delta_notional_usdt": candidate_delta.target_notional_delta_usdt,
        "canary_capped_notional_usdt": candidate_delta.canary_notional_usdt,
        "fresh_pre_submit_readback_performed": bool(account_proof and fresh_book and filters),
        "fresh_remote_account_read_performed": bool(account_proof),
        "fresh_order_book_read_performed": bool(fresh_book),
        "exchange_filter_read_performed": bool(filters),
        "strict_pit_safe_v2v3_account_proof_ready": account_proof.get("pit_safe_read_only_account_proof_ready") is True,
        "candidate_scope_account_proof_ready": candidate_account_ready,
        "pit_safe_v2v3_account_proof_ready": candidate_account_ready,
        "can_trade_decision_source": account_proof.get("can_trade_source") or CAN_TRADE_SOURCE,
        "can_trade_pre": account_proof.get("can_trade_pre"),
        "can_trade_post": account_proof.get("can_trade_post"),
        "order_test_endpoint_called": False,
        "canary_position_rollback_contract_ready": rollback_contract.status == "ready",
        "canary_pre_position_amt": rollback_contract.pre_position_amt,
        "canary_post_position_amt": rollback_contract.post_position_amt,
        "canary_reduce_only_restoration_possible_if_filled": rollback_contract.reduce_only_restoration_possible_if_filled,
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
        "candidate_target_plan_sha256": p10g.get("candidate_target_plan_sha256"),
        "baseline_target_plan_sha256": p10g.get("baseline_target_plan_sha256"),
        "actual_target_plan_replacement_performed": False,
        "actual_executor_input_mutation_performed": False,
        "timer_path_load_authorized": False,
        "supervisor_invocation_authorized": False,
        "continuous_automation_enabled": False,
        "remote_files_written": 0,
        "remote_sync_performed": False,
        "canary_symbol": CANARY_SYMBOL,
        "canary_side": candidate_delta.side,
        "max_notional_usdt": float(MAX_NOTIONAL_USDT),
        "maker_buffer_ticks": max(1, int(args.maker_buffer_ticks or 1)),
        "max_orders_per_cycle": 1,
        "max_symbols_per_cycle": 1,
        "order_type": ORDER_TYPE,
        "time_in_force": TIME_IN_FORCE,
        "market_orders_allowed": False,
        "post_only_required": True,
        "maker_only_required": True,
        "limit_order_must_not_cross_spread": True,
        "allowed_next_gate": P10J_GATE,
        "allowed_next_gate_scope": P10J_SCOPE,
        "allowed_next_gate_must_be_separately_requested": True,
        "source_evidence": {
            "p10h_summary": evidence_file(p10h_path),
            "p10h_terms": evidence_file(p10h_terms_path),
            "p10g_summary": evidence_file(p10g_path),
            "candidate_target_plan": evidence_file(candidate_plan_path),
            "project_profile": evidence_file(project_profile_path),
        },
        "gates": {
            **pre_checks,
            "remote_stdout_pit_safe_v2v3_account_collector_ready": p9ci_collector_ready(account_collector),
            "remote_stdout_market_and_fingerprint_collector_ready": p9ce_collector_ready(market_collector),
            "strict_pit_safe_v2v3_account_proof_ready": account_proof.get("pit_safe_read_only_account_proof_ready") is True,
            "candidate_scope_account_proof_ready": candidate_account_ready,
            "pit_safe_v2v3_account_proof_ready": candidate_account_ready,
            "canary_position_rollback_contract_ready": rollback_contract.status == "ready",
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
            "report": str(root / "p10i_single_cycle_live_delta_canary.md"),
            "proof_artifact_manifest": str(proof_files["proof_artifact_manifest"]),
            **{key: str(path) for key, path in proof_files.items() if key != "proof_artifact_manifest"},
        },
    }
    write_json(root / "summary.json", summary)
    (root / "p10i_single_cycle_live_delta_canary.md").write_text(render_markdown(summary), encoding="utf-8")
    return summary, 0 if status == "ready" else 2


def write_proof_manifest(proof_root: Path, files: dict[str, Path]) -> dict[str, Any]:
    entries = {name: evidence_file(path) for name, path in sorted(files.items()) if name != "proof_artifact_manifest"}
    manifest = {
        "contract_version": "hv_balanced_12factor_p10i_proof_artifact_manifest.v1",
        "artifact_count": len(entries),
        "artifacts": entries,
    }
    manifest_path = proof_root / "proof_artifact_manifest.json"
    write_json(manifest_path, manifest)
    manifest["self"] = evidence_file(manifest_path)
    write_json(manifest_path, manifest)
    return manifest


def evidence_file(path: Path | None) -> dict[str, Any]:
    if not path or str(path) == "." or not path.exists() or not path.is_file():
        return {"path": "" if not path or str(path) == "." else str(path), "exists": False, "sha256": ""}
    return {"path": str(path), "exists": True, "sha256": file_sha256(path)}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced 12-Factor P10I Single-Cycle Live Delta Canary",
        "",
        f"`Status: {summary['status']}`",
        "",
        "P10I is scoped to exactly one BTCUSDT post-only GTX canary order derived from the retained P10G candidate delta. It does not load timer/supervisor paths or enable continuous automation.",
        "",
        "## Boundary",
        "",
        "```text",
        f"candidate_delta_side = {summary['candidate_delta_side']}",
        f"candidate_delta_notional_usdt = {summary['candidate_delta_notional_usdt']}",
        f"canary_capped_notional_usdt = {summary['canary_capped_notional_usdt']}",
        f"fresh_pre_submit_readback_performed = {str(bool(summary['fresh_pre_submit_readback_performed'])).lower()}",
        f"canary_position_rollback_contract_ready = {str(bool(summary['canary_position_rollback_contract_ready'])).lower()}",
        f"canary_order_plan_ready = {str(bool(summary['canary_order_plan_ready'])).lower()}",
        f"live_order_submission_performed = {str(bool(summary['live_order_submission_performed'])).lower()}",
        f"orders_submitted = {summary['orders_submitted']}",
        f"orders_canceled = {summary['orders_canceled']}",
        f"fill_count = {summary['fill_count']}",
        f"remote_control_boundary_unchanged = {str(bool(summary['remote_control_boundary_unchanged'])).lower()}",
        "timer_path_load_authorized = false",
        "supervisor_invocation_authorized = false",
        "continuous_automation_enabled = false",
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


def ceil_to_step(value: Decimal, step: Decimal) -> Decimal:
    if step <= 0:
        return Decimal("0")
    return (value / step).to_integral_value(rounding=ROUND_CEILING) * step


def format_decimal(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_p10i(parse_args(argv))
    print("p10i_single_cycle_live_delta_canary_ready=" + str(bool(summary["p10i_single_cycle_live_delta_canary_ready"])).lower())
    print("candidate_delta_side=" + str(summary["candidate_delta_side"]))
    print("orders_submitted=" + str(int(summary["orders_submitted"])))
    print("fill_count=" + str(int(summary["fill_count"])))
    print("summary=" + str(summary["output_files"]["summary"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
