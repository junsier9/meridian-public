from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bs_execution_path_scope_definition import (  # noqa: E402
    DEFAULT_OUTPUT_PARENT as P9BS_SCOPE_PARENT,
    p9bs_scope_ready_for_live_order_gate_review,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bt_stage3_profile_transition import (  # noqa: E402
    DEFAULT_OUTPUT_PARENT as P9BT_PARENT,
    STAGE3,
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
    "hv_balanced_dth60_coinglass_phase9bu_executor_target_plan_preapproval_terms_review.v1"
)
APPROVE_P9BU_DECISION = (
    "approve_p9bu_define_candidate_executor_target_plan_preapproval_and_risk_order_terms_only"
)
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/p9bu_preapproval_terms"
P9BV_GATE = (
    "P9BV_no_order_candidate_target_plan_replacement_dry_run_only_if_separately_requested"
)
P9BV_SCOPE = (
    "prove_candidate_target_plan_replacement_semantics_with_exact_preapproved_terms_no_order"
)
DEFAULT_RISK_CEILING_USDT = 25.0
DEFAULT_MAX_NOTIONAL_USDT = 10.0
DEFAULT_MAX_ORDERS_PER_CYCLE = 1
DEFAULT_MAX_SYMBOLS_PER_CYCLE = 1
DEFAULT_ORDER_TYPE = "post_only_limit"
DEFAULT_TIME_IN_FORCE = "GTX"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Define and review the candidate executor/target-plan integration "
            "preapproval plus concrete risk/order terms. P9BU is not a live-order "
            "gate: it does not replace target plans, mutate executor input, invoke "
            "supervisor/timer/remote paths, execute the candidate, or submit orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9bs-scope-summary", default="")
    parser.add_argument("--phase9bt-summary", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9BU_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:define_and_review_candidate_executor_target_plan_preapproval_terms_no_order",
    )
    parser.add_argument("--risk-ceiling-usdt", type=float, default=DEFAULT_RISK_CEILING_USDT)
    parser.add_argument("--max-notional-usdt", type=float, default=DEFAULT_MAX_NOTIONAL_USDT)
    parser.add_argument("--max-orders-per-cycle", type=int, default=DEFAULT_MAX_ORDERS_PER_CYCLE)
    parser.add_argument("--max-symbols-per-cycle", type=int, default=DEFAULT_MAX_SYMBOLS_PER_CYCLE)
    parser.add_argument("--order-type", default=DEFAULT_ORDER_TYPE)
    parser.add_argument("--time-in-force", default=DEFAULT_TIME_IN_FORCE)
    parser.add_argument(
        "--kill-switch",
        default=(
            "set candidate_overlay_enabled=false; set executor_target_source=baseline_only; "
            "set live_delta_armed=false before any future candidate order gate may resume"
        ),
    )
    parser.add_argument(
        "--rollback-condition",
        action="append",
        default=[
            "candidate target-plan replacement proof missing, stale, or hash-mismatched",
            "executor input hash differs from approved candidate target-plan hash",
            "candidate delta affects anything outside distance_to_high_60 contribution",
            "fresh account, position, open-order, fill, or trade fingerprint missing or stale",
            "any order, cancel, fill, or trade delta is not exactly explained by the approved candidate plan",
            "provider, exchange, risk, or live-supervisor health check reports an exception",
            "realized plus unrealized candidate PnL drawdown exceeds 5 USDT",
        ],
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


def latest_p9bs_scope_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9bs_scope_summary).strip():
        return resolve_path(args.phase9bs_scope_summary)
    return latest_match(P9BS_SCOPE_PARENT, "*/summary.json")


def latest_p9bt_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9bt_summary).strip():
        return resolve_path(args.phase9bt_summary)
    return latest_match(P9BT_PARENT, "*/summary.json")


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def p9bt_ready_for_human_approved_review(summary: dict[str, Any]) -> bool:
    return (
        summary.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9bt_stage3_profile_transition.v1"
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9bt_stage3_profile_transition_ready") is True
        and summary.get("current_stage") == STAGE3
        and summary.get("project_stage_allows_live_order_gate_review") is True
        and summary.get("execution_manifest_stage_minimum_satisfied") is True
        and summary.get("automated_execution_unlocked") is False
        and summary.get("stage4_automated_execution_authorized") is False
        and summary.get("candidate_execution_authorized") is False
        and summary.get("live_order_submission_authorized") is False
        and int_zero(summary, "orders_submitted")
        and int_zero(summary, "fill_count")
    )


