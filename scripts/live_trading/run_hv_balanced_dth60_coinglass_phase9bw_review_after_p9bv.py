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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bv_no_order_candidate_target_plan_replacement_dry_run import (  # noqa: E402
    CONTRACT_VERSION as P9BV_CONTRACT,
    DEFAULT_OUTPUT_PARENT as P9BV_PARENT,
    P9BW_GATE,
    P9BW_SCOPE,
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


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9bw_review_after_p9bv.v1"
APPROVE_P9BW_DECISION = (
    "approve_p9bw_review_p9bv_sufficiency_for_live_order_gate_discussion_only"
)
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/p9bw_review_p9bv"
P9BX_GATE = "P9BX_define_live_order_gate_scope_only_if_separately_requested"
P9BX_SCOPE = (
    "define_live_order_gate_scope_and_required_fresh_proofs_only_no_order_no_execution"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Review retained P9BV no-order replacement dry-run evidence for "
            "sufficiency to enter a future live-order gate discussion. P9BW is "
            "review-only: it does not define P9BX scope, approve live orders, "
            "enter candidate executor path, mutate target plans or executor input, "
            "invoke supervisor/timer/remote paths, or submit orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9bv-summary", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9BW_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:p9bw_review_p9bv_sufficiency_for_live_order_gate_discussion_only",
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


def latest_p9bv_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9bv_summary).strip():
        return resolve_path(args.phase9bv_summary)
    return latest_match(P9BV_PARENT, "*/summary.json")


def source_output_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("output_files") or {}).get(key) or "")
    return resolve_path(text) if text.strip() else Path("")


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def output_under_proof_artifacts(path: Path) -> bool:
    return "proof_artifacts" in [part.lower() for part in path.resolve().parts]


def p9bv_summary_ready(summary: dict[str, Any]) -> bool:
    return (
        summary.get("contract_version") == P9BV_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9bv_no_order_replacement_dry_run_ready") is True
        and summary.get("candidate_target_plan_replacement_semantics_proven") is True
        and summary.get("exact_p9bu_terms_applied") is True
        and summary.get("same_timestamp_context") is True
        and summary.get("same_risk_inputs") is True
        and summary.get("candidate_plan_differs_from_baseline") is True
        and summary.get("simulated_executor_input_replacement_matches_candidate") is True
        and summary.get("actual_executor_input_changed") is False
        and summary.get("actual_target_plan_replaced") is False
        and summary.get("only_distance_to_high_60_contribution_changed") is True
        and int(summary.get("changed_symbol_count") or 0) == 1
        and int(summary.get("order_intent_preview_count") or 0) == 1
        and float(summary.get("risk_ceiling_usdt") or 0) == 25.0
        and float(summary.get("max_notional_usdt") or 0) == 10.0
        and summary.get("order_type") == "post_only_limit"
        and summary.get("time_in_force") == "GTX"
        and summary.get("candidate_enter_executor_target_plan_path_authorized") is False
        and summary.get("candidate_execution_authorized") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("target_plan_replacement_authorized") is False
        and summary.get("executor_input_mutation_authorized") is False
        and summary.get("allowed_next_gate") == P9BW_GATE
        and summary.get("allowed_next_gate_scope") == P9BW_SCOPE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
        and int_zero(summary, "orders_submitted")
        and int_zero(summary, "fill_count")
    )


