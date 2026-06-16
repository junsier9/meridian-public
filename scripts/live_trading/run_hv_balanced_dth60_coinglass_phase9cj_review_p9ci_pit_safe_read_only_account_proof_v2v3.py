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
    OPEN_ORDERS_ENDPOINT,
    POSITION_MODE_ENDPOINT,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ac_remote_runner_p9aa_readback import (  # noqa: E402
    DEFAULT_EXPECTED_EGRESS_IP,
    DEFAULT_REMOTE_CONFIG,
    DEFAULT_REMOTE_HOST,
    DEFAULT_REMOTE_REPO,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ci_pit_safe_read_only_account_proof_v2v3 import (  # noqa: E402
    CONTRACT_VERSION as P9CI_CONTRACT,
    DEFAULT_OUTPUT_PARENT as P9CI_PARENT,
    P9CJ_GATE,
    P9CJ_SCOPE,
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
    "hv_balanced_dth60_coinglass_phase9cj_review_p9ci_pit_safe_read_only_account_proof_v2v3.v1"
)
APPROVE_P9CJ_DECISION = (
    "approve_p9cj_review_p9ci_pit_safe_read_only_account_proof_v2v3_only_no_remote_no_order_no_execution"
)
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/p9cj_review_p9ci_pit_safe_read_only_account_proof_v2v3"
)
P9CK_GATE = (
    "P9CK_define_post_account_blocker_live_order_readiness_scope_only_if_separately_requested"
)
P9CK_SCOPE = (
    "define_post_account_blocker_live_order_readiness_scope_no_order_no_candidate_no_executor_or_timer_change"
)
EXPECTED_P9CI_ARTIFACT_KEYS = {
    "account_delta_acceptance",
    "control_boundary_readback",
    "history_delta_acceptance",
    "non_authorization",
    "pit_safe_account_proof",
    "remote_runner_identity_readback",
    "remote_stdout_collector_sanitized",
}
EXPECTED_ENDPOINTS = {
    "account_v2": ACCOUNT_V2_ENDPOINT,
    "account_v3": ACCOUNT_V3_ENDPOINT,
    "account_config": ACCOUNT_CONFIG_ENDPOINT,
    "position_mode": POSITION_MODE_ENDPOINT,
    "open_orders": OPEN_ORDERS_ENDPOINT,
    "api_restrictions": API_RESTRICTIONS_ENDPOINT,
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Review retained P9CI PIT-safe v2/v3 read-only account proof. "
            "P9CJ is local review-only: it does not SSH, read Binance, collect "
            "fresh proofs, call order-test endpoints, run supervisor/timer paths, "
            "execute the candidate, mutate executor input or target plans, remote "
            "sync, cancel orders, or submit orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9ci-summary", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9CJ_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default=(
            "user_chat:p9cj_review_p9ci_pit_safe_read_only_account_proof_v2v3_only_if_separately_requested"
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


def latest_p9ci_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9ci_summary).strip():
        return resolve_path(args.phase9ci_summary)
    return latest_match(P9CI_PARENT, "*/summary.json")


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


def count_key(payload: Any, target: str) -> int:
    if isinstance(payload, dict):
        return sum(1 for key in payload if key == target) + sum(
            count_key(value, target) for value in payload.values()
        )
    if isinstance(payload, list):
        return sum(count_key(item, target) for item in payload)
    return 0


def side_effects_zero(side_effects: dict[str, Any]) -> bool:
    methods = {str(item).upper() for item in list(side_effects.get("http_methods_used") or [])}
    return (
        (not methods or methods == {"GET"})
        and side_effects.get("only_http_get_endpoints") is True
        and int_zero(side_effects, "remote_files_written")
        and side_effects.get("remote_sync_performed") is False
        and side_effects.get("supervisor_invoked") is False
        and side_effects.get("timer_path_invoked") is False
        and side_effects.get("candidate_executed") is False
        and side_effects.get("executor_input_mutated") is False
        and side_effects.get("target_plan_replaced") is False
        and int_zero(side_effects, "orders_submitted")
        and int_zero(side_effects, "orders_canceled")
        and int_zero(side_effects, "order_test_calls")
        and int_zero(side_effects, "fill_count")
        and int_zero(side_effects, "trade_count")
    )


def endpoint_result_ready(result: dict[str, Any], expected_path: str) -> bool:
    return (
        result.get("status") == "ok"
        and result.get("method") == "GET"
        and result.get("path") == expected_path
        and int_equals(result, "status_code", 200)
        and not result.get("error")
        and not result.get("error_type")
    )


def endpoint_group_ready(group: dict[str, Any]) -> bool:
    return all(
        endpoint_result_ready(dict(group.get(key) or {}), expected_path)
        for key, expected_path in EXPECTED_ENDPOINTS.items()
    )


def p9ci_summary_ready(summary: dict[str, Any]) -> bool:
    gates = dict(summary.get("gates") or {})
    return (
        summary.get("contract_version") == P9CI_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9ci_pit_safe_read_only_account_proof_v2v3_ready") is True
        and summary.get("p9ch_sufficient_for_p9ci_execution") is True
        and summary.get("fresh_remote_account_read_performed") is True
        and summary.get("pit_safe_v2v3_account_proof_executed") is True
        and summary.get("fresh_order_book_read_performed") is False
        and summary.get("exchange_filter_read_performed") is False
        and summary.get("order_test_endpoint_called") is False
        and summary.get("remote_execution_scope")
        == "stdout_pit_safe_v2v3_read_only_account_collector_only"
        and summary.get("remote_execution_performed") is True
        and int_equals(summary, "remote_files_written", 0)
        and summary.get("remote_sync_performed") is False
        and summary.get("target_runner_identity_proven_in_p9ci") is True
        and summary.get("target_deploy_root_proven_in_p9ci") is True
        and summary.get("remote_host") == DEFAULT_REMOTE_HOST
        and summary.get("remote_repo") == DEFAULT_REMOTE_REPO
        and summary.get("remote_config") == DEFAULT_REMOTE_CONFIG
        and summary.get("expected_egress_ip") == DEFAULT_EXPECTED_EGRESS_IP
        and summary.get("remote_egress_ip") == DEFAULT_EXPECTED_EGRESS_IP
        and summary.get("can_trade_decision_source") == CAN_TRADE_SOURCE
        and summary.get("can_trade_pre") is True
        and summary.get("can_trade_post") is True
        and summary.get("account_v2_has_canTrade_pre") is True
        and summary.get("account_v2_has_canTrade_post") is True
        and summary.get("account_v3_canTrade_ignored_for_permission_decision") is True
        and list(summary.get("live_order_readiness_blockers") or []) == []
        and summary.get("eligible_to_clear_p9cf_account_can_trade_blocker") is True
        and summary.get("prior_p9ce_blocker_reclassification")
        == "prior_p9ce_false_or_missing_blocker_was_endpoint_schema_gap"
        and summary.get("eligible_for_future_live_order_submission") is False
        and summary.get("eligible_for_future_candidate_execution") is False
        and summary.get("live_order_gate_approved") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("candidate_execution_authorized") is False
        and summary.get("target_plan_replacement_authorized") is False
        and summary.get("executor_input_mutation_authorized") is False
        and summary.get("supervisor_invocation_authorized") is False
        and summary.get("timer_path_load_authorized") is False
        and summary.get("position_fingerprint_stable") is True
        and summary.get("open_order_fingerprint_stable") is True
        and summary.get("balance_fingerprint_stable") is True
        and summary.get("open_order_count_zero_pre_post") is True
        and summary.get("order_cancel_fill_trade_delta_zero") is True
        and summary.get("remote_control_boundary_unchanged") is True
        and summary.get("open_position_count_pre") == summary.get("open_position_count_post")
        and int_equals(summary, "open_order_count_pre", 0)
        and int_equals(summary, "open_order_count_post", 0)
        and int_zero(summary, "orders_submitted")
        and int_zero(summary, "orders_canceled")
        and int_zero(summary, "fill_count")
        and int_zero(summary, "trade_count")
        and summary.get("allowed_next_gate") == P9CJ_GATE
        and summary.get("allowed_next_gate_scope") == P9CJ_SCOPE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
        and bool(gates)
        and all(value is True for value in gates.values())
    )


def proof_manifest_ready(manifest: dict[str, Any]) -> bool:
    artifacts = dict(manifest.get("artifacts") or {})
    return (
        manifest.get("contract_version") == "hv_balanced_dth60_coinglass_phase9ci_proof_manifest.v1"
        and int(manifest.get("artifact_count") or 0) == len(EXPECTED_P9CI_ARTIFACT_KEYS)
        and set(artifacts) == EXPECTED_P9CI_ARTIFACT_KEYS
        and all(
            dict(entry).get("exists") is True and bool(dict(entry).get("sha256"))
            for entry in artifacts.values()
        )
        and dict(manifest.get("self") or {}).get("exists") is True
        and bool(dict(manifest.get("self") or {}).get("sha256"))
    )


def pit_safe_account_proof_ready(proof: dict[str, Any]) -> bool:
    checks = dict(proof.get("checks") or {})
    pre = dict(proof.get("pre") or {})
    post = dict(proof.get("post") or {})
    pre_restrictions = dict(pre.get("api_restrictions_summary") or {})
    post_restrictions = dict(post.get("api_restrictions_summary") or {})
    return (
        proof.get("contract_version") == ACCOUNT_PROOF_CONTRACT_VERSION
        and proof.get("status") == "ready"
        and not proof.get("blockers")
        and proof.get("pit_safe_read_only_account_proof_ready") is True
        and proof.get("account_permission_source_corrected") is True
        and proof.get("can_trade_source") == CAN_TRADE_SOURCE
        and proof.get("can_trade_pre") is True
        and proof.get("can_trade_post") is True
        and proof.get("account_v2_has_canTrade_pre") is True
        and proof.get("account_v2_has_canTrade_post") is True
        and proof.get("account_v3_canTrade_ignored_for_permission_decision") is True
        and list(proof.get("live_order_readiness_blockers") or []) == []
        and proof.get("eligible_to_clear_p9cf_account_can_trade_blocker") is True
        and proof.get("prior_p9ce_blocker_reclassification")
        == "prior_p9ce_false_or_missing_blocker_was_endpoint_schema_gap"
        and checks.get("can_trade_source_is_v2_account") is True
        and checks.get("account_v3_canTrade_ignored") is True
        and checks.get("can_trade_state_stable") is True
        and checks.get("position_fingerprint_stable") is True
        and checks.get("open_order_fingerprint_stable") is True
        and checks.get("balance_fingerprint_stable") is True
        and checks.get("open_order_count_zero_pre_post") is True
        and checks.get("side_effects_zero") is True
        and pre.get("account_readable") is True
        and post.get("account_readable") is True
        and pre.get("account_v2_has_canTrade") is True
        and post.get("account_v2_has_canTrade") is True
        and pre.get("account_v3_canTrade_ignored_for_permission_decision") is True
        and post.get("account_v3_canTrade_ignored_for_permission_decision") is True
        and pre.get("can_trade") is True
        and post.get("can_trade") is True
        and pre.get("can_trade_source") == CAN_TRADE_SOURCE
        and post.get("can_trade_source") == CAN_TRADE_SOURCE
        and pre.get("expected_egress_ip") == DEFAULT_EXPECTED_EGRESS_IP
        and post.get("expected_egress_ip") == DEFAULT_EXPECTED_EGRESS_IP
        and pre.get("egress_ip") == DEFAULT_EXPECTED_EGRESS_IP
        and post.get("egress_ip") == DEFAULT_EXPECTED_EGRESS_IP
        and pre.get("position_mode") == "one_way"
        and post.get("position_mode") == "one_way"
        and endpoint_group_ready(dict(pre.get("endpoint_results") or {}))
        and endpoint_group_ready(dict(post.get("endpoint_results") or {}))
        and dict(pre.get("endpoint_schema") or {}).get("can_trade_decision_source")
        == CAN_TRADE_SOURCE
        and dict(post.get("endpoint_schema") or {}).get("can_trade_decision_source")
        == CAN_TRADE_SOURCE
        and dict(pre.get("endpoint_schema") or {}).get("can_trade_missing_blocker")
        == BLOCKER_CAN_TRADE_MISSING
        and dict(post.get("endpoint_schema") or {}).get("can_trade_missing_blocker")
        == BLOCKER_CAN_TRADE_MISSING
        and dict(pre.get("endpoint_schema") or {}).get("can_trade_false_blocker")
        == BLOCKER_CAN_TRADE_FALSE
        and dict(post.get("endpoint_schema") or {}).get("can_trade_false_blocker")
        == BLOCKER_CAN_TRADE_FALSE
        and pre.get("future_live_order_readiness_blockers") == []
        and post.get("future_live_order_readiness_blockers") == []
        and pre_restrictions.get("enable_futures") is True
        and post_restrictions.get("enable_futures") is True
        and pre_restrictions.get("enable_reading") is True
        and post_restrictions.get("enable_reading") is True
        and pre_restrictions.get("enable_withdrawals") is False
        and post_restrictions.get("enable_withdrawals") is False
        and pre_restrictions.get("ip_restrict") is True
        and post_restrictions.get("ip_restrict") is True
        and pre.get("open_position_count") == post.get("open_position_count")
        and int_equals(pre, "open_order_count", 0)
        and int_equals(post, "open_order_count", 0)
        and side_effects_zero(dict(proof.get("side_effects") or {}))
        and int_zero(proof, "orders_submitted")
        and int_zero(proof, "orders_canceled")
        and int_zero(proof, "fill_count")
        and int_zero(proof, "trade_count")
    )


def account_delta_ready(delta: dict[str, Any]) -> bool:
    return (
        delta.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9ci_account_delta_acceptance.v1"
        and delta.get("position_fingerprint_stable") is True
        and delta.get("open_order_fingerprint_stable") is True
        and delta.get("balance_fingerprint_stable") is True
        and delta.get("open_order_count_zero_pre_post") is True
        and delta.get("side_effects_zero") is True
        and delta.get("position_delta_zero_or_stable") is True
        and delta.get("open_order_delta_zero_or_stable") is True
        and delta.get("balance_delta_zero_or_stable") is True
        and delta.get("open_position_count_pre") == delta.get("open_position_count_post")
        and int_equals(delta, "open_order_count_pre", 0)
        and int_equals(delta, "open_order_count_post", 0)
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
        and bool(delta.get("order_history_hash_pre"))
        and delta.get("order_history_hash_pre") == delta.get("order_history_hash_post")
        and bool(delta.get("trade_history_hash_pre"))
        and delta.get("trade_history_hash_pre") == delta.get("trade_history_hash_post")
        and bool(list(delta.get("proof_symbols") or []))
        and delta.get("order_cancel_fill_trade_delta_zero") is True
        and int_zero(delta, "orders_submitted")
        and int_zero(delta, "orders_canceled")
        and int_zero(delta, "fill_count")
        and int_zero(delta, "trade_count")
    )


def remote_stdout_collector_ready(collector: dict[str, Any]) -> bool:
    history = dict(collector.get("history_delta") or {})
    return (
        collector.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9ci_remote_stdout_v2v3_account_collector.v1"
        and collector.get("status") == "ready"
        and not collector.get("blockers")
        and collector.get("pre_egress_ip") == DEFAULT_EXPECTED_EGRESS_IP
        and collector.get("post_egress_ip") == DEFAULT_EXPECTED_EGRESS_IP
        and endpoint_group_ready(dict(collector.get("pre_endpoint_results") or {}))
        and endpoint_group_ready(dict(collector.get("post_endpoint_results") or {}))
        and bool(list(collector.get("proof_symbols") or []))
        and history.get("order_history_fingerprint_stable") is True
        and history.get("trade_history_fingerprint_stable") is True
        and bool(history.get("order_history_hash_pre"))
        and history.get("order_history_hash_pre") == history.get("order_history_hash_post")
        and bool(history.get("trade_history_hash_pre"))
        and history.get("trade_history_hash_pre") == history.get("trade_history_hash_post")
        and side_effects_zero(dict(collector.get("side_effects") or {}))
        and count_key(collector, "payload") == 0
    )


def remote_identity_ready(identity: dict[str, Any]) -> bool:
    return (
        identity.get("whoami") == "root"
        and identity.get("repo_path") == DEFAULT_REMOTE_REPO
        and identity.get("config_path") == DEFAULT_REMOTE_CONFIG
        and identity.get("egress_ip") == DEFAULT_EXPECTED_EGRESS_IP
        and bool(identity.get("config_sha256"))
        and bool(identity.get("live_supervisor_sha256"))
    )


def non_authorization_ready(matrix: dict[str, Any]) -> bool:
    authorizations = dict(matrix.get("authorizations") or {})
    return (
        matrix.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9ci_non_authorization.v1"
        and authorizations.get("p9ci_pit_safe_v2v3_read_only_account_proof") is True
        and authorizations.get("remote_stdout_read_only_account_collection") is True
        and authorizations.get("fresh_order_book_read") is False
        and authorizations.get("exchange_filter_read") is False
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


def control_boundary_ready(control: dict[str, Any]) -> bool:
    return (
        control.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9ci_control_boundary.v1"
        and control.get("scope") == "pit_safe_v2v3_read_only_account_proof_stdout_only"
        and control.get("ssh_invoked") is True
        and control.get("remote_network_connection_performed") is True
        and control.get("remote_execution_scope")
        == "stdout_pit_safe_v2v3_read_only_account_collector_only"
        and int_equals(control, "remote_files_written", 0)
        and control.get("remote_sync_performed") is False
        and control.get("fresh_remote_account_read_performed") is True
        and control.get("fresh_order_book_read_performed") is False
        and control.get("exchange_filter_read_performed") is False
        and control.get("order_test_endpoint_called") is False
        and control.get("entered_timer_path") is False
        and control.get("ran_supervisor") is False
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


def command_records_ready(records: dict[str, Any]) -> bool:
    commands = list(records.get("commands") or [])
    labels = [str(dict(command).get("label") or "") for command in commands]
    command_text = "\n".join(
        " ".join(str(arg) for arg in list(dict(command).get("args") or []))
        for command in commands
    ).lower()
    forbidden = [
        "scp ",
        "rsync ",
        "systemctl start",
        "systemctl enable",
        "systemctl restart",
        "/fapi/v1/order/test",
        "/fapi/v1/order?",
    ]
    return (
        labels
        == [
            "pre_control_snapshot",
            "remote_stdout_pit_safe_v2v3_account_collector",
            "post_control_snapshot",
        ]
        and all(int_equals(dict(command), "returncode", 0) for command in commands)
        and all(bool(dict(command).get("stdout_sha256")) for command in commands)
        and all("stdout_tail" not in dict(command) for command in commands)
        and not any(item in command_text for item in forbidden)
    )


def retained_p9ci_payload_key_count(
    *,
    summary: dict[str, Any],
    artifacts: list[dict[str, Any]],
    commands: dict[str, Any],
) -> int:
    return count_key(summary, "payload") + count_key(commands, "payload") + sum(
        count_key(artifact, "payload") for artifact in artifacts
    )


def build_phase9cj_review_p9ci_pit_safe_read_only_account_proof_v2v3(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    now = now_fn()
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9cj" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    p9ci_summary_path = latest_p9ci_summary(args)
    p9ci = load_optional(p9ci_summary_path)
    manifest_path = source_output_path(p9ci, "proof_artifact_manifest")
    proof_path = source_output_path(p9ci, "pit_safe_account_proof")
    account_delta_path = source_output_path(p9ci, "account_delta_acceptance")
    history_delta_path = source_output_path(p9ci, "history_delta_acceptance")
    collector_path = source_output_path(p9ci, "remote_stdout_collector_sanitized")
    identity_path = source_output_path(p9ci, "remote_runner_identity_readback")
    non_auth_path = source_output_path(p9ci, "non_authorization")
    control_path = source_output_path(p9ci, "control_boundary_readback")
    command_records_path = source_output_path(p9ci, "command_records")

    manifest = load_optional(manifest_path)
    proof = load_optional(proof_path)
    account_delta = load_optional(account_delta_path)
    history_delta = load_optional(history_delta_path)
    collector = load_optional(collector_path)
    identity = load_optional(identity_path)
    p9ci_non_auth = load_optional(non_auth_path)
    p9ci_control = load_optional(control_path)
    command_records = load_optional(command_records_path)
    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)

    retained_payload_key_count = retained_p9ci_payload_key_count(
        summary=p9ci,
        artifacts=[
            manifest,
            proof,
            account_delta,
            history_delta,
            collector,
            identity,
            p9ci_non_auth,
            p9ci_control,
        ],
        commands=command_records,
    )
    owner_decision_ok = str(args.owner_decision) == APPROVE_P9CJ_DECISION
    checks = {
        "owner_decision_p9cj_review_only_recorded": owner_decision_ok,
        "project_profile_exists": bool(project_profile),
        "current_stage_is_stage3": str(project_profile.get("current_stage") or "")
        == "stage_3_human_approved_execution",
        "p9ci_summary_exists": bool(p9ci),
        "p9ci_summary_ready_for_account_blocker_review": p9ci_summary_ready(p9ci),
        "p9ci_proof_manifest_ready": proof_manifest_ready(manifest),
        "p9ci_pit_safe_account_proof_ready": pit_safe_account_proof_ready(proof),
        "p9ci_account_delta_acceptance_ready": account_delta_ready(account_delta),
        "p9ci_history_delta_acceptance_ready": history_delta_ready(history_delta),
        "p9ci_remote_stdout_collector_sanitized_ready": remote_stdout_collector_ready(
            collector
        ),
        "p9ci_remote_runner_identity_ready": remote_identity_ready(identity),
        "p9ci_non_authorization_ready": non_authorization_ready(p9ci_non_auth),
        "p9ci_control_boundary_ready": control_boundary_ready(p9ci_control),
        "p9ci_command_records_ready": command_records_ready(command_records),
        "retained_p9ci_payload_keys_absent": retained_payload_key_count == 0,
    }
    blockers = [key for key, value in checks.items() if not value]
    ready = not blockers
    account_blocker_cleared = ready

    owner_record = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cj_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "review_p9ci_retained_v2v3_account_proof_to_classify_account_blocker_only_no_remote_no_order_no_execution",
        "recorded_at_utc": iso_z(now),
        "p9cj_review_approved": owner_decision_ok,
        "account_blocker_clearance_review_approved": owner_decision_ok,
        "fresh_remote_account_read_approved": False,
        "remote_execution_approved": False,
        "live_order_gate_approved": False,
        "candidate_execution_approved": False,
        "target_plan_replacement_approved": False,
        "executor_input_mutation_approved": False,
        "live_order_submission_approved": False,
    }
    review = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cj_sufficiency_review.v1",
        "run_id": run_id,
        "status": "ready" if ready else "blocked",
        "review_scope": "p9ci_retained_pit_safe_v2v3_account_proof_classification_before_any_live_order_or_executor_path_change",
        "checks": checks,
        "blockers": blockers,
        "p9ci_sufficient_for_p9cj_review": ready,
        "p9ci_sufficient_to_clear_account_can_trade_blocker": account_blocker_cleared,
        "account_blocker_clearance_conclusion": (
            "clear_account_can_trade_false_or_missing_as_endpoint_schema_gap"
            if account_blocker_cleared
            else "do_not_clear_account_can_trade_false_or_missing"
        ),
        "live_order_gate_conclusion": "not_approved_by_p9cj_review",
        "fresh_remote_account_read_performed_in_p9cj": False,
        "remote_execution_performed_in_p9cj": False,
        "retained_p9ci_payload_key_count": retained_payload_key_count,
    }
    account_clearance = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cj_account_blocker_clearance_decision.v1",
        "run_id": run_id,
        "status": "ready" if account_blocker_cleared else "blocked",
        "prior_blocker": "account_can_trade_false_or_missing",
        "replacement_blockers": [
            BLOCKER_CAN_TRADE_MISSING,
            BLOCKER_CAN_TRADE_FALSE,
        ],
        "can_trade_decision_source": CAN_TRADE_SOURCE,
        "source_p9ci_can_trade_pre": p9ci.get("can_trade_pre"),
        "source_p9ci_can_trade_post": p9ci.get("can_trade_post"),
        "source_p9ci_account_v2_has_canTrade_pre": p9ci.get(
            "account_v2_has_canTrade_pre"
        ),
        "source_p9ci_account_v2_has_canTrade_post": p9ci.get(
            "account_v2_has_canTrade_post"
        ),
        "source_p9ci_account_v3_has_canTrade_pre": p9ci.get(
            "account_v3_has_canTrade_pre"
        ),
        "source_p9ci_account_v3_has_canTrade_post": p9ci.get(
            "account_v3_has_canTrade_post"
        ),
        "source_p9ci_account_v3_canTrade_ignored_for_permission_decision": p9ci.get(
            "account_v3_canTrade_ignored_for_permission_decision"
        )
        is True,
        "source_p9ci_live_order_readiness_blockers": list(
            p9ci.get("live_order_readiness_blockers") or []
        ),
        "source_p9ci_eligible_to_clear_p9cf_account_can_trade_blocker": p9ci.get(
            "eligible_to_clear_p9cf_account_can_trade_blocker"
        )
        is True,
        "source_p9ci_prior_p9ce_blocker_reclassification": p9ci.get(
            "prior_p9ce_blocker_reclassification"
        ),
        "p9ce_false_or_missing_reclassified_as_endpoint_schema_gap": account_blocker_cleared,
        "account_can_trade_blocker_cleared_by_p9cj_review": account_blocker_cleared,
        "remaining_account_permission_blockers": [] if account_blocker_cleared else blockers,
        "live_order_readiness_blockers_after_account_review": []
        if account_blocker_cleared
        else ["account_can_trade_false_or_missing"],
        "clears_live_order_gate": False,
        "approves_live_order_submission": False,
        "approves_candidate_execution": False,
        "approves_target_plan_replacement": False,
        "approves_executor_input_mutation": False,
    }
    non_authorization = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cj_non_authorization.v1",
        "run_id": run_id,
        "authorizations": {
            "review_p9ci_retained_pit_safe_account_proof": ready,
            "clear_account_can_trade_blocker_for_future_discussion": account_blocker_cleared,
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
        "contract_version": "hv_balanced_dth60_coinglass_phase9cj_control_boundary.v1",
        "run_id": run_id,
        "scope": "p9ci_retained_evidence_review_only",
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
    review_path = proof_root / "p9ci_sufficiency_review.json"
    clearance_path = proof_root / "account_blocker_clearance_decision.json"
    non_auth_out_path = proof_root / "non_authorization.json"
    control_out_path = proof_root / "control_boundary_readback.json"
    summary_path = root / "summary.json"
    report_path = root / "p9cj_review_p9ci_pit_safe_read_only_account_proof_v2v3.md"

    output_files = {
        "summary": str(summary_path),
        "owner_decision_record": str(owner_path),
        "p9ci_sufficiency_review": str(review_path),
        "account_blocker_clearance_decision": str(clearance_path),
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
        "p9cj_review_p9ci_pit_safe_read_only_account_proof_v2v3_ready": ready,
        "p9ci_sufficient_for_p9cj_review": ready,
        "p9ci_sufficient_to_clear_account_can_trade_blocker": account_blocker_cleared,
        "account_can_trade_blocker_cleared_by_p9cj_review": account_blocker_cleared,
        "p9ce_false_or_missing_reclassified_as_endpoint_schema_gap": account_blocker_cleared,
        "live_order_readiness_blockers_after_account_review": []
        if account_blocker_cleared
        else ["account_can_trade_false_or_missing"],
        "remaining_account_permission_blockers": [] if account_blocker_cleared else blockers,
        "eligible_for_future_p9ck_scope_gate": ready,
        "eligible_for_future_live_order_submission": False,
        "eligible_for_future_candidate_execution": False,
        "eligible_for_future_candidate_executor_path_entry": False,
        "fresh_remote_account_read_performed_in_p9cj": False,
        "fresh_remote_account_read_performed": False,
        "fresh_order_book_read_performed": False,
        "exchange_filter_read_performed": False,
        "order_test_endpoint_called": False,
        "remote_execution_performed": False,
        "remote_sync_performed": False,
        "remote_files_written": 0,
        "source_p9ci_remote_execution_performed": p9ci.get("remote_execution_performed"),
        "source_p9ci_remote_execution_scope": p9ci.get("remote_execution_scope"),
        "source_p9ci_remote_files_written": p9ci.get("remote_files_written"),
        "source_p9ci_remote_sync_performed": p9ci.get("remote_sync_performed"),
        "source_p9ci_can_trade_decision_source": p9ci.get("can_trade_decision_source"),
        "source_p9ci_can_trade_pre": p9ci.get("can_trade_pre"),
        "source_p9ci_can_trade_post": p9ci.get("can_trade_post"),
        "source_p9ci_account_v2_has_canTrade_pre": p9ci.get(
            "account_v2_has_canTrade_pre"
        ),
        "source_p9ci_account_v2_has_canTrade_post": p9ci.get(
            "account_v2_has_canTrade_post"
        ),
        "source_p9ci_account_v3_has_canTrade_pre": p9ci.get(
            "account_v3_has_canTrade_pre"
        ),
        "source_p9ci_account_v3_has_canTrade_post": p9ci.get(
            "account_v3_has_canTrade_post"
        ),
        "source_p9ci_account_v3_canTrade_ignored_for_permission_decision": p9ci.get(
            "account_v3_canTrade_ignored_for_permission_decision"
        )
        is True,
        "source_p9ci_live_order_readiness_blockers": list(
            p9ci.get("live_order_readiness_blockers") or []
        ),
        "source_p9ci_eligible_to_clear_p9cf_account_can_trade_blocker": p9ci.get(
            "eligible_to_clear_p9cf_account_can_trade_blocker"
        )
        is True,
        "source_p9ci_prior_p9ce_blocker_reclassification": p9ci.get(
            "prior_p9ce_blocker_reclassification"
        ),
        "source_p9ci_open_position_count_pre": p9ci.get("open_position_count_pre"),
        "source_p9ci_open_position_count_post": p9ci.get("open_position_count_post"),
        "source_p9ci_open_order_count_pre": p9ci.get("open_order_count_pre"),
        "source_p9ci_open_order_count_post": p9ci.get("open_order_count_post"),
        "source_p9ci_position_fingerprint_stable": p9ci.get(
            "position_fingerprint_stable"
        ),
        "source_p9ci_open_order_fingerprint_stable": p9ci.get(
            "open_order_fingerprint_stable"
        ),
        "source_p9ci_balance_fingerprint_stable": p9ci.get(
            "balance_fingerprint_stable"
        ),
        "source_p9ci_order_cancel_fill_trade_delta_zero": p9ci.get(
            "order_cancel_fill_trade_delta_zero"
        ),
        "source_p9ci_remote_control_boundary_unchanged": p9ci.get(
            "remote_control_boundary_unchanged"
        ),
        "retained_p9ci_payload_key_count": retained_payload_key_count,
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
        "allowed_next_gate": P9CK_GATE,
        "allowed_next_gate_scope": P9CK_SCOPE,
        "allowed_next_gate_must_be_separately_requested": True,
        "source_evidence": {
            "phase9ci_summary": evidence_file(p9ci_summary_path),
            "phase9ci_proof_manifest": evidence_file(manifest_path),
            "phase9ci_pit_safe_account_proof": evidence_file(proof_path),
            "phase9ci_account_delta_acceptance": evidence_file(account_delta_path),
            "phase9ci_history_delta_acceptance": evidence_file(history_delta_path),
            "phase9ci_remote_stdout_collector_sanitized": evidence_file(collector_path),
            "phase9ci_remote_runner_identity_readback": evidence_file(identity_path),
            "phase9ci_non_authorization": evidence_file(non_auth_path),
            "phase9ci_control_boundary": evidence_file(control_path),
            "phase9ci_command_records": evidence_file(command_records_path),
            "project_profile": evidence_file(project_profile_path),
        },
        "checks": checks,
        "output_files": output_files,
    }

    write_json(owner_path, owner_record)
    write_json(review_path, review)
    write_json(clearance_path, account_clearance)
    write_json(non_auth_out_path, non_authorization)
    write_json(control_out_path, control)
    write_json(summary_path, summary)
    report_path.write_text(render_markdown(summary), encoding="utf-8")
    return summary, 0 if ready else 2


def build_phase9cj(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    return build_phase9cj_review_p9ci_pit_safe_read_only_account_proof_v2v3(
        args,
        now_fn=now_fn,
    )


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9CJ Review P9CI PIT-Safe v2/v3 Account Proof",
        "",
        f"`Status: {summary['status']}`",
        "",
        "P9CJ reviews retained P9CI evidence only. It does not SSH, read Binance, collect fresh proofs, call order-test endpoints, run supervisor or timer paths, mutate config/operator/timer/executor state, execute the candidate, replace target plans, cancel orders, or submit orders.",
        "",
        "## Review Result",
        "",
        "```text",
        "p9cj_review_p9ci_pit_safe_read_only_account_proof_v2v3_ready = "
        f"{str(bool(summary['p9cj_review_p9ci_pit_safe_read_only_account_proof_v2v3_ready'])).lower()}",
        "p9ci_sufficient_to_clear_account_can_trade_blocker = "
        f"{str(bool(summary['p9ci_sufficient_to_clear_account_can_trade_blocker'])).lower()}",
        "account_can_trade_blocker_cleared_by_p9cj_review = "
        f"{str(bool(summary['account_can_trade_blocker_cleared_by_p9cj_review'])).lower()}",
        "p9ce_false_or_missing_reclassified_as_endpoint_schema_gap = "
        f"{str(bool(summary['p9ce_false_or_missing_reclassified_as_endpoint_schema_gap'])).lower()}",
        "live_order_readiness_blockers_after_account_review = "
        + ", ".join(summary["live_order_readiness_blockers_after_account_review"]),
        "eligible_for_future_live_order_submission = false",
        "eligible_for_future_candidate_execution = false",
        "eligible_for_future_p9ck_scope_gate = "
        f"{str(bool(summary['eligible_for_future_p9ck_scope_gate'])).lower()}",
        "```",
        "",
        "## Source P9CI Evidence",
        "",
        "```text",
        f"source_p9ci_remote_execution_scope = {summary['source_p9ci_remote_execution_scope']}",
        f"source_p9ci_can_trade_decision_source = {summary['source_p9ci_can_trade_decision_source']}",
        "source_p9ci_can_trade_pre = "
        f"{str(bool(summary['source_p9ci_can_trade_pre'])).lower()}",
        "source_p9ci_can_trade_post = "
        f"{str(bool(summary['source_p9ci_can_trade_post'])).lower()}",
        "source_p9ci_account_v2_has_canTrade_pre = "
        f"{str(bool(summary['source_p9ci_account_v2_has_canTrade_pre'])).lower()}",
        "source_p9ci_account_v2_has_canTrade_post = "
        f"{str(bool(summary['source_p9ci_account_v2_has_canTrade_post'])).lower()}",
        "source_p9ci_account_v3_canTrade_ignored_for_permission_decision = "
        f"{str(bool(summary['source_p9ci_account_v3_canTrade_ignored_for_permission_decision'])).lower()}",
        f"source_p9ci_open_position_count_pre = {summary['source_p9ci_open_position_count_pre']}",
        f"source_p9ci_open_position_count_post = {summary['source_p9ci_open_position_count_post']}",
        f"source_p9ci_open_order_count_pre = {summary['source_p9ci_open_order_count_pre']}",
        f"source_p9ci_open_order_count_post = {summary['source_p9ci_open_order_count_post']}",
        "source_p9ci_order_cancel_fill_trade_delta_zero = "
        f"{str(bool(summary['source_p9ci_order_cancel_fill_trade_delta_zero'])).lower()}",
        "source_p9ci_remote_control_boundary_unchanged = "
        f"{str(bool(summary['source_p9ci_remote_control_boundary_unchanged'])).lower()}",
        f"retained_p9ci_payload_key_count = {summary['retained_p9ci_payload_key_count']}",
        "```",
        "",
        "## No-Order Boundary",
        "",
        "```text",
        "fresh_remote_account_read_performed_in_p9cj = false",
        "remote_execution_performed = false",
        "order_test_endpoint_called = false",
        "live_order_submission_authorized = false",
        "candidate_execution_authorized = false",
        "target_plan_replacement_authorized = false",
        "executor_input_mutation_authorized = false",
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
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_phase9cj(parse_args(argv))
    print(f"status={summary['status']}")
    print(f"summary={summary['output_files']['summary']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
