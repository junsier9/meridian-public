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
    DEFAULT_MAX_NOTIONAL_USDT,
    DEFAULT_MAX_ORDERS_PER_CYCLE,
    DEFAULT_MAX_SYMBOLS_PER_CYCLE,
    DEFAULT_ORDER_TYPE,
    DEFAULT_RISK_CEILING_USDT,
    DEFAULT_TIME_IN_FORCE,
    EXPECTED_FORBIDDEN_ACTIONS,
    EXPECTED_PROOFS,
    EXPECTED_READ_CATEGORIES,
    TARGET_DEPLOY_ROOT_HINT,
    TARGET_RUNNER_IDENTITY_HINT,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cc_review_p9cb_fresh_remote_proof_collection_review_package import (  # noqa: E402
    CONTRACT_VERSION as P9CC_CONTRACT,
    DEFAULT_OUTPUT_PARENT as P9CC_PARENT,
    EXPECTED_MANIFEST_OUTPUTS,
    P9CD_GATE,
    P9CD_SCOPE,
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
    "hv_balanced_dth60_coinglass_phase9cd_read_only_fresh_remote_proof_collection_owner_gate.v1"
)
APPROVE_P9CD_DECISION = (
    "approve_p9cd_allow_read_only_fresh_remote_proof_collection_owner_gate_only_no_collection_no_order_no_execution"
)
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/p9cd_read_only_fresh_remote_proof_collection_owner_gate"
)
P9CE_GATE = (
    "P9CE_execute_read_only_fresh_remote_proof_collection_only_if_separately_requested"
)
P9CE_SCOPE = (
    "execute_read_only_fresh_remote_proof_collection_from_p9cb_manifest_no_order_no_candidate_no_timer_no_supervisor_no_executor_mutation"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build the P9CD owner gate for allowing a later read-only fresh "
            "remote proof collection request. P9CD is discussion/authorization "
            "only: it does not SSH, read the account, read the order book, read "
            "exchange filters, collect fresh proofs, run supervisor/timer/remote "
            "paths, mutate executor input or target plans, execute the candidate, "
            "or submit orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9cc-summary", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9CD_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:p9cd_allow_read_only_fresh_remote_proof_collection_owner_gate_only_if_separately_requested",
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


def latest_p9cc_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9cc_summary).strip():
        return resolve_path(args.phase9cc_summary)
    return latest_match(P9CC_PARENT, "*/summary.json")


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def source_output_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("output_files") or {}).get(key) or "")
    return resolve_path(text) if text.strip() else Path("")


def p9cc_summary_ready(summary: dict[str, Any]) -> bool:
    return (
        summary.get("contract_version") == P9CC_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get(
            "p9cc_review_p9cb_fresh_remote_proof_collection_review_package_ready"
        )
        is True
        and summary.get(
            "p9cb_package_sufficient_for_fresh_remote_proof_collection_owner_gate"
        )
        is True
        and summary.get("eligible_for_future_p9cd_owner_gate") is True
        and summary.get("eligible_for_future_fresh_remote_proof_collection") is False
        and summary.get("eligible_for_future_live_order_submission") is False
        and summary.get(
            "fresh_remote_proof_collection_owner_gate_approved_in_p9cc"
        )
        is False
        and summary.get("fresh_remote_proof_collection_performed_in_p9cc") is False
        and summary.get("fresh_proofs_collected_in_p9cc") is False
        and summary.get("fresh_remote_account_read_performed") is False
        and summary.get("fresh_order_book_read_performed") is False
        and summary.get("exchange_filter_read_performed") is False
        and summary.get("target_runner_identity_hint") == TARGET_RUNNER_IDENTITY_HINT
        and summary.get("target_deploy_root_hint") == TARGET_DEPLOY_ROOT_HINT
        and summary.get("target_runner_identity_proven_in_p9cc") is False
        and summary.get("target_deploy_root_proven_in_p9cc") is False
        and summary.get("live_order_gate_approved") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("candidate_execution_authorized") is False
        and summary.get("target_plan_replacement_authorized") is False
        and summary.get("executor_input_mutation_authorized") is False
        and summary.get("remote_sync_authorized") is False
        and summary.get("remote_execution_authorized") is False
        and summary.get("allowed_next_gate") == P9CD_GATE
        and summary.get("allowed_next_gate_scope") == P9CD_SCOPE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
        and summary.get("canary_symbol") == CANARY_SYMBOL
        and summary.get("canary_side") == CANARY_SIDE
        and float(summary.get("risk_ceiling_usdt") or 0) == DEFAULT_RISK_CEILING_USDT
        and float(summary.get("max_notional_usdt") or 0)
        == DEFAULT_MAX_NOTIONAL_USDT
        and int(summary.get("max_orders_per_cycle") or 0)
        == DEFAULT_MAX_ORDERS_PER_CYCLE
        and int(summary.get("max_symbols_per_cycle") or 0)
        == DEFAULT_MAX_SYMBOLS_PER_CYCLE
        and summary.get("order_type") == DEFAULT_ORDER_TYPE
        and summary.get("time_in_force") == DEFAULT_TIME_IN_FORCE
        and summary.get("market_orders_allowed") is False
        and int(summary.get("required_fresh_proof_count") or 0)
        == len(EXPECTED_PROOFS)
        and summary.get("only_distance_to_high_60_contribution_changed") is True
        and int_zero(summary, "orders_submitted")
        and int_zero(summary, "orders_canceled")
        and int_zero(summary, "fill_count")
        and int_zero(summary, "trade_count")
    )


