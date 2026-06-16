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


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9h_timer_hook_implementation_load_proposal.v1"
APPROVE_P9H_DECISION = "approve_p9h_timer_hook_implementation_load_proposal_only"
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_coinglass_candidate/"
    "phase9h_timer_hook_implementation_load_proposal"
)
PHASE9G_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_coinglass_candidate/"
    "phase9g_timer_hook_review_pack"
)
PROJECT_PROFILE = "config/project_governance/project_profile.json"
HOOK_MODULE = "src/enhengclaw/live_trading/dth60_observe_only_shadow_hook.py"
SUPERVISOR_PATH = "src/enhengclaw/live_trading/mainnet_live_supervisor.py"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a separate owner-gated P9H timer-hook implementation/load "
            "proposal. This creates a proof-only proposal and future gate "
            "checklist from retained P9G evidence. It does not implement, "
            "deploy, load, or enable a hook; it does not run the supervisor, "
            "invoke the timer path, mutate executor input, or authorize orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9g-summary", default="")
    parser.add_argument("--hook-module", default=HOOK_MODULE)
    parser.add_argument("--supervisor", default=SUPERVISOR_PATH)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9H_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:execute_owner_gated_p9h_timer_hook_implementation_load_proposal",
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


def p9g_ready(summary: dict[str, Any], *, current_hook_sha256: str) -> bool:
    gates = dict(summary.get("gates") or {})
    source_hook = dict(dict(summary.get("source_evidence") or {}).get("hook_module") or {})
    owner = dict(summary.get("owner_decision") or {})
    return (
        summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("review_pack_scope") == "owner_gated_timer_hook_review_pack_only"
        and summary.get("timer_hook_review_pack_ready") is True
        and summary.get("eligible_for_owner_timer_hook_review") is True
        and summary.get("eligible_for_timer_hook_implementation") is False
        and summary.get("timer_hook_implementation_authorized") is False
        and summary.get("hook_deployment_authorized") is False
        and summary.get("timer_path_load_authorized") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("target_plan_replacement_authorized") is False
        and summary.get("executor_input_mutation_authorized") is False
        and summary.get("candidate_order_authority") == "disabled"
        and summary.get("candidate_live_order_submission_authorized") is False
        and summary.get("execution_target_source") == "baseline_only"
        and summary.get("candidate_overlay_execution_path") == "excluded"
        and summary.get("candidate_artifact_sink") == "proof_artifacts_only"
        and summary.get("default_live_hook_enabled") is False
        and summary.get("live_supervisor_loads_candidate_hook") is False
        and summary.get("ran_supervisor") is False
        and summary.get("timer_path_invoked") is False
        and summary.get("remote_execution_performed") is False
        and summary.get("deployed_hook") is False
        and summary.get("eligible_for_timer_path_load") is False
        and summary.get("eligible_for_live_order_submission") is False
        and summary.get("eligible_for_stage_governance_change") is False
        and no_live_mutation(summary)
        and zero_orders_fills(summary)
        and owner.get("decision") == "approve_p9g_timer_hook_review_pack_only"
        and owner.get("timer_hook_review_pack_approved") is True
        and owner.get("timer_hook_implementation_approved") is False
        and owner.get("hook_deployment_approved") is False
        and owner.get("timer_path_load_approved") is False
        and owner.get("live_order_submission_approved") is False
        and source_hook.get("sha256") == current_hook_sha256
        and all(
            gates.get(key) is True
            for key in (
                "owner_decision_p9g_review_pack_only",
                "project_stage_boundary_preserved",
                "p9r_research_to_live_parity_ready",
                "p9d_default_off_hook_ready",
                "p9e_timer_adjacent_fixture_ready",
                "p9f_remote_proof_wrapper_ready",
                "current_live_supervisor_not_loading_hook",
                "hook_module_hash_consistent",
                "default_live_hook_disabled",
                "executor_baseline_only_all_proofs",
                "candidate_plan_not_referenced_all_proofs",
                "candidate_artifacts_proof_only_all_proofs",
                "no_timer_path_load_all_proofs",
                "no_live_mutation_all_proofs",
                "zero_orders_fills_all_proofs",
            )
        )
    )


def build_owner_decision_record(args: argparse.Namespace, started_at: datetime) -> dict[str, Any]:
    approved = str(args.owner_decision) == APPROVE_P9H_DECISION
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9h_owner_decision.v1",
        "owner": str(args.owner),
        "decision": str(args.owner_decision),
        "decision_source": str(args.owner_decision_source),
        "recorded_at_utc": iso_z(started_at),
        "decision_effect": (
            "authorize_p9h_timer_hook_implementation_load_proposal_only" if approved else "none"
        ),
        "implementation_load_proposal_approved": approved,
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


