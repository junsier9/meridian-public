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


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate.v1"
APPROVE_P9Q_DECISION = "approve_p9q_allow_define_next_gate_scope_only"
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9q_define_next_gate_scope_gate"
PHASE9P_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9p_owner_review_after_default_off_readback"
PROJECT_PROFILE = "config/project_governance/project_profile.json"
HOOK_MODULE = "src/enhengclaw/live_trading/dth60_observe_only_shadow_hook.py"
SUPERVISOR_PATH = "src/enhengclaw/live_trading/mainnet_live_supervisor.py"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build the P9Q owner gate that only decides whether a future concrete "
            "next-gate scope may be defined. P9Q does not define that scope, "
            "execute the next gate, deploy/load hooks, mutate executor input, "
            "remote sync, or authorize orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9p-summary", default="")
    parser.add_argument("--hook-module", default=HOOK_MODULE)
    parser.add_argument("--supervisor", default=SUPERVISOR_PATH)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9Q_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:allow_define_next_gate_scope_only",
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


def int_zero(payload: dict[str, Any], key: str) -> bool:
    return int(payload.get(key) or 0) == 0


def zero_orders_fills(payload: dict[str, Any]) -> bool:
    exchange_submission = payload.get("exchange_order_submission")
    return (
        int_zero(payload, "orders_submitted")
        and int_zero(payload, "fill_count")
        and int_zero(payload, "fills_observed")
        and exchange_submission in (None, "disabled")
    )


def no_live_mutation(payload: dict[str, Any]) -> bool:
    return (
        payload.get("applied_to_live") is False
        and payload.get("live_config_changed") is False
        and payload.get("operator_state_changed") is False
        and payload.get("timer_state_changed") is False
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


def source_output_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("output_files") or {}).get(key) or "")
    return resolve_path(text) if text.strip() else Path("")


