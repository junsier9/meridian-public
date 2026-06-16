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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9co_post_account_blocker_read_only_fresh_remote_proof_collection import (  # noqa: E402
    APPROVE_P9CO_DECISION,
    CONTRACT_VERSION as P9CO_CONTRACT,
    DEFAULT_EXPECTED_EGRESS_IP,
    DEFAULT_REMOTE_CONFIG,
    DEFAULT_REMOTE_HOST,
    DEFAULT_REMOTE_LIVE_ENV,
    DEFAULT_REMOTE_PYTHON,
    DEFAULT_REMOTE_REPO,
    CommandRunner,
    build_phase9co,
    local_command_runner,
)
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
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cw_define_final_owner_live_order_decision_gate_scope_after_p9cv import (  # noqa: E402
    CONTRACT_VERSION as P9CW_CONTRACT,
    DEFAULT_OUTPUT_PARENT as P9CW_PARENT,
    P9CX_GATE,
    P9CX_SCOPE,
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
    "hv_balanced_dth60_coinglass_phase9cx_fresh_proof_no_order_replacement_pre_order_control_big_package.v1"
)
APPROVE_P9CX_DECISION = (
    "approve_p9cx_execute_fresh_proof_no_order_replacement_pre_order_control_big_package_only_no_order_no_candidate_no_executor_mutation"
)
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/p9cx_big_package"
)
P9CY_GATE = (
    "P9CY_review_p9cx_fresh_proof_no_order_replacement_pre_order_control_big_package_only_if_separately_requested"
)
P9CY_SCOPE = (
    "review_p9cx_fresh_proof_no_order_replacement_pre_order_control_big_package_before_any_live_order_or_executor_path_change"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Execute the P9CX big package: fresh read-only proof collection, "
            "no-order candidate target-plan replacement dry-run, and pre-order "
            "control readback. P9CX does not call order-test endpoints, submit "
            "orders, execute the candidate, mutate executor input or target "
            "plans, remote sync, invoke supervisor or timer paths, or mutate "
            "live config/operator/timer state."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9cw-summary", default="")
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
    parser.add_argument("--owner-decision", default=APPROVE_P9CX_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default=(
            "user_chat:p9cx_fresh_proof_no_order_replacement_pre_order_control_big_package"
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


def latest_p9cw_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9cw_summary).strip():
        return resolve_path(args.phase9cw_summary)
    return latest_match(P9CW_PARENT, "*/summary.json")


def source_output_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("output_files") or {}).get(key) or "")
    return resolve_path(text) if text.strip() else Path("")


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def p9cw_summary_ready(summary: dict[str, Any]) -> bool:
    return (
        summary.get("contract_version") == P9CW_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9cw_final_owner_live_order_decision_gate_scope_defined")
        is True
        and summary.get("p9cv_sufficient_for_p9cw_scope_definition") is True
        and summary.get("p9cx_big_package_scope_defined") is True
        and summary.get("p9cx_fresh_proof_collection_in_scope") is True
        and summary.get("p9cx_no_order_candidate_replacement_dry_run_in_scope")
        is True
        and summary.get("p9cx_pre_order_control_readback_in_scope") is True
        and int(summary.get("required_fresh_final_decision_evidence_count") or 0)
        == len(EXPECTED_FINAL_EVIDENCE)
        and summary.get("fresh_proofs_collected_in_p9cw") is False
        and summary.get("fresh_remote_proof_collection_approved_in_p9cw") is False
        and summary.get("p9cw_satisfies_final_owner_live_order_gate") is False
        and summary.get("eligible_for_future_p9cx_big_package_execution") is True
        and summary.get("eligible_for_future_live_order_submission") is False
        and summary.get("eligible_for_future_candidate_execution") is False
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
        and summary.get("allowed_next_gate") == P9CX_GATE
        and summary.get("allowed_next_gate_scope") == P9CX_SCOPE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
        and bool(summary.get("baseline_target_plan_sha256"))
        and bool(summary.get("candidate_target_plan_sha256"))
        and summary.get("baseline_target_plan_sha256")
        != summary.get("candidate_target_plan_sha256")
        and summary.get("only_distance_to_high_60_contribution_changed") is True
    )


