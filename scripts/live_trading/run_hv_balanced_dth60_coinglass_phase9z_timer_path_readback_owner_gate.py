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
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9y_owner_review_after_p9x import (  # noqa: E402
    P9Z_GATE,
)


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9z_timer_path_readback_owner_gate.v1"
APPROVE_P9Z_DECISION = "approve_p9z_observe_only_default_off_timer_path_readback_gate_only"
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9z_timer_path_readback_owner_gate"
PHASE9Y_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9y_owner_review_after_p9x"
P9AA_GATE = "P9AA_consecutive_real_timer_path_observe_only_shadow_cycles_no_order_only_if_separately_requested"
P9Y_CONTRACT = "hv_balanced_dth60_coinglass_phase9y_owner_review_after_p9x.v1"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "P9Z is a separate owner gate for observe-only/default-off timer-path "
            "readback. It may authorize a future no-order wrapper run, but it does "
            "not itself run the supervisor, deploy services, or submit orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9y-summary", default="")
    parser.add_argument("--hook-module", default=HOOK_MODULE)
    parser.add_argument("--supervisor", default=SUPERVISOR_PATH)
    parser.add_argument("--live-config-dir", default=LIVE_CONFIG_DIR)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9Z_DECISION)
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
    approved = args.owner_decision == APPROVE_P9Z_DECISION
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9z_owner_decision.v1",
        "recorded_at_utc": iso_z(generated_at),
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "authorize_future_observe_only_default_off_timer_path_readback_gate_only",
        "decision_effect": "allow_p9aa_no_order_timer_path_shadow_cycles" if approved else "none",
        "p9z_owner_gate_approved": approved,
        "future_p9aa_timer_path_shadow_cycles_approved": approved,
        "default_off_implementation_required": True,
        "observe_only_shadow_readback_approved": approved,
        "candidate_execution_approved": False,
        "live_order_submission_approved": False,
        "target_plan_replacement_approved": False,
        "executor_input_mutation_approved": False,
        "candidate_live_order_submission_approved": False,
        "live_config_mutation_approved": False,
        "operator_state_mutation_approved": False,
        "timer_or_service_mutation_approved": False,
        "remote_sync_approved": False,
        "production_timer_service_load_approved": False,
        "repo_stage_change_approved": False,
    }


def p9y_ready(summary: dict[str, Any]) -> bool:
    gates = dict(summary.get("gates") or {})
    owner = dict(summary.get("owner_decision") or {})
    required = (
        "owner_decision_p9y_review_only",
        "project_stage_boundary_preserved",
        "p9x_default_off_dry_load_sufficient",
        "current_live_supervisor_still_not_loading_hook",
        "no_timer_path_load_in_p9y",
        "no_supervisor_run_in_p9y",
        "no_remote_sync_in_p9y",
        "no_executor_input_mutation_in_p9y",
        "no_live_mutation_in_p9y",
        "zero_orders_fills_in_p9y",
    )
    return (
        summary.get("contract_version") == P9Y_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9y_owner_review_ready") is True
        and summary.get("p9x_sufficient_for_next_owner_gate") is True
        and summary.get("eligible_for_p9z_owner_gate") is True
        and summary.get("allowed_next_gate") == P9Z_GATE
        and summary.get("timer_path_readback_execution_authorized") is False
        and summary.get("candidate_execution_authorized") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("target_plan_replacement_authorized") is False
        and summary.get("executor_input_mutation_authorized") is False
        and summary.get("live_config_mutation_authorized") is False
        and summary.get("operator_state_mutation_authorized") is False
        and summary.get("timer_or_service_mutation_authorized") is False
        and summary.get("remote_sync_authorized") is False
        and owner.get("decision") == "approve_p9y_review_p9x_default_off_dry_load_only"
        and owner.get("p9z_owner_gate_discussion_approved") is True
        and zero_orders_fills(summary)
        and all(gates.get(key) is True for key in required)
    )