def implementation_load_proposal(run_id: str, owner_decision: dict[str, Any]) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9h_implementation_load_proposal.v1",
        "run_id": run_id,
        "proposal_scope": "owner_gated_timer_hook_implementation_load_proposal_only",
        "owner_decision": owner_decision,
        "proposal_question": (
            "What future, separately gated changes would be required before a "
            "default-off observe-only timer hook could be implemented and dry-loaded?"
        ),
        "proposed_future_sequence": [
            {
                "gate": "P9I",
                "name": "default_off_local_implementation_diff_fixture",
                "allowed_now": False,
                "required_owner_decision": "separate_owner_gate",
                "minimum_proof": [
                    "hook_disabled_baseline_byte_for_byte_unchanged",
                    "hook_enabled_writes_shadow_artifact_only",
                    "executor_input_hash_equals_baseline_target_hash",
                    "candidate_artifacts_under_proof_artifacts_only",
                    "orders_fills_zero",
                ],
            },
            {
                "gate": "P9J",
                "name": "proof_artifacts_dry_load_readback",
                "allowed_now": False,
                "required_owner_decision": "separate_owner_gate",
                "minimum_proof": [
                    "load_from_proof_artifacts_only",
                    "live_timer_service_not_enabled",
                    "supervisor_not_run_from_timer",
                    "executor_input_baseline_only",
                    "remote_control_plane_unchanged",
                ],
            },
            {
                "gate": "P9K",
                "name": "owner_review_after_dry_load_readback",
                "allowed_now": False,
                "required_owner_decision": "separate_owner_gate",
                "minimum_proof": [
                    "same_timestamp_context",
                    "same_risk_inputs",
                    "overlay_only_distance_to_high_60_contribution",
                    "candidate_plan_not_referenced_by_executor",
                    "no_live_order_submission",
                ],
            },
        ],
        "must_remain_false_in_p9h": [
            "timer_hook_implementation_authorized",
            "hook_deployment_authorized",
            "timer_path_load_authorized",
            "live_order_submission_authorized",
            "target_plan_replacement_authorized",
            "executor_input_mutation_authorized",
            "live_config_mutation_authorized",
            "operator_state_mutation_authorized",
            "timer_or_service_mutation_authorized",
            "remote_sync_authorized",
            "supervisor_run_authorized",
            "stage_governance_change_authorized",
        ],
        "non_goals": [
            "do_not_modify_mainnet_live_supervisor",
            "do_not_write_live_hook_config",
            "do_not_load_candidate_hook_from_timer",
            "do_not_run_supervisor",
            "do_not_invoke_timer_path",
            "do_not_mutate_executor_input",
            "do_not_replace_target_plan",
            "do_not_submit_orders",
        ],
    }


def future_gate_checklist(run_id: str) -> dict[str, Any]:
    checklist = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9h_future_gate_checklist.v1",
        "run_id": run_id,
        "status": "draft_for_future_owner_review",
        "p9h_authorizes_execution": False,
        "implementation_gate_required": True,
        "timer_load_gate_required": True,
        "live_order_gate_required": True,
        "required_before_any_implementation": [
            "separate_owner_decision_for_implementation",
            "specific_diff_scope_reviewed",
            "disabled_mode_byte_for_byte_baseline_parity_test",
            "enabled_fixture_shadow_artifact_only_test",
            "executor_baseline_only_readback_test",
            "zero_orders_fills_assertion",
        ],
        "required_before_any_load": [
            "separate_owner_decision_for_dry_load",
            "load_config_default_off",
            "proof_artifacts_output_root_only",
            "timer_service_disabled_or_not_invoked",
            "executor_input_hash_equals_baseline",
            "operator_state_unchanged",
            "live_config_unchanged_or_explicitly_reviewed_as_default_off_only",
        ],
        "required_before_any_live_orders": [
            "separate_owner_activation_decision",
            "fresh_pit_sidecar_proofs",
            "fresh_remote_observe_only_cycles",
            "risk_governance_review",
            "stage_boundary_or_live_policy_review",
        ],
    }
    return checklist