def p9cw_scope_ready(scope: dict[str, Any]) -> bool:
    components = set(scope.get("p9cx_big_package_components") or [])
    may_execute = set(scope.get("p9cx_may_execute_only") or [])
    may_not = set(scope.get("p9cx_may_not_execute") or [])
    evidence_rows = list(scope.get("required_fresh_final_decision_evidence") or [])
    return (
        scope.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cw_p9cx_big_package_scope.v1"
        and scope.get("scope_definition_only") is True
        and scope.get("future_gate") == P9CX_GATE
        and scope.get("future_gate_scope") == P9CX_SCOPE
        and scope.get("future_gate_must_be_separately_requested") is True
        and components
        == {
            "fresh_proof_collection",
            "no_order_candidate_target_plan_replacement_dry_run",
            "pre_order_control_boundary_readback",
        }
        and "stdout-only read-only remote account and market proof collection"
        in may_execute
        and "local proof_artifacts-only no-order candidate target-plan replacement dry-run"
        in may_execute
        and "pre-order control-boundary readback and post-readback comparison"
        in may_execute
        and "live order submission" in may_not
        and "order-test endpoint call" in may_not
        and "candidate execution" in may_not
        and "actual target-plan replacement" in may_not
        and "actual executor-input mutation" in may_not
        and "timer path load" in may_not
        and "supervisor invocation" in may_not
        and "remote sync" in may_not
        and "remote file write" in may_not
        and {str(row.get("evidence_id")) for row in evidence_rows}
        == set(EXPECTED_FINAL_EVIDENCE)
        and scope.get("p9cw_satisfies_final_owner_live_order_gate") is False
        and scope.get("live_order_submission_authorized") is False
        and scope.get("candidate_execution_authorized") is False
        and scope.get("target_plan_replacement_authorized") is False
        and scope.get("executor_input_mutation_authorized") is False
        and scope.get("only_distance_to_high_60_contribution_changed") is True
    )


def p9cw_evidence_manifest_ready(manifest: dict[str, Any]) -> bool:
    rows = list(manifest.get("evidence") or [])
    return (
        manifest.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cw_p9cx_required_evidence_manifest.v1"
        and manifest.get("scope_definition_only") is True
        and int(manifest.get("evidence_count") or 0) == len(EXPECTED_FINAL_EVIDENCE)
        and {str(row.get("evidence_id")) for row in rows}
        == set(EXPECTED_FINAL_EVIDENCE)
        and manifest.get("all_evidence_must_be_freshly_collected_inside_p9cx")
        is True
        and manifest.get(
            "retained_p9cv_package_evidence_is_not_fresh_final_decision_evidence"
        )
        is True
    )


def p9cw_non_authorization_ready(matrix: dict[str, Any]) -> bool:
    authorizations = dict(matrix.get("authorizations") or {})
    return (
        matrix.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cw_non_authorization.v1"
        and authorizations.get("define_p9cx_big_package_scope") is True
        and authorizations.get("allow_future_p9cx_execution_request") is True
        and authorizations.get("execute_p9cx_in_p9cw") is False
        and authorizations.get("fresh_remote_proof_collection") is False
        and authorizations.get("fresh_remote_account_read") is False
        and authorizations.get("fresh_order_book_read") is False
        and authorizations.get("exchange_filter_read") is False
        and authorizations.get("order_test_endpoint") is False
        and authorizations.get("remote_execution") is False
        and authorizations.get("remote_sync") is False
        and authorizations.get("remote_file_write") is False
        and authorizations.get("final_owner_live_order_gate_approval") is False
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


def p9cw_control_ready(control: dict[str, Any]) -> bool:
    return (
        control.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cw_control_boundary.v1"
        and control.get("scope") == "define_p9cx_big_package_scope_only"
        and control.get("ssh_invoked") is False
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
        and int_zero(control, "orders_submitted")
        and int_zero(control, "orders_canceled")
        and int_zero(control, "fill_count")
        and int_zero(control, "trade_count")
    )


def p9co_summary_ready_for_p9cx(summary: dict[str, Any]) -> bool:
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
        and summary.get("remote_execution_scope")
        == "stdout_read_only_account_market_collectors_only"
        and int_zero(summary, "remote_files_written")
        and summary.get("remote_sync_performed") is False
        and summary.get("account_blocker_cleared_by_p9co") is True
        and summary.get("can_trade_pre") is True
        and summary.get("can_trade_post") is True
        and summary.get("position_fingerprint_stable") is True
        and summary.get("open_order_fingerprint_stable") is True
        and summary.get("balance_fingerprint_stable") is True
        and summary.get("open_order_count_zero_pre_post") is True
        and summary.get("order_cancel_fill_trade_delta_zero") is True
        and summary.get("remote_control_boundary_unchanged") is True
        and summary.get("same_risk_paired_target_plan_binding") is True
        and summary.get("distance_to_high_60_only_delta") is True
        and summary.get("no_order_candidate_target_plan_replacement_dry_run_ready")
        is True
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
        and bool(summary.get("baseline_target_plan_sha256"))
        and bool(summary.get("candidate_target_plan_sha256"))
        and summary.get("baseline_target_plan_sha256")
        != summary.get("candidate_target_plan_sha256")
        and summary.get("only_distance_to_high_60_contribution_changed") is True
        and int_zero(summary, "orders_submitted")
        and int_zero(summary, "orders_canceled")
        and int_zero(summary, "fill_count")
        and int_zero(summary, "trade_count")
    )


