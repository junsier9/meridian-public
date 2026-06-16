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


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9n_default_off_timer_path_dry_load_readback_owner_gate.v1"
APPROVE_P9N_DECISION = "approve_p9n_execute_default_off_timer_path_dry_load_readback_only"
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9n_dry_load_readback_owner_gate"
PHASE9M_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9m_default_off_timer_path_dry_load_proposal"
PROJECT_PROFILE = "config/project_governance/project_profile.json"
HOOK_MODULE = "src/enhengclaw/live_trading/dth60_observe_only_shadow_hook.py"
SUPERVISOR_PATH = "src/enhengclaw/live_trading/mainnet_live_supervisor.py"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build the P9N owner gate for deciding whether a future default-off "
            "timer-path dry-load readback may be executed. P9N does not execute "
            "the readback, implement, deploy, load a live timer path, run the "
            "supervisor, mutate executor input, sync remote state, or authorize orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9m-summary", default="")
    parser.add_argument("--hook-module", default=HOOK_MODULE)
    parser.add_argument("--supervisor", default=SUPERVISOR_PATH)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9N_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:execute_p9n_owner_gate_default_off_timer_path_dry_load_readback",
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
    if not path or str(path) in {"", "."}:
        return {"path": "", "exists": False, "sha256": ""}
    resolved = resolve_path(path)
    if not resolved.exists() or not resolved.is_file():
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
    return (
        int_zero(payload, "orders_submitted")
        and int_zero(payload, "fill_count")
        and int_zero(payload, "fills_observed")
        and payload.get("exchange_order_submission") == "disabled"
    )


def proposed_contract_ready(proposal: dict[str, Any]) -> bool:
    contract = dict(proposal.get("proposed_future_dry_load_contract") or {})
    hook_config = dict(proposal.get("default_off_hook_config_contract") or {})
    required_false = (
        "p9m_authorizes_timer_path_dry_load",
        "p9m_authorizes_timer_hook_implementation",
        "p9m_authorizes_hook_deployment",
        "p9m_authorizes_timer_path_load",
        "p9m_authorizes_supervisor_run",
        "p9m_authorizes_live_orders",
    )
    return (
        proposal.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9m_default_off_timer_path_dry_load_proposal_body.v1"
        and proposal.get("proposal_scope") == "owner_gated_default_off_timer_path_dry_load_proposal_only"
        and proposal.get("proposal_status") == "draft_for_future_owner_review"
        and proposal.get("future_gate_required") is True
        and proposal.get("proposed_future_gate")
        == "P9N_default_off_timer_path_dry_load_readback_only_if_separately_requested"
        and proposal.get("proposed_future_gate_scope") == "default_off_timer_path_dry_load_readback_only"
        and all(proposal.get(key) is False for key in required_false)
        and contract.get("default_off_required") is True
        and contract.get("hook_config_enabled_default") is False
        and contract.get("observe_only_mode_required") is True
        and contract.get("candidate_order_authority") == "disabled"
        and contract.get("candidate_live_order_submission_authorized") is False
        and contract.get("execution_target_source") == "baseline_only"
        and contract.get("candidate_overlay_execution_path") == "excluded"
        and contract.get("candidate_artifact_sink") == "proof_artifacts_only"
        and contract.get("executor_input_must_remain_baseline_only") is True
        and contract.get("candidate_plan_must_not_be_referenced_by_executor") is True
        and contract.get("target_plan_must_not_be_replaced") is True
        and contract.get("live_timer_service_must_not_be_enabled_or_invoked") is True
        and contract.get("supervisor_must_not_be_run_for_execution") is True
        and contract.get("remote_sync_must_not_occur") is True
        and contract.get("live_config_must_not_change") is True
        and contract.get("operator_state_must_not_change") is True
        and contract.get("timer_state_must_not_change") is True
        and int(contract.get("orders_submitted_must_equal", -1)) == 0
        and int(contract.get("fill_count_must_equal", -1)) == 0
        and hook_config.get("ObserveOnlyShadowHookConfig.enabled") is False
        and hook_config.get("ObserveOnlyShadowHookConfig.mode") == "observe_only"
        and hook_config.get("ObserveOnlyShadowHookConfig.artifact_sink") == "proof_artifacts_only"
        and hook_config.get("ObserveOnlyShadowHookConfig.candidate_order_authority") == "disabled"
        and hook_config.get("ObserveOnlyShadowHookConfig.candidate_live_order_submission_authorized") is False
        and hook_config.get("ObserveOnlyShadowHookConfig.execution_target_source") == "baseline_only"
        and hook_config.get("ObserveOnlyShadowHookConfig.candidate_overlay_execution_path") == "excluded"
    )


