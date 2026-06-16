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
    ACCOUNT_PROOF_CONTRACT_VERSION,
    CAN_TRADE_SOURCE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cm_review_p9cl_post_account_blocker_live_order_readiness_review_package import (  # noqa: E402
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
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9co_post_account_blocker_read_only_fresh_remote_proof_collection import (  # noqa: E402
    CONTRACT_VERSION as P9CO_CONTRACT,
    DEFAULT_OUTPUT_PARENT as P9CO_PARENT,
    P9CP_GATE,
    P9CP_SCOPE,
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
    "hv_balanced_dth60_coinglass_phase9cp_review_p9co_post_account_blocker_read_only_fresh_remote_proof_collection.v1"
)
APPROVE_P9CP_DECISION = (
    "approve_p9cp_review_p9co_post_account_blocker_read_only_fresh_remote_proof_collection_only_no_remote_no_order_no_execution"
)
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/p9cp_review_p9co_post_account_blocker_read_only_fresh_remote_proof_collection"
)
P9CQ_GATE = (
    "P9CQ_define_final_owner_live_order_gate_scope_after_p9co_only_if_separately_requested"
)
P9CQ_SCOPE = (
    "define_final_owner_live_order_gate_scope_after_p9co_no_order_no_candidate_no_executor_or_timer_change"
)
EXPECTED_P9CO_ARTIFACT_KEYS = {
    "account_delta_acceptance",
    "account_history_delta_acceptance",
    "control_boundary_readback",
    "exchange_filter_readback",
    "fresh_order_book",
    "kill_switch_rollback_readback",
    "market_proof_collection_delta_acceptance",
    "no_order_candidate_target_plan_replacement_dry_run_summary",
    "non_authorization",
    "pit_safe_v2v3_account_proof",
    "proof_status_matrix",
    "remote_runner_identity_readback",
    "remote_stdout_account_collector_sanitized",
    "remote_stdout_market_collector",
}
P9CO_COMMAND_LABELS = [
    "pre_control_snapshot",
    "remote_stdout_pit_safe_v2v3_account_collector",
    "remote_stdout_market_and_fingerprint_collector",
    "post_control_snapshot",
]
FORBIDDEN_COMMAND_FRAGMENTS = [
    "scp ",
    "/fapi/v1/order/test",
    "systemctl start",
    "systemctl enable",
    "systemctl stop",
    "systemctl disable",
    "systemctl restart",
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Review retained P9CO post-account-blocker read-only fresh remote "
            "proof collection evidence. P9CP is local retained-evidence review "
            "only: it does not SSH, read Binance, collect fresh proofs, call "
            "order-test endpoints, run supervisor/timer paths, execute the "
            "candidate, mutate executor input or target plans, remote sync, "
            "cancel orders, or submit orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9co-summary", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9CP_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default=(
            "user_chat:p9cp_review_p9co_post_account_blocker_read_only_fresh_remote_proof_collection_only_if_separately_requested"
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


def latest_p9co_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9co_summary).strip():
        return resolve_path(args.phase9co_summary)
    return latest_match(P9CO_PARENT, "*/summary.json")


def source_output_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("output_files") or {}).get(key) or "")
    return resolve_path(text) if text.strip() else Path("")


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def int_equals(payload: dict[str, Any], key: str, expected: int) -> bool:
    try:
        return int(payload.get(key)) == expected
    except (TypeError, ValueError):
        return False


