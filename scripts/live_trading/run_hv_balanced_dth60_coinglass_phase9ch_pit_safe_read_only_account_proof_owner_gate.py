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

from scripts.live_trading.hv_balanced_binance_usdm_pit_safe_account_proof_builder import (  # noqa: E402
    ACCOUNT_CONFIG_ENDPOINT,
    ACCOUNT_PROOF_CONTRACT_VERSION,
    ACCOUNT_V2_ENDPOINT,
    ACCOUNT_V3_ENDPOINT,
    API_RESTRICTIONS_ENDPOINT,
    BLOCKER_CAN_TRADE_FALSE,
    BLOCKER_CAN_TRADE_MISSING,
    CAN_TRADE_SOURCE,
    CONTRACT_VERSION as ACCOUNT_BUILDER_CONTRACT,
    OPEN_ORDERS_ENDPOINT,
    POSITION_MODE_ENDPOINT,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cf_review_p9ce_read_only_fresh_remote_proof_collection import (  # noqa: E402
    LIVE_ORDER_BLOCKER_ACCOUNT_CAN_TRADE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cg_define_live_order_readiness_blocker_resolution_scope import (  # noqa: E402
    CONTRACT_VERSION as P9CG_CONTRACT,
    DEFAULT_OUTPUT_PARENT as P9CG_PARENT,
    P9CH_GATE,
    P9CH_SCOPE,
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
    "hv_balanced_dth60_coinglass_phase9ch_pit_safe_read_only_account_proof_owner_gate.v1"
)
APPROVE_P9CH_DECISION = (
    "approve_p9ch_allow_pit_safe_read_only_account_proof_v2v3_owner_gate_only_no_collection_no_order_no_execution"
)
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/p9ch_pit_safe_read_only_account_proof_owner_gate"
)
P9CI_GATE = (
    "P9CI_execute_pit_safe_read_only_account_proof_v2v3_only_if_separately_requested"
)
P9CI_SCOPE = (
    "execute_pit_safe_read_only_account_proof_v2v3_no_order_no_candidate_no_timer_no_supervisor"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build the P9CH owner gate for allowing a later PIT-safe read-only "
            "Binance account proof collection request. P9CH is owner-gate-only: "
            "it does not SSH, read Binance, call order-test endpoints, collect "
            "fresh account proofs, run supervisor/timer paths, mutate executor "
            "input or target plans, execute the candidate, or submit orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9cg-summary", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9CH_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default=(
            "user_chat:p9ch_allow_pit_safe_read_only_account_proof_v2v3_owner_gate_only_if_separately_requested"
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


def latest_p9cg_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9cg_summary).strip():
        return resolve_path(args.phase9cg_summary)
    return latest_match(P9CG_PARENT, "*/summary.json")


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def source_output_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("output_files") or {}).get(key) or "")
    return resolve_path(text) if text.strip() else Path("")


def _replacement_blockers(payload: dict[str, Any]) -> list[str]:
    return [str(item) for item in list(payload.get("replacement_blockers") or [])]


def p9cg_summary_ready(summary: dict[str, Any]) -> bool:
    return (
        summary.get("contract_version") == P9CG_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9cg_live_order_readiness_blocker_resolution_scope_defined")
        is True
        and summary.get("p9cf_sufficient_for_p9cg_scope_definition") is True
        and summary.get("pit_safe_v2v3_account_proof_builder_defined") is True
        and summary.get("prior_p9ce_blocker") == LIVE_ORDER_BLOCKER_ACCOUNT_CAN_TRADE
        and _replacement_blockers(summary)
        == [BLOCKER_CAN_TRADE_MISSING, BLOCKER_CAN_TRADE_FALSE]
        and summary.get("can_trade_decision_source") == CAN_TRADE_SOURCE
        and summary.get("account_v3_canTrade_must_be_ignored_for_permission_decision")
        is True
        and summary.get("eligible_for_future_p9ch_account_proof_owner_gate") is True
        and summary.get("eligible_for_future_live_order_submission") is False
        and summary.get("eligible_for_future_candidate_execution") is False
        and summary.get("fresh_remote_proof_collection_performed_in_p9cg") is False
        and summary.get("fresh_remote_account_read_performed") is False
        and summary.get("fresh_order_book_read_performed") is False
        and summary.get("exchange_filter_read_performed") is False
        and summary.get("order_test_endpoint_called") is False
        and summary.get("live_order_gate_approved") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("candidate_execution_authorized") is False
        and summary.get("target_plan_replacement_authorized") is False
        and summary.get("executor_input_mutation_authorized") is False
        and summary.get("remote_execution_authorized") is False
        and summary.get("remote_sync_authorized") is False
        and summary.get("supervisor_invocation_authorized") is False
        and summary.get("timer_path_load_authorized") is False
        and summary.get("allowed_next_gate") == P9CH_GATE
        and summary.get("allowed_next_gate_scope") == P9CH_SCOPE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
        and int_zero(summary, "orders_submitted")
        and int_zero(summary, "orders_canceled")
        and int_zero(summary, "fill_count")
        and int_zero(summary, "trade_count")
    )


