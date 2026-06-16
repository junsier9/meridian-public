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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ca_fresh_remote_proof_collection_scope import (  # noqa: E402
    CONTRACT_VERSION as P9CA_CONTRACT,
    DEFAULT_MAX_NOTIONAL_USDT,
    DEFAULT_MAX_ORDERS_PER_CYCLE,
    DEFAULT_MAX_SYMBOLS_PER_CYCLE,
    DEFAULT_ORDER_TYPE,
    DEFAULT_OUTPUT_PARENT as P9CA_PARENT,
    DEFAULT_RISK_CEILING_USDT,
    DEFAULT_TIME_IN_FORCE,
    P9CB_GATE,
    P9CB_SCOPE,
    TARGET_DEPLOY_ROOT_HINT,
    TARGET_RUNNER_IDENTITY_HINT,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ca_fresh_remote_proof_collection_scope import (  # noqa: E402
    CANARY_SIDE,
    CANARY_SYMBOL,
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
    "hv_balanced_dth60_coinglass_phase9cb_fresh_remote_proof_collection_review_package.v1"
)
APPROVE_P9CB_DECISION = (
    "approve_p9cb_prepare_fresh_remote_proof_collection_review_package_only_no_remote_no_order_no_execution"
)
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/p9cb_fresh_remote_proof_review_package"
P9CC_GATE = (
    "P9CC_review_p9cb_fresh_remote_proof_collection_review_package_only_if_separately_requested"
)
P9CC_SCOPE = (
    "review_p9cb_package_sufficiency_before_any_fresh_remote_proof_collection_no_remote_no_order_no_execution"
)


EXPECTED_PROOFS = {
    "fresh_remote_account_read": 60,
    "pre_position_fingerprint": 60,
    "pre_open_order_fingerprint": 60,
    "pre_fill_trade_fingerprint": 60,
    "fresh_order_book": 10,
    "exchange_filter_readback": 60,
    "p9bu_terms_operator_acceptance": 300,
    "candidate_target_plan_hash_binding": 60,
    "baseline_candidate_plan_diff": 60,
    "kill_switch_readback": 60,
    "rollback_command_readback": 60,
    "final_owner_live_order_gate_approval": 300,
}
EXPECTED_READ_CATEGORIES = {
    "account_state_read",
    "position_state_read",
    "open_order_state_read",
    "fills_and_trades_read",
    "order_book_read",
    "exchange_info_and_symbol_filter_read",
    "operator_config_and_state_readback",
    "candidate_and_baseline_artifact_hash_readback",
    "kill_switch_and_rollback_readback",
}
EXPECTED_FORBIDDEN_ACTIONS = {
    "place_order",
    "cancel_order",
    "modify_order",
    "transfer_assets",
    "change_leverage",
    "change_margin_mode",
    "run_live_supervisor",
    "run_timer_path",
    "enable_or_start_production_timer_service",
    "mutate_live_config",
    "mutate_operator_state",
    "replace_executor_input",
    "replace_target_plan",
    "execute_candidate",
    "remote_sync_or_deploy_code",
    "write_files_outside_future_proof_artifact_root",
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare the P9CB fresh remote proof collection review package from "
            "retained P9CA scope evidence. P9CB is package-preparation-only: it "
            "does not SSH, read the account, read the order book, read exchange "
            "filters, collect fresh proofs, run supervisor/timer/remote paths, "
            "mutate executor input or target plans, execute the candidate, or "
            "submit orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9ca-summary", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9CB_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:p9cb_prepare_fresh_remote_proof_collection_review_package_only_if_separately_requested",
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


def latest_p9ca_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9ca_summary).strip():
        return resolve_path(args.phase9ca_summary)
    return latest_match(P9CA_PARENT, "*/summary.json")


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def source_output_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("output_files") or {}).get(key) or "")
    return resolve_path(text) if text.strip() else Path("")


def proof_rows_by_id(scope: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("proof_id")): dict(item)
        for item in list(scope.get("required_fresh_proofs") or [])
    }


