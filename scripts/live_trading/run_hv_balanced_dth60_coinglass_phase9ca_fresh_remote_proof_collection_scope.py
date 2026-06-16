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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bz_review_p9by_live_order_gate_package import (  # noqa: E402
    CANARY_SIDE,
    CANARY_SYMBOL,
    CONTRACT_VERSION as P9BZ_CONTRACT,
    DEFAULT_MAX_NOTIONAL_USDT,
    DEFAULT_MAX_ORDERS_PER_CYCLE,
    DEFAULT_MAX_SYMBOLS_PER_CYCLE,
    DEFAULT_ORDER_TYPE,
    DEFAULT_OUTPUT_PARENT as P9BZ_PARENT,
    DEFAULT_RISK_CEILING_USDT,
    DEFAULT_TIME_IN_FORCE,
    P9CA_GATE,
    P9CA_SCOPE,
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
    "hv_balanced_dth60_coinglass_phase9ca_fresh_remote_proof_collection_scope.v1"
)
APPROVE_P9CA_DECISION = (
    "approve_p9ca_define_fresh_remote_proof_collection_scope_only_no_remote_no_order_no_execution"
)
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/p9ca_fresh_remote_proof_scope"
P9CB_GATE = (
    "P9CB_prepare_fresh_remote_proof_collection_review_package_only_if_separately_requested"
)
P9CB_SCOPE = (
    "prepare_fresh_remote_proof_collection_package_from_p9ca_scope_only_no_remote_no_order_no_execution"
)
TARGET_RUNNER_IDENTITY_HINT = "root@203.0.113.10"
TARGET_DEPLOY_ROOT_HINT = "/root/meridian_alpha_live_runner/repo"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Define the P9CA fresh remote proof collection scope only. P9CA "
            "consumes retained P9BZ evidence and writes a proof-only scope "
            "package. It does not SSH, read the account, read the order book, "
            "collect fresh proofs, run supervisor/timer/remote paths, mutate "
            "executor input or target plans, execute the candidate, or submit "
            "orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9bz-summary", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9CA_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:p9ca_define_fresh_remote_proof_collection_scope_only_if_separately_requested",
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


def latest_p9bz_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9bz_summary).strip():
        return resolve_path(args.phase9bz_summary)
    return latest_match(P9BZ_PARENT, "*/summary.json")


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def source_output_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("output_files") or {}).get(key) or "")
    return resolve_path(text) if text.strip() else Path("")


def p9bz_summary_ready(summary: dict[str, Any]) -> bool:
    return (
        summary.get("contract_version") == P9BZ_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9bz_review_p9by_live_order_gate_package_ready") is True
        and summary.get(
            "p9by_package_sufficient_for_fresh_remote_proof_collection_scope_definition"
        )
        is True
        and summary.get("eligible_for_future_p9ca_scope_definition") is True
        and summary.get("eligible_for_future_fresh_remote_proof_collection") is False
        and summary.get("eligible_for_future_live_order_submission") is False
        and summary.get("fresh_remote_proof_collection_scope_defined_in_p9bz")
        is False
        and summary.get("fresh_proofs_collected_in_p9bz") is False
        and summary.get("fresh_remote_account_read_performed") is False
        and summary.get("fresh_order_book_read_performed") is False
        and summary.get("exchange_filter_read_performed") is False
        and summary.get("live_order_gate_approved") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("candidate_execution_authorized") is False
        and summary.get("target_plan_replacement_authorized") is False
        and summary.get("executor_input_mutation_authorized") is False
        and summary.get("remote_sync_authorized") is False
        and summary.get("remote_execution_authorized") is False
        and summary.get("allowed_next_gate") == P9CA_GATE
        and summary.get("allowed_next_gate_scope") == P9CA_SCOPE
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
        and int(summary.get("required_fresh_proof_count") or 0) == 12
        and summary.get("only_distance_to_high_60_contribution_changed") is True
        and int_zero(summary, "orders_submitted")
        and int_zero(summary, "orders_canceled")
        and int_zero(summary, "fill_count")
        and int_zero(summary, "trade_count")
    )