def p9cg_scope_ready(scope: dict[str, Any]) -> bool:
    required_endpoints = {
        ACCOUNT_V2_ENDPOINT,
        ACCOUNT_V3_ENDPOINT,
        ACCOUNT_CONFIG_ENDPOINT,
        POSITION_MODE_ENDPOINT,
        OPEN_ORDERS_ENDPOINT,
        API_RESTRICTIONS_ENDPOINT,
    }
    endpoints = set(str(item) for item in list(scope.get("required_read_only_endpoints") or []))
    forbidden = set(str(item) for item in list(scope.get("forbidden_in_p9cg") or []))
    return (
        scope.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cg_scope_definition.v1"
        and scope.get("status") == "ready"
        and not scope.get("blockers")
        and scope.get("scope") == "define_live_order_readiness_blocker_resolution_only"
        and scope.get("prior_blocker") == LIVE_ORDER_BLOCKER_ACCOUNT_CAN_TRADE
        and _replacement_blockers(scope)
        == [BLOCKER_CAN_TRADE_MISSING, BLOCKER_CAN_TRADE_FALSE]
        and scope.get("pit_safe_read_only_account_proof_builder_required") is True
        and scope.get("pit_safe_read_only_account_proof_contract")
        == ACCOUNT_PROOF_CONTRACT_VERSION
        and scope.get("account_proof_builder_contract") == ACCOUNT_BUILDER_CONTRACT
        and required_endpoints.issubset(endpoints)
        and scope.get("can_trade_decision_source") == CAN_TRADE_SOURCE
        and scope.get("account_v3_canTrade_must_be_ignored_for_permission_decision")
        is True
        and dict(scope.get("if_v2_canTrade_true") or {}).get("classification")
        == "prior_p9ce_false_or_missing_blocker_was_endpoint_schema_gap"
        and dict(scope.get("if_v2_canTrade_false") or {}).get("classification")
        == "account_side_permission_blocker"
        and {
            "live order submission",
            "candidate execution",
            "target-plan replacement",
            "executor-input mutation",
            "fresh remote account read",
            "order-test endpoint",
            "supervisor/timer invocation",
            "remote sync",
            "live config/operator/timer mutation",
        }.issubset(forbidden)
    )


def p9cg_builder_contract_ready(builder: dict[str, Any]) -> bool:
    permission = dict(builder.get("permission_field_contract") or {})
    side_effect = dict(builder.get("side_effect_contract") or {})
    source = dict(builder.get("builder_source") or {})
    return (
        builder.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cg_account_proof_builder_contract.v1"
        and builder.get("builder_contract_version") == ACCOUNT_BUILDER_CONTRACT
        and builder.get("account_proof_contract_version") == ACCOUNT_PROOF_CONTRACT_VERSION
        and source.get("exists") is True
        and bool(source.get("sha256"))
        and permission.get("can_trade_source") == CAN_TRADE_SOURCE
        and permission.get("account_v2_endpoint") == ACCOUNT_V2_ENDPOINT
        and permission.get("account_v3_endpoint") == ACCOUNT_V3_ENDPOINT
        and permission.get("account_v3_canTrade_ignored_for_permission_decision")
        is True
        and permission.get("split_missing_blocker") == BLOCKER_CAN_TRADE_MISSING
        and permission.get("split_false_blocker") == BLOCKER_CAN_TRADE_FALSE
        and side_effect.get("http_methods_allowed") == ["GET"]
        and int_zero(side_effect, "remote_files_written")
        and side_effect.get("remote_sync_performed") is False
        and int_zero(side_effect, "order_test_calls")
        and int_zero(side_effect, "orders_submitted")
        and int_zero(side_effect, "orders_canceled")
        and int_zero(side_effect, "fill_count")
        and int_zero(side_effect, "trade_count")
    )


