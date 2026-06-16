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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ag_nonflat_remote_readback import (  # noqa: E402
    CONTRACT_VERSION as P9AG_CONTRACT,
)
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


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9ah_default_off_shadow_review_owner_gate.v1"
APPROVE_P9AH_DECISION = "approve_p9ah_review_p9ag_for_default_off_observe_only_shadow_review_only"
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9ah_default_off_shadow_review_owner_gate"
PHASE9AG_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9ag_nonflat_remote_readback"
P9AI_GATE = "P9AI_default_off_observe_only_live_supervisor_shadow_review_only_if_separately_requested"

PROOF_HARNESS_SYNC_ALLOWLIST = {
    "scripts/live_trading/run_hv_balanced_dth60_coinglass_phase9aa_timer_path_shadow_cycles.py",
}
DISALLOWED_REMOTE_SYNC_PATH_PARTS = (
    "config/live_trading/",
    "config\\live_trading\\",
    "operator_state",
    "systemd",
    ".timer",
    ".service",
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "P9AH is an owner gate that reviews whether the ready P9AG "
            "non-flat no-order readback is sufficient to enter a future "
            "default-off observe-only live-supervisor shadow review. P9AH "
            "does not execute that review, sync remote files, load a timer "
            "path, mutate executor input, or authorize orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9ag-summary", default="")
    parser.add_argument("--hook-module", default=HOOK_MODULE)
    parser.add_argument("--supervisor", default=SUPERVISOR_PATH)
    parser.add_argument("--live-config-dir", default=LIVE_CONFIG_DIR)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9AH_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:review_p9ag_for_default_off_shadow_review",
    )
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def owner_decision_record(args: argparse.Namespace, generated_at: datetime) -> dict[str, Any]:
    approved = args.owner_decision == APPROVE_P9AH_DECISION
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ah_owner_decision.v1",
        "recorded_at_utc": iso_z(generated_at),
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "review_ready_p9ag_for_default_off_observe_only_shadow_review_only",
        "decision_effect": "open_p9ah_sufficiency_review_gate" if approved else "none",
        "p9ah_owner_gate_approved": approved,
        "review_scope": "p9ag_sufficiency_for_future_default_off_observe_only_shadow_review",
        "future_p9ai_shadow_review_may_be_separately_requested": approved,
        "p9ai_shadow_review_execution_approved": False,
        "remote_sync_approved": False,
        "remote_execution_approved": False,
        "timer_path_load_approved": False,
        "candidate_execution_approved": False,
        "candidate_live_order_submission_approved": False,
        "live_order_submission_approved": False,
        "target_plan_replacement_approved": False,
        "executor_input_mutation_approved": False,
        "live_config_mutation_approved": False,
        "operator_state_mutation_approved": False,
        "timer_or_service_mutation_approved": False,
        "production_timer_service_load_approved": False,
        "repo_stage_change_approved": False,
    }


def bool_false(payload: dict[str, Any], key: str) -> bool:
    return payload.get(key) is False


def int_equals(payload: dict[str, Any], key: str, expected: int) -> bool:
    try:
        return int(payload.get(key)) == expected
    except (TypeError, ValueError):
        return False


def evidence_ready(payload: dict[str, Any], key: str) -> bool:
    item = dict(payload.get(key) or {})
    return item.get("exists") is True and bool(item.get("sha256"))


def proof_artifacts_path(path_text: str) -> bool:
    return "proof_artifacts" in str(path_text).replace("\\", "/").lower().split("/")


def position_reference_fixture_ready(summary: dict[str, Any], p9aa_summary: dict[str, Any]) -> bool:
    fixture = dict(summary.get("position_reference_fixture") or {})
    p9aa_fixture = dict(p9aa_summary.get("position_reference_fixture") or {})
    fixture_summary = dict(p9aa_summary.get("position_reference_fixture_summary") or {})
    return (
        summary.get("pit_safe_position_reference_fixture_ready") is True
        and fixture.get("exists") is True
        and bool(fixture.get("sha256"))
        and proof_artifacts_path(str(fixture.get("path") or ""))
        and p9aa_summary.get("position_reference_fixture_requested") is True
        and p9aa_summary.get("position_reference_fixture_ready") is True
        and p9aa_fixture.get("exists") is True
        and bool(p9aa_fixture.get("sha256"))
        and fixture_summary.get("source_created_before_p9aa") is True
        and fixture_summary.get("read_only") is True
        and fixture_summary.get("proof_artifacts_only") is True
        and int(fixture_summary.get("orders_submitted") or 0) == 0
        and int(fixture_summary.get("fill_count") or 0) == 0
        and int(fixture_summary.get("source_open_order_count") or 0) == 0
        and int(fixture_summary.get("source_open_position_count") or 0) > 0
    )


