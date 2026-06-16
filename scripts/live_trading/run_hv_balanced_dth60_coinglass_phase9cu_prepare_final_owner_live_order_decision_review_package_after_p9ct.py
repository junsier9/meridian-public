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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cr_prepare_final_owner_live_order_gate_review_package_after_p9co import (  # noqa: E402
    CANARY_SIDE,
    CANARY_SYMBOL,
    DEFAULT_MAX_NOTIONAL_USDT,
    DEFAULT_MAX_ORDERS_PER_CYCLE,
    DEFAULT_MAX_SYMBOLS_PER_CYCLE,
    DEFAULT_ORDER_TYPE,
    DEFAULT_RISK_CEILING_USDT,
    DEFAULT_TIME_IN_FORCE,
    EXPECTED_FINAL_EVIDENCE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ct_define_final_owner_live_order_gate_decision_scope_after_p9cs import (  # noqa: E402
    CONTRACT_VERSION as P9CT_CONTRACT,
    DEFAULT_OUTPUT_PARENT as P9CT_PARENT,
    P9CU_GATE,
    P9CU_SCOPE,
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
    "hv_balanced_dth60_coinglass_phase9cu_prepare_final_owner_live_order_decision_review_package_after_p9ct.v1"
)
APPROVE_P9CU_DECISION = (
    "approve_p9cu_prepare_final_owner_live_order_decision_review_package_after_p9ct_only_no_order_no_candidate_no_executor_or_timer_change"
)
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/p9cu_final_owner_live_order_decision_review_package_after_p9ct"
)
P9CV_GATE = (
    "P9CV_review_p9cu_final_owner_live_order_decision_review_package_after_p9ct_only_if_separately_requested"
)
P9CV_SCOPE = (
    "review_p9cu_final_owner_live_order_decision_review_package_after_p9ct_no_order_no_candidate_no_executor_or_timer_change"
)

DECISION_CHECKLIST = [
    ("p9ct_decision_scope_defined", True),
    ("p9ct_required_decision_evidence_packaged", True),
    ("fresh_required_decision_evidence_present_and_unexpired", False),
    ("candidate_target_plan_hash_bound_to_executor_input", False),
    ("candidate_delta_limited_to_distance_to_high_60", False),
    ("post_only_limit_price_does_not_cross_spread", False),
    ("kill_switch_and_rollback_readback_available", False),
    ("explicit_final_owner_live_order_decision", False),
    ("pre_order_control_boundary_readback_available", False),
    ("post_order_observation_and_rollback_plan_bound", False),
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare the P9CU final owner live-order decision review package "
            "after retained P9CT scope. P9CU is package-preparation-only: it "
            "does not SSH, read Binance, collect fresh proofs, call order-test "
            "endpoints, run supervisor/timer paths, execute the candidate, "
            "mutate executor input or target plans, remote sync, cancel orders, "
            "or submit orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9ct-summary", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9CU_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default=(
            "user_chat:p9cu_prepare_final_owner_live_order_decision_review_package_after_p9ct_only_if_separately_requested"
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


def latest_p9ct_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9ct_summary).strip():
        return resolve_path(args.phase9ct_summary)
    return latest_match(P9CT_PARENT, "*/summary.json")


def source_output_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("output_files") or {}).get(key) or "")
    return resolve_path(text) if text.strip() else Path("")


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def p9ct_summary_ready(summary: dict[str, Any]) -> bool:
    checks = dict(summary.get("checks") or {})
    return (
        summary.get("contract_version") == P9CT_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9ct_final_owner_live_order_gate_decision_scope_defined")
        is True
        and summary.get("p9cs_sufficient_for_p9ct_scope_definition") is True
        and summary.get("decision_scope_defined_after_p9cs") is True
        and summary.get("p9cr_package_sufficient_for_p9cs_review") is True
        and summary.get("p9cr_package_sufficient_for_future_p9ct_scope_definition")
        is True
        and int(summary.get("required_final_decision_evidence_count") or 0)
        == len(EXPECTED_FINAL_EVIDENCE)
        and int(summary.get("remaining_evidence_gap_count_from_p9cs") or 0)
        == len(EXPECTED_FINAL_EVIDENCE)
        and int(summary.get("remaining_approval_gap_count_from_p9cs") or 0) == 7
        and summary.get("final_decision_evidence_collected_in_p9ct") is False
        and summary.get("fresh_proofs_collected_in_p9ct") is False
        and summary.get("fresh_remote_proof_collection_approved_in_p9ct") is False
        and summary.get("final_owner_live_order_gate_approval_collected") is False
        and summary.get("p9ct_satisfies_final_owner_live_order_gate") is False
        and summary.get("eligible_for_future_p9cu_package_preparation") is True
        and summary.get("eligible_for_future_live_order_submission") is False
        and summary.get("eligible_for_future_candidate_execution") is False
        and summary.get("eligible_for_future_candidate_executor_path_entry") is False
        and summary.get("fresh_remote_proof_collection_performed_in_p9ct") is False
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
        and summary.get("timer_path_load_authorized") is False
        and summary.get("supervisor_invocation_authorized") is False
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
        and bool(summary.get("baseline_target_plan_sha256"))
        and bool(summary.get("candidate_target_plan_sha256"))
        and summary.get("baseline_target_plan_sha256")
        != summary.get("candidate_target_plan_sha256")
        and summary.get("only_distance_to_high_60_contribution_changed") is True
        and summary.get("allowed_next_gate") == P9CU_GATE
        and summary.get("allowed_next_gate_scope") == P9CU_SCOPE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
        and bool(checks)
        and all(value is True for value in checks.values())
    )