def p9cg_remediation_ready(remediation: dict[str, Any]) -> bool:
    if_true = set(str(item) for item in list(remediation.get("if_v2_canTrade_true") or []))
    if_false = set(str(item) for item in list(remediation.get("if_v2_canTrade_false") or []))
    required_true = {
        "treat retained P9CE blocker as endpoint-schema proof bug",
        "rerun fresh proof using the PIT-safe v2/v3 account proof builder",
        "rerun retained review proving no live-order blocker remains",
    }
    required_false = {
        "do not proceed to live-order gate",
        "fix account/API-key permissions outside repo",
        "ensure Futures account is enabled",
        "ensure API key has Futures/trading permission",
        "ensure API key IP restriction includes 203.0.113.10",
        "recreate API key if it predates Futures-account enablement",
        "keep withdrawal permission disabled",
        "rerun fresh read-only proof after the account-side fix",
    }
    return (
        remediation.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cg_remediation_scope.v1"
        and required_true.issubset(if_true)
        and required_false.issubset(if_false)
    )


def p9cg_non_authorization_ready(matrix: dict[str, Any]) -> bool:
    authorizations = dict(matrix.get("authorizations") or {})
    return (
        matrix.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cg_non_authorization.v1"
        and authorizations.get("define_blocker_resolution_scope") is True
        and authorizations.get("allow_future_p9ch_account_proof_owner_gate") is True
        and authorizations.get("pit_safe_account_proof_collection") is False
        and authorizations.get("fresh_remote_account_read") is False
        and authorizations.get("fresh_order_book_read") is False
        and authorizations.get("exchange_filter_read") is False
        and authorizations.get("order_test_endpoint") is False
        and authorizations.get("remote_execution") is False
        and authorizations.get("remote_sync") is False
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
        and authorizations.get("stage_governance_change") is False
    )


def p9cg_control_ready(control: dict[str, Any]) -> bool:
    return (
        control.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cg_control_boundary.v1"
        and control.get("scope") == "blocker_resolution_scope_definition_only"
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


def build_account_proof_execution_gate_terms(
    run_id: str,
    p9cg_summary_path: Path,
    p9cg: dict[str, Any],
) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ch_account_proof_execution_gate_terms.v1",
        "run_id": run_id,
        "owner_gate_only": True,
        "source_p9cg_summary": evidence_file(p9cg_summary_path),
        "allowed_next_gate": P9CI_GATE,
        "allowed_next_gate_scope": P9CI_SCOPE,
        "allowed_next_gate_must_be_separately_requested": True,
        "pit_safe_read_only_account_proof_may_be_requested_next": True,
        "pit_safe_account_proof_collection_performed_in_p9ch": False,
        "required_read_only_endpoints": [
            ACCOUNT_V2_ENDPOINT,
            ACCOUNT_V3_ENDPOINT,
            ACCOUNT_CONFIG_ENDPOINT,
            POSITION_MODE_ENDPOINT,
            OPEN_ORDERS_ENDPOINT,
            API_RESTRICTIONS_ENDPOINT,
        ],
        "account_proof_contract": ACCOUNT_PROOF_CONTRACT_VERSION,
        "account_proof_builder_contract": ACCOUNT_BUILDER_CONTRACT,
        "can_trade_decision_source": CAN_TRADE_SOURCE,
        "account_v3_canTrade_must_be_ignored_for_permission_decision": True,
        "replacement_blockers": [
            BLOCKER_CAN_TRADE_MISSING,
            BLOCKER_CAN_TRADE_FALSE,
        ],
        "required_future_side_effect_contract": {
            "http_methods_allowed": ["GET"],
            "remote_files_written_must_equal": 0,
            "remote_sync_performed_must_equal": False,
            "order_test_calls_must_equal": 0,
            "orders_submitted_must_equal": 0,
            "orders_canceled_must_equal": 0,
            "fill_count_must_equal": 0,
            "trade_count_must_equal": 0,
        },
        "required_future_proofs": [
            "fresh v2 account read",
            "fresh v3 account read",
            "fresh account config read",
            "fresh position mode read",
            "fresh open orders read",
            "fresh api restrictions read",
            "pre/post position fingerprint stable",
            "pre/post open-order fingerprint stable",
            "pre/post balance fingerprint stable",
            "pre/post fill/trade delta zero",
            "zero order/cancel/fill/trade delta",
        ],
        "classification_contract": {
            "if_v2_canTrade_true": "prior_p9ce_false_or_missing_blocker_was_endpoint_schema_gap",
            "if_v2_canTrade_false": "account_side_permission_blocker",
            "if_v2_canTrade_missing": BLOCKER_CAN_TRADE_MISSING,
        },
        "source_p9cg_prior_blocker": p9cg.get("prior_p9ce_blocker"),
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
    }