def p9aa_shadow_cycle_ready(summary: dict[str, Any], p9aa_summary: dict[str, Any]) -> bool:
    p9aa_gates = dict(p9aa_summary.get("gates") or {})
    return (
        evidence_ready(summary, "remote_p9aa_summary")
        and p9aa_summary.get("contract_version") == "hv_balanced_dth60_coinglass_phase9aa_timer_path_shadow_cycles.v1"
        and p9aa_summary.get("status") == "ready"
        and not p9aa_summary.get("blockers")
        and p9aa_summary.get("timer_path_shadow_cycles_ready") is True
        and int(p9aa_summary.get("completed_shadow_cycles") or 0) >= 3
        and p9aa_summary.get("fresh_proof_each_cycle") is True
        and p9aa_summary.get("same_risk_no_order_config_each_cycle") is True
        and p9aa_summary.get("execution_target_source") == "baseline_only"
        and p9aa_summary.get("candidate_order_authority") == "disabled"
        and p9aa_summary.get("candidate_overlay_execution_path") == "excluded"
        and p9aa_summary.get("timer_path_supervisor_entrypoint_invoked") is True
        and p9aa_summary.get("systemd_timer_service_invoked") is False
        and p9aa_summary.get("production_timer_service_loaded_or_modified") is False
        and p9aa_summary.get("candidate_execution_enabled") is False
        and p9aa_summary.get("candidate_live_order_submission_authorized") is False
        and p9aa_summary.get("live_order_submission_authorized") is False
        and p9aa_summary.get("target_plan_replaced") is False
        and p9aa_summary.get("executor_input_mutated") is False
        and p9aa_summary.get("live_config_changed") is False
        and p9aa_summary.get("operator_state_changed_outside_generated_p9aa_state") is False
        and p9aa_summary.get("timer_state_changed") is False
        and int(p9aa_summary.get("orders_submitted") or 0) == 0
        and int(p9aa_summary.get("fill_count") or 0) == 0
        and p9aa_summary.get("plan_artifact_missing_cycles") == []
        and p9aa_summary.get("supervisor_cycle_blockers") == []
        and all(
            p9aa_gates.get(key) is True
            for key in (
                "all_cycles_ready",
                "fresh_supervisor_run_each_cycle",
                "fresh_hook_proof_root_each_cycle",
                "all_executor_baseline_only",
                "all_candidate_artifacts_shadow_only",
                "all_candidate_plan_not_referenced_by_executor",
                "no_candidate_execution",
                "no_live_order_submission",
                "no_target_plan_replacement",
                "no_executor_input_mutation",
                "no_production_timer_service_mutation",
                "position_reference_fixture_ready",
            )
        )
    )


def remote_sync_manifest_proof_harness_only(manifest: dict[str, Any]) -> bool:
    files = list(manifest.get("files") or [])
    if not files:
        return False
    synced_paths: set[str] = set()
    for row in files:
        item = dict(row or {})
        path = str(item.get("path") or "")
        normalized = path.replace("\\", "/")
        status = str(item.get("status") or "")
        if status not in {"already_matching", "synced"}:
            return False
        if any(part in normalized for part in DISALLOWED_REMOTE_SYNC_PATH_PARTS):
            return False
        if status == "synced":
            synced_paths.add(normalized)
            if int(item.get("copy_returncode") or 0) != 0:
                return False
        if item.get("local_sha256") != item.get("remote_sha256"):
            return False
        if not item.get("local_sha256"):
            return False
    return synced_paths.issubset(PROOF_HARNESS_SYNC_ALLOWLIST)


