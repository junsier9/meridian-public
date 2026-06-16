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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cl_post_account_blocker_live_order_readiness_review_package import (  # noqa: E402
    CANARY_SIDE,
    CANARY_SYMBOL,
    DEFAULT_MAX_NOTIONAL_USDT,
    DEFAULT_MAX_ORDERS_PER_CYCLE,
    DEFAULT_MAX_SYMBOLS_PER_CYCLE,
    DEFAULT_ORDER_TYPE,
    DEFAULT_RISK_CEILING_USDT,
    DEFAULT_TIME_IN_FORCE,
    EXPECTED_PROOFS,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cq_define_final_owner_live_order_gate_scope_after_p9co import (  # noqa: E402
    CONTRACT_VERSION as P9CQ_CONTRACT,
    DEFAULT_OUTPUT_PARENT as P9CQ_PARENT,
    P9CR_GATE,
    P9CR_SCOPE,
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
    "hv_balanced_dth60_coinglass_phase9cr_prepare_final_owner_live_order_gate_review_package_after_p9co.v1"
)
APPROVE_P9CR_DECISION = (
    "approve_p9cr_prepare_final_owner_live_order_gate_review_package_after_p9co_only_no_order_no_candidate_no_executor_or_timer_change"
)
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/p9cr_final_owner_live_order_gate_review_package_after_p9co"
)
P9CS_GATE = (
    "P9CS_review_p9cr_final_owner_live_order_gate_review_package_after_p9co_only_if_separately_requested"
)
P9CS_SCOPE = (
    "review_p9cr_final_owner_live_order_gate_review_package_sufficiency_only_no_order_no_candidate_no_executor_or_timer_change"
)


EXPECTED_FINAL_EVIDENCE = {
    **EXPECTED_PROOFS,
    "explicit_final_owner_live_order_decision": 300,
    "pre_order_control_boundary_readback": 60,
    "post_order_observation_and_rollback_plan": 300,
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare the P9CR final owner live-order gate review package after "
            "retained P9CO/P9CP/P9CQ proof. P9CR is package-only: it does not "
            "SSH, read Binance, collect fresh proofs, call order-test endpoints, "
            "run supervisor or timer paths, execute the candidate, mutate "
            "executor input or target plans, remote sync, cancel orders, or "
            "submit orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9cq-summary", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9CR_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default=(
            "user_chat:p9cr_prepare_final_owner_live_order_gate_review_package_after_p9co_only_if_separately_requested"
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


def latest_p9cq_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9cq_summary).strip():
        return resolve_path(args.phase9cq_summary)
    return latest_match(P9CQ_PARENT, "*/summary.json")


def source_output_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("output_files") or {}).get(key) or "")
    return resolve_path(text) if text.strip() else Path("")


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def p9cq_summary_ready(summary: dict[str, Any]) -> bool:
    checks = dict(summary.get("checks") or {})
    return (
        summary.get("contract_version") == P9CQ_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9cq_final_owner_live_order_gate_scope_defined") is True
        and summary.get("p9cp_sufficient_for_p9cq_scope_definition") is True
        and summary.get("p9co_retained_read_only_fresh_proofs_ready") is True
        and summary.get("account_blocker_cleared_by_p9co") is True
        and summary.get("final_owner_live_order_gate_scope_defined_after_p9co")
        is True
        and int(summary.get("required_final_gate_evidence_count") or 0)
        == len(EXPECTED_FINAL_EVIDENCE)
        and summary.get("final_owner_live_order_gate_approval_collected") is False
        and summary.get("final_owner_live_order_gate_approval_required_next") is True
        and summary.get("p9cq_satisfies_final_owner_live_order_gate") is False
        and summary.get("eligible_for_future_p9cr_review_package") is True
        and summary.get("eligible_for_future_live_order_submission") is False
        and summary.get("eligible_for_future_candidate_execution") is False
        and summary.get("eligible_for_future_candidate_executor_path_entry") is False
        and summary.get("fresh_remote_proof_collection_performed_in_p9cq") is False
        and summary.get("fresh_remote_account_read_performed") is False
        and summary.get("fresh_order_book_read_performed") is False
        and summary.get("exchange_filter_read_performed") is False
        and summary.get("order_test_endpoint_called") is False
        and summary.get("remote_execution_performed") is False
        and summary.get("remote_sync_performed") is False
        and int_zero(summary, "remote_files_written")
        and summary.get("live_order_gate_approved") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("candidate_enter_executor_target_plan_path_authorized")
        is False
        and summary.get("candidate_execution_authorized") is False
        and summary.get("target_plan_replacement_authorized") is False
        and summary.get("executor_input_mutation_authorized") is False
        and summary.get("supervisor_invocation_authorized") is False
        and summary.get("timer_path_load_authorized") is False
        and int_zero(summary, "orders_submitted")
        and int_zero(summary, "orders_canceled")
        and int_zero(summary, "fill_count")
        and int_zero(summary, "trade_count")
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
        and bool(summary.get("source_p9co_baseline_target_plan_sha256"))
        and bool(summary.get("source_p9co_candidate_target_plan_sha256"))
        and summary.get("source_p9co_baseline_target_plan_sha256")
        != summary.get("source_p9co_candidate_target_plan_sha256")
        and summary.get("source_p9co_can_trade_pre") is True
        and summary.get("source_p9co_can_trade_post") is True
        and summary.get("source_p9co_open_order_count_pre") == 0
        and summary.get("source_p9co_open_order_count_post") == 0
        and summary.get("source_p9co_order_cancel_fill_trade_delta_zero") is True
        and summary.get("source_p9co_remote_control_boundary_unchanged") is True
        and summary.get("source_p9co_only_distance_to_high_60_contribution_changed")
        is True
        and summary.get("allowed_next_gate") == P9CR_GATE
        and summary.get("allowed_next_gate_scope") == P9CR_SCOPE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
        and bool(checks)
        and all(value is True for value in checks.values())
    )


