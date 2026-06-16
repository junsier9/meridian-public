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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ck_define_post_account_blocker_live_order_readiness_scope import (  # noqa: E402
    CANARY_SIDE,
    CANARY_SYMBOL,
    CONTRACT_VERSION as P9CK_CONTRACT,
    DEFAULT_MAX_NOTIONAL_USDT,
    DEFAULT_MAX_ORDERS_PER_CYCLE,
    DEFAULT_MAX_SYMBOLS_PER_CYCLE,
    DEFAULT_ORDER_TYPE,
    DEFAULT_OUTPUT_PARENT as P9CK_PARENT,
    DEFAULT_RISK_CEILING_USDT,
    DEFAULT_TIME_IN_FORCE,
    P9CL_GATE,
    P9CL_SCOPE,
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
    "hv_balanced_dth60_coinglass_phase9cl_post_account_blocker_live_order_readiness_review_package.v1"
)
APPROVE_P9CL_DECISION = (
    "approve_p9cl_prepare_post_account_blocker_live_order_readiness_review_package_only_no_order_no_remote_no_execution"
)
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/p9cl_post_account_blocker_live_order_readiness_review_package"
)
P9CM_GATE = (
    "P9CM_review_p9cl_post_account_blocker_live_order_readiness_review_package_only_if_separately_requested"
)
P9CM_SCOPE = (
    "review_p9cl_package_sufficiency_before_any_fresh_remote_proof_collection_or_live_order_no_remote_no_order_no_execution"
)
EXPECTED_PROOFS = {
    "pit_safe_v2v3_account_proof": 60,
    "fresh_position_open_order_balance_fingerprints": 60,
    "fresh_order_trade_history_delta": 60,
    "fresh_order_book_and_exchange_filters": 10,
    "same_risk_paired_target_plan_binding": 60,
    "distance_to_high_60_only_delta": 60,
    "no_order_candidate_target_plan_replacement_dry_run": 60,
    "kill_switch_and_rollback_readback": 60,
    "final_owner_live_order_gate_approval": 300,
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare the P9CL post-account-blocker live-order readiness review "
            "package from retained P9CK scope evidence. P9CL is package-only: it "
            "does not SSH, read Binance, collect fresh proofs, run supervisor or "
            "timer paths, execute the candidate, mutate executor input or target "
            "plans, remote sync, cancel orders, or submit orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9ck-summary", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9CL_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default=(
            "user_chat:p9cl_prepare_post_account_blocker_live_order_readiness_review_package_only_if_separately_requested"
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


def latest_p9ck_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9ck_summary).strip():
        return resolve_path(args.phase9ck_summary)
    return latest_match(P9CK_PARENT, "*/summary.json")


def source_output_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("output_files") or {}).get(key) or "")
    return resolve_path(text) if text.strip() else Path("")


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def p9ck_summary_ready(summary: dict[str, Any]) -> bool:
    checks = dict(summary.get("checks") or {})
    return (
        summary.get("contract_version") == P9CK_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9ck_post_account_blocker_live_order_readiness_scope_defined")
        is True
        and summary.get("p9cj_sufficient_for_p9ck_scope_definition") is True
        and summary.get("account_blocker_cleared_before_p9ck") is True
        and summary.get("live_order_readiness_scope_defined_after_account_blocker_clearance")
        is True
        and int(summary.get("required_fresh_proof_count") or 0) == len(EXPECTED_PROOFS)
        and summary.get("fresh_proofs_required_before_any_future_order_submission")
        is True
        and summary.get("fresh_proofs_satisfied_by_p9ck") is False
        and summary.get("eligible_for_future_p9cl_review_package") is True
        and summary.get("eligible_for_future_fresh_remote_proof_collection") is False
        and summary.get("eligible_for_future_live_order_submission") is False
        and summary.get("eligible_for_future_candidate_execution") is False
        and summary.get("eligible_for_future_candidate_executor_path_entry") is False
        and summary.get("fresh_remote_proof_collection_performed_in_p9ck") is False
        and summary.get("fresh_remote_account_read_performed") is False
        and summary.get("fresh_order_book_read_performed") is False
        and summary.get("exchange_filter_read_performed") is False
        and summary.get("order_test_endpoint_called") is False
        and summary.get("remote_execution_performed") is False
        and summary.get("remote_sync_performed") is False
        and int_zero(summary, "remote_files_written")
        and summary.get("live_order_gate_approved") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("candidate_execution_authorized") is False
        and summary.get("target_plan_replacement_authorized") is False
        and summary.get("executor_input_mutation_authorized") is False
        and summary.get("timer_path_load_authorized") is False
        and summary.get("supervisor_invocation_authorized") is False
        and summary.get("allowed_next_gate") == P9CL_GATE
        and summary.get("allowed_next_gate_scope") == P9CL_SCOPE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
        and summary.get("canary_symbol") == CANARY_SYMBOL
        and summary.get("canary_side") == CANARY_SIDE
        and float(summary.get("risk_ceiling_usdt") or 0) == DEFAULT_RISK_CEILING_USDT
        and float(summary.get("max_notional_usdt") or 0) == DEFAULT_MAX_NOTIONAL_USDT
        and int(summary.get("max_orders_per_cycle") or 0) == DEFAULT_MAX_ORDERS_PER_CYCLE
        and int(summary.get("max_symbols_per_cycle") or 0) == DEFAULT_MAX_SYMBOLS_PER_CYCLE
        and summary.get("order_type") == DEFAULT_ORDER_TYPE
        and summary.get("time_in_force") == DEFAULT_TIME_IN_FORCE
        and summary.get("market_orders_allowed") is False
        and summary.get("source_p9cj_account_blocker_cleared") is True
        and list(summary.get("source_p9cj_live_order_readiness_blockers_after_account_review") or [])
        == []
        and list(summary.get("source_p9cj_remaining_account_permission_blockers") or [])
        == []
        and summary.get("source_p9cj_can_trade_decision_source")
        == "/fapi/v2/account.canTrade"
        and summary.get("source_p9cj_can_trade_pre") is True
        and summary.get("source_p9cj_can_trade_post") is True
        and summary.get("source_p9cj_order_cancel_fill_trade_delta_zero") is True
        and summary.get("source_p9cj_remote_control_boundary_unchanged") is True
        and int_zero(summary, "orders_submitted")
        and int_zero(summary, "orders_canceled")
        and int_zero(summary, "fill_count")
        and int_zero(summary, "trade_count")
        and bool(checks)
        and all(value is True for value in checks.values())
    )


