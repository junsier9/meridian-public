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

from enhengclaw.live_trading.dth60_observe_only_shadow_hook import (  # noqa: E402
    ObserveOnlyShadowHookConfig,
    run_observe_only_shadow_hook,
)


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9o_default_off_timer_path_dry_load_readback.v1"
APPROVE_P9O_DECISION = "approve_p9o_execute_default_off_timer_path_dry_load_readback_only"
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9o_default_off_dry_load_readback"
PHASE9N_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9n_dry_load_readback_owner_gate"
PROJECT_PROFILE = "config/project_governance/project_profile.json"
HOOK_MODULE = "src/enhengclaw/live_trading/dth60_observe_only_shadow_hook.py"
SUPERVISOR_PATH = "src/enhengclaw/live_trading/mainnet_live_supervisor.py"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Execute P9O default-off timer-path dry-load readback. This executes "
            "a proof_artifacts-only dry-load readback from retained P9N permission. "
            "It keeps hook enabled=false, executor input baseline-only, live timer "
            "service disabled, supervisor execution disabled, and order submission disabled."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9n-summary", default="")
    parser.add_argument("--hook-module", default=HOOK_MODULE)
    parser.add_argument("--supervisor", default=SUPERVISOR_PATH)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9O_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:execute_default_off_timer_path_dry_load_readback",
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


def path_under(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


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


def source_output_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("output_files") or {}).get(key) or "")
    return resolve_path(text) if text.strip() else Path("")


def p9n_gate_ready(gate: dict[str, Any]) -> bool:
    constraints = dict(gate.get("allowed_next_action_constraints") or {})
    owner = dict(gate.get("owner_decision") or {})
    return (
        gate.get("contract_version") == "hv_balanced_dth60_coinglass_phase9n_dry_load_readback_execution_gate.v1"
        and gate.get("gate_scope") == "owner_gated_default_off_timer_path_dry_load_readback_execution_permission_only"
        and gate.get("allowed_next_action") == "execute_default_off_timer_path_dry_load_readback"
        and gate.get("allowed_next_gate")
        == "P9O_default_off_timer_path_dry_load_readback_execution_only_if_separately_requested"
        and gate.get("executed_in_p9n") is False
        and constraints.get("default_off_required") is True
        and constraints.get("proof_artifacts_only") is True
        and constraints.get("candidate_order_authority") == "disabled"
        and constraints.get("candidate_live_order_submission_authorized") is False
        and constraints.get("executor_input_must_remain_baseline_only") is True
        and constraints.get("candidate_plan_must_not_be_referenced_by_executor") is True
        and constraints.get("target_plan_must_not_be_replaced") is True
        and constraints.get("must_not_modify_mainnet_live_supervisor") is True
        and constraints.get("must_not_modify_live_config") is True
        and constraints.get("must_not_modify_operator_state") is True
        and constraints.get("must_not_modify_timer_or_service_state") is True
        and constraints.get("must_not_enable_or_invoke_live_timer_service") is True
        and constraints.get("must_not_run_supervisor_for_execution") is True
        and constraints.get("must_not_remote_sync") is True
        and int(constraints.get("orders_submitted_must_equal", -1)) == 0
        and int(constraints.get("fill_count_must_equal", -1)) == 0
        and owner.get("decision") == "approve_p9n_execute_default_off_timer_path_dry_load_readback_only"
        and owner.get("future_default_off_timer_path_dry_load_readback_execution_approved") is True
        and owner.get("execute_readback_in_p9n_approved") is False
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
    )


