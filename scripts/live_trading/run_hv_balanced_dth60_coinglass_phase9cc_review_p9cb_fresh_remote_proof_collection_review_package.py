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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cb_fresh_remote_proof_collection_review_package import (  # noqa: E402
    CANARY_SIDE,
    CANARY_SYMBOL,
    CONTRACT_VERSION as P9CB_CONTRACT,
    DEFAULT_MAX_NOTIONAL_USDT,
    DEFAULT_MAX_ORDERS_PER_CYCLE,
    DEFAULT_MAX_SYMBOLS_PER_CYCLE,
    DEFAULT_ORDER_TYPE,
    DEFAULT_OUTPUT_PARENT as P9CB_PARENT,
    DEFAULT_RISK_CEILING_USDT,
    DEFAULT_TIME_IN_FORCE,
    EXPECTED_FORBIDDEN_ACTIONS,
    EXPECTED_PROOFS,
    EXPECTED_READ_CATEGORIES,
    P9CC_GATE,
    P9CC_SCOPE,
    TARGET_DEPLOY_ROOT_HINT,
    TARGET_RUNNER_IDENTITY_HINT,
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
    "hv_balanced_dth60_coinglass_phase9cc_review_p9cb_fresh_remote_proof_collection_review_package.v1"
)
APPROVE_P9CC_DECISION = (
    "approve_p9cc_review_p9cb_fresh_remote_proof_collection_review_package_only_no_remote_no_order_no_execution"
)
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/p9cc_review_p9cb_package"
P9CD_GATE = (
    "P9CD_allow_read_only_fresh_remote_proof_collection_owner_gate_only_if_separately_requested"
)
P9CD_SCOPE = (
    "allow_read_only_fresh_remote_proof_collection_owner_gate_discussion_only_no_remote_no_order_no_execution"
)
EXPECTED_MANIFEST_OUTPUTS = {
    "remote_runner_identity_readback.json",
    "fresh_remote_account_read.json",
    "pre_position_fingerprint.json",
    "pre_open_order_fingerprint.json",
    "pre_fill_trade_fingerprint.json",
    "fresh_order_book.json",
    "exchange_filter_readback.json",
    "p9bu_terms_operator_acceptance.json",
    "candidate_target_plan_hash_binding.json",
    "baseline_candidate_plan_diff.json",
    "kill_switch_readback.json",
    "rollback_command_readback.json",
    "post_position_fingerprint.json",
    "post_open_order_fingerprint.json",
    "post_fill_trade_fingerprint.json",
    "proof_collection_delta_acceptance.json",
    "proof_artifact_manifest.json",
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Review retained P9CB fresh remote proof collection review package "
            "evidence. P9CC is review-only: it does not SSH, read the account, "
            "read the order book, read exchange filters, collect fresh proofs, "
            "run supervisor/timer/remote paths, mutate executor input or target "
            "plans, execute the candidate, or submit orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9cb-summary", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9CC_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:p9cc_review_p9cb_fresh_remote_proof_collection_review_package_only_if_separately_requested",
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


def latest_p9cb_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9cb_summary).strip():
        return resolve_path(args.phase9cb_summary)
    return latest_match(P9CB_PARENT, "*/summary.json")


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def source_output_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("output_files") or {}).get(key) or "")
    return resolve_path(text) if text.strip() else Path("")