def canary_terms_ready(terms: dict[str, Any]) -> bool:
    return (
        terms.get("symbol") == CANARY_SYMBOL
        and terms.get("side") == CANARY_SIDE
        and float(terms.get("risk_ceiling_usdt") or 0) == DEFAULT_RISK_CEILING_USDT
        and float(terms.get("max_notional_usdt") or 0) == DEFAULT_MAX_NOTIONAL_USDT
        and int(terms.get("max_orders_per_cycle") or 0)
        == DEFAULT_MAX_ORDERS_PER_CYCLE
        and int(terms.get("max_symbols_per_cycle") or 0)
        == DEFAULT_MAX_SYMBOLS_PER_CYCLE
        and terms.get("order_type") == DEFAULT_ORDER_TYPE
        and terms.get("time_in_force") == DEFAULT_TIME_IN_FORCE
        and terms.get("market_orders_allowed") is False
        and terms.get("post_only_required") is True
        and terms.get("maker_only_required") is True
        and terms.get("limit_order_must_not_cross_spread") is True
        and terms.get("candidate_delta_source")
        == "distance_to_high_60_contribution_only"
    )


def candidate_path_terms_ready(terms: dict[str, Any], summary: dict[str, Any]) -> bool:
    return (
        terms.get(
            "candidate_may_enter_executor_target_plan_path_only_in_future_final_decision_gate"
        )
        is True
        and terms.get("candidate_execution_may_be_authorized_only_in_future_final_decision_gate")
        is True
        and terms.get(
            "target_plan_replacement_may_be_authorized_only_in_future_final_decision_gate"
        )
        is True
        and terms.get(
            "executor_input_mutation_may_be_authorized_only_in_future_final_decision_gate"
        )
        is True
        and terms.get("must_bind_candidate_target_plan_hash") is True
        and terms.get("baseline_target_plan_sha256")
        == summary.get("baseline_target_plan_sha256")
        and terms.get("candidate_target_plan_sha256")
        == summary.get("candidate_target_plan_sha256")
        and terms.get("must_preserve_same_timestamp_same_risk_inputs") is True
        and terms.get("only_allowed_strategy_delta")
        == "distance_to_high_60_contribution"
        and terms.get("actual_candidate_executor_path_entry_authorized_in_p9ct")
        is False
        and terms.get("actual_target_plan_replacement_authorized_in_p9ct") is False
        and terms.get("actual_executor_input_mutation_authorized_in_p9ct") is False
    )


