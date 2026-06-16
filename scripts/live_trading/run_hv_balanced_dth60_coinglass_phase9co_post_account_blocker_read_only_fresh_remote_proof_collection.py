from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.live_trading.hv_balanced_binance_usdm_pit_safe_account_proof_builder import (  # noqa: E402
    CAN_TRADE_SOURCE,
    build_pit_safe_account_proof,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ac_remote_runner_p9aa_readback import (  # noqa: E402
    DEFAULT_EXPECTED_EGRESS_IP,
    DEFAULT_REMOTE_CONFIG,
    DEFAULT_REMOTE_HOST,
    DEFAULT_REMOTE_LIVE_ENV,
    DEFAULT_REMOTE_REPO,
    CommandResult,
    CommandRunner,
    json_from_command,
    local_command_runner,
    remote_snapshot_script,
    snapshot_boundary_ok,
    ssh_args,
    timer_state_digest,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ag_nonflat_remote_readback import (  # noqa: E402
    DEFAULT_REMOTE_PYTHON,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bv_no_order_candidate_target_plan_replacement_dry_run import (  # noqa: E402
    APPROVE_P9BV_DECISION,
    build_p9bv_no_order_candidate_target_plan_replacement_dry_run,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ce_read_only_fresh_remote_proof_collection import (  # noqa: E402
    collector_ready as p9ce_collector_ready,
    fingerprint_delta_acceptance as p9ce_fingerprint_delta_acceptance,
    remote_identity_ready as p9ce_remote_identity_ready,
    remote_p9ce_collector_command,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ci_pit_safe_read_only_account_proof_v2v3 import (  # noqa: E402
    account_delta_acceptance,
    collector_contract_ready as p9ci_collector_ready,
    history_delta_acceptance,
    remote_identity_ready as p9ci_remote_identity_ready,
    remote_p9ci_collector_command,
    sanitized_collector as sanitize_p9ci_collector,
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
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cn_post_account_blocker_read_only_fresh_remote_proof_collection_owner_gate import (  # noqa: E402
    CONTRACT_VERSION as P9CN_CONTRACT,
    DEFAULT_OUTPUT_PARENT as P9CN_PARENT,
    P9CO_GATE,
    P9CO_SCOPE,
    proof_rows_ready as p9cn_proof_rows_ready,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    evidence_file,
    file_sha256,
    latest_match,
    load_optional,
    resolve_path,
    write_json,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9tuv_proof_only_corridor import (  # noqa: E402
    PROJECT_PROFILE,
)


CONTRACT_VERSION = (
    "hv_balanced_dth60_coinglass_phase9co_post_account_blocker_read_only_fresh_remote_proof_collection.v1"
)
APPROVE_P9CO_DECISION = (
    "approve_p9co_execute_post_account_blocker_read_only_fresh_remote_proof_collection_only_no_order_no_candidate_no_timer_no_supervisor"
)
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/p9co_post_account_blocker_read_only_fresh_remote_proof_collection"
)
P9CP_GATE = (
    "P9CP_review_p9co_post_account_blocker_read_only_fresh_remote_proof_collection_only_if_separately_requested"
)
P9CP_SCOPE = (
    "review_p9co_post_account_blocker_read_only_fresh_remote_proof_collection_before_any_live_order_or_executor_path_change"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Execute P9CO post-account-blocker read-only fresh remote proof collection. "
            "This gate uses stdout-only SSH GET readers plus local proof_artifacts. It "
            "does not call order-test endpoints, remote sync, invoke supervisor/timer "
            "paths, mutate executor input or target plans, execute the candidate, "
            "cancel orders, or submit orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9cn-summary", default="")
    parser.add_argument("--phase9bu-summary", default="")
    parser.add_argument("--remote-host", default=DEFAULT_REMOTE_HOST)
    parser.add_argument("--remote-repo", default=DEFAULT_REMOTE_REPO)
    parser.add_argument("--remote-config", default=DEFAULT_REMOTE_CONFIG)
    parser.add_argument("--remote-live-env", default=DEFAULT_REMOTE_LIVE_ENV)
    parser.add_argument("--remote-python", default=DEFAULT_REMOTE_PYTHON)
    parser.add_argument("--expected-egress-ip", default=DEFAULT_EXPECTED_EGRESS_IP)
    parser.add_argument("--canary-symbol", default=CANARY_SYMBOL)
    parser.add_argument("--max-history-symbols", type=int, default=20)
    parser.add_argument("--ssh-connect-timeout", type=int, default=10)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9CO_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default=(
            "user_chat:p9co_execute_post_account_blocker_read_only_fresh_remote_proof_collection_only_if_separately_requested"
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


def latest_p9cn_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9cn_summary).strip():
        return resolve_path(args.phase9cn_summary)
    return latest_match(P9CN_PARENT, "*/summary.json")


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def source_output_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("output_files") or {}).get(key) or "")
    return resolve_path(text) if text.strip() else Path("")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def p9cn_summary_ready(summary: dict[str, Any]) -> bool:
    return (
        summary.get("contract_version") == P9CN_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get(
            "p9cn_post_account_blocker_read_only_fresh_remote_proof_collection_owner_gate_ready"
        )
        is True
        and summary.get("p9cm_sufficient_for_p9cn_owner_gate") is True
        and summary.get(
            "post_account_blocker_read_only_fresh_remote_proof_collection_owner_gate_approved_in_p9cn"
        )
        is True
        and summary.get("eligible_for_future_p9co_execution_gate_request") is True
        and summary.get(
            "eligible_for_future_fresh_remote_proof_collection_without_separate_request"
        )
        is False
        and summary.get("fresh_remote_proof_collection_execution_approved_in_p9cn")
        is False
        and summary.get("fresh_remote_proof_collection_performed_in_p9cn") is False
        and summary.get("fresh_proofs_collected_in_p9cn") is False
        and summary.get("fresh_proofs_satisfied_by_p9cn") is False
        and summary.get("eligible_for_future_fresh_remote_proof_collection") is False
        and summary.get("eligible_for_future_live_order_submission") is False
        and summary.get("eligible_for_future_candidate_execution") is False
        and int(summary.get("required_fresh_proof_count") or 0) == len(EXPECTED_PROOFS)
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
        and summary.get("allowed_next_gate") == P9CO_GATE
        and summary.get("allowed_next_gate_scope") == P9CO_SCOPE
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
        and int_zero(summary, "orders_submitted")
        and int_zero(summary, "orders_canceled")
        and int_zero(summary, "fill_count")
        and int_zero(summary, "trade_count")
    )


def p9cn_owner_gate_ready(owner_gate: dict[str, Any]) -> bool:
    return (
        owner_gate.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cn_owner_gate.v1"
        and owner_gate.get("owner_gate_only") is True
        and owner_gate.get("owner_gate_decision")
        == "allow_future_p9co_execution_gate_request_only"
        and owner_gate.get("p9cm_sufficient_for_p9cn_owner_gate") is True
        and owner_gate.get(
            "post_account_blocker_read_only_fresh_remote_proof_collection_owner_gate_approved_in_p9cn"
        )
        is True
        and owner_gate.get("eligible_for_future_p9co_execution_gate_request") is True
        and owner_gate.get(
            "eligible_for_future_fresh_remote_proof_collection_without_separate_request"
        )
        is False
        and owner_gate.get("fresh_remote_proof_collection_execution_approved_in_p9cn")
        is False
        and owner_gate.get("fresh_remote_proof_collection_performed_in_p9cn") is False
        and owner_gate.get("live_order_gate_approved") is False
        and owner_gate.get("live_order_submission_authorized") is False
        and owner_gate.get("candidate_execution_authorized") is False
        and owner_gate.get("target_plan_replacement_authorized") is False
        and owner_gate.get("executor_input_mutation_authorized") is False
        and owner_gate.get("future_gate") == P9CO_GATE
        and owner_gate.get("future_gate_scope") == P9CO_SCOPE
        and owner_gate.get("future_gate_must_be_separately_requested") is True
        and p9cn_proof_rows_ready(
            list(owner_gate.get("required_proofs_to_collect_later") or [])
        )
        and int_zero(owner_gate, "orders_submitted")
        and int_zero(owner_gate, "orders_canceled")
        and int_zero(owner_gate, "fill_count")
        and int_zero(owner_gate, "trade_count")
    )


def p9cn_future_scope_ready(scope: dict[str, Any]) -> bool:
    may_execute = set(str(item) for item in list(scope.get("future_gate_may_execute_only") or []))
    may_not = set(str(item) for item in list(scope.get("future_gate_may_not_execute") or []))
    return (
        scope.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cn_future_p9co_execution_gate_scope.v1"
        and scope.get("owner_gate_only") is True
        and scope.get("future_gate") == P9CO_GATE
        and scope.get("future_gate_scope") == P9CO_SCOPE
        and scope.get("future_gate_must_be_separately_requested") is True
        and "read-only fresh remote proof collection" in may_execute
        and "PIT-safe v2/v3 account proof" in may_execute
        and "fresh position, open-order, balance, order, trade, book, and filter reads"
        in may_execute
        and "no-order same-risk paired target-plan and distance_to_high_60 contribution checks"
        in may_execute
        and "kill-switch and rollback readbacks" in may_execute
        and "live order submission" in may_not
        and "order-test endpoint call" in may_not
        and "candidate execution" in may_not
        and "target-plan replacement" in may_not
        and "executor-input mutation" in may_not
        and "timer path load" in may_not
        and "supervisor invocation" in may_not
        and "remote sync" in may_not
        and "live config, operator state, or timer mutation" in may_not
        and p9cn_proof_rows_ready(list(scope.get("required_proofs") or []))
        and scope.get("fresh_remote_proof_collection_performed_in_p9cn") is False
        and scope.get("fresh_remote_proof_collection_execution_approved_in_p9cn")
        is False
        and scope.get("live_order_submission_authorized") is False
    )


def p9cn_non_authorization_ready(matrix: dict[str, Any]) -> bool:
    authorizations = dict(matrix.get("authorizations") or {})
    return (
        matrix.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cn_non_authorization.v1"
        and authorizations.get("allow_future_p9co_execution_gate_request") is True
        and authorizations.get("fresh_remote_proof_collection_execution") is False
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
        and authorizations.get("live_config_mutation") is False
        and authorizations.get("operator_state_mutation") is False
        and authorizations.get("timer_or_service_mutation") is False
        and authorizations.get("timer_path_load") is False
        and authorizations.get("production_timer_service_load") is False
        and authorizations.get("supervisor_invocation") is False
        and authorizations.get("stage_governance_change") is False
    )


def p9cn_control_ready(control: dict[str, Any]) -> bool:
    return (
        control.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cn_control_boundary.v1"
        and control.get("scope")
        == "post_account_blocker_read_only_fresh_remote_proof_collection_owner_gate_only"
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


def write_proof_manifest(proof_root: Path, files: dict[str, Path]) -> dict[str, Any]:
    entries = {
        name: evidence_file(path)
        for name, path in sorted(files.items())
        if name != "proof_artifact_manifest"
    }
    manifest = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9co_proof_artifact_manifest.v1",
        "artifact_count": len(entries),
        "artifacts": entries,
    }
    manifest_path = proof_root / "proof_artifact_manifest.json"
    write_json(manifest_path, manifest)
    manifest["self"] = evidence_file(manifest_path)
    write_json(manifest_path, manifest)
    return manifest


def owner_decision_record(args: argparse.Namespace, now: datetime) -> dict[str, Any]:
    approved = str(args.owner_decision) == APPROVE_P9CO_DECISION
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9co_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "execute_post_account_blocker_read_only_fresh_remote_proof_collection_only",
        "recorded_at_utc": iso_z(now),
        "p9co_read_only_fresh_remote_proof_collection_approved": approved,
        "remote_stdout_read_only_collection_approved": approved,
        "order_test_endpoint_approved": False,
        "remote_files_written_approved": False,
        "remote_sync_approved": False,
        "supervisor_invocation_approved": False,
        "timer_path_load_approved": False,
        "candidate_execution_approved": False,
        "target_plan_replacement_approved": False,
        "executor_input_mutation_approved": False,
        "live_order_submission_approved": False,
    }


def build_p9bv_args(args: argparse.Namespace, output_root: Path) -> argparse.Namespace:
    return argparse.Namespace(
        output_root=str(output_root),
        project_profile=str(args.project_profile),
        phase9bu_summary=str(args.phase9bu_summary),
        owner=args.owner,
        owner_decision=APPROVE_P9BV_DECISION,
        owner_decision_source="p9co_embedded_no_order_candidate_target_plan_replacement_dry_run",
    )


def build_proof_status_matrix(
    *,
    proof: dict[str, Any],
    account_delta: dict[str, Any],
    history_delta: dict[str, Any],
    market_collector: dict[str, Any],
    market_delta: dict[str, Any],
    p9bv_summary: dict[str, Any],
    remote_control_unchanged: bool,
) -> dict[str, Any]:
    fresh_book = dict(market_collector.get("fresh_order_book") or {})
    filters = dict(market_collector.get("exchange_filter_readback") or {})
    p9bv_ready = (
        p9bv_summary.get("p9bv_no_order_replacement_dry_run_ready") is True
        and p9bv_summary.get("same_timestamp_context") is True
        and p9bv_summary.get("same_risk_inputs") is True
        and p9bv_summary.get("simulated_executor_input_replacement_matches_candidate")
        is True
        and p9bv_summary.get("actual_executor_input_changed") is False
        and p9bv_summary.get("actual_target_plan_replaced") is False
        and p9bv_summary.get("only_distance_to_high_60_contribution_changed") is True
        and int_zero(p9bv_summary, "orders_submitted")
        and int_zero(p9bv_summary, "fill_count")
    )
    rows = [
        {
            "proof_id": "pit_safe_v2v3_account_proof",
            "max_age_seconds": EXPECTED_PROOFS["pit_safe_v2v3_account_proof"],
            "status": "ready"
            if (
                proof.get("pit_safe_read_only_account_proof_ready") is True
                and proof.get("can_trade_source") == CAN_TRADE_SOURCE
                and proof.get("can_trade_pre") is True
                and proof.get("can_trade_post") is True
                and proof.get("account_v3_canTrade_ignored_for_permission_decision")
                is True
            )
            else "blocked",
        },
        {
            "proof_id": "fresh_position_open_order_balance_fingerprints",
            "max_age_seconds": EXPECTED_PROOFS[
                "fresh_position_open_order_balance_fingerprints"
            ],
            "status": "ready"
            if (
                account_delta.get("position_fingerprint_stable") is True
                and account_delta.get("open_order_fingerprint_stable") is True
                and account_delta.get("balance_fingerprint_stable") is True
                and account_delta.get("open_order_count_zero_pre_post") is True
                and market_delta.get("position_delta_zero_or_stable") is True
                and market_delta.get("balance_delta_zero_or_stable") is True
            )
            else "blocked",
        },
        {
            "proof_id": "fresh_order_trade_history_delta",
            "max_age_seconds": EXPECTED_PROOFS["fresh_order_trade_history_delta"],
            "status": "ready"
            if (
                history_delta.get("order_cancel_fill_trade_delta_zero") is True
                and market_delta.get("order_cancel_fill_trade_delta_zero") is True
                and market_delta.get("fill_trade_fingerprint_stable") is True
            )
            else "blocked",
        },
        {
            "proof_id": "fresh_order_book_and_exchange_filters",
            "max_age_seconds": EXPECTED_PROOFS[
                "fresh_order_book_and_exchange_filters"
            ],
            "status": "ready"
            if fresh_book.get("status") == "ready"
            and filters.get("status") == "ready"
            and int(filters.get("symbol_count") or 0) > 0
            else "blocked",
        },
        {
            "proof_id": "same_risk_paired_target_plan_binding",
            "max_age_seconds": EXPECTED_PROOFS[
                "same_risk_paired_target_plan_binding"
            ],
            "status": "ready"
            if (
                p9bv_ready
                and bool(p9bv_summary.get("baseline_target_plan_sha256"))
                and bool(p9bv_summary.get("candidate_target_plan_sha256"))
            )
            else "blocked",
        },
        {
            "proof_id": "distance_to_high_60_only_delta",
            "max_age_seconds": EXPECTED_PROOFS["distance_to_high_60_only_delta"],
            "status": "ready"
            if p9bv_summary.get("only_distance_to_high_60_contribution_changed") is True
            else "blocked",
        },
        {
            "proof_id": "no_order_candidate_target_plan_replacement_dry_run",
            "max_age_seconds": EXPECTED_PROOFS[
                "no_order_candidate_target_plan_replacement_dry_run"
            ],
            "status": "ready" if p9bv_ready else "blocked",
        },
        {
            "proof_id": "kill_switch_and_rollback_readback",
            "max_age_seconds": EXPECTED_PROOFS["kill_switch_and_rollback_readback"],
            "status": "ready" if remote_control_unchanged else "blocked",
        },
        {
            "proof_id": "final_owner_live_order_gate_approval",
            "max_age_seconds": EXPECTED_PROOFS["final_owner_live_order_gate_approval"],
            "status": "not_collected_by_design",
            "live_order_gate_approved": False,
        },
    ]
    required_read_only_ids = [
        row["proof_id"]
        for row in rows
        if row["proof_id"] != "final_owner_live_order_gate_approval"
    ]
    read_only_ready = all(
        row.get("status") == "ready"
        for row in rows
        if row.get("proof_id") in required_read_only_ids
    )
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9co_proof_status_matrix.v1",
        "read_only_fresh_proofs_ready": read_only_ready,
        "live_order_gate_approval_collected": False,
        "p9co_satisfies_live_order_gate": False,
        "proofs": rows,
    }


def build_phase9co(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
    command_runner: CommandRunner = local_command_runner,
) -> tuple[dict[str, Any], int]:
    started_at = now_fn()
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9co" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    p9cn_path = latest_p9cn_summary(args)
    p9cn = load_optional(p9cn_path)
    owner_gate_path = source_output_path(
        p9cn, "read_only_fresh_remote_proof_collection_owner_gate"
    )
    future_scope_path = source_output_path(p9cn, "future_p9co_execution_gate_scope")
    p9cn_non_auth_path = source_output_path(p9cn, "non_authorization")
    p9cn_control_path = source_output_path(p9cn, "control_boundary_readback")
    owner_gate = load_optional(owner_gate_path)
    future_scope = load_optional(future_scope_path)
    p9cn_non_auth = load_optional(p9cn_non_auth_path)
    p9cn_control = load_optional(p9cn_control_path)
    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)

    owner_record = owner_decision_record(args, started_at)
    write_json(root / "owner_decision_record.json", owner_record)

    pre_checks = {
        "owner_decision_p9co_execute_read_only_recorded": str(args.owner_decision)
        == APPROVE_P9CO_DECISION,
        "project_profile_exists": bool(project_profile),
        "current_stage_is_stage3": str(project_profile.get("current_stage") or "")
        == "stage_3_human_approved_execution",
        "p9cn_summary_exists": bool(p9cn),
        "p9cn_summary_ready_for_p9co": p9cn_summary_ready(p9cn),
        "p9cn_owner_gate_ready_for_p9co": p9cn_owner_gate_ready(owner_gate),
        "p9cn_future_scope_ready_for_p9co": p9cn_future_scope_ready(future_scope),
        "p9cn_non_authorization_ready": p9cn_non_authorization_ready(p9cn_non_auth),
        "p9cn_control_boundary_ready": p9cn_control_ready(p9cn_control),
        "remote_host_matches_expected_runner": str(args.remote_host)
        == DEFAULT_REMOTE_HOST,
        "remote_repo_matches_expected_runner": str(args.remote_repo)
        == DEFAULT_REMOTE_REPO,
        "canary_symbol_matches_p9cn": str(args.canary_symbol) == CANARY_SYMBOL,
    }
    blockers = [key for key, value in pre_checks.items() if not value]
    command_records: list[dict[str, Any]] = []
    pre_snapshot: dict[str, Any] = {}
    post_snapshot: dict[str, Any] = {}
    account_collector: dict[str, Any] = {}
    market_collector: dict[str, Any] = {}
    account_sanitized: dict[str, Any] = {}
    account_proof: dict[str, Any] = {}
    p9bv_summary: dict[str, Any] = {}
    p9bv_exit_code = 2

    def run_record(label: str, cmd: Sequence[str]) -> CommandResult:
        result = command_runner(cmd)
        command_records.append(
            {
                "label": label,
                "args": list(cmd),
                "returncode": result.returncode,
                "stdout_sha256": sha256_text(result.stdout),
                "stdout_bytes": len(result.stdout.encode("utf-8")),
                "stderr_tail": result.stderr[-4000:],
            }
        )
        return result

    if not blockers:
        pre_result = run_record(
            "pre_control_snapshot",
            ssh_args(
                args.remote_host,
                args.ssh_connect_timeout,
                remote_snapshot_script(args.remote_repo, args.remote_config),
            ),
        )
        pre_snapshot = json_from_command(pre_result)
        write_json(root / "pre_control_snapshot.json", pre_snapshot)
        if pre_result.returncode != 0:
            blockers.append("pre_control_snapshot_failed")

    if not blockers:
        account_result = run_record(
            "remote_stdout_pit_safe_v2v3_account_collector",
            ssh_args(
                args.remote_host,
                args.ssh_connect_timeout,
                remote_p9ci_collector_command(
                    remote_repo=args.remote_repo,
                    remote_live_env=args.remote_live_env,
                    remote_python=args.remote_python,
                    remote_config=args.remote_config,
                    expected_egress_ip=args.expected_egress_ip,
                    history_canary_symbol=args.canary_symbol,
                    max_history_symbols=int(args.max_history_symbols or 0),
                ),
            ),
        )
        account_collector = json_from_command(account_result)
        account_sanitized = sanitize_p9ci_collector(account_collector)
        write_json(root / "remote_stdout_account_collector_sanitized.json", account_sanitized)
        if account_result.returncode != 0:
            blockers.append("remote_stdout_pit_safe_v2v3_account_collector_failed")
        if not p9ci_collector_ready(account_collector):
            blockers.append("remote_stdout_pit_safe_v2v3_account_collector_not_ready")
        fixture = {
            "expected_egress_ip": args.expected_egress_ip,
            "pre_egress_ip": account_collector.get("pre_egress_ip"),
            "post_egress_ip": account_collector.get("post_egress_ip"),
            "pre_endpoint_results": dict(account_collector.get("pre_endpoint_results") or {}),
            "post_endpoint_results": dict(account_collector.get("post_endpoint_results") or {}),
            "side_effects": dict(account_collector.get("side_effects") or {}),
        }
        account_proof = build_pit_safe_account_proof(fixture, generated_at=started_at)

    if not blockers:
        market_result = run_record(
            "remote_stdout_market_and_fingerprint_collector",
            ssh_args(
                args.remote_host,
                args.ssh_connect_timeout,
                remote_p9ce_collector_command(
                    remote_repo=args.remote_repo,
                    remote_live_env=args.remote_live_env,
                    remote_python=args.remote_python,
                    remote_config=args.remote_config,
                    expected_egress_ip=args.expected_egress_ip,
                    canary_symbol=args.canary_symbol,
                    max_history_symbols=int(args.max_history_symbols or 0),
                ),
            ),
        )
        market_collector = json_from_command(market_result)
        write_json(root / "remote_stdout_market_collector.json", market_collector)
        if market_result.returncode != 0:
            blockers.append("remote_stdout_market_and_fingerprint_collector_failed")
        if not p9ce_collector_ready(market_collector):
            blockers.append("remote_stdout_market_and_fingerprint_collector_not_ready")

    if not blockers:
        p9bv_summary, p9bv_exit_code = build_p9bv_no_order_candidate_target_plan_replacement_dry_run(
            build_p9bv_args(args, root / "p9bv"),
            now_fn=lambda: started_at,
        )
        if p9bv_exit_code != 0:
            blockers.append("no_order_candidate_target_plan_replacement_dry_run_failed")

    if pre_snapshot:
        post_result = run_record(
            "post_control_snapshot",
            ssh_args(
                args.remote_host,
                args.ssh_connect_timeout,
                remote_snapshot_script(args.remote_repo, args.remote_config),
            ),
        )
        post_snapshot = json_from_command(post_result)
        write_json(root / "post_control_snapshot.json", post_snapshot)
        if post_result.returncode != 0:
            blockers.append("post_control_snapshot_failed")
        if not snapshot_boundary_ok(pre_snapshot, post_snapshot):
            blockers.append("remote_control_boundary_changed")

    account_delta = account_delta_acceptance(account_proof) if account_proof else {}
    history_delta = history_delta_acceptance(account_collector) if account_collector else {}
    market_delta = (
        p9ce_fingerprint_delta_acceptance(market_collector)
        if market_collector
        else {}
    )
    account_identity = dict(account_collector.get("remote_runner_identity_readback") or {})
    market_identity = dict(market_collector.get("remote_runner_identity_readback") or {})
    remote_control_unchanged = bool(pre_snapshot and post_snapshot) and snapshot_boundary_ok(
        pre_snapshot, post_snapshot
    )

    if account_collector and not p9ci_remote_identity_ready(
        account_identity,
        remote_host=args.remote_host,
        remote_repo=args.remote_repo,
        remote_config=args.remote_config,
        expected_egress_ip=args.expected_egress_ip,
    ):
        blockers.append("account_collector_remote_runner_identity_not_ready")
    if market_collector and not p9ce_remote_identity_ready(
        market_identity,
        remote_host=args.remote_host,
        remote_repo=args.remote_repo,
        remote_config=args.remote_config,
        expected_egress_ip=args.expected_egress_ip,
    ):
        blockers.append("market_collector_remote_runner_identity_not_ready")
    if account_proof and account_proof.get("pit_safe_read_only_account_proof_ready") is not True:
        blockers.append("pit_safe_v2v3_account_proof_not_ready")
    if account_proof and account_proof.get("can_trade_source") != CAN_TRADE_SOURCE:
        blockers.append("can_trade_source_not_fapi_v2_account")
    if account_proof and account_proof.get("account_v3_canTrade_ignored_for_permission_decision") is not True:
        blockers.append("account_v3_canTrade_not_ignored")
    if account_proof and (
        account_proof.get("can_trade_pre") is not True
        or account_proof.get("can_trade_post") is not True
    ):
        blockers.append("can_trade_v2_false_or_missing_after_account_blocker")
    if account_delta and account_delta.get("open_order_count_zero_pre_post") is not True:
        blockers.append("open_order_count_not_zero_pre_post")
    if history_delta and history_delta.get("order_cancel_fill_trade_delta_zero") is not True:
        blockers.append("account_history_order_cancel_fill_trade_delta_not_zero")
    if market_delta and market_delta.get("order_cancel_fill_trade_delta_zero") is not True:
        blockers.append("market_order_cancel_fill_trade_delta_not_zero")
    if market_delta and market_delta.get("position_delta_zero_or_stable") is not True:
        blockers.append("market_position_delta_not_zero_or_unstable")
    if market_delta and market_delta.get("balance_delta_zero_or_stable") is not True:
        blockers.append("market_balance_delta_not_zero_or_unstable")

    proof_status = build_proof_status_matrix(
        proof=account_proof,
        account_delta=account_delta,
        history_delta=history_delta,
        market_collector=market_collector,
        market_delta=market_delta,
        p9bv_summary=p9bv_summary,
        remote_control_unchanged=remote_control_unchanged,
    )
    if proof_status.get("read_only_fresh_proofs_ready") is not True:
        blockers.append("read_only_fresh_proof_status_matrix_not_ready")

    fresh_book = dict(market_collector.get("fresh_order_book") or {})
    filters = dict(market_collector.get("exchange_filter_readback") or {})
    kill_switch_rollback = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9co_kill_switch_rollback_readback.v1",
        "remote_control_boundary_unchanged": remote_control_unchanged,
        "pre_control_snapshot": evidence_file(root / "pre_control_snapshot.json"),
        "post_control_snapshot": evidence_file(root / "post_control_snapshot.json"),
        "kill_switch_or_operator_state_mutated_by_p9co": False,
        "rollback_context": "no live mutation performed; rollback is no-op for P9CO",
        "remote_sync_performed": False,
        "remote_files_written": 0,
        "supervisor_invoked": False,
        "timer_path_invoked": False,
        "candidate_executed": False,
        "executor_input_mutated": False,
        "target_plan_replaced": False,
    }
    non_auth = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9co_non_authorization.v1",
        "authorizations": {
            "p9co_post_account_blocker_read_only_fresh_remote_proof_collection": str(args.owner_decision)
            == APPROVE_P9CO_DECISION,
            "remote_stdout_read_only_account_market_collection": str(args.owner_decision)
            == APPROVE_P9CO_DECISION,
            "order_test_endpoint": False,
            "remote_files_written": False,
            "remote_sync": False,
            "supervisor_invocation": False,
            "timer_path_load": False,
            "production_timer_service_load": False,
            "candidate_execution": False,
            "live_order_submission": False,
            "target_plan_replacement": False,
            "executor_input_mutation": False,
            "live_config_mutation": False,
            "operator_state_mutation": False,
            "timer_or_service_mutation": False,
            "stage_governance_change": False,
        },
    }
    control = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9co_control_boundary.v1",
        "scope": "post_account_blocker_read_only_fresh_remote_proof_collection_stdout_only",
        "ssh_invoked": bool(command_records),
        "remote_network_connection_performed": bool(account_collector or market_collector),
        "remote_execution_scope": "stdout_read_only_account_market_collectors_only",
        "remote_files_written": 0,
        "remote_sync_performed": False,
        "fresh_remote_account_read_performed": bool(account_proof),
        "fresh_order_book_read_performed": bool(fresh_book),
        "exchange_filter_read_performed": bool(filters),
        "order_test_endpoint_called": False,
        "entered_timer_path": False,
        "ran_supervisor": False,
        "candidate_execution_performed": False,
        "candidate_entered_actual_executor_target_plan_path": False,
        "live_order_submission_performed": False,
        "target_plan_replaced": False,
        "executor_input_changed": False,
        "live_config_changed": bool(pre_snapshot and post_snapshot)
        and pre_snapshot.get("remote_live_config_sha256")
        != post_snapshot.get("remote_live_config_sha256"),
        "operator_state_changed": bool(pre_snapshot and post_snapshot)
        and pre_snapshot.get("operator_state") != post_snapshot.get("operator_state"),
        "timer_state_changed": bool(pre_snapshot and post_snapshot)
        and timer_state_digest(pre_snapshot) != timer_state_digest(post_snapshot),
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
    }
    proof_files = {
        "remote_runner_identity_readback": proof_root / "remote_runner_identity_readback.json",
        "remote_stdout_account_collector_sanitized": proof_root / "remote_stdout_account_collector_sanitized.json",
        "pit_safe_v2v3_account_proof": proof_root / "pit_safe_v2v3_account_proof.json",
        "account_delta_acceptance": proof_root / "account_delta_acceptance.json",
        "account_history_delta_acceptance": proof_root / "account_history_delta_acceptance.json",
        "remote_stdout_market_collector": proof_root / "remote_stdout_market_collector.json",
        "market_proof_collection_delta_acceptance": proof_root / "market_proof_collection_delta_acceptance.json",
        "fresh_order_book": proof_root / "fresh_order_book.json",
        "exchange_filter_readback": proof_root / "exchange_filter_readback.json",
        "no_order_candidate_target_plan_replacement_dry_run_summary": proof_root / "no_order_candidate_target_plan_replacement_dry_run_summary.json",
        "proof_status_matrix": proof_root / "proof_status_matrix.json",
        "kill_switch_rollback_readback": proof_root / "kill_switch_rollback_readback.json",
        "non_authorization": proof_root / "non_authorization.json",
        "control_boundary_readback": proof_root / "control_boundary_readback.json",
        "proof_artifact_manifest": proof_root / "proof_artifact_manifest.json",
    }
    combined_identity = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9co_remote_identity_readback.v1",
        "account_collector_identity": account_identity,
        "market_collector_identity": market_identity,
        "account_collector_identity_ready": bool(account_collector)
        and p9ci_remote_identity_ready(
            account_identity,
            remote_host=args.remote_host,
            remote_repo=args.remote_repo,
            remote_config=args.remote_config,
            expected_egress_ip=args.expected_egress_ip,
        ),
        "market_collector_identity_ready": bool(market_collector)
        and p9ce_remote_identity_ready(
            market_identity,
            remote_host=args.remote_host,
            remote_repo=args.remote_repo,
            remote_config=args.remote_config,
            expected_egress_ip=args.expected_egress_ip,
        ),
    }
    write_json(proof_files["remote_runner_identity_readback"], combined_identity)
    write_json(proof_files["remote_stdout_account_collector_sanitized"], account_sanitized)
    write_json(proof_files["pit_safe_v2v3_account_proof"], account_proof)
    write_json(proof_files["account_delta_acceptance"], account_delta)
    write_json(proof_files["account_history_delta_acceptance"], history_delta)
    write_json(proof_files["remote_stdout_market_collector"], market_collector)
    write_json(proof_files["market_proof_collection_delta_acceptance"], market_delta)
    write_json(proof_files["fresh_order_book"], fresh_book)
    write_json(proof_files["exchange_filter_readback"], filters)
    write_json(
        proof_files["no_order_candidate_target_plan_replacement_dry_run_summary"],
        p9bv_summary,
    )
    write_json(proof_files["proof_status_matrix"], proof_status)
    write_json(proof_files["kill_switch_rollback_readback"], kill_switch_rollback)
    write_json(proof_files["non_authorization"], non_auth)
    write_json(proof_files["control_boundary_readback"], control)
    manifest = write_proof_manifest(proof_root, proof_files)
    write_json(root / "command_records.json", {"commands": command_records})

    gates = {
        **pre_checks,
        "pre_control_snapshot_ready": bool(pre_snapshot)
        and pre_snapshot.get("status") != "parse_failed",
        "remote_stdout_pit_safe_v2v3_account_collector_ready": p9ci_collector_ready(
            account_collector
        ),
        "remote_stdout_market_and_fingerprint_collector_ready": p9ce_collector_ready(
            market_collector
        ),
        "account_collector_remote_identity_ready": combined_identity[
            "account_collector_identity_ready"
        ],
        "market_collector_remote_identity_ready": combined_identity[
            "market_collector_identity_ready"
        ],
        "pit_safe_v2v3_account_proof_ready": account_proof.get(
            "pit_safe_read_only_account_proof_ready"
        )
        is True,
        "can_trade_source_is_fapi_v2_account": account_proof.get("can_trade_source")
        == CAN_TRADE_SOURCE,
        "account_v3_canTrade_ignored": account_proof.get(
            "account_v3_canTrade_ignored_for_permission_decision"
        )
        is True,
        "can_trade_v2_true_pre_post": account_proof.get("can_trade_pre") is True
        and account_proof.get("can_trade_post") is True,
        "position_fingerprint_stable": account_delta.get("position_fingerprint_stable")
        is True
        and market_delta.get("position_delta_zero_or_stable") is True,
        "open_order_fingerprint_stable": account_delta.get(
            "open_order_fingerprint_stable"
        )
        is True
        and market_delta.get("open_order_fingerprint_stable") is True,
        "balance_fingerprint_stable": account_delta.get("balance_fingerprint_stable")
        is True
        and market_delta.get("balance_delta_zero_or_stable") is True,
        "open_order_count_zero_pre_post": account_delta.get(
            "open_order_count_zero_pre_post"
        )
        is True,
        "order_cancel_fill_trade_delta_zero": history_delta.get(
            "order_cancel_fill_trade_delta_zero"
        )
        is True
        and market_delta.get("order_cancel_fill_trade_delta_zero") is True,
        "fresh_order_book_ready": fresh_book.get("status") == "ready",
        "exchange_filter_readback_ready": filters.get("status") == "ready",
        "no_order_candidate_target_plan_replacement_dry_run_ready": p9bv_summary.get(
            "p9bv_no_order_replacement_dry_run_ready"
        )
        is True,
        "same_risk_paired_target_plan_binding": p9bv_summary.get("same_risk_inputs")
        is True
        and p9bv_summary.get("same_timestamp_context") is True,
        "distance_to_high_60_only_delta": p9bv_summary.get(
            "only_distance_to_high_60_contribution_changed"
        )
        is True,
        "remote_control_boundary_unchanged": remote_control_unchanged,
        "read_only_fresh_proofs_ready": proof_status.get(
            "read_only_fresh_proofs_ready"
        )
        is True,
        "final_owner_live_order_gate_approval_not_collected_by_design": proof_status.get(
            "live_order_gate_approval_collected"
        )
        is False,
        "proof_artifact_manifest_ready": bool(manifest.get("self", {}).get("sha256")),
        "remote_files_written_zero": control.get("remote_files_written") == 0,
        "remote_sync_not_performed": control.get("remote_sync_performed") is False,
        "order_test_endpoint_not_called": control.get("order_test_endpoint_called")
        is False,
        "supervisor_not_invoked": control.get("ran_supervisor") is False,
        "timer_path_not_loaded": control.get("entered_timer_path") is False,
        "candidate_not_executed": control.get("candidate_execution_performed") is False,
        "executor_input_not_mutated": control.get("executor_input_changed") is False,
        "target_plan_not_replaced": control.get("target_plan_replaced") is False,
        "zero_orders_fills_trades": control.get("orders_submitted") == 0
        and control.get("orders_canceled") == 0
        and control.get("fill_count") == 0
        and control.get("trade_count") == 0,
    }
    blockers.extend(key for key, value in gates.items() if not value and key not in blockers)
    blockers = sorted(set(blockers))
    status = "ready" if not blockers else "blocked"

    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "status": status,
        "blockers": blockers,
        "p9co_post_account_blocker_read_only_fresh_remote_proof_collection_ready": status
        == "ready",
        "p9cn_sufficient_for_p9co_execution": p9cn_summary_ready(p9cn),
        "fresh_remote_proof_collection_performed_in_p9co": bool(
            account_collector or market_collector
        ),
        "pit_safe_v2v3_account_proof_ready": gates[
            "pit_safe_v2v3_account_proof_ready"
        ],
        "fresh_remote_account_read_performed": bool(account_proof),
        "fresh_order_book_read_performed": bool(fresh_book),
        "exchange_filter_read_performed": bool(filters),
        "order_test_endpoint_called": False,
        "remote_execution_performed": bool(account_collector or market_collector),
        "remote_execution_scope": "stdout_read_only_account_market_collectors_only",
        "remote_files_written": 0,
        "remote_sync_performed": False,
        "target_runner_identity_proven_in_p9co": gates[
            "account_collector_remote_identity_ready"
        ]
        and gates["market_collector_remote_identity_ready"],
        "target_deploy_root_proven_in_p9co": gates[
            "account_collector_remote_identity_ready"
        ]
        and gates["market_collector_remote_identity_ready"],
        "remote_host": args.remote_host,
        "remote_repo": args.remote_repo,
        "remote_config": args.remote_config,
        "remote_python": args.remote_python,
        "expected_egress_ip": args.expected_egress_ip,
        "remote_egress_ip": account_identity.get("egress_ip")
        or market_identity.get("egress_ip"),
        "can_trade_decision_source": account_proof.get("can_trade_source")
        or CAN_TRADE_SOURCE,
        "can_trade_pre": account_proof.get("can_trade_pre"),
        "can_trade_post": account_proof.get("can_trade_post"),
        "account_v2_has_canTrade_pre": account_proof.get("account_v2_has_canTrade_pre"),
        "account_v2_has_canTrade_post": account_proof.get("account_v2_has_canTrade_post"),
        "account_v3_has_canTrade_pre": account_proof.get("account_v3_has_canTrade_pre"),
        "account_v3_has_canTrade_post": account_proof.get("account_v3_has_canTrade_post"),
        "account_v3_canTrade_ignored_for_permission_decision": account_proof.get(
            "account_v3_canTrade_ignored_for_permission_decision"
        )
        is True,
        "account_blocker_cleared_by_p9co": account_proof.get("can_trade_pre") is True
        and account_proof.get("can_trade_post") is True
        and not account_proof.get("live_order_readiness_blockers"),
        "live_order_readiness_blockers": list(
            account_proof.get("live_order_readiness_blockers") or []
        ),
        "position_fingerprint_stable": gates["position_fingerprint_stable"],
        "open_order_fingerprint_stable": gates["open_order_fingerprint_stable"],
        "balance_fingerprint_stable": gates["balance_fingerprint_stable"],
        "open_order_count_zero_pre_post": gates["open_order_count_zero_pre_post"],
        "order_cancel_fill_trade_delta_zero": gates[
            "order_cancel_fill_trade_delta_zero"
        ],
        "remote_control_boundary_unchanged": gates[
            "remote_control_boundary_unchanged"
        ],
        "open_position_count_pre": account_delta.get("open_position_count_pre"),
        "open_position_count_post": account_delta.get("open_position_count_post"),
        "open_order_count_pre": account_delta.get("open_order_count_pre"),
        "open_order_count_post": account_delta.get("open_order_count_post"),
        "same_risk_paired_target_plan_binding": gates[
            "same_risk_paired_target_plan_binding"
        ],
        "distance_to_high_60_only_delta": gates["distance_to_high_60_only_delta"],
        "no_order_candidate_target_plan_replacement_dry_run_ready": gates[
            "no_order_candidate_target_plan_replacement_dry_run_ready"
        ],
        "baseline_target_plan_sha256": p9bv_summary.get("baseline_target_plan_sha256"),
        "candidate_target_plan_sha256": p9bv_summary.get("candidate_target_plan_sha256"),
        "only_distance_to_high_60_contribution_changed": p9bv_summary.get(
            "only_distance_to_high_60_contribution_changed"
        ),
        "read_only_fresh_proofs_ready": proof_status.get(
            "read_only_fresh_proofs_ready"
        )
        is True,
        "live_order_gate_approval_collected": False,
        "live_order_gate_approved": False,
        "eligible_for_future_live_order_submission": False,
        "eligible_for_future_candidate_execution": False,
        "candidate_enter_executor_target_plan_path_authorized": False,
        "candidate_execution_authorized": False,
        "live_order_submission_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "supervisor_invocation_authorized": False,
        "timer_path_load_authorized": False,
        "production_timer_service_load_authorized": False,
        "live_config_mutation_authorized": False,
        "operator_state_mutation_authorized": False,
        "timer_or_service_mutation_authorized": False,
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
        "allowed_next_gate": P9CP_GATE,
        "allowed_next_gate_scope": P9CP_SCOPE,
        "allowed_next_gate_must_be_separately_requested": True,
        "source_evidence": {
            "phase9cn_summary": evidence_file(p9cn_path),
            "phase9cn_owner_gate": evidence_file(owner_gate_path),
            "phase9cn_future_p9co_execution_gate_scope": evidence_file(
                future_scope_path
            ),
            "phase9cn_non_authorization": evidence_file(p9cn_non_auth_path),
            "phase9cn_control_boundary": evidence_file(p9cn_control_path),
            "project_profile": evidence_file(project_profile_path),
        },
        "gates": gates,
        "output_files": {
            "summary": str(root / "summary.json"),
            "owner_decision_record": str(root / "owner_decision_record.json"),
            "command_records": str(root / "command_records.json"),
            "pre_control_snapshot": str(root / "pre_control_snapshot.json"),
            "post_control_snapshot": str(root / "post_control_snapshot.json"),
            "report": str(root / "p9co_post_account_blocker_read_only_fresh_remote_proof_collection.md"),
            "proof_artifact_manifest": str(proof_files["proof_artifact_manifest"]),
            **{
                key: str(path)
                for key, path in proof_files.items()
                if key != "proof_artifact_manifest"
            },
        },
    }
    write_json(root / "summary.json", summary)
    (root / "p9co_post_account_blocker_read_only_fresh_remote_proof_collection.md").write_text(
        render_markdown(summary),
        encoding="utf-8",
    )
    return summary, 0 if status == "ready" else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9CO Post-Account-Blocker Read-Only Fresh Remote Proof Collection",
        "",
        f"`Status: {summary['status']}`",
        "",
        "P9CO executes read-only fresh remote proof collection after the account blocker review. It uses stdout-only GET collectors and local proof artifacts. It does not call order-test endpoints, write remote files, remote sync, invoke supervisor/timer paths, execute the candidate, replace target plans, mutate executor input, cancel orders, or submit orders.",
        "",
        "## Proof Boundary",
        "",
        "```text",
        "p9co_post_account_blocker_read_only_fresh_remote_proof_collection_ready = "
        f"{str(bool(summary['p9co_post_account_blocker_read_only_fresh_remote_proof_collection_ready'])).lower()}",
        f"can_trade_decision_source = {summary['can_trade_decision_source']}",
        f"can_trade_pre = {str(summary['can_trade_pre']).lower()}",
        f"can_trade_post = {str(summary['can_trade_post']).lower()}",
        "account_blocker_cleared_by_p9co = "
        f"{str(bool(summary['account_blocker_cleared_by_p9co'])).lower()}",
        "read_only_fresh_proofs_ready = "
        f"{str(bool(summary['read_only_fresh_proofs_ready'])).lower()}",
        "live_order_gate_approval_collected = false",
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
    summary, exit_code = build_phase9co(parse_args(argv))
    print(
        "p9co_post_account_blocker_read_only_fresh_remote_proof_collection_ready="
        + str(
            bool(
                summary[
                    "p9co_post_account_blocker_read_only_fresh_remote_proof_collection_ready"
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