def p9cb_summary_ready(summary: dict[str, Any]) -> bool:
    return (
        summary.get("contract_version") == P9CB_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9cb_fresh_remote_proof_collection_review_package_prepared")
        is True
        and summary.get("p9ca_sufficient_for_review_package") is True
        and summary.get("read_only_collection_plan_packaged") is True
        and summary.get("acceptance_contract_packaged") is True
        and summary.get("eligible_for_future_p9cc_package_review") is True
        and summary.get("eligible_for_future_fresh_remote_proof_collection") is False
        and summary.get("eligible_for_future_live_order_submission") is False
        and summary.get("fresh_remote_proof_collection_performed_in_p9cb") is False
        and summary.get("fresh_proofs_collected_in_p9cb") is False
        and summary.get("fresh_remote_account_read_performed") is False
        and summary.get("fresh_order_book_read_performed") is False
        and summary.get("exchange_filter_read_performed") is False
        and summary.get("target_runner_identity_hint") == TARGET_RUNNER_IDENTITY_HINT
        and summary.get("target_deploy_root_hint") == TARGET_DEPLOY_ROOT_HINT
        and summary.get("target_runner_identity_proven_in_p9cb") is False
        and summary.get("target_deploy_root_proven_in_p9cb") is False
        and summary.get("live_order_gate_approved") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("candidate_execution_authorized") is False
        and summary.get("target_plan_replacement_authorized") is False
        and summary.get("executor_input_mutation_authorized") is False
        and summary.get("remote_sync_authorized") is False
        and summary.get("remote_execution_authorized") is False
        and summary.get("allowed_next_gate") == P9CC_GATE
        and summary.get("allowed_next_gate_scope") == P9CC_SCOPE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
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
        and int(summary.get("required_fresh_proof_count") or 0) == len(EXPECTED_PROOFS)
        and summary.get("only_distance_to_high_60_contribution_changed") is True
        and int_zero(summary, "orders_submitted")
        and int_zero(summary, "orders_canceled")
        and int_zero(summary, "fill_count")
        and int_zero(summary, "trade_count")
    )


def package_plan_ready(package: dict[str, Any]) -> bool:
    rows = {
        str(item.get("proof_id")): dict(item)
        for item in list(package.get("proof_collection_plan") or [])
    }
    boundary = dict(package.get("read_only_command_boundary") or {})
    acceptance = dict(package.get("acceptance_contract") or {})
    deltas = dict(acceptance.get("delta_acceptance") or {})
    staleness = dict(acceptance.get("staleness_policy") or {})
    hashes = dict(acceptance.get("hash_binding_required") or {})
    no_order = list(acceptance.get("no_order_collection_phase_must_prove") or [])
    return (
        package.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cb_review_package.v1"
        and package.get("package_only") is True
        and package.get("future_gate_name") == "fresh_remote_proof_collection_gate"
        and package.get("package_decision") == "prepared_for_future_review_only"
        and package.get("target_runner_identity_hint") == TARGET_RUNNER_IDENTITY_HINT
        and package.get("target_deploy_root_hint") == TARGET_DEPLOY_ROOT_HINT
        and package.get("target_runner_identity_proven_in_p9cb") is False
        and package.get("target_deploy_root_proven_in_p9cb") is False
        and package.get("read_only_collection_only") is True
        and package.get("fresh_remote_proof_collection_performed_in_p9cb") is False
        and set(rows) == set(EXPECTED_PROOFS)
        and all(
            int(rows[key].get("max_age_seconds") or 0) == max_age
            and rows[key].get("required") is True
            and rows[key].get("point_in_time_safe_required") is True
            and rows[key].get("collection_status_in_p9cb") == "not_collected"
            and rows[key].get("future_collection_status")
            == "pending_separate_owner_gate"
            and rows[key].get("future_collection_channel") == "remote_read_only"
            for key, max_age in EXPECTED_PROOFS.items()
        )
        and set(boundary.get("allowed_future_read_categories") or [])
        == EXPECTED_READ_CATEGORIES
        and set(boundary.get("forbidden_future_actions_during_proof_collection") or [])
        == EXPECTED_FORBIDDEN_ACTIONS
        and all(
            int(deltas.get(key) or 0) == 0
            for key in [
                "order_delta_must_equal",
                "cancel_delta_must_equal",
                "fill_delta_must_equal",
                "trade_delta_must_equal",
                "position_delta_must_equal",
                "balance_delta_must_equal",
            ]
        )
        and staleness.get("missing_proof_fails_closed") is True
        and staleness.get("stale_proof_fails_closed") is True
        and staleness.get("future_timestamp_fails_closed") is True
        and staleness.get("future_fill_or_stale_fill_evidence_must_fail_closed") is True
        and hashes.get("candidate_target_plan_hash") is True
        and hashes.get("baseline_target_plan_hash") is True
        and hashes.get("baseline_candidate_distance_to_high_60_only_diff") is True
        and hashes.get("proof_artifact_manifest_hash") is True
        and "zero order submissions" in no_order
        and "zero fills" in no_order
        and "whether to execute a separately owner-approved read-only fresh proof collection run"
        in list(package.get("future_gate_may_discuss") or [])
        and "live order submission" in list(package.get("future_gate_may_not_discuss") or [])
        and "remote sync or deployment"
        in list(package.get("future_gate_may_not_discuss") or [])
        and package.get("only_distance_to_high_60_contribution_changed") is True
        and int_zero(package, "orders_submitted")
        and int_zero(package, "orders_canceled")
        and int_zero(package, "fill_count")
        and int_zero(package, "trade_count")
    )