def replacement_dry_run_ready(replacement: dict[str, Any], summary: dict[str, Any]) -> bool:
    baseline = summary.get("baseline_target_plan_sha256")
    candidate = summary.get("candidate_target_plan_sha256")
    return (
        replacement.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9bv_replacement_dry_run.v1"
        and replacement.get("dry_run_mode") == "shadow_executor_reference_only"
        and replacement.get("baseline_generated_first") is True
        and replacement.get("candidate_generated_after_baseline") is True
        and replacement.get("same_timestamp_context") is True
        and replacement.get("same_risk_inputs") is True
        and replacement.get("baseline_target_plan_sha256") == baseline
        and replacement.get("candidate_target_plan_sha256") == candidate
        and replacement.get("candidate_plan_differs_from_baseline") is True
        and replacement.get("simulated_executor_input_plan_sha256_before_dry_run") == baseline
        and replacement.get("simulated_executor_input_plan_sha256_after_dry_run") == candidate
        and replacement.get("simulated_executor_input_replacement_matches_candidate") is True
        and replacement.get("actual_executor_input_plan_sha256_before_dry_run") == baseline
        and replacement.get("actual_executor_input_plan_sha256_after_dry_run") == baseline
        and replacement.get("actual_executor_input_changed") is False
        and replacement.get("actual_target_plan_replaced") is False
        and replacement.get("candidate_entered_actual_executor_target_plan_path") is False
        and replacement.get("candidate_replacement_semantics_proven_in_shadow") is True
        and replacement.get("candidate_artifacts_under_proof_artifacts_only") is True
        and int_zero(replacement, "orders_submitted")
        and int_zero(replacement, "fill_count")
    )


def target_plan_diff_ready(diff: dict[str, Any]) -> bool:
    return (
        diff.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9bv_target_plan_diff.v1"
        and diff.get("changed_symbols") == ["BTCUSDT"]
        and int(diff.get("changed_symbol_count") or 0) == 1
        and float(diff.get("distance_to_high_60_contribution_delta_abs_sum") or 0) > 0
        and float(diff.get("non_target_contribution_delta_abs_sum") or 0) == 0.0
        and diff.get("only_distance_to_high_60_contribution_changed") is True
    )


def order_preview_ready(preview: dict[str, Any]) -> bool:
    orders = list(preview.get("orders") or [])
    return (
        preview.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9bv_order_intent_preview.v1"
        and preview.get("preview_only") is True
        and int(preview.get("order_intent_count") or 0) == 1
        and len(orders) == 1
        and orders[0].get("symbol") == "BTCUSDT"
        and orders[0].get("side") == "BUY"
        and float(orders[0].get("notional_usdt") or 0) == 10.0
        and orders[0].get("order_type") == "post_only_limit"
        and orders[0].get("time_in_force") == "GTX"
        and orders[0].get("preview_only") is True
        and orders[0].get("would_submit_order") is False
        and preview.get("within_max_orders_per_cycle") is True
        and preview.get("within_max_symbols_per_cycle") is True
        and preview.get("within_max_notional") is True
        and preview.get("market_orders_forbidden") is True
        and int_zero(preview, "orders_submitted")
        and int_zero(preview, "fill_count")
    )


def non_authorization_ready(matrix: dict[str, Any]) -> bool:
    authorizations = dict(matrix.get("authorizations") or {})
    return (
        matrix.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9bv_non_authorization_matrix.v1"
        and authorizations.get("no_order_shadow_replacement_dry_run") is True
        and authorizations.get("candidate_replacement_semantics_shadow_proof") is True
        and authorizations.get("actual_candidate_executor_target_path_entry") is False
        and authorizations.get("candidate_execution") is False
        and authorizations.get("live_order_submission") is False
        and authorizations.get("actual_target_plan_replacement") is False
        and authorizations.get("actual_executor_input_mutation") is False
        and authorizations.get("live_config_mutation") is False
        and authorizations.get("operator_state_mutation") is False
        and authorizations.get("timer_or_service_mutation") is False
        and authorizations.get("supervisor_invocation") is False
        and authorizations.get("remote_sync") is False
        and authorizations.get("remote_execution") is False
    )