def p9m_ready(
    summary: dict[str, Any],
    *,
    current_hook_sha256: str,
    current_supervisor_sha256: str,
) -> bool:
    gates = dict(summary.get("gates") or {})
    source = dict(summary.get("source_evidence") or {})
    hook = dict(source.get("hook_module") or {})
    supervisor = dict(source.get("live_supervisor") or {})
    owner = dict(summary.get("owner_decision") or {})
    required_gates = (
        "owner_decision_p9m_proposal_only",
        "project_stage_boundary_preserved",
        "p9l_proposal_preparation_gate_ready",
        "current_live_supervisor_not_loading_hook",
        "current_hook_hash_matches_p9l_source",
        "current_supervisor_hash_matches_p9l_source",
        "proposal_output_under_proof_artifacts",
        "proposal_body_output_under_proof_artifacts",
        "proposal_default_off_required",
        "proposal_artifact_sink_proof_artifacts_only",
        "proposal_executor_input_source_baseline_only",
        "proposal_candidate_order_authority_disabled",
        "proposal_requires_separate_future_dry_load_gate",
        "no_timer_path_dry_load_execution_in_p9m",
        "no_timer_hook_implementation_in_p9m",
        "no_hook_deployment_in_p9m",
        "no_timer_path_load_in_p9m",
        "no_supervisor_run_in_p9m",
        "no_remote_execution_in_p9m",
        "no_executor_input_mutation_in_p9m",
        "no_target_plan_replacement_in_p9m",
        "no_live_mutation_in_p9m",
        "zero_orders_fills_in_p9m",
    )
    return (
        summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("proposal_scope") == "owner_gated_default_off_timer_path_dry_load_proposal_only"
        and summary.get("default_off_timer_path_dry_load_proposal_ready") is True
        and summary.get("eligible_for_future_default_off_timer_path_dry_load_review") is True
        and summary.get("prepared_default_off_timer_path_dry_load_proposal") is True
        and summary.get("wrote_default_off_timer_path_dry_load_proposal_body") is True
        and summary.get("proposal_body_sink") == "proof_artifacts_only"
        and summary.get("p9m_authorizes_timer_path_dry_load") is False
        and summary.get("future_dry_load_gate_required") is True
        and summary.get("proposed_future_gate")
        == "P9N_default_off_timer_path_dry_load_readback_only_if_separately_requested"
        and summary.get("proposed_dry_load_default_off") is True
        and summary.get("proposed_dry_load_mode") == "proposal_only_not_loaded"
        and summary.get("proposed_timer_load_mode") == "proposal_only_not_loaded"
        and summary.get("proposed_executor_input_source") == "baseline_only"
        and summary.get("proposed_candidate_artifact_sink") == "proof_artifacts_only"
        and summary.get("proposed_candidate_order_authority") == "disabled"
        and summary.get("proposed_candidate_live_order_submission_authorized") is False
        and summary.get("eligible_for_timer_path_dry_load_execution") is False
        and summary.get("eligible_for_timer_hook_implementation") is False
        and summary.get("eligible_for_hook_deployment") is False
        and summary.get("eligible_for_timer_path_load") is False
        and summary.get("eligible_for_live_order_submission") is False
        and summary.get("eligible_for_stage_governance_change") is False
        and summary.get("timer_path_dry_load_authorized") is False
        and summary.get("timer_hook_implementation_authorized") is False
        and summary.get("hook_deployment_authorized") is False
        and summary.get("timer_path_load_authorized") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("target_plan_replacement_authorized") is False
        and summary.get("executor_input_mutation_authorized") is False
        and summary.get("remote_sync_authorized") is False
        and summary.get("supervisor_run_authorized") is False
        and summary.get("candidate_order_authority") == "disabled"
        and summary.get("candidate_live_order_submission_authorized") is False
        and summary.get("execution_target_source") == "baseline_only"
        and summary.get("candidate_overlay_execution_path") == "excluded"
        and summary.get("candidate_artifact_sink") == "proof_artifacts_only"
        and summary.get("live_supervisor_loads_candidate_hook") is False
        and summary.get("live_supervisor_source_unchanged") is True
        and summary.get("live_timer_path_loaded") is False
        and summary.get("live_timer_service_enabled_or_invoked") is False
        and summary.get("ran_supervisor") is False
        and summary.get("timer_path_invoked") is False
        and summary.get("remote_execution_performed") is False
        and summary.get("remote_control_plane_touched") is False
        and no_live_mutation(summary)
        and zero_orders_fills(summary)
        and summary.get("wrote_live_hook_config") is False
        and summary.get("implemented_hook") is False
        and summary.get("deployed_hook") is False
        and summary.get("loaded_hook") is False
        and summary.get("target_plan_replaced") is False
        and summary.get("executor_input_changed") is False
        and owner.get("decision") == "approve_p9m_default_off_timer_path_dry_load_proposal_only"
        and owner.get("draft_default_off_timer_path_dry_load_proposal_approved") is True
        and owner.get("write_proposal_artifact_approved") is True
        and owner.get("timer_path_dry_load_approved") is False
        and owner.get("timer_hook_implementation_approved") is False
        and owner.get("hook_deployment_approved") is False
        and owner.get("timer_path_load_approved") is False
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
        and all(gates.get(key) is True for key in required_gates)
    )