def manifest_template_ready(manifest: dict[str, Any]) -> bool:
    return (
        manifest.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cb_collection_manifest_template.v1"
        and manifest.get("package_only") is True
        and manifest.get("template_only_not_executed") is True
        and manifest.get("target_runner_identity_hint") == TARGET_RUNNER_IDENTITY_HINT
        and manifest.get("target_deploy_root_hint") == TARGET_DEPLOY_ROOT_HINT
        and manifest.get("future_collection_requires_separate_owner_gate") is True
        and set(manifest.get("required_output_artifacts") or [])
        == EXPECTED_MANIFEST_OUTPUTS
        and set(manifest.get("proof_ids") or []) == set(EXPECTED_PROOFS)
        and list(manifest.get("commands_executed_in_p9cb") or []) == []
        and manifest.get("fresh_proofs_collected_in_p9cb") is False
        and int_zero(manifest, "orders_submitted")
        and int_zero(manifest, "orders_canceled")
        and int_zero(manifest, "fill_count")
        and int_zero(manifest, "trade_count")
    )


def p9cb_non_authorization_ready(matrix: dict[str, Any]) -> bool:
    authorizations = dict(matrix.get("authorizations") or {})
    return (
        matrix.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cb_non_authorization.v1"
        and authorizations.get("prepare_fresh_remote_proof_collection_review_package")
        is True
        and authorizations.get("review_fresh_remote_proof_collection_review_package")
        is True
        and authorizations.get("fresh_remote_proof_collection") is False
        and authorizations.get("fresh_remote_account_read") is False
        and authorizations.get("fresh_order_book_read") is False
        and authorizations.get("exchange_filter_read") is False
        and authorizations.get("live_order_gate_approval") is False
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
        and authorizations.get("remote_sync") is False
        and authorizations.get("remote_execution") is False
        and authorizations.get("stage_governance_change") is False
    )