def control_boundary_ready(control: dict[str, Any]) -> bool:
    return (
        control.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9bv_control_boundary_readback.v1"
        and control.get("scope") == "no_order_shadow_executor_replacement_dry_run_only"
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


def retained_files_ready(paths: dict[str, Path]) -> bool:
    required = (
        "replacement_dry_run",
        "target_plan_diff",
        "order_intent_preview",
        "non_authorization_matrix",
        "control_boundary_readback",
    )
    return all(
        paths[key].exists()
        and paths[key].is_file()
        and output_under_proof_artifacts(paths[key])
        for key in required
    )


def build_p9bw_review_after_p9bv(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    now = now_fn()
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9bw" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    p9bv_summary_path = latest_p9bv_summary(args)
    p9bv = load_optional(p9bv_summary_path)
    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)
    paths = {
        "replacement_dry_run": source_output_path(p9bv, "replacement_dry_run"),
        "target_plan_diff": source_output_path(p9bv, "target_plan_diff"),
        "order_intent_preview": source_output_path(p9bv, "order_intent_preview"),
        "non_authorization_matrix": source_output_path(p9bv, "non_authorization_matrix"),
        "control_boundary_readback": source_output_path(p9bv, "control_boundary_readback"),
    }
    replacement = load_optional(paths["replacement_dry_run"])
    diff = load_optional(paths["target_plan_diff"])
    preview = load_optional(paths["order_intent_preview"])
    matrix = load_optional(paths["non_authorization_matrix"])
    control = load_optional(paths["control_boundary_readback"])

    owner_decision_ok = str(args.owner_decision) == APPROVE_P9BW_DECISION
    checks = {
        "owner_decision_p9bw_review_recorded": owner_decision_ok,
        "project_profile_exists": bool(project_profile),
        "current_stage_is_stage3": str(project_profile.get("current_stage") or "")
        == "stage_3_human_approved_execution",
        "p9bv_summary_exists": bool(p9bv),
        "p9bv_summary_ready": p9bv_summary_ready(p9bv),
        "retained_proof_files_exist_under_proof_artifacts": retained_files_ready(paths),
        "replacement_dry_run_ready": replacement_dry_run_ready(replacement, p9bv),
        "target_plan_diff_ready": target_plan_diff_ready(diff),
        "order_preview_ready": order_preview_ready(preview),
        "non_authorization_matrix_ready": non_authorization_ready(matrix),
        "control_boundary_ready": control_boundary_ready(control),
    }
    blockers = [key for key, value in checks.items() if not value]
    ready = not blockers

    owner_record = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bw_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "review_p9bv_sufficiency_for_live_order_gate_discussion_only",
        "recorded_at_utc": iso_z(now),
        "review_approved": owner_decision_ok,
        "live_order_gate_approved": False,
        "candidate_execution_approved": False,
        "live_order_submission_approved": False,
    }

    sufficiency_checklist = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bw_sufficiency_checklist.v1",
        "run_id": run_id,
        "status": "ready" if ready else "blocked",
        "checks": checks,
        "blockers": blockers,
        "p9bv_retained_evidence_sufficient_for_live_order_gate_discussion": ready,
        "eligible_for_future_live_order_gate_discussion": ready,
        "eligible_for_future_live_order_submission": False,
        "required_before_any_future_live_order_submission": [
            "separately requested live-order gate scope definition",
            "fresh account, position, open-order, fill, and trade fingerprints",
            "fresh order-book and exchange filter proof",
            "explicit operator acceptance of P9BU risk/order terms",
            "candidate target-plan hash bound to executor input in a no-order gate",
            "kill switch and rollback command readback on the target runner",
            "final owner live-order gate approval",
        ],
    }

    non_authorization_matrix = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bw_non_authorization_matrix.v1",
        "run_id": run_id,
        "authorizations": {
            "review_p9bv_retained_evidence": ready,
            "enter_live_order_gate_discussion": ready,
            "define_p9bx_scope": False,
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

    control_boundary = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bw_control_boundary_readback.v1",
        "run_id": run_id,
        "scope": "retained_review_only",
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

    review_packet = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bw_review_packet.v1",
        "run_id": run_id,
        "status": "ready" if ready else "blocked",
        "review_scope": "p9bv_retained_evidence_sufficiency_for_live_order_gate_discussion_only",
        "source_p9bv_summary": evidence_file(p9bv_summary_path),
        "sufficiency_checklist": sufficiency_checklist,
        "live_order_gate_approved": False,
        "decision": (
            "sufficient_for_future_live_order_gate_discussion_only"
            if ready
            else "blocked"
        ),
    }

    owner_path = root / "owner_decision_record.json"
    checklist_path = proof_root / "sufficiency.json"
    review_path = proof_root / "review.json"
    matrix_path = proof_root / "non_authorization.json"
    control_path = proof_root / "control.json"
    summary_path = root / "summary.json"
    report_path = root / "p9bw_review_p9bv.md"

    output_files = {
        "summary": str(summary_path),
        "owner_decision_record": str(owner_path),
        "sufficiency_checklist": str(checklist_path),
        "review_packet": str(review_path),
        "non_authorization_matrix": str(matrix_path),
        "control_boundary_readback": str(control_path),
        "report": str(report_path),
    }

    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "status": "ready" if ready else "blocked",
        "blockers": blockers,
        "p9bw_review_after_p9bv_ready": ready,
        "p9bv_retained_evidence_sufficient_for_live_order_gate_discussion": ready,
        "eligible_for_future_live_order_gate_discussion": ready,
        "eligible_for_future_live_order_submission": False,
        "live_order_gate_approved": False,
        "allowed_next_gate": P9BX_GATE,
        "allowed_next_gate_scope": P9BX_SCOPE,
        "allowed_next_gate_must_be_separately_requested": True,
        "source_p9bv_summary_sha256": evidence_file(p9bv_summary_path).get("sha256", ""),
        "baseline_target_plan_sha256": p9bv.get("baseline_target_plan_sha256"),
        "candidate_target_plan_sha256": p9bv.get("candidate_target_plan_sha256"),
        "simulated_executor_input_replacement_matches_candidate": p9bv.get(
            "simulated_executor_input_replacement_matches_candidate"
        ),
        "actual_executor_input_changed": False,
        "actual_target_plan_replaced": False,
        "only_distance_to_high_60_contribution_changed": p9bv.get(
            "only_distance_to_high_60_contribution_changed"
        ),
        "changed_symbol_count": p9bv.get("changed_symbol_count"),
        "order_intent_preview_count": p9bv.get("order_intent_preview_count"),
        "candidate_enter_executor_target_plan_path_authorized": False,
        "candidate_execution_authorized": False,
        "live_order_submission_authorized": False,
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
        "source_evidence": {
            "phase9bv_summary": evidence_file(p9bv_summary_path),
            "replacement_dry_run": evidence_file(paths["replacement_dry_run"]),
            "target_plan_diff": evidence_file(paths["target_plan_diff"]),
            "order_intent_preview": evidence_file(paths["order_intent_preview"]),
            "phase9bv_non_authorization": evidence_file(paths["non_authorization_matrix"]),
            "phase9bv_control_boundary": evidence_file(paths["control_boundary_readback"]),
            "project_profile": evidence_file(project_profile_path),
        },
        "output_files": output_files,
    }

    write_json(owner_path, owner_record)
    write_json(checklist_path, sufficiency_checklist)
    write_json(review_path, review_packet)
    write_json(matrix_path, non_authorization_matrix)
    write_json(control_path, control_boundary)
    write_json(summary_path, summary)
    report_path.write_text(
        "\n".join(
            [
                "# hv_balanced DTH60/CoinGlass P9BW Review After P9BV",
                "",
                f"`Status: {summary['status']}`",
                "",
                "## Decision",
                "",
                "P9BW reviews retained P9BV no-order replacement dry-run evidence and finds it sufficient only to enter a future live-order gate discussion. P9BW does not approve live orders, candidate execution, actual target-plan replacement, executor-input mutation, supervisor/timer/remote activity, or P9BX scope itself.",
                "",
                "```text",
                f"p9bv_retained_evidence_sufficient_for_live_order_gate_discussion = {str(ready).lower()}",
                "live_order_gate_approved = false",
                "candidate_execution_authorized = false",
                "live_order_submission_authorized = false",
                "target_plan_replacement_authorized = false",
                "executor_input_mutation_authorized = false",
                "orders_submitted = 0",
                "fill_count = 0",
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )

    return summary, 0 if ready else 2


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_p9bw_review_after_p9bv(parse_args(argv))
    print(f"status={summary['status']}")
    print(f"run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
