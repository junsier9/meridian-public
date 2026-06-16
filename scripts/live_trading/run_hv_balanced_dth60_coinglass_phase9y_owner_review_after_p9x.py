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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    current_supervisor_loads_hook,
    evidence_file,
    file_sha256,
    latest_match,
    load_optional,
    resolve_path,
    write_json,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9tuv_proof_only_corridor import (  # noqa: E402
    HOOK_MODULE,
    LIVE_CONFIG_DIR,
    PROJECT_PROFILE,
    SUPERVISOR_PATH,
    tree_sha256,
)


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9y_owner_review_after_p9x.v1"
APPROVE_P9Y_DECISION = "approve_p9y_review_p9x_default_off_dry_load_only"
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9y_owner_review_after_p9x"
PHASE9X_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9x_default_off_timer_path_dry_load"
P9Z_GATE = "P9Z_observe_only_default_off_timer_path_readback_owner_gate_only_if_separately_requested"
P9X_CONTRACT = "hv_balanced_dth60_coinglass_phase9x_default_off_timer_path_dry_load.v1"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "P9Y reviews retained P9X default-off dry-load evidence and decides "
            "whether a separate owner gate may discuss observe-only timer-path readback. "
            "It does not load a hook, run the supervisor, mutate config/state, or submit orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9x-summary", default="")
    parser.add_argument("--hook-module", default=HOOK_MODULE)
    parser.add_argument("--supervisor", default=SUPERVISOR_PATH)
    parser.add_argument("--live-config-dir", default=LIVE_CONFIG_DIR)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9Y_DECISION)
    parser.add_argument("--owner-decision-source", default="user_chat:request_p9y_p9z_p9aa")
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def zero_orders_fills(payload: dict[str, Any]) -> bool:
    return int_zero(payload, "orders_submitted") and int_zero(payload, "fill_count")


def owner_decision_record(args: argparse.Namespace, generated_at: datetime) -> dict[str, Any]:
    approved = args.owner_decision == APPROVE_P9Y_DECISION
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9y_owner_decision.v1",
        "recorded_at_utc": iso_z(generated_at),
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "review_p9x_sufficiency_for_next_owner_gate_only",
        "decision_effect": "allow_p9z_discussion_gate" if approved else "none",
        "p9y_review_approved": approved,
        "p9z_owner_gate_discussion_approved": approved,
        "timer_path_readback_execution_approved": False,
        "timer_hook_implementation_approved": False,
        "hook_deployment_approved": False,
        "live_timer_path_load_approved": False,
        "candidate_execution_approved": False,
        "live_order_submission_approved": False,
        "target_plan_replacement_approved": False,
        "executor_input_mutation_approved": False,
        "live_config_mutation_approved": False,
        "operator_state_mutation_approved": False,
        "timer_or_service_mutation_approved": False,
        "remote_sync_approved": False,
        "supervisor_run_approved": False,
        "repo_stage_change_approved": False,
    }


