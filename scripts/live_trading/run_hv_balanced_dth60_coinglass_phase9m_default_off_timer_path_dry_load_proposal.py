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


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9m_default_off_timer_path_dry_load_proposal.v1"
APPROVE_P9M_DECISION = "approve_p9m_default_off_timer_path_dry_load_proposal_only"
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9m_default_off_timer_path_dry_load_proposal"
PHASE9L_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9l_prepare_dry_load_proposal_gate"
PROJECT_PROFILE = "config/project_governance/project_profile.json"
HOOK_MODULE = "src/enhengclaw/live_trading/dth60_observe_only_shadow_hook.py"
SUPERVISOR_PATH = "src/enhengclaw/live_trading/mainnet_live_supervisor.py"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build the P9M default-off timer-path dry-load proposal bundle. "
            "P9M drafts a proposal under proof_artifacts only. It does not "
            "implement, deploy, load, dry-load, run a timer/supervisor path, "
            "mutate executor input, sync remote state, or authorize orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9l-summary", default="")
    parser.add_argument("--hook-module", default=HOOK_MODULE)
    parser.add_argument("--supervisor", default=SUPERVISOR_PATH)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9M_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:execute_p9m_default_off_timer_path_dry_load_proposal_only",
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
    return (
        int_zero(payload, "orders_submitted")
        and int_zero(payload, "fill_count")
        and int_zero(payload, "fills_observed")
        and payload.get("exchange_order_submission") == "disabled"
    )