def p9n_ready(
    summary: dict[str, Any],
    gate: dict[str, Any],
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
        "owner_decision_p9n_dry_load_readback_gate_only",
        "project_stage_boundary_preserved",
        "p9m_default_off_timer_path_dry_load_proposal_ready",
        "p9m_proposal_body_ready",
        "current_live_supervisor_not_loading_hook",
        "current_hook_hash_matches_p9m_source",
        "current_supervisor_hash_matches_p9m_source",
        "dry_load_readback_gate_output_under_proof_artifacts",
        "future_readback_must_be_default_off",
        "future_readback_must_be_proof_artifacts_only",
        "future_readback_must_keep_order_authority_disabled",
        "future_readback_must_keep_executor_baseline_only",
        "future_readback_must_not_reference_candidate_plan_by_executor",
        "future_readback_must_not_replace_target_plan",
        "future_readback_must_not_enable_live_timer_service",
        "future_readback_must_not_run_supervisor_for_execution",
        "no_readback_execution_in_p9n",
        "no_timer_hook_implementation_in_p9n",
        "no_hook_deployment_in_p9n",
        "no_live_timer_path_load_in_p9n",
        "no_supervisor_run_in_p9n",
        "no_remote_execution_in_p9n",
        "no_executor_input_mutation_in_p9n",
        "no_target_plan_replacement_in_p9n",
        "no_live_mutation_in_p9n",
        "zero_orders_fills_in_p9n",
    )
    return (
        summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("gate_scope") == "owner_gated_default_off_timer_path_dry_load_readback_execution_permission_only"
        and summary.get("p9n_default_off_timer_path_dry_load_readback_owner_gate_ready") is True
        and summary.get("eligible_to_execute_default_off_timer_path_dry_load_readback") is True
        and summary.get("executed_default_off_timer_path_dry_load_readback") is False
        and summary.get("allowed_next_gate")
        == "P9O_default_off_timer_path_dry_load_readback_execution_only_if_separately_requested"
        and summary.get("future_readback_default_off_required") is True
        and summary.get("future_readback_artifact_sink_required") == "proof_artifacts_only"
        and summary.get("future_readback_executor_input_required") == "baseline_only"
        and summary.get("future_readback_candidate_order_authority_required") == "disabled"
        and summary.get("future_readback_live_order_submission_authorized_required") is False
        and summary.get("future_readback_must_not_enable_live_timer_service") is True
        and summary.get("future_readback_must_not_run_supervisor_for_execution") is True
        and summary.get("eligible_for_timer_hook_implementation") is False
        and summary.get("eligible_for_hook_deployment") is False
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
        and owner.get("decision") == "approve_p9n_execute_default_off_timer_path_dry_load_readback_only"
        and owner.get("future_default_off_timer_path_dry_load_readback_execution_approved") is True
        and owner.get("execute_readback_in_p9n_approved") is False
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
        and p9n_gate_ready(gate)
        and all(gates.get(key) is True for key in required_gates)
    )


def build_owner_decision_record(args: argparse.Namespace, started_at: datetime) -> dict[str, Any]:
    approved = str(args.owner_decision) == APPROVE_P9O_DECISION
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9o_owner_decision.v1",
        "owner": str(args.owner),
        "decision": str(args.owner_decision),
        "decision_source": str(args.owner_decision_source),
        "recorded_at_utc": iso_z(started_at),
        "decision_question": "execute_default_off_timer_path_dry_load_readback_only",
        "decision_effect": (
            "execute_default_off_timer_path_dry_load_readback_under_p9n_constraints"
            if approved
            else "none"
        ),
        "default_off_timer_path_dry_load_readback_execution_approved": approved,
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


def build_fixture_plans(proof_root: Path) -> dict[str, Path]:
    input_root = proof_root / "input_plans"
    baseline = input_root / "baseline_target_plan.json"
    executor = input_root / "executor_input_target_plan.json"
    candidate = input_root / "candidate_shadow_plan.json"
    baseline_payload = {
        "contract_version": "hv_balanced_dth60_phase9o_fixture_plan.v1",
        "plan_type": "baseline_target_plan",
        "generated_for": "default_off_timer_path_dry_load_readback",
        "positions": [
            {"symbol": "BTCUSDT", "target_weight": 0.10},
            {"symbol": "ETHUSDT", "target_weight": -0.05},
        ],
        "risk_inputs": {"gross_cap": 0.15, "execution_target_source": "baseline_only"},
    }
    candidate_payload = {
        "contract_version": "hv_balanced_dth60_phase9o_fixture_plan.v1",
        "plan_type": "candidate_shadow_plan",
        "generated_for": "default_off_timer_path_dry_load_readback",
        "positions": [
            {"symbol": "BTCUSDT", "target_weight": 0.07},
            {"symbol": "ETHUSDT", "target_weight": -0.02},
        ],
        "risk_inputs": {"gross_cap": 0.15, "execution_target_source": "candidate_shadow_only"},
    }
    write_json(baseline, baseline_payload)
    write_json(executor, baseline_payload)
    write_json(candidate, candidate_payload)
    return {"baseline": baseline, "executor": executor, "candidate": candidate}