def required_decision_evidence_ready(evidence: dict[str, Any]) -> bool:
    rows = [dict(row) for row in list(evidence.get("evidence") or [])]
    by_id = {str(row.get("evidence_id")): row for row in rows}
    return (
        evidence.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9ct_required_final_decision_evidence.v1"
        and evidence.get("scope_definition_only") is True
        and evidence.get("final_owner_gate_required_before_any_order_submission")
        is True
        and evidence.get("final_owner_gate_required_before_candidate_executor_path_entry")
        is True
        and evidence.get("p9ct_satisfies_final_owner_live_order_gate") is False
        and evidence.get("fresh_remote_proof_collection_performed_in_p9ct") is False
        and set(by_id) == set(EXPECTED_FINAL_EVIDENCE)
        and all(
            by_id[key].get("required") is True
            and int(by_id[key].get("max_age_seconds") or 0) == max_age
            and by_id[key].get("must_be_retained") is True
            and by_id[key].get("status_in_p9ct") == "defined_not_collected"
            and by_id[key].get("collection_status_in_p9ct") == "not_collected"
            and by_id[key].get("freshness_status_in_p9ct") == "not_evaluated"
            for key, max_age in EXPECTED_FINAL_EVIDENCE.items()
        )
    )


def decision_scope_ready(scope: dict[str, Any], summary: dict[str, Any]) -> bool:
    return (
        scope.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9ct_final_owner_live_order_gate_decision_scope.v1"
        and scope.get("scope_definition_only") is True
        and scope.get("decision_scope_status") == "defined_for_future_owner_gate_only"
        and scope.get("future_decision_gate_name")
        == "final_owner_live_order_gate_decision_after_p9cs"
        and "whether to approve candidate entry into the executor target-plan path"
        in list(scope.get("final_owner_gate_may_decide") or [])
        and "whether to approve submitting one maker-only post-only canary order under exact risk terms"
        in list(scope.get("final_owner_gate_may_decide") or [])
        and "freshness evaluation for every required final-decision evidence row"
        in list(scope.get("final_owner_gate_may_not_skip") or [])
        and "explicit final owner approval naming candidate path, target-plan hashes, order terms, and rollback terms"
        in list(scope.get("final_owner_gate_may_not_skip") or [])
        and candidate_path_terms_ready(dict(scope.get("candidate_path_terms") or {}), summary)
        and canary_terms_ready(dict(scope.get("exact_canary_terms") or {}))
        and required_decision_evidence_ready(
            dict(scope.get("required_decision_evidence_contract") or {})
        )
        and "actual order placement" in list(scope.get("out_of_scope_for_p9ct") or [])
        and "candidate execution" in list(scope.get("out_of_scope_for_p9ct") or [])
        and "executor-input mutation" in list(scope.get("out_of_scope_for_p9ct") or [])
        and len(scope.get("rollback_conditions") or []) >= 8
        and scope.get("p9ct_satisfies_final_owner_live_order_gate") is False
        and scope.get("final_owner_live_order_gate_approved") is False
        and scope.get("live_order_submission_authorized") is False
        and scope.get("candidate_enter_executor_target_plan_path_authorized") is False
        and scope.get("candidate_execution_authorized") is False
        and scope.get("target_plan_replacement_authorized") is False
        and scope.get("executor_input_mutation_authorized") is False
    )