def p9l_ready(
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
        "owner_decision_p9l_prepare_proposal_only",
        "project_stage_boundary_preserved",
        "p9k_owner_review_after_dry_load_ready",
        "current_live_supervisor_not_loading_hook",
        "current_hook_hash_matches_p9k_source",
        "current_supervisor_hash_matches_p9k_source",
        "proposal_preparation_gate_output_under_proof_artifacts",
        "future_proposal_must_be_default_off",
        "future_proposal_must_be_proof_artifacts_only",
        "future_proposal_must_keep_order_authority_disabled",
        "future_proposal_must_keep_executor_baseline_only",
        "no_proposal_body_written_in_p9l",
        "no_timer_hook_implementation_in_p9l",
        "no_hook_deployment_in_p9l",
        "no_timer_path_load_in_p9l",
        "no_supervisor_run_in_p9l",
        "no_remote_execution_in_p9l",
        "no_executor_input_mutation_in_p9l",
        "no_target_plan_replacement_in_p9l",
        "no_live_mutation_in_p9l",
        "zero_orders_fills_in_p9l",
    )
    return (
        summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("gate_scope") == "owner_gated_prepare_default_off_timer_path_dry_load_proposal_only"
        and summary.get("p9l_prepare_default_off_timer_path_dry_load_proposal_gate_ready") is True
        and summary.get("eligible_to_prepare_default_off_timer_path_dry_load_proposal") is True
        and summary.get("prepared_default_off_timer_path_dry_load_proposal") is False
        and summary.get("wrote_timer_path_dry_load_proposal_body") is False
        and summary.get("future_proposal_default_off_required") is True
        and summary.get("future_proposal_artifact_sink_required") == "proof_artifacts_only"
        and summary.get("future_proposal_executor_input_required") == "baseline_only"
        and summary.get("future_proposal_live_order_submission_authorized_required") is False
        and summary.get("eligible_for_timer_hook_implementation") is False
        and summary.get("eligible_for_hook_deployment") is False
        and summary.get("eligible_for_timer_path_load") is False
        and summary.get("eligible_for_live_order_submission") is False
        and summary.get("eligible_for_stage_governance_change") is False
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
        and owner.get("decision") == "approve_p9l_prepare_default_off_timer_path_dry_load_proposal_only"
        and owner.get("prepare_default_off_timer_path_dry_load_proposal_approved") is True
        and owner.get("write_proposal_artifact_approved") is True
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
    approved = str(args.owner_decision) == APPROVE_P9M_DECISION
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9m_owner_decision.v1",
        "owner": str(args.owner),
        "decision": str(args.owner_decision),
        "decision_source": str(args.owner_decision_source),
        "recorded_at_utc": iso_z(started_at),
        "decision_question": "draft_default_off_timer_path_dry_load_proposal_only",
        "decision_effect": (
            "authorize_default_off_timer_path_dry_load_proposal_body_only" if approved else "none"
        ),
        "draft_default_off_timer_path_dry_load_proposal_approved": approved,
        "write_proposal_artifact_approved": approved,
        "timer_path_dry_load_approved": False,
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


def default_off_timer_path_dry_load_proposal(
    *,
    run_id: str,
    owner_decision: dict[str, Any],
    source_evidence: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9m_default_off_timer_path_dry_load_proposal_body.v1",
        "run_id": run_id,
        "proposal_scope": "owner_gated_default_off_timer_path_dry_load_proposal_only",
        "proposal_status": "draft_for_future_owner_review",
        "owner_decision": owner_decision,
        "source_evidence": source_evidence,
        "p9m_authorizes_timer_path_dry_load": False,
        "p9m_authorizes_timer_hook_implementation": False,
        "p9m_authorizes_hook_deployment": False,
        "p9m_authorizes_timer_path_load": False,
        "p9m_authorizes_supervisor_run": False,
        "p9m_authorizes_live_orders": False,
        "future_gate_required": True,
        "proposed_future_gate": "P9N_default_off_timer_path_dry_load_readback_only_if_separately_requested",
        "proposed_future_gate_scope": "default_off_timer_path_dry_load_readback_only",
        "proposed_future_dry_load_contract": {
            "default_off_required": True,
            "hook_config_enabled_default": False,
            "observe_only_mode_required": True,
            "candidate_order_authority": "disabled",
            "candidate_live_order_submission_authorized": False,
            "execution_target_source": "baseline_only",
            "candidate_overlay_execution_path": "excluded",
            "candidate_artifact_sink": "proof_artifacts_only",
            "executor_input_must_remain_baseline_only": True,
            "candidate_plan_must_not_be_referenced_by_executor": True,
            "target_plan_must_not_be_replaced": True,
            "live_timer_service_must_not_be_enabled_or_invoked": True,
            "supervisor_must_not_be_run_for_execution": True,
            "remote_sync_must_not_occur": True,
            "live_config_must_not_change": True,
            "operator_state_must_not_change": True,
            "timer_state_must_not_change": True,
            "orders_submitted_must_equal": 0,
            "fill_count_must_equal": 0,
        },
        "default_off_hook_config_contract": {
            "ObserveOnlyShadowHookConfig.enabled": False,
            "ObserveOnlyShadowHookConfig.mode": "observe_only",
            "ObserveOnlyShadowHookConfig.artifact_sink": "proof_artifacts_only",
            "ObserveOnlyShadowHookConfig.candidate_order_authority": "disabled",
            "ObserveOnlyShadowHookConfig.candidate_live_order_submission_authorized": False,
            "ObserveOnlyShadowHookConfig.execution_target_source": "baseline_only",
            "ObserveOnlyShadowHookConfig.candidate_overlay_execution_path": "excluded",
        },
        "minimum_future_dry_load_inputs": [
            "retained_p9m_summary",
            "retained_p9l_summary",
            "current_hook_module_hash_matching_p9m_source",
            "current_live_supervisor_hash_matching_p9m_source",
            "fresh_baseline_target_plan_artifact",
            "fresh_executor_input_readback",
            "candidate_shadow_artifact_root_under_proof_artifacts",
        ],
        "minimum_future_dry_load_proofs": [
            "default_off_config_readback",
            "timer_path_loaded_flag_false_or_dry_load_only",
            "timer_service_enabled_or_invoked_false",
            "supervisor_run_false",
            "executor_input_hash_equals_baseline_target_plan_hash",
            "candidate_plan_referenced_by_executor_false",
            "candidate_artifacts_under_proof_artifacts_only",
            "live_supervisor_source_hash_unchanged",
            "live_config_changed_false",
            "operator_state_changed_false",
            "timer_state_changed_false",
            "remote_control_plane_touched_false",
            "orders_submitted_zero",
            "fill_count_zero",
        ],
        "explicit_non_authorizations": [
            "timer_hook_implementation",
            "hook_deployment",
            "timer_path_load",
            "timer_path_dry_load_execution",
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


def proposal_acceptance_checklist(run_id: str) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9m_proposal_acceptance_checklist.v1",
        "run_id": run_id,
        "status": "draft_for_future_owner_review",
        "p9m_authorizes_checklist_execution": False,
        "future_gate_required_before_any_dry_load": True,
        "must_be_true_before_future_p9n": [
            "separate_owner_decision_exists",
            "proposal_body_hash_matches_p9m_retained_artifact",
            "project_stage_boundary_still_stage_1",
            "current_live_supervisor_still_not_loading_candidate_hook",
            "current_hook_module_hash_matches_p9m_source_or_owner_reviews_hash_change",
            "current_live_supervisor_hash_matches_p9m_source_or_owner_reviews_hash_change",
            "candidate_output_root_under_proof_artifacts",
            "default_off_config_readback_before_any_timer_path_probe",
            "executor_input_source_baseline_only",
            "candidate_order_authority_disabled",
        ],
        "must_remain_false_in_future_p9n_unless_separately_authorized": [
            "timer_service_enabled_or_invoked",
            "supervisor_run_for_execution",
            "remote_sync",
            "live_config_changed",
            "operator_state_changed",
            "timer_state_changed",
            "target_plan_replaced",
            "executor_input_changed",
            "orders_submitted",
            "fills_observed",
        ],
        "review_questions_for_owner": [
            "Is it acceptable to prepare a proof-artifacts-only dry-load readback that keeps the hook default-off?",
            "Is the proposed proof set sufficient to prove baseline-only executor input after dry-load readback?",
            "Should any future dry-load be local-only first before remote proof_artifacts readback?",
        ],
    }


def non_authorization_matrix(run_id: str, proposal_ready: bool) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9m_non_authorization_matrix.v1",
        "run_id": run_id,
        "authorizations": {
            "draft_default_off_timer_path_dry_load_proposal": proposal_ready,
            "write_proposal_artifact_under_proof_artifacts": proposal_ready,
            "future_owner_review_discussion": proposal_ready,
            "timer_path_dry_load_execution": False,
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


def render_proposal_markdown(proposal: dict[str, Any]) -> str:
    contract = dict(proposal["proposed_future_dry_load_contract"])
    lines = [
        "# P9M Default-Off Timer-Path Dry-Load Proposal",
        "",
        "This is a proposal artifact only. It is not a dry-load execution, hook deployment,",
        "timer-path load, supervisor run, executor-input mutation, or live-order approval.",
        "",
        "## Proposed Future Gate",
        "",
        "```text",
        f"proposed_future_gate = {proposal['proposed_future_gate']}",
        f"future_gate_required = {str(bool(proposal['future_gate_required'])).lower()}",
        "p9m_authorizes_timer_path_dry_load = false",
        "p9m_authorizes_live_orders = false",
        "```",
        "",
        "## Default-Off Contract",
        "",
        "```text",
    ]
    for key, value in contract.items():
        if isinstance(value, bool):
            value_text = str(value).lower()
        else:
            value_text = str(value)
        lines.append(f"{key} = {value_text}")
    lines.extend(
        [
            "```",
            "",
            "## Minimum Future Proofs",
            "",
        ]
    )
    lines.extend(f"- `{item}`" for item in proposal["minimum_future_dry_load_proofs"])
    lines.extend(
        [
            "",
            "## Explicit Non-Authorizations",
            "",
        ]
    )
    lines.extend(f"- `{item}`" for item in proposal["explicit_non_authorizations"])
    lines.append("")
    return "\n".join(lines)


def build_phase9m(
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
    proof_root = output_root / "proof_artifacts" / "p9m" / run_id
    proof_root.mkdir(parents=True, exist_ok=True)

    paths = {
        "project_profile": resolve_path(args.project_profile),
        "phase9l": (
            resolve_path(args.phase9l_summary)
            if str(getattr(args, "phase9l_summary", "") or "").strip()
            else latest_match(PHASE9L_PARENT, "*/summary.json")
        ),
        "hook_module": resolve_path(args.hook_module),
        "supervisor": resolve_path(args.supervisor),
    }
    project_profile = load_optional(paths["project_profile"])
    p9l = load_optional(paths["phase9l"])
    current_hook_sha = file_sha256(paths["hook_module"]) if paths["hook_module"].exists() else ""
    supervisor_sha_before = file_sha256(paths["supervisor"]) if paths["supervisor"].exists() else ""
    supervisor_text = paths["supervisor"].read_text(encoding="utf-8") if paths["supervisor"].exists() else ""
    live_supervisor_loads_hook_now = "dth60_observe_only_shadow_hook" in supervisor_text
    owner_decision_record = build_owner_decision_record(args, started_at)

    source_evidence = {
        "project_profile": evidence_file(paths["project_profile"]),
        "phase9l_summary": evidence_file(paths["phase9l"]),
        "hook_module": evidence_file(paths["hook_module"]),
        "live_supervisor": evidence_file(paths["supervisor"]),
    }
    p9l_ok = p9l_ready(
        p9l,
        current_hook_sha256=current_hook_sha,
        current_supervisor_sha256=supervisor_sha_before,
    )

    proposal_json_path = proof_root / "default_off_timer_path_dry_load_proposal.json"
    proposal_md_path = proof_root / "default_off_timer_path_dry_load_proposal.md"
    checklist_path = proof_root / "proposal_acceptance_checklist.json"
    matrix_path = proof_root / "non_authorization_matrix.json"
    boundary_path = proof_root / "control_boundary_readback.json"

    gates = {
        "owner_decision_p9m_proposal_only": str(args.owner_decision) == APPROVE_P9M_DECISION,
        "project_stage_boundary_preserved": project_profile.get("current_stage") == "stage_1_research_readiness_only",
        "p9l_proposal_preparation_gate_ready": p9l_ok,
        "current_live_supervisor_not_loading_hook": not live_supervisor_loads_hook_now,
        "current_hook_hash_matches_p9l_source": (
            dict(dict(p9l.get("source_evidence") or {}).get("hook_module") or {}).get("sha256")
            == current_hook_sha
        ),
        "current_supervisor_hash_matches_p9l_source": (
            dict(dict(p9l.get("source_evidence") or {}).get("live_supervisor") or {}).get("sha256")
            == supervisor_sha_before
        ),
        "proposal_output_under_proof_artifacts": output_under_proof_artifacts(proof_root),
        "proposal_body_output_under_proof_artifacts": output_under_proof_artifacts(proposal_json_path),
        "proposal_default_off_required": True,
        "proposal_artifact_sink_proof_artifacts_only": True,
        "proposal_executor_input_source_baseline_only": True,
        "proposal_candidate_order_authority_disabled": True,
        "proposal_requires_separate_future_dry_load_gate": True,
        "no_timer_path_dry_load_execution_in_p9m": True,
        "no_timer_hook_implementation_in_p9m": True,
        "no_hook_deployment_in_p9m": True,
        "no_timer_path_load_in_p9m": True,
        "no_supervisor_run_in_p9m": True,
        "no_remote_execution_in_p9m": True,
        "no_executor_input_mutation_in_p9m": True,
        "no_target_plan_replacement_in_p9m": True,
        "no_live_mutation_in_p9m": True,
        "zero_orders_fills_in_p9m": True,
    }
    blockers = [key for key, value in gates.items() if not value]
    status = "ready" if not blockers else "blocked"
    proposal_ready = status == "ready"

    control_boundary_readback = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9m_control_boundary_readback.v1",
        "run_id": run_id,
        "scope": "local_source_and_retained_p9l_gate_only",
        "live_supervisor": source_evidence["live_supervisor"],
        "live_supervisor_sha256_before": supervisor_sha_before,
        "live_supervisor_sha256_after": file_sha256(paths["supervisor"]) if paths["supervisor"].exists() else "",
        "live_supervisor_loads_candidate_hook": live_supervisor_loads_hook_now,
        "wrote_proposal_artifact": proposal_ready,
        "proposal_artifact_sink": "proof_artifacts_only" if proposal_ready else "",
        "timer_path_dry_load_executed": False,
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

    write_json(output_root / "owner_decision_record.json", owner_decision_record)
    if proposal_ready:
        proposal = default_off_timer_path_dry_load_proposal(
            run_id=run_id,
            owner_decision=owner_decision_record,
            source_evidence=source_evidence,
        )
        checklist = proposal_acceptance_checklist(run_id)
        write_json(proposal_json_path, proposal)
        proposal_md_path.write_text(render_proposal_markdown(proposal), encoding="utf-8")
        write_json(checklist_path, checklist)
    write_json(matrix_path, non_authorization_matrix(run_id, proposal_ready))
    write_json(boundary_path, control_boundary_readback)

    output_files: dict[str, str] = {
        "summary": str(output_root / "summary.json"),
        "owner_decision_record": str(output_root / "owner_decision_record.json"),
        "non_authorization_matrix": str(matrix_path),
        "control_boundary_readback": str(boundary_path),
        "report": str(output_root / "p9m_default_off_timer_path_dry_load_proposal.md"),
    }
    if proposal_ready:
        output_files.update(
            {
                "default_off_timer_path_dry_load_proposal": str(proposal_json_path),
                "default_off_timer_path_dry_load_proposal_markdown": str(proposal_md_path),
                "proposal_acceptance_checklist": str(checklist_path),
            }
        )

    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "proposal_scope": "owner_gated_default_off_timer_path_dry_load_proposal_only",
        "owner_decision": owner_decision_record,
        "source_evidence": source_evidence,
        "default_off_timer_path_dry_load_proposal_ready": proposal_ready,
        "eligible_for_future_default_off_timer_path_dry_load_review": proposal_ready,
        "prepared_default_off_timer_path_dry_load_proposal": proposal_ready,
        "wrote_default_off_timer_path_dry_load_proposal_body": proposal_ready,
        "proposal_body_sink": "proof_artifacts_only" if proposal_ready else "",
        "p9m_authorizes_timer_path_dry_load": False,
        "future_dry_load_gate_required": True,
        "proposed_future_gate": "P9N_default_off_timer_path_dry_load_readback_only_if_separately_requested",
        "proposed_dry_load_default_off": True,
        "proposed_dry_load_mode": "proposal_only_not_loaded",
        "proposed_timer_load_mode": "proposal_only_not_loaded",
        "proposed_executor_input_source": "baseline_only",
        "proposed_candidate_artifact_sink": "proof_artifacts_only",
        "proposed_candidate_order_authority": "disabled",
        "proposed_candidate_live_order_submission_authorized": False,
        "eligible_for_timer_path_dry_load_execution": False,
        "eligible_for_timer_hook_implementation": False,
        "eligible_for_hook_deployment": False,
        "eligible_for_timer_path_load": False,
        "eligible_for_live_order_submission": False,
        "eligible_for_stage_governance_change": False,
        "timer_path_dry_load_authorized": False,
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
        "recommended_next_gate": "P9N_default_off_timer_path_dry_load_readback_only_if_separately_requested",
        "proof_root": str(proof_root),
        "gates": gates,
        "blockers": blockers,
        "output_files": output_files,
    }
    write_json(output_root / "summary.json", summary)
    (output_root / "p9m_default_off_timer_path_dry_load_proposal.md").write_text(
        render_markdown(summary),
        encoding="utf-8",
    )
    return summary, 0 if status == "ready" else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9M Default-Off Timer-Path Dry-Load Proposal",
        "",
        f"`Status: {summary['status']}`",
        "",
        "## Boundary",
        "",
        "P9M drafts a default-off timer-path dry-load proposal under proof_artifacts only.",
        "",
        "```text",
        "proposal_scope = owner_gated_default_off_timer_path_dry_load_proposal_only",
        "default_off_timer_path_dry_load_proposal_ready = "
        f"{str(bool(summary['default_off_timer_path_dry_load_proposal_ready'])).lower()}",
        "wrote_default_off_timer_path_dry_load_proposal_body = "
        f"{str(bool(summary['wrote_default_off_timer_path_dry_load_proposal_body'])).lower()}",
        "p9m_authorizes_timer_path_dry_load = false",
        "timer_path_dry_load_authorized = false",
        "timer_hook_implementation_authorized = false",
        "hook_deployment_authorized = false",
        "timer_path_load_authorized = false",
        "live_order_submission_authorized = false",
        "execution_target_source = baseline_only",
        "candidate_artifact_sink = proof_artifacts_only",
        "proposed_dry_load_mode = proposal_only_not_loaded",
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
    summary, exit_code = build_phase9m(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