def p9co_summary_ready(summary: dict[str, Any]) -> bool:
    gates = dict(summary.get("gates") or {})
    return (
        summary.get("contract_version") == P9CO_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get(
            "p9co_post_account_blocker_read_only_fresh_remote_proof_collection_ready"
        )
        is True
        and summary.get("p9cn_sufficient_for_p9co_execution") is True
        and summary.get("fresh_remote_proof_collection_performed_in_p9co") is True
        and summary.get("pit_safe_v2v3_account_proof_ready") is True
        and summary.get("fresh_remote_account_read_performed") is True
        and summary.get("fresh_order_book_read_performed") is True
        and summary.get("exchange_filter_read_performed") is True
        and summary.get("order_test_endpoint_called") is False
        and summary.get("remote_execution_performed") is True
        and summary.get("remote_execution_scope")
        == "stdout_read_only_account_market_collectors_only"
        and int_equals(summary, "remote_files_written", 0)
        and summary.get("remote_sync_performed") is False
        and summary.get("target_runner_identity_proven_in_p9co") is True
        and summary.get("target_deploy_root_proven_in_p9co") is True
        and summary.get("can_trade_decision_source") == CAN_TRADE_SOURCE
        and summary.get("can_trade_pre") is True
        and summary.get("can_trade_post") is True
        and summary.get("account_v2_has_canTrade_pre") is True
        and summary.get("account_v2_has_canTrade_post") is True
        and summary.get("account_v3_canTrade_ignored_for_permission_decision")
        is True
        and summary.get("account_blocker_cleared_by_p9co") is True
        and list(summary.get("live_order_readiness_blockers") or []) == []
        and summary.get("position_fingerprint_stable") is True
        and summary.get("open_order_fingerprint_stable") is True
        and summary.get("balance_fingerprint_stable") is True
        and summary.get("open_order_count_zero_pre_post") is True
        and summary.get("order_cancel_fill_trade_delta_zero") is True
        and summary.get("remote_control_boundary_unchanged") is True
        and summary.get("open_position_count_pre") == summary.get("open_position_count_post")
        and int_equals(summary, "open_order_count_pre", 0)
        and int_equals(summary, "open_order_count_post", 0)
        and summary.get("same_risk_paired_target_plan_binding") is True
        and summary.get("distance_to_high_60_only_delta") is True
        and summary.get("no_order_candidate_target_plan_replacement_dry_run_ready")
        is True
        and bool(summary.get("baseline_target_plan_sha256"))
        and bool(summary.get("candidate_target_plan_sha256"))
        and summary.get("baseline_target_plan_sha256")
        != summary.get("candidate_target_plan_sha256")
        and summary.get("only_distance_to_high_60_contribution_changed") is True
        and summary.get("read_only_fresh_proofs_ready") is True
        and summary.get("live_order_gate_approval_collected") is False
        and summary.get("live_order_gate_approved") is False
        and summary.get("eligible_for_future_live_order_submission") is False
        and summary.get("eligible_for_future_candidate_execution") is False
        and summary.get("candidate_enter_executor_target_plan_path_authorized")
        is False
        and summary.get("candidate_execution_authorized") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("target_plan_replacement_authorized") is False
        and summary.get("executor_input_mutation_authorized") is False
        and summary.get("supervisor_invocation_authorized") is False
        and summary.get("timer_path_load_authorized") is False
        and summary.get("production_timer_service_load_authorized") is False
        and summary.get("live_config_mutation_authorized") is False
        and summary.get("operator_state_mutation_authorized") is False
        and summary.get("timer_or_service_mutation_authorized") is False
        and int_zero(summary, "orders_submitted")
        and int_zero(summary, "orders_canceled")
        and int_zero(summary, "fill_count")
        and int_zero(summary, "trade_count")
        and summary.get("canary_symbol") == CANARY_SYMBOL
        and summary.get("canary_side") == CANARY_SIDE
        and float(summary.get("risk_ceiling_usdt") or 0) == DEFAULT_RISK_CEILING_USDT
        and float(summary.get("max_notional_usdt") or 0) == DEFAULT_MAX_NOTIONAL_USDT
        and int(summary.get("max_orders_per_cycle") or 0) == DEFAULT_MAX_ORDERS_PER_CYCLE
        and int(summary.get("max_symbols_per_cycle") or 0) == DEFAULT_MAX_SYMBOLS_PER_CYCLE
        and summary.get("order_type") == DEFAULT_ORDER_TYPE
        and summary.get("time_in_force") == DEFAULT_TIME_IN_FORCE
        and summary.get("market_orders_allowed") is False
        and summary.get("allowed_next_gate") == P9CP_GATE
        and summary.get("allowed_next_gate_scope") == P9CP_SCOPE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
        and bool(gates)
        and all(value is True for value in gates.values())
    )