def p9ck_scope_ready(scope: dict[str, Any]) -> bool:
    canary = dict(scope.get("canary_terms") or {})
    target = dict(scope.get("target_runner") or {})
    return (
        scope.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9ck_post_account_blocker_live_order_readiness_scope.v1"
        and scope.get("scope_definition_only") is True
        and scope.get("account_blocker_status") == "cleared_by_p9cj_retained_review"
        and scope.get("future_gate_name") == "post_account_blocker_live_order_readiness_review"
        and "whether a post-account-blocker review package is complete"
        in list(scope.get("future_gate_may_discuss") or [])
        and "new PIT-safe v2/v3 account proof after P9CJ"
        in list(scope.get("future_gate_may_not_skip") or [])
        and "separate final owner live-order gate"
        in list(scope.get("future_gate_may_not_skip") or [])
        and canary.get("symbol") == CANARY_SYMBOL
        and canary.get("side") == CANARY_SIDE
        and float(canary.get("risk_ceiling_usdt") or 0) == DEFAULT_RISK_CEILING_USDT
        and float(canary.get("max_notional_usdt") or 0) == DEFAULT_MAX_NOTIONAL_USDT
        and int(canary.get("max_orders_per_cycle") or 0) == DEFAULT_MAX_ORDERS_PER_CYCLE
        and int(canary.get("max_symbols_per_cycle") or 0) == DEFAULT_MAX_SYMBOLS_PER_CYCLE
        and canary.get("order_type") == DEFAULT_ORDER_TYPE
        and canary.get("time_in_force") == DEFAULT_TIME_IN_FORCE
        and canary.get("market_orders_allowed") is False
        and canary.get("post_only_required") is True
        and canary.get("maker_only_required") is True
        and canary.get("candidate_delta_source") == "distance_to_high_60_contribution_only"
        and target.get("remote_host") == "root@203.0.113.10"
        and target.get("expected_egress_ip") == "203.0.113.10"
        and "fresh remote proof collection" in list(scope.get("out_of_scope_for_p9ck") or [])
        and "actual order placement" in list(scope.get("out_of_scope_for_p9ck") or [])
        and "candidate execution" in list(scope.get("out_of_scope_for_p9ck") or [])
        and "actual target-plan replacement"
        in list(scope.get("out_of_scope_for_p9ck") or [])
        and "executor-input mutation" in list(scope.get("out_of_scope_for_p9ck") or [])
        and "timer or service mutation" in list(scope.get("out_of_scope_for_p9ck") or [])
        and "supervisor invocation" in list(scope.get("out_of_scope_for_p9ck") or [])
        and "remote execution" in list(scope.get("out_of_scope_for_p9ck") or [])
        and len(scope.get("rollback_conditions") or []) >= 8
    )