def p9x_sufficient(
    summary: dict[str, Any],
    *,
    hook_sha256: str,
    supervisor_sha256: str,
    live_config_sha256: str,
) -> bool:
    gates = dict(summary.get("gates") or {})
    owner = dict(summary.get("owner_decision") or {})
    source = dict(summary.get("source_evidence") or {})
    hook = dict(source.get("hook_module") or {})
    supervisor = dict(source.get("live_supervisor") or {})
    live_config = dict(source.get("live_config_dir") or {})
    required_gates = (
        "project_stage_boundary_preserved",
        "p9w_owner_gate_ready",
        "p9w_allows_future_p9x_gate_request",
        "dry_load_outputs_under_proof_artifacts",
        "dry_load_mode_not_live_timer_service",
        "default_off_config_loaded",
        "disabled_hook_readback_ready",
        "disabled_hook_writes_zero_candidate_artifacts",
        "baseline_target_plan_byte_for_byte_unchanged",
        "executor_input_hash_unchanged",
        "executor_input_hash_equals_baseline",
        "executor_consumes_baseline_only",
        "candidate_shadow_hash_differs_from_executor",
        "candidate_plan_not_referenced_by_executor",
        "target_plan_not_replaced",
        "live_supervisor_source_unchanged",
        "live_config_dir_unchanged",
        "live_timer_service_not_enabled_or_invoked",
        "supervisor_not_run_for_execution",
        "no_remote_sync_in_p9x",
        "no_live_timer_path_load_in_p9x",
        "no_executor_input_mutation_in_p9x",
        "no_target_plan_replacement_in_p9x",
        "no_live_mutation_in_p9x",
        "zero_orders_fills_in_p9x",
    )
    return (
        summary.get("contract_version") == P9X_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and owner.get("decision") == "approve_p9x_execute_default_off_timer_path_dry_load_only"
        and owner.get("default_off_timer_path_dry_load_execution_approved") is True
        and owner.get("candidate_execution_approved") is False
        and owner.get("live_order_submission_approved") is False
        and summary.get("default_off_timer_path_dry_load_ready") is True
        and summary.get("default_off_timer_path_dry_load_execution_authorized") is True
        and summary.get("default_off_timer_path_dry_load_executed") is True
        and summary.get("dry_load_mode") == "default_off_timer_path_dry_load_harness_not_live_timer_service"
        and summary.get("entered_timer_path_dry_load_harness") is True
        and summary.get("entered_live_timer_path") is False
        and summary.get("default_off_hook_enabled") is False
        and summary.get("candidate_execution_enabled") is False
        and int(summary.get("disabled_hook_candidate_artifacts_written_count") or 0) == 0
        and summary.get("executor_consumes_baseline_only") is True
        and summary.get("executor_input_hash_equals_baseline") is True
        and summary.get("candidate_plan_referenced_by_executor") is False
        and summary.get("target_plan_replaced") is False
        and summary.get("executor_input_changed") is False
        and summary.get("eligible_for_live_order_submission") is False
        and summary.get("eligible_for_live_timer_path_load") is False
        and summary.get("live_timer_path_loaded") is False
        and summary.get("live_timer_service_enabled_or_invoked") is False
        and summary.get("ran_supervisor") is False
        and summary.get("remote_execution_performed") is False
        and summary.get("live_config_changed") is False
        and summary.get("operator_state_changed") is False
        and summary.get("timer_state_changed") is False
        and zero_orders_fills(summary)
        and hook.get("sha256") == hook_sha256
        and supervisor.get("sha256") == supervisor_sha256
        and live_config.get("sha256") == live_config_sha256
        and all(gates.get(key) is True for key in required_gates)
    )


