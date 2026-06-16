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


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9p_owner_review_after_default_off_readback.v1"
APPROVE_P9P_DECISION = "approve_p9p_review_default_off_readback_sufficiency_only"
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9p_owner_review_after_default_off_readback"
PHASE9O_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9o_default_off_dry_load_readback"
PROJECT_PROFILE = "config/project_governance/project_profile.json"
HOOK_MODULE = "src/enhengclaw/live_trading/dth60_observe_only_shadow_hook.py"
SUPERVISOR_PATH = "src/enhengclaw/live_trading/mainnet_live_supervisor.py"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build the P9P owner review after P9O default-off dry-load readback. "
            "This is review-only: it decides whether P9O is sufficient to enter "
            "a separate next owner gate, without authorizing hook deployment, "
            "timer-path load, executor mutation, remote sync, or orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9o-summary", default="")
    parser.add_argument("--hook-module", default=HOOK_MODULE)
    parser.add_argument("--supervisor", default=SUPERVISOR_PATH)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9P_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:review_default_off_readback_sufficiency_for_next_owner_gate_only",
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
    return load_json(resolved) if resolved.exists() and resolved.is_file() else {}


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
    if not path or str(path) in {"", "."}:
        return {"path": "", "exists": False, "sha256": ""}
    resolved = resolve_path(path)
    if not resolved.exists() or not resolved.is_file():
        return {"path": str(path), "exists": False, "sha256": ""}
    return {"path": str(path), "exists": True, "sha256": file_sha256(resolved)}


def output_under_proof_artifacts(path: Path) -> bool:
    return "proof_artifacts" in [part.lower() for part in path.resolve().parts]


def source_output_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("output_files") or {}).get(key) or "")
    return resolve_path(text) if text.strip() else Path("")


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


def current_supervisor_loads_hook(path: Path) -> bool:
    if not path.exists():
        return True
    text = path.read_text(encoding="utf-8", errors="ignore")
    needles = (
        "dth60_observe_only_shadow_hook",
        "candidate_shadow_hook",
        "run_observe_only_shadow_hook",
        "ObserveOnlyShadowHookConfig",
    )
    return any(needle in text for needle in needles)


def build_owner_decision_record(args: argparse.Namespace, started_at: datetime) -> dict[str, Any]:
    approved = str(args.owner_decision) == APPROVE_P9P_DECISION
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9p_owner_decision.v1",
        "owner": str(args.owner),
        "decision": str(args.owner_decision),
        "decision_source": str(args.owner_decision_source),
        "recorded_at_utc": iso_z(started_at),
        "decision_question": "review_default_off_readback_sufficiency_for_next_owner_gate_only",
        "decision_effect": (
            "p9o_sufficient_for_separate_next_owner_gate_discussion"
            if approved
            else "none"
        ),
        "review_default_off_readback_sufficiency_approved": approved,
        "next_owner_gate_execution_approved": False,
        "timer_hook_implementation_approved": False,
        "hook_deployment_approved": False,
        "live_timer_path_load_approved": False,
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


def proof_file_paths(p9o: dict[str, Any]) -> dict[str, Path]:
    return {
        "dry_load_execution_manifest": source_output_path(p9o, "dry_load_execution_manifest"),
        "default_off_config_readback": source_output_path(p9o, "default_off_config_readback"),
        "disabled_hook_readback_summary": source_output_path(p9o, "disabled_hook_readback_summary"),
        "executor_input_readback": source_output_path(p9o, "executor_input_readback"),
        "control_boundary_readback": source_output_path(p9o, "control_boundary_readback"),
        "baseline_target_plan": source_output_path(p9o, "baseline_target_plan"),
        "executor_input_plan": source_output_path(p9o, "executor_input_plan"),
        "candidate_shadow_plan": source_output_path(p9o, "candidate_shadow_plan"),
    }