def build_phase9z(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    generated_at = now_fn()
    run_id = generated_at.strftime("%Y%m%dT%H%M%SZ")
    root = resolve_path(args.output_root) if str(args.output_root).strip() else resolve_path(DEFAULT_OUTPUT_PARENT) / run_id
    proof_root = root / "proof_artifacts" / "p9z" / run_id

    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)
    p9y_path = resolve_path(args.phase9y_summary) if str(args.phase9y_summary).strip() else latest_match(PHASE9Y_PARENT, "*/summary.json")
    p9y = load_optional(p9y_path)
    hook_path = resolve_path(args.hook_module)
    supervisor_path = resolve_path(args.supervisor)
    live_config_dir = resolve_path(args.live_config_dir)
    hook_sha = file_sha256(hook_path) if hook_path.exists() and hook_path.is_file() else ""
    supervisor_sha = file_sha256(supervisor_path) if supervisor_path.exists() and supervisor_path.is_file() else ""
    live_config_sha = tree_sha256(live_config_dir)
    supervisor_loads_hook = current_supervisor_loads_hook(supervisor_path)
    decision = owner_decision_record(args, generated_at)

    gates = {
        "owner_decision_p9z_gate_only": args.owner_decision == APPROVE_P9Z_DECISION,
        "project_stage_boundary_preserved": project_profile.get("current_stage") == "stage_1_research_readiness_only",
        "p9y_owner_review_ready": p9y_ready(p9y),
        "current_live_supervisor_still_not_loading_hook_before_p9aa": supervisor_loads_hook is False,
        "current_hook_matches_p9y_source": dict(dict(p9y.get("source_evidence") or {}).get("hook_module") or {}).get("sha256") == hook_sha,
        "current_supervisor_matches_p9y_source": dict(dict(p9y.get("source_evidence") or {}).get("live_supervisor") or {}).get("sha256") == supervisor_sha,
        "current_live_config_matches_p9y_source": dict(dict(p9y.get("source_evidence") or {}).get("live_config_dir") or {}).get("sha256") == live_config_sha,
        "observe_only_shadow_readback_authorized": decision["observe_only_shadow_readback_approved"] is True,
        "default_off_implementation_required": True,
        "baseline_only_executor_input_required": True,
        "candidate_execution_forbidden": True,
        "live_order_submission_forbidden": True,
        "target_plan_replacement_forbidden": True,
        "executor_input_mutation_forbidden": True,
        "operator_state_mutation_forbidden": True,
        "production_timer_service_load_forbidden": True,
        "no_timer_path_execution_in_p9z": True,
        "no_supervisor_run_in_p9z": True,
        "no_remote_sync_in_p9z": True,
        "zero_orders_fills_in_p9z": True,
    }
    blockers = [key for key, value in gates.items() if not value]
    status = "ready" if not blockers else "blocked"

    gate = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9z_timer_path_readback_gate.v1",
        "run_id": run_id,
        "gate_status": status,
        "authorized_next_gate": P9AA_GATE if status == "ready" else "",
        "authorized_next_gate_must_be_no_order": True,
        "authorized_next_gate_must_run_consecutive_cycles": 3,
        "authorized_next_gate_may_invoke_supervisor_entrypoint": status == "ready",
        "authorized_next_gate_may_enable_observe_only_hook": status == "ready",
        "authorized_next_gate_must_keep_candidate_out_of_executor": True,
        "authorized_next_gate_must_write_candidate_artifacts_only_under_proof_artifacts": True,
        "non_authorizations": {
            "candidate_execution": False,
            "live_order_submission": False,
            "target_plan_replacement": False,
            "executor_input_mutation": False,
            "operator_state_mutation": False,
            "production_timer_service_load": False,
            "remote_sync": False,
            "repo_stage_change": False,
        },
    }
    write_json(proof_root / "timer_path_readback_owner_gate.json", gate)

    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(generated_at),
        "status": status,
        "blockers": blockers,
        "owner_decision": decision,
        "p9z_timer_path_readback_owner_gate_ready": status == "ready",
        "eligible_for_p9aa_timer_path_shadow_cycles": status == "ready",
        "allowed_next_gate": P9AA_GATE if status == "ready" else "",
        "allowed_next_gate_must_be_separately_requested": True,
        "observe_only_shadow_readback_authorized": status == "ready",
        "future_p9aa_consecutive_cycles_required": 3,
        "future_p9aa_supervisor_entrypoint_authorized": status == "ready",
        "future_p9aa_observe_only_hook_enabled_authorized": status == "ready",
        "candidate_execution_authorized": False,
        "live_order_submission_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "live_config_mutation_authorized": False,
        "operator_state_mutation_authorized": False,
        "timer_or_service_mutation_authorized": False,
        "production_timer_service_load_authorized": False,
        "remote_sync_authorized": False,
        "ran_supervisor": False,
        "entered_timer_path": False,
        "remote_execution_performed": False,
        "orders_submitted": 0,
        "fill_count": 0,
        "source_evidence": {
            "project_profile": evidence_file(project_profile_path),
            "phase9y_summary": evidence_file(p9y_path),
            "hook_module": evidence_file(hook_path),
            "live_supervisor": evidence_file(supervisor_path),
            "live_config_dir": {"path": str(live_config_dir), "exists": live_config_dir.exists(), "sha256": live_config_sha},
        },
        "proof_root": str(proof_root),
        "gates": gates,
        "output_files": {
            "summary": str(root / "summary.json"),
            "owner_decision_record": str(root / "owner_decision_record.json"),
            "timer_path_readback_owner_gate": str(proof_root / "timer_path_readback_owner_gate.json"),
        },
    }
    write_json(root / "owner_decision_record.json", decision)
    write_json(root / "summary.json", summary)
    return summary, 0 if status == "ready" else 2


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_phase9z(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