def p9bz_prerequisites_ready(prereq: dict[str, Any]) -> bool:
    before_collection = list(prereq.get("required_before_any_fresh_remote_proof_collection") or [])
    before_order = list(prereq.get("required_before_any_future_live_order_submission") or [])
    required_collection_items = {
        "separately requested P9CA scope definition",
        "target runner identity and read-only command boundary",
        "account-read, position, open-order, fill/trade, order-book, and exchange-filter proof collection plan",
        "no-order/no-cancel/no-trade delta acceptance contract",
        "explicit owner approval for proof collection only",
    }
    required_order_items = {
        "fresh proofs collected and retained",
        "fresh no-order candidate executor input hash binding",
        "post-only order price proof from fresh order book",
        "kill switch and rollback readback",
        "final owner live-order gate approval",
    }
    return (
        prereq.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9bz_future_gate_prerequisites.v1"
        and prereq.get("allowed_next_gate") == P9CA_GATE
        and prereq.get("allowed_next_gate_scope") == P9CA_SCOPE
        and required_collection_items.issubset(set(before_collection))
        and required_order_items.issubset(set(before_order))
    )


def p9bz_non_authorization_ready(matrix: dict[str, Any]) -> bool:
    authorizations = dict(matrix.get("authorizations") or {})
    return (
        matrix.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9bz_non_authorization.v1"
        and authorizations.get("review_p9by_live_order_gate_review_package") is True
        and authorizations.get("define_fresh_remote_proof_collection_scope") is False
        and authorizations.get("fresh_remote_proof_collection") is False
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


def p9bz_control_ready(control: dict[str, Any]) -> bool:
    return (
        control.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9bz_control_boundary.v1"
        and control.get("scope") == "p9by_package_review_only"
        and control.get("fresh_remote_account_read_performed") is False
        and control.get("fresh_order_book_read_performed") is False
        and control.get("exchange_filter_read_performed") is False
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


def required_fresh_proofs() -> list[dict[str, Any]]:
    proof_rows = [
        (
            "fresh_remote_account_read",
            60,
            "read account balances/equity on the target runner without account mutation",
        ),
        (
            "pre_position_fingerprint",
            60,
            "fingerprint all current positions before any future candidate execution discussion",
        ),
        (
            "pre_open_order_fingerprint",
            60,
            "fingerprint all open orders before any future candidate execution discussion",
        ),
        (
            "pre_fill_trade_fingerprint",
            60,
            "fingerprint recent fills and trades before any future candidate execution discussion",
        ),
        (
            "fresh_order_book",
            10,
            "bind any future post-only limit price discussion to a fresh book snapshot",
        ),
        (
            "exchange_filter_readback",
            60,
            "read symbol filters, precision, tick size, step size, min notional, and post-only support",
        ),
        (
            "p9bu_terms_operator_acceptance",
            300,
            "bind operator acceptance of exact P9BU risk and order terms",
        ),
        (
            "candidate_target_plan_hash_binding",
            60,
            "bind a no-order candidate target-plan hash before any executor-path discussion",
        ),
        (
            "baseline_candidate_plan_diff",
            60,
            "prove the candidate delta remains distance_to_high_60 contribution only",
        ),
        (
            "kill_switch_readback",
            60,
            "read kill-switch and disable path before any future live-order gate",
        ),
        (
            "rollback_command_readback",
            60,
            "read rollback commands and expected post-failure state boundary",
        ),
        (
            "final_owner_live_order_gate_approval",
            300,
            "retain a final owner approval artifact before any future order submission",
        ),
    ]
    return [
        {
            "proof_id": proof_id,
            "required": True,
            "max_age_seconds": max_age,
            "collection_status_in_p9ca": "not_collected",
            "future_collection_requires_separate_owner_gate": True,
            "must_be_point_in_time_safe": True,
            "purpose": purpose,
        }
        for proof_id, max_age, purpose in proof_rows
    ]


def build_scope(run_id: str, p9bz_summary_path: Path) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ca_scope.v1",
        "run_id": run_id,
        "scope_definition_only": True,
        "source_p9bz_summary": evidence_file(p9bz_summary_path),
        "target_runner_identity_hint": TARGET_RUNNER_IDENTITY_HINT,
        "target_deploy_root_hint": TARGET_DEPLOY_ROOT_HINT,
        "target_runner_identity_proven_in_p9ca": False,
        "target_deploy_root_proven_in_p9ca": False,
        "read_only_collection_only": True,
        "fresh_remote_proof_collection_performed_in_p9ca": False,
        "future_collection_requires_separate_owner_gate": True,
        "required_fresh_proofs": required_fresh_proofs(),
        "canary_terms_carried_forward_for_future_review": {
            "symbol": CANARY_SYMBOL,
            "side": CANARY_SIDE,
            "risk_ceiling_usdt": DEFAULT_RISK_CEILING_USDT,
            "max_notional_usdt": DEFAULT_MAX_NOTIONAL_USDT,
            "max_orders_per_cycle": DEFAULT_MAX_ORDERS_PER_CYCLE,
            "max_symbols_per_cycle": DEFAULT_MAX_SYMBOLS_PER_CYCLE,
            "order_type": DEFAULT_ORDER_TYPE,
            "time_in_force": DEFAULT_TIME_IN_FORCE,
            "market_orders_allowed": False,
            "would_submit_order_in_p9ca": False,
        },
    }


def build_read_only_command_boundary(run_id: str) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ca_read_only_command_boundary.v1",
        "run_id": run_id,
        "scope_definition_only": True,
        "commands_executed_in_p9ca": [],
        "ssh_invoked_in_p9ca": False,
        "remote_network_connection_performed_in_p9ca": False,
        "allowed_future_read_categories": [
            "account_state_read",
            "position_state_read",
            "open_order_state_read",
            "fills_and_trades_read",
            "order_book_read",
            "exchange_info_and_symbol_filter_read",
            "operator_config_and_state_readback",
            "candidate_and_baseline_artifact_hash_readback",
            "kill_switch_and_rollback_readback",
        ],
        "forbidden_future_actions_during_proof_collection": [
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
        ],
    }