def proof_manifest_ready(manifest: dict[str, Any]) -> bool:
    artifacts = dict(manifest.get("artifacts") or {})
    return (
        manifest.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9co_proof_artifact_manifest.v1"
        and int(manifest.get("artifact_count") or 0) == len(EXPECTED_P9CO_ARTIFACT_KEYS)
        and set(artifacts) == EXPECTED_P9CO_ARTIFACT_KEYS
        and all(
            dict(entry).get("exists") is True and bool(dict(entry).get("sha256"))
            for entry in artifacts.values()
        )
        and dict(manifest.get("self") or {}).get("exists") is True
        and bool(dict(manifest.get("self") or {}).get("sha256"))
    )


def proof_status_matrix_ready(matrix: dict[str, Any]) -> bool:
    rows = {str(row.get("proof_id")): dict(row) for row in list(matrix.get("proofs") or [])}
    return (
        matrix.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9co_proof_status_matrix.v1"
        and matrix.get("read_only_fresh_proofs_ready") is True
        and matrix.get("live_order_gate_approval_collected") is False
        and matrix.get("p9co_satisfies_live_order_gate") is False
        and set(rows) == set(EXPECTED_PROOFS)
        and all(
            rows[key].get("status") == "ready"
            and int(rows[key].get("max_age_seconds") or 0) == max_age
            for key, max_age in EXPECTED_PROOFS.items()
            if key != "final_owner_live_order_gate_approval"
        )
        and rows["final_owner_live_order_gate_approval"].get("status")
        == "not_collected_by_design"
        and rows["final_owner_live_order_gate_approval"].get("live_order_gate_approved")
        is False
        and int(rows["final_owner_live_order_gate_approval"].get("max_age_seconds") or 0)
        == EXPECTED_PROOFS["final_owner_live_order_gate_approval"]
    )


def account_proof_ready(proof: dict[str, Any]) -> bool:
    checks = dict(proof.get("checks") or {})
    return (
        proof.get("contract_version") == ACCOUNT_PROOF_CONTRACT_VERSION
        and proof.get("pit_safe_read_only_account_proof_ready") is True
        and not proof.get("blockers")
        and proof.get("can_trade_source") == CAN_TRADE_SOURCE
        and proof.get("can_trade_pre") is True
        and proof.get("can_trade_post") is True
        and proof.get("account_v2_has_canTrade_pre") is True
        and proof.get("account_v2_has_canTrade_post") is True
        and proof.get("account_v3_canTrade_ignored_for_permission_decision") is True
        and proof.get("eligible_to_clear_p9cf_account_can_trade_blocker") is True
        and proof.get("account_permission_source_corrected") is True
        and list(proof.get("live_order_readiness_blockers") or []) == []
        and int_zero(proof, "orders_submitted")
        and int_zero(proof, "orders_canceled")
        and int_zero(proof, "fill_count")
        and bool(checks)
        and all(value is True for value in checks.values())
    )


def account_delta_ready(delta: dict[str, Any]) -> bool:
    return (
        delta.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9ci_account_delta_acceptance.v1"
        and delta.get("position_fingerprint_stable") is True
        and delta.get("open_order_fingerprint_stable") is True
        and delta.get("balance_fingerprint_stable") is True
        and delta.get("position_delta_zero_or_stable") is True
        and delta.get("open_order_delta_zero_or_stable") is True
        and delta.get("balance_delta_zero_or_stable") is True
        and delta.get("open_order_count_zero_pre_post") is True
        and delta.get("open_position_count_pre") == delta.get("open_position_count_post")
        and int_equals(delta, "open_order_count_pre", 0)
        and int_equals(delta, "open_order_count_post", 0)
        and delta.get("side_effects_zero") is True
        and int_zero(delta, "orders_submitted")
        and int_zero(delta, "orders_canceled")
        and int_zero(delta, "fill_count")
        and int_zero(delta, "trade_count")
    )