def build_future_p9ci_acceptance_contract(run_id: str) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ch_future_p9ci_acceptance_contract.v1",
        "run_id": run_id,
        "future_gate": P9CI_GATE,
        "future_gate_scope": P9CI_SCOPE,
        "future_gate_must_be_separately_requested": True,
        "p9ci_must_fail_closed_unless": {
            "owner_request_is_separate_and_explicit": True,
            "project_stage_is_stage3": True,
            "p9ch_summary_ready": True,
            "read_only_endpoints_are_v2v3_account_contract": True,
            "canTrade_decision_source_is_fapi_v2_account": True,
            "account_v3_canTrade_is_ignored_for_permission_decision": True,
            "pre_post_fingerprints_are_stable": True,
            "zero_order_cancel_fill_trade_delta": True,
            "no_order_test_endpoint_call": True,
            "no_timer_supervisor_executor_or_target_plan_mutation": True,
        },
        "p9ci_must_report": {
            "canTrade_missing_from_endpoint": BLOCKER_CAN_TRADE_MISSING,
            "canTrade_false": BLOCKER_CAN_TRADE_FALSE,
            "canTrade_true_clears_prior_false_or_missing_only_after_review": True,
        },
        "p9ci_does_not_authorize": [
            "live order submission",
            "candidate execution",
            "target-plan replacement",
            "executor-input mutation",
            "supervisor/timer invocation",
            "remote sync",
            "live config/operator/timer mutation",
            "stage governance change",
        ],
    }