def p9ck_required_proofs_ready(proofs: dict[str, Any]) -> bool:
    proof_rows = list(proofs.get("proofs") or [])
    proof_by_id = {str(item.get("proof_id")): dict(item) for item in proof_rows}
    return (
        proofs.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9ck_required_fresh_proofs.v1"
        and proofs.get("scope_definition_only") is True
        and proofs.get("fresh_proofs_required_before_any_future_order_submission")
        is True
        and proofs.get("p9ck_satisfies_fresh_proofs") is False
        and proofs.get("fresh_remote_proof_collection_performed_in_p9ck") is False
        and set(proof_by_id) == set(EXPECTED_PROOFS)
        and all(
            int(proof_by_id[key].get("max_age_seconds") or 0) == max_age
            and proof_by_id[key].get("required_before")
            in {"future_live_order_gate_approval", "any_order_submission"}
            and bool(proof_by_id[key].get("acceptance"))
            for key, max_age in EXPECTED_PROOFS.items()
        )
    )


def p9ck_non_authorization_ready(matrix: dict[str, Any]) -> bool:
    authorizations = dict(matrix.get("authorizations") or {})
    return (
        matrix.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9ck_non_authorization.v1"
        and authorizations.get("define_post_account_blocker_live_order_readiness_scope")
        is True
        and authorizations.get("prepare_future_p9cl_review_package") is True
        and authorizations.get("fresh_remote_proof_collection") is False
        and authorizations.get("fresh_remote_account_read") is False
        and authorizations.get("fresh_order_book_read") is False
        and authorizations.get("exchange_filter_read") is False
        and authorizations.get("order_test_endpoint") is False
        and authorizations.get("remote_execution") is False
        and authorizations.get("remote_sync") is False
        and authorizations.get("live_order_gate_approval") is False
        and authorizations.get("actual_candidate_executor_target_path_entry") is False
        and authorizations.get("candidate_execution") is False
        and authorizations.get("live_order_submission") is False
        and authorizations.get("actual_target_plan_replacement") is False
        and authorizations.get("actual_executor_input_mutation") is False
        and authorizations.get("timer_path_load") is False
        and authorizations.get("production_timer_service_load") is False
        and authorizations.get("supervisor_invocation") is False
        and authorizations.get("stage_governance_change") is False
    )


def p9ck_control_ready(control: dict[str, Any]) -> bool:
    return (
        control.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9ck_control_boundary.v1"
        and control.get("scope")
        == "post_account_blocker_live_order_readiness_scope_definition_only"
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
        and control.get("candidate_entered_actual_executor_target_plan_path") is False
        and control.get("live_order_submission_performed") is False
        and control.get("target_plan_replaced") is False
        and control.get("executor_input_changed") is False
        and int_zero(control, "orders_submitted")
        and int_zero(control, "orders_canceled")
        and int_zero(control, "fill_count")
        and int_zero(control, "trade_count")
    )