def history_delta_ready(delta: dict[str, Any]) -> bool:
    return (
        delta.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9ci_history_delta_acceptance.v1"
        and delta.get("order_history_fingerprint_stable") is True
        and delta.get("trade_history_fingerprint_stable") is True
        and delta.get("order_cancel_fill_trade_delta_zero") is True
        and delta.get("order_history_hash_pre") == delta.get("order_history_hash_post")
        and delta.get("trade_history_hash_pre") == delta.get("trade_history_hash_post")
        and int_zero(delta, "orders_submitted")
        and int_zero(delta, "orders_canceled")
        and int_zero(delta, "fill_count")
        and int_zero(delta, "trade_count")
        and len(delta.get("proof_symbols") or []) >= 1
    )


def market_delta_ready(delta: dict[str, Any]) -> bool:
    return (
        delta.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9ce_delta_acceptance.v1"
        and delta.get("position_fingerprint_stable") is True
        and delta.get("open_order_fingerprint_stable") is True
        and delta.get("balance_fingerprint_stable") is True
        and delta.get("fill_trade_fingerprint_stable") is True
        and delta.get("position_delta_zero_or_stable") is True
        and delta.get("balance_delta_zero_or_stable") is True
        and delta.get("order_cancel_fill_trade_delta_zero") is True
        and delta.get("open_position_count_pre") == delta.get("open_position_count_post")
        and int_equals(delta, "open_order_count_pre", 0)
        and int_equals(delta, "open_order_count_post", 0)
        and delta.get("order_history_hash_pre") == delta.get("order_history_hash_post")
        and delta.get("trade_history_hash_pre") == delta.get("trade_history_hash_post")
        and int_zero(delta, "orders_submitted")
        and int_zero(delta, "orders_canceled")
        and int_zero(delta, "fill_count")
        and int_zero(delta, "trade_count")
    )


def fresh_book_ready(book: dict[str, Any]) -> bool:
    payload = dict(book.get("book") or {})
    return (
        book.get("status") == "ready"
        and book.get("symbol") == CANARY_SYMBOL
        and book.get("endpoint") == "/fapi/v1/depth"
        and book.get("method") == "GET"
        and bool(book.get("book_hash"))
        and payload.get("symbol") == CANARY_SYMBOL
        and bool(payload.get("best_bid"))
        and bool(payload.get("best_ask"))
    )


def exchange_filter_ready(filters: dict[str, Any]) -> bool:
    symbols = list(filters.get("symbols") or [])
    by_symbol = {str(row.get("symbol")): dict(row) for row in symbols if isinstance(row, dict)}
    return (
        filters.get("status") == "ready"
        and filters.get("endpoint") == "/fapi/v1/exchangeInfo"
        and filters.get("method") == "GET"
        and bool(filters.get("filters_hash"))
        and int(filters.get("symbol_count") or 0) >= 1
        and CANARY_SYMBOL in by_symbol
        and by_symbol[CANARY_SYMBOL].get("status") == "TRADING"
        and by_symbol[CANARY_SYMBOL].get("contractType") == "PERPETUAL"
        and bool(by_symbol[CANARY_SYMBOL].get("filters"))
    )


def no_order_dry_run_ready(dry_run: dict[str, Any], summary: dict[str, Any]) -> bool:
    return (
        dry_run.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9bv_no_order_candidate_target_plan_replacement_dry_run.v1"
        and dry_run.get("status") == "ready"
        and not dry_run.get("blockers")
        and dry_run.get("p9bv_no_order_replacement_dry_run_ready") is True
        and dry_run.get("candidate_target_plan_replacement_semantics_proven") is True
        and dry_run.get("exact_p9bu_terms_applied") is True
        and dry_run.get("same_timestamp_context") is True
        and dry_run.get("same_risk_inputs") is True
        and dry_run.get("candidate_plan_differs_from_baseline") is True
        and dry_run.get("simulated_executor_input_replacement_matches_candidate") is True
        and dry_run.get("actual_executor_input_changed") is False
        and dry_run.get("actual_target_plan_replaced") is False
        and dry_run.get("only_distance_to_high_60_contribution_changed") is True
        and int(dry_run.get("changed_symbol_count") or 0) == 1
        and int(dry_run.get("order_intent_preview_count") or 0) == 1
        and dry_run.get("baseline_target_plan_sha256")
        == summary.get("baseline_target_plan_sha256")
        and dry_run.get("candidate_target_plan_sha256")
        == summary.get("candidate_target_plan_sha256")
        and dry_run.get("candidate_enter_executor_target_plan_path_authorized")
        is False
        and dry_run.get("candidate_execution_authorized") is False
        and dry_run.get("live_order_submission_authorized") is False
        and dry_run.get("target_plan_replacement_authorized") is False
        and dry_run.get("executor_input_mutation_authorized") is False
        and int_zero(dry_run, "orders_submitted")
        and int_zero(dry_run, "orders_canceled")
        and int_zero(dry_run, "fill_count")
        and int_zero(dry_run, "trade_count")
    )


