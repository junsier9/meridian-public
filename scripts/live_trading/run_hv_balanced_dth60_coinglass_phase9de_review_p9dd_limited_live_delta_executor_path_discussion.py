from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9dd_execute_0_001_btcusdt_round_trip_canary import (  # noqa: E402
    CANARY_QUANTITY,
    CANARY_SYMBOL,
    CONTRACT_VERSION as P9DD_CONTRACT,
    DEFAULT_OUTPUT_PARENT as P9DD_PARENT,
    MAX_GROSS_TURNOVER_USDT,
    MAX_NOTIONAL_PER_LEG_USDT,
    ORDER_TYPE,
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


CONTRACT_VERSION = (
    "hv_balanced_dth60_coinglass_phase9de_review_p9dd_limited_live_delta_executor_path_discussion.v1"
)
APPROVE_P9DE_DECISION = (
    "approve_p9de_review_p9dd_retained_evidence_for_limited_live_delta_candidate_executor_path_canary_discussion_only"
)
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/p9de_review_p9dd_limited_live_delta_executor_path_discussion"
)
P9DF_GATE = (
    "P9DF_define_limited_live_delta_candidate_executor_path_canary_discussion_scope_only_if_separately_requested"
)
P9DF_SCOPE = (
    "define_scope_only_for_single_cycle_limited_live_delta_candidate_executor_path_canary_discussion_after_p9dd"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Review P9DD retained evidence for whether it is sufficient to enter "
            "a limited live_delta / candidate executor-path canary discussion. "
            "P9DE is review-only and does not SSH, call Binance, submit orders, "
            "mutate timer/supervisor/executor paths, or authorize continuous "
            "automated order flow."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9dd-summary", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9DE_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default=(
            "user_chat:review_p9dd_retained_evidence_for_limited_live_delta_"
            "candidate_executor_path_canary_discussion"
        ),
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


def latest_p9dd_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9dd_summary).strip():
        return resolve_path(args.phase9dd_summary)
    return latest_match(P9DD_PARENT, "*/summary.json")


def source_output_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("output_files") or {}).get(key) or "")
    return resolve_path(text) if text.strip() else Path("")


def decimal_value(value: Any, default: str = "0") -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def p9dd_summary_ready(summary: dict[str, Any]) -> bool:
    return (
        summary.get("contract_version") == P9DD_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9dd_0_001_btcusdt_round_trip_canary_ready") is True
        and summary.get("p9dc_sufficient_for_p9dd_execution") is True
        and summary.get("fresh_pre_submit_readback_performed") is True
        and summary.get("fresh_remote_account_read_performed") is True
        and summary.get("fresh_order_book_read_performed") is True
        and summary.get("exchange_filter_read_performed") is True
        and summary.get("can_trade_decision_source") == "/fapi/v2/account.canTrade"
        and summary.get("live_order_submission_authorized") is True
        and summary.get("live_order_submission_performed") is True
        and summary.get("actual_live_order_submission_performed") is True
        and int(summary.get("orders_submitted") or 0) == 2
        and int_zero(summary, "orders_canceled")
        and int(summary.get("fill_count") or 0) == 2
        and int(summary.get("trade_count") or 0) >= 2
        and decimal_value(summary.get("buy_executed_qty")) == CANARY_QUANTITY
        and decimal_value(summary.get("sell_executed_qty")) == CANARY_QUANTITY
        and summary.get("post_position_equals_pre") is True
        and decimal_value(summary.get("gross_turnover_usdt")) <= MAX_GROSS_TURNOVER_USDT
        and decimal_value(summary.get("max_notional_per_leg_usdt")) == MAX_NOTIONAL_PER_LEG_USDT
        and decimal_value(summary.get("max_gross_turnover_usdt")) == MAX_GROSS_TURNOVER_USDT
        and decimal_value(summary.get("quantity_btc")) == CANARY_QUANTITY
        and summary.get("symbol") == CANARY_SYMBOL
        and summary.get("order_type") == ORDER_TYPE
        and summary.get("time_in_force") == TIME_IN_FORCE
        and summary.get("market_orders_allowed") is False
        and summary.get("sell_leg_reduce_only_required") is True
        and summary.get("remote_control_boundary_unchanged") is True
        and summary.get("remote_sync_performed") is False
        and int_zero(summary, "remote_files_written")
        and summary.get("order_test_endpoint_called") is False
        and summary.get("candidate_execution_performed") is False
        and summary.get("target_plan_replaced") is False
        and summary.get("executor_input_mutated") is False
        and summary.get("timer_path_loaded") is False
        and summary.get("supervisor_invoked") is False
    )