def build_phase9o(
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
    proof_root = output_root / "proof_artifacts" / "p9o" / run_id
    proof_root.mkdir(parents=True, exist_ok=True)

    paths = {
        "project_profile": resolve_path(args.project_profile),
        "phase9n": (
            resolve_path(args.phase9n_summary)
            if str(getattr(args, "phase9n_summary", "") or "").strip()
            else latest_match(PHASE9N_PARENT, "*/summary.json")
        ),
        "hook_module": resolve_path(args.hook_module),
        "supervisor": resolve_path(args.supervisor),
    }
    project_profile = load_optional(paths["project_profile"])
    p9n = load_optional(paths["phase9n"])
    p9n_gate_path = source_output_path(p9n, "dry_load_readback_execution_gate")
    p9n_gate = load_optional(p9n_gate_path)
    current_hook_sha = file_sha256(paths["hook_module"]) if paths["hook_module"].exists() else ""
    supervisor_sha_before = file_sha256(paths["supervisor"]) if paths["supervisor"].exists() else ""
    supervisor_text = paths["supervisor"].read_text(encoding="utf-8") if paths["supervisor"].exists() else ""
    live_supervisor_loads_hook_now = "dth60_observe_only_shadow_hook" in supervisor_text
    owner_decision_record = build_owner_decision_record(args, started_at)

    source_evidence = {
        "project_profile": evidence_file(paths["project_profile"]),
        "phase9n_summary": evidence_file(paths["phase9n"]),
        "phase9n_execution_gate": evidence_file(p9n_gate_path),
        "hook_module": evidence_file(paths["hook_module"]),
        "live_supervisor": evidence_file(paths["supervisor"]),
    }
    p9n_ok = p9n_ready(
        p9n,
        p9n_gate,
        current_hook_sha256=current_hook_sha,
        current_supervisor_sha256=supervisor_sha_before,
    )
    owner_ok = str(args.owner_decision) == APPROVE_P9O_DECISION
    project_stage_ok = project_profile.get("current_stage") == "stage_1_research_readiness_only"
    current_supervisor_not_loading_hook = not live_supervisor_loads_hook_now
    current_hook_matches_p9n = (
        dict(dict(p9n.get("source_evidence") or {}).get("hook_module") or {}).get("sha256")
        == current_hook_sha
    )
    current_supervisor_matches_p9n = (
        dict(dict(p9n.get("source_evidence") or {}).get("live_supervisor") or {}).get("sha256")
        == supervisor_sha_before
    )
    pre_execution_gates = {
        "owner_decision_p9o_execute_readback_only": owner_ok,
        "project_stage_boundary_preserved": project_stage_ok,
        "p9n_dry_load_readback_owner_gate_ready": p9n_ok,
        "current_live_supervisor_not_loading_hook": current_supervisor_not_loading_hook,
        "current_hook_hash_matches_p9n_source": current_hook_matches_p9n,
        "current_supervisor_hash_matches_p9n_source": current_supervisor_matches_p9n,
        "dry_load_output_root_under_proof_artifacts": output_under_proof_artifacts(proof_root),
    }
    pre_execution_blockers = [key for key, value in pre_execution_gates.items() if not value]
    if pre_execution_blockers:
        supervisor_sha_after = file_sha256(paths["supervisor"]) if paths["supervisor"].exists() else ""
        control_boundary_readback = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9o_control_boundary_readback.v1",
            "run_id": run_id,
            "scope": "pre_execution_gate_failed_no_dry_load_readback",
            "live_supervisor": source_evidence["live_supervisor"],
            "live_supervisor_sha256_before": supervisor_sha_before,
            "live_supervisor_sha256_after": supervisor_sha_after,
            "live_supervisor_source_unchanged": supervisor_sha_before == supervisor_sha_after,
            "live_supervisor_loads_candidate_hook": live_supervisor_loads_hook_now,
            "live_timer_path_loaded": False,
            "live_timer_service_enabled_or_invoked": False,
            "ran_supervisor": False,
            "remote_control_plane_touched": False,
            "live_config_changed": False,
            "operator_state_changed": False,
            "timer_state_changed": False,
            "executor_input_mutated": False,
            "target_plan_replaced": False,
            "orders_submitted": 0,
            "fill_count": 0,
        }
        write_json(proof_root / "control_boundary_readback.json", control_boundary_readback)
        output_files = {
            "summary": str(output_root / "summary.json"),
            "owner_decision_record": str(output_root / "owner_decision_record.json"),
            "control_boundary_readback": str(proof_root / "control_boundary_readback.json"),
            "report": str(output_root / "p9o_default_off_timer_path_dry_load_readback.md"),
        }
        summary = {
            "contract_version": CONTRACT_VERSION,
            "status": "blocked",
            "run_id": run_id,
            "generated_at_utc": iso_z(started_at),
            "dry_load_readback_scope": "owner_gated_default_off_timer_path_dry_load_readback_execution_only",
            "owner_decision": owner_decision_record,
            "source_evidence": source_evidence,
            "default_off_timer_path_dry_load_readback_ready": False,
            "executed_default_off_timer_path_dry_load_readback": False,
            "dry_load_mode": "not_executed",
            "dry_load_outputs_under_proof_artifacts": output_under_proof_artifacts(proof_root),
            "default_off_config_loaded": False,
            "default_off_hook_enabled": False,
            "disabled_hook_readback_ready": False,
            "disabled_hook_candidate_artifacts_written_count": 0,
            "baseline_target_plan_byte_for_byte_unchanged": False,
            "executor_input_hash_unchanged": False,
            "executor_input_hash_equals_baseline": False,
            "executor_consumes_baseline_only": False,
            "candidate_shadow_hash_differs_from_executor": False,
            "candidate_plan_referenced_by_executor": False,
            "target_plan_replaced": False,
            "executor_input_changed": False,
            "eligible_for_owner_p9p_review": False,
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
            "live_supervisor_source_unchanged": supervisor_sha_before == supervisor_sha_after,
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
            "recommended_next_gate": "",
            "proof_root": str(proof_root),
            "gates": pre_execution_gates,
            "blockers": pre_execution_blockers,
            "output_files": output_files,
        }
        write_json(output_root / "owner_decision_record.json", owner_decision_record)
        write_json(output_root / "summary.json", summary)
        (output_root / "p9o_default_off_timer_path_dry_load_readback.md").write_text(
            render_markdown(summary),
            encoding="utf-8",
        )
        return summary, 2

    plan_paths = build_fixture_plans(proof_root)
    dry_load_config = ObserveOnlyShadowHookConfig(
        enabled=False,
        mode="observe_only",
        artifact_sink="proof_artifacts_only",
        output_root=proof_root / "default_off_hook_disabled_output",
        candidate_order_authority="disabled",
        candidate_live_order_submission_authorized=False,
        execution_target_source="baseline_only",
        candidate_overlay_execution_path="excluded",
    )
    hook_summary = run_observe_only_shadow_hook(
        config=dry_load_config,
        baseline_target_plan_path=plan_paths["baseline"],
        executor_input_plan_path=plan_paths["executor"],
        candidate_shadow_plan_path=plan_paths["candidate"],
        supervisor_context={
            "phase": "P9O",
            "dry_load_mode": "default_off_timer_path_readback_not_live_timer_service",
            "live_timer_service_enabled_or_invoked": False,
            "supervisor_run_for_execution": False,
        },
        run_id=f"{run_id}-default-off-readback",
        now=started_at,
    )
    write_json(proof_root / "disabled_hook_readback_summary.json", hook_summary)

    baseline_sha = file_sha256(plan_paths["baseline"])
    executor_sha = file_sha256(plan_paths["executor"])
    candidate_sha = file_sha256(plan_paths["candidate"])
    executor_input_hash_equals_baseline = bool(executor_sha) and executor_sha == baseline_sha
    candidate_shadow_hash_differs_from_executor = bool(candidate_sha) and candidate_sha != executor_sha

    default_off_config_readback = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9o_default_off_config_readback.v1",
        "run_id": run_id,
        "dry_load_mode": "default_off_timer_path_readback_not_live_timer_service",
        "default_off_required": True,
        "hook_config_enabled": dry_load_config.enabled,
        "mode": dry_load_config.mode,
        "artifact_sink": dry_load_config.artifact_sink,
        "candidate_order_authority": dry_load_config.candidate_order_authority,
        "candidate_live_order_submission_authorized": dry_load_config.candidate_live_order_submission_authorized,
        "execution_target_source": dry_load_config.execution_target_source,
        "candidate_overlay_execution_path": dry_load_config.candidate_overlay_execution_path,
        "proof_artifacts_only": output_under_proof_artifacts(proof_root),
        "live_timer_service_enabled_or_invoked": False,
        "supervisor_run_for_execution": False,
        "remote_sync_performed": False,
        "orders_submitted": 0,
        "fill_count": 0,
    }
    executor_input_readback = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9o_executor_input_readback.v1",
        "run_id": run_id,
        "execution_target_source": "baseline_only",
        "baseline_target_plan": evidence_file(plan_paths["baseline"]),
        "executor_input_plan": evidence_file(plan_paths["executor"]),
        "candidate_shadow_plan": evidence_file(plan_paths["candidate"]),
        "executor_input_hash_equals_baseline": executor_input_hash_equals_baseline,
        "candidate_shadow_hash_differs_from_executor": candidate_shadow_hash_differs_from_executor,
        "candidate_plan_referenced_by_executor": False,
        "target_plan_replaced": False,
        "executor_input_changed": False,
        "orders_submitted": 0,
        "fill_count": 0,
    }
    write_json(proof_root / "default_off_config_readback.json", default_off_config_readback)
    write_json(proof_root / "executor_input_readback.json", executor_input_readback)
    dry_load_execution_manifest = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9o_dry_load_execution_manifest.v1",
        "run_id": run_id,
        "dry_load_readback_executed": True,
        "dry_load_mode": "default_off_timer_path_readback_not_live_timer_service",
        "dry_load_source": "retained_p9n_owner_gate_plus_local_fresh_fixture_plans",
        "source_evidence": source_evidence,
        "default_off_config_readback": evidence_file(proof_root / "default_off_config_readback.json"),
        "disabled_hook_readback_summary": evidence_file(proof_root / "disabled_hook_readback_summary.json"),
        "executor_input_readback": evidence_file(proof_root / "executor_input_readback.json"),
        "live_timer_path_loaded": False,
        "live_timer_service_enabled_or_invoked": False,
        "supervisor_run_invoked": False,
        "remote_sync_performed": False,
        "execution_target_source": "baseline_only",
        "candidate_order_authority": "disabled",
        "candidate_live_order_submission_authorized": False,
        "orders_submitted": 0,
        "fill_count": 0,
    }
    write_json(proof_root / "dry_load_execution_manifest.json", dry_load_execution_manifest)

    supervisor_sha_after = file_sha256(paths["supervisor"]) if paths["supervisor"].exists() else ""
    control_boundary_readback = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9o_control_boundary_readback.v1",
        "run_id": run_id,
        "scope": "local_proof_artifacts_default_off_dry_load_readback_only",
        "live_supervisor": source_evidence["live_supervisor"],
        "live_supervisor_sha256_before": supervisor_sha_before,
        "live_supervisor_sha256_after": supervisor_sha_after,
        "live_supervisor_source_unchanged": supervisor_sha_before == supervisor_sha_after,
        "live_supervisor_loads_candidate_hook": live_supervisor_loads_hook_now,
        "live_timer_path_loaded": False,
        "live_timer_service_enabled_or_invoked": False,
        "ran_supervisor": False,
        "remote_control_plane_touched": False,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "executor_input_mutated": False,
        "target_plan_replaced": False,
        "orders_submitted": 0,
        "fill_count": 0,
    }
    write_json(proof_root / "control_boundary_readback.json", control_boundary_readback)

    output_files = {
        "summary": str(output_root / "summary.json"),
        "owner_decision_record": str(output_root / "owner_decision_record.json"),
        "dry_load_execution_manifest": str(proof_root / "dry_load_execution_manifest.json"),
        "default_off_config_readback": str(proof_root / "default_off_config_readback.json"),
        "disabled_hook_readback_summary": str(proof_root / "disabled_hook_readback_summary.json"),
        "executor_input_readback": str(proof_root / "executor_input_readback.json"),
        "control_boundary_readback": str(proof_root / "control_boundary_readback.json"),
        "baseline_target_plan": str(plan_paths["baseline"]),
        "executor_input_plan": str(plan_paths["executor"]),
        "candidate_shadow_plan": str(plan_paths["candidate"]),
        "report": str(output_root / "p9o_default_off_timer_path_dry_load_readback.md"),
    }
    output_paths_under_proof = all(
        output_under_proof_artifacts(resolve_path(path))
        for key, path in output_files.items()
        if key not in {"summary", "owner_decision_record", "report"}
    )
    hook_summary_ready = (
        hook_summary.get("status") == "ready"
        and hook_summary.get("hook_enabled") is False
        and hook_summary.get("executor_consumes_baseline_only") is True
        and hook_summary.get("candidate_artifacts_written_count") == 0
        and hook_summary.get("candidate_plan_referenced_by_executor") is False
        and zero_orders_fills(hook_summary)
        and no_live_mutation(hook_summary)
    )
    gates = {
        **pre_execution_gates,
        "dry_load_outputs_under_proof_artifacts": output_paths_under_proof,
        "dry_load_mode_not_live_timer_service": default_off_config_readback.get("dry_load_mode")
        == "default_off_timer_path_readback_not_live_timer_service",
        "default_off_config_loaded": default_off_config_readback.get("hook_config_enabled") is False,
        "artifact_sink_proof_artifacts_only": default_off_config_readback.get("artifact_sink") == "proof_artifacts_only",
        "candidate_order_authority_disabled": default_off_config_readback.get("candidate_order_authority") == "disabled",
        "candidate_live_order_submission_authorized_false": default_off_config_readback.get(
            "candidate_live_order_submission_authorized"
        )
        is False,
        "execution_target_source_baseline_only": default_off_config_readback.get("execution_target_source")
        == "baseline_only",
        "disabled_hook_readback_ready": hook_summary_ready,
        "disabled_hook_writes_zero_candidate_artifacts": hook_summary.get("candidate_artifacts_written_count") == 0,
        "baseline_target_plan_byte_for_byte_unchanged": hook_summary.get(
            "baseline_target_plan_byte_for_byte_unchanged"
        )
        is True,
        "executor_input_hash_unchanged": hook_summary.get("executor_input_plan_hash_unchanged") is True,
        "executor_input_hash_equals_baseline": executor_input_hash_equals_baseline,
        "executor_consumes_baseline_only": hook_summary.get("executor_consumes_baseline_only") is True,
        "candidate_shadow_hash_differs_from_executor": candidate_shadow_hash_differs_from_executor,
        "candidate_plan_not_referenced_by_executor": executor_input_readback.get("candidate_plan_referenced_by_executor")
        is False,
        "target_plan_not_replaced": executor_input_readback.get("target_plan_replaced") is False,
        "live_supervisor_source_unchanged": supervisor_sha_before == supervisor_sha_after,
        "live_timer_service_not_enabled_or_invoked": default_off_config_readback.get(
            "live_timer_service_enabled_or_invoked"
        )
        is False,
        "supervisor_not_run_for_execution": default_off_config_readback.get("supervisor_run_for_execution") is False,
        "no_remote_sync_in_p9o": default_off_config_readback.get("remote_sync_performed") is False,
        "no_live_timer_path_load_in_p9o": True,
        "no_executor_input_mutation_in_p9o": True,
        "no_target_plan_replacement_in_p9o": True,
        "no_live_mutation_in_p9o": True,
        "zero_orders_fills_in_p9o": True,
    }
    blockers = [key for key, value in gates.items() if not value]
    status = "ready" if not blockers else "blocked"
    readback_ready = status == "ready"

    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "dry_load_readback_scope": "owner_gated_default_off_timer_path_dry_load_readback_execution_only",
        "owner_decision": owner_decision_record,
        "source_evidence": source_evidence,
        "default_off_timer_path_dry_load_readback_ready": readback_ready,
        "executed_default_off_timer_path_dry_load_readback": True,
        "dry_load_mode": "default_off_timer_path_readback_not_live_timer_service",
        "dry_load_outputs_under_proof_artifacts": output_paths_under_proof,
        "default_off_config_loaded": default_off_config_readback.get("hook_config_enabled") is False,
        "default_off_hook_enabled": False,
        "disabled_hook_readback_ready": hook_summary_ready,
        "disabled_hook_candidate_artifacts_written_count": int(
            hook_summary.get("candidate_artifacts_written_count") or 0
        ),
        "baseline_target_plan_byte_for_byte_unchanged": hook_summary.get(
            "baseline_target_plan_byte_for_byte_unchanged"
        ),
        "executor_input_hash_unchanged": hook_summary.get("executor_input_plan_hash_unchanged"),
        "executor_input_hash_equals_baseline": executor_input_hash_equals_baseline,
        "executor_consumes_baseline_only": hook_summary.get("executor_consumes_baseline_only"),
        "candidate_shadow_hash_differs_from_executor": candidate_shadow_hash_differs_from_executor,
        "candidate_plan_referenced_by_executor": False,
        "target_plan_replaced": False,
        "executor_input_changed": False,
        "eligible_for_owner_p9p_review": readback_ready,
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
        "live_supervisor_source_unchanged": supervisor_sha_before == supervisor_sha_after,
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
        "recommended_next_gate": "P9P_owner_review_after_default_off_dry_load_readback_if_separately_requested",
        "proof_root": str(proof_root),
        "gates": gates,
        "blockers": blockers,
        "output_files": output_files,
    }
    write_json(output_root / "owner_decision_record.json", owner_decision_record)
    write_json(output_root / "summary.json", summary)
    (output_root / "p9o_default_off_timer_path_dry_load_readback.md").write_text(
        render_markdown(summary),
        encoding="utf-8",
    )
    return summary, 0 if status == "ready" else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9O Default-Off Timer-Path Dry-Load Readback",
        "",
        f"`Status: {summary['status']}`",
        "",
        "## Boundary",
        "",
        "P9O executes a default-off timer-path dry-load readback under proof_artifacts only.",
        "",
        "```text",
        "dry_load_readback_scope = owner_gated_default_off_timer_path_dry_load_readback_execution_only",
        f"default_off_timer_path_dry_load_readback_ready = {str(bool(summary['default_off_timer_path_dry_load_readback_ready'])).lower()}",
        "executed_default_off_timer_path_dry_load_readback = "
        f"{str(bool(summary['executed_default_off_timer_path_dry_load_readback'])).lower()}",
        f"dry_load_mode = {summary['dry_load_mode']}",
        "default_off_hook_enabled = false",
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
    summary, exit_code = build_phase9o(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