def kill_switch_rollback_ready(readback: dict[str, Any]) -> bool:
    return (
        readback.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9co_kill_switch_rollback_readback.v1"
        and readback.get("remote_control_boundary_unchanged") is True
        and readback.get("kill_switch_or_operator_state_mutated_by_p9co") is False
        and readback.get("remote_sync_performed") is False
        and int_equals(readback, "remote_files_written", 0)
        and readback.get("supervisor_invoked") is False
        and readback.get("timer_path_invoked") is False
        and readback.get("candidate_executed") is False
        and readback.get("executor_input_mutated") is False
        and readback.get("target_plan_replaced") is False
        and dict(readback.get("pre_control_snapshot") or {}).get("exists") is True
        and dict(readback.get("post_control_snapshot") or {}).get("exists") is True
    )


def p9co_non_authorization_ready(matrix: dict[str, Any]) -> bool:
    authorizations = dict(matrix.get("authorizations") or {})
    return (
        matrix.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9co_non_authorization.v1"
        and authorizations.get("p9co_post_account_blocker_read_only_fresh_remote_proof_collection")
        is True
        and authorizations.get("remote_stdout_read_only_account_market_collection")
        is True
        and authorizations.get("order_test_endpoint") is False
        and authorizations.get("remote_files_written") is False
        and authorizations.get("remote_sync") is False
        and authorizations.get("supervisor_invocation") is False
        and authorizations.get("timer_path_load") is False
        and authorizations.get("production_timer_service_load") is False
        and authorizations.get("candidate_execution") is False
        and authorizations.get("live_order_submission") is False
        and authorizations.get("target_plan_replacement") is False
        and authorizations.get("executor_input_mutation") is False
        and authorizations.get("live_config_mutation") is False
        and authorizations.get("operator_state_mutation") is False
        and authorizations.get("timer_or_service_mutation") is False
        and authorizations.get("stage_governance_change") is False
    )


def p9co_control_ready(control: dict[str, Any]) -> bool:
    return (
        control.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9co_control_boundary.v1"
        and control.get("scope")
        == "post_account_blocker_read_only_fresh_remote_proof_collection_stdout_only"
        and control.get("ssh_invoked") is True
        and control.get("remote_network_connection_performed") is True
        and control.get("remote_execution_scope")
        == "stdout_read_only_account_market_collectors_only"
        and int_equals(control, "remote_files_written", 0)
        and control.get("remote_sync_performed") is False
        and control.get("fresh_remote_account_read_performed") is True
        and control.get("fresh_order_book_read_performed") is True
        and control.get("exchange_filter_read_performed") is True
        and control.get("order_test_endpoint_called") is False
        and control.get("entered_timer_path") is False
        and control.get("ran_supervisor") is False
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


def command_records_ready(records: dict[str, Any]) -> bool:
    commands = [dict(item) for item in list(records.get("commands") or [])]
    command_text = "\n".join(" ".join(str(part) for part in command.get("args") or []) for command in commands)
    return (
        [command.get("label") for command in commands] == P9CO_COMMAND_LABELS
        and all(int(command.get("returncode", -1)) == 0 for command in commands)
        and all(bool(command.get("stdout_sha256")) for command in commands)
        and all(fragment not in command_text for fragment in FORBIDDEN_COMMAND_FRAGMENTS)
    )


def build_sufficiency_review(
    *,
    checks: dict[str, bool],
    p9co: dict[str, Any],
    ready: bool,
) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cp_p9co_sufficiency_review.v1",
        "review_only": True,
        "p9co_retained_evidence_sufficient_for_p9cp_review": ready,
        "p9co_read_only_fresh_proofs_sufficient_for_next_scope_gate": ready,
        "p9co_sufficient_for_live_order_submission": False,
        "p9co_sufficient_for_candidate_execution": False,
        "final_owner_live_order_gate_approval_collected": False,
        "final_owner_live_order_gate_approval_required_next": True,
        "eligible_for_future_p9cq_scope_definition": ready,
        "future_gate": P9CQ_GATE,
        "future_gate_scope": P9CQ_SCOPE,
        "future_gate_must_be_separately_requested": True,
        "read_only_fresh_proofs_ready": p9co.get("read_only_fresh_proofs_ready") is True,
        "account_blocker_cleared_by_p9co": p9co.get("account_blocker_cleared_by_p9co") is True,
        "live_order_readiness_blockers_after_p9co": list(
            p9co.get("live_order_readiness_blockers") or []
        ),
        "checks": checks,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
    }