def p9dd_control_ready(control: dict[str, Any]) -> bool:
    return (
        control.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9dd_control_boundary.v1"
        and control.get("scope") == "0_001_btcusdt_limit_ioc_round_trip_canary_only"
        and control.get("ssh_invoked") is True
        and control.get("remote_network_connection_performed") is True
        and control.get("fresh_remote_account_read_performed") is True
        and control.get("fresh_order_book_read_performed") is True
        and control.get("exchange_filter_read_performed") is True
        and control.get("order_test_endpoint_called") is False
        and control.get("live_order_submission_performed") is True
        and int(control.get("orders_submitted") or 0) == 2
        and int_zero(control, "orders_canceled")
        and int(control.get("fill_count") or 0) == 2
        and int(control.get("trade_count") or 0) >= 2
        and control.get("entered_timer_path") is False
        and control.get("ran_supervisor") is False
        and control.get("timer_path_loaded") is False
        and control.get("candidate_execution_performed") is False
        and control.get("target_plan_replaced") is False
        and control.get("executor_input_changed") is False
        and control.get("live_config_changed") is False
        and control.get("operator_state_changed") is False
        and control.get("timer_state_changed") is False
        and int_zero(control, "remote_files_written")
        and control.get("remote_sync_performed") is False
    )


def p9dd_submission_ready(submission: dict[str, Any]) -> bool:
    buy = dict(dict(submission.get("buy_order_query") or {}).get("payload") or {})
    sell = dict(dict(submission.get("sell_order_query") or {}).get("payload") or {})
    side_effects = dict(submission.get("side_effects") or {})
    methods = set(str(item).upper() for item in list(side_effects.get("http_methods_used") or []))
    return (
        submission.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9dd_remote_round_trip_canary_submitter.v1"
        and submission.get("status") == "ready"
        and not submission.get("blockers")
        and submission.get("symbol") == CANARY_SYMBOL
        and decimal_value(submission.get("quantity_btc")) == CANARY_QUANTITY
        and int(submission.get("orders_submitted") or 0) == 2
        and int_zero(submission, "orders_canceled")
        and int(submission.get("fill_count") or 0) == 2
        and int(submission.get("trade_count") or 0) >= 2
        and decimal_value(submission.get("buy_executed_qty")) == CANARY_QUANTITY
        and decimal_value(submission.get("sell_executed_qty")) == CANARY_QUANTITY
        and decimal_value(submission.get("gross_turnover_usdt")) <= MAX_GROSS_TURNOVER_USDT
        and submission.get("post_position_equals_pre") is True
        and buy.get("symbol") == CANARY_SYMBOL
        and buy.get("side") == "BUY"
        and buy.get("type") == "LIMIT"
        and buy.get("timeInForce") == TIME_IN_FORCE
        and buy.get("reduceOnly") is False
        and buy.get("status") == "FILLED"
        and decimal_value(buy.get("origQty")) == CANARY_QUANTITY
        and decimal_value(buy.get("executedQty")) == CANARY_QUANTITY
        and sell.get("symbol") == CANARY_SYMBOL
        and sell.get("side") == "SELL"
        and sell.get("type") == "LIMIT"
        and sell.get("timeInForce") == TIME_IN_FORCE
        and sell.get("reduceOnly") is True
        and sell.get("status") == "FILLED"
        and decimal_value(sell.get("origQty")) == CANARY_QUANTITY
        and decimal_value(sell.get("executedQty")) == CANARY_QUANTITY
        and methods == {"GET", "POST"}
        and int(side_effects.get("remote_files_written") or 0) == 0
        and side_effects.get("remote_sync_performed") is False
        and side_effects.get("supervisor_invoked") is False
        and side_effects.get("timer_path_invoked") is False
        and side_effects.get("candidate_executed") is False
        and side_effects.get("executor_input_mutated") is False
        and side_effects.get("target_plan_replaced") is False
        and side_effects.get("order_test_endpoint_called") is False
    )


def owner_decision_record(args: argparse.Namespace, now: datetime) -> dict[str, Any]:
    approved = str(args.owner_decision) == APPROVE_P9DE_DECISION
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9de_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": (
            "review_p9dd_retained_evidence_for_limited_live_delta_candidate_"
            "executor_path_canary_discussion_only"
        ),
        "recorded_at_utc": iso_z(now),
        "p9de_review_approved": approved,
        "limited_live_delta_candidate_executor_path_discussion_allowed": approved,
        "live_order_submission_approved": False,
        "candidate_executor_path_execution_approved": False,
        "continuous_automated_order_flow_approved": False,
        "timer_path_load_approved": False,
        "supervisor_invocation_approved": False,
    }