def build_canary_order_terms(scope: dict[str, Any]) -> dict[str, Any]:
    canary = dict(scope.get("canary_terms") or {})
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cl_canary_order_terms.v1",
        "package_only": True,
        "symbol": canary.get("symbol"),
        "side": canary.get("side"),
        "risk_ceiling_usdt": canary.get("risk_ceiling_usdt"),
        "max_notional_usdt": canary.get("max_notional_usdt"),
        "max_orders_per_cycle": canary.get("max_orders_per_cycle"),
        "max_symbols_per_cycle": canary.get("max_symbols_per_cycle"),
        "order_type": canary.get("order_type"),
        "time_in_force": canary.get("time_in_force"),
        "market_orders_allowed": False,
        "post_only_required": True,
        "maker_only_required": True,
        "limit_order_must_not_cross_spread": True,
        "candidate_delta_source": "distance_to_high_60_contribution_only",
        "would_submit_order": False,
    }


def build_fresh_proof_collection_plan(proofs: dict[str, Any]) -> dict[str, Any]:
    plan_rows = []
    for item in list(proofs.get("proofs") or []):
        plan_rows.append(
            {
                "proof_id": str(item.get("proof_id")),
                "required": True,
                "max_age_seconds": int(item.get("max_age_seconds") or 0),
                "required_before": item.get("required_before"),
                "acceptance": list(item.get("acceptance") or []),
                "collection_status_in_p9cl": "not_collected",
                "future_collection_requires_separate_owner_gate": True,
            }
        )
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cl_fresh_proof_collection_plan.v1",
        "package_only": True,
        "fresh_proofs_collected_in_p9cl": False,
        "remote_account_read_performed": False,
        "order_book_read_performed": False,
        "exchange_filter_read_performed": False,
        "future_collection_requires_separate_owner_gate": True,
        "proofs": plan_rows,
    }


def build_approval_checklist(scope: dict[str, Any]) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cl_approval_checklist.v1",
        "package_only": True,
        "approval_items": [
            {
                "item": "account_blocker_cleared_by_p9cj",
                "required_for_live_order_gate": True,
                "satisfied_in_p9cl": True,
            },
            {
                "item": "all_required_fresh_proofs_present_and_unexpired",
                "required_for_live_order_gate": True,
                "satisfied_in_p9cl": False,
            },
            {
                "item": "fresh_v2_account_canTrade_true",
                "required_for_live_order_gate": True,
                "satisfied_in_p9cl": False,
            },
            {
                "item": "same_risk_candidate_target_plan_hash_bound",
                "required_for_live_order_gate": True,
                "satisfied_in_p9cl": False,
            },
            {
                "item": "distance_to_high_60_only_delta",
                "required_for_live_order_gate": True,
                "satisfied_in_p9cl": False,
            },
            {
                "item": "no_order_replacement_dry_run_passed",
                "required_for_live_order_gate": True,
                "satisfied_in_p9cl": False,
            },
            {
                "item": "post_only_limit_price_does_not_cross_spread",
                "required_for_live_order_gate": True,
                "satisfied_in_p9cl": False,
            },
            {
                "item": "kill_switch_and_rollback_readback_available",
                "required_for_live_order_gate": True,
                "satisfied_in_p9cl": False,
            },
            {
                "item": "final_owner_live_order_gate_approval",
                "required_for_live_order_gate": True,
                "satisfied_in_p9cl": False,
            },
        ],
        "rollback_conditions": list(scope.get("rollback_conditions") or []),
    }


def build_review_package(
    *,
    run_id: str,
    p9ck_summary_path: Path,
    p9ck_summary: dict[str, Any],
    scope: dict[str, Any],
    fresh_plan: dict[str, Any],
    canary_terms: dict[str, Any],
    approval_checklist: dict[str, Any],
) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cl_review_package.v1",
        "run_id": run_id,
        "package_only": True,
        "source_p9ck_summary": evidence_file(p9ck_summary_path),
        "package_decision": "prepared_for_future_review_only",
        "account_blocker_status": "cleared_by_p9cj_retained_review",
        "future_gate_name": "post_account_blocker_live_order_readiness_review",
        "canary_order_terms": canary_terms,
        "fresh_proof_collection_plan": fresh_plan,
        "approval_checklist": approval_checklist,
        "future_gate_may_discuss": list(scope.get("future_gate_may_discuss") or []),
        "future_gate_may_not_skip": list(scope.get("future_gate_may_not_skip") or []),
        "target_runner": dict(scope.get("target_runner") or {}),
        "required_fresh_proof_count": len(fresh_plan["proofs"]),
        "fresh_proofs_collected_in_p9cl": False,
        "fresh_proofs_satisfied_by_p9cl": False,
        "fresh_remote_proof_collection_approved_in_p9cl": False,
        "live_order_gate_approved": False,
        "live_order_submission_authorized": False,
        "candidate_execution_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
        "source_p9ck_account_blocker_cleared": p9ck_summary.get(
            "account_blocker_cleared_before_p9ck"
        ),
    }