def p9o_summary_ready(
    p9o: dict[str, Any],
    *,
    current_hook_sha256: str,
    current_supervisor_sha256: str,
    current_supervisor_loads_candidate_hook: bool,
) -> bool:
    source = dict(p9o.get("source_evidence") or {})
    hook = dict(source.get("hook_module") or {})
    supervisor = dict(source.get("live_supervisor") or {})
    owner = dict(p9o.get("owner_decision") or {})
    gates = dict(p9o.get("gates") or {})
    required_false = (
        "eligible_for_timer_hook_implementation",
        "eligible_for_hook_deployment",
        "eligible_for_live_timer_path_load",
        "eligible_for_live_order_submission",
        "eligible_for_stage_governance_change",
        "timer_hook_implementation_authorized",
        "hook_deployment_authorized",
        "timer_path_load_authorized",
        "live_order_submission_authorized",
        "target_plan_replacement_authorized",
        "executor_input_mutation_authorized",
        "remote_sync_authorized",
        "supervisor_run_authorized",
        "candidate_live_order_submission_authorized",
        "live_supervisor_loads_candidate_hook",
        "live_timer_path_loaded",
        "live_timer_service_enabled_or_invoked",
        "ran_supervisor",
        "timer_path_invoked",
        "remote_execution_performed",
        "remote_control_plane_touched",
        "wrote_live_hook_config",
        "implemented_hook",
        "deployed_hook",
        "loaded_hook",
        "target_plan_replaced",
        "executor_input_changed",
    )
    required_gates = (
        "owner_decision_p9o_execute_readback_only",
        "project_stage_boundary_preserved",
        "p9n_dry_load_readback_owner_gate_ready",
        "current_live_supervisor_not_loading_hook",
        "current_hook_hash_matches_p9n_source",
        "current_supervisor_hash_matches_p9n_source",
        "dry_load_outputs_under_proof_artifacts",
        "dry_load_mode_not_live_timer_service",
        "default_off_config_loaded",
        "artifact_sink_proof_artifacts_only",
        "candidate_order_authority_disabled",
        "candidate_live_order_submission_authorized_false",
        "execution_target_source_baseline_only",
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
        "live_timer_service_not_enabled_or_invoked",
        "supervisor_not_run_for_execution",
        "no_remote_sync_in_p9o",
        "no_live_timer_path_load_in_p9o",
        "no_executor_input_mutation_in_p9o",
        "no_target_plan_replacement_in_p9o",
        "no_live_mutation_in_p9o",
        "zero_orders_fills_in_p9o",
    )
    return (
        p9o.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9o_default_off_timer_path_dry_load_readback.v1"
        and p9o.get("status") == "ready"
        and not p9o.get("blockers")
        and p9o.get("dry_load_readback_scope")
        == "owner_gated_default_off_timer_path_dry_load_readback_execution_only"
        and p9o.get("default_off_timer_path_dry_load_readback_ready") is True
        and p9o.get("executed_default_off_timer_path_dry_load_readback") is True
        and p9o.get("dry_load_mode") == "default_off_timer_path_readback_not_live_timer_service"
        and p9o.get("dry_load_outputs_under_proof_artifacts") is True
        and p9o.get("default_off_config_loaded") is True
        and p9o.get("default_off_hook_enabled") is False
        and p9o.get("disabled_hook_readback_ready") is True
        and int(
            p9o.get("disabled_hook_candidate_artifacts_written_count")
            if p9o.get("disabled_hook_candidate_artifacts_written_count") is not None
            else -1
        )
        == 0
        and p9o.get("baseline_target_plan_byte_for_byte_unchanged") is True
        and p9o.get("executor_input_hash_unchanged") is True
        and p9o.get("executor_input_hash_equals_baseline") is True
        and p9o.get("executor_consumes_baseline_only") is True
        and p9o.get("candidate_shadow_hash_differs_from_executor") is True
        and p9o.get("candidate_plan_referenced_by_executor") is False
        and p9o.get("eligible_for_owner_p9p_review") is True
        and p9o.get("candidate_order_authority") == "disabled"
        and p9o.get("execution_target_source") == "baseline_only"
        and p9o.get("candidate_overlay_execution_path") == "excluded"
        and p9o.get("candidate_artifact_sink") == "proof_artifacts_only"
        and p9o.get("live_supervisor_source_unchanged") is True
        and no_live_mutation(p9o)
        and zero_orders_fills(p9o)
        and owner.get("decision") == "approve_p9o_execute_default_off_timer_path_dry_load_readback_only"
        and owner.get("default_off_timer_path_dry_load_readback_execution_approved") is True
        and owner.get("timer_hook_implementation_approved") is False
        and owner.get("hook_deployment_approved") is False
        and owner.get("live_timer_path_load_approved") is False
        and owner.get("live_order_submission_approved") is False
        and owner.get("target_plan_replacement_approved") is False
        and owner.get("executor_input_mutation_approved") is False
        and owner.get("live_config_mutation_approved") is False
        and owner.get("operator_state_mutation_approved") is False
        and owner.get("timer_or_service_mutation_approved") is False
        and owner.get("remote_sync_approved") is False
        and owner.get("supervisor_run_approved") is False
        and owner.get("repo_stage_change_approved") is False
        and hook.get("sha256") == current_hook_sha256
        and supervisor.get("sha256") == current_supervisor_sha256
        and current_supervisor_loads_candidate_hook is False
        and all(p9o.get(key) is False for key in required_false)
        and all(gates.get(key) is True for key in required_gates)
    )