def p9cb_control_ready(control: dict[str, Any]) -> bool:
    return (
        control.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cb_control_boundary.v1"
        and control.get("scope")
        == "fresh_remote_proof_collection_review_package_preparation_only"
        and control.get("ssh_invoked") is False
        and control.get("remote_network_connection_performed") is False
        and control.get("fresh_remote_account_read_performed") is False
        and control.get("fresh_order_book_read_performed") is False
        and control.get("exchange_filter_read_performed") is False
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


def build_p9cc_review_p9cb_fresh_remote_proof_collection_review_package(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    now = now_fn()
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9cc" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    p9cb_summary_path = latest_p9cb_summary(args)
    p9cb = load_optional(p9cb_summary_path)
    package_path = source_output_path(p9cb, "fresh_remote_proof_collection_review_package")
    manifest_path = source_output_path(p9cb, "collection_manifest_template")
    matrix_path = source_output_path(p9cb, "non_authorization")
    control_path = source_output_path(p9cb, "control_boundary_readback")
    package = load_optional(package_path)
    manifest = load_optional(manifest_path)
    p9cb_matrix = load_optional(matrix_path)
    p9cb_control = load_optional(control_path)
    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)

    owner_decision_ok = str(args.owner_decision) == APPROVE_P9CC_DECISION
    checks = {
        "owner_decision_p9cc_review_only_recorded": owner_decision_ok,
        "project_profile_exists": bool(project_profile),
        "current_stage_is_stage3": str(project_profile.get("current_stage") or "")
        == "stage_3_human_approved_execution",
        "p9cb_summary_exists": bool(p9cb),
        "p9cb_summary_ready_for_package_review": p9cb_summary_ready(p9cb),
        "p9cb_review_package_ready": package_plan_ready(package),
        "p9cb_manifest_template_ready": manifest_template_ready(manifest),
        "p9cb_non_authorization_ready": p9cb_non_authorization_ready(p9cb_matrix),
        "p9cb_control_boundary_ready": p9cb_control_ready(p9cb_control),
    }
    blockers = [key for key, value in checks.items() if not value]
    ready = not blockers

    owner_record = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cc_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "review_p9cb_package_sufficiency_only_no_remote_no_order_no_execution",
        "recorded_at_utc": iso_z(now),
        "package_review_approved": owner_decision_ok,
        "fresh_remote_proof_collection_owner_gate_approved": False,
        "fresh_remote_proof_collection_approved": False,
        "fresh_remote_account_read_approved": False,
        "order_book_read_approved": False,
        "exchange_filter_read_approved": False,
        "remote_execution_approved": False,
        "live_order_gate_approved": False,
        "candidate_execution_approved": False,
        "target_plan_replacement_approved": False,
        "executor_input_mutation_approved": False,
        "live_order_submission_approved": False,
    }
    review = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cc_sufficiency_review.v1",
        "run_id": run_id,
        "status": "ready" if ready else "blocked",
        "review_scope": "p9cb_package_sufficiency_before_any_fresh_remote_proof_collection",
        "checks": checks,
        "blockers": blockers,
        "p9cb_package_sufficient_for_fresh_remote_proof_collection_owner_gate": ready,
        "fresh_remote_proof_collection_owner_gate_approved_in_p9cc": False,
        "fresh_remote_proof_collection_performed": False,
        "live_order_gate_approved": False,
    }
    prerequisites = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cc_future_gate_prerequisites.v1",
        "run_id": run_id,
        "allowed_next_gate": P9CD_GATE,
        "allowed_next_gate_scope": P9CD_SCOPE,
        "required_before_any_fresh_remote_proof_collection": [
            "separately requested P9CD owner gate",
            "explicit owner approval for read-only proof collection only",
            "target runner identity and deploy-root readback plan",
            "strict read-only command manifest using retained P9CB package",
            "pre/post account, position, open-order, fill/trade fingerprints",
            "zero order/cancel/fill/trade/position/balance delta acceptance contract",
            "fresh proof artifacts retained under a dedicated proof root",
        ],
        "still_required_before_any_future_live_order_submission": [
            "fresh proofs collected and reviewed in later gates",
            "fresh no-order candidate executor input hash binding",
            "post-only order price proof from fresh order book",
            "kill switch and rollback readback",
            "final owner live-order gate approval",
        ],
    }
    non_authorization = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cc_non_authorization.v1",
        "run_id": run_id,
        "authorizations": {
            "review_p9cb_fresh_remote_proof_collection_review_package": ready,
            "allow_fresh_remote_proof_collection_owner_gate": False,
            "fresh_remote_proof_collection": False,
            "fresh_remote_account_read": False,
            "fresh_order_book_read": False,
            "exchange_filter_read": False,
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
            "remote_sync": False,
            "remote_execution": False,
            "stage_governance_change": False,
        },
    }
    control = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cc_control_boundary.v1",
        "run_id": run_id,
        "scope": "p9cb_package_review_only",
        "ssh_invoked": False,
        "remote_network_connection_performed": False,
        "fresh_remote_account_read_performed": False,
        "fresh_order_book_read_performed": False,
        "exchange_filter_read_performed": False,
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
    review_path = proof_root / "sufficiency_review.json"
    prereq_path = proof_root / "future_gate_prerequisites.json"
    non_auth_path = proof_root / "non_authorization.json"
    control_path_out = proof_root / "control.json"
    summary_path = root / "summary.json"
    report_path = root / "p9cc_review_p9cb_package.md"

    output_files = {
        "summary": str(summary_path),
        "owner_decision_record": str(owner_path),
        "sufficiency_review": str(review_path),
        "future_gate_prerequisites": str(prereq_path),
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
        "p9cc_review_p9cb_fresh_remote_proof_collection_review_package_ready": ready,
        "p9cb_package_sufficient_for_fresh_remote_proof_collection_owner_gate": ready,
        "eligible_for_future_p9cd_owner_gate": ready,
        "eligible_for_future_fresh_remote_proof_collection": False,
        "eligible_for_future_live_order_submission": False,
        "fresh_remote_proof_collection_owner_gate_approved_in_p9cc": False,
        "fresh_remote_proof_collection_performed_in_p9cc": False,
        "fresh_proofs_collected_in_p9cc": False,
        "fresh_remote_account_read_performed": False,
        "fresh_order_book_read_performed": False,
        "exchange_filter_read_performed": False,
        "target_runner_identity_hint": TARGET_RUNNER_IDENTITY_HINT,
        "target_deploy_root_hint": TARGET_DEPLOY_ROOT_HINT,
        "target_runner_identity_proven_in_p9cc": False,
        "target_deploy_root_proven_in_p9cc": False,
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
        "allowed_next_gate": P9CD_GATE,
        "allowed_next_gate_scope": P9CD_SCOPE,
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
        "required_fresh_proof_count": len(EXPECTED_PROOFS),
        "source_p9cb_summary_sha256": evidence_file(p9cb_summary_path).get("sha256", ""),
        "baseline_target_plan_sha256": p9cb.get("baseline_target_plan_sha256"),
        "candidate_target_plan_sha256": p9cb.get("candidate_target_plan_sha256"),
        "only_distance_to_high_60_contribution_changed": p9cb.get(
            "only_distance_to_high_60_contribution_changed"
        ),
        "source_evidence": {
            "phase9cb_summary": evidence_file(p9cb_summary_path),
            "phase9cb_review_package": evidence_file(package_path),
            "phase9cb_manifest_template": evidence_file(manifest_path),
            "phase9cb_non_authorization": evidence_file(matrix_path),
            "phase9cb_control_boundary": evidence_file(control_path),
            "project_profile": evidence_file(project_profile_path),
        },
        "output_files": output_files,
    }

    write_json(owner_path, owner_record)
    write_json(review_path, review)
    write_json(prereq_path, prerequisites)
    write_json(non_auth_path, non_authorization)
    write_json(control_path_out, control)
    write_json(summary_path, summary)
    report_path.write_text(render_markdown(summary), encoding="utf-8")

    return summary, 0 if ready else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9CC Review P9CB Fresh Remote Proof Collection Package",
        "",
        f"`Status: {summary['status']}`",
        "",
        "P9CC reviews the retained P9CB fresh remote proof collection review package only. It does not authorize or execute fresh proof collection, SSH, account reads, order-book reads, exchange-filter reads, live orders, candidate execution, target-plan replacement, executor mutation, supervisor/timer invocation, remote sync, or remote execution.",
        "",
        "## Review Boundary",
        "",
        "```text",
        f"p9cc_review_p9cb_fresh_remote_proof_collection_review_package_ready = {str(bool(summary['p9cc_review_p9cb_fresh_remote_proof_collection_review_package_ready'])).lower()}",
        f"p9cb_package_sufficient_for_fresh_remote_proof_collection_owner_gate = {str(bool(summary['p9cb_package_sufficient_for_fresh_remote_proof_collection_owner_gate'])).lower()}",
        "fresh_remote_proof_collection_owner_gate_approved_in_p9cc = false",
        "fresh_remote_proof_collection_performed_in_p9cc = false",
        "fresh_remote_account_read_performed = false",
        "fresh_order_book_read_performed = false",
        "exchange_filter_read_performed = false",
        "eligible_for_future_fresh_remote_proof_collection = false",
        "eligible_for_future_live_order_submission = false",
        "live_order_submission_authorized = false",
        "candidate_execution_authorized = false",
        "target_plan_replacement_authorized = false",
        "executor_input_mutation_authorized = false",
        "orders_submitted = 0",
        "fill_count = 0",
        "```",
        "",
        "## Allowed Next Gate",
        "",
        "```text",
        str(summary["allowed_next_gate"]),
        "```",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = (
        build_p9cc_review_p9cb_fresh_remote_proof_collection_review_package(
            parse_args(argv)
        )
    )
    print(f"status={summary['status']}")
    print(f"run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