def build_acceptance_contract(run_id: str) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ca_acceptance_contract.v1",
        "run_id": run_id,
        "scope_definition_only": True,
        "fresh_proofs_collected_in_p9ca": False,
        "future_collection_requires_separate_owner_gate": True,
        "max_age_contract_by_proof_id": {
            item["proof_id"]: item["max_age_seconds"] for item in required_fresh_proofs()
        },
        "delta_acceptance": {
            "order_delta_must_equal": 0,
            "cancel_delta_must_equal": 0,
            "fill_delta_must_equal": 0,
            "trade_delta_must_equal": 0,
            "position_delta_must_equal": 0,
            "balance_delta_must_equal": 0,
        },
        "pre_post_fingerprints_required_for_future_collection": [
            "position_fingerprint",
            "open_order_fingerprint",
            "fills_and_trades_fingerprint",
            "account_balance_fingerprint",
        ],
        "staleness_policy": {
            "missing_proof_fails_closed": True,
            "stale_proof_fails_closed": True,
            "future_timestamp_fails_closed": True,
            "clock_skew_must_be_reported": True,
            "future_fill_or_stale_fill_evidence_must_fail_closed": True,
        },
        "hash_binding_required": {
            "candidate_target_plan_hash": True,
            "baseline_target_plan_hash": True,
            "baseline_candidate_distance_to_high_60_only_diff": True,
            "proof_artifact_manifest_hash": True,
        },
        "no_order_collection_phase_must_prove": [
            "baseline-only executor remains unchanged",
            "candidate remains shadow-only until a later gate explicitly changes path authority",
            "zero order submissions",
            "zero cancels",
            "zero fills",
            "zero trades",
            "no live config mutation",
            "no operator state mutation",
            "no timer or service mutation",
        ],
    }