def p9ag_ready_for_p9ah(
    summary: dict[str, Any],
    *,
    p9aa_summary: dict[str, Any],
    sync_manifest: dict[str, Any],
) -> bool:
    gates = dict(summary.get("gates") or {})
    source = dict(summary.get("source_evidence") or {})
    required_gates = (
        "owner_decision_p9ag_execute_only",
        "p9af_owner_gate_ready",
        "phase9z_summary_exists",
        "fresh_remote_account_read_pre_nonflat_ready",
        "position_fingerprint_pre_ready",
        "remote_sync_all_files_ready",
        "remote_py_compile_passed",
        "remote_p9aa_no_order_readback_ready",
        "pit_safe_position_reference_fixture_ready",
        "position_fingerprint_post_ready",
        "position_fingerprint_stable",
        "fresh_remote_account_read_post_nonflat_ready",
        "zero_order_cancel_fill_trade_delta",
        "remote_control_boundary_unchanged",
        "shadow_cycles_at_least_three",
        "fresh_proof_each_cycle",
        "same_risk_no_order_config_each_cycle",
        "baseline_only_executor_input",
        "candidate_shadow_only",
        "candidate_execution_forbidden",
        "live_order_submission_forbidden",
        "target_plan_replacement_forbidden",
        "executor_input_mutation_forbidden",
        "production_timer_service_not_loaded_or_modified",
    )
    return (
        summary.get("contract_version") == P9AG_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9ag_nonflat_remote_no_order_readback_ready") is True
        and all(gates.get(key) is True for key in required_gates)
        and evidence_ready(summary, "fresh_remote_account_read_pre")
        and evidence_ready(summary, "fresh_remote_account_read_post")
        and evidence_ready(summary, "position_fingerprint_pre")
        and evidence_ready(summary, "position_fingerprint_post")
        and evidence_ready(summary, "pre_control_snapshot")
        and evidence_ready(summary, "post_control_snapshot")
        and evidence_ready(summary, "remote_sync_manifest")
        and dict(source.get("phase9af_summary") or {}).get("exists") is True
        and dict(source.get("phase9z_summary") or {}).get("exists") is True
        and summary.get("position_fingerprint_stable") is True
        and summary.get("order_cancel_fill_trade_delta_zero") is True
        and int(summary.get("completed_shadow_cycles") or 0) >= 3
        and summary.get("fresh_proof_each_cycle") is True
        and summary.get("same_risk_no_order_config_each_cycle") is True
        and summary.get("baseline_only_executor_input") is True
        and summary.get("candidate_shadow_only") is True
        and summary.get("candidate_execution_authorized") is False
        and summary.get("candidate_live_order_submission_authorized") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("target_plan_replaced") is False
        and summary.get("executor_input_mutated") is False
        and int(summary.get("orders_submitted") or 0) == 0
        and int(summary.get("fill_count") or 0) == 0
        and summary.get("production_timer_service_loaded_or_modified") is False
        and summary.get("live_config_changed") is False
        and summary.get("operator_state_changed") is False
        and summary.get("timer_state_changed") is False
        and int(summary.get("open_order_count_pre") or 0) == 0
        and int(summary.get("open_order_count_post") or 0) == 0
        and int(summary.get("open_position_count_pre") or 0) > 0
        and int(summary.get("open_position_count_pre") or 0) == int(summary.get("open_position_count_post") or -1)
        and position_reference_fixture_ready(summary, p9aa_summary)
        and p9aa_shadow_cycle_ready(summary, p9aa_summary)
        and remote_sync_manifest_proof_harness_only(sync_manifest)
        and int(summary.get("remote_sync_files_copied") or 0)
        == sum(1 for row in list(sync_manifest.get("files") or []) if dict(row or {}).get("status") == "synced")
    )


def shadow_review_matrix(run_id: str, p9ag_summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ah_shadow_review_matrix.v1",
        "run_id": run_id,
        "review_question": "whether ready P9AG is sufficient to enter a future default-off observe-only live-supervisor shadow review",
        "decision": "eligible_for_future_p9ai_shadow_review_only",
        "source_p9ag_run_id": p9ag_summary.get("run_id"),
        "allowed_next_gate": P9AI_GATE,
        "allowed_next_gate_must_be_separately_requested": True,
        "p9ai_required_boundaries": {
            "default_off": True,
            "observe_only": True,
            "order_submission_disabled": True,
            "candidate_execution_disabled": True,
            "executor_consumes_baseline_only": True,
            "candidate_shadow_artifact_only": True,
            "target_plan_replacement": False,
            "executor_input_mutation": False,
            "live_config_mutation": False,
            "operator_state_mutation": False,
            "timer_or_service_mutation": False,
            "production_timer_service_load": False,
        },
        "p9ai_must_reprove": {
            "fresh_remote_account_read_if_remote_context_is_reused": True,
            "baseline_only_executor_input": True,
            "candidate_shadow_only": True,
            "zero_order_cancel_fill_trade_delta": True,
            "live_supervisor_hook_default_off": True,
            "no_timer_path_load_without_separate_owner_gate": True,
            "stage_1_boundary_preserved": True,
        },
        "current_gate_authorizations": {
            "p9ai_shadow_review_execution": False,
            "remote_sync": False,
            "remote_execution": False,
            "timer_path_load": False,
            "candidate_execution": False,
            "live_order_submission": False,
            "target_plan_replacement": False,
            "executor_input_mutation": False,
            "live_config_mutation": False,
            "operator_state_mutation": False,
            "timer_or_service_mutation": False,
            "production_timer_service_load": False,
            "stage_governance_change": False,
        },
    }