def p9cq_scope_ready(scope: dict[str, Any]) -> bool:
    canary = dict(scope.get("exact_canary_terms") or {})
    candidate_path = dict(scope.get("candidate_path_terms") or {})
    return (
        scope.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cq_final_owner_live_order_gate_scope.v1"
        and scope.get("scope_definition_only") is True
        and scope.get("scope_basis")
        == "retained_p9cp_review_of_p9co_read_only_fresh_remote_proofs"
        and scope.get("final_owner_gate_name") == "final_owner_live_order_gate_after_p9co"
        and "whether to approve candidate entry into the executor target-plan path"
        in list(scope.get("final_owner_gate_may_discuss") or [])
        and "whether to submit one maker-only post-only canary order under exact risk terms"
        in list(scope.get("final_owner_gate_may_discuss") or [])
        and "PIT-safe account permission decision from /fapi/v2/account.canTrade"
        in list(scope.get("final_owner_gate_may_not_skip") or [])
        and "explicit final owner approval naming candidate path, order terms, and rollback terms"
        in list(scope.get("final_owner_gate_may_not_skip") or [])
        and canary.get("symbol") == CANARY_SYMBOL
        and canary.get("side") == CANARY_SIDE
        and float(canary.get("risk_ceiling_usdt") or 0) == DEFAULT_RISK_CEILING_USDT
        and float(canary.get("max_notional_usdt") or 0) == DEFAULT_MAX_NOTIONAL_USDT
        and int(canary.get("max_orders_per_cycle") or 0) == DEFAULT_MAX_ORDERS_PER_CYCLE
        and int(canary.get("max_symbols_per_cycle") or 0)
        == DEFAULT_MAX_SYMBOLS_PER_CYCLE
        and canary.get("order_type") == DEFAULT_ORDER_TYPE
        and canary.get("time_in_force") == DEFAULT_TIME_IN_FORCE
        and canary.get("market_orders_allowed") is False
        and canary.get("post_only_required") is True
        and canary.get("maker_only_required") is True
        and canary.get("candidate_delta_source") == "distance_to_high_60_contribution_only"
        and candidate_path.get("candidate_may_enter_executor_target_plan_path_only_in_final_gate")
        is True
        and candidate_path.get("candidate_execution_may_be_authorized_only_in_final_gate")
        is True
        and candidate_path.get("target_plan_replacement_may_be_authorized_only_in_final_gate")
        is True
        and candidate_path.get("executor_input_mutation_may_be_authorized_only_in_final_gate")
        is True
        and candidate_path.get("must_bind_candidate_target_plan_hash") is True
        and candidate_path.get("must_preserve_same_timestamp_same_risk_inputs") is True
        and candidate_path.get("only_allowed_strategy_delta")
        == "distance_to_high_60_contribution"
        and bool(scope.get("source_p9co_baseline_target_plan_sha256"))
        and bool(scope.get("source_p9co_candidate_target_plan_sha256"))
        and scope.get("source_p9co_baseline_target_plan_sha256")
        != scope.get("source_p9co_candidate_target_plan_sha256")
        and "fresh remote proof collection" in list(scope.get("out_of_scope_for_p9cq") or [])
        and "order-test endpoint calls" in list(scope.get("out_of_scope_for_p9cq") or [])
        and "actual order placement" in list(scope.get("out_of_scope_for_p9cq") or [])
        and "candidate execution" in list(scope.get("out_of_scope_for_p9cq") or [])
        and "actual target-plan replacement" in list(scope.get("out_of_scope_for_p9cq") or [])
        and "executor-input mutation" in list(scope.get("out_of_scope_for_p9cq") or [])
        and "timer or service mutation" in list(scope.get("out_of_scope_for_p9cq") or [])
        and "supervisor invocation" in list(scope.get("out_of_scope_for_p9cq") or [])
        and "remote execution" in list(scope.get("out_of_scope_for_p9cq") or [])
        and len(scope.get("rollback_conditions") or []) >= 8
    )