def proof_payloads_ready(
    *,
    paths: dict[str, Path],
    dry_load_manifest: dict[str, Any],
    default_config: dict[str, Any],
    hook_summary: dict[str, Any],
    executor_readback: dict[str, Any],
    control_readback: dict[str, Any],
) -> dict[str, bool]:
    p9o_output_files_exist = all(path.exists() and path.is_file() for path in paths.values())
    p9o_output_files_under_proof_artifacts = all(output_under_proof_artifacts(path) for path in paths.values())
    dry_load_manifest_ready = (
        dry_load_manifest.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9o_dry_load_execution_manifest.v1"
        and dry_load_manifest.get("dry_load_readback_executed") is True
        and dry_load_manifest.get("dry_load_mode") == "default_off_timer_path_readback_not_live_timer_service"
        and dry_load_manifest.get("live_timer_path_loaded") is False
        and dry_load_manifest.get("live_timer_service_enabled_or_invoked") is False
        and dry_load_manifest.get("supervisor_run_invoked") is False
        and dry_load_manifest.get("remote_sync_performed") is False
        and dry_load_manifest.get("execution_target_source") == "baseline_only"
        and dry_load_manifest.get("candidate_order_authority") == "disabled"
        and dry_load_manifest.get("candidate_live_order_submission_authorized") is False
        and zero_orders_fills(dry_load_manifest)
    )
    default_config_ready = (
        default_config.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9o_default_off_config_readback.v1"
        and default_config.get("default_off_required") is True
        and default_config.get("proof_artifacts_only") is True
        and default_config.get("hook_config_enabled") is False
        and default_config.get("mode") == "observe_only"
        and default_config.get("artifact_sink") == "proof_artifacts_only"
        and default_config.get("candidate_order_authority") == "disabled"
        and default_config.get("candidate_live_order_submission_authorized") is False
        and default_config.get("candidate_overlay_execution_path") == "excluded"
        and default_config.get("execution_target_source") == "baseline_only"
        and default_config.get("live_timer_service_enabled_or_invoked") is False
        and default_config.get("supervisor_run_for_execution") is False
        and default_config.get("remote_sync_performed") is False
        and zero_orders_fills(default_config)
    )
    hook_summary_ready = (
        hook_summary.get("status") == "ready"
        and not hook_summary.get("blockers")
        and hook_summary.get("hook_enabled") is False
        and hook_summary.get("baseline_target_plan_byte_for_byte_unchanged") is True
        and hook_summary.get("executor_input_plan_hash_unchanged") is True
        and hook_summary.get("executor_input_plan_hash_equals_baseline") is True
        and hook_summary.get("executor_consumes_baseline_only") is True
        and int(
            hook_summary.get("candidate_artifacts_written_count")
            if hook_summary.get("candidate_artifacts_written_count") is not None
            else -1
        )
        == 0
        and hook_summary.get("candidate_plan_referenced_by_executor") is False
        and hook_summary.get("candidate_order_authority") == "disabled"
        and hook_summary.get("candidate_live_order_submission_authorized") is False
        and hook_summary.get("candidate_overlay_execution_path") == "excluded"
        and hook_summary.get("execution_target_source") == "baseline_only"
        and hook_summary.get("artifact_sink") == "proof_artifacts_only"
        and hook_summary.get("deployed_hook") is False
        and hook_summary.get("ran_supervisor") is False
        and hook_summary.get("timer_path_invoked") is False
        and no_live_mutation(hook_summary)
        and zero_orders_fills(hook_summary)
    )
    executor_hashes_match = (
        dict(executor_readback.get("baseline_target_plan") or {}).get("sha256")
        == dict(executor_readback.get("executor_input_plan") or {}).get("sha256")
    )
    candidate_hash_differs = (
        dict(executor_readback.get("candidate_shadow_plan") or {}).get("sha256")
        not in {
            "",
            dict(executor_readback.get("executor_input_plan") or {}).get("sha256"),
        }
    )
    executor_readback_ready = (
        executor_readback.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9o_executor_input_readback.v1"
        and dict(executor_readback.get("baseline_target_plan") or {}).get("exists") is True
        and dict(executor_readback.get("executor_input_plan") or {}).get("exists") is True
        and dict(executor_readback.get("candidate_shadow_plan") or {}).get("exists") is True
        and executor_readback.get("executor_input_hash_equals_baseline") is True
        and executor_hashes_match
        and executor_readback.get("candidate_shadow_hash_differs_from_executor") is True
        and candidate_hash_differs
        and executor_readback.get("candidate_plan_referenced_by_executor") is False
        and executor_readback.get("target_plan_replaced") is False
        and executor_readback.get("executor_input_changed") is False
        and zero_orders_fills(executor_readback)
    )
    control_readback_ready = (
        control_readback.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9o_control_boundary_readback.v1"
        and control_readback.get("scope") == "local_proof_artifacts_default_off_dry_load_readback_only"
        and control_readback.get("live_supervisor_source_unchanged") is True
        and control_readback.get("live_supervisor_loads_candidate_hook") is False
        and control_readback.get("live_timer_path_loaded") is False
        and control_readback.get("live_timer_service_enabled_or_invoked") is False
        and control_readback.get("ran_supervisor") is False
        and control_readback.get("remote_control_plane_touched") is False
        and control_readback.get("executor_input_mutated") is False
        and control_readback.get("target_plan_replaced") is False
        and control_readback.get("live_config_changed") is False
        and control_readback.get("operator_state_changed") is False
        and control_readback.get("timer_state_changed") is False
        and zero_orders_fills(control_readback)
    )
    return {
        "p9o_output_files_exist": p9o_output_files_exist,
        "p9o_output_files_under_proof_artifacts": p9o_output_files_under_proof_artifacts,
        "dry_load_manifest_ready": dry_load_manifest_ready,
        "default_off_config_readback_ready": default_config_ready,
        "disabled_hook_readback_summary_ready": hook_summary_ready,
        "executor_input_readback_ready": executor_readback_ready,
        "control_boundary_readback_ready": control_readback_ready,
    }