def build_phase9h(
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
    proof_root = output_root / "proof_artifacts" / "p9h" / run_id
    proof_root.mkdir(parents=True, exist_ok=True)

    paths = {
        "project_profile": resolve_path(args.project_profile),
        "phase9g": (
            resolve_path(args.phase9g_summary)
            if str(getattr(args, "phase9g_summary", "") or "").strip()
            else latest_match(PHASE9G_PARENT, "*/summary.json")
        ),
        "hook_module": resolve_path(args.hook_module),
        "supervisor": resolve_path(args.supervisor),
    }
    project_profile = load_optional(paths["project_profile"])
    p9g = load_optional(paths["phase9g"])
    current_hook_sha = file_sha256(paths["hook_module"]) if paths["hook_module"].exists() else ""
    supervisor_text = paths["supervisor"].read_text(encoding="utf-8") if paths["supervisor"].exists() else ""
    live_supervisor_loads_hook_now = "dth60_observe_only_shadow_hook" in supervisor_text

    owner_decision_record = build_owner_decision_record(args, started_at)
    proposal = implementation_load_proposal(run_id, owner_decision_record)
    checklist = future_gate_checklist(run_id)

    gates = {
        "owner_decision_p9h_proposal_only": str(args.owner_decision) == APPROVE_P9H_DECISION,
        "project_stage_boundary_preserved": project_profile.get("current_stage") == "stage_1_research_readiness_only",
        "p9g_timer_hook_review_pack_ready": p9g_ready(p9g, current_hook_sha256=current_hook_sha),
        "current_live_supervisor_not_loading_hook": not live_supervisor_loads_hook_now,
        "current_hook_hash_matches_p9g_source": (
            dict(dict(p9g.get("source_evidence") or {}).get("hook_module") or {}).get("sha256")
            == current_hook_sha
        ),
        "proposal_output_under_proof_artifacts": output_under_proof_artifacts(proof_root),
        "proposal_default_off_required": True,
        "proposal_timer_load_mode_is_not_live_timer_path": True,
        "proposal_executor_input_source_baseline_only": True,
        "proposal_candidate_order_authority_disabled": True,
        "proposal_artifact_sink_proof_artifacts_only": True,
        "future_implementation_gate_separate": True,
        "future_timer_load_gate_separate": True,
        "future_live_order_gate_separate": True,
        "no_hook_implementation_in_p9h": True,
        "no_hook_deployment_in_p9h": True,
        "no_timer_path_load_in_p9h": True,
        "no_supervisor_run_in_p9h": True,
        "no_remote_execution_in_p9h": True,
        "no_executor_input_mutation_in_p9h": True,
        "no_target_plan_replacement_in_p9h": True,
        "no_live_mutation_in_p9h": True,
        "zero_orders_fills_in_p9h": True,
    }
    blockers = [key for key, value in gates.items() if not value]
    status = "ready" if not blockers else "blocked"

    write_json(output_root / "owner_decision_record.json", owner_decision_record)
    write_json(proof_root / "implementation_load_proposal.json", proposal)
    write_json(proof_root / "future_gate_checklist.json", checklist)

    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "proposal_scope": "owner_gated_timer_hook_implementation_load_proposal_only",
        "owner_decision": owner_decision_record,
        "source_evidence": {
            "project_profile": evidence_file(paths["project_profile"]),
            "phase9g_summary": evidence_file(paths["phase9g"]),
            "hook_module": evidence_file(paths["hook_module"]),
            "live_supervisor": evidence_file(paths["supervisor"]),
        },
        "implementation_load_proposal_ready": status == "ready",
        "eligible_for_owner_implementation_load_review": status == "ready",
        "eligible_for_timer_hook_implementation": False,
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
        "proposed_default_live_hook_enabled": False,
        "proposed_timer_load_mode": "proposal_only_not_loaded",
        "proposed_executor_input_source": "baseline_only",
        "proposed_candidate_artifact_sink": "proof_artifacts_only",
        "default_live_hook_enabled": False,
        "live_supervisor_loads_candidate_hook": live_supervisor_loads_hook_now,
        "ran_supervisor": False,
        "timer_path_invoked": False,
        "remote_execution_performed": False,
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
        "eligible_for_timer_path_load": False,
        "eligible_for_live_order_submission": False,
        "eligible_for_stage_governance_change": False,
        "current_hook_module_sha256": current_hook_sha,
        "proof_root": str(proof_root),
        "gates": gates,
        "blockers": blockers,
        "output_files": {
            "summary": str(output_root / "summary.json"),
            "owner_decision_record": str(output_root / "owner_decision_record.json"),
            "implementation_load_proposal": str(proof_root / "implementation_load_proposal.json"),
            "future_gate_checklist": str(proof_root / "future_gate_checklist.json"),
            "report": str(output_root / "p9h_timer_hook_implementation_load_proposal.md"),
        },
    }
    write_json(output_root / "summary.json", summary)
    (output_root / "p9h_timer_hook_implementation_load_proposal.md").write_text(
        render_markdown(summary),
        encoding="utf-8",
    )
    return summary, 0 if status == "ready" else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9H Timer-Hook Implementation/Load Proposal",
        "",
        f"`Status: {summary['status']}`",
        "",
        "## Boundary",
        "",
        "This is a separate owner-gated implementation/load proposal only.",
        "",
        "```text",
        "proposal_scope = owner_gated_timer_hook_implementation_load_proposal_only",
        "implementation_load_proposal_ready = "
        f"{str(bool(summary['implementation_load_proposal_ready'])).lower()}",
        "timer_hook_implementation_authorized = false",
        "hook_deployment_authorized = false",
        "timer_path_load_authorized = false",
        "live_order_submission_authorized = false",
        "execution_target_source = baseline_only",
        "candidate_artifact_sink = proof_artifacts_only",
        "proposed_timer_load_mode = proposal_only_not_loaded",
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
    summary, exit_code = build_phase9h(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