def build_p9ch_pit_safe_read_only_account_proof_owner_gate(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    now = now_fn()
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9ch" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    p9cg_summary_path = latest_p9cg_summary(args)
    p9cg = load_optional(p9cg_summary_path)
    scope_path = source_output_path(p9cg, "blocker_resolution_scope")
    builder_path = source_output_path(p9cg, "pit_safe_account_proof_builder_contract")
    remediation_path = source_output_path(p9cg, "remediation_runbook")
    p9cg_matrix_path = source_output_path(p9cg, "non_authorization")
    p9cg_control_path = source_output_path(p9cg, "control_boundary_readback")
    scope = load_optional(scope_path)
    builder_contract = load_optional(builder_path)
    remediation = load_optional(remediation_path)
    p9cg_matrix = load_optional(p9cg_matrix_path)
    p9cg_control = load_optional(p9cg_control_path)
    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)

    owner_decision_ok = str(args.owner_decision) == APPROVE_P9CH_DECISION
    checks = {
        "owner_decision_p9ch_owner_gate_recorded": owner_decision_ok,
        "project_profile_exists": bool(project_profile),
        "current_stage_is_stage3": str(project_profile.get("current_stage") or "")
        == "stage_3_human_approved_execution",
        "p9cg_summary_exists": bool(p9cg),
        "p9cg_summary_ready_for_p9ch_owner_gate": p9cg_summary_ready(p9cg),
        "p9cg_scope_definition_ready": p9cg_scope_ready(scope),
        "p9cg_builder_contract_ready": p9cg_builder_contract_ready(builder_contract),
        "p9cg_remediation_scope_ready": p9cg_remediation_ready(remediation),
        "p9cg_non_authorization_ready": p9cg_non_authorization_ready(p9cg_matrix),
        "p9cg_control_boundary_ready": p9cg_control_ready(p9cg_control),
    }
    blockers = [key for key, value in checks.items() if not value]
    ready = not blockers

    owner_record = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ch_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "allow_future_pit_safe_v2v3_read_only_account_proof_gate_only_no_collection_no_order_no_execution",
        "decision_effect": (
            "allow_future_p9ci_pit_safe_read_only_account_proof_gate_if_separately_requested"
            if owner_decision_ok
            else "none"
        ),
        "recorded_at_utc": iso_z(now),
        "pit_safe_read_only_account_proof_owner_gate_approved": owner_decision_ok,
        "future_p9ci_account_proof_gate_may_be_requested": owner_decision_ok,
        "pit_safe_account_proof_collection_approved_in_p9ch": False,
        "fresh_remote_account_read_approved_in_p9ch": False,
        "order_test_endpoint_approved": False,
        "remote_execution_approved": False,
        "live_order_gate_approved": False,
        "candidate_execution_approved": False,
        "target_plan_replacement_approved": False,
        "executor_input_mutation_approved": False,
        "live_order_submission_approved": False,
    }
    gate_terms = build_account_proof_execution_gate_terms(
        run_id,
        p9cg_summary_path,
        p9cg,
    )
    future_contract = build_future_p9ci_acceptance_contract(run_id)
    non_authorization = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ch_non_authorization.v1",
        "run_id": run_id,
        "authorizations": {
            "allow_future_p9ci_account_proof_gate_request": ready,
            "execute_pit_safe_read_only_account_proof_in_p9ch": False,
            "pit_safe_account_proof_collection": False,
            "fresh_remote_account_read": False,
            "fresh_order_book_read": False,
            "exchange_filter_read": False,
            "order_test_endpoint": False,
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
        "contract_version": "hv_balanced_dth60_coinglass_phase9ch_control_boundary.v1",
        "run_id": run_id,
        "scope": "pit_safe_read_only_account_proof_owner_gate_only",
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
    terms_path = proof_root / "account_proof_execution_gate_terms.json"
    future_contract_path = proof_root / "future_p9ci_acceptance_contract.json"
    non_auth_path = proof_root / "non_authorization.json"
    control_path_out = proof_root / "control_boundary_readback.json"
    summary_path = root / "summary.json"
    report_path = root / "p9ch_pit_safe_read_only_account_proof_owner_gate.md"
    output_files = {
        "summary": str(summary_path),
        "owner_decision_record": str(owner_path),
        "account_proof_execution_gate_terms": str(terms_path),
        "future_p9ci_acceptance_contract": str(future_contract_path),
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
        "p9ch_pit_safe_read_only_account_proof_owner_gate_ready": ready,
        "p9cg_sufficient_for_p9ch_owner_gate": p9cg_summary_ready(p9cg),
        "pit_safe_read_only_account_proof_owner_gate_approved_in_p9ch": ready,
        "eligible_for_future_p9ci_account_proof_execution_gate": ready,
        "eligible_for_future_live_order_submission": False,
        "eligible_for_future_candidate_execution": False,
        "eligible_for_future_pit_safe_account_proof_without_separate_request": False,
        "fresh_remote_proof_collection_execution_approved_in_p9ch": False,
        "pit_safe_account_proof_collection_performed_in_p9ch": False,
        "fresh_remote_account_read_performed": False,
        "fresh_order_book_read_performed": False,
        "exchange_filter_read_performed": False,
        "order_test_endpoint_called": False,
        "live_order_gate_approved": False,
        "live_order_submission_authorized": False,
        "candidate_execution_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "remote_execution_authorized": False,
        "remote_sync_authorized": False,
        "supervisor_invocation_authorized": False,
        "timer_path_load_authorized": False,
        "can_trade_decision_source": CAN_TRADE_SOURCE,
        "prior_p9ce_blocker": LIVE_ORDER_BLOCKER_ACCOUNT_CAN_TRADE,
        "replacement_blockers": [
            BLOCKER_CAN_TRADE_MISSING,
            BLOCKER_CAN_TRADE_FALSE,
        ],
        "account_v3_canTrade_must_be_ignored_for_permission_decision": True,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
        "allowed_next_gate": P9CI_GATE,
        "allowed_next_gate_scope": P9CI_SCOPE,
        "allowed_next_gate_must_be_separately_requested": True,
        "source_evidence": {
            "phase9cg_summary": evidence_file(p9cg_summary_path),
            "p9cg_blocker_resolution_scope": evidence_file(scope_path),
            "p9cg_builder_contract": evidence_file(builder_path),
            "p9cg_remediation_runbook": evidence_file(remediation_path),
            "p9cg_non_authorization": evidence_file(p9cg_matrix_path),
            "p9cg_control_boundary": evidence_file(p9cg_control_path),
            "project_profile": evidence_file(project_profile_path),
        },
        "checks": checks,
        "output_files": output_files,
    }

    write_json(owner_path, owner_record)
    write_json(terms_path, gate_terms)
    write_json(future_contract_path, future_contract)
    write_json(non_auth_path, non_authorization)
    write_json(control_path_out, control)
    write_json(summary_path, summary)
    report_path.write_text(render_markdown(summary), encoding="utf-8")
    return summary, 0 if ready else 2


def build_phase9ch(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    return build_p9ch_pit_safe_read_only_account_proof_owner_gate(
        args,
        now_fn=now_fn,
    )


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9CH PIT-Safe Account Proof Owner Gate",
        "",
        f"`Status: {summary['status']}`",
        "",
        "P9CH is owner-gate-only. It allows only a future separately requested P9CI PIT-safe v2/v3 read-only account proof gate. It does not SSH, read Binance, call order-test endpoints, collect fresh account proofs, run supervisor/timer paths, mutate live state, execute the candidate, replace target plans, or submit orders.",
        "",
        "## Gate Result",
        "",
        "```text",
        "p9ch_pit_safe_read_only_account_proof_owner_gate_ready = "
        f"{str(bool(summary['p9ch_pit_safe_read_only_account_proof_owner_gate_ready'])).lower()}",
        "p9cg_sufficient_for_p9ch_owner_gate = "
        f"{str(bool(summary['p9cg_sufficient_for_p9ch_owner_gate'])).lower()}",
        "eligible_for_future_p9ci_account_proof_execution_gate = "
        f"{str(bool(summary['eligible_for_future_p9ci_account_proof_execution_gate'])).lower()}",
        "pit_safe_account_proof_collection_performed_in_p9ch = false",
        "fresh_remote_account_read_performed = false",
        "order_test_endpoint_called = false",
        "live_order_submission_authorized = false",
        "orders_submitted = 0",
        "fill_count = 0",
        "```",
        "",
        "## Account Proof Contract",
        "",
        "```text",
        f"can_trade_decision_source = {summary['can_trade_decision_source']}",
        "replacement_blockers = "
        + ", ".join(summary["replacement_blockers"]),
        "account_v3_canTrade_must_be_ignored_for_permission_decision = true",
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
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_phase9ch(parse_args(argv))
    print(f"status={summary['status']}")
    print(f"summary={summary['output_files']['summary']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    print(
        "p9ch_pit_safe_read_only_account_proof_owner_gate_ready="
        + str(bool(summary["p9ch_pit_safe_read_only_account_proof_owner_gate_ready"])).lower()
    )
    print(
        "eligible_for_future_p9ci_account_proof_execution_gate="
        + str(bool(summary["eligible_for_future_p9ci_account_proof_execution_gate"])).lower()
    )
    print("pit_safe_account_proof_collection_performed_in_p9ch=false")
    print(f"can_trade_decision_source={summary['can_trade_decision_source']}")
    print("replacement_blockers=" + ",".join(summary["replacement_blockers"]))
    print("orders_submitted=0")
    print("fill_count=0")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