def build_p9co_args(args: argparse.Namespace, output_root: Path) -> argparse.Namespace:
    return argparse.Namespace(
        output_root=str(output_root),
        project_profile=args.project_profile,
        phase9cn_summary=args.phase9cn_summary,
        phase9bu_summary=args.phase9bu_summary,
        remote_host=args.remote_host,
        remote_repo=args.remote_repo,
        remote_config=args.remote_config,
        remote_live_env=args.remote_live_env,
        remote_python=args.remote_python,
        expected_egress_ip=args.expected_egress_ip,
        canary_symbol=args.canary_symbol,
        max_history_symbols=args.max_history_symbols,
        ssh_connect_timeout=args.ssh_connect_timeout,
        owner=args.owner,
        owner_decision=APPROVE_P9CO_DECISION,
        owner_decision_source="p9cx_embedded_p9co_read_only_fresh_proof_collection",
    )


def build_pre_order_control_readback(
    *,
    p9cw_summary: dict[str, Any],
    p9co_summary: dict[str, Any],
    ready: bool,
    run_id: str,
) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cx_pre_order_control_readback.v1",
        "run_id": run_id,
        "pre_order_control_readback_ready": ready,
        "source_p9cw_scope_ready": p9cw_summary_ready(p9cw_summary),
        "source_p9co_read_only_fresh_proofs_ready": p9co_summary_ready_for_p9cx(
            p9co_summary
        ),
        "executor_input_expected": "baseline_only",
        "candidate_output_expected": "shadow_or_proof_artifacts_only",
        "final_owner_live_order_gate_approval_collected": False,
        "live_order_submission_authorized": False,
        "candidate_enter_executor_target_plan_path_authorized": False,
        "candidate_execution_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "timer_path_load_authorized": False,
        "supervisor_invocation_authorized": False,
        "order_test_endpoint_called": False,
        "remote_files_written": 0,
        "remote_sync_performed": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
        "baseline_target_plan_sha256": p9co_summary.get("baseline_target_plan_sha256")
        or p9cw_summary.get("baseline_target_plan_sha256"),
        "candidate_target_plan_sha256": p9co_summary.get("candidate_target_plan_sha256")
        or p9cw_summary.get("candidate_target_plan_sha256"),
        "only_distance_to_high_60_contribution_changed": (
            p9co_summary.get("only_distance_to_high_60_contribution_changed") is True
            and p9cw_summary.get("only_distance_to_high_60_contribution_changed")
            is True
        ),
    }


def build_post_order_observation_plan(run_id: str) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cx_post_order_observation_plan.v1",
        "run_id": run_id,
        "plan_only": True,
        "observation_not_executed_in_p9cx": True,
        "requires_future_live_order_gate_before_use": True,
        "required_post_order_checks": [
            "fresh account/order/fill/trade delta after any future canary",
            "post-only maker status or immediate cancel rollback condition",
            "position notional remains within approved max_notional_usdt",
            "operator kill switch remains readable",
            "candidate can be disabled and executor restored to baseline-only",
        ],
        "rollback_conditions": [
            "candidate artifact missing or stale",
            "executor input hash differs from approved baseline or candidate plan",
            "unexpected order/cancel/fill/trade delta",
            "order crosses spread or is not maker-only",
            "remote control boundary changes unexpectedly",
        ],
        "live_order_submission_authorized": False,
    }