def build_phase9cl_post_account_blocker_live_order_readiness_review_package(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    now = now_fn()
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9cl" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    p9ck_summary_path = latest_p9ck_summary(args)
    p9ck = load_optional(p9ck_summary_path)
    scope_path = source_output_path(p9ck, "post_account_blocker_live_order_readiness_scope")
    proofs_path = source_output_path(p9ck, "required_fresh_proofs")
    matrix_path = source_output_path(p9ck, "non_authorization")
    control_path = source_output_path(p9ck, "control_boundary_readback")
    scope = load_optional(scope_path)
    proofs = load_optional(proofs_path)
    p9ck_matrix = load_optional(matrix_path)
    p9ck_control = load_optional(control_path)
    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)

    owner_decision_ok = str(args.owner_decision) == APPROVE_P9CL_DECISION
    checks = {
        "owner_decision_p9cl_package_only_recorded": owner_decision_ok,
        "project_profile_exists": bool(project_profile),
        "current_stage_is_stage3": str(project_profile.get("current_stage") or "")
        == "stage_3_human_approved_execution",
        "p9ck_summary_exists": bool(p9ck),
        "p9ck_summary_ready_for_p9cl_package": p9ck_summary_ready(p9ck),
        "p9ck_scope_ready": p9ck_scope_ready(scope),
        "p9ck_required_fresh_proofs_ready": p9ck_required_proofs_ready(proofs),
        "p9ck_non_authorization_ready": p9ck_non_authorization_ready(p9ck_matrix),
        "p9ck_control_boundary_ready": p9ck_control_ready(p9ck_control),
    }
    blockers = [key for key, value in checks.items() if not value]
    ready = not blockers

    canary_terms = build_canary_order_terms(scope)
    fresh_plan = build_fresh_proof_collection_plan(proofs)
    approval_checklist = build_approval_checklist(scope)
    review_package = build_review_package(
        run_id=run_id,
        p9ck_summary_path=p9ck_summary_path,
        p9ck_summary=p9ck,
        scope=scope,
        fresh_plan=fresh_plan,
        canary_terms=canary_terms,
        approval_checklist=approval_checklist,
    )
    owner_record = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cl_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "prepare_post_account_blocker_live_order_readiness_review_package_only_no_order_no_remote_no_execution",
        "recorded_at_utc": iso_z(now),
        "review_package_preparation_approved": owner_decision_ok,
        "fresh_remote_proof_collection_approved": False,
        "remote_execution_approved": False,
        "live_order_gate_approved": False,
        "candidate_execution_approved": False,
        "target_plan_replacement_approved": False,
        "executor_input_mutation_approved": False,
        "live_order_submission_approved": False,
    }
    non_authorization = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cl_non_authorization.v1",
        "run_id": run_id,
        "authorizations": {
            "prepare_post_account_blocker_live_order_readiness_review_package": ready,
            "review_p9cl_package": ready,
            "fresh_remote_proof_collection": False,
            "fresh_remote_account_read": False,
            "fresh_order_book_read": False,
            "exchange_filter_read": False,
            "order_test_endpoint": False,
            "remote_execution": False,
            "remote_sync": False,
            "live_order_gate_approval": False,
            "actual_candidate_executor_target_path_entry": False,
            "candidate_execution": False,
            "live_order_submission": False,
            "actual_target_plan_replacement": False,
            "actual_executor_input_mutation": False,
            "live_config_mutation": False,
            "operator_state_mutation": False,
            "timer_or_service_mutation": False,
            "timer_path_load": False,
            "production_timer_service_load": False,
            "supervisor_invocation": False,
            "stage_governance_change": False,
        },
    }
    control = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cl_control_boundary.v1",
        "run_id": run_id,
        "scope": "post_account_blocker_live_order_readiness_review_package_preparation_only",
        "ssh_invoked": False,
        "remote_network_connection_performed": False,
        "fresh_remote_account_read_performed": False,
        "fresh_order_book_read_performed": False,
        "exchange_filter_read_performed": False,
        "order_test_endpoint_called": False,
        "fresh_proofs_collected": False,
        "entered_timer_path": False,
        "ran_supervisor": False,
        "remote_sync_performed": False,
        "remote_execution_performed": False,
        "candidate_execution_performed": False,
        "candidate_entered_actual_executor_target_plan_path": False,
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

    owner_path = root / "owner_decision_record.json"
    package_path = proof_root / "post_account_blocker_live_order_readiness_review_package.json"
    canary_path = proof_root / "canary_order_terms.json"
    fresh_plan_path = proof_root / "fresh_proof_collection_plan.json"
    approval_path = proof_root / "approval_checklist.json"
    non_auth_path = proof_root / "non_authorization.json"
    control_path_out = proof_root / "control_boundary_readback.json"
    summary_path = root / "summary.json"
    report_path = root / "p9cl_post_account_blocker_live_order_readiness_review_package.md"

    output_files = {
        "summary": str(summary_path),
        "owner_decision_record": str(owner_path),
        "post_account_blocker_live_order_readiness_review_package": str(package_path),
        "canary_order_terms": str(canary_path),
        "fresh_proof_collection_plan": str(fresh_plan_path),
        "approval_checklist": str(approval_path),
        "non_authorization": str(non_auth_path),
        "control_boundary_readback": str(control_path_out),
        "report": str(report_path),
    }
    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "status": "ready" if ready else "blocked",
        "blockers": blockers,
        "p9cl_post_account_blocker_live_order_readiness_review_package_prepared": ready,
        "p9ck_sufficient_for_p9cl_review_package": p9ck_summary_ready(p9ck),
        "account_blocker_cleared_before_p9cl": p9ck.get(
            "account_blocker_cleared_before_p9ck"
        )
        is True,
        "review_package_prepared_after_account_blocker_clearance": ready,
        "required_fresh_proof_count": len(fresh_plan["proofs"]),
        "fresh_proofs_collected_in_p9cl": False,
        "fresh_proofs_satisfied_by_p9cl": False,
        "fresh_remote_proof_collection_approved_in_p9cl": False,
        "eligible_for_future_p9cm_package_review": ready,
        "eligible_for_future_fresh_remote_proof_collection": False,
        "eligible_for_future_live_order_submission": False,
        "eligible_for_future_candidate_execution": False,
        "eligible_for_future_candidate_executor_path_entry": False,
        "fresh_remote_account_read_performed": False,
        "fresh_order_book_read_performed": False,
        "exchange_filter_read_performed": False,
        "order_test_endpoint_called": False,
        "remote_execution_performed": False,
        "remote_sync_performed": False,
        "remote_files_written": 0,
        "live_order_gate_approved": False,
        "live_order_submission_authorized": False,
        "candidate_enter_executor_target_plan_path_authorized": False,
        "candidate_execution_authorized": False,
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
        "allowed_next_gate": P9CM_GATE,
        "allowed_next_gate_scope": P9CM_SCOPE,
        "allowed_next_gate_must_be_separately_requested": True,
        "canary_symbol": CANARY_SYMBOL,
        "canary_side": CANARY_SIDE,
        "risk_ceiling_usdt": DEFAULT_RISK_CEILING_USDT,
        "max_notional_usdt": DEFAULT_MAX_NOTIONAL_USDT,
        "max_orders_per_cycle": DEFAULT_MAX_ORDERS_PER_CYCLE,
        "max_symbols_per_cycle": DEFAULT_MAX_SYMBOLS_PER_CYCLE,
        "order_type": DEFAULT_ORDER_TYPE,
        "time_in_force": DEFAULT_TIME_IN_FORCE,
        "market_orders_allowed": False,
        "source_p9ck_summary_sha256": evidence_file(p9ck_summary_path).get("sha256", ""),
        "source_p9ck_account_blocker_cleared": p9ck.get(
            "account_blocker_cleared_before_p9ck"
        ),
        "source_p9ck_fresh_proofs_satisfied": p9ck.get("fresh_proofs_satisfied_by_p9ck"),
        "source_p9ck_eligible_for_future_fresh_remote_proof_collection": p9ck.get(
            "eligible_for_future_fresh_remote_proof_collection"
        ),
        "source_evidence": {
            "phase9ck_summary": evidence_file(p9ck_summary_path),
            "phase9ck_scope": evidence_file(scope_path),
            "phase9ck_required_fresh_proofs": evidence_file(proofs_path),
            "phase9ck_non_authorization": evidence_file(matrix_path),
            "phase9ck_control_boundary": evidence_file(control_path),
            "project_profile": evidence_file(project_profile_path),
        },
        "checks": checks,
        "output_files": output_files,
    }

    write_json(owner_path, owner_record)
    write_json(package_path, review_package)
    write_json(canary_path, canary_terms)
    write_json(fresh_plan_path, fresh_plan)
    write_json(approval_path, approval_checklist)
    write_json(non_auth_path, non_authorization)
    write_json(control_path_out, control)
    write_json(summary_path, summary)
    report_path.write_text(render_markdown(summary, review_package), encoding="utf-8")
    return summary, 0 if ready else 2