def build_phase9y(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    generated_at = now_fn()
    run_id = generated_at.strftime("%Y%m%dT%H%M%SZ")
    root = resolve_path(args.output_root) if str(args.output_root).strip() else resolve_path(DEFAULT_OUTPUT_PARENT) / run_id
    proof_root = root / "proof_artifacts" / "p9y" / run_id

    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)
    p9x_path = resolve_path(args.phase9x_summary) if str(args.phase9x_summary).strip() else latest_match(PHASE9X_PARENT, "*/summary.json")
    p9x = load_optional(p9x_path)
    hook_path = resolve_path(args.hook_module)
    supervisor_path = resolve_path(args.supervisor)
    live_config_dir = resolve_path(args.live_config_dir)
    hook_sha = file_sha256(hook_path) if hook_path.exists() and hook_path.is_file() else ""
    supervisor_sha = file_sha256(supervisor_path) if supervisor_path.exists() and supervisor_path.is_file() else ""
    live_config_sha = tree_sha256(live_config_dir)
    supervisor_loads_hook = current_supervisor_loads_hook(supervisor_path)
    decision = owner_decision_record(args, generated_at)

    gates = {
        "owner_decision_p9y_review_only": args.owner_decision == APPROVE_P9Y_DECISION,
        "project_stage_boundary_preserved": project_profile.get("current_stage") == "stage_1_research_readiness_only",
        "p9x_default_off_dry_load_sufficient": p9x_sufficient(
            p9x,
            hook_sha256=hook_sha,
            supervisor_sha256=supervisor_sha,
            live_config_sha256=live_config_sha,
        ),
        "p9x_did_not_authorize_timer_path_load": p9x.get("timer_path_load_authorized") is False,
        "p9x_did_not_authorize_live_orders": p9x.get("live_order_submission_authorized") is False,
        "p9x_did_not_authorize_candidate_execution": p9x.get("candidate_execution_enabled") is False,
        "current_live_supervisor_still_not_loading_hook": supervisor_loads_hook is False,
        "current_live_config_matches_p9x_source": dict(dict(p9x.get("source_evidence") or {}).get("live_config_dir") or {}).get("sha256") == live_config_sha,
        "current_supervisor_matches_p9x_source": dict(dict(p9x.get("source_evidence") or {}).get("live_supervisor") or {}).get("sha256") == supervisor_sha,
        "current_hook_matches_p9x_source": dict(dict(p9x.get("source_evidence") or {}).get("hook_module") or {}).get("sha256") == hook_sha,
        "no_timer_path_load_in_p9y": True,
        "no_supervisor_run_in_p9y": True,
        "no_remote_sync_in_p9y": True,
        "no_executor_input_mutation_in_p9y": True,
        "no_live_mutation_in_p9y": True,
        "zero_orders_fills_in_p9y": True,
    }
    blockers = [key for key, value in gates.items() if not value]
    status = "ready" if not blockers else "blocked"

    review_packet = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9y_review_packet.v1",
        "run_id": run_id,
        "review_scope": "p9x_sufficiency_for_next_owner_gate",
        "p9x_summary": evidence_file(p9x_path),
        "p9x_sufficient_for_next_owner_gate": status == "ready",
        "allowed_next_gate": P9Z_GATE if status == "ready" else "",
        "allowed_next_gate_must_be_separately_requested": True,
        "required_next_gate_boundaries": {
            "default_off_implementation_required": True,
            "observe_only_shadow_readback_only": True,
            "baseline_only_executor_input": True,
            "candidate_execution_forbidden": True,
            "live_order_submission_forbidden": True,
            "target_plan_replacement_forbidden": True,
            "executor_input_mutation_forbidden": True,
            "live_config_mutation_requires_separate_gate": True,
            "operator_state_mutation_forbidden": True,
            "timer_service_enable_or_disable_forbidden_without_separate_gate": True,
            "orders_submitted_must_equal": 0,
            "fill_count_must_equal": 0,
        },
    }
    write_json(proof_root / "p9x_sufficiency_review.json", review_packet)

    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(generated_at),
        "status": status,
        "blockers": blockers,
        "owner_decision": decision,
        "p9y_owner_review_ready": status == "ready",
        "p9x_sufficient_for_next_owner_gate": status == "ready",
        "eligible_for_p9z_owner_gate": status == "ready",
        "allowed_next_gate": P9Z_GATE if status == "ready" else "",
        "allowed_next_gate_must_be_separately_requested": True,
        "timer_path_readback_execution_authorized": False,
        "timer_hook_implementation_authorized": False,
        "hook_deployment_authorized": False,
        "live_timer_path_load_authorized": False,
        "candidate_execution_authorized": False,
        "live_order_submission_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "live_config_mutation_authorized": False,
        "operator_state_mutation_authorized": False,
        "timer_or_service_mutation_authorized": False,
        "remote_sync_authorized": False,
        "supervisor_run_authorized": False,
        "entered_timer_path": False,
        "ran_supervisor": False,
        "remote_execution_performed": False,
        "orders_submitted": 0,
        "fill_count": 0,
        "source_evidence": {
            "project_profile": evidence_file(project_profile_path),
            "phase9x_summary": evidence_file(p9x_path),
            "hook_module": evidence_file(hook_path),
            "live_supervisor": evidence_file(supervisor_path),
            "live_config_dir": {"path": str(live_config_dir), "exists": live_config_dir.exists(), "sha256": live_config_sha},
        },
        "proof_root": str(proof_root),
        "gates": gates,
        "output_files": {
            "summary": str(root / "summary.json"),
            "owner_decision_record": str(root / "owner_decision_record.json"),
            "p9x_sufficiency_review": str(proof_root / "p9x_sufficiency_review.json"),
        },
    }
    write_json(root / "owner_decision_record.json", decision)
    write_json(root / "summary.json", summary)
    return summary, 0 if status == "ready" else 2


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_phase9y(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