def p9cc_sufficiency_review_ready(review: dict[str, Any]) -> bool:
    checks = dict(review.get("checks") or {})
    return (
        review.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cc_sufficiency_review.v1"
        and review.get("status") == "ready"
        and not review.get("blockers")
        and checks
        and all(value is True for value in checks.values())
        and review.get(
            "p9cb_package_sufficient_for_fresh_remote_proof_collection_owner_gate"
        )
        is True
        and review.get(
            "fresh_remote_proof_collection_owner_gate_approved_in_p9cc"
        )
        is False
        and review.get("fresh_remote_proof_collection_performed") is False
        and review.get("live_order_gate_approved") is False
    )


def p9cc_prerequisites_ready(prereq: dict[str, Any]) -> bool:
    before_collection = set(
        prereq.get("required_before_any_fresh_remote_proof_collection") or []
    )
    before_order = set(
        prereq.get("still_required_before_any_future_live_order_submission") or []
    )
    required_collection = {
        "separately requested P9CD owner gate",
        "explicit owner approval for read-only proof collection only",
        "target runner identity and deploy-root readback plan",
        "strict read-only command manifest using retained P9CB package",
        "pre/post account, position, open-order, fill/trade fingerprints",
        "zero order/cancel/fill/trade/position/balance delta acceptance contract",
        "fresh proof artifacts retained under a dedicated proof root",
    }
    required_order = {
        "fresh proofs collected and reviewed in later gates",
        "fresh no-order candidate executor input hash binding",
        "post-only order price proof from fresh order book",
        "kill switch and rollback readback",
        "final owner live-order gate approval",
    }
    return (
        prereq.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cc_future_gate_prerequisites.v1"
        and prereq.get("allowed_next_gate") == P9CD_GATE
        and prereq.get("allowed_next_gate_scope") == P9CD_SCOPE
        and required_collection.issubset(before_collection)
        and required_order.issubset(before_order)
    )