def build_owner_decision_record(args: argparse.Namespace, started_at: datetime) -> dict[str, Any]:
    approved = str(args.owner_decision) == APPROVE_P9N_DECISION
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9n_owner_decision.v1",
        "owner": str(args.owner),
        "decision": str(args.owner_decision),
        "decision_source": str(args.owner_decision_source),
        "recorded_at_utc": iso_z(started_at),
        "decision_question": "allow_future_default_off_timer_path_dry_load_readback_execution_only",
        "decision_effect": (
            "authorize_future_default_off_timer_path_dry_load_readback_execution_only"
            if approved
            else "none"
        ),
        "future_default_off_timer_path_dry_load_readback_execution_approved": approved,
        "write_p9n_owner_gate_artifact_approved": approved,
        "execute_readback_in_p9n_approved": False,
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


def dry_load_readback_execution_gate(
    *,
    run_id: str,
    owner_decision: dict[str, Any],
    source_evidence: dict[str, dict[str, Any]],
    ready: bool,
) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9n_dry_load_readback_execution_gate.v1",
        "run_id": run_id,
        "gate_scope": "owner_gated_default_off_timer_path_dry_load_readback_execution_permission_only",
        "owner_decision": owner_decision,
        "source_evidence": source_evidence,
        "allowed_next_action": (
            "execute_default_off_timer_path_dry_load_readback" if ready else ""
        ),
        "allowed_next_gate": (
            "P9O_default_off_timer_path_dry_load_readback_execution_only_if_separately_requested"
            if ready
            else ""
        ),
        "allowed_next_action_constraints": {
            "default_off_required": True,
            "proof_artifacts_only": True,
            "candidate_order_authority": "disabled",
            "candidate_live_order_submission_authorized": False,
            "executor_input_must_remain_baseline_only": True,
            "candidate_plan_must_not_be_referenced_by_executor": True,
            "target_plan_must_not_be_replaced": True,
            "must_not_modify_mainnet_live_supervisor": True,
            "must_not_modify_live_config": True,
            "must_not_modify_operator_state": True,
            "must_not_modify_timer_or_service_state": True,
            "must_not_enable_or_invoke_live_timer_service": True,
            "must_not_run_supervisor_for_execution": True,
            "must_not_remote_sync": True,
            "orders_submitted_must_equal": 0,
            "fill_count_must_equal": 0,
        },
        "executed_in_p9n": False,
        "explicitly_not_authorized": [
            "execute_readback_inside_p9n",
            "timer_hook_implementation",
            "hook_deployment",
            "live_timer_path_load",
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


def non_authorization_matrix(run_id: str, ready: bool) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9n_non_authorization_matrix.v1",
        "run_id": run_id,
        "authorizations": {
            "allow_future_default_off_timer_path_dry_load_readback_execution": ready,
            "write_p9n_owner_gate_artifact_under_proof_artifacts": ready,
            "execute_default_off_timer_path_dry_load_readback_inside_p9n": False,
            "timer_hook_implementation": False,
            "hook_deployment": False,
            "live_timer_path_load": False,
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


def build_phase9n(
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
    proof_root = output_root / "proof_artifacts" / "p9n" / run_id
    proof_root.mkdir(parents=True, exist_ok=True)

    paths = {
        "project_profile": resolve_path(args.project_profile),
        "phase9m": (
            resolve_path(args.phase9m_summary)
            if str(getattr(args, "phase9m_summary", "") or "").strip()
            else latest_match(PHASE9M_PARENT, "*/summary.json")
        ),
        "hook_module": resolve_path(args.hook_module),
        "supervisor": resolve_path(args.supervisor),
    }
    project_profile = load_optional(paths["project_profile"])
    p9m = load_optional(paths["phase9m"])
    proposal_path_text = str(
        dict(p9m.get("output_files") or {}).get("default_off_timer_path_dry_load_proposal") or ""
    )
    proposal_path = resolve_path(proposal_path_text) if proposal_path_text.strip() else Path("")
    proposal = load_optional(proposal_path)
    current_hook_sha = file_sha256(paths["hook_module"]) if paths["hook_module"].exists() else ""
    supervisor_sha_before = file_sha256(paths["supervisor"]) if paths["supervisor"].exists() else ""
    supervisor_text = paths["supervisor"].read_text(encoding="utf-8") if paths["supervisor"].exists() else ""
    live_supervisor_loads_hook_now = "dth60_observe_only_shadow_hook" in supervisor_text
    owner_decision_record = build_owner_decision_record(args, started_at)

    source_evidence = {
        "project_profile": evidence_file(paths["project_profile"]),
        "phase9m_summary": evidence_file(paths["phase9m"]),
        "phase9m_proposal_body": evidence_file(proposal_path),
        "hook_module": evidence_file(paths["hook_module"]),
        "live_supervisor": evidence_file(paths["supervisor"]),
    }
    p9m_ok = p9m_ready(
        p9m,
        current_hook_sha256=current_hook_sha,
        current_supervisor_sha256=supervisor_sha_before,
    )
    proposal_ok = proposed_contract_ready(proposal)

    gates = {
        "owner_decision_p9n_dry_load_readback_gate_only": str(args.owner_decision) == APPROVE_P9N_DECISION,
        "project_stage_boundary_preserved": project_profile.get("current_stage") == "stage_1_research_readiness_only",
        "p9m_default_off_timer_path_dry_load_proposal_ready": p9m_ok,
        "p9m_proposal_body_ready": proposal_ok,
        "current_live_supervisor_not_loading_hook": not live_supervisor_loads_hook_now,
        "current_hook_hash_matches_p9m_source": (
            dict(dict(p9m.get("source_evidence") or {}).get("hook_module") or {}).get("sha256")
            == current_hook_sha
        ),
        "current_supervisor_hash_matches_p9m_source": (
            dict(dict(p9m.get("source_evidence") or {}).get("live_supervisor") or {}).get("sha256")
            == supervisor_sha_before
        ),
        "dry_load_readback_gate_output_under_proof_artifacts": output_under_proof_artifacts(proof_root),
        "future_readback_must_be_default_off": True,
        "future_readback_must_be_proof_artifacts_only": True,
        "future_readback_must_keep_order_authority_disabled": True,
        "future_readback_must_keep_executor_baseline_only": True,
        "future_readback_must_not_reference_candidate_plan_by_executor": True,
        "future_readback_must_not_replace_target_plan": True,
        "future_readback_must_not_enable_live_timer_service": True,
        "future_readback_must_not_run_supervisor_for_execution": True,
        "no_readback_execution_in_p9n": True,
        "no_timer_hook_implementation_in_p9n": True,
        "no_hook_deployment_in_p9n": True,
        "no_live_timer_path_load_in_p9n": True,
        "no_supervisor_run_in_p9n": True,
        "no_remote_execution_in_p9n": True,
        "no_executor_input_mutation_in_p9n": True,
        "no_target_plan_replacement_in_p9n": True,
        "no_live_mutation_in_p9n": True,
        "zero_orders_fills_in_p9n": True,
    }
    blockers = [key for key, value in gates.items() if not value]
    status = "ready" if not blockers else "blocked"
    gate_ready = status == "ready"

    control_boundary_readback = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9n_control_boundary_readback.v1",
        "run_id": run_id,
        "scope": "local_source_and_retained_p9m_proposal_only",
        "live_supervisor": source_evidence["live_supervisor"],
        "live_supervisor_sha256_before": supervisor_sha_before,
        "live_supervisor_sha256_after": file_sha256(paths["supervisor"]) if paths["supervisor"].exists() else "",
        "live_supervisor_loads_candidate_hook": live_supervisor_loads_hook_now,
        "eligible_to_execute_default_off_timer_path_dry_load_readback": gate_ready,
        "executed_default_off_timer_path_dry_load_readback": False,
        "live_timer_path_loaded": False,
        "live_timer_service_enabled_or_invoked": False,
        "ran_supervisor": False,
        "remote_control_plane_touched": False,
        "executor_input_mutated": False,
        "target_plan_replaced": False,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "orders_submitted": 0,
        "fill_count": 0,
    }
    control_boundary_readback["live_supervisor_source_unchanged"] = (
        control_boundary_readback["live_supervisor_sha256_before"]
        == control_boundary_readback["live_supervisor_sha256_after"]
    )

    gate = dry_load_readback_execution_gate(
        run_id=run_id,
        owner_decision=owner_decision_record,
        source_evidence=source_evidence,
        ready=gate_ready,
    )
    matrix = non_authorization_matrix(run_id, gate_ready)
    write_json(output_root / "owner_decision_record.json", owner_decision_record)
    write_json(proof_root / "dry_load_readback_execution_gate.json", gate)
    write_json(proof_root / "non_authorization_matrix.json", matrix)
    write_json(proof_root / "control_boundary_readback.json", control_boundary_readback)

    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "gate_scope": "owner_gated_default_off_timer_path_dry_load_readback_execution_permission_only",
        "owner_decision": owner_decision_record,
        "source_evidence": source_evidence,
        "p9n_default_off_timer_path_dry_load_readback_owner_gate_ready": gate_ready,
        "eligible_to_execute_default_off_timer_path_dry_load_readback": gate_ready,
        "executed_default_off_timer_path_dry_load_readback": False,
        "wrote_p9n_owner_gate_artifact": True,
        "allowed_next_gate": (
            "P9O_default_off_timer_path_dry_load_readback_execution_only_if_separately_requested"
            if gate_ready
            else ""
        ),
        "future_readback_default_off_required": True,
        "future_readback_artifact_sink_required": "proof_artifacts_only",
        "future_readback_executor_input_required": "baseline_only",
        "future_readback_candidate_order_authority_required": "disabled",
        "future_readback_live_order_submission_authorized_required": False,
        "future_readback_must_not_enable_live_timer_service": True,
        "future_readback_must_not_run_supervisor_for_execution": True,
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
        "recommended_next_gate": (
            "P9O_default_off_timer_path_dry_load_readback_execution_only_if_separately_requested"
            if gate_ready
            else ""
        ),
        "proof_root": str(proof_root),
        "gates": gates,
        "blockers": blockers,
        "output_files": {
            "summary": str(output_root / "summary.json"),
            "owner_decision_record": str(output_root / "owner_decision_record.json"),
            "dry_load_readback_execution_gate": str(proof_root / "dry_load_readback_execution_gate.json"),
            "non_authorization_matrix": str(proof_root / "non_authorization_matrix.json"),
            "control_boundary_readback": str(proof_root / "control_boundary_readback.json"),
            "report": str(output_root / "p9n_default_off_timer_path_dry_load_readback_owner_gate.md"),
        },
    }
    write_json(output_root / "summary.json", summary)
    (output_root / "p9n_default_off_timer_path_dry_load_readback_owner_gate.md").write_text(
        render_markdown(summary),
        encoding="utf-8",
    )
    return summary, 0 if status == "ready" else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9N Default-Off Timer-Path Dry-Load Readback Owner Gate",
        "",
        f"`Status: {summary['status']}`",
        "",
        "## Boundary",
        "",
        "P9N only decides whether a future default-off timer-path dry-load readback may be executed.",
        "",
        "```text",
        "gate_scope = owner_gated_default_off_timer_path_dry_load_readback_execution_permission_only",
        "eligible_to_execute_default_off_timer_path_dry_load_readback = "
        f"{str(bool(summary['eligible_to_execute_default_off_timer_path_dry_load_readback'])).lower()}",
        "executed_default_off_timer_path_dry_load_readback = false",
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
    summary, exit_code = build_phase9n(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