def p9cq_required_evidence_ready(evidence: dict[str, Any]) -> bool:
    rows = list(evidence.get("evidence") or [])
    by_id = {str(row.get("evidence_id")): dict(row) for row in rows}
    return (
        evidence.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cq_required_final_gate_evidence.v1"
        and evidence.get("scope_definition_only") is True
        and evidence.get("final_owner_gate_required_before_any_order_submission") is True
        and evidence.get("p9cq_satisfies_final_owner_live_order_gate") is False
        and evidence.get("fresh_remote_proof_collection_performed_in_p9cq") is False
        and set(by_id) == set(EXPECTED_FINAL_EVIDENCE)
        and all(
            int(by_id[key].get("max_age_seconds") or 0) == max_age
            and by_id[key].get("must_be_retained") is True
            for key, max_age in EXPECTED_FINAL_EVIDENCE.items()
        )
    )


def p9cq_non_authorization_ready(matrix: dict[str, Any]) -> bool:
    authorizations = dict(matrix.get("authorizations") or {})
    return (
        matrix.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cq_non_authorization.v1"
        and authorizations.get("define_final_owner_live_order_gate_scope") is True
        and authorizations.get("prepare_future_p9cr_review_package") is True
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


def p9cq_control_ready(control: dict[str, Any]) -> bool:
    return (
        control.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cq_control_boundary.v1"
        and control.get("scope") == "final_owner_live_order_gate_scope_definition_only"
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
        and control.get("live_config_changed") is False
        and control.get("operator_state_changed") is False
        and control.get("timer_state_changed") is False
        and int_zero(control, "orders_submitted")
        and int_zero(control, "orders_canceled")
        and int_zero(control, "fill_count")
        and int_zero(control, "trade_count")
    )


def build_canary_order_terms(scope: dict[str, Any]) -> dict[str, Any]:
    canary = dict(scope.get("exact_canary_terms") or {})
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cr_canary_order_terms.v1",
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


def build_final_gate_evidence_plan(evidence: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for item in list(evidence.get("evidence") or []):
        evidence_id = str(item.get("evidence_id"))
        rows.append(
            {
                "evidence_id": evidence_id,
                "required": True,
                "max_age_seconds": int(item.get("max_age_seconds") or 0),
                "required_before": item.get("required_before"),
                "must_be_retained": item.get("must_be_retained") is True,
                "status_in_p9cr": "packaged_only_not_final_approved",
                "collection_status_in_p9cr": "not_collected",
                "freshness_status_in_p9cr": "not_evaluated_for_final_gate",
            }
        )
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cr_final_gate_evidence_plan.v1",
        "package_only": True,
        "final_owner_gate_required_before_any_order_submission": True,
        "p9cr_satisfies_final_owner_live_order_gate": False,
        "fresh_remote_proof_collection_performed_in_p9cr": False,
        "evidence": rows,
    }


def build_approval_checklist(scope: dict[str, Any]) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cr_approval_checklist.v1",
        "package_only": True,
        "approval_items": [
            {
                "item": "p9co_account_blocker_cleared_and_canTrade_v2_true",
                "required_for_final_owner_live_order_gate": True,
                "satisfied_in_p9cr": True,
                "note": "retained P9CO/P9CP reference only; final gate still needs freshness review",
            },
            {
                "item": "all_required_final_gate_evidence_present_and_unexpired",
                "required_for_final_owner_live_order_gate": True,
                "satisfied_in_p9cr": False,
            },
            {
                "item": "candidate_target_plan_hash_bound_to_executor_input",
                "required_for_final_owner_live_order_gate": True,
                "satisfied_in_p9cr": False,
            },
            {
                "item": "candidate_delta_limited_to_distance_to_high_60",
                "required_for_final_owner_live_order_gate": True,
                "satisfied_in_p9cr": False,
            },
            {
                "item": "post_only_limit_price_does_not_cross_spread",
                "required_for_final_owner_live_order_gate": True,
                "satisfied_in_p9cr": False,
            },
            {
                "item": "kill_switch_and_rollback_readback_available",
                "required_for_final_owner_live_order_gate": True,
                "satisfied_in_p9cr": False,
            },
            {
                "item": "explicit_final_owner_live_order_decision",
                "required_for_final_owner_live_order_gate": True,
                "satisfied_in_p9cr": False,
            },
            {
                "item": "post_order_observation_and_rollback_plan_bound",
                "required_for_final_owner_live_order_gate": True,
                "satisfied_in_p9cr": False,
            },
        ],
        "rollback_conditions": list(scope.get("rollback_conditions") or []),
    }