def build_phase9ah(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    generated_at = now_fn()
    run_id = generated_at.strftime("%Y%m%dT%H%M%SZ")
    root = resolve_path(args.output_root) if str(args.output_root).strip() else resolve_path(DEFAULT_OUTPUT_PARENT) / run_id
    proof_root = root / "proof_artifacts" / "p9ah" / run_id

    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)
    p9ag_path = (
        resolve_path(args.phase9ag_summary)
        if str(args.phase9ag_summary).strip()
        else latest_match(PHASE9AG_PARENT, "*/summary.json")
    )
    p9ag_summary = load_optional(p9ag_path)
    p9aa_path = resolve_path(dict(p9ag_summary.get("remote_p9aa_summary") or {}).get("path", ""))
    sync_manifest_path = resolve_path(dict(p9ag_summary.get("remote_sync_manifest") or {}).get("path", ""))
    p9aa_summary = load_optional(p9aa_path)
    sync_manifest = load_optional(sync_manifest_path)
    hook_path = resolve_path(args.hook_module)
    supervisor_path = resolve_path(args.supervisor)
    live_config_dir = resolve_path(args.live_config_dir)

    decision = owner_decision_record(args, generated_at)
    matrix = shadow_review_matrix(run_id, p9ag_summary)
    write_json(root / "owner_decision_record.json", decision)
    write_json(proof_root / "shadow_review_matrix.json", matrix)

    supervisor_loads_hook = current_supervisor_loads_hook(supervisor_path)
    gates = {
        "owner_decision_p9ah_review_only": args.owner_decision == APPROVE_P9AH_DECISION,
        "project_stage_boundary_preserved": project_profile.get("current_stage") == "stage_1_research_readiness_only",
        "p9ag_summary_ready": p9ag_ready_for_p9ah(
            p9ag_summary,
            p9aa_summary=p9aa_summary,
            sync_manifest=sync_manifest,
        ),
        "p9ag_remote_p9aa_summary_exists": bool(p9aa_summary),
        "p9ag_remote_sync_manifest_exists": bool(sync_manifest),
        "p9ag_position_reference_fixture_pit_safe": position_reference_fixture_ready(p9ag_summary, p9aa_summary),
        "p9ag_three_fresh_shadow_cycles": p9aa_shadow_cycle_ready(p9ag_summary, p9aa_summary),
        "p9ag_remote_sync_proof_harness_only": remote_sync_manifest_proof_harness_only(sync_manifest),
        "current_live_supervisor_still_not_loading_hook": supervisor_loads_hook is False,
        "current_hook_module_exists": hook_path.exists() and hook_path.is_file(),
        "shadow_review_matrix_under_proof_artifacts": proof_artifacts_path(str(proof_root / "shadow_review_matrix.json")),
        "p9ai_must_be_separately_requested": True,
        "p9ai_not_executed_in_p9ah": True,
        "remote_sync_not_authorized_in_p9ah": True,
        "remote_execution_not_authorized_in_p9ah": True,
        "timer_path_load_not_authorized_in_p9ah": True,
        "candidate_execution_forbidden": True,
        "live_order_submission_forbidden": True,
        "target_plan_replacement_forbidden": True,
        "executor_input_mutation_forbidden": True,
        "live_config_operator_timer_mutation_forbidden": True,
        "production_timer_service_load_forbidden": True,
        "no_remote_sync_in_p9ah": True,
        "no_remote_execution_in_p9ah": True,
        "zero_orders_fills_in_p9ah": True,
    }
    blockers = [key for key, value in gates.items() if not value]
    status = "ready" if not blockers else "blocked"

    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(generated_at),
        "status": status,
        "blockers": blockers,
        "owner_decision": decision,
        "p9ah_default_off_shadow_review_owner_gate_ready": status == "ready",
        "review_scope": "p9ag_sufficiency_for_default_off_observe_only_live_supervisor_shadow_review",
        "eligible_for_future_default_off_observe_only_live_supervisor_shadow_review": status == "ready",
        "allowed_next_gate": P9AI_GATE if status == "ready" else "",
        "allowed_next_gate_must_be_separately_requested": True,
        "default_off_live_supervisor_shadow_review_authorized": False,
        "p9ai_shadow_review_execution_authorized": False,
        "remote_sync_authorized": False,
        "remote_execution_authorized": False,
        "timer_path_load_authorized": False,
        "candidate_execution_authorized": False,
        "candidate_live_order_submission_authorized": False,
        "live_order_submission_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "live_config_mutation_authorized": False,
        "operator_state_mutation_authorized": False,
        "timer_or_service_mutation_authorized": False,
        "production_timer_service_load_authorized": False,
        "repo_stage_change_authorized": False,
        "remote_sync_performed": False,
        "remote_execution_performed": False,
        "entered_timer_path": False,
        "ran_supervisor": False,
        "orders_submitted": 0,
        "fill_count": 0,
        "source_evidence": {
            "project_profile": evidence_file(project_profile_path),
            "phase9ag_summary": evidence_file(p9ag_path),
            "phase9ag_remote_p9aa_summary": evidence_file(p9aa_path),
            "phase9ag_remote_sync_manifest": evidence_file(sync_manifest_path),
            "hook_module": evidence_file(hook_path),
            "live_supervisor": evidence_file(supervisor_path),
            "live_config_dir": {
                "path": str(live_config_dir),
                "exists": live_config_dir.exists(),
                "sha256": tree_sha256(live_config_dir),
            },
            "hook_module_sha256": file_sha256(hook_path) if hook_path.exists() and hook_path.is_file() else "",
            "live_supervisor_sha256": file_sha256(supervisor_path)
            if supervisor_path.exists() and supervisor_path.is_file()
            else "",
        },
        "reviewed_p9ag_facts": {
            "source_p9ag_run_id": p9ag_summary.get("run_id"),
            "p9ag_status": p9ag_summary.get("status"),
            "open_order_count_pre": p9ag_summary.get("open_order_count_pre"),
            "open_order_count_post": p9ag_summary.get("open_order_count_post"),
            "open_position_count_pre": p9ag_summary.get("open_position_count_pre"),
            "open_position_count_post": p9ag_summary.get("open_position_count_post"),
            "completed_shadow_cycles": p9ag_summary.get("completed_shadow_cycles"),
            "fresh_proof_each_cycle": p9ag_summary.get("fresh_proof_each_cycle"),
            "same_risk_no_order_config_each_cycle": p9ag_summary.get("same_risk_no_order_config_each_cycle"),
            "baseline_only_executor_input": p9ag_summary.get("baseline_only_executor_input"),
            "candidate_shadow_only": p9ag_summary.get("candidate_shadow_only"),
            "pit_safe_position_reference_fixture_ready": p9ag_summary.get("pit_safe_position_reference_fixture_ready"),
            "position_reference_fixture": p9ag_summary.get("position_reference_fixture"),
            "remote_sync_files_copied": p9ag_summary.get("remote_sync_files_copied"),
            "orders_submitted": p9ag_summary.get("orders_submitted"),
            "fill_count": p9ag_summary.get("fill_count"),
            "live_config_changed": p9ag_summary.get("live_config_changed"),
            "operator_state_changed": p9ag_summary.get("operator_state_changed"),
            "timer_state_changed": p9ag_summary.get("timer_state_changed"),
            "production_timer_service_loaded_or_modified": p9ag_summary.get("production_timer_service_loaded_or_modified"),
        },
        "future_p9ai_requirements": matrix["p9ai_required_boundaries"],
        "future_p9ai_must_reprove": matrix["p9ai_must_reprove"],
        "proof_root": str(proof_root),
        "gates": gates,
        "output_files": {
            "summary": str(root / "summary.json"),
            "owner_decision_record": str(root / "owner_decision_record.json"),
            "shadow_review_matrix": str(proof_root / "shadow_review_matrix.json"),
        },
    }
    write_json(root / "summary.json", summary)
    return summary, 0 if status == "ready" else 2


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_phase9ah(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