def build_fresh_final_decision_proof_bundle(
    *,
    p9co_summary: dict[str, Any],
    pre_order_control: dict[str, Any],
    post_order_plan: dict[str, Any],
    run_id: str,
) -> dict[str, Any]:
    p9co_outputs = dict(p9co_summary.get("output_files") or {})
    proof_rows = [
        proof_row(
            "pit_safe_v2v3_account_proof",
            p9co_summary.get("pit_safe_v2v3_account_proof_ready") is True,
            [p9co_outputs.get("pit_safe_v2v3_account_proof", "")],
        ),
        proof_row(
            "fresh_position_open_order_balance_fingerprints",
            p9co_summary.get("position_fingerprint_stable") is True
            and p9co_summary.get("open_order_fingerprint_stable") is True
            and p9co_summary.get("balance_fingerprint_stable") is True,
            [
                p9co_outputs.get("account_delta_acceptance", ""),
                p9co_outputs.get("market_proof_collection_delta_acceptance", ""),
            ],
        ),
        proof_row(
            "fresh_order_trade_history_delta",
            p9co_summary.get("order_cancel_fill_trade_delta_zero") is True,
            [
                p9co_outputs.get("account_history_delta_acceptance", ""),
                p9co_outputs.get("market_proof_collection_delta_acceptance", ""),
            ],
        ),
        proof_row(
            "fresh_order_book_and_exchange_filters",
            p9co_summary.get("fresh_order_book_read_performed") is True
            and p9co_summary.get("exchange_filter_read_performed") is True,
            [
                p9co_outputs.get("fresh_order_book", ""),
                p9co_outputs.get("exchange_filter_readback", ""),
            ],
        ),
        proof_row(
            "same_risk_paired_target_plan_binding",
            p9co_summary.get("same_risk_paired_target_plan_binding") is True,
            [p9co_outputs.get("no_order_candidate_target_plan_replacement_dry_run_summary", "")],
        ),
        proof_row(
            "distance_to_high_60_only_delta",
            p9co_summary.get("distance_to_high_60_only_delta") is True
            and p9co_summary.get("only_distance_to_high_60_contribution_changed")
            is True,
            [p9co_outputs.get("no_order_candidate_target_plan_replacement_dry_run_summary", "")],
        ),
        proof_row(
            "no_order_candidate_target_plan_replacement_dry_run",
            p9co_summary.get("no_order_candidate_target_plan_replacement_dry_run_ready")
            is True,
            [p9co_outputs.get("no_order_candidate_target_plan_replacement_dry_run_summary", "")],
        ),
        proof_row(
            "kill_switch_and_rollback_readback",
            p9co_summary.get("remote_control_boundary_unchanged") is True,
            [p9co_outputs.get("kill_switch_rollback_readback", "")],
        ),
        proof_row(
            "final_owner_live_order_gate_approval",
            False,
            [],
            status_override="not_collected_by_design",
        ),
        proof_row(
            "explicit_final_owner_live_order_decision",
            False,
            [],
            status_override="not_collected_by_design",
        ),
        proof_row(
            "pre_order_control_boundary_readback",
            pre_order_control.get("pre_order_control_readback_ready") is True,
            [],
        ),
        proof_row(
            "post_order_observation_and_rollback_plan",
            post_order_plan.get("plan_only") is True,
            [],
            status_override="plan_prepared_not_executed",
        ),
    ]
    ready_count = sum(1 for row in proof_rows if row["status"] in {"ready", "plan_prepared_not_executed"})
    missing_count = sum(1 for row in proof_rows if row["status"] == "not_collected_by_design")
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cx_fresh_final_decision_proof_bundle.v1",
        "run_id": run_id,
        "proof_rows": proof_rows,
        "proof_row_count": len(proof_rows),
        "read_only_or_plan_ready_count": ready_count,
        "not_collected_by_design_count": missing_count,
        "all_read_only_fresh_proofs_ready": p9co_summary.get("read_only_fresh_proofs_ready")
        is True,
        "pre_order_control_readback_ready": pre_order_control.get(
            "pre_order_control_readback_ready"
        )
        is True,
        "post_order_observation_plan_prepared": post_order_plan.get("plan_only") is True,
        "final_owner_live_order_gate_approval_collected": False,
        "p9cx_satisfies_final_owner_live_order_gate": False,
    }