def build_review_package(
    *,
    run_id: str,
    p9cq_summary_path: Path,
    p9cq_summary: dict[str, Any],
    scope: dict[str, Any],
    canary_terms: dict[str, Any],
    evidence_plan: dict[str, Any],
    approval_checklist: dict[str, Any],
) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cr_review_package.v1",
        "run_id": run_id,
        "package_only": True,
        "source_p9cq_summary": evidence_file(p9cq_summary_path),
        "package_decision": "prepared_for_future_review_only",
        "future_gate_name": "final_owner_live_order_gate_after_p9co",
        "canary_order_terms": canary_terms,
        "candidate_path_terms": dict(scope.get("candidate_path_terms") or {}),
        "final_gate_evidence_plan": evidence_plan,
        "approval_checklist": approval_checklist,
        "future_gate_may_discuss": list(scope.get("final_owner_gate_may_discuss") or []),
        "future_gate_may_not_skip": list(scope.get("final_owner_gate_may_not_skip") or []),
        "baseline_target_plan_sha256": p9cq_summary.get(
            "source_p9co_baseline_target_plan_sha256"
        ),
        "candidate_target_plan_sha256": p9cq_summary.get(
            "source_p9co_candidate_target_plan_sha256"
        ),
        "only_distance_to_high_60_contribution_changed": p9cq_summary.get(
            "source_p9co_only_distance_to_high_60_contribution_changed"
        ),
        "p9cr_satisfies_final_owner_live_order_gate": False,
        "final_owner_live_order_gate_approved": False,
        "live_order_submission_authorized": False,
        "candidate_enter_executor_target_plan_path_authorized": False,
        "candidate_execution_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
    }


