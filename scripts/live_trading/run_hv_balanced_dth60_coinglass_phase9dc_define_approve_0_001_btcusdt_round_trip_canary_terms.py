from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9db_review_p9da_blocked_no_order_evidence import (  # noqa: E402
    CONTRACT_VERSION as P9DB_CONTRACT,
    DEFAULT_OUTPUT_PARENT as P9DB_PARENT,
    P9DC_GATE,
    P9DC_SCOPE,
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


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9dc_define_approve_0_001_btcusdt_round_trip_canary_terms.v1"
APPROVE_P9DC_DECISION = "approve_p9dc_0_001_btcusdt_round_trip_canary_terms_only"
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/p9dc_0_001_btcusdt_round_trip_canary_terms"
P9DD_GATE = "P9DD_execute_0_001_btcusdt_buy_then_reduce_only_sell_canary"
P9DD_SCOPE = (
    "execute_one_0_001_btcusdt_limit_ioc_buy_then_one_0_001_btcusdt_limit_ioc_reduce_only_sell_after_fresh_readback"
)

CANARY_SYMBOL = "BTCUSDT"
CANARY_QUANTITY = Decimal("0.001")
MAX_NOTIONAL_PER_LEG_USDT = Decimal("75")
MAX_GROSS_TURNOVER_USDT = Decimal("150")
MAX_ORDERS = 2
PRICE_COLLAR_BPS = Decimal("10")
TIME_IN_FORCE = "IOC"
ORDER_TYPE = "limit_ioc_round_trip"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Define and approve P9DC terms for one 0.001 BTCUSDT buy followed "
            "by one 0.001 BTCUSDT reduce-only sell. P9DC records terms only; "
            "it does not SSH, submit orders, execute candidate logic, or mutate "
            "timer/supervisor/executor paths."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9db-summary", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9DC_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:p9dc_define_and_approve_0_001_btcusdt_round_trip_canary_terms",
    )
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def fmt(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def phase_root(args: argparse.Namespace, run_id: str) -> Path:
    if str(args.output_root).strip():
        return resolve_path(args.output_root)
    return resolve_path(DEFAULT_OUTPUT_PARENT) / run_id


def latest_p9db_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9db_summary).strip():
        return resolve_path(args.phase9db_summary)
    return latest_match(P9DB_PARENT, "*/summary.json")


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def p9db_summary_ready(summary: dict[str, Any]) -> bool:
    return (
        summary.get("contract_version") == P9DB_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9db_review_p9da_blocked_no_order_evidence_ready") is True
        and summary.get("p9da_retained_evidence_sufficient_for_p9db_review") is True
        and summary.get("p9da_proved_btcusdt_minimum_notional_exceeded_authorized_max") is True
        and summary.get("p9da_proved_order_submitter_not_invoked") is True
        and summary.get("p9da_proved_zero_orders_fills") is True
        and summary.get("future_round_trip_terms_change_required") is True
        and summary.get("eligible_for_future_p9dc_round_trip_terms_gate") is True
        and summary.get("eligible_for_live_order_submission") is False
        and summary.get("round_trip_terms_approved") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("live_order_submission_performed") is False
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
        and summary.get("allowed_next_gate") == P9DC_GATE
        and summary.get("allowed_next_gate_scope") == P9DC_SCOPE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
    )