def build_terms(args: argparse.Namespace) -> dict[str, Any]:
    rollback_conditions = [
        str(item).strip() for item in (args.rollback_condition or []) if str(item).strip()
    ]
    return {
        "risk_ceiling_usdt": float(args.risk_ceiling_usdt),
        "max_notional_usdt": float(args.max_notional_usdt),
        "max_orders_per_cycle": int(args.max_orders_per_cycle),
        "max_symbols_per_cycle": int(args.max_symbols_per_cycle),
        "order_type": str(args.order_type or "").strip().lower(),
        "time_in_force": str(args.time_in_force or "").strip().upper(),
        "market_orders_allowed": False,
        "post_only_required": True,
        "maker_only_required": True,
        "reduce_only_required_for_rollback_exits": True,
        "candidate_delta_source": "distance_to_high_60_contribution_only",
        "candidate_overlay_components": [
            "coinglass_top_trader_crowded_branch",
            "binance_shock_branch",
        ],
        "fresh_account_read_max_age_seconds": 60,
        "fresh_position_fingerprint_max_age_seconds": 60,
        "fresh_open_order_fingerprint_max_age_seconds": 60,
        "fresh_fill_trade_fingerprint_max_age_seconds": 60,
        "fresh_order_book_max_age_seconds": 10,
        "candidate_artifact_stale_after_seconds": 60,
        "limit_price_must_not_cross_spread": True,
        "max_limit_price_distance_bps_from_mid": 5,
        "max_mark_price_deviation_bps": 10,
        "order_lifetime_seconds": 60,
        "kill_switch": str(args.kill_switch or "").strip(),
        "rollback_conditions": rollback_conditions,
    }


def terms_valid(terms: dict[str, Any]) -> dict[str, bool]:
    risk_ceiling = float(terms.get("risk_ceiling_usdt") or 0)
    max_notional = float(terms.get("max_notional_usdt") or 0)
    max_orders = int(terms.get("max_orders_per_cycle") or 0)
    max_symbols = int(terms.get("max_symbols_per_cycle") or 0)
    return {
        "risk_ceiling_explicit_positive": risk_ceiling > 0,
        "risk_ceiling_within_canary_cap": risk_ceiling <= DEFAULT_RISK_CEILING_USDT,
        "max_notional_explicit_positive": max_notional > 0,
        "max_notional_within_risk_ceiling": 0 < max_notional <= risk_ceiling,
        "max_notional_within_canary_cap": max_notional <= DEFAULT_MAX_NOTIONAL_USDT,
        "max_orders_per_cycle_is_one": max_orders == DEFAULT_MAX_ORDERS_PER_CYCLE,
        "max_symbols_per_cycle_is_one": max_symbols == DEFAULT_MAX_SYMBOLS_PER_CYCLE,
        "order_type_supported_and_explicit": terms.get("order_type") == DEFAULT_ORDER_TYPE,
        "time_in_force_is_post_only_gtx": terms.get("time_in_force") == DEFAULT_TIME_IN_FORCE,
        "market_orders_forbidden": terms.get("market_orders_allowed") is False,
        "post_only_required": terms.get("post_only_required") is True,
        "maker_only_required": terms.get("maker_only_required") is True,
        "candidate_delta_source_is_dth60_only": (
            terms.get("candidate_delta_source") == "distance_to_high_60_contribution_only"
        ),
        "kill_switch_explicit": bool(terms.get("kill_switch")),
        "rollback_conditions_explicit": len(terms.get("rollback_conditions") or []) >= 3,
    }