def proof_row(
    proof_id: str,
    ready: bool,
    source_paths: list[str],
    *,
    status_override: str = "",
) -> dict[str, Any]:
    status = status_override or ("ready" if ready else "blocked")
    return {
        "proof_id": proof_id,
        "max_age_seconds": EXPECTED_FINAL_EVIDENCE[proof_id],
        "status": status,
        "ready": ready,
        "sources": [
            evidence_file(resolve_path(path)) for path in source_paths if str(path).strip()
        ],
    }


def build_phase9cx(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
    command_runner: CommandRunner = local_command_runner,
    p9co_builder: Callable[..., tuple[dict[str, Any], int]] = build_phase9co,
) -> tuple[dict[str, Any], int]:
    started_at = now_fn()
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9cx" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    p9cw_path = latest_p9cw_summary(args)
    p9cw = load_optional(p9cw_path)
    scope_path = source_output_path(p9cw, "p9cx_big_package_scope")
    evidence_manifest_path = source_output_path(p9cw, "required_evidence_manifest")
    p9cw_non_auth_path = source_output_path(p9cw, "non_authorization")
    p9cw_control_path = source_output_path(p9cw, "control_boundary_readback")
    scope = load_optional(scope_path)
    evidence_manifest = load_optional(evidence_manifest_path)
    p9cw_non_auth = load_optional(p9cw_non_auth_path)
    p9cw_control = load_optional(p9cw_control_path)
    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)
    owner_decision_ok = str(args.owner_decision) == APPROVE_P9CX_DECISION

    pre_checks = {
        "owner_decision_p9cx_big_package_execute_recorded": owner_decision_ok,
        "project_profile_exists": bool(project_profile),
        "current_stage_is_stage3": str(project_profile.get("current_stage") or "")
        == "stage_3_human_approved_execution",
        "p9cw_summary_exists": bool(p9cw),
        "p9cw_summary_ready_for_p9cx": p9cw_summary_ready(p9cw),
        "p9cw_scope_ready": p9cw_scope_ready(scope),
        "p9cw_required_evidence_manifest_ready": p9cw_evidence_manifest_ready(
            evidence_manifest
        ),
        "p9cw_non_authorization_ready": p9cw_non_authorization_ready(p9cw_non_auth),
        "p9cw_control_boundary_ready": p9cw_control_ready(p9cw_control),
        "remote_host_matches_expected_runner": str(args.remote_host)
        == DEFAULT_REMOTE_HOST,
        "remote_repo_matches_expected_runner": str(args.remote_repo)
        == DEFAULT_REMOTE_REPO,
        "canary_symbol_matches_scope": str(args.canary_symbol) == CANARY_SYMBOL,
    }
    blockers = [key for key, value in pre_checks.items() if not value]

    owner_record = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cx_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "execute_p9cx_big_package_no_order_no_candidate_no_executor_mutation",
        "recorded_at_utc": iso_z(started_at),
        "p9cx_big_package_execution_approved": owner_decision_ok,
        "live_order_submission_approved": False,
        "candidate_execution_approved": False,
        "target_plan_replacement_approved": False,
        "executor_input_mutation_approved": False,
        "timer_or_supervisor_change_approved": False,
    }

    p9co_summary: dict[str, Any] = {}
    p9co_exit_code = 2
    p9co_exception = ""
    if not blockers:
        try:
            p9co_summary, p9co_exit_code = p9co_builder(
                build_p9co_args(args, root / "p9co"),
                now_fn=lambda: started_at,
                command_runner=command_runner,
            )
        except Exception as exc:  # pragma: no cover - retained crash-to-blocker guard
            p9co_exception = f"{type(exc).__name__}: {exc}"
            p9co_summary = {
                "contract_version": P9CO_CONTRACT,
                "run_id": run_id,
                "status": "blocked",
                "blockers": ["embedded_p9co_exception"],
                "exception": p9co_exception,
                "output_files": {},
            }
            p9co_exit_code = 2
            blockers.append("embedded_p9co_exception")
        if p9co_exit_code != 0:
            blockers.append("embedded_p9co_read_only_fresh_proof_collection_failed")
        if not p9co_summary_ready_for_p9cx(p9co_summary):
            blockers.append("embedded_p9co_summary_not_ready_for_p9cx")

    p9co_ready = p9co_summary_ready_for_p9cx(p9co_summary)
    ready = not blockers and p9co_ready
    pre_order_control = build_pre_order_control_readback(
        p9cw_summary=p9cw,
        p9co_summary=p9co_summary,
        ready=ready,
        run_id=run_id,
    )
    post_order_plan = build_post_order_observation_plan(run_id)
    proof_bundle = build_fresh_final_decision_proof_bundle(
        p9co_summary=p9co_summary,
        pre_order_control=pre_order_control,
        post_order_plan=post_order_plan,
        run_id=run_id,
    )
    if proof_bundle.get("all_read_only_fresh_proofs_ready") is not True and not blockers:
        blockers.append("p9cx_read_only_fresh_proofs_not_ready")
    if pre_order_control.get("pre_order_control_readback_ready") is not True and not blockers:
        blockers.append("p9cx_pre_order_control_readback_not_ready")
    blockers = sorted(set(blockers))
    status = "ready" if not blockers else "blocked"

    p9co_outputs = dict(p9co_summary.get("output_files") or {})
    p9co_summary_path = p9co_outputs.get("summary", "")
    source_binding = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cx_source_binding.v1",
        "run_id": run_id,
        "source_p9cw_summary": evidence_file(p9cw_path),
        "source_p9cw_scope": evidence_file(scope_path),
        "embedded_p9co_summary": evidence_file(resolve_path(p9co_summary_path))
        if str(p9co_summary_path).strip()
        else {"path": "", "exists": False, "sha256": ""},
        "embedded_p9co_run_id": p9co_summary.get("run_id"),
        "embedded_p9co_status": p9co_summary.get("status"),
        "embedded_p9co_exit_code": p9co_exit_code,
        "embedded_p9co_exception": p9co_exception,
        "baseline_target_plan_sha256": p9co_summary.get("baseline_target_plan_sha256")
        or p9cw.get("baseline_target_plan_sha256"),
        "candidate_target_plan_sha256": p9co_summary.get("candidate_target_plan_sha256")
        or p9cw.get("candidate_target_plan_sha256"),
        "same_risk_paired_target_plan_binding": p9co_summary.get(
            "same_risk_paired_target_plan_binding"
        )
        is True,
        "only_distance_to_high_60_contribution_changed": p9co_summary.get(
            "only_distance_to_high_60_contribution_changed"
        )
        is True,
    }
    non_authorization = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cx_non_authorization.v1",
        "run_id": run_id,
        "authorizations": {
            "execute_p9cx_big_package": owner_decision_ok,
            "fresh_read_only_remote_proof_collection": owner_decision_ok,
            "no_order_candidate_target_plan_replacement_dry_run": owner_decision_ok,
            "pre_order_control_readback": owner_decision_ok,
            "order_test_endpoint": False,
            "remote_files_written": False,
            "remote_sync": False,
            "supervisor_invocation": False,
            "timer_path_load": False,
            "production_timer_service_load": False,
            "actual_candidate_executor_target_path_entry": False,
            "candidate_execution": False,
            "live_order_submission": False,
            "actual_target_plan_replacement": False,
            "actual_executor_input_mutation": False,
            "live_config_mutation": False,
            "operator_state_mutation": False,
            "timer_or_service_mutation": False,
            "stage_governance_change": False,
        },
    }
    control = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cx_control_boundary.v1",
        "run_id": run_id,
        "scope": "fresh_proof_no_order_replacement_pre_order_control_big_package",
        "fresh_remote_proof_collection_performed": p9co_summary.get(
            "fresh_remote_proof_collection_performed_in_p9co"
        )
        is True,
        "fresh_remote_account_read_performed": p9co_summary.get(
            "fresh_remote_account_read_performed"
        )
        is True,
        "fresh_order_book_read_performed": p9co_summary.get(
            "fresh_order_book_read_performed"
        )
        is True,
        "exchange_filter_read_performed": p9co_summary.get(
            "exchange_filter_read_performed"
        )
        is True,
        "pre_order_control_readback_performed": pre_order_control.get(
            "pre_order_control_readback_ready"
        )
        is True,
        "order_test_endpoint_called": False,
        "remote_files_written": 0,
        "remote_sync_performed": False,
        "entered_timer_path": False,
        "ran_supervisor": False,
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

    output_files = {
        "summary": str(root / "summary.json"),
        "owner_decision_record": str(root / "owner_decision_record.json"),
        "fresh_final_decision_proof_bundle": str(
            proof_root / "fresh_final_decision_proof_bundle.json"
        ),
        "pre_order_control_readback": str(proof_root / "pre_order_control_readback.json"),
        "post_order_observation_plan": str(
            proof_root / "post_order_observation_plan.json"
        ),
        "p9co_source_binding": str(proof_root / "p9co_source_binding.json"),
        "non_authorization": str(proof_root / "non_authorization.json"),
        "control_boundary_readback": str(proof_root / "control_boundary_readback.json"),
        "embedded_p9co_summary": str(p9co_summary_path),
        "report": str(root / "p9cx_big_package.md"),
    }
    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "status": status,
        "blockers": blockers,
        "p9cx_fresh_proof_no_order_replacement_pre_order_control_big_package_ready": status
        == "ready",
        "p9cw_sufficient_for_p9cx_big_package_execution": p9cw_summary_ready(p9cw),
        "fresh_proof_collection_performed_in_p9cx": p9co_summary.get(
            "fresh_remote_proof_collection_performed_in_p9co"
        )
        is True,
        "fresh_remote_account_read_performed": p9co_summary.get(
            "fresh_remote_account_read_performed"
        )
        is True,
        "fresh_order_book_read_performed": p9co_summary.get(
            "fresh_order_book_read_performed"
        )
        is True,
        "exchange_filter_read_performed": p9co_summary.get(
            "exchange_filter_read_performed"
        )
        is True,
        "pit_safe_v2v3_account_proof_ready": p9co_summary.get(
            "pit_safe_v2v3_account_proof_ready"
        )
        is True,
        "account_blocker_cleared_by_p9cx": p9co_summary.get(
            "account_blocker_cleared_by_p9co"
        )
        is True,
        "read_only_fresh_proofs_ready": p9co_summary.get(
            "read_only_fresh_proofs_ready"
        )
        is True,
        "no_order_candidate_target_plan_replacement_dry_run_ready": p9co_summary.get(
            "no_order_candidate_target_plan_replacement_dry_run_ready"
        )
        is True,
        "candidate_target_plan_replacement_semantics_proven": p9co_summary.get(
            "no_order_candidate_target_plan_replacement_dry_run_ready"
        )
        is True,
        "same_risk_paired_target_plan_binding": p9co_summary.get(
            "same_risk_paired_target_plan_binding"
        )
        is True,
        "distance_to_high_60_only_delta": p9co_summary.get(
            "distance_to_high_60_only_delta"
        )
        is True,
        "only_distance_to_high_60_contribution_changed": p9co_summary.get(
            "only_distance_to_high_60_contribution_changed"
        )
        is True,
        "pre_order_control_readback_ready": pre_order_control.get(
            "pre_order_control_readback_ready"
        )
        is True,
        "post_order_observation_plan_prepared": post_order_plan.get("plan_only") is True,
        "remote_control_boundary_unchanged": p9co_summary.get(
            "remote_control_boundary_unchanged"
        )
        is True,
        "final_owner_live_order_gate_approval_collected": False,
        "explicit_final_owner_live_order_decision_collected": False,
        "p9cx_satisfies_final_owner_live_order_gate": False,
        "eligible_for_future_p9cy_review": status == "ready",
        "eligible_for_future_live_order_submission": False,
        "eligible_for_future_candidate_execution": False,
        "candidate_enter_executor_target_plan_path_authorized": False,
        "candidate_execution_authorized": False,
        "live_order_submission_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "timer_path_load_authorized": False,
        "supervisor_invocation_authorized": False,
        "order_test_endpoint_called": False,
        "remote_execution_performed": p9co_summary.get("remote_execution_performed")
        is True,
        "remote_execution_scope": p9co_summary.get("remote_execution_scope")
        or "stdout_read_only_account_market_collectors_only",
        "remote_files_written": 0,
        "remote_sync_performed": False,
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
        "baseline_target_plan_sha256": source_binding["baseline_target_plan_sha256"],
        "candidate_target_plan_sha256": source_binding["candidate_target_plan_sha256"],
        "fresh_final_decision_evidence_total_count": len(EXPECTED_FINAL_EVIDENCE),
        "fresh_final_decision_evidence_read_only_or_plan_ready_count": proof_bundle[
            "read_only_or_plan_ready_count"
        ],
        "fresh_final_decision_evidence_not_collected_by_design_count": proof_bundle[
            "not_collected_by_design_count"
        ],
        "embedded_p9co_exception": p9co_exception,
        "allowed_next_gate": P9CY_GATE,
        "allowed_next_gate_scope": P9CY_SCOPE,
        "allowed_next_gate_must_be_separately_requested": True,
        "source_evidence": {
            "phase9cw_summary": evidence_file(p9cw_path),
            "phase9cw_scope": evidence_file(scope_path),
            "phase9cw_required_evidence_manifest": evidence_file(evidence_manifest_path),
            "phase9cw_non_authorization": evidence_file(p9cw_non_auth_path),
            "phase9cw_control_boundary": evidence_file(p9cw_control_path),
            "project_profile": evidence_file(project_profile_path),
        },
        "pre_checks": pre_checks,
        "output_files": output_files,
    }

    write_json(Path(output_files["owner_decision_record"]), owner_record)
    write_json(Path(output_files["fresh_final_decision_proof_bundle"]), proof_bundle)
    write_json(Path(output_files["pre_order_control_readback"]), pre_order_control)
    write_json(Path(output_files["post_order_observation_plan"]), post_order_plan)
    write_json(Path(output_files["p9co_source_binding"]), source_binding)
    write_json(Path(output_files["non_authorization"]), non_authorization)
    write_json(Path(output_files["control_boundary_readback"]), control)
    write_json(Path(output_files["summary"]), summary)
    Path(output_files["report"]).write_text(render_markdown(summary), encoding="utf-8")
    return summary, 0 if status == "ready" else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9CX Fresh Proof No-Order Replacement Pre-Order Control Big Package",
        "",
        f"`Status: {summary['status']}`",
        "",
        "P9CX executes the retained no-order big package: fresh read-only proof collection, no-order candidate target-plan replacement dry-run, and pre-order control readback. It does not call order-test endpoints, execute the candidate, mutate executor input or target plans, invoke supervisor/timer paths, remote sync, or submit orders.",
        "",
        "## Result",
        "",
        "```text",
        "p9cx_fresh_proof_no_order_replacement_pre_order_control_big_package_ready = "
        f"{str(bool(summary['p9cx_fresh_proof_no_order_replacement_pre_order_control_big_package_ready'])).lower()}",
        "fresh_proof_collection_performed_in_p9cx = "
        f"{str(bool(summary['fresh_proof_collection_performed_in_p9cx'])).lower()}",
        "read_only_fresh_proofs_ready = "
        f"{str(bool(summary['read_only_fresh_proofs_ready'])).lower()}",
        "no_order_candidate_target_plan_replacement_dry_run_ready = "
        f"{str(bool(summary['no_order_candidate_target_plan_replacement_dry_run_ready'])).lower()}",
        "pre_order_control_readback_ready = "
        f"{str(bool(summary['pre_order_control_readback_ready'])).lower()}",
        "final_owner_live_order_gate_approval_collected = false",
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
    summary, exit_code = build_phase9cx(parse_args(argv))
    print(
        "p9cx_fresh_proof_no_order_replacement_pre_order_control_big_package_ready="
        + str(
            bool(
                summary[
                    "p9cx_fresh_proof_no_order_replacement_pre_order_control_big_package_ready"
                ]
            )
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