def build_phase9p(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    started_at = now_fn()
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")
    output_root = resolve_path(args.output_root) if args.output_root else resolve_path(DEFAULT_OUTPUT_PARENT) / run_id
    proof_root = output_root / "proof_artifacts" / "p9p" / run_id
    paths = {
        "project_profile": resolve_path(args.project_profile),
        "phase9o": resolve_path(args.phase9o_summary)
        if args.phase9o_summary
        else latest_match(PHASE9O_PARENT, "*/summary.json"),
        "hook_module": resolve_path(args.hook_module),
        "supervisor": resolve_path(args.supervisor),
    }
    project_profile = load_optional(paths["project_profile"])
    p9o = load_optional(paths["phase9o"])
    hook_sha = file_sha256(paths["hook_module"]) if paths["hook_module"].exists() else ""
    supervisor_sha_before = file_sha256(paths["supervisor"]) if paths["supervisor"].exists() else ""
    supervisor_loads_hook = current_supervisor_loads_hook(paths["supervisor"])
    owner_decision_record = build_owner_decision_record(args, started_at)

    p9o_paths = proof_file_paths(p9o)
    dry_load_manifest = load_optional(p9o_paths["dry_load_execution_manifest"])
    default_config = load_optional(p9o_paths["default_off_config_readback"])
    hook_summary = load_optional(p9o_paths["disabled_hook_readback_summary"])
    executor_readback = load_optional(p9o_paths["executor_input_readback"])
    control_readback = load_optional(p9o_paths["control_boundary_readback"])
    proof_checks = proof_payloads_ready(
        paths=p9o_paths,
        dry_load_manifest=dry_load_manifest,
        default_config=default_config,
        hook_summary=hook_summary,
        executor_readback=executor_readback,
        control_readback=control_readback,
    )
    p9o_ok = p9o_summary_ready(
        p9o,
        current_hook_sha256=hook_sha,
        current_supervisor_sha256=supervisor_sha_before,
        current_supervisor_loads_candidate_hook=supervisor_loads_hook,
    )
    source_evidence = {
        "project_profile": evidence_file(paths["project_profile"]),
        "phase9o_summary": evidence_file(paths["phase9o"]),
        "hook_module": evidence_file(paths["hook_module"]),
        "live_supervisor": evidence_file(paths["supervisor"]),
        "p9o_dry_load_execution_manifest": evidence_file(p9o_paths["dry_load_execution_manifest"]),
        "p9o_default_off_config_readback": evidence_file(p9o_paths["default_off_config_readback"]),
        "p9o_disabled_hook_readback_summary": evidence_file(p9o_paths["disabled_hook_readback_summary"]),
        "p9o_executor_input_readback": evidence_file(p9o_paths["executor_input_readback"]),
        "p9o_control_boundary_readback": evidence_file(p9o_paths["control_boundary_readback"]),
    }
    minimum_proof = {
        "stage_boundary_preserved": project_profile.get("current_stage") == "stage_1_research_readiness_only",
        "p9o_summary_ready": p9o_ok,
        "p9o_default_off_readback_executed": p9o.get("executed_default_off_timer_path_dry_load_readback") is True,
        "p9o_readback_default_off": p9o.get("default_off_hook_enabled") is False,
        "p9o_readback_not_live_timer_service": p9o.get("dry_load_mode")
        == "default_off_timer_path_readback_not_live_timer_service",
        "proof_files_exist": proof_checks["p9o_output_files_exist"],
        "proof_files_under_proof_artifacts": proof_checks["p9o_output_files_under_proof_artifacts"],
        "dry_load_manifest_ready": proof_checks["dry_load_manifest_ready"],
        "default_off_config_readback_ready": proof_checks["default_off_config_readback_ready"],
        "disabled_hook_readback_summary_ready": proof_checks["disabled_hook_readback_summary_ready"],
        "executor_input_readback_ready": proof_checks["executor_input_readback_ready"],
        "control_boundary_readback_ready": proof_checks["control_boundary_readback_ready"],
        "baseline_executor_input_hash_unchanged": p9o.get("executor_input_hash_equals_baseline") is True,
        "executor_consumes_baseline_only": p9o.get("executor_consumes_baseline_only") is True,
        "candidate_plan_not_referenced_by_executor": p9o.get("candidate_plan_referenced_by_executor") is False,
        "target_plan_not_replaced": p9o.get("target_plan_replaced") is False,
        "live_supervisor_not_loading_hook": supervisor_loads_hook is False
        and p9o.get("live_supervisor_loads_candidate_hook") is False,
        "live_timer_path_not_loaded": p9o.get("live_timer_path_loaded") is False,
        "supervisor_not_run": p9o.get("ran_supervisor") is False,
        "remote_not_touched": p9o.get("remote_execution_performed") is False
        and p9o.get("remote_control_plane_touched") is False,
        "zero_orders_fills": zero_orders_fills(p9o),
        "no_live_mutation": no_live_mutation(p9o),
    }
    control_boundary_readback = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9p_control_boundary_readback.v1",
        "run_id": run_id,
        "scope": "p9o_default_off_readback_sufficiency_review_only",
        "live_supervisor": source_evidence["live_supervisor"],
        "live_supervisor_sha256_before": supervisor_sha_before,
        "live_supervisor_sha256_after": file_sha256(paths["supervisor"]) if paths["supervisor"].exists() else "",
        "live_supervisor_source_unchanged": True,
        "live_supervisor_loads_candidate_hook": supervisor_loads_hook,
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
        "contract_version": "hv_balanced_dth60_coinglass_phase9p_review_decision_matrix.v1",
        "run_id": run_id,
        "review_question": "is_p9o_default_off_readback_sufficient_to_enter_separate_next_owner_gate",
        "minimum_proof": minimum_proof,
        "authorizations": {
            "p9p_review_default_off_readback_sufficiency": str(args.owner_decision) == APPROVE_P9P_DECISION,
            "enter_separate_next_owner_gate_discussion": str(args.owner_decision) == APPROVE_P9P_DECISION,
            "execute_next_owner_gate": False,
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
    owner_review_packet = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9p_owner_review_packet.v1",
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "review_scope": "owner_gated_p9o_default_off_readback_sufficiency_review_only",
        "owner_decision": owner_decision_record,
        "source_evidence": source_evidence,
        "minimum_proof": minimum_proof,
        "review_result": {
            "p9o_default_off_readback_sufficient_for_next_owner_gate": False,
            "next_owner_gate_execution_authorized": False,
            "timer_path_load_authorized": False,
            "live_order_submission_authorized": False,
        },
    }
    gates = {
        "owner_decision_p9p_review_only": str(args.owner_decision) == APPROVE_P9P_DECISION,
        **minimum_proof,
        "review_output_under_proof_artifacts": output_under_proof_artifacts(proof_root),
        "no_timer_hook_implementation_in_p9p": True,
        "no_hook_deployment_in_p9p": True,
        "no_timer_path_load_in_p9p": True,
        "no_supervisor_run_in_p9p": True,
        "no_remote_execution_in_p9p": True,
        "no_executor_input_mutation_in_p9p": True,
        "no_target_plan_replacement_in_p9p": True,
        "no_live_mutation_in_p9p": True,
        "zero_orders_fills_in_p9p": True,
    }
    blockers = [key for key, value in gates.items() if not value]
    status = "ready" if not blockers else "blocked"
    sufficient = status == "ready"
    owner_review_packet["review_result"][
        "p9o_default_off_readback_sufficient_for_next_owner_gate"
    ] = sufficient

    write_json(output_root / "owner_decision_record.json", owner_decision_record)
    write_json(proof_root / "owner_review_packet.json", owner_review_packet)
    write_json(proof_root / "review_decision_matrix.json", decision_matrix)
    write_json(proof_root / "control_boundary_readback.json", control_boundary_readback)

    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "review_scope": "owner_gated_p9o_default_off_readback_sufficiency_review_only",
        "owner_decision": owner_decision_record,
        "source_evidence": source_evidence,
        "p9o_default_off_readback_sufficient_for_next_owner_gate": sufficient,
        "eligible_for_next_owner_gate_discussion": sufficient,
        "next_owner_gate_execution_authorized": False,
        "eligible_for_timer_hook_implementation": False,
        "eligible_for_hook_deployment": False,
        "eligible_for_live_timer_path_load": False,
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
        "default_off_readback_executed": minimum_proof["p9o_default_off_readback_executed"],
        "default_off_readback_proof_files_ready": all(proof_checks.values()),
        "default_off_readback_not_live_timer_service": minimum_proof["p9o_readback_not_live_timer_service"],
        "baseline_executor_input_hash_unchanged": minimum_proof["baseline_executor_input_hash_unchanged"],
        "executor_consumes_baseline_only": minimum_proof["executor_consumes_baseline_only"],
        "candidate_plan_referenced_by_executor": False,
        "target_plan_replaced": False,
        "live_supervisor_loads_candidate_hook": supervisor_loads_hook,
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
        "executor_input_changed": False,
        "recommended_next_gate": (
            "separate_owner_gate_required_before_any_default_off_timer_path_load_or_remote_scope"
        ),
        "proof_root": str(proof_root),
        "minimum_proof": minimum_proof,
        "proof_checks": proof_checks,
        "gates": gates,
        "blockers": blockers,
        "output_files": {
            "summary": str(output_root / "summary.json"),
            "owner_decision_record": str(output_root / "owner_decision_record.json"),
            "owner_review_packet": str(proof_root / "owner_review_packet.json"),
            "review_decision_matrix": str(proof_root / "review_decision_matrix.json"),
            "control_boundary_readback": str(proof_root / "control_boundary_readback.json"),
            "report": str(output_root / "p9p_owner_review_after_default_off_readback.md"),
        },
    }
    write_json(output_root / "summary.json", summary)
    (output_root / "p9p_owner_review_after_default_off_readback.md").write_text(
        render_markdown(summary),
        encoding="utf-8",
    )
    return summary, 0 if status == "ready" else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9P Owner Review After Default-Off Readback",
        "",
        f"`Status: {summary['status']}`",
        "",
        "## Boundary",
        "",
        "This review only decides whether P9O is sufficient to enter a separate next owner gate.",
        "",
        "```text",
        "review_scope = owner_gated_p9o_default_off_readback_sufficiency_review_only",
        "p9o_default_off_readback_sufficient_for_next_owner_gate = "
        f"{str(bool(summary['p9o_default_off_readback_sufficient_for_next_owner_gate'])).lower()}",
        "eligible_for_next_owner_gate_discussion = "
        f"{str(bool(summary['eligible_for_next_owner_gate_discussion'])).lower()}",
        "next_owner_gate_execution_authorized = false",
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
    ]
    for key, value in dict(summary.get("minimum_proof") or {}).items():
        lines.append(f"{key} = {str(bool(value)).lower()}")
    lines.extend(["```", "", "## Gates", "", "```text"])
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
    summary, exit_code = build_phase9p(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