def build_phase9cl(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    return build_phase9cl_post_account_blocker_live_order_readiness_review_package(
        args,
        now_fn=now_fn,
    )


def render_markdown(summary: dict[str, Any], package: dict[str, Any]) -> str:
    canary = dict(package.get("canary_order_terms") or {})
    fresh_plan = dict(package.get("fresh_proof_collection_plan") or {})
    lines = [
        "# hv_balanced DTH60/CoinGlass P9CL Post-Account-Blocker Live-Order Readiness Review Package",
        "",
        f"`Status: {summary['status']}`",
        "",
        "P9CL prepares the post-account-blocker live-order readiness review package only. It does not collect fresh proofs, approve fresh remote proof collection, approve live orders, execute the candidate, replace target plans, mutate executor input, invoke supervisor/timer/remote paths, or submit orders.",
        "",
        "## Package Boundary",
        "",
        "```text",
        "p9cl_post_account_blocker_live_order_readiness_review_package_prepared = "
        f"{str(bool(summary['p9cl_post_account_blocker_live_order_readiness_review_package_prepared'])).lower()}",
        "account_blocker_cleared_before_p9cl = "
        f"{str(bool(summary['account_blocker_cleared_before_p9cl'])).lower()}",
        "fresh_proofs_collected_in_p9cl = false",
        "fresh_remote_proof_collection_approved_in_p9cl = false",
        "eligible_for_future_live_order_submission = false",
        "live_order_gate_approved = false",
        "live_order_submission_authorized = false",
        "candidate_execution_authorized = false",
        "target_plan_replacement_authorized = false",
        "executor_input_mutation_authorized = false",
        "orders_submitted = 0",
        "fill_count = 0",
        "```",
        "",
        "## Canary Terms For Future Review",
        "",
        "```text",
        f"symbol = {canary.get('symbol')}",
        f"side = {canary.get('side')}",
        f"risk_ceiling_usdt = {canary.get('risk_ceiling_usdt')}",
        f"max_notional_usdt = {canary.get('max_notional_usdt')}",
        f"max_orders_per_cycle = {canary.get('max_orders_per_cycle')}",
        f"max_symbols_per_cycle = {canary.get('max_symbols_per_cycle')}",
        f"order_type = {canary.get('order_type')}",
        f"time_in_force = {canary.get('time_in_force')}",
        "market_orders_allowed = false",
        "would_submit_order = false",
        "```",
        "",
        "## Required Fresh Proofs To Collect Later",
        "",
    ]
    for proof in list(fresh_plan.get("proofs") or []):
        lines.append(
            f"- `{proof['proof_id']}` max_age_seconds={proof['max_age_seconds']} status={proof['collection_status_in_p9cl']}"
        )
    lines.extend(
        [
            "",
            "## Allowed Next Gate",
            "",
            "```text",
            str(summary["allowed_next_gate"]),
            str(summary["allowed_next_gate_scope"]),
            "allowed_next_gate_must_be_separately_requested = true",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_phase9cl(parse_args(argv))
    print(f"status={summary['status']}")
    print(f"summary={summary['output_files']['summary']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