def build_phase9cr(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    now = now_fn()
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9cr" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    p9cq_summary_path = latest_p9cq_summary(args)
    p9cq = load_optional(p9cq_summary_path)
    scope_path = source_output_path(p9cq, "final_owner_live_order_gate_scope")
    evidence_path = source_output_path(p9cq, "required_final_gate_evidence")
    matrix_path = source_output_path(p9cq, "non_authorization")
    control_path = source_output_path(p9cq, "control_boundary_readback")
    scope = load_optional(scope_path)
    evidence = load_optional(evidence_path)
    p9cq_matrix = load_optional(matrix_path)
    p9cq_control = load_optional(control_path)
    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)

    owner_decision_ok = str(args.owner_decision) == APPROVE_P9CR_DECISION
    checks = {
        "owner_decision_p9cr_package_only_recorded": owner_decision_ok,
        "project_profile_exists": bool(project_profile),
        "current_stage_is_stage3": str(project_profile.get("current_stage") or "")
        == "stage_3_human_approved_execution",
        "p9cq_summary_exists": bool(p9cq),
        "p9cq_summary_ready_for_p9cr_package": p9cq_summary_ready(p9cq),
        "p9cq_scope_ready": p9cq_scope_ready(scope),
        "p9cq_required_final_gate_evidence_ready": p9cq_required_evidence_ready(
            evidence
        ),
        "p9cq_non_authorization_ready": p9cq_non_authorization_ready(p9cq_matrix),
        "p9cq_control_boundary_ready": p9cq_control_ready(p9cq_control),
    }
    blockers = [key for key, value in checks.items() if not value]
    ready = not blockers

    canary_terms = build_canary_order_terms(scope)
    evidence_plan = build_final_gate_evidence_plan(evidence)
    approval_checklist = build_approval_checklist(scope)
    review_package = build_review_package(
        run_id=run_id,
        p9cq_summary_path=p9cq_summary_path,
        p9cq_summary=p9cq,
        scope=scope,
        canary_terms=canary_terms,
        evidence_plan=evidence_plan,
        approval_checklist=approval_checklist,
    )
    owner_record = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cr_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "prepare_final_owner_live_order_gate_review_package_after_p9co_only_no_order_no_candidate_no_executor_or_timer_change",
        "recorded_at_utc": iso_z(now),
        "review_package_preparation_approved": owner_decision_ok,
        "fresh_remote_proof_collection_approved": False,
        "remote_execution_approved": False,
        "final_owner_live_order_gate_approved": False,
        "candidate_executor_path_entry_approved": False,
        "candidate_execution_approved": False,
        "target_plan_replacement_approved": False,
        "executor_input_mutation_approved": False,
        "live_order_submission_approved": False,
    }
    non_authorization = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cr_non_authorization.v1",
        "run_id": run_id,
        "authorizations": {
            "prepare_final_owner_live_order_gate_review_package": ready,
            "review_p9cr_package": ready,
            "fresh_remote_proof_collection": False,
            "fresh_remote_account_read": False,
            "fresh_order_book_read": False,
            "exchange_filter_read": False,
            "order_test_endpoint": False,
            "remote_execution": False,
            "remote_sync": False,
            "final_owner_live_order_gate_approval": False,
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
        "contract_version": "hv_balanced_dth60_coinglass_phase9cr_control_boundary.v1",
        "run_id": run_id,
        "scope": "final_owner_live_order_gate_review_package_preparation_only",
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
    package_path = proof_root / "final_owner_live_order_gate_review_package.json"
    canary_path = proof_root / "canary_order_terms.json"
    evidence_plan_path = proof_root / "final_gate_evidence_plan.json"
    approval_path = proof_root / "approval_checklist.json"
    non_auth_path = proof_root / "non_authorization.json"
    control_path_out = proof_root / "control_boundary_readback.json"
    summary_path = root / "summary.json"
    report_path = root / "p9cr_final_owner_live_order_gate_review_package.md"

    output_files = {
        "summary": str(summary_path),
        "owner_decision_record": str(owner_path),
        "final_owner_live_order_gate_review_package": str(package_path),
        "canary_order_terms": str(canary_path),
        "final_gate_evidence_plan": str(evidence_plan_path),
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
        "p9cr_final_owner_live_order_gate_review_package_prepared": ready,
        "p9cq_sufficient_for_p9cr_review_package": p9cq_summary_ready(p9cq),
        "review_package_prepared_after_p9co": ready,
        "required_final_gate_evidence_count": len(evidence_plan["evidence"]),
        "final_gate_evidence_collected_in_p9cr": False,
        "fresh_proofs_collected_in_p9cr": False,
        "fresh_remote_proof_collection_approved_in_p9cr": False,
        "final_owner_live_order_gate_approval_collected": False,
        "p9cr_satisfies_final_owner_live_order_gate": False,
        "eligible_for_future_p9cs_package_review": ready,
        "eligible_for_future_live_order_submission": False,
        "eligible_for_future_candidate_execution": False,
        "eligible_for_future_candidate_executor_path_entry": False,
        "fresh_remote_proof_collection_performed_in_p9cr": False,
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
        "allowed_next_gate": P9CS_GATE,
        "allowed_next_gate_scope": P9CS_SCOPE,
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
        "source_p9cq_summary_sha256": evidence_file(p9cq_summary_path).get("sha256", ""),
        "source_p9cq_scope_sha256": evidence_file(scope_path).get("sha256", ""),
        "source_p9cq_required_final_gate_evidence_sha256": evidence_file(
            evidence_path
        ).get("sha256", ""),
        "source_p9cq_non_authorization_sha256": evidence_file(matrix_path).get(
            "sha256", ""
        ),
        "source_p9cq_control_boundary_sha256": evidence_file(control_path).get(
            "sha256", ""
        ),
        "source_p9co_baseline_target_plan_sha256": p9cq.get(
            "source_p9co_baseline_target_plan_sha256"
        ),
        "source_p9co_candidate_target_plan_sha256": p9cq.get(
            "source_p9co_candidate_target_plan_sha256"
        ),
        "source_p9co_only_distance_to_high_60_contribution_changed": p9cq.get(
            "source_p9co_only_distance_to_high_60_contribution_changed"
        ),
        "source_p9co_can_trade_pre": p9cq.get("source_p9co_can_trade_pre"),
        "source_p9co_can_trade_post": p9cq.get("source_p9co_can_trade_post"),
        "source_p9co_open_order_count_pre": p9cq.get("source_p9co_open_order_count_pre"),
        "source_p9co_open_order_count_post": p9cq.get(
            "source_p9co_open_order_count_post"
        ),
        "source_p9co_order_cancel_fill_trade_delta_zero": p9cq.get(
            "source_p9co_order_cancel_fill_trade_delta_zero"
        ),
        "source_p9co_remote_control_boundary_unchanged": p9cq.get(
            "source_p9co_remote_control_boundary_unchanged"
        ),
        "source_evidence": {
            "phase9cq_summary": evidence_file(p9cq_summary_path),
            "phase9cq_final_owner_live_order_gate_scope": evidence_file(scope_path),
            "phase9cq_required_final_gate_evidence": evidence_file(evidence_path),
            "phase9cq_non_authorization": evidence_file(matrix_path),
            "phase9cq_control_boundary": evidence_file(control_path),
            "project_profile": evidence_file(project_profile_path),
        },
        "checks": checks,
        "output_files": output_files,
    }

    write_json(owner_path, owner_record)
    write_json(package_path, review_package)
    write_json(canary_path, canary_terms)
    write_json(evidence_plan_path, evidence_plan)
    write_json(approval_path, approval_checklist)
    write_json(non_auth_path, non_authorization)
    write_json(control_path_out, control)
    write_json(summary_path, summary)
    report_path.write_text(render_markdown(summary, review_package), encoding="utf-8")
    return summary, 0 if ready else 2


def render_markdown(summary: dict[str, Any], package: dict[str, Any]) -> str:
    canary = dict(package.get("canary_order_terms") or {})
    evidence_plan = dict(package.get("final_gate_evidence_plan") or {})
    lines = [
        "# hv_balanced DTH60/CoinGlass P9CR Final Owner Live-Order Gate Review Package",
        "",
        f"`Status: {summary['status']}`",
        "",
        "P9CR prepares the final owner live-order gate review package only. It does not collect fresh proofs, approve live orders, execute the candidate, replace target plans, mutate executor input, invoke supervisor/timer/remote paths, or submit orders.",
        "",
        "## Package Boundary",
        "",
        "```text",
        "p9cr_final_owner_live_order_gate_review_package_prepared = "
        f"{str(bool(summary['p9cr_final_owner_live_order_gate_review_package_prepared'])).lower()}",
        "p9cr_satisfies_final_owner_live_order_gate = false",
        "final_owner_live_order_gate_approval_collected = false",
        "fresh_proofs_collected_in_p9cr = false",
        "eligible_for_future_live_order_submission = false",
        "live_order_gate_approved = false",
        "live_order_submission_authorized = false",
        "candidate_enter_executor_target_plan_path_authorized = false",
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
        "## Required Final-Gate Evidence To Review Later",
        "",
    ]
    for row in list(evidence_plan.get("evidence") or []):
        lines.append(
            f"- `{row['evidence_id']}` max_age_seconds={row['max_age_seconds']} status={row['status_in_p9cr']}"
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
    summary, exit_code = build_phase9cr(parse_args(argv))
    print(
        "p9cr_final_owner_live_order_gate_review_package_prepared="
        + str(bool(summary["p9cr_final_owner_live_order_gate_review_package_prepared"])).lower()
    )
    print(f"status={summary['status']}")
    print(f"run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