def p9p_ready(
    summary: dict[str, Any],
    matrix: dict[str, Any],
    *,
    current_hook_sha256: str,
    current_supervisor_sha256: str,
    current_supervisor_loads_candidate_hook: bool,
) -> bool:
    source = dict(summary.get("source_evidence") or {})
    hook = dict(source.get("hook_module") or {})
    supervisor = dict(source.get("live_supervisor") or {})
    owner = dict(summary.get("owner_decision") or {})
    authorizations = dict(matrix.get("authorizations") or {})
    gates = dict(summary.get("gates") or {})
    required_gates = (
        "owner_decision_p9p_review_only",
        "stage_boundary_preserved",
        "p9o_summary_ready",
        "p9o_default_off_readback_executed",
        "p9o_readback_default_off",
        "p9o_readback_not_live_timer_service",
        "proof_files_exist",
        "proof_files_under_proof_artifacts",
        "dry_load_manifest_ready",
        "default_off_config_readback_ready",
        "disabled_hook_readback_summary_ready",
        "executor_input_readback_ready",
        "control_boundary_readback_ready",
        "baseline_executor_input_hash_unchanged",
        "executor_consumes_baseline_only",
        "candidate_plan_not_referenced_by_executor",
        "target_plan_not_replaced",
        "live_supervisor_not_loading_hook",
        "live_timer_path_not_loaded",
        "supervisor_not_run",
        "remote_not_touched",
        "zero_orders_fills",
        "no_live_mutation",
        "review_output_under_proof_artifacts",
        "no_timer_hook_implementation_in_p9p",
        "no_hook_deployment_in_p9p",
        "no_timer_path_load_in_p9p",
        "no_supervisor_run_in_p9p",
        "no_remote_execution_in_p9p",
        "no_executor_input_mutation_in_p9p",
        "no_target_plan_replacement_in_p9p",
        "no_live_mutation_in_p9p",
        "zero_orders_fills_in_p9p",
    )
    return (
        summary.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9p_owner_review_after_default_off_readback.v1"
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("review_scope") == "owner_gated_p9o_default_off_readback_sufficiency_review_only"
        and summary.get("p9o_default_off_readback_sufficient_for_next_owner_gate") is True
        and summary.get("eligible_for_next_owner_gate_discussion") is True
        and summary.get("next_owner_gate_execution_authorized") is False
        and summary.get("eligible_for_live_timer_path_load") is False
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
        and summary.get("default_off_readback_executed") is True
        and summary.get("default_off_readback_proof_files_ready") is True
        and summary.get("default_off_readback_not_live_timer_service") is True
        and summary.get("baseline_executor_input_hash_unchanged") is True
        and summary.get("executor_consumes_baseline_only") is True
        and summary.get("candidate_plan_referenced_by_executor") is False
        and summary.get("target_plan_replaced") is False
        and summary.get("live_supervisor_loads_candidate_hook") is False
        and summary.get("live_supervisor_source_unchanged") is True
        and summary.get("live_timer_path_loaded") is False
        and summary.get("live_timer_service_enabled_or_invoked") is False
        and summary.get("ran_supervisor") is False
        and summary.get("timer_path_invoked") is False
        and summary.get("remote_execution_performed") is False
        and summary.get("remote_control_plane_touched") is False
        and summary.get("wrote_live_hook_config") is False
        and summary.get("implemented_hook") is False
        and summary.get("deployed_hook") is False
        and summary.get("loaded_hook") is False
        and summary.get("executor_input_changed") is False
        and no_live_mutation(summary)
        and zero_orders_fills(summary)
        and owner.get("decision") == "approve_p9p_review_default_off_readback_sufficiency_only"
        and owner.get("review_default_off_readback_sufficiency_approved") is True
        and owner.get("next_owner_gate_execution_approved") is False
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
        and authorizations.get("p9p_review_default_off_readback_sufficiency") is True
        and authorizations.get("enter_separate_next_owner_gate_discussion") is True
        and authorizations.get("execute_next_owner_gate") is False
        and authorizations.get("timer_hook_implementation") is False
        and authorizations.get("hook_deployment") is False
        and authorizations.get("timer_path_load") is False
        and authorizations.get("live_order_submission") is False
        and authorizations.get("target_plan_replacement") is False
        and authorizations.get("executor_input_mutation") is False
        and authorizations.get("live_config_mutation") is False
        and authorizations.get("operator_state_mutation") is False
        and authorizations.get("timer_or_service_mutation") is False
        and authorizations.get("remote_sync") is False
        and authorizations.get("supervisor_run") is False
        and authorizations.get("stage_governance_change") is False
        and hook.get("sha256") == current_hook_sha256
        and supervisor.get("sha256") == current_supervisor_sha256
        and current_supervisor_loads_candidate_hook is False
        and all(gates.get(key) is True for key in required_gates)
    )


def build_owner_decision_record(args: argparse.Namespace, started_at: datetime) -> dict[str, Any]:
    approved = str(args.owner_decision) == APPROVE_P9Q_DECISION
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9q_owner_decision.v1",
        "owner": str(args.owner),
        "decision": str(args.owner_decision),
        "decision_source": str(args.owner_decision_source),
        "recorded_at_utc": iso_z(started_at),
        "decision_question": "allow_future_definition_of_next_gate_concrete_scope_only",
        "decision_effect": "authorize_future_next_gate_scope_definition_only" if approved else "none",
        "future_next_gate_scope_definition_approved": approved,
        "define_next_gate_scope_in_p9q_approved": False,
        "execute_next_gate_approved": False,
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


