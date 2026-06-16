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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9aj_define_next_gate_after_shadow_review import (  # noqa: E402
    CONTRACT_VERSION as P9AJ_CONTRACT,
    P9AK_GATE,
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


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9ak_default_off_timer_path_readback_proposal.v1"
APPROVE_P9AK_DECISION = (
    "approve_p9ak_prepare_default_off_observe_only_hook_live_supervisor_timer_path_"
    "dry_load_readback_proposal_only"
)
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9ak_default_off_timer_path_readback_proposal"
PHASE9AJ_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9aj_define_next_gate_after_shadow_review"
P9AL_GATE = (
    "P9AL_default_off_observe_only_hook_live_supervisor_timer_path_"
    "dry_load_readback_owner_gate_only_if_separately_requested"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build P9AK as the owner-gated proposal-preparation step after P9AJ. "
            "P9AK writes a default-off observe-only live-supervisor/timer-path "
            "dry-load/readback proposal under proof_artifacts only. It does not "
            "execute dry-load/readback, remote sync, load a timer path, invoke "
            "the supervisor, mutate live state, replace target plans, mutate "
            "executor input, or authorize orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9aj-summary", default="")
    parser.add_argument("--hook-module", default=HOOK_MODULE)
    parser.add_argument("--supervisor", default=SUPERVISOR_PATH)
    parser.add_argument("--live-config-dir", default=LIVE_CONFIG_DIR)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9AK_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:open_next_owner_gate_after_p9aj",
    )
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def proof_artifacts_path(path_text: str) -> bool:
    return "proof_artifacts" in str(path_text).replace("\\", "/").lower().split("/")


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def p9aj_ready_for_p9ak(
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
    next_scope = dict(summary.get("next_gate_scope") or {})
    required_gates = (
        "owner_decision_p9aj_define_scope_only",
        "project_stage_boundary_preserved",
        "p9ai_summary_ready",
        "p9ai_shadow_review_packet_ready",
        "next_gate_scope_definition_under_proof_artifacts",
        "p9aj_defines_scope_only",
        "p9aj_does_not_prepare_p9ak_proposal",
        "p9aj_does_not_write_proposal_body",
        "p9ak_must_be_separately_requested",
        "p9ak_must_remain_proposal_only",
        "p9ak_must_keep_default_off",
        "p9ak_must_keep_order_submission_disabled",
        "p9ak_must_keep_executor_baseline_only",
        "p9ak_must_keep_candidate_shadow_only",
        "p9ak_must_not_execute_dry_load",
        "p9ak_must_not_load_timer_path",
        "p9ak_must_not_invoke_supervisor",
        "current_live_supervisor_still_not_loading_hook",
        "current_hook_hash_matches_p9ai_source",
        "current_supervisor_hash_matches_p9ai_source",
        "remote_sync_not_authorized_in_p9aj",
        "remote_execution_not_authorized_in_p9aj",
        "timer_path_load_not_authorized_in_p9aj",
        "supervisor_invocation_not_authorized_in_p9aj",
        "candidate_execution_forbidden",
        "live_order_submission_forbidden",
        "target_plan_replacement_forbidden",
        "executor_input_mutation_forbidden",
        "live_config_operator_timer_mutation_forbidden",
        "production_timer_service_load_forbidden",
        "zero_orders_fills_in_p9aj",
    )
    authorizations = dict(next_scope.get("current_gate_authorizations") or {})
    required_scope_boundaries = dict(next_scope.get("p9ak_required_boundaries") or {})
    return (
        summary.get("contract_version") == P9AJ_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9aj_define_next_gate_after_shadow_review_ready") is True
        and summary.get("p9ai_sufficient_for_future_p9ak_proposal_preparation") is True
        and summary.get("allowed_next_gate") == P9AK_GATE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
        and summary.get("p9ak_proposal_preparation_authorized") is False
        and summary.get("prepared_p9ak_proposal") is False
        and summary.get("wrote_p9ak_proposal_body") is False
        and summary.get("dry_load_readback_execution_authorized") is False
        and summary.get("remote_sync_authorized") is False
        and summary.get("remote_execution_authorized") is False
        and summary.get("timer_path_load_authorized") is False
        and summary.get("supervisor_invocation_authorized") is False
        and summary.get("candidate_execution_authorized") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("target_plan_replacement_authorized") is False
        and summary.get("executor_input_mutation_authorized") is False
        and summary.get("live_config_mutation_authorized") is False
        and summary.get("operator_state_mutation_authorized") is False
        and summary.get("timer_or_service_mutation_authorized") is False
        and summary.get("production_timer_service_load_authorized") is False
        and summary.get("repo_stage_change_authorized") is False
        and summary.get("entered_timer_path") is False
        and summary.get("ran_supervisor") is False
        and summary.get("live_supervisor_hook_loaded") is False
        and int_zero(summary, "orders_submitted")
        and int_zero(summary, "fill_count")
        and next_scope.get("allowed_next_gate") == P9AK_GATE
        and next_scope.get("p9ak_may_prepare_proposal_body") is True
        and next_scope.get("p9ak_may_execute_proposal") is False
        and next_scope.get("future_dry_load_readback_execution_gate_required") is True
        and next_scope.get("future_timer_path_load_gate_required") is True
        and required_scope_boundaries.get("proposal_only") is True
        and required_scope_boundaries.get("proof_artifacts_only") is True
        and required_scope_boundaries.get("default_off") is True
        and required_scope_boundaries.get("observe_only") is True
        and required_scope_boundaries.get("order_submission_disabled") is True
        and required_scope_boundaries.get("candidate_execution_disabled") is True
        and required_scope_boundaries.get("executor_consumes_baseline_only") is True
        and required_scope_boundaries.get("candidate_shadow_artifact_only") is True
        and all(value is False for value in authorizations.values())
        and owner.get("decision") == "approve_p9aj_define_next_gate_after_default_off_shadow_review_scope_only"
        and owner.get("p9aj_define_scope_approved") is True
        and owner.get("p9ak_may_be_separately_requested") is True
        and owner.get("p9ak_proposal_preparation_approved") is False
        and hook.get("sha256") == current_hook_sha256
        and supervisor.get("sha256") == current_supervisor_sha256
        and all(gates.get(key) is True for key in required_gates)
    )


def build_owner_decision_record(args: argparse.Namespace, generated_at: datetime) -> dict[str, Any]:
    approved = str(args.owner_decision) == APPROVE_P9AK_DECISION
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ak_owner_decision.v1",
        "recorded_at_utc": iso_z(generated_at),
        "owner": str(args.owner),
        "decision": str(args.owner_decision),
        "decision_source": str(args.owner_decision_source),
        "decision_question": "prepare_default_off_observe_only_timer_path_dry_load_readback_proposal_only",
        "decision_effect": (
            "authorize_p9ak_proposal_body_under_proof_artifacts_only" if approved else "none"
        ),
        "p9ak_proposal_preparation_approved": approved,
        "proposal_body_write_approved": approved,
        "future_owner_review_discussion_approved": approved,
        "dry_load_readback_execution_approved": False,
        "timer_hook_implementation_approved": False,
        "hook_deployment_approved": False,
        "timer_path_load_approved": False,
        "supervisor_invocation_approved": False,
        "remote_sync_approved": False,
        "remote_execution_approved": False,
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


def proposal_body(
    *,
    run_id: str,
    owner_decision: dict[str, Any],
    source_evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ak_timer_path_readback_proposal_body.v1",
        "run_id": run_id,
        "proposal_scope": "prepare_default_off_observe_only_hook_live_supervisor_timer_path_dry_load_readback_proposal_only",
        "proposal_status": "draft_for_future_owner_review",
        "owner_decision": owner_decision,
        "source_evidence": source_evidence,
        "p9ak_authorizes_dry_load_readback_execution": False,
        "p9ak_authorizes_timer_hook_implementation": False,
        "p9ak_authorizes_hook_deployment": False,
        "p9ak_authorizes_timer_path_load": False,
        "p9ak_authorizes_supervisor_invocation": False,
        "p9ak_authorizes_remote_sync": False,
        "p9ak_authorizes_live_orders": False,
        "future_gate_required": True,
        "proposed_future_gate": P9AL_GATE,
        "proposed_future_gate_scope": "decide_whether_to_execute_default_off_observe_only_timer_path_dry_load_readback",
        "proposed_future_readback_contract": {
            "default_off_required": True,
            "hook_config_enabled_default": False,
            "observe_only_mode_required": True,
            "candidate_order_authority": "disabled",
            "candidate_live_order_submission_authorized": False,
            "candidate_execution_authorized": False,
            "execution_target_source": "baseline_only",
            "candidate_overlay_execution_path": "excluded",
            "candidate_artifact_sink": "proof_artifacts_only",
            "executor_input_must_remain_baseline_only": True,
            "candidate_plan_must_not_be_referenced_by_executor": True,
            "target_plan_must_not_be_replaced": True,
            "executor_input_must_not_change": True,
            "dry_load_readback_must_not_submit_orders": True,
            "remote_sync_must_not_occur_without_separate_gate": True,
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
        "minimum_future_gate_inputs": [
            "retained_p9ak_summary",
            "retained_p9ak_proposal_body",
            "retained_p9aj_summary",
            "current_project_stage_readback",
            "current_hook_module_hash_matching_p9ak_source_or_explicit_owner_review",
            "current_live_supervisor_hash_matching_p9ak_source_or_explicit_owner_review",
            "fresh_baseline_target_plan_artifact",
            "fresh_executor_input_readback",
        ],
        "minimum_future_readback_proofs": [
            "default_off_hook_config_readback",
            "observe_only_mode_readback",
            "order_authority_disabled_readback",
            "executor_input_hash_equals_baseline_target_plan_hash",
            "candidate_plan_referenced_by_executor_false",
            "candidate_artifacts_under_proof_artifacts_only",
            "target_plan_replaced_false",
            "executor_input_changed_false",
            "live_config_changed_false",
            "operator_state_changed_false",
            "timer_state_changed_false",
            "orders_submitted_zero",
            "fills_observed_zero",
        ],
        "explicit_non_authorizations": [
            "dry_load_readback_execution",
            "timer_hook_implementation",
            "hook_deployment",
            "timer_path_load",
            "supervisor_invocation",
            "remote_sync",
            "remote_execution",
            "candidate_execution",
            "target_plan_replacement",
            "executor_input_mutation",
            "live_config_mutation",
            "operator_state_mutation",
            "timer_or_service_mutation",
            "production_timer_service_load",
            "live_order_submission",
            "stage_governance_change",
        ],
    }


def proposal_acceptance_checklist(run_id: str) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ak_proposal_acceptance_checklist.v1",
        "run_id": run_id,
        "status": "draft_for_future_owner_review",
        "p9ak_authorizes_checklist_execution": False,
        "future_gate_required_before_any_dry_load_readback": True,
        "must_be_true_before_future_p9al": [
            "separate_owner_decision_exists",
            "proposal_body_hash_matches_p9ak_retained_artifact",
            "project_stage_boundary_still_stage_1",
            "hook_config_default_off",
            "observe_only_mode",
            "candidate_order_authority_disabled",
            "executor_input_source_baseline_only",
            "candidate_output_root_under_proof_artifacts",
            "fresh_baseline_target_plan_available",
            "fresh_executor_input_readback_available",
        ],
        "must_remain_false_in_future_p9al_unless_separately_authorized": [
            "remote_sync",
            "remote_execution",
            "candidate_execution",
            "live_config_changed",
            "operator_state_changed",
            "timer_state_changed",
            "target_plan_replaced",
            "executor_input_changed",
            "orders_submitted",
            "fills_observed",
        ],
        "review_questions_for_owner": [
            "Is the proof set sufficient before any default-off timer-path readback is executed?",
            "Should the future readback stay local-only before any remote proof_artifacts readback?",
            "Is baseline-only executor input still the hard invariant for the next readback gate?",
        ],
    }


def non_authorization_matrix(run_id: str, proposal_ready: bool) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ak_non_authorization_matrix.v1",
        "run_id": run_id,
        "authorizations": {
            "p9ak_proposal_preparation": proposal_ready,
            "write_proposal_artifact_under_proof_artifacts": proposal_ready,
            "future_owner_review_discussion": proposal_ready,
            "dry_load_readback_execution": False,
            "timer_hook_implementation": False,
            "hook_deployment": False,
            "timer_path_load": False,
            "supervisor_invocation": False,
            "remote_sync": False,
            "remote_execution": False,
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


def render_proposal_markdown(proposal: dict[str, Any]) -> str:
    contract = dict(proposal["proposed_future_readback_contract"])
    lines = [
        "# P9AK Default-Off Observe-Only Timer-Path Readback Proposal",
        "",
        "This is a proposal artifact only. It is not dry-load/readback execution,",
        "timer-path load, supervisor invocation, remote sync, executor-input mutation,",
        "target-plan replacement, or live-order approval.",
        "",
        "## Proposed Future Gate",
        "",
        "```text",
        f"proposed_future_gate = {proposal['proposed_future_gate']}",
        f"future_gate_required = {str(bool(proposal['future_gate_required'])).lower()}",
        "p9ak_authorizes_dry_load_readback_execution = false",
        "p9ak_authorizes_live_orders = false",
        "```",
        "",
        "## Default-Off Readback Contract",
        "",
        "```text",
    ]
    for key, value in contract.items():
        value_text = str(value).lower() if isinstance(value, bool) else str(value)
        lines.append(f"{key} = {value_text}")
    lines.extend(["```", "", "## Minimum Future Proofs", ""])
    lines.extend(f"- `{item}`" for item in proposal["minimum_future_readback_proofs"])
    lines.extend(["", "## Explicit Non-Authorizations", ""])
    lines.extend(f"- `{item}`" for item in proposal["explicit_non_authorizations"])
    lines.append("")
    return "\n".join(lines)


def build_phase9ak(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    generated_at = now_fn()
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=UTC)
    run_id = generated_at.strftime("%Y%m%dT%H%M%SZ")
    root = resolve_path(args.output_root) if str(args.output_root).strip() else resolve_path(DEFAULT_OUTPUT_PARENT) / run_id
    proof_root = root / "proof_artifacts" / "p9ak" / run_id
    proof_root.mkdir(parents=True, exist_ok=True)

    project_profile_path = resolve_path(args.project_profile)
    p9aj_path = (
        resolve_path(args.phase9aj_summary)
        if str(args.phase9aj_summary).strip()
        else latest_match(PHASE9AJ_PARENT, "*/summary.json")
    )
    hook_path = resolve_path(args.hook_module)
    supervisor_path = resolve_path(args.supervisor)
    live_config_dir = resolve_path(args.live_config_dir)

    project_profile = load_optional(project_profile_path)
    p9aj = load_optional(p9aj_path)
    current_hook_sha = file_sha256(hook_path) if hook_path.exists() and hook_path.is_file() else ""
    supervisor_sha_before = file_sha256(supervisor_path) if supervisor_path.exists() and supervisor_path.is_file() else ""
    supervisor_loads_hook = current_supervisor_loads_hook(supervisor_path)
    owner_decision = build_owner_decision_record(args, generated_at)

    source_evidence = {
        "project_profile": evidence_file(project_profile_path),
        "phase9aj_summary": evidence_file(p9aj_path),
        "hook_module": evidence_file(hook_path),
        "live_supervisor": evidence_file(supervisor_path),
        "live_config_dir": {
            "path": str(live_config_dir),
            "exists": live_config_dir.exists(),
            "sha256": tree_sha256(live_config_dir),
        },
    }

    proposal_json_path = proof_root / "default_off_observe_only_timer_path_readback_proposal.json"
    proposal_md_path = proof_root / "default_off_observe_only_timer_path_readback_proposal.md"
    checklist_path = proof_root / "proposal_acceptance_checklist.json"
    matrix_path = proof_root / "non_authorization_matrix.json"
    boundary_path = proof_root / "control_boundary_readback.json"

    p9aj_ok = p9aj_ready_for_p9ak(
        p9aj,
        current_hook_sha256=current_hook_sha,
        current_supervisor_sha256=supervisor_sha_before,
    )
    gates = {
        "owner_decision_p9ak_proposal_only": str(args.owner_decision) == APPROVE_P9AK_DECISION,
        "project_stage_boundary_preserved": project_profile.get("current_stage") == "stage_1_research_readiness_only",
        "p9aj_scope_gate_ready": p9aj_ok,
        "current_live_supervisor_not_loading_hook": supervisor_loads_hook is False,
        "current_hook_hash_matches_p9aj_source": (
            dict(dict(p9aj.get("source_evidence") or {}).get("hook_module") or {}).get("sha256")
            == current_hook_sha
        ),
        "current_supervisor_hash_matches_p9aj_source": (
            dict(dict(p9aj.get("source_evidence") or {}).get("live_supervisor") or {}).get("sha256")
            == supervisor_sha_before
        ),
        "proposal_output_under_proof_artifacts": proof_artifacts_path(str(proof_root)),
        "proposal_body_output_under_proof_artifacts": proof_artifacts_path(str(proposal_json_path)),
        "proposal_default_off_required": True,
        "proposal_observe_only_required": True,
        "proposal_artifact_sink_proof_artifacts_only": True,
        "proposal_executor_input_source_baseline_only": True,
        "proposal_candidate_shadow_only": True,
        "proposal_candidate_order_authority_disabled": True,
        "proposal_requires_separate_future_readback_gate": True,
        "no_dry_load_readback_execution_in_p9ak": True,
        "no_timer_hook_implementation_in_p9ak": True,
        "no_hook_deployment_in_p9ak": True,
        "no_timer_path_load_in_p9ak": True,
        "no_supervisor_invocation_in_p9ak": True,
        "no_remote_sync_in_p9ak": True,
        "no_remote_execution_in_p9ak": True,
        "no_candidate_execution_in_p9ak": True,
        "no_executor_input_mutation_in_p9ak": True,
        "no_target_plan_replacement_in_p9ak": True,
        "no_live_mutation_in_p9ak": True,
        "zero_orders_fills_in_p9ak": True,
    }
    blockers = [key for key, value in gates.items() if not value]
    status = "ready" if not blockers else "blocked"
    proposal_ready = status == "ready"

    control_boundary_readback = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ak_control_boundary_readback.v1",
        "run_id": run_id,
        "scope": "local_source_and_retained_p9aj_gate_only",
        "live_supervisor": source_evidence["live_supervisor"],
        "live_supervisor_sha256_before": supervisor_sha_before,
        "live_supervisor_sha256_after": file_sha256(supervisor_path) if supervisor_path.exists() else "",
        "live_supervisor_loads_candidate_hook": supervisor_loads_hook,
        "wrote_proposal_artifact": proposal_ready,
        "proposal_artifact_sink": "proof_artifacts_only" if proposal_ready else "",
        "dry_load_readback_executed": False,
        "live_timer_path_loaded": False,
        "live_timer_service_enabled_or_invoked": False,
        "ran_supervisor": False,
        "supervisor_invoked": False,
        "remote_sync_performed": False,
        "remote_execution_performed": False,
        "remote_control_plane_touched": False,
        "candidate_execution_performed": False,
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

    write_json(root / "owner_decision_record.json", owner_decision)
    if proposal_ready:
        proposal = proposal_body(run_id=run_id, owner_decision=owner_decision, source_evidence=source_evidence)
        checklist = proposal_acceptance_checklist(run_id)
        write_json(proposal_json_path, proposal)
        proposal_md_path.write_text(render_proposal_markdown(proposal), encoding="utf-8")
        write_json(checklist_path, checklist)
    write_json(matrix_path, non_authorization_matrix(run_id, proposal_ready))
    write_json(boundary_path, control_boundary_readback)

    output_files: dict[str, str] = {
        "summary": str(root / "summary.json"),
        "owner_decision_record": str(root / "owner_decision_record.json"),
        "non_authorization_matrix": str(matrix_path),
        "control_boundary_readback": str(boundary_path),
        "report": str(root / "p9ak_default_off_timer_path_readback_proposal.md"),
    }
    if proposal_ready:
        output_files.update(
            {
                "default_off_observe_only_timer_path_readback_proposal": str(proposal_json_path),
                "default_off_observe_only_timer_path_readback_proposal_markdown": str(proposal_md_path),
                "proposal_acceptance_checklist": str(checklist_path),
            }
        )

    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(generated_at),
        "status": status,
        "blockers": blockers,
        "proposal_scope": "owner_gated_default_off_observe_only_timer_path_readback_proposal_only",
        "owner_decision": owner_decision,
        "source_evidence": source_evidence,
        "p9ak_default_off_observe_only_timer_path_readback_proposal_ready": proposal_ready,
        "eligible_for_future_default_off_observe_only_readback_owner_gate": proposal_ready,
        "prepared_p9ak_proposal": proposal_ready,
        "wrote_p9ak_proposal_body": proposal_ready,
        "proposal_body_sink": "proof_artifacts_only" if proposal_ready else "",
        "p9ak_authorizes_dry_load_readback_execution": False,
        "future_readback_execution_gate_required": True,
        "proposed_future_gate": P9AL_GATE,
        "proposed_readback_default_off": True,
        "proposed_readback_observe_only": True,
        "proposed_readback_mode": "proposal_only_not_executed",
        "proposed_timer_load_mode": "proposal_only_not_loaded",
        "proposed_executor_input_source": "baseline_only",
        "proposed_candidate_artifact_sink": "proof_artifacts_only",
        "proposed_candidate_order_authority": "disabled",
        "proposed_candidate_live_order_submission_authorized": False,
        "eligible_for_dry_load_readback_execution": False,
        "eligible_for_timer_hook_implementation": False,
        "eligible_for_hook_deployment": False,
        "eligible_for_timer_path_load": False,
        "eligible_for_supervisor_invocation": False,
        "eligible_for_remote_sync": False,
        "eligible_for_live_order_submission": False,
        "eligible_for_stage_governance_change": False,
        "dry_load_readback_execution_authorized": False,
        "timer_hook_implementation_authorized": False,
        "hook_deployment_authorized": False,
        "timer_path_load_authorized": False,
        "supervisor_invocation_authorized": False,
        "remote_sync_authorized": False,
        "remote_execution_authorized": False,
        "candidate_execution_authorized": False,
        "live_order_submission_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "live_config_mutation_authorized": False,
        "operator_state_mutation_authorized": False,
        "timer_or_service_mutation_authorized": False,
        "production_timer_service_load_authorized": False,
        "repo_stage_change_authorized": False,
        "candidate_order_authority": "disabled",
        "candidate_live_order_submission_authorized": False,
        "execution_target_source": "baseline_only",
        "candidate_overlay_execution_path": "excluded",
        "candidate_artifact_sink": "proof_artifacts_only",
        "live_supervisor_loads_candidate_hook": supervisor_loads_hook,
        "live_supervisor_source_unchanged": control_boundary_readback["live_supervisor_source_unchanged"],
        "live_timer_path_loaded": False,
        "live_timer_service_enabled_or_invoked": False,
        "entered_timer_path": False,
        "ran_supervisor": False,
        "supervisor_invoked": False,
        "timer_path_invoked": False,
        "remote_sync_performed": False,
        "remote_execution_performed": False,
        "remote_control_plane_touched": False,
        "candidate_execution_performed": False,
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
        "recommended_next_gate": P9AL_GATE,
        "proof_root": str(proof_root),
        "gates": gates,
        "output_files": output_files,
    }
    write_json(root / "summary.json", summary)
    (root / "p9ak_default_off_timer_path_readback_proposal.md").write_text(
        render_markdown(summary),
        encoding="utf-8",
    )
    return summary, 0 if status == "ready" else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9AK Default-Off Timer-Path Readback Proposal",
        "",
        f"`Status: {summary['status']}`",
        "",
        "## Boundary",
        "",
        "P9AK prepares a default-off observe-only timer-path dry-load/readback proposal under proof_artifacts only.",
        "",
        "```text",
        "proposal_scope = owner_gated_default_off_observe_only_timer_path_readback_proposal_only",
        "p9ak_default_off_observe_only_timer_path_readback_proposal_ready = "
        f"{str(bool(summary['p9ak_default_off_observe_only_timer_path_readback_proposal_ready'])).lower()}",
        "wrote_p9ak_proposal_body = "
        f"{str(bool(summary['wrote_p9ak_proposal_body'])).lower()}",
        "p9ak_authorizes_dry_load_readback_execution = false",
        "dry_load_readback_execution_authorized = false",
        "timer_path_load_authorized = false",
        "supervisor_invocation_authorized = false",
        "remote_sync_authorized = false",
        "live_order_submission_authorized = false",
        "execution_target_source = baseline_only",
        "candidate_artifact_sink = proof_artifacts_only",
        "proposed_readback_mode = proposal_only_not_executed",
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
    summary, exit_code = build_phase9ak(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
