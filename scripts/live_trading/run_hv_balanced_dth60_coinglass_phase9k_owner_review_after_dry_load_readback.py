from __future__ import annotations

import argparse
import hashlib
import json
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


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9k_owner_review_after_dry_load_readback.v1"
APPROVE_P9K_DECISION = "approve_p9k_owner_review_after_dry_load_readback_only"
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9k_owner_review"
PHASE4_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_coinglass_candidate/"
    "phase4_paired_target_plan_shadow"
)
PHASE9E_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_coinglass_candidate/"
    "phase9e_owner_gated_timer_adjacent_fixture"
)
PHASE9J_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9j_dry_load_readback"
PHASE9R_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_coinglass_candidate/"
    "phase9r_research_to_live_parity"
)
PROJECT_PROFILE = "config/project_governance/project_profile.json"
HOOK_MODULE = "src/enhengclaw/live_trading/dth60_observe_only_shadow_hook.py"
SUPERVISOR_PATH = "src/enhengclaw/live_trading/mainnet_live_supervisor.py"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build the owner-gated P9K review packet after P9J dry-load readback. "
            "This is review-only: it reads retained proof artifacts, writes a "
            "P9K review bundle, and does not implement, deploy, load, run, mutate "
            "executor input, or authorize orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase4-summary", default="")
    parser.add_argument("--phase9e-summary", default="")
    parser.add_argument("--phase9j-summary", default="")
    parser.add_argument("--phase9r-summary", default="")
    parser.add_argument("--hook-module", default=HOOK_MODULE)
    parser.add_argument("--supervisor", default=SUPERVISOR_PATH)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9K_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:execute_owner_gated_p9k_review_after_dry_load_readback",
    )
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def resolve_path(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def latest_match(parent: str, pattern: str) -> Path:
    root = resolve_path(parent)
    matches = [path for path in root.glob(pattern) if path.is_file()]
    if not matches:
        return Path("")
    return sorted(matches, key=lambda path: (path.stat().st_mtime, str(path)))[-1]


def load_json(path: Path) -> dict[str, Any]:
    with resolve_path(path).open(encoding="utf-8") as handle:
        return dict(json.load(handle))


def load_optional(path: Path) -> dict[str, Any]:
    resolved = resolve_path(path)
    return load_json(resolved) if resolved.exists() else {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def evidence_file(path: Path) -> dict[str, Any]:
    if not path:
        return {"path": "", "exists": False, "sha256": ""}
    resolved = resolve_path(path)
    if not resolved.exists():
        return {"path": str(path), "exists": False, "sha256": ""}
    return {"path": str(path), "exists": True, "sha256": file_sha256(resolved)}


def output_under_proof_artifacts(path: Path) -> bool:
    return "proof_artifacts" in [part.lower() for part in path.resolve().parts]


def int_zero(payload: dict[str, Any], key: str) -> bool:
    return int(payload.get(key) or 0) == 0


def no_live_mutation(payload: dict[str, Any]) -> bool:
    return (
        payload.get("applied_to_live") is False
        and payload.get("live_config_changed") is False
        and payload.get("operator_state_changed") is False
        and payload.get("timer_state_changed") is False
    )


def zero_orders_fills(payload: dict[str, Any]) -> bool:
    exchange_submission = payload.get("exchange_order_submission")
    return (
        int_zero(payload, "orders_submitted")
        and int_zero(payload, "fill_count")
        and int_zero(payload, "fills_observed")
        and exchange_submission in (None, "disabled")
    )


def row_parity_zero(summary: dict[str, Any]) -> bool:
    row = dict(summary.get("row_parity") or {})
    return all(
        int(row.get(key) or 0) == 0
        for key in (
            "trigger_mismatch_count",
            "multiplier_mismatch_count",
            "target_contribution_mismatch_count",
            "score_mismatch_count",
        )
    )


def p9r_ready(summary: dict[str, Any]) -> bool:
    target = dict(summary.get("target_weight_parity") or {})
    slices = dict(summary.get("slice_metric_parity") or {})
    retained = dict(summary.get("retained_forward_artifact_compare") or {})
    return (
        summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("scope") == "research_to_live_parity_harness_only"
        and summary.get("candidate_scorer_mode") == "research_h10d_contract"
        and summary.get("candidate_scorer_mode_scope") == "proof_harness_only"
        and summary.get("candidate_scorer_loaded_into_live_wrapper") is False
        and summary.get("candidate_scorer_loaded_into_timer") is False
        and summary.get("candidate_scorer_loaded_into_executor") is False
        and summary.get("target_factor") == "distance_to_high_60"
        and summary.get("target_overlay_semantics")
        == "only distance_to_high_60 contribution is multiplied by 0.0 on candidate trigger rows"
        and row_parity_zero(summary)
        and int(target.get("mismatch_count") or 0) == 0
        and int(slices.get("mismatch_count") or 0) == 0
        and retained.get("status") == "ready"
        and zero_orders_fills(summary)
        and summary.get("applied_to_live") is False
        and summary.get("live_config_changed") is False
        and summary.get("operator_state_changed") is False
        and summary.get("live_supervisor_timer_loaded_candidate_overlay") is False
    )


def phase4_ready(summary: dict[str, Any]) -> bool:
    phase3 = dict(summary.get("phase3_parity_proof_checks") or {})
    phase2 = dict(summary.get("phase2_pit_proof_checks") or {})
    phase2b = dict(summary.get("phase2b_pit_proof_checks") or {})
    combined = dict(summary.get("combined_candidate_trigger_proof") or {})
    return (
        summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("contract_version") == "hv_balanced_dth60_coinglass_phase4_paired_target_plan_shadow.v1"
        and summary.get("plan_only") is True
        and summary.get("same_timestamp_context_proven") is True
        and summary.get("same_risk_inputs_proven") is True
        and summary.get("same_portfolio_engine_proven") is True
        and summary.get("same_symbol_set_proven") is True
        and summary.get("deterministic_target_difference_proven") is True
        and summary.get("combined_candidate_trigger_proven") is True
        and summary.get("target_factor") == "distance_to_high_60"
        and phase3.get("disabled_wrapper_score_matches_core") is True
        and phase3.get("overlay_enabled_only_target_contribution_changed") is True
        and phase3.get("combined_candidate_trigger_proven") is True
        and phase2.get("no_future_fill_proven") is True
        and phase2.get("no_stale_fill_proven") is True
        and phase2b.get("no_future_fill_proven") is True
        and phase2b.get("no_stale_fill_proven") is True
        and phase2b.get("train_excludes_decision_row") is True
        and combined.get("proven") is True
        and zero_orders_fills(summary)
        and no_live_mutation(summary)
        and summary.get("mainnet_order_submission_authorized") is False
    )


def p9e_ready(
    summary: dict[str, Any],
    *,
    current_hook_sha256: str,
    current_supervisor_sha256: str,
) -> bool:
    owner = dict(summary.get("owner_decision") or {})
    source = dict(summary.get("source_evidence") or {})
    hook = dict(source.get("hook_module") or {})
    supervisor = dict(source.get("live_supervisor") or {})
    context = dict(summary.get("copied_timer_context_snapshot") or {})
    return (
        summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("fixture_scope") == "owner_gated_timer_adjacent_local_fixture_only"
        and owner.get("decision") == "approve_p9e_timer_adjacent_local_fixture_only"
        and owner.get("hook_deployment_approved") is False
        and owner.get("timer_path_load_approved") is False
        and owner.get("live_order_submission_approved") is False
        and owner.get("target_plan_replacement_approved") is False
        and owner.get("executor_input_mutation_approved") is False
        and summary.get("hook_enabled_inside_fixture") is True
        and summary.get("default_live_hook_enabled") is False
        and summary.get("executor_consumes_baseline_only") is True
        and summary.get("candidate_plan_referenced_by_executor") is False
        and summary.get("candidate_artifacts_under_proof_artifacts_only") is True
        and summary.get("live_supervisor_loads_candidate_hook") is False
        and summary.get("ran_supervisor") is False
        and summary.get("timer_path_invoked") is False
        and summary.get("eligible_for_timer_path_load") is False
        and summary.get("eligible_for_live_order_submission") is False
        and zero_orders_fills(summary)
        and no_live_mutation(summary)
        and summary.get("deployed_hook") is False
        and hook.get("sha256") == current_hook_sha256
        and supervisor.get("sha256") == current_supervisor_sha256
        and dict(context.get("source_shared_input_context") or {}).get("exists") is True
        and dict(context.get("source_target_plan_diff") or {}).get("exists") is True
        and dict(context.get("executor_input_plan_copy") or {}).get("sha256")
        == dict(context.get("baseline_target_plan_copy") or {}).get("sha256")
    )


def p9j_ready(
    summary: dict[str, Any],
    *,
    current_hook_sha256: str,
    current_supervisor_sha256: str,
) -> bool:
    gates = dict(summary.get("gates") or {})
    owner = dict(summary.get("owner_decision") or {})
    source = dict(summary.get("source_evidence") or {})
    hook = dict(source.get("hook_module") or {})
    supervisor = dict(source.get("live_supervisor") or {})
    required_gates = (
        "owner_decision_p9j_dry_load_readback_only",
        "project_stage_boundary_preserved",
        "p9i_diff_fixture_ready",
        "current_live_supervisor_not_loading_hook",
        "current_hook_hash_matches_p9i_source",
        "current_supervisor_hash_matches_p9i_source",
        "dry_load_source_files_exist",
        "dry_load_source_files_under_p9i_proof_artifacts",
        "dry_load_output_under_proof_artifacts",
        "dry_load_mode_not_live_timer_path",
        "dry_load_default_off",
        "dry_load_order_authority_disabled",
        "dry_load_executor_source_baseline_only",
        "live_timer_service_not_enabled_or_invoked",
        "supervisor_not_run_from_timer",
        "executor_input_hash_equals_baseline",
        "executor_consumes_baseline_only",
        "candidate_shadow_hash_differs_from_executor",
        "candidate_plan_not_referenced_by_executor",
        "candidate_artifacts_under_proof_artifacts_only",
        "live_supervisor_source_unchanged",
        "no_timer_path_load_in_p9j",
        "no_supervisor_run_in_p9j",
        "no_remote_execution_in_p9j",
        "no_executor_input_mutation_in_p9j",
        "no_target_plan_replacement_in_p9j",
        "no_live_mutation_in_p9j",
        "zero_orders_fills_in_p9j",
    )
    return (
        summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("dry_load_readback_scope") == "owner_gated_proof_artifacts_dry_load_readback_only"
        and summary.get("proof_artifacts_dry_load_readback_ready") is True
        and summary.get("eligible_for_owner_p9k_review") is True
        and summary.get("eligible_for_timer_hook_implementation") is False
        and summary.get("timer_hook_implementation_authorized") is False
        and summary.get("hook_deployment_authorized") is False
        and summary.get("timer_path_load_authorized") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("target_plan_replacement_authorized") is False
        and summary.get("executor_input_mutation_authorized") is False
        and summary.get("remote_sync_authorized") is False
        and summary.get("supervisor_run_authorized") is False
        and summary.get("dry_load_mode") == "proof_artifacts_readback_only_not_timer_path"
        and summary.get("dry_loaded_from_proof_artifacts_only") is True
        and summary.get("live_timer_path_loaded") is False
        and summary.get("live_timer_service_enabled_or_invoked") is False
        and summary.get("live_supervisor_loads_candidate_hook") is False
        and summary.get("live_supervisor_source_unchanged") is True
        and summary.get("executor_input_hash_equals_baseline") is True
        and summary.get("executor_consumes_baseline_only") is True
        and summary.get("candidate_shadow_hash_differs_from_executor") is True
        and summary.get("candidate_plan_referenced_by_executor") is False
        and summary.get("candidate_artifacts_under_proof_artifacts_only") is True
        and summary.get("candidate_order_authority") == "disabled"
        and summary.get("execution_target_source") == "baseline_only"
        and summary.get("candidate_artifact_sink") == "proof_artifacts_only"
        and summary.get("ran_supervisor") is False
        and summary.get("timer_path_invoked") is False
        and summary.get("remote_execution_performed") is False
        and no_live_mutation(summary)
        and zero_orders_fills(summary)
        and owner.get("decision") == "approve_p9j_proof_artifacts_dry_load_readback_only"
        and owner.get("proof_artifacts_dry_load_readback_approved") is True
        and owner.get("timer_hook_implementation_approved") is False
        and owner.get("hook_deployment_approved") is False
        and owner.get("timer_path_load_approved") is False
        and owner.get("live_order_submission_approved") is False
        and hook.get("sha256") == current_hook_sha256
        and supervisor.get("sha256") == current_supervisor_sha256
        and summary.get("supervisor_sha256_before_readback") == current_supervisor_sha256
        and summary.get("supervisor_sha256_after_readback") == current_supervisor_sha256
        and all(gates.get(key) is True for key in required_gates)
    )


def build_owner_decision_record(args: argparse.Namespace, started_at: datetime) -> dict[str, Any]:
    approved = str(args.owner_decision) == APPROVE_P9K_DECISION
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9k_owner_decision.v1",
        "owner": str(args.owner),
        "decision": str(args.owner_decision),
        "decision_source": str(args.owner_decision_source),
        "recorded_at_utc": iso_z(started_at),
        "decision_effect": (
            "authorize_p9k_owner_review_after_dry_load_readback_only" if approved else "none"
        ),
        "owner_review_after_dry_load_readback_approved": approved,
        "timer_hook_implementation_approved": False,
        "hook_deployment_approved": False,
        "timer_path_load_approved": False,
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


def review_packet(
    *,
    run_id: str,
    owner_decision: dict[str, Any],
    sources: dict[str, dict[str, Any]],
    minimum_proof: dict[str, bool],
) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9k_review_packet.v1",
        "run_id": run_id,
        "review_scope": "owner_gated_review_after_dry_load_readback_only",
        "owner_decision": owner_decision,
        "source_evidence": sources,
        "minimum_proof": minimum_proof,
        "review_conclusion": (
            "ready_for_separate_owner_next_step_discussion_only"
            if all(minimum_proof.values())
            else "blocked"
        ),
        "explicit_non_authorizations": [
            "timer_hook_implementation",
            "hook_deployment",
            "timer_path_load",
            "target_plan_replacement",
            "executor_input_mutation",
            "live_config_mutation",
            "operator_state_mutation",
            "timer_or_service_mutation",
            "remote_sync",
            "supervisor_run",
            "live_order_submission",
            "stage_governance_change",
        ],
    }


def build_phase9k(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] | None = None,
) -> tuple[dict[str, Any], int]:
    now = now_fn or utc_now
    started_at = now()
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=UTC)
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")
    output_root = resolve_path(args.output_root) if args.output_root else resolve_path(DEFAULT_OUTPUT_PARENT) / run_id
    proof_root = output_root / "proof_artifacts" / "p9k" / run_id
    proof_root.mkdir(parents=True, exist_ok=True)

    paths = {
        "project_profile": resolve_path(args.project_profile),
        "phase4": (
            resolve_path(args.phase4_summary)
            if str(getattr(args, "phase4_summary", "") or "").strip()
            else latest_match(PHASE4_PARENT, "*/summary.json")
        ),
        "phase9e": (
            resolve_path(args.phase9e_summary)
            if str(getattr(args, "phase9e_summary", "") or "").strip()
            else latest_match(PHASE9E_PARENT, "*/summary.json")
        ),
        "phase9j": (
            resolve_path(args.phase9j_summary)
            if str(getattr(args, "phase9j_summary", "") or "").strip()
            else latest_match(PHASE9J_PARENT, "*/summary.json")
        ),
        "phase9r": (
            resolve_path(args.phase9r_summary)
            if str(getattr(args, "phase9r_summary", "") or "").strip()
            else latest_match(PHASE9R_PARENT, "*/summary.json")
        ),
        "hook_module": resolve_path(args.hook_module),
        "supervisor": resolve_path(args.supervisor),
    }
    project_profile = load_optional(paths["project_profile"])
    phase4 = load_optional(paths["phase4"])
    p9e = load_optional(paths["phase9e"])
    p9j = load_optional(paths["phase9j"])
    p9r = load_optional(paths["phase9r"])
    current_hook_sha = file_sha256(paths["hook_module"]) if paths["hook_module"].exists() else ""
    supervisor_sha_before = file_sha256(paths["supervisor"]) if paths["supervisor"].exists() else ""
    supervisor_text = paths["supervisor"].read_text(encoding="utf-8") if paths["supervisor"].exists() else ""
    live_supervisor_loads_hook_now = "dth60_observe_only_shadow_hook" in supervisor_text
    owner_decision_record = build_owner_decision_record(args, started_at)

    phase4_ok = phase4_ready(phase4)
    p9e_ok = p9e_ready(
        p9e,
        current_hook_sha256=current_hook_sha,
        current_supervisor_sha256=supervisor_sha_before,
    )
    p9j_ok = p9j_ready(
        p9j,
        current_hook_sha256=current_hook_sha,
        current_supervisor_sha256=supervisor_sha_before,
    )
    p9r_ok = p9r_ready(p9r)

    minimum_proof = {
        "same_timestamp_context": phase4_ok and p9e_ok,
        "same_risk_inputs": phase4_ok and p9e_ok,
        "overlay_only_distance_to_high_60_contribution": phase4_ok and p9r_ok,
        "research_to_live_trigger_multiplier_contribution_target_weight_slice_parity": p9r_ok,
        "dry_load_readback_from_proof_artifacts_only": p9j_ok,
        "executor_input_baseline_only_after_dry_load": p9j_ok,
        "candidate_plan_not_referenced_by_executor": (
            p9j.get("candidate_plan_referenced_by_executor") is False
            and p9e.get("candidate_plan_referenced_by_executor") is False
        ),
        "timer_path_not_loaded_or_invoked": (
            p9j.get("live_timer_path_loaded") is False
            and p9j.get("timer_path_invoked") is False
            and p9e.get("timer_path_invoked") is False
        ),
        "current_live_supervisor_not_loading_hook": not live_supervisor_loads_hook_now,
        "no_live_order_submission": (
            zero_orders_fills(phase4)
            and zero_orders_fills(p9e)
            and zero_orders_fills(p9j)
            and zero_orders_fills(p9r)
        ),
        "stage_boundary_preserved": project_profile.get("current_stage") == "stage_1_research_readiness_only",
    }
    sources = {
        "project_profile": evidence_file(paths["project_profile"]),
        "phase4_summary": evidence_file(paths["phase4"]),
        "phase9e_summary": evidence_file(paths["phase9e"]),
        "phase9j_summary": evidence_file(paths["phase9j"]),
        "phase9r_summary": evidence_file(paths["phase9r"]),
        "hook_module": evidence_file(paths["hook_module"]),
        "live_supervisor": evidence_file(paths["supervisor"]),
    }

    control_boundary_readback = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9k_control_boundary_readback.v1",
        "run_id": run_id,
        "scope": "local_source_and_retained_proof_artifacts_review_only",
        "live_supervisor": sources["live_supervisor"],
        "live_supervisor_sha256_before": supervisor_sha_before,
        "live_supervisor_sha256_after": file_sha256(paths["supervisor"]) if paths["supervisor"].exists() else "",
        "live_supervisor_source_unchanged": True,
        "live_supervisor_loads_candidate_hook": live_supervisor_loads_hook_now,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "timer_service_enabled_or_invoked": False,
        "remote_control_plane_touched": False,
        "executor_input_mutated": False,
        "target_plan_replaced": False,
        "orders_submitted": 0,
        "fill_count": 0,
    }
    control_boundary_readback["live_supervisor_source_unchanged"] = (
        control_boundary_readback["live_supervisor_sha256_before"]
        == control_boundary_readback["live_supervisor_sha256_after"]
    )

    decision_matrix = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9k_review_decision_matrix.v1",
        "run_id": run_id,
        "review_inputs": {
            "phase4_ready": phase4_ok,
            "phase9e_ready": p9e_ok,
            "phase9j_ready": p9j_ok,
            "phase9r_ready": p9r_ok,
        },
        "minimum_proof": minimum_proof,
        "authorizations": {
            "owner_review_after_dry_load_readback": str(args.owner_decision) == APPROVE_P9K_DECISION,
            "timer_hook_implementation": False,
            "hook_deployment": False,
            "timer_path_load": False,
            "live_order_submission": False,
            "target_plan_replacement": False,
            "executor_input_mutation": False,
            "live_config_mutation": False,
            "operator_state_mutation": False,
            "timer_or_service_mutation": False,
            "remote_sync": False,
            "supervisor_run": False,
            "stage_governance_change": False,
        },
    }
    packet = review_packet(
        run_id=run_id,
        owner_decision=owner_decision_record,
        sources=sources,
        minimum_proof=minimum_proof,
    )

    gates = {
        "owner_decision_p9k_review_only": str(args.owner_decision) == APPROVE_P9K_DECISION,
        "project_stage_boundary_preserved": minimum_proof["stage_boundary_preserved"],
        "phase4_same_context_ready": phase4_ok,
        "p9e_timer_adjacent_same_context_ready": p9e_ok,
        "p9j_dry_load_readback_ready": p9j_ok,
        "p9r_research_to_live_parity_ready": p9r_ok,
        "same_timestamp_context_proven": minimum_proof["same_timestamp_context"],
        "same_risk_inputs_proven": minimum_proof["same_risk_inputs"],
        "overlay_only_distance_to_high_60_contribution": minimum_proof[
            "overlay_only_distance_to_high_60_contribution"
        ],
        "research_contract_parity_zero_mismatches": minimum_proof[
            "research_to_live_trigger_multiplier_contribution_target_weight_slice_parity"
        ],
        "dry_load_from_proof_artifacts_only": minimum_proof["dry_load_readback_from_proof_artifacts_only"],
        "executor_input_baseline_only_after_dry_load": minimum_proof[
            "executor_input_baseline_only_after_dry_load"
        ],
        "candidate_plan_not_referenced_by_executor": minimum_proof["candidate_plan_not_referenced_by_executor"],
        "timer_path_not_loaded_or_invoked": minimum_proof["timer_path_not_loaded_or_invoked"],
        "current_live_supervisor_not_loading_hook": minimum_proof["current_live_supervisor_not_loading_hook"],
        "review_output_under_proof_artifacts": output_under_proof_artifacts(proof_root),
        "no_timer_hook_implementation_in_p9k": True,
        "no_hook_deployment_in_p9k": True,
        "no_timer_path_load_in_p9k": True,
        "no_supervisor_run_in_p9k": True,
        "no_remote_execution_in_p9k": True,
        "no_executor_input_mutation_in_p9k": True,
        "no_target_plan_replacement_in_p9k": True,
        "no_live_mutation_in_p9k": True,
        "zero_orders_fills_in_p9k": minimum_proof["no_live_order_submission"],
    }
    blockers = [key for key, value in gates.items() if not value]
    status = "ready" if not blockers else "blocked"

    write_json(output_root / "owner_decision_record.json", owner_decision_record)
    write_json(proof_root / "owner_review_packet.json", packet)
    write_json(proof_root / "review_decision_matrix.json", decision_matrix)
    write_json(proof_root / "control_boundary_readback.json", control_boundary_readback)

    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "review_scope": "owner_gated_review_after_dry_load_readback_only",
        "owner_decision": owner_decision_record,
        "source_evidence": sources,
        "owner_review_after_dry_load_readback_ready": status == "ready",
        "eligible_for_owner_next_step_discussion": status == "ready",
        "eligible_for_timer_hook_implementation": False,
        "eligible_for_timer_path_load": False,
        "eligible_for_live_order_submission": False,
        "eligible_for_stage_governance_change": False,
        "timer_hook_implementation_authorized": False,
        "hook_deployment_authorized": False,
        "timer_path_load_authorized": False,
        "live_order_submission_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "remote_sync_authorized": False,
        "supervisor_run_authorized": False,
        "candidate_order_authority": "disabled",
        "candidate_live_order_submission_authorized": False,
        "execution_target_source": "baseline_only",
        "candidate_overlay_execution_path": "excluded",
        "candidate_artifact_sink": "proof_artifacts_only",
        "same_timestamp_context_proven": minimum_proof["same_timestamp_context"],
        "same_risk_inputs_proven": minimum_proof["same_risk_inputs"],
        "overlay_only_distance_to_high_60_contribution": minimum_proof[
            "overlay_only_distance_to_high_60_contribution"
        ],
        "research_contract_parity_zero_mismatches": minimum_proof[
            "research_to_live_trigger_multiplier_contribution_target_weight_slice_parity"
        ],
        "dry_load_readback_from_proof_artifacts_only": minimum_proof[
            "dry_load_readback_from_proof_artifacts_only"
        ],
        "executor_input_baseline_only_after_dry_load": minimum_proof[
            "executor_input_baseline_only_after_dry_load"
        ],
        "candidate_plan_referenced_by_executor": False,
        "live_supervisor_loads_candidate_hook": live_supervisor_loads_hook_now,
        "live_supervisor_source_unchanged": control_boundary_readback["live_supervisor_source_unchanged"],
        "live_timer_path_loaded": False,
        "live_timer_service_enabled_or_invoked": False,
        "ran_supervisor": False,
        "timer_path_invoked": False,
        "remote_execution_performed": False,
        "remote_control_plane_touched": False,
        "orders_submitted": 0,
        "fill_count": 0,
        "fills_observed": 0,
        "exchange_order_submission": "disabled",
        "applied_to_live": False,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "wrote_live_hook_config": False,
        "implemented_hook": False,
        "deployed_hook": False,
        "loaded_hook": False,
        "target_plan_replaced": False,
        "executor_input_changed": False,
        "recommended_next_gate": "separate_owner_gate_required_before_any_p9l_or_timer_path_load_discussion",
        "proof_root": str(proof_root),
        "gates": gates,
        "blockers": blockers,
        "output_files": {
            "summary": str(output_root / "summary.json"),
            "owner_decision_record": str(output_root / "owner_decision_record.json"),
            "owner_review_packet": str(proof_root / "owner_review_packet.json"),
            "review_decision_matrix": str(proof_root / "review_decision_matrix.json"),
            "control_boundary_readback": str(proof_root / "control_boundary_readback.json"),
            "report": str(output_root / "p9k_owner_review_after_dry_load_readback.md"),
        },
    }
    write_json(output_root / "summary.json", summary)
    (output_root / "p9k_owner_review_after_dry_load_readback.md").write_text(
        render_markdown(summary),
        encoding="utf-8",
    )
    return summary, 0 if status == "ready" else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9K Owner Review After Dry-Load Readback",
        "",
        f"`Status: {summary['status']}`",
        "",
        "## Boundary",
        "",
        "This is an owner-gated review packet after P9J dry-load readback only.",
        "",
        "```text",
        "review_scope = owner_gated_review_after_dry_load_readback_only",
        "owner_review_after_dry_load_readback_ready = "
        f"{str(bool(summary['owner_review_after_dry_load_readback_ready'])).lower()}",
        "eligible_for_owner_next_step_discussion = "
        f"{str(bool(summary['eligible_for_owner_next_step_discussion'])).lower()}",
        "timer_hook_implementation_authorized = false",
        "hook_deployment_authorized = false",
        "timer_path_load_authorized = false",
        "live_order_submission_authorized = false",
        "execution_target_source = baseline_only",
        "candidate_artifact_sink = proof_artifacts_only",
        "orders_submitted = 0",
        "fill_count = 0",
        "```",
        "",
        "## Minimum Proof",
        "",
        "```text",
        f"same_timestamp_context_proven = {str(bool(summary['same_timestamp_context_proven'])).lower()}",
        f"same_risk_inputs_proven = {str(bool(summary['same_risk_inputs_proven'])).lower()}",
        "overlay_only_distance_to_high_60_contribution = "
        f"{str(bool(summary['overlay_only_distance_to_high_60_contribution'])).lower()}",
        "dry_load_readback_from_proof_artifacts_only = "
        f"{str(bool(summary['dry_load_readback_from_proof_artifacts_only'])).lower()}",
        "executor_input_baseline_only_after_dry_load = "
        f"{str(bool(summary['executor_input_baseline_only_after_dry_load'])).lower()}",
        "candidate_plan_referenced_by_executor = false",
        "```",
        "",
        "## Gates",
        "",
        "```text",
    ]
    for key, value in dict(summary.get("gates") or {}).items():
        lines.append(f"{key} = {str(bool(value)).lower()}")
    lines.extend(["```", "", "## Blockers", ""])
    blockers = list(summary.get("blockers") or [])
    if blockers:
        lines.extend(f"- `{item}`" for item in blockers)
    else:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_phase9k(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