def build_phase9q(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    started_at = now_fn()
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")
    output_root = resolve_path(args.output_root) if args.output_root else resolve_path(DEFAULT_OUTPUT_PARENT) / run_id
    proof_root = output_root / "proof_artifacts" / "p9q" / run_id
    paths = {
        "project_profile": resolve_path(args.project_profile),
        "phase9p": resolve_path(args.phase9p_summary)
        if args.phase9p_summary
        else latest_match(PHASE9P_PARENT, "*/summary.json"),
        "hook_module": resolve_path(args.hook_module),
        "supervisor": resolve_path(args.supervisor),
    }
    project_profile = load_optional(paths["project_profile"])
    p9p = load_optional(paths["phase9p"])
    matrix_path = source_output_path(p9p, "review_decision_matrix")
    p9p_matrix = load_optional(matrix_path)
    hook_sha = file_sha256(paths["hook_module"]) if paths["hook_module"].exists() else ""
    supervisor_sha_before = file_sha256(paths["supervisor"]) if paths["supervisor"].exists() else ""
    supervisor_loads_hook = current_supervisor_loads_hook(paths["supervisor"])
    owner_decision_record = build_owner_decision_record(args, started_at)
    p9p_ok = p9p_ready(
        p9p,
        p9p_matrix,
        current_hook_sha256=hook_sha,
        current_supervisor_sha256=supervisor_sha_before,
        current_supervisor_loads_candidate_hook=supervisor_loads_hook,
    )
    source_evidence = {
        "project_profile": evidence_file(paths["project_profile"]),
        "phase9p_summary": evidence_file(paths["phase9p"]),
        "phase9p_review_decision_matrix": evidence_file(matrix_path),
        "hook_module": evidence_file(paths["hook_module"]),
        "live_supervisor": evidence_file(paths["supervisor"]),
    }
    next_gate_scope_definition_gate = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9q_next_gate_scope_definition_gate.v1",
        "run_id": run_id,
        "gate_scope": "owner_gated_allow_future_next_gate_scope_definition_only",
        "source_evidence": source_evidence,
        "owner_decision": owner_decision_record,
        "allowed_next_action": "define_next_gate_concrete_scope",
        "allowed_next_gate": "P9S_define_next_gate_scope_only_if_separately_requested",
        "defined_in_p9q": False,
        "executed_in_p9q": False,
        "allowed_next_action_constraints": {
            "scope_definition_only": True,
            "proof_artifacts_only": True,
            "must_consume_p9p_proof": True,
            "must_not_execute_next_gate": True,
            "must_not_implement_hook": True,
            "must_not_deploy_hook": True,
            "must_not_load_live_timer_path": True,
            "must_not_replace_target_plan": True,
            "must_not_mutate_executor_input": True,
            "must_not_modify_live_config": True,
            "must_not_modify_operator_state": True,
            "must_not_modify_timer_or_service_state": True,
            "must_not_remote_sync": True,
            "must_not_run_supervisor": True,
            "candidate_order_authority": "disabled",
            "candidate_live_order_submission_authorized": False,
            "orders_submitted_must_equal": 0,
            "fill_count_must_equal": 0,
        },
    }
    non_authorization_matrix = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9q_non_authorization_matrix.v1",
        "run_id": run_id,
        "authorizations": {
            "future_next_gate_scope_definition": str(args.owner_decision) == APPROVE_P9Q_DECISION,
            "define_next_gate_scope_in_p9q": False,
            "execute_next_gate": False,
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
    control_boundary_readback = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9q_control_boundary_readback.v1",
        "run_id": run_id,
        "scope": "future_next_gate_scope_definition_permission_only",
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
    gates = {
        "owner_decision_p9q_define_scope_only": str(args.owner_decision) == APPROVE_P9Q_DECISION,
        "project_stage_boundary_preserved": project_profile.get("current_stage")
        == "stage_1_research_readiness_only",
        "p9p_owner_review_ready": p9p_ok,
        "p9p_sufficient_for_next_owner_gate_discussion": p9p.get(
            "p9o_default_off_readback_sufficient_for_next_owner_gate"
        )
        is True
        and p9p.get("eligible_for_next_owner_gate_discussion") is True,
        "p9p_next_gate_execution_not_authorized": p9p.get("next_owner_gate_execution_authorized") is False,
        "current_live_supervisor_not_loading_hook": supervisor_loads_hook is False,
        "current_hook_hash_matches_p9p_source": dict(dict(p9p.get("source_evidence") or {}).get("hook_module") or {}).get(
            "sha256"
        )
        == hook_sha,
        "current_supervisor_hash_matches_p9p_source": dict(
            dict(p9p.get("source_evidence") or {}).get("live_supervisor") or {}
        ).get("sha256")
        == supervisor_sha_before,
        "scope_definition_gate_output_under_proof_artifacts": output_under_proof_artifacts(
            proof_root / "next_gate_scope_definition_gate.json"
        ),
        "future_scope_definition_must_be_proof_artifacts_only": True,
        "future_scope_definition_must_not_execute_next_gate": True,
        "future_scope_definition_must_keep_order_authority_disabled": True,
        "future_scope_definition_must_not_authorize_live_order_submission": True,
        "no_scope_definition_in_p9q": True,
        "no_next_gate_execution_in_p9q": True,
        "no_timer_hook_implementation_in_p9q": True,
        "no_hook_deployment_in_p9q": True,
        "no_live_timer_path_load_in_p9q": True,
        "no_supervisor_run_in_p9q": True,
        "no_remote_execution_in_p9q": True,
        "no_executor_input_mutation_in_p9q": True,
        "no_target_plan_replacement_in_p9q": True,
        "no_live_mutation_in_p9q": True,
        "zero_orders_fills_in_p9q": True,
    }
    blockers = [key for key, value in gates.items() if not value]
    status = "ready" if not blockers else "blocked"
    gate_ready = status == "ready"
    write_json(output_root / "owner_decision_record.json", owner_decision_record)
    write_json(proof_root / "next_gate_scope_definition_gate.json", next_gate_scope_definition_gate)
    write_json(proof_root / "non_authorization_matrix.json", non_authorization_matrix)
    write_json(proof_root / "control_boundary_readback.json", control_boundary_readback)

    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "gate_scope": "owner_gated_allow_future_next_gate_scope_definition_only",
        "owner_decision": owner_decision_record,
        "source_evidence": source_evidence,
        "p9q_define_next_gate_scope_owner_gate_ready": gate_ready,
        "eligible_to_define_next_gate_scope": gate_ready,
        "defined_next_gate_scope": False,
        "next_gate_scope_definition_in_p9q_authorized": False,
        "next_gate_execution_authorized": False,
        "allowed_next_gate": "P9S_define_next_gate_scope_only_if_separately_requested",
        "future_scope_definition_must_be_proof_artifacts_only": True,
        "future_scope_definition_must_not_execute_next_gate": True,
        "future_scope_definition_must_keep_order_authority_disabled": True,
        "future_scope_definition_must_not_authorize_live_order_submission": True,
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
        "target_plan_replaced": False,
        "executor_input_changed": False,
        "recommended_next_gate": "P9S_define_next_gate_scope_only_if_separately_requested",
        "proof_root": str(proof_root),
        "gates": gates,
        "blockers": blockers,
        "output_files": {
            "summary": str(output_root / "summary.json"),
            "owner_decision_record": str(output_root / "owner_decision_record.json"),
            "next_gate_scope_definition_gate": str(proof_root / "next_gate_scope_definition_gate.json"),
            "non_authorization_matrix": str(proof_root / "non_authorization_matrix.json"),
            "control_boundary_readback": str(proof_root / "control_boundary_readback.json"),
            "report": str(output_root / "p9q_define_next_gate_scope_owner_gate.md"),
        },
    }
    write_json(output_root / "summary.json", summary)
    (output_root / "p9q_define_next_gate_scope_owner_gate.md").write_text(
        render_markdown(summary),
        encoding="utf-8",
    )
    return summary, 0 if status == "ready" else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9Q Define Next-Gate Scope Owner Gate",
        "",
        f"`Status: {summary['status']}`",
        "",
        "## Boundary",
        "",
        "P9Q only decides whether a future concrete next-gate scope may be defined.",
        "",
        "```text",
        "gate_scope = owner_gated_allow_future_next_gate_scope_definition_only",
        "eligible_to_define_next_gate_scope = "
        f"{str(bool(summary['eligible_to_define_next_gate_scope'])).lower()}",
        "defined_next_gate_scope = false",
        "next_gate_execution_authorized = false",
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
    summary, exit_code = build_phase9q(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