def p9cc_non_authorization_ready(matrix: dict[str, Any]) -> bool:
    authorizations = dict(matrix.get("authorizations") or {})
    return (
        matrix.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cc_non_authorization.v1"
        and authorizations.get(
            "review_p9cb_fresh_remote_proof_collection_review_package"
        )
        is True
        and authorizations.get("allow_fresh_remote_proof_collection_owner_gate")
        is False
        and authorizations.get("fresh_remote_proof_collection") is False
        and authorizations.get("fresh_remote_account_read") is False
        and authorizations.get("fresh_order_book_read") is False
        and authorizations.get("exchange_filter_read") is False
        and authorizations.get("live_order_gate_approval") is False
        and authorizations.get("actual_candidate_executor_target_path_entry")
        is False
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


def p9cc_control_ready(control: dict[str, Any]) -> bool:
    return (
        control.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cc_control_boundary.v1"
        and control.get("scope") == "p9cb_package_review_only"
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
        and control.get("candidate_entered_actual_executor_target_plan_path")
        is False
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


def build_read_only_collection_gate_terms(
    run_id: str,
    p9cc_summary_path: Path,
    p9cc_summary: dict[str, Any],
) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cd_collection_gate_terms.v1",
        "run_id": run_id,
        "owner_gate_only": True,
        "source_p9cc_summary": evidence_file(p9cc_summary_path),
        "allowed_next_gate": P9CE_GATE,
        "allowed_next_gate_scope": P9CE_SCOPE,
        "allowed_next_gate_must_be_separately_requested": True,
        "read_only_fresh_remote_proof_collection_may_be_requested_next": True,
        "read_only_collection_execution_performed_in_p9cd": False,
        "target_runner_identity_hint": TARGET_RUNNER_IDENTITY_HINT,
        "target_deploy_root_hint": TARGET_DEPLOY_ROOT_HINT,
        "target_runner_identity_proven_in_p9cd": False,
        "target_deploy_root_proven_in_p9cd": False,
        "required_proofs": [
            {
                "proof_id": proof_id,
                "required": True,
                "max_age_seconds": max_age,
                "point_in_time_safe_required": True,
                "collection_status_in_p9cd": "not_collected",
                "future_collection_status": "pending_separate_p9ce_request",
                "future_collection_channel": "remote_read_only",
            }
            for proof_id, max_age in EXPECTED_PROOFS.items()
        ],
        "required_output_artifacts": sorted(EXPECTED_MANIFEST_OUTPUTS),
        "allowed_future_read_categories": sorted(EXPECTED_READ_CATEGORIES),
        "forbidden_future_actions_during_proof_collection": sorted(
            EXPECTED_FORBIDDEN_ACTIONS
        ),
        "delta_acceptance": {
            "order_delta_must_equal": 0,
            "cancel_delta_must_equal": 0,
            "fill_delta_must_equal": 0,
            "trade_delta_must_equal": 0,
            "position_delta_must_equal": 0,
            "balance_delta_must_equal": 0,
        },
        "staleness_policy": {
            "missing_proof_fails_closed": True,
            "stale_proof_fails_closed": True,
            "future_timestamp_fails_closed": True,
            "future_fill_or_stale_fill_evidence_must_fail_closed": True,
        },
        "hash_binding_required": {
            "candidate_target_plan_hash": True,
            "baseline_target_plan_hash": True,
            "baseline_candidate_distance_to_high_60_only_diff": True,
            "proof_artifact_manifest_hash": True,
        },
        "baseline_target_plan_sha256": p9cc_summary.get("baseline_target_plan_sha256"),
        "candidate_target_plan_sha256": p9cc_summary.get("candidate_target_plan_sha256"),
        "only_distance_to_high_60_contribution_changed": p9cc_summary.get(
            "only_distance_to_high_60_contribution_changed"
        ),
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
    }


def build_p9cd_read_only_fresh_remote_proof_collection_owner_gate(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    now = now_fn()
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9cd" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    p9cc_summary_path = latest_p9cc_summary(args)
    p9cc = load_optional(p9cc_summary_path)
    sufficiency_path = source_output_path(p9cc, "sufficiency_review")
    prereq_path = source_output_path(p9cc, "future_gate_prerequisites")
    matrix_path = source_output_path(p9cc, "non_authorization")
    control_path = source_output_path(p9cc, "control_boundary_readback")
    sufficiency = load_optional(sufficiency_path)
    prereq = load_optional(prereq_path)
    p9cc_matrix = load_optional(matrix_path)
    p9cc_control = load_optional(control_path)
    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)

    owner_decision_ok = str(args.owner_decision) == APPROVE_P9CD_DECISION
    checks = {
        "owner_decision_p9cd_owner_gate_recorded": owner_decision_ok,
        "project_profile_exists": bool(project_profile),
        "current_stage_is_stage3": str(project_profile.get("current_stage") or "")
        == "stage_3_human_approved_execution",
        "p9cc_summary_exists": bool(p9cc),
        "p9cc_summary_ready_for_owner_gate": p9cc_summary_ready(p9cc),
        "p9cc_sufficiency_review_ready": p9cc_sufficiency_review_ready(sufficiency),
        "p9cc_future_gate_prerequisites_ready": p9cc_prerequisites_ready(prereq),
        "p9cc_non_authorization_ready": p9cc_non_authorization_ready(p9cc_matrix),
        "p9cc_control_boundary_ready": p9cc_control_ready(p9cc_control),
    }
    blockers = [key for key, value in checks.items() if not value]
    ready = not blockers

    owner_record = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cd_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "allow_future_read_only_fresh_remote_proof_collection_gate_only_no_collection_no_order_no_execution",
        "decision_effect": (
            "allow_future_p9ce_read_only_collection_gate_if_separately_requested"
            if owner_decision_ok
            else "none"
        ),
        "recorded_at_utc": iso_z(now),
        "read_only_fresh_remote_proof_collection_owner_gate_approved": owner_decision_ok,
        "future_p9ce_read_only_collection_gate_may_be_requested": owner_decision_ok,
        "fresh_remote_proof_collection_execution_approved_in_p9cd": False,
        "fresh_remote_account_read_approved_in_p9cd": False,
        "order_book_read_approved_in_p9cd": False,
        "exchange_filter_read_approved_in_p9cd": False,
        "remote_execution_approved": False,
        "live_order_gate_approved": False,
        "candidate_execution_approved": False,
        "target_plan_replacement_approved": False,
        "executor_input_mutation_approved": False,
        "live_order_submission_approved": False,
    }
    gate_terms = build_read_only_collection_gate_terms(
        run_id,
        p9cc_summary_path,
        p9cc,
    )
    non_authorization = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cd_non_authorization.v1",
        "run_id": run_id,
        "authorizations": {
            "allow_future_p9ce_read_only_collection_gate_request": ready,
            "execute_read_only_fresh_remote_proof_collection_in_p9cd": False,
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
        "contract_version": "hv_balanced_dth60_coinglass_phase9cd_control_boundary.v1",
        "run_id": run_id,
        "scope": "read_only_fresh_remote_proof_collection_owner_gate_only",
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
    terms_path = proof_root / "read_only_collection_gate_terms.json"
    non_auth_path = proof_root / "non_authorization.json"
    control_path_out = proof_root / "control.json"
    summary_path = root / "summary.json"
    report_path = root / "p9cd_read_only_fresh_remote_proof_collection_owner_gate.md"

    output_files = {
        "summary": str(summary_path),
        "owner_decision_record": str(owner_path),
        "read_only_collection_gate_terms": str(terms_path),
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
        "p9cd_read_only_fresh_remote_proof_collection_owner_gate_ready": ready,
        "p9cc_sufficient_for_p9cd_owner_gate": p9cc_summary_ready(p9cc),
        "read_only_fresh_remote_proof_collection_owner_gate_approved_in_p9cd": ready,
        "eligible_for_future_p9ce_read_only_collection_execution_gate": ready,
        "eligible_for_future_fresh_remote_proof_collection_without_separate_request": False,
        "eligible_for_future_live_order_submission": False,
        "fresh_remote_proof_collection_execution_approved_in_p9cd": False,
        "fresh_remote_proof_collection_performed_in_p9cd": False,
        "fresh_proofs_collected_in_p9cd": False,
        "fresh_remote_account_read_performed": False,
        "fresh_order_book_read_performed": False,
        "exchange_filter_read_performed": False,
        "target_runner_identity_hint": TARGET_RUNNER_IDENTITY_HINT,
        "target_deploy_root_hint": TARGET_DEPLOY_ROOT_HINT,
        "target_runner_identity_proven_in_p9cd": False,
        "target_deploy_root_proven_in_p9cd": False,
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
        "allowed_next_gate": P9CE_GATE,
        "allowed_next_gate_scope": P9CE_SCOPE,
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
        "source_p9cc_summary_sha256": evidence_file(p9cc_summary_path).get(
            "sha256", ""
        ),
        "baseline_target_plan_sha256": p9cc.get("baseline_target_plan_sha256"),
        "candidate_target_plan_sha256": p9cc.get("candidate_target_plan_sha256"),
        "only_distance_to_high_60_contribution_changed": p9cc.get(
            "only_distance_to_high_60_contribution_changed"
        ),
        "source_evidence": {
            "phase9cc_summary": evidence_file(p9cc_summary_path),
            "phase9cc_sufficiency_review": evidence_file(sufficiency_path),
            "phase9cc_future_gate_prerequisites": evidence_file(prereq_path),
            "phase9cc_non_authorization": evidence_file(matrix_path),
            "phase9cc_control_boundary": evidence_file(control_path),
            "project_profile": evidence_file(project_profile_path),
        },
        "output_files": output_files,
    }

    write_json(owner_path, owner_record)
    write_json(terms_path, gate_terms)
    write_json(non_auth_path, non_authorization)
    write_json(control_path_out, control)
    write_json(summary_path, summary)
    report_path.write_text(render_markdown(summary), encoding="utf-8")

    return summary, 0 if ready else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9CD Read-Only Fresh Remote Proof Collection Owner Gate",
        "",
        f"`Status: {summary['status']}`",
        "",
        "P9CD records the owner gate for allowing a future read-only fresh remote proof collection request. It does not execute that collection, SSH, read the account, read the order book, read exchange filters, collect fresh proofs, approve live orders, execute the candidate, enter the candidate into the actual executor path, replace target plans, mutate executor input, invoke supervisor/timer/remote paths, remote sync, remote execute, or submit orders.",
        "",
        "## Owner-Gate Boundary",
        "",
        "```text",
        "p9cd_read_only_fresh_remote_proof_collection_owner_gate_ready = "
        f"{str(bool(summary['p9cd_read_only_fresh_remote_proof_collection_owner_gate_ready'])).lower()}",
        "read_only_fresh_remote_proof_collection_owner_gate_approved_in_p9cd = "
        f"{str(bool(summary['read_only_fresh_remote_proof_collection_owner_gate_approved_in_p9cd'])).lower()}",
        "eligible_for_future_p9ce_read_only_collection_execution_gate = "
        f"{str(bool(summary['eligible_for_future_p9ce_read_only_collection_execution_gate'])).lower()}",
        "fresh_remote_proof_collection_execution_approved_in_p9cd = false",
        "fresh_remote_proof_collection_performed_in_p9cd = false",
        "fresh_remote_account_read_performed = false",
        "fresh_order_book_read_performed = false",
        "exchange_filter_read_performed = false",
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
        build_p9cd_read_only_fresh_remote_proof_collection_owner_gate(parse_args(argv))
    )
    print(f"status={summary['status']}")
    print(f"run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