def build_p9ca_fresh_remote_proof_collection_scope(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    now = now_fn()
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9ca" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    p9bz_summary_path = latest_p9bz_summary(args)
    p9bz = load_optional(p9bz_summary_path)
    prereq_path = source_output_path(p9bz, "future_gate_prerequisites")
    matrix_path = source_output_path(p9bz, "non_authorization")
    control_path = source_output_path(p9bz, "control_boundary_readback")
    prereq = load_optional(prereq_path)
    p9bz_matrix = load_optional(matrix_path)
    p9bz_control = load_optional(control_path)
    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)

    owner_decision_ok = str(args.owner_decision) == APPROVE_P9CA_DECISION
    checks = {
        "owner_decision_p9ca_scope_only_recorded": owner_decision_ok,
        "project_profile_exists": bool(project_profile),
        "current_stage_is_stage3": str(project_profile.get("current_stage") or "")
        == "stage_3_human_approved_execution",
        "p9bz_summary_exists": bool(p9bz),
        "p9bz_summary_ready_for_p9ca_scope_definition": p9bz_summary_ready(p9bz),
        "p9bz_future_gate_prerequisites_ready": p9bz_prerequisites_ready(prereq),
        "p9bz_non_authorization_ready": p9bz_non_authorization_ready(p9bz_matrix),
        "p9bz_control_boundary_ready": p9bz_control_ready(p9bz_control),
    }
    blockers = [key for key, value in checks.items() if not value]
    ready = not blockers

    scope = build_scope(run_id, p9bz_summary_path)
    read_only_boundary = build_read_only_command_boundary(run_id)
    acceptance = build_acceptance_contract(run_id)
    owner_record = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ca_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "define_fresh_remote_proof_collection_scope_only_no_remote_no_order_no_execution",
        "recorded_at_utc": iso_z(now),
        "scope_definition_approved": owner_decision_ok,
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
        "contract_version": "hv_balanced_dth60_coinglass_phase9ca_non_authorization.v1",
        "run_id": run_id,
        "authorizations": {
            "define_fresh_remote_proof_collection_scope": ready,
            "prepare_future_fresh_remote_proof_collection_package": ready,
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
        "contract_version": "hv_balanced_dth60_coinglass_phase9ca_control_boundary.v1",
        "run_id": run_id,
        "scope": "fresh_remote_proof_collection_scope_definition_only",
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
    scope_path = proof_root / "fresh_remote_proof_collection_scope.json"
    boundary_path = proof_root / "read_only_command_boundary.json"
    acceptance_path = proof_root / "proof_collection_acceptance_contract.json"
    non_auth_path = proof_root / "non_authorization.json"
    control_path_out = proof_root / "control.json"
    summary_path = root / "summary.json"
    report_path = root / "p9ca_fresh_remote_proof_collection_scope.md"

    output_files = {
        "summary": str(summary_path),
        "owner_decision_record": str(owner_path),
        "fresh_remote_proof_collection_scope": str(scope_path),
        "read_only_command_boundary": str(boundary_path),
        "proof_collection_acceptance_contract": str(acceptance_path),
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
        "p9ca_fresh_remote_proof_collection_scope_defined": ready,
        "p9bz_sufficient_for_scope_definition": p9bz_summary_ready(p9bz),
        "read_only_command_boundary_defined": ready,
        "proof_collection_acceptance_contract_defined": ready,
        "eligible_for_future_p9cb_package_preparation": ready,
        "eligible_for_future_fresh_remote_proof_collection": False,
        "eligible_for_future_live_order_submission": False,
        "fresh_remote_proof_collection_performed_in_p9ca": False,
        "fresh_proofs_collected_in_p9ca": False,
        "fresh_remote_account_read_performed": False,
        "fresh_order_book_read_performed": False,
        "exchange_filter_read_performed": False,
        "target_runner_identity_hint": TARGET_RUNNER_IDENTITY_HINT,
        "target_deploy_root_hint": TARGET_DEPLOY_ROOT_HINT,
        "target_runner_identity_proven_in_p9ca": False,
        "target_deploy_root_proven_in_p9ca": False,
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
        "allowed_next_gate": P9CB_GATE,
        "allowed_next_gate_scope": P9CB_SCOPE,
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
        "required_fresh_proof_count": len(required_fresh_proofs()),
        "source_p9bz_summary_sha256": evidence_file(p9bz_summary_path).get("sha256", ""),
        "baseline_target_plan_sha256": p9bz.get("baseline_target_plan_sha256"),
        "candidate_target_plan_sha256": p9bz.get("candidate_target_plan_sha256"),
        "only_distance_to_high_60_contribution_changed": p9bz.get(
            "only_distance_to_high_60_contribution_changed"
        ),
        "source_evidence": {
            "phase9bz_summary": evidence_file(p9bz_summary_path),
            "phase9bz_future_gate_prerequisites": evidence_file(prereq_path),
            "phase9bz_non_authorization": evidence_file(matrix_path),
            "phase9bz_control_boundary": evidence_file(control_path),
            "project_profile": evidence_file(project_profile_path),
        },
        "output_files": output_files,
    }

    write_json(owner_path, owner_record)
    write_json(scope_path, scope)
    write_json(boundary_path, read_only_boundary)
    write_json(acceptance_path, acceptance)
    write_json(non_auth_path, non_authorization)
    write_json(control_path_out, control)
    write_json(summary_path, summary)
    report_path.write_text(render_markdown(summary), encoding="utf-8")

    return summary, 0 if ready else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9CA Fresh Remote Proof Collection Scope",
        "",
        f"`Status: {summary['status']}`",
        "",
        "P9CA defines the future fresh remote proof collection scope only. It does not SSH, read the account, read the order book, collect fresh proofs, approve live orders, execute the candidate, replace target plans, mutate executor input, invoke supervisor/timer/remote paths, remote sync, or submit orders.",
        "",
        "## Scope Boundary",
        "",
        "```text",
        f"p9ca_fresh_remote_proof_collection_scope_defined = {str(bool(summary['p9ca_fresh_remote_proof_collection_scope_defined'])).lower()}",
        "fresh_remote_proof_collection_performed_in_p9ca = false",
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
        "target_runner_identity_proven_in_p9ca = false",
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
    summary, exit_code = build_p9ca_fresh_remote_proof_collection_scope(parse_args(argv))
    print(f"status={summary['status']}")
    print(f"run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