def approved_terms(now: datetime, args: argparse.Namespace) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9dc_0_001_btcusdt_round_trip_canary_terms.v1",
        "owner": args.owner,
        "approved_at_utc": iso_z(now),
        "approval_decision": args.owner_decision,
        "approval_decision_source": args.owner_decision_source,
        "symbol": CANARY_SYMBOL,
        "quantity_btc": fmt(CANARY_QUANTITY),
        "max_notional_per_leg_usdt": fmt(MAX_NOTIONAL_PER_LEG_USDT),
        "max_gross_turnover_usdt": fmt(MAX_GROSS_TURNOVER_USDT),
        "max_orders_total": MAX_ORDERS,
        "max_symbols_total": 1,
        "order_type": ORDER_TYPE,
        "time_in_force": TIME_IN_FORCE,
        "price_collar_bps": fmt(PRICE_COLLAR_BPS),
        "market_orders_allowed": False,
        "post_only_required": False,
        "maker_only_required": False,
        "taker_execution_allowed": True,
        "emergency_reduce_only_market_fallback_allowed": False,
        "legs": [
            {
                "leg_id": "buy_opening_probe",
                "sequence": 1,
                "side": "BUY",
                "type": "LIMIT",
                "time_in_force": TIME_IN_FORCE,
                "quantity": fmt(CANARY_QUANTITY),
                "reduce_only": False,
                "limit_price_rule": "ceil(best_ask * (1 + price_collar_bps / 10000), tick_size)",
                "must_fill_exact_quantity_before_next_leg": True,
            },
            {
                "leg_id": "sell_reduce_only_close_probe",
                "sequence": 2,
                "side": "SELL",
                "type": "LIMIT",
                "time_in_force": TIME_IN_FORCE,
                "quantity": fmt(CANARY_QUANTITY),
                "reduce_only": True,
                "limit_price_rule": "floor(best_bid * (1 - price_collar_bps / 10000), tick_size)",
                "must_run_only_after_buy_filled_exact_quantity": True,
                "must_fill_exact_quantity": True,
            },
        ],
        "fresh_pre_submit_requirements": [
            "read /fapi/v2/account and require canTrade true from /fapi/v2/account.canTrade",
            "read /fapi/v3/account but do not source canTrade from v3",
            "read position mode and require one-way/BOTH order semantics",
            "read pre position/open-order/history fingerprint",
            "require BTCUSDT pre position amount >= 0 before buy-then-reduce-only-sell",
            "read fresh BTCUSDT book and exchange filters",
            "prove quantity 0.001 satisfies LOT_SIZE and MIN_NOTIONAL under current book",
            "prove each leg notional <= max_notional_per_leg_usdt",
            "prove gross turnover upper bound <= max_gross_turnover_usdt",
            "read remote control boundary before and after",
        ],
        "post_submit_acceptance": {
            "orders_submitted_exactly": 2,
            "orders_canceled_exactly": 0,
            "buy_executed_qty_exact": fmt(CANARY_QUANTITY),
            "sell_executed_qty_exact": fmt(CANARY_QUANTITY),
            "sell_reduce_only_required": True,
            "post_open_orders_zero": True,
            "post_btcusdt_position_must_equal_pre_btcusdt_position": True,
            "remote_control_boundary_unchanged": True,
            "timer_path_loaded": False,
            "supervisor_invoked": False,
            "candidate_executed": False,
            "target_plan_replaced": False,
            "executor_input_mutated": False,
            "remote_sync_performed": False,
            "remote_files_written": 0,
        },
        "allowed_next_gate": P9DD_GATE,
        "allowed_next_gate_scope": P9DD_SCOPE,
        "allowed_next_gate_must_be_separately_requested": True,
    }


def owner_decision_record(args: argparse.Namespace, now: datetime) -> dict[str, Any]:
    approved = str(args.owner_decision) == APPROVE_P9DC_DECISION
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9dc_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "define_and_approve_0_001_btcusdt_round_trip_canary_terms_only",
        "recorded_at_utc": iso_z(now),
        "p9dc_round_trip_terms_approved": approved,
        "future_p9dd_round_trip_execution_may_be_requested": approved,
        "live_order_submission_in_p9dc": False,
        "remote_execution_approved_in_p9dc": False,
        "timer_path_load_approved": False,
        "supervisor_invocation_approved": False,
        "candidate_execution_approved": False,
    }