def p9ca_summary_ready(summary: dict[str, Any]) -> bool:
    return (
        summary.get("contract_version") == P9CA_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9ca_fresh_remote_proof_collection_scope_defined") is True
        and summary.get("p9bz_sufficient_for_scope_definition") is True
        and summary.get("read_only_command_boundary_defined") is True
        and summary.get("proof_collection_acceptance_contract_defined") is True
        and summary.get("eligible_for_future_p9cb_package_preparation") is True
        and summary.get("eligible_for_future_fresh_remote_proof_collection") is False
        and summary.get("eligible_for_future_live_order_submission") is False
        and summary.get("fresh_remote_proof_collection_performed_in_p9ca") is False
        and summary.get("fresh_proofs_collected_in_p9ca") is False
        and summary.get("fresh_remote_account_read_performed") is False
        and summary.get("fresh_order_book_read_performed") is False
        and summary.get("exchange_filter_read_performed") is False
        and summary.get("target_runner_identity_hint") == TARGET_RUNNER_IDENTITY_HINT
        and summary.get("target_deploy_root_hint") == TARGET_DEPLOY_ROOT_HINT
        and summary.get("target_runner_identity_proven_in_p9ca") is False
        and summary.get("target_deploy_root_proven_in_p9ca") is False
        and summary.get("live_order_gate_approved") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("candidate_execution_authorized") is False
        and summary.get("target_plan_replacement_authorized") is False
        and summary.get("executor_input_mutation_authorized") is False
        and summary.get("remote_sync_authorized") is False
        and summary.get("remote_execution_authorized") is False
        and summary.get("allowed_next_gate") == P9CB_GATE
        and summary.get("allowed_next_gate_scope") == P9CB_SCOPE
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


def p9ca_scope_ready(scope: dict[str, Any]) -> bool:
    rows = proof_rows_by_id(scope)
    canary = dict(scope.get("canary_terms_carried_forward_for_future_review") or {})
    return (
        scope.get("contract_version") == "hv_balanced_dth60_coinglass_phase9ca_scope.v1"
        and scope.get("scope_definition_only") is True
        and scope.get("target_runner_identity_hint") == TARGET_RUNNER_IDENTITY_HINT
        and scope.get("target_deploy_root_hint") == TARGET_DEPLOY_ROOT_HINT
        and scope.get("target_runner_identity_proven_in_p9ca") is False
        and scope.get("target_deploy_root_proven_in_p9ca") is False
        and scope.get("read_only_collection_only") is True
        and scope.get("fresh_remote_proof_collection_performed_in_p9ca") is False
        and scope.get("future_collection_requires_separate_owner_gate") is True
        and set(rows) == set(EXPECTED_PROOFS)
        and all(
            int(rows[key].get("max_age_seconds") or 0) == max_age
            and rows[key].get("required") is True
            and rows[key].get("collection_status_in_p9ca") == "not_collected"
            and rows[key].get("future_collection_requires_separate_owner_gate") is True
            and rows[key].get("must_be_point_in_time_safe") is True
            for key, max_age in EXPECTED_PROOFS.items()
        )
        and canary.get("symbol") == CANARY_SYMBOL
        and canary.get("side") == CANARY_SIDE
        and float(canary.get("risk_ceiling_usdt") or 0) == DEFAULT_RISK_CEILING_USDT
        and float(canary.get("max_notional_usdt") or 0) == DEFAULT_MAX_NOTIONAL_USDT
        and int(canary.get("max_orders_per_cycle") or 0)
        == DEFAULT_MAX_ORDERS_PER_CYCLE
        and int(canary.get("max_symbols_per_cycle") or 0)
        == DEFAULT_MAX_SYMBOLS_PER_CYCLE
        and canary.get("order_type") == DEFAULT_ORDER_TYPE
        and canary.get("time_in_force") == DEFAULT_TIME_IN_FORCE
        and canary.get("market_orders_allowed") is False
        and canary.get("would_submit_order_in_p9ca") is False
    )


def p9ca_read_only_boundary_ready(boundary: dict[str, Any]) -> bool:
    return (
        boundary.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9ca_read_only_command_boundary.v1"
        and boundary.get("scope_definition_only") is True
        and list(boundary.get("commands_executed_in_p9ca") or []) == []
        and boundary.get("ssh_invoked_in_p9ca") is False
        and boundary.get("remote_network_connection_performed_in_p9ca") is False
        and set(boundary.get("allowed_future_read_categories") or [])
        == EXPECTED_READ_CATEGORIES
        and set(boundary.get("forbidden_future_actions_during_proof_collection") or [])
        == EXPECTED_FORBIDDEN_ACTIONS
    )


def p9ca_acceptance_ready(acceptance: dict[str, Any]) -> bool:
    deltas = dict(acceptance.get("delta_acceptance") or {})
    staleness = dict(acceptance.get("staleness_policy") or {})
    hashes = dict(acceptance.get("hash_binding_required") or {})
    return (
        acceptance.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9ca_acceptance_contract.v1"
        and acceptance.get("scope_definition_only") is True
        and acceptance.get("fresh_proofs_collected_in_p9ca") is False
        and acceptance.get("future_collection_requires_separate_owner_gate") is True
        and dict(acceptance.get("max_age_contract_by_proof_id") or {})
        == EXPECTED_PROOFS
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
        and {
            "position_fingerprint",
            "open_order_fingerprint",
            "fills_and_trades_fingerprint",
            "account_balance_fingerprint",
        }.issubset(set(acceptance.get("pre_post_fingerprints_required_for_future_collection") or []))
        and staleness.get("missing_proof_fails_closed") is True
        and staleness.get("stale_proof_fails_closed") is True
        and staleness.get("future_timestamp_fails_closed") is True
        and staleness.get("future_fill_or_stale_fill_evidence_must_fail_closed") is True
        and hashes.get("candidate_target_plan_hash") is True
        and hashes.get("baseline_target_plan_hash") is True
        and hashes.get("baseline_candidate_distance_to_high_60_only_diff") is True
        and hashes.get("proof_artifact_manifest_hash") is True
        and "zero order submissions"
        in list(acceptance.get("no_order_collection_phase_must_prove") or [])
        and "zero fills" in list(acceptance.get("no_order_collection_phase_must_prove") or [])
    )


def p9ca_non_authorization_ready(matrix: dict[str, Any]) -> bool:
    authorizations = dict(matrix.get("authorizations") or {})
    return (
        matrix.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9ca_non_authorization.v1"
        and authorizations.get("define_fresh_remote_proof_collection_scope") is True
        and authorizations.get("prepare_future_fresh_remote_proof_collection_package")
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


def p9ca_control_ready(control: dict[str, Any]) -> bool:
    return (
        control.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9ca_control_boundary.v1"
        and control.get("scope") == "fresh_remote_proof_collection_scope_definition_only"
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


def proof_collection_plan(scope: dict[str, Any]) -> list[dict[str, Any]]:
    rows = proof_rows_by_id(scope)
    plan = []
    for proof_id, max_age in EXPECTED_PROOFS.items():
        source = rows[proof_id]
        plan.append(
            {
                "proof_id": proof_id,
                "required": True,
                "max_age_seconds": max_age,
                "point_in_time_safe_required": True,
                "collection_status_in_p9cb": "not_collected",
                "future_collection_status": "pending_separate_owner_gate",
                "future_collection_channel": "remote_read_only",
                "purpose": source.get("purpose"),
            }
        )
    return plan


def build_review_package(
    *,
    run_id: str,
    p9ca_summary_path: Path,
    p9ca_summary: dict[str, Any],
    scope: dict[str, Any],
    boundary: dict[str, Any],
    acceptance: dict[str, Any],
) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cb_review_package.v1",
        "run_id": run_id,
        "package_only": True,
        "source_p9ca_summary": evidence_file(p9ca_summary_path),
        "future_gate_name": "fresh_remote_proof_collection_gate",
        "package_decision": "prepared_for_future_review_only",
        "target_runner_identity_hint": TARGET_RUNNER_IDENTITY_HINT,
        "target_deploy_root_hint": TARGET_DEPLOY_ROOT_HINT,
        "target_runner_identity_proven_in_p9cb": False,
        "target_deploy_root_proven_in_p9cb": False,
        "read_only_collection_only": True,
        "fresh_remote_proof_collection_performed_in_p9cb": False,
        "proof_collection_plan": proof_collection_plan(scope),
        "read_only_command_boundary": {
            "allowed_future_read_categories": list(
                boundary.get("allowed_future_read_categories") or []
            ),
            "forbidden_future_actions_during_proof_collection": list(
                boundary.get("forbidden_future_actions_during_proof_collection") or []
            ),
        },
        "acceptance_contract": {
            "delta_acceptance": dict(acceptance.get("delta_acceptance") or {}),
            "staleness_policy": dict(acceptance.get("staleness_policy") or {}),
            "hash_binding_required": dict(acceptance.get("hash_binding_required") or {}),
            "pre_post_fingerprints_required_for_future_collection": list(
                acceptance.get("pre_post_fingerprints_required_for_future_collection") or []
            ),
            "no_order_collection_phase_must_prove": list(
                acceptance.get("no_order_collection_phase_must_prove") or []
            ),
        },
        "future_gate_may_discuss": [
            "whether to execute a separately owner-approved read-only fresh proof collection run",
            "target runner identity readback requirements",
            "fresh account, position, open-order, fill/trade, order-book, and exchange-filter proof collection",
            "pre/post fingerprint delta acceptance for a no-order collection run",
        ],
        "future_gate_may_not_discuss": [
            "live order submission",
            "candidate execution",
            "target-plan replacement",
            "executor input mutation",
            "supervisor or timer invocation",
            "remote sync or deployment",
        ],
        "baseline_target_plan_sha256": p9ca_summary.get("baseline_target_plan_sha256"),
        "candidate_target_plan_sha256": p9ca_summary.get("candidate_target_plan_sha256"),
        "only_distance_to_high_60_contribution_changed": p9ca_summary.get(
            "only_distance_to_high_60_contribution_changed"
        ),
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
    }


def build_manifest_template(run_id: str, package: dict[str, Any]) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cb_collection_manifest_template.v1",
        "run_id": run_id,
        "package_only": True,
        "template_only_not_executed": True,
        "target_runner_identity_hint": TARGET_RUNNER_IDENTITY_HINT,
        "target_deploy_root_hint": TARGET_DEPLOY_ROOT_HINT,
        "future_collection_requires_separate_owner_gate": True,
        "required_output_artifacts": [
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
        ],
        "proof_ids": [item["proof_id"] for item in package["proof_collection_plan"]],
        "commands_executed_in_p9cb": [],
        "fresh_proofs_collected_in_p9cb": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
    }


def build_p9cb_fresh_remote_proof_collection_review_package(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    now = now_fn()
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9cb" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    p9ca_summary_path = latest_p9ca_summary(args)
    p9ca = load_optional(p9ca_summary_path)
    scope_path = source_output_path(p9ca, "fresh_remote_proof_collection_scope")
    boundary_path = source_output_path(p9ca, "read_only_command_boundary")
    acceptance_path = source_output_path(p9ca, "proof_collection_acceptance_contract")
    matrix_path = source_output_path(p9ca, "non_authorization")
    control_path = source_output_path(p9ca, "control_boundary_readback")
    scope = load_optional(scope_path)
    boundary = load_optional(boundary_path)
    acceptance = load_optional(acceptance_path)
    p9ca_matrix = load_optional(matrix_path)
    p9ca_control = load_optional(control_path)
    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)

    owner_decision_ok = str(args.owner_decision) == APPROVE_P9CB_DECISION
    checks = {
        "owner_decision_p9cb_package_only_recorded": owner_decision_ok,
        "project_profile_exists": bool(project_profile),
        "current_stage_is_stage3": str(project_profile.get("current_stage") or "")
        == "stage_3_human_approved_execution",
        "p9ca_summary_exists": bool(p9ca),
        "p9ca_summary_ready_for_review_package": p9ca_summary_ready(p9ca),
        "p9ca_scope_ready": p9ca_scope_ready(scope),
        "p9ca_read_only_boundary_ready": p9ca_read_only_boundary_ready(boundary),
        "p9ca_acceptance_contract_ready": p9ca_acceptance_ready(acceptance),
        "p9ca_non_authorization_ready": p9ca_non_authorization_ready(p9ca_matrix),
        "p9ca_control_boundary_ready": p9ca_control_ready(p9ca_control),
    }
    blockers = [key for key, value in checks.items() if not value]
    ready = not blockers

    review_package = build_review_package(
        run_id=run_id,
        p9ca_summary_path=p9ca_summary_path,
        p9ca_summary=p9ca,
        scope=scope,
        boundary=boundary,
        acceptance=acceptance,
    )
    manifest_template = build_manifest_template(run_id, review_package)
    owner_record = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cb_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "prepare_fresh_remote_proof_collection_review_package_only_no_remote_no_order_no_execution",
        "recorded_at_utc": iso_z(now),
        "review_package_preparation_approved": owner_decision_ok,
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
    non_authorization = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cb_non_authorization.v1",
        "run_id": run_id,
        "authorizations": {
            "prepare_fresh_remote_proof_collection_review_package": ready,
            "review_fresh_remote_proof_collection_review_package": ready,
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
        "contract_version": "hv_balanced_dth60_coinglass_phase9cb_control_boundary.v1",
        "run_id": run_id,
        "scope": "fresh_remote_proof_collection_review_package_preparation_only",
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
    package_path = proof_root / "fresh_remote_proof_collection_review_package.json"
    manifest_path = proof_root / "collection_manifest_template.json"
    non_auth_path = proof_root / "non_authorization.json"
    control_path_out = proof_root / "control.json"
    summary_path = root / "summary.json"
    report_path = root / "p9cb_fresh_remote_proof_collection_review_package.md"

    output_files = {
        "summary": str(summary_path),
        "owner_decision_record": str(owner_path),
        "fresh_remote_proof_collection_review_package": str(package_path),
        "collection_manifest_template": str(manifest_path),
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
        "p9cb_fresh_remote_proof_collection_review_package_prepared": ready,
        "p9ca_sufficient_for_review_package": p9ca_summary_ready(p9ca),
        "read_only_collection_plan_packaged": ready,
        "acceptance_contract_packaged": ready,
        "eligible_for_future_p9cc_package_review": ready,
        "eligible_for_future_fresh_remote_proof_collection": False,
        "eligible_for_future_live_order_submission": False,
        "fresh_remote_proof_collection_performed_in_p9cb": False,
        "fresh_proofs_collected_in_p9cb": False,
        "fresh_remote_account_read_performed": False,
        "fresh_order_book_read_performed": False,
        "exchange_filter_read_performed": False,
        "target_runner_identity_hint": TARGET_RUNNER_IDENTITY_HINT,
        "target_deploy_root_hint": TARGET_DEPLOY_ROOT_HINT,
        "target_runner_identity_proven_in_p9cb": False,
        "target_deploy_root_proven_in_p9cb": False,
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
        "allowed_next_gate": P9CC_GATE,
        "allowed_next_gate_scope": P9CC_SCOPE,
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
        "source_p9ca_summary_sha256": evidence_file(p9ca_summary_path).get("sha256", ""),
        "baseline_target_plan_sha256": p9ca.get("baseline_target_plan_sha256"),
        "candidate_target_plan_sha256": p9ca.get("candidate_target_plan_sha256"),
        "only_distance_to_high_60_contribution_changed": p9ca.get(
            "only_distance_to_high_60_contribution_changed"
        ),
        "source_evidence": {
            "phase9ca_summary": evidence_file(p9ca_summary_path),
            "phase9ca_scope": evidence_file(scope_path),
            "phase9ca_read_only_command_boundary": evidence_file(boundary_path),
            "phase9ca_acceptance_contract": evidence_file(acceptance_path),
            "phase9ca_non_authorization": evidence_file(matrix_path),
            "phase9ca_control_boundary": evidence_file(control_path),
            "project_profile": evidence_file(project_profile_path),
        },
        "output_files": output_files,
    }

    write_json(owner_path, owner_record)
    write_json(package_path, review_package)
    write_json(manifest_path, manifest_template)
    write_json(non_auth_path, non_authorization)
    write_json(control_path_out, control)
    write_json(summary_path, summary)
    report_path.write_text(render_markdown(summary), encoding="utf-8")

    return summary, 0 if ready else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9CB Fresh Remote Proof Collection Review Package",
        "",
        f"`Status: {summary['status']}`",
        "",
        "P9CB prepares the future fresh remote proof collection review package only. It does not SSH, read the account, read the order book, read exchange filters, collect fresh proofs, approve live orders, execute the candidate, replace target plans, mutate executor input, invoke supervisor/timer/remote paths, remote sync, remote execute, or submit orders.",
        "",
        "## Package Boundary",
        "",
        "```text",
        f"p9cb_fresh_remote_proof_collection_review_package_prepared = {str(bool(summary['p9cb_fresh_remote_proof_collection_review_package_prepared'])).lower()}",
        "fresh_remote_proof_collection_performed_in_p9cb = false",
        "fresh_remote_account_read_performed = false",
        "fresh_order_book_read_performed = false",
        "exchange_filter_read_performed = false",
        "eligible_for_future_fresh_remote_proof_collection = false",
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
        "## Future Target Runner Hints",
        "",
        "```text",
        f"target_runner_identity_hint = {summary['target_runner_identity_hint']}",
        f"target_deploy_root_hint = {summary['target_deploy_root_hint']}",
        "target_runner_identity_proven_in_p9cb = false",
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
    summary, exit_code = build_p9cb_fresh_remote_proof_collection_review_package(
        parse_args(argv)
    )
    print(f"status={summary['status']}")
    print(f"run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