def build_phase9cp(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    now = now_fn()
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9cp" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    p9co_path = latest_p9co_summary(args)
    p9co = load_optional(p9co_path)
    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)
    paths = {
        key: source_output_path(p9co, key)
        for key in [
            "proof_artifact_manifest",
            "proof_status_matrix",
            "pit_safe_v2v3_account_proof",
            "account_delta_acceptance",
            "account_history_delta_acceptance",
            "market_proof_collection_delta_acceptance",
            "fresh_order_book",
            "exchange_filter_readback",
            "no_order_candidate_target_plan_replacement_dry_run_summary",
            "kill_switch_rollback_readback",
            "non_authorization",
            "control_boundary_readback",
            "command_records",
        ]
    }
    loaded = {key: load_optional(path) for key, path in paths.items()}
    owner_decision_ok = str(args.owner_decision) == APPROVE_P9CP_DECISION
    checks = {
        "owner_decision_p9cp_review_only_recorded": owner_decision_ok,
        "project_profile_exists": bool(project_profile),
        "current_stage_is_stage3": str(project_profile.get("current_stage") or "")
        == "stage_3_human_approved_execution",
        "p9co_summary_exists": bool(p9co),
        "p9co_summary_ready_for_p9cp_review": p9co_summary_ready(p9co),
        "p9co_proof_manifest_ready": proof_manifest_ready(
            loaded["proof_artifact_manifest"]
        ),
        "p9co_proof_status_matrix_ready": proof_status_matrix_ready(
            loaded["proof_status_matrix"]
        ),
        "pit_safe_v2v3_account_proof_ready": account_proof_ready(
            loaded["pit_safe_v2v3_account_proof"]
        ),
        "account_delta_acceptance_ready": account_delta_ready(
            loaded["account_delta_acceptance"]
        ),
        "account_history_delta_acceptance_ready": history_delta_ready(
            loaded["account_history_delta_acceptance"]
        ),
        "market_proof_collection_delta_acceptance_ready": market_delta_ready(
            loaded["market_proof_collection_delta_acceptance"]
        ),
        "fresh_order_book_ready": fresh_book_ready(loaded["fresh_order_book"]),
        "exchange_filter_readback_ready": exchange_filter_ready(
            loaded["exchange_filter_readback"]
        ),
        "no_order_candidate_target_plan_replacement_dry_run_ready": no_order_dry_run_ready(
            loaded["no_order_candidate_target_plan_replacement_dry_run_summary"],
            p9co,
        ),
        "kill_switch_rollback_readback_ready": kill_switch_rollback_ready(
            loaded["kill_switch_rollback_readback"]
        ),
        "p9co_non_authorization_ready": p9co_non_authorization_ready(
            loaded["non_authorization"]
        ),
        "p9co_control_boundary_ready": p9co_control_ready(
            loaded["control_boundary_readback"]
        ),
        "p9co_command_records_ready": command_records_ready(
            loaded["command_records"]
        ),
    }
    blockers = [key for key, value in checks.items() if not value]
    ready = not blockers

    sufficiency = build_sufficiency_review(
        checks=checks,
        p9co=p9co,
        ready=ready,
    )
    owner_record = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cp_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "review_p9co_retained_evidence_only_before_any_live_order_or_executor_path_change",
        "recorded_at_utc": iso_z(now),
        "p9cp_review_p9co_retained_evidence_approved": owner_decision_ok,
        "future_p9cq_scope_definition_request_allowed_if_review_ready": ready,
        "fresh_remote_proof_collection_approved": False,
        "remote_execution_approved": False,
        "live_order_gate_approved": False,
        "candidate_execution_approved": False,
        "target_plan_replacement_approved": False,
        "executor_input_mutation_approved": False,
        "live_order_submission_approved": False,
    }
    non_auth = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cp_non_authorization.v1",
        "authorizations": {
            "review_p9co_retained_evidence": ready,
            "allow_future_p9cq_scope_definition_request": ready,
            "define_p9cq_scope_in_p9cp": False,
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
        "contract_version": "hv_balanced_dth60_coinglass_phase9cp_control_boundary.v1",
        "scope": "p9co_retained_evidence_review_only",
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
    sufficiency_path = proof_root / "p9co_sufficiency_review.json"
    non_auth_path = proof_root / "non_authorization.json"
    control_path = proof_root / "control_boundary_readback.json"
    summary_path = root / "summary.json"
    report_path = root / "p9cp_review_p9co.md"
    output_files = {
        "summary": str(summary_path),
        "owner_decision_record": str(owner_path),
        "p9co_sufficiency_review": str(sufficiency_path),
        "non_authorization": str(non_auth_path),
        "control_boundary_readback": str(control_path),
        "report": str(report_path),
    }
    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "status": "ready" if ready else "blocked",
        "blockers": blockers,
        "p9cp_review_p9co_post_account_blocker_read_only_fresh_remote_proof_collection_ready": ready,
        "p9co_retained_evidence_sufficient_for_p9cp_review": ready,
        "p9co_read_only_fresh_proofs_sufficient_for_next_scope_gate": ready,
        "p9co_sufficient_for_live_order_submission": False,
        "p9co_sufficient_for_candidate_execution": False,
        "account_blocker_cleared_by_p9co": p9co.get("account_blocker_cleared_by_p9co")
        is True,
        "read_only_fresh_proofs_ready": p9co.get("read_only_fresh_proofs_ready") is True,
        "final_owner_live_order_gate_approval_collected": False,
        "final_owner_live_order_gate_approval_required_next": True,
        "eligible_for_future_p9cq_scope_definition": ready,
        "eligible_for_future_live_order_submission": False,
        "eligible_for_future_candidate_execution": False,
        "live_order_gate_approved": False,
        "live_order_submission_authorized": False,
        "candidate_enter_executor_target_plan_path_authorized": False,
        "candidate_execution_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "supervisor_invocation_authorized": False,
        "timer_path_load_authorized": False,
        "remote_execution_authorized": False,
        "remote_sync_authorized": False,
        "fresh_remote_proof_collection_performed_in_p9cp": False,
        "fresh_remote_account_read_performed": False,
        "fresh_order_book_read_performed": False,
        "exchange_filter_read_performed": False,
        "order_test_endpoint_called": False,
        "remote_execution_performed": False,
        "remote_sync_performed": False,
        "remote_files_written": 0,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
        "source_p9co_summary_sha256": evidence_file(p9co_path).get("sha256", ""),
        "source_p9co_proof_manifest_sha256": evidence_file(
            paths["proof_artifact_manifest"]
        ).get("sha256", ""),
        "source_p9co_proof_status_matrix_sha256": evidence_file(
            paths["proof_status_matrix"]
        ).get("sha256", ""),
        "source_p9co_command_records_sha256": evidence_file(
            paths["command_records"]
        ).get("sha256", ""),
        "source_p9co_baseline_target_plan_sha256": p9co.get(
            "baseline_target_plan_sha256"
        ),
        "source_p9co_candidate_target_plan_sha256": p9co.get(
            "candidate_target_plan_sha256"
        ),
        "source_p9co_can_trade_pre": p9co.get("can_trade_pre"),
        "source_p9co_can_trade_post": p9co.get("can_trade_post"),
        "source_p9co_open_position_count_pre": p9co.get("open_position_count_pre"),
        "source_p9co_open_position_count_post": p9co.get("open_position_count_post"),
        "source_p9co_open_order_count_pre": p9co.get("open_order_count_pre"),
        "source_p9co_open_order_count_post": p9co.get("open_order_count_post"),
        "source_p9co_order_cancel_fill_trade_delta_zero": p9co.get(
            "order_cancel_fill_trade_delta_zero"
        ),
        "source_p9co_remote_control_boundary_unchanged": p9co.get(
            "remote_control_boundary_unchanged"
        ),
        "source_p9co_only_distance_to_high_60_contribution_changed": p9co.get(
            "only_distance_to_high_60_contribution_changed"
        ),
        "allowed_next_gate": P9CQ_GATE,
        "allowed_next_gate_scope": P9CQ_SCOPE,
        "allowed_next_gate_must_be_separately_requested": True,
        "source_evidence": {
            "phase9co_summary": evidence_file(p9co_path),
            "phase9co_proof_artifact_manifest": evidence_file(
                paths["proof_artifact_manifest"]
            ),
            "phase9co_proof_status_matrix": evidence_file(
                paths["proof_status_matrix"]
            ),
            "phase9co_pit_safe_v2v3_account_proof": evidence_file(
                paths["pit_safe_v2v3_account_proof"]
            ),
            "phase9co_no_order_replacement_dry_run": evidence_file(
                paths["no_order_candidate_target_plan_replacement_dry_run_summary"]
            ),
            "phase9co_command_records": evidence_file(paths["command_records"]),
            "project_profile": evidence_file(project_profile_path),
        },
        "checks": checks,
        "output_files": output_files,
    }

    write_json(owner_path, owner_record)
    write_json(sufficiency_path, sufficiency)
    write_json(non_auth_path, non_auth)
    write_json(control_path, control)
    write_json(summary_path, summary)
    report_path.write_text(render_markdown(summary), encoding="utf-8")
    return summary, 0 if ready else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9CP Review P9CO",
        "",
        f"`Status: {summary['status']}`",
        "",
        "P9CP reviews retained P9CO evidence only. It does not SSH, read Binance, collect fresh proofs, call order-test endpoints, invoke supervisor/timer paths, execute the candidate, replace target plans, mutate executor input, remote sync, cancel orders, or submit orders.",
        "",
        "## Review Result",
        "",
        "```text",
        "p9cp_review_p9co_post_account_blocker_read_only_fresh_remote_proof_collection_ready = "
        f"{str(bool(summary['p9cp_review_p9co_post_account_blocker_read_only_fresh_remote_proof_collection_ready'])).lower()}",
        "p9co_read_only_fresh_proofs_sufficient_for_next_scope_gate = "
        f"{str(bool(summary['p9co_read_only_fresh_proofs_sufficient_for_next_scope_gate'])).lower()}",
        "p9co_sufficient_for_live_order_submission = false",
        "final_owner_live_order_gate_approval_collected = false",
        "live_order_submission_authorized = false",
        "candidate_execution_authorized = false",
        "target_plan_replacement_authorized = false",
        "executor_input_mutation_authorized = false",
        "orders_submitted = 0",
        "fill_count = 0",
        "```",
        "",
        "## Next Gate",
        "",
        str(summary["allowed_next_gate"]),
        str(summary["allowed_next_gate_scope"]),
        "allowed_next_gate_must_be_separately_requested = true",
        "",
    ]
    if summary.get("blockers"):
        lines.extend(["## Blockers", "", *[f"- {item}" for item in summary["blockers"]], ""])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_phase9cp(parse_args(argv))
    print(
        "p9cp_review_p9co_ready="
        + str(
            bool(
                summary[
                    "p9cp_review_p9co_post_account_blocker_read_only_fresh_remote_proof_collection_ready"
                ]
            )
        ).lower()
    )
    print(f"status={summary['status']}")
    print(f"run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