def build_phase9de(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    started_at = now_fn()
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9de" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    p9dd_path = latest_p9dd_summary(args)
    p9dd = load_optional(p9dd_path)
    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)
    control_path = source_output_path(p9dd, "control_boundary_readback")
    submission_path = source_output_path(p9dd, "remote_round_trip_canary_order_submission")
    command_records_path = source_output_path(p9dd, "command_records")
    terms_path = source_output_path(p9dd, "approved_round_trip_terms")
    control = load_optional(control_path)
    submission = load_optional(submission_path)
    command_records = load_optional(command_records_path)
    terms = load_optional(terms_path)
    owner_record = owner_decision_record(args, started_at)

    command_labels = [
        str(row.get("label"))
        for row in list(command_records.get("commands") or [])
        if isinstance(row, dict)
    ]
    gates = {
        "owner_decision_p9de_review_recorded": str(args.owner_decision) == APPROVE_P9DE_DECISION,
        "project_profile_exists": bool(project_profile),
        "current_stage_is_stage3": str(project_profile.get("current_stage") or "")
        == "stage_3_human_approved_execution",
        "p9dd_summary_exists": bool(p9dd),
        "p9dd_summary_ready_for_review": p9dd_summary_ready(p9dd),
        "p9dd_control_boundary_ready": p9dd_control_ready(control),
        "p9dd_remote_submission_ready": p9dd_submission_ready(submission),
        "p9dd_command_sequence_expected": command_labels
        == [
            "pre_control_snapshot",
            "remote_round_trip_canary_order_submitter",
            "post_control_snapshot",
        ],
        "p9dc_terms_bound_to_p9dd": terms.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9dc_0_001_btcusdt_round_trip_canary_terms.v1"
        and terms.get("allowed_next_gate") == "P9DD_execute_0_001_btcusdt_buy_then_reduce_only_sell_canary",
    }
    blockers = sorted(key for key, value in gates.items() if not value)
    status = "ready" if not blockers else "blocked"
    sufficient_for_discussion = status == "ready"

    review = {
        "contract_version": (
            "hv_balanced_dth60_coinglass_phase9de_p9dd_limited_executor_path_discussion_review.v1"
        ),
        "review_only": True,
        "p9dd_retained_evidence_sufficient_for_review": sufficient_for_discussion,
        "p9dd_sufficient_for_limited_live_delta_candidate_executor_path_canary_discussion": sufficient_for_discussion,
        "p9dd_sufficient_for_live_order_submission_without_new_gate": False,
        "p9dd_sufficient_for_candidate_executor_path_execution_without_new_gate": False,
        "p9dd_sufficient_for_continuous_automated_order_flow": False,
        "positive_findings": [
            "single bounded live order round-trip completed with fresh readback",
            "buy and reduce-only sell both filled exact 0.001 BTCUSDT",
            "BTCUSDT position returned to pre-run amount",
            "remote control boundary stayed unchanged",
            "timer/supervisor/executor/candidate paths were not touched",
        ],
        "required_next_discussion_constraints": {
            "scope_type": "discussion_and_scope_definition_only",
            "max_cycles_to_discuss": 1,
            "candidate_path_mode": "single_cycle_canary_only",
            "default_order_state": "disabled_until_separate_execution_gate",
            "continuous_automated_order_flow": "not_allowed",
            "must_define_kill_switch": True,
            "must_define_max_notional": True,
            "must_define_candidate_plan_hash_binding": True,
            "must_define_baseline_fallback": True,
            "must_define_post_run_position_reconciliation": True,
        },
        "checks": gates,
    }
    non_auth = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9de_non_authorization.v1",
        "authorizations": {
            "review_p9dd_retained_evidence": str(args.owner_decision) == APPROVE_P9DE_DECISION,
            "allow_future_limited_live_delta_candidate_executor_path_discussion_scope_gate": sufficient_for_discussion,
            "live_order_submission_in_p9de": False,
            "candidate_executor_path_execution_in_p9de": False,
            "candidate_target_plan_replacement_in_p9de": False,
            "executor_input_mutation_in_p9de": False,
            "timer_path_load_in_p9de": False,
            "supervisor_invocation_in_p9de": False,
            "remote_execution_in_p9de": False,
            "remote_sync_in_p9de": False,
            "remote_file_write_in_p9de": False,
            "continuous_automated_order_flow": False,
            "stage_governance_change": False,
        },
    }
    control_review = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9de_control_boundary.v1",
        "scope": "retained_evidence_review_only",
        "ssh_invoked": False,
        "remote_network_connection_performed": False,
        "fresh_remote_account_read_performed": False,
        "fresh_order_book_read_performed": False,
        "exchange_filter_read_performed": False,
        "order_test_endpoint_called": False,
        "live_order_submission_performed": False,
        "candidate_execution_performed": False,
        "target_plan_replaced": False,
        "executor_input_changed": False,
        "entered_timer_path": False,
        "ran_supervisor": False,
        "timer_path_loaded": False,
        "remote_sync_performed": False,
        "remote_files_written": 0,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
    }

    proof_files = {
        "p9dd_limited_executor_path_discussion_review": proof_root / "p9dd_limited_executor_path_discussion_review.json",
        "non_authorization": proof_root / "non_authorization.json",
        "control_boundary_readback": proof_root / "control_boundary_readback.json",
        "owner_decision_record": root / "owner_decision_record.json",
    }
    write_json(proof_files["p9dd_limited_executor_path_discussion_review"], review)
    write_json(proof_files["non_authorization"], non_auth)
    write_json(proof_files["control_boundary_readback"], control_review)
    write_json(proof_files["owner_decision_record"], owner_record)
    manifest_path = proof_root / "proof_artifact_manifest.json"
    manifest = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9de_proof_artifact_manifest.v1",
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
        "p9de_review_p9dd_limited_live_delta_executor_path_discussion_ready": status == "ready",
        "p9dd_retained_evidence_sufficient_for_p9de_review": sufficient_for_discussion,
        "p9dd_sufficient_for_limited_live_delta_candidate_executor_path_canary_discussion": sufficient_for_discussion,
        "p9dd_sufficient_for_live_order_submission_without_new_gate": False,
        "p9dd_sufficient_for_candidate_executor_path_execution_without_new_gate": False,
        "p9dd_sufficient_for_continuous_automated_order_flow": False,
        "allowed_scope_after_p9de": "discussion_and_scope_definition_only",
        "eligible_for_future_p9df_scope_definition_gate": sufficient_for_discussion,
        "live_order_submission_authorized": False,
        "candidate_executor_path_execution_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "timer_path_load_authorized": False,
        "supervisor_invocation_authorized": False,
        "continuous_automated_order_flow_authorized": False,
        "remote_execution_performed": False,
        "remote_sync_performed": False,
        "remote_files_written": 0,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
        "p9dd_orders_submitted": p9dd.get("orders_submitted"),
        "p9dd_fill_count": p9dd.get("fill_count"),
        "p9dd_trade_count": p9dd.get("trade_count"),
        "p9dd_gross_turnover_usdt": p9dd.get("gross_turnover_usdt"),
        "p9dd_pre_btcusdt_position_amt": p9dd.get("pre_btcusdt_position_amt"),
        "p9dd_post_btcusdt_position_amt": p9dd.get("post_btcusdt_position_amt"),
        "p9dd_remote_control_boundary_unchanged": p9dd.get("remote_control_boundary_unchanged"),
        "source_evidence": {
            "phase9dd_summary": evidence_file(p9dd_path),
            "phase9dd_control_boundary_readback": evidence_file(control_path),
            "phase9dd_remote_round_trip_canary_order_submission": evidence_file(submission_path),
            "phase9dd_command_records": evidence_file(command_records_path),
            "phase9dc_approved_round_trip_terms": evidence_file(terms_path),
            "project_profile": evidence_file(project_profile_path),
        },
        "gates": gates,
        "allowed_next_gate": P9DF_GATE,
        "allowed_next_gate_scope": P9DF_SCOPE,
        "allowed_next_gate_must_be_separately_requested": True,
        "output_files": {
            "summary": str(root / "summary.json"),
            "report": str(root / "p9de_review_p9dd_limited_live_delta_executor_path_discussion.md"),
            "proof_artifact_manifest": str(manifest_path),
            **{key: str(path) for key, path in proof_files.items()},
        },
    }
    write_json(root / "summary.json", summary)
    (root / "p9de_review_p9dd_limited_live_delta_executor_path_discussion.md").write_text(
        render_markdown(summary), encoding="utf-8"
    )
    return summary, 0 if status == "ready" else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9DE P9DD Limited Executor-Path Discussion Review",
        "",
        f"`Status: {summary['status']}`",
        "",
        "P9DE is retained-evidence review only. It decides whether P9DD is sufficient for a limited live_delta / candidate executor-path canary discussion, not for execution.",
        "",
        "```text",
        "sufficient_for_limited_discussion = "
        f"{str(bool(summary['p9dd_sufficient_for_limited_live_delta_candidate_executor_path_canary_discussion'])).lower()}",
        "sufficient_for_live_order_submission_without_new_gate = false",
        "sufficient_for_candidate_executor_path_execution_without_new_gate = false",
        "sufficient_for_continuous_automated_order_flow = false",
        f"p9dd_orders_submitted = {summary['p9dd_orders_submitted']}",
        f"p9dd_fill_count = {summary['p9dd_fill_count']}",
        f"p9dd_trade_count = {summary['p9dd_trade_count']}",
        f"p9dd_pre_btcusdt_position_amt = {summary['p9dd_pre_btcusdt_position_amt']}",
        f"p9dd_post_btcusdt_position_amt = {summary['p9dd_post_btcusdt_position_amt']}",
        "live_order_submission_authorized = false",
        "candidate_executor_path_execution_authorized = false",
        "continuous_automated_order_flow_authorized = false",
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
    summary, exit_code = build_phase9de(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