def p9ct_non_authorization_ready(matrix: dict[str, Any]) -> bool:
    authorizations = dict(matrix.get("authorizations") or {})
    return (
        matrix.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9ct_non_authorization.v1"
        and authorizations.get("define_final_owner_live_order_gate_decision_scope")
        is True
        and authorizations.get("allow_future_p9cu_package_preparation_request")
        is True
        and authorizations.get("prepare_p9cu_package_in_p9ct") is False
        and authorizations.get("fresh_remote_proof_collection") is False
        and authorizations.get("fresh_remote_account_read") is False
        and authorizations.get("fresh_order_book_read") is False
        and authorizations.get("exchange_filter_read") is False
        and authorizations.get("order_test_endpoint") is False
        and authorizations.get("remote_execution") is False
        and authorizations.get("remote_sync") is False
        and authorizations.get("final_owner_live_order_gate_approval") is False
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
        and authorizations.get("stage_governance_change") is False
    )


def p9ct_control_ready(control: dict[str, Any]) -> bool:
    return (
        control.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9ct_control_boundary.v1"
        and control.get("scope") == "final_owner_live_order_gate_decision_scope_definition_only"
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


def build_evidence_package(evidence: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for row in list(evidence.get("evidence") or []):
        item = dict(row)
        rows.append(
            {
                "evidence_id": item.get("evidence_id"),
                "required": True,
                "max_age_seconds": item.get("max_age_seconds"),
                "required_before": item.get("required_before"),
                "must_be_retained": True,
                "source_status_in_p9ct": item.get("status_in_p9ct"),
                "status_in_p9cu": "packaged_for_future_decision_not_collected",
                "collection_status_in_p9cu": "not_collected",
                "freshness_status_in_p9cu": "not_evaluated",
                "satisfied_for_final_decision": False,
            }
        )
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cu_required_final_decision_evidence_package.v1",
        "package_only": True,
        "final_owner_gate_required_before_any_order_submission": True,
        "final_owner_gate_required_before_candidate_executor_path_entry": True,
        "p9cu_satisfies_final_owner_live_order_gate": False,
        "fresh_remote_proof_collection_performed_in_p9cu": False,
        "evidence": rows,
    }


def build_decision_template(scope: dict[str, Any]) -> dict[str, Any]:
    candidate_terms = dict(scope.get("candidate_path_terms") or {})
    canary_terms = dict(scope.get("exact_canary_terms") or {})
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cu_final_owner_decision_template.v1",
        "template_only": True,
        "future_decision_gate_name": "final_owner_live_order_gate_decision_after_p9cs",
        "decision_status_in_p9cu": "not_collected",
        "must_explicitly_name": [
            "candidate_target_plan_sha256",
            "baseline_target_plan_sha256",
            "candidate_executor_target_plan_path_entry",
            "target_plan_replacement",
            "executor_input_mutation",
            "canary_order_terms",
            "risk_ceiling_usdt",
            "max_notional_usdt",
            "kill_switch_and_rollback_terms",
        ],
        "candidate_path_terms": candidate_terms,
        "canary_order_terms": canary_terms,
        "owner_must_choose_one": [
            "approve_exact_canary_live_order_under_bound_terms",
            "reject_or_defer_live_order_gate",
        ],
        "approval_collected_in_p9cu": False,
        "live_order_submission_authorized": False,
        "candidate_execution_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
    }


def build_decision_checklist() -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cu_final_decision_checklist.v1",
        "package_only": True,
        "approval_items": [
            {
                "item": item,
                "required_for_final_owner_live_order_gate": True,
                "satisfied_in_p9cu": satisfied,
            }
            for item, satisfied in DECISION_CHECKLIST
        ],
        "p9cu_satisfies_final_owner_live_order_gate": False,
    }