def build_phase9dc(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    started_at = now_fn()
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9dc" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    p9db_path = latest_p9db_summary(args)
    p9db = load_optional(p9db_path)
    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)
    terms = approved_terms(started_at, args)
    owner_record = owner_decision_record(args, started_at)

    gates = {
        "owner_decision_p9dc_terms_recorded": str(args.owner_decision) == APPROVE_P9DC_DECISION,
        "project_profile_exists": bool(project_profile),
        "current_stage_is_stage3": str(project_profile.get("current_stage") or "")
        == "stage_3_human_approved_execution",
        "p9db_summary_exists": bool(p9db),
        "p9db_summary_ready_for_p9dc": p9db_summary_ready(p9db),
        "terms_symbol_btcusdt": terms["symbol"] == CANARY_SYMBOL,
        "terms_quantity_is_0_001": Decimal(str(terms["quantity_btc"])) == CANARY_QUANTITY,
        "terms_max_notional_per_leg_75": Decimal(str(terms["max_notional_per_leg_usdt"]))
        == MAX_NOTIONAL_PER_LEG_USDT,
        "terms_gross_turnover_150": Decimal(str(terms["max_gross_turnover_usdt"]))
        == MAX_GROSS_TURNOVER_USDT,
        "terms_limit_ioc_not_market": terms["order_type"] == ORDER_TYPE
        and terms["time_in_force"] == TIME_IN_FORCE
        and terms["market_orders_allowed"] is False,
        "terms_sell_leg_reduce_only": dict(terms["legs"][1]).get("reduce_only") is True,
        "terms_forbid_timer_supervisor_executor_candidate": terms["post_submit_acceptance"][
            "timer_path_loaded"
        ]
        is False
        and terms["post_submit_acceptance"]["supervisor_invoked"] is False
        and terms["post_submit_acceptance"]["candidate_executed"] is False
        and terms["post_submit_acceptance"]["target_plan_replaced"] is False
        and terms["post_submit_acceptance"]["executor_input_mutated"] is False,
    }
    blockers = sorted(key for key, value in gates.items() if not value)
    status = "ready" if not blockers else "blocked"

    non_auth = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9dc_non_authorization.v1",
        "authorizations": {
            "define_and_approve_round_trip_terms": str(args.owner_decision) == APPROVE_P9DC_DECISION,
            "future_p9dd_round_trip_execution_request_allowed": status == "ready",
            "live_order_submission_in_p9dc": False,
            "remote_execution_in_p9dc": False,
            "remote_sync": False,
            "remote_file_write": False,
            "market_order": False,
            "emergency_market_fallback": False,
            "timer_path_load": False,
            "supervisor_invocation": False,
            "candidate_execution": False,
            "target_plan_replacement": False,
            "executor_input_mutation": False,
            "stage_governance_change": False,
        },
    }
    control = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9dc_control_boundary.v1",
        "scope": "terms_approval_only",
        "ssh_invoked": False,
        "remote_network_connection_performed": False,
        "fresh_remote_account_read_performed": False,
        "fresh_order_book_read_performed": False,
        "exchange_filter_read_performed": False,
        "order_test_endpoint_called": False,
        "live_order_submission_performed": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
        "entered_timer_path": False,
        "ran_supervisor": False,
        "timer_path_loaded": False,
        "candidate_execution_performed": False,
        "target_plan_replaced": False,
        "executor_input_changed": False,
        "remote_files_written": 0,
        "remote_sync_performed": False,
    }

    proof_files = {
        "approved_round_trip_terms": proof_root / "approved_round_trip_terms.json",
        "owner_decision_record": root / "owner_decision_record.json",
        "non_authorization": proof_root / "non_authorization.json",
        "control_boundary_readback": proof_root / "control_boundary_readback.json",
    }
    write_json(proof_files["approved_round_trip_terms"], terms)
    write_json(proof_files["owner_decision_record"], owner_record)
    write_json(proof_files["non_authorization"], non_auth)
    write_json(proof_files["control_boundary_readback"], control)
    manifest_path = proof_root / "proof_artifact_manifest.json"
    manifest = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9dc_proof_artifact_manifest.v1",
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
        "p9dc_0_001_btcusdt_round_trip_canary_terms_ready": status == "ready",
        "p9db_sufficient_for_p9dc_terms_gate": p9db_summary_ready(p9db),
        "round_trip_terms_approved": status == "ready",
        "eligible_for_future_p9dd_round_trip_canary_execution": status == "ready",
        "live_order_submission_authorized": status == "ready",
        "live_order_submission_performed": False,
        "actual_live_order_submission_performed": False,
        "authorization_scope": "future_p9dd_0_001_btcusdt_buy_then_reduce_only_sell_canary_only",
        "symbol": CANARY_SYMBOL,
        "quantity_btc": float(CANARY_QUANTITY),
        "max_notional_per_leg_usdt": float(MAX_NOTIONAL_PER_LEG_USDT),
        "max_gross_turnover_usdt": float(MAX_GROSS_TURNOVER_USDT),
        "max_orders_total": MAX_ORDERS,
        "max_symbols_total": 1,
        "order_type": ORDER_TYPE,
        "time_in_force": TIME_IN_FORCE,
        "price_collar_bps": float(PRICE_COLLAR_BPS),
        "market_orders_allowed": False,
        "post_only_required": False,
        "maker_only_required": False,
        "taker_execution_allowed": True,
        "sell_leg_reduce_only_required": True,
        "emergency_reduce_only_market_fallback_allowed": False,
        "pre_submit_fresh_readback_required_before_p9dd": True,
        "post_position_must_equal_pre_position": True,
        "remote_execution_performed": False,
        "remote_sync_performed": False,
        "remote_files_written": 0,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
        "candidate_execution_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "timer_path_load_authorized": False,
        "supervisor_invocation_authorized": False,
        "source_evidence": {
            "phase9db_summary": evidence_file(p9db_path),
            "project_profile": evidence_file(project_profile_path),
        },
        "gates": gates,
        "allowed_next_gate": P9DD_GATE,
        "allowed_next_gate_scope": P9DD_SCOPE,
        "allowed_next_gate_must_be_separately_requested": True,
        "output_files": {
            "summary": str(root / "summary.json"),
            "report": str(root / "p9dc_0_001_btcusdt_round_trip_canary_terms.md"),
            "proof_artifact_manifest": str(manifest_path),
            **{key: str(path) for key, path in proof_files.items()},
        },
    }
    write_json(root / "summary.json", summary)
    (root / "p9dc_0_001_btcusdt_round_trip_canary_terms.md").write_text(
        render_markdown(summary), encoding="utf-8"
    )
    return summary, 0 if status == "ready" else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9DC 0.001 BTCUSDT Round-Trip Terms",
        "",
        f"`Status: {summary['status']}`",
        "",
        "P9DC records new terms only. It does not submit orders.",
        "",
        "```text",
        f"symbol = {summary['symbol']}",
        f"quantity_btc = {summary['quantity_btc']}",
        f"max_notional_per_leg_usdt = {summary['max_notional_per_leg_usdt']}",
        f"max_gross_turnover_usdt = {summary['max_gross_turnover_usdt']}",
        f"order_type = {summary['order_type']}",
        f"time_in_force = {summary['time_in_force']}",
        "market_orders_allowed = false",
        "sell_leg_reduce_only_required = true",
        "live_order_submission_performed = false",
        "```",
        "",
        "## Blockers",
        "",
    ]
    blockers = list(summary.get("blockers") or [])
    lines.extend([f"- `{item}`" for item in blockers] if blockers else ["- none"])
    lines.extend(["", "## Allowed Next Gate", "", "```text", str(summary["allowed_next_gate"]), "```", ""])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_phase9dc(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