def build_p9bu_executor_target_plan_preapproval_terms_review(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    now = now_fn()
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9bu" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    p9bs_scope_path = latest_p9bs_scope_summary(args)
    p9bt_path = latest_p9bt_summary(args)
    project_profile_path = resolve_path(args.project_profile)
    p9bs_scope = load_optional(p9bs_scope_path)
    p9bt = load_optional(p9bt_path)
    project_profile = load_optional(project_profile_path)
    terms = build_terms(args)
    term_checks = terms_valid(terms)

    owner_decision_ok = str(args.owner_decision) == APPROVE_P9BU_DECISION
    p9bs_scope_ready = p9bs_scope_ready_for_live_order_gate_review(p9bs_scope)
    p9bt_ready = p9bt_ready_for_human_approved_review(p9bt)
    current_stage = str(project_profile.get("current_stage") or "")
    checks = {
        "owner_decision_p9bu_preapproval_terms_recorded": owner_decision_ok,
        "project_profile_exists": bool(project_profile),
        "current_stage_is_stage3": current_stage == STAGE3,
        "p9bs_scope_summary_exists": bool(p9bs_scope),
        "p9bs_scope_ready": p9bs_scope_ready,
        "p9bt_summary_exists": bool(p9bt),
        "p9bt_stage3_ready": p9bt_ready,
        **term_checks,
    }
    blockers = [key for key, value in checks.items() if not value]
    ready = not blockers

    preapproval_contract = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bu_executor_target_plan_preapproval.v1",
        "run_id": run_id,
        "status": "ready" if ready else "blocked",
        "preapproval_scope": "future_gate_review_only_no_execution",
        "candidate_executor_target_path_preapproval_exists": ready,
        "candidate_executor_target_path_preapproval_review_passed": ready,
        "candidate_enter_executor_target_plan_path_authorized_now": False,
        "candidate_execution_authorized_now": False,
        "live_order_submission_authorized_now": False,
        "integration_contract": {
            "baseline_plan_must_be_generated_first": True,
            "candidate_plan_must_be_paired_with_baseline_same_timestamp": True,
            "candidate_plan_must_use_same_risk_inputs_as_baseline": True,
            "candidate_delta_source": "distance_to_high_60_contribution_only",
            "candidate_overlay_components": terms["candidate_overlay_components"],
            "candidate_target_plan_replacement_requires_future_no_order_dry_run": True,
            "executor_input_replacement_requires_future_live_order_gate": True,
            "executor_must_log_baseline_plan_hash": True,
            "executor_must_log_candidate_plan_hash": True,
            "executor_must_log_delta_hash_and_slice_metrics": True,
            "candidate_artifacts_must_remain_under_proof_artifacts_until_future_gate": True,
        },
    }

    review_packet = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bu_preapproval_terms_review_packet.v1",
        "run_id": run_id,
        "status": "ready" if ready else "blocked",
        "checks": checks,
        "blockers": blockers,
        "terms": terms,
        "preapproval_contract": preapproval_contract,
        "resolved_prior_live_order_blockers_for_future_review": [
            "candidate_executor_target_path_preapproval_exists",
            "risk_ceiling_explicit_positive",
            "max_notional_explicit_positive",
            "max_notional_within_risk_ceiling",
            "order_type_supported_and_explicit",
            "kill_switch_explicit",
            "rollback_conditions_explicit",
            "requested_live_order_terms_complete",
        ]
        if ready
        else [],
    }

    non_authorization_matrix = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bu_non_authorization_matrix.v1",
        "run_id": run_id,
        "authorizations": {
            "define_candidate_executor_target_path_preapproval": ready,
            "define_concrete_risk_order_terms": ready,
            "candidate_enter_executor_target_plan_path_now": False,
            "candidate_execution": False,
            "live_order_submission": False,
            "target_plan_replacement": False,
            "executor_input_mutation": False,
            "live_config_mutation": False,
            "operator_state_mutation": False,
            "timer_or_service_mutation": False,
            "timer_path_load": False,
            "production_timer_service_load": False,
            "supervisor_invocation": False,
            "remote_sync": False,
            "remote_execution": False,
            "stage_governance_change": False,
        },
    }

    control_boundary = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bu_control_boundary_readback.v1",
        "run_id": run_id,
        "scope": "preapproval_terms_review_only_no_order",
        "entered_timer_path": False,
        "ran_supervisor": False,
        "remote_sync_performed": False,
        "remote_execution_performed": False,
        "candidate_execution_performed": False,
        "candidate_entered_executor_target_plan_path": False,
        "live_order_submission_performed": False,
        "target_plan_replaced": False,
        "executor_input_changed": False,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
    }

    owner_record = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bu_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "define_candidate_executor_target_plan_preapproval_and_terms_only",
        "recorded_at_utc": iso_z(now),
        "preapproval_terms_review_approved": owner_decision_ok,
        "candidate_enter_executor_target_plan_path_approved_now": False,
        "candidate_execution_approved": False,
        "live_order_submission_approved": False,
    }

    owner_path = root / "owner_decision_record.json"
    preapproval_path = proof_root / "preapproval.json"
    terms_path = proof_root / "terms.json"
    review_path = proof_root / "review.json"
    matrix_path = proof_root / "non_authorization.json"
    control_path = proof_root / "control.json"
    summary_path = root / "summary.json"
    report_path = root / "p9bu_preapproval_terms.md"

    output_files = {
        "summary": str(summary_path),
        "owner_decision_record": str(owner_path),
        "candidate_executor_target_plan_preapproval": str(preapproval_path),
        "risk_order_terms": str(terms_path),
        "preapproval_terms_review_packet": str(review_path),
        "non_authorization_matrix": str(matrix_path),
        "control_boundary_readback": str(control_path),
        "report": str(report_path),
    }

    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "status": "ready" if ready else "blocked",
        "blockers": blockers,
        "p9bu_preapproval_terms_review_ready": ready,
        "candidate_executor_target_path_preapproval_exists": ready,
        "candidate_executor_target_path_preapproval_review_passed": ready,
        "requested_live_order_terms_complete": ready,
        "risk_ceiling_usdt": terms["risk_ceiling_usdt"],
        "max_notional_usdt": terms["max_notional_usdt"],
        "max_orders_per_cycle": terms["max_orders_per_cycle"],
        "max_symbols_per_cycle": terms["max_symbols_per_cycle"],
        "order_type": terms["order_type"],
        "time_in_force": terms["time_in_force"],
        "kill_switch_explicit": bool(terms["kill_switch"]),
        "rollback_conditions_explicit": len(terms["rollback_conditions"]) >= 3,
        "eligible_for_future_no_order_target_plan_replacement_dry_run": ready,
        "eligible_for_future_live_order_gate_review": ready,
        "allowed_next_gate": P9BV_GATE,
        "allowed_next_gate_scope": P9BV_SCOPE,
        "allowed_next_gate_must_be_separately_requested": True,
        "candidate_enter_executor_target_plan_path_authorized": False,
        "candidate_execution_authorized": False,
        "live_order_submission_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "live_config_mutation_authorized": False,
        "operator_state_mutation_authorized": False,
        "timer_or_service_mutation_authorized": False,
        "timer_path_load_authorized": False,
        "production_timer_service_load_authorized": False,
        "supervisor_invocation_authorized": False,
        "remote_sync_authorized": False,
        "remote_execution_authorized": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
        "source_evidence": {
            "phase9bs_scope_summary": evidence_file(p9bs_scope_path),
            "phase9bt_summary": evidence_file(p9bt_path),
            "project_profile": evidence_file(project_profile_path),
        },
        "output_files": output_files,
    }

    write_json(owner_path, owner_record)
    write_json(preapproval_path, preapproval_contract)
    write_json(terms_path, terms)
    write_json(review_path, review_packet)
    write_json(matrix_path, non_authorization_matrix)
    write_json(control_path, control_boundary)
    write_json(summary_path, summary)
    report_path.write_text(
        "\n".join(
            [
                "# hv_balanced DTH60/CoinGlass P9BU Executor/Target-Plan Preapproval Terms Review",
                "",
                f"`Status: {summary['status']}`",
                "",
                "## Decision",
                "",
                "P9BU defines and reviews the candidate executor/target-plan integration preapproval plus concrete risk/order terms for a future gate. It does not enter the candidate into the executor path, replace target plans, mutate executor input, invoke supervisor/timer/remote paths, execute the candidate, or submit orders.",
                "",
                "```text",
                f"risk_ceiling_usdt = {terms['risk_ceiling_usdt']}",
                f"max_notional_usdt = {terms['max_notional_usdt']}",
                f"order_type = {terms['order_type']}",
                f"time_in_force = {terms['time_in_force']}",
                "candidate_enter_executor_target_plan_path_authorized = false",
                "candidate_execution_authorized = false",
                "live_order_submission_authorized = false",
                "orders_submitted = 0",
                "fill_count = 0",
                "```",
                "",
                "## Rollback Conditions",
                "",
                *[f"- {item}" for item in terms["rollback_conditions"]],
                "",
            ]
        ),
        encoding="utf-8",
    )

    return summary, 0 if ready else 2


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_p9bu_executor_target_plan_preapproval_terms_review(
        parse_args(argv)
    )
    print(f"status={summary['status']}")
    print(f"run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