def build_review_package(
    *,
    run_id: str,
    p9ct_summary_path: Path,
    p9ct: dict[str, Any],
    scope: dict[str, Any],
    evidence_package: dict[str, Any],
    decision_template: dict[str, Any],
    checklist: dict[str, Any],
) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cu_final_owner_live_order_decision_review_package.v1",
        "run_id": run_id,
        "package_only": True,
        "source_p9ct_summary": evidence_file(p9ct_summary_path),
        "package_decision": "prepared_for_future_owner_decision_review_only",
        "future_decision_gate_name": "final_owner_live_order_gate_decision_after_p9cs",
        "final_owner_live_order_decision_collected": False,
        "decision_scope": scope,
        "required_final_decision_evidence_package": evidence_package,
        "final_owner_decision_template": decision_template,
        "final_decision_checklist": checklist,
        "baseline_target_plan_sha256": p9ct.get("baseline_target_plan_sha256"),
        "candidate_target_plan_sha256": p9ct.get("candidate_target_plan_sha256"),
        "only_distance_to_high_60_contribution_changed": p9ct.get(
            "only_distance_to_high_60_contribution_changed"
        )
        is True,
        "p9cu_satisfies_final_owner_live_order_gate": False,
        "live_order_gate_approved": False,
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


def build_phase9cu(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    now = now_fn()
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9cu" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    p9ct_path = latest_p9ct_summary(args)
    p9ct = load_optional(p9ct_path)
    scope_path = source_output_path(p9ct, "final_owner_live_order_gate_decision_scope")
    evidence_path = source_output_path(p9ct, "required_final_decision_evidence")
    non_auth_path = source_output_path(p9ct, "non_authorization")
    control_path = source_output_path(p9ct, "control_boundary_readback")
    scope = load_optional(scope_path)
    evidence = load_optional(evidence_path)
    p9ct_non_auth = load_optional(non_auth_path)
    p9ct_control = load_optional(control_path)
    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)
    owner_decision_ok = str(args.owner_decision) == APPROVE_P9CU_DECISION

    checks = {
        "owner_decision_p9cu_package_only_recorded": owner_decision_ok,
        "project_profile_exists": bool(project_profile),
        "current_stage_is_stage3": str(project_profile.get("current_stage") or "")
        == "stage_3_human_approved_execution",
        "p9ct_summary_exists": bool(p9ct),
        "p9ct_summary_ready_for_p9cu_package": p9ct_summary_ready(p9ct),
        "p9ct_decision_scope_ready": decision_scope_ready(scope, p9ct),
        "p9ct_required_final_decision_evidence_ready": required_decision_evidence_ready(
            evidence
        ),
        "p9ct_non_authorization_ready": p9ct_non_authorization_ready(p9ct_non_auth),
        "p9ct_control_boundary_ready": p9ct_control_ready(p9ct_control),
    }
    blockers = [key for key, value in checks.items() if not value]
    ready = not blockers

    evidence_package = build_evidence_package(evidence)
    decision_template = build_decision_template(scope)
    checklist = build_decision_checklist()
    review_package = build_review_package(
        run_id=run_id,
        p9ct_summary_path=p9ct_path,
        p9ct=p9ct,
        scope=scope,
        evidence_package=evidence_package,
        decision_template=decision_template,
        checklist=checklist,
    )
    owner_record = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cu_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "prepare_final_owner_live_order_decision_review_package_after_p9ct_only_no_order_no_candidate_no_executor_or_timer_change",
        "recorded_at_utc": iso_z(now),
        "p9cu_package_preparation_approved": owner_decision_ok,
        "future_p9cv_review_request_allowed_if_package_ready": ready,
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
        "contract_version": "hv_balanced_dth60_coinglass_phase9cu_non_authorization.v1",
        "run_id": run_id,
        "authorizations": {
            "prepare_final_owner_live_order_decision_review_package": ready,
            "allow_future_p9cv_package_review_request": ready,
            "review_p9cu_package_in_p9cu": False,
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
        "contract_version": "hv_balanced_dth60_coinglass_phase9cu_control_boundary.v1",
        "run_id": run_id,
        "scope": "final_owner_live_order_decision_review_package_preparation_only",
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
    package_path = proof_root / "final_owner_live_order_decision_review_package.json"
    evidence_out_path = proof_root / "required_final_decision_evidence_package.json"
    template_path = proof_root / "final_owner_decision_template.json"
    checklist_path = proof_root / "final_decision_checklist.json"
    non_auth_out_path = proof_root / "non_authorization.json"
    control_out_path = proof_root / "control_boundary_readback.json"
    summary_path = root / "summary.json"
    report_path = root / "p9cu_final_owner_live_order_decision_review_package.md"
    output_files = {
        "summary": str(summary_path),
        "owner_decision_record": str(owner_path),
        "final_owner_live_order_decision_review_package": str(package_path),
        "required_final_decision_evidence_package": str(evidence_out_path),
        "final_owner_decision_template": str(template_path),
        "final_decision_checklist": str(checklist_path),
        "non_authorization": str(non_auth_out_path),
        "control_boundary_readback": str(control_out_path),
        "report": str(report_path),
    }
    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "status": "ready" if ready else "blocked",
        "blockers": blockers,
        "p9cu_final_owner_live_order_decision_review_package_prepared": ready,
        "p9ct_sufficient_for_p9cu_package_preparation": ready,
        "decision_review_package_prepared_after_p9ct": ready,
        "required_final_decision_evidence_count": len(evidence_package["evidence"]),
        "final_decision_evidence_collected_in_p9cu": False,
        "fresh_proofs_collected_in_p9cu": False,
        "fresh_remote_proof_collection_approved_in_p9cu": False,
        "final_owner_live_order_gate_approval_collected": False,
        "p9cu_satisfies_final_owner_live_order_gate": False,
        "eligible_for_future_p9cv_package_review": ready,
        "eligible_for_future_live_order_submission": False,
        "eligible_for_future_candidate_execution": False,
        "eligible_for_future_candidate_executor_path_entry": False,
        "fresh_remote_proof_collection_performed_in_p9cu": False,
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
        "canary_symbol": CANARY_SYMBOL,
        "canary_side": CANARY_SIDE,
        "risk_ceiling_usdt": DEFAULT_RISK_CEILING_USDT,
        "max_notional_usdt": DEFAULT_MAX_NOTIONAL_USDT,
        "max_orders_per_cycle": DEFAULT_MAX_ORDERS_PER_CYCLE,
        "max_symbols_per_cycle": DEFAULT_MAX_SYMBOLS_PER_CYCLE,
        "order_type": DEFAULT_ORDER_TYPE,
        "time_in_force": DEFAULT_TIME_IN_FORCE,
        "market_orders_allowed": False,
        "baseline_target_plan_sha256": p9ct.get("baseline_target_plan_sha256"),
        "candidate_target_plan_sha256": p9ct.get("candidate_target_plan_sha256"),
        "only_distance_to_high_60_contribution_changed": p9ct.get(
            "only_distance_to_high_60_contribution_changed"
        )
        is True,
        "final_owner_decision_template_only": True,
        "final_owner_decision_collected_in_p9cu": False,
        "decision_checklist_total_count": len(DECISION_CHECKLIST),
        "decision_checklist_satisfied_count": len(
            [item for item, satisfied in DECISION_CHECKLIST if satisfied]
        ),
        "decision_checklist_unsatisfied_count": len(
            [item for item, satisfied in DECISION_CHECKLIST if not satisfied]
        ),
        "source_p9ct_summary_sha256": evidence_file(p9ct_path).get("sha256", ""),
        "source_p9ct_decision_scope_sha256": evidence_file(scope_path).get(
            "sha256", ""
        ),
        "source_p9ct_required_final_decision_evidence_sha256": evidence_file(
            evidence_path
        ).get("sha256", ""),
        "source_p9ct_non_authorization_sha256": evidence_file(non_auth_path).get(
            "sha256", ""
        ),
        "source_p9ct_control_boundary_sha256": evidence_file(control_path).get(
            "sha256", ""
        ),
        "allowed_next_gate": P9CV_GATE,
        "allowed_next_gate_scope": P9CV_SCOPE,
        "allowed_next_gate_must_be_separately_requested": True,
        "source_evidence": {
            "phase9ct_summary": evidence_file(p9ct_path),
            "phase9ct_final_owner_live_order_gate_decision_scope": evidence_file(
                scope_path
            ),
            "phase9ct_required_final_decision_evidence": evidence_file(evidence_path),
            "phase9ct_non_authorization": evidence_file(non_auth_path),
            "phase9ct_control_boundary": evidence_file(control_path),
            "project_profile": evidence_file(project_profile_path),
        },
        "checks": checks,
        "output_files": output_files,
    }

    write_json(owner_path, owner_record)
    write_json(package_path, review_package)
    write_json(evidence_out_path, evidence_package)
    write_json(template_path, decision_template)
    write_json(checklist_path, checklist)
    write_json(non_auth_out_path, non_authorization)
    write_json(control_out_path, control)
    write_json(summary_path, summary)
    report_path.write_text(render_markdown(summary), encoding="utf-8")
    return summary, 0 if ready else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9CU Final Owner Live-Order Decision Review Package",
        "",
        f"`Status: {summary['status']}`",
        "",
        "P9CU prepares a final owner live-order decision review package only. It does not SSH, read Binance, collect fresh proofs, call order-test endpoints, invoke supervisor/timer paths, execute the candidate, replace target plans, mutate executor input, remote sync, cancel orders, or submit orders.",
        "",
        "## Package Result",
        "",
        "```text",
        "p9cu_final_owner_live_order_decision_review_package_prepared = "
        f"{str(bool(summary['p9cu_final_owner_live_order_decision_review_package_prepared'])).lower()}",
        "p9ct_sufficient_for_p9cu_package_preparation = "
        f"{str(bool(summary['p9ct_sufficient_for_p9cu_package_preparation'])).lower()}",
        "p9cu_satisfies_final_owner_live_order_gate = false",
        "final_owner_live_order_gate_approval_collected = false",
        "final_decision_evidence_collected_in_p9cu = false",
        "fresh_proofs_collected_in_p9cu = false",
        f"required_final_decision_evidence_count = {summary['required_final_decision_evidence_count']}",
        f"decision_checklist_unsatisfied_count = {summary['decision_checklist_unsatisfied_count']}",
        "```",
        "",
        "## Candidate And Canary Terms",
        "",
        "```text",
        f"baseline_target_plan_sha256 = {summary['baseline_target_plan_sha256']}",
        f"candidate_target_plan_sha256 = {summary['candidate_target_plan_sha256']}",
        "only_distance_to_high_60_contribution_changed = true",
        f"symbol = {summary['canary_symbol']}",
        f"side = {summary['canary_side']}",
        f"risk_ceiling_usdt = {summary['risk_ceiling_usdt']}",
        f"max_notional_usdt = {summary['max_notional_usdt']}",
        f"order_type = {summary['order_type']}",
        f"time_in_force = {summary['time_in_force']}",
        "market_orders_allowed = false",
        "```",
        "",
        "## No-Order Boundary",
        "",
        "```text",
        "fresh_remote_proof_collection_performed_in_p9cu = false",
        "fresh_remote_account_read_performed = false",
        "fresh_order_book_read_performed = false",
        "exchange_filter_read_performed = false",
        "order_test_endpoint_called = false",
        "remote_execution_performed = false",
        "remote_sync_performed = false",
        "remote_files_written = 0",
        "live_order_gate_approved = false",
        "live_order_submission_authorized = false",
        "candidate_enter_executor_target_plan_path_authorized = false",
        "candidate_execution_authorized = false",
        "target_plan_replacement_authorized = false",
        "executor_input_mutation_authorized = false",
        "timer_path_load_authorized = false",
        "supervisor_invocation_authorized = false",
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
    if summary.get("blockers"):
        lines.extend(["", "## Blockers", "", *[f"- {item}" for item in summary["blockers"]]])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_phase9cu(parse_args(argv))
    print(
        "p9cu_final_owner_live_order_decision_review_package_prepared="
        + str(
            bool(summary["p9cu_final_owner_live_order_decision_review_package_prepared"])
        ).lower()
    )
    print(f"status={summary['status']}")
    print(f"run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
