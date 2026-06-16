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


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9j_proof_artifacts_dry_load_readback.v1"
APPROVE_P9J_DECISION = "approve_p9j_proof_artifacts_dry_load_readback_only"
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9j_dry_load_readback"
PHASE9I_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9i_diff_fixture"
PROJECT_PROFILE = "config/project_governance/project_profile.json"
HOOK_MODULE = "src/enhengclaw/live_trading/dth60_observe_only_shadow_hook.py"
SUPERVISOR_PATH = "src/enhengclaw/live_trading/mainnet_live_supervisor.py"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the P9J proof_artifacts dry-load readback. This reads the "
            "retained P9I proof_artifacts bundle and writes a dry-load readback "
            "bundle. It does not apply a supervisor diff, load the live timer "
            "path, run the supervisor, mutate executor input, sync remote state, "
            "or authorize orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9i-summary", default="")
    parser.add_argument("--hook-module", default=HOOK_MODULE)
    parser.add_argument("--supervisor", default=SUPERVISOR_PATH)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9J_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:execute_owner_gated_p9j_proof_artifacts_dry_load_readback",
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


def path_contains_part(path: Path, part: str) -> bool:
    return part.lower() in [item.lower() for item in path.resolve().parts]


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


def output_path(summary: dict[str, Any], key: str) -> Path:
    return resolve_path(str(dict(summary.get("output_files") or {}).get(key) or ""))


def p9i_ready(summary: dict[str, Any], *, current_hook_sha256: str, current_supervisor_sha256: str) -> bool:
    gates = dict(summary.get("gates") or {})
    source_evidence = dict(summary.get("source_evidence") or {})
    source_hook = dict(source_evidence.get("hook_module") or {})
    source_supervisor = dict(source_evidence.get("live_supervisor") or {})
    owner = dict(summary.get("owner_decision") or {})
    required_gates = (
        "owner_decision_p9i_fixture_only",
        "project_stage_boundary_preserved",
        "p9h_proposal_ready",
        "current_live_supervisor_not_loading_hook",
        "current_hook_hash_matches_p9h_source",
        "current_supervisor_hash_matches_p9h_source",
        "implementation_diff_fixture_written",
        "proposed_diff_patch_written",
        "implementation_diff_fixture_not_applied_to_live_supervisor",
        "diff_fixture_default_off",
        "diff_fixture_order_authority_disabled",
        "diff_fixture_executor_source_baseline_only",
        "disabled_hook_ready",
        "disabled_hook_baseline_byte_for_byte_unchanged",
        "disabled_hook_writes_zero_candidate_artifacts",
        "enabled_hook_ready",
        "enabled_hook_writes_shadow_artifact_only",
        "executor_input_hash_equals_baseline_target_hash",
        "candidate_artifacts_under_output_proof_root",
        "candidate_order_authority_disabled",
        "candidate_live_order_submission_authorized_false",
        "no_timer_path_load_in_p9i",
        "no_supervisor_run_in_p9i",
        "no_remote_execution_in_p9i",
        "no_executor_input_mutation_in_p9i",
        "no_target_plan_replacement_in_p9i",
        "no_live_mutation_in_p9i",
        "zero_orders_fills_in_p9i",
    )
    return (
        summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("fixture_scope") == "owner_gated_default_off_local_implementation_diff_fixture_only"
        and summary.get("implementation_diff_fixture_ready") is True
        and summary.get("eligible_for_owner_p9j_dry_load_review") is True
        and summary.get("eligible_for_timer_hook_implementation") is False
        and summary.get("timer_hook_implementation_authorized") is False
        and summary.get("hook_deployment_authorized") is False
        and summary.get("timer_path_load_authorized") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("target_plan_replacement_authorized") is False
        and summary.get("executor_input_mutation_authorized") is False
        and summary.get("remote_sync_authorized") is False
        and summary.get("supervisor_run_authorized") is False
        and summary.get("candidate_order_authority") == "disabled"
        and summary.get("execution_target_source") == "baseline_only"
        and summary.get("candidate_artifact_sink") == "proof_artifacts_only"
        and summary.get("live_supervisor_loads_candidate_hook") is False
        and summary.get("implemented_hook_in_live_supervisor") is False
        and summary.get("implementation_diff_fixture_applied_to_live_supervisor") is False
        and summary.get("supervisor_sha256_before_fixture") == summary.get("supervisor_sha256_after_fixture")
        and summary.get("supervisor_sha256_before_fixture") == current_supervisor_sha256
        and summary.get("disabled_hook_baseline_byte_for_byte_unchanged") is True
        and int(summary.get("disabled_hook_candidate_artifacts_written_count") or 0) == 0
        and summary.get("enabled_hook_writes_shadow_artifact_only") is True
        and summary.get("executor_input_hash_equals_baseline_target_hash") is True
        and summary.get("candidate_artifacts_under_proof_artifacts_only") is True
        and summary.get("candidate_plan_referenced_by_executor") is False
        and summary.get("ran_supervisor") is False
        and summary.get("timer_path_invoked") is False
        and summary.get("remote_execution_performed") is False
        and summary.get("eligible_for_timer_path_load") is False
        and summary.get("eligible_for_live_order_submission") is False
        and no_live_mutation(summary)
        and zero_orders_fills(summary)
        and owner.get("decision") == "approve_p9i_default_off_local_implementation_diff_fixture_only"
        and owner.get("local_implementation_diff_fixture_approved") is True
        and owner.get("timer_hook_implementation_approved") is False
        and owner.get("hook_deployment_approved") is False
        and owner.get("timer_path_load_approved") is False
        and owner.get("live_order_submission_approved") is False
        and source_hook.get("sha256") == current_hook_sha256
        and source_supervisor.get("sha256") == current_supervisor_sha256
        and all(gates.get(key) is True for key in required_gates)
    )


def build_owner_decision_record(args: argparse.Namespace, started_at: datetime) -> dict[str, Any]:
    approved = str(args.owner_decision) == APPROVE_P9J_DECISION
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9j_owner_decision.v1",
        "owner": str(args.owner),
        "decision": str(args.owner_decision),
        "decision_source": str(args.owner_decision_source),
        "recorded_at_utc": iso_z(started_at),
        "decision_effect": (
            "authorize_p9j_proof_artifacts_dry_load_readback_only" if approved else "none"
        ),
        "proof_artifacts_dry_load_readback_approved": approved,
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


def build_phase9j(
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
    proof_root = output_root / "proof_artifacts" / "p9j" / run_id
    proof_root.mkdir(parents=True, exist_ok=True)

    paths = {
        "project_profile": resolve_path(args.project_profile),
        "phase9i": (
            resolve_path(args.phase9i_summary)
            if str(getattr(args, "phase9i_summary", "") or "").strip()
            else latest_match(PHASE9I_PARENT, "*/summary.json")
        ),
        "hook_module": resolve_path(args.hook_module),
        "supervisor": resolve_path(args.supervisor),
    }
    project_profile = load_optional(paths["project_profile"])
    p9i = load_optional(paths["phase9i"])
    current_hook_sha = file_sha256(paths["hook_module"]) if paths["hook_module"].exists() else ""
    supervisor_sha_before = file_sha256(paths["supervisor"]) if paths["supervisor"].exists() else ""
    supervisor_text = paths["supervisor"].read_text(encoding="utf-8") if paths["supervisor"].exists() else ""
    live_supervisor_loads_hook_now = "dth60_observe_only_shadow_hook" in supervisor_text
    owner_decision_record = build_owner_decision_record(args, started_at)

    source_paths = {
        "implementation_diff_fixture": output_path(p9i, "implementation_diff_fixture"),
        "proposed_supervisor_hook_diff": output_path(p9i, "proposed_supervisor_hook_diff"),
        "disabled_hook_summary": output_path(p9i, "disabled_hook_summary"),
        "enabled_hook_summary": output_path(p9i, "enabled_hook_summary"),
    }
    implementation_diff = load_optional(source_paths["implementation_diff_fixture"])
    disabled_hook = load_optional(source_paths["disabled_hook_summary"])
    enabled_hook = load_optional(source_paths["enabled_hook_summary"])
    enabled_proof_root = resolve_path(str(enabled_hook.get("proof_root") or ""))
    source_paths["executor_input_readback"] = enabled_proof_root / "executor_input_readback.json"
    source_paths["shadow_manifest"] = enabled_proof_root / "manifest.json"
    source_paths["candidate_shadow_plan"] = enabled_proof_root / "candidate_shadow_plan.json"
    executor_readback = load_optional(source_paths["executor_input_readback"])
    shadow_manifest = load_optional(source_paths["shadow_manifest"])

    baseline_plan = dict(executor_readback.get("baseline_target_plan") or {})
    executor_plan = dict(executor_readback.get("executor_input_plan") or {})
    candidate_plan = dict(executor_readback.get("candidate_shadow_plan") or {})
    executor_input_hash_equals_baseline = (
        bool(executor_plan.get("sha256"))
        and executor_plan.get("sha256") == baseline_plan.get("sha256")
    )
    candidate_shadow_hash_differs_from_executor = (
        bool(candidate_plan.get("sha256"))
        and bool(executor_plan.get("sha256"))
        and candidate_plan.get("sha256") != executor_plan.get("sha256")
    )

    dry_load_manifest = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9j_dry_load_manifest.v1",
        "run_id": run_id,
        "dry_load_mode": "proof_artifacts_readback_only_not_timer_path",
        "dry_load_source": "phase9i_proof_artifacts",
        "source_phase9i_summary": evidence_file(paths["phase9i"]),
        "source_files": {key: evidence_file(path) for key, path in source_paths.items()},
        "live_timer_path_loaded": False,
        "live_timer_service_enabled_or_invoked": False,
        "supervisor_run_invoked": False,
        "remote_sync_performed": False,
        "execution_target_source": "baseline_only",
        "candidate_order_authority": "disabled",
        "candidate_live_order_submission_authorized": False,
    }
    dry_load_readback = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9j_dry_load_readback.v1",
        "run_id": run_id,
        "dry_load_mode": "proof_artifacts_readback_only_not_timer_path",
        "implementation_diff_fixture": implementation_diff,
        "disabled_hook_status": disabled_hook.get("status"),
        "enabled_hook_status": enabled_hook.get("status"),
        "executor_input_readback": executor_readback,
        "shadow_manifest": shadow_manifest,
        "baseline_target_plan_sha256": str(baseline_plan.get("sha256") or ""),
        "executor_input_plan_sha256": str(executor_plan.get("sha256") or ""),
        "candidate_shadow_plan_sha256": str(candidate_plan.get("sha256") or ""),
        "executor_input_hash_equals_baseline": executor_input_hash_equals_baseline,
        "candidate_shadow_hash_differs_from_executor": candidate_shadow_hash_differs_from_executor,
        "candidate_plan_referenced_by_executor": executor_readback.get("candidate_plan_referenced_by_executor"),
        "candidate_artifacts_under_proof_artifacts_only": enabled_hook.get(
            "candidate_artifacts_under_proof_artifacts_only"
        ),
        "orders_submitted": 0,
        "fill_count": 0,
    }
    write_json(proof_root / "dry_load_manifest.json", dry_load_manifest)
    write_json(proof_root / "dry_load_readback.json", dry_load_readback)

    supervisor_sha_after = file_sha256(paths["supervisor"]) if paths["supervisor"].exists() else ""
    control_plane_readback = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9j_control_plane_readback.v1",
        "run_id": run_id,
        "scope": "local_source_and_proof_artifacts_only",
        "live_supervisor": evidence_file(paths["supervisor"]),
        "live_supervisor_sha256_before": supervisor_sha_before,
        "live_supervisor_sha256_after": supervisor_sha_after,
        "live_supervisor_source_unchanged": supervisor_sha_before == supervisor_sha_after,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "remote_control_plane_readback_performed": False,
        "remote_control_plane_touched": False,
    }
    write_json(proof_root / "control_plane_readback.json", control_plane_readback)

    dry_load_source_files = list(source_paths.values())
    gates = {
        "owner_decision_p9j_dry_load_readback_only": str(args.owner_decision) == APPROVE_P9J_DECISION,
        "project_stage_boundary_preserved": project_profile.get("current_stage") == "stage_1_research_readiness_only",
        "p9i_diff_fixture_ready": p9i_ready(
            p9i,
            current_hook_sha256=current_hook_sha,
            current_supervisor_sha256=supervisor_sha_before,
        ),
        "current_live_supervisor_not_loading_hook": not live_supervisor_loads_hook_now,
        "current_hook_hash_matches_p9i_source": (
            dict(dict(p9i.get("source_evidence") or {}).get("hook_module") or {}).get("sha256")
            == current_hook_sha
        ),
        "current_supervisor_hash_matches_p9i_source": (
            dict(dict(p9i.get("source_evidence") or {}).get("live_supervisor") or {}).get("sha256")
            == supervisor_sha_before
        ),
        "dry_load_source_files_exist": all(path.exists() for path in dry_load_source_files),
        "dry_load_source_files_under_p9i_proof_artifacts": all(
            path_contains_part(path, "proof_artifacts") for path in dry_load_source_files
        ),
        "dry_load_output_under_proof_artifacts": path_contains_part(proof_root, "proof_artifacts"),
        "dry_load_mode_not_live_timer_path": dry_load_manifest.get("dry_load_mode")
        == "proof_artifacts_readback_only_not_timer_path",
        "dry_load_default_off": implementation_diff.get("default_live_hook_enabled") is False,
        "dry_load_order_authority_disabled": implementation_diff.get("candidate_order_authority") == "disabled",
        "dry_load_executor_source_baseline_only": implementation_diff.get("execution_target_source") == "baseline_only",
        "live_timer_service_not_enabled_or_invoked": dry_load_manifest.get("live_timer_service_enabled_or_invoked") is False,
        "supervisor_not_run_from_timer": dry_load_manifest.get("supervisor_run_invoked") is False,
        "executor_input_hash_equals_baseline": executor_input_hash_equals_baseline,
        "executor_consumes_baseline_only": (
            enabled_hook.get("executor_consumes_baseline_only") is True
            and executor_readback.get("execution_target_source") == "baseline_only"
        ),
        "candidate_shadow_hash_differs_from_executor": candidate_shadow_hash_differs_from_executor,
        "candidate_plan_not_referenced_by_executor": executor_readback.get("candidate_plan_referenced_by_executor") is False,
        "candidate_artifacts_under_proof_artifacts_only": enabled_hook.get(
            "candidate_artifacts_under_proof_artifacts_only"
        )
        is True,
        "live_supervisor_source_unchanged": supervisor_sha_before == supervisor_sha_after,
        "no_timer_path_load_in_p9j": True,
        "no_supervisor_run_in_p9j": True,
        "no_remote_execution_in_p9j": True,
        "no_executor_input_mutation_in_p9j": True,
        "no_target_plan_replacement_in_p9j": True,
        "no_live_mutation_in_p9j": True,
        "zero_orders_fills_in_p9j": True,
    }
    blockers = [key for key, value in gates.items() if not value]
    status = "ready" if not blockers else "blocked"

    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "dry_load_readback_scope": "owner_gated_proof_artifacts_dry_load_readback_only",
        "owner_decision": owner_decision_record,
        "source_evidence": {
            "project_profile": evidence_file(paths["project_profile"]),
            "phase9i_summary": evidence_file(paths["phase9i"]),
            "hook_module": evidence_file(paths["hook_module"]),
            "live_supervisor": evidence_file(paths["supervisor"]),
        },
        "proof_artifacts_dry_load_readback_ready": status == "ready",
        "eligible_for_owner_p9k_review": status == "ready",
        "eligible_for_timer_hook_implementation": False,
        "timer_hook_implementation_authorized": False,
        "proof_artifacts_dry_load_readback_authorized": str(args.owner_decision) == APPROVE_P9J_DECISION,
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
        "dry_load_mode": "proof_artifacts_readback_only_not_timer_path",
        "dry_loaded_from_proof_artifacts_only": gates["dry_load_source_files_under_p9i_proof_artifacts"],
        "dry_load_output_under_proof_artifacts": gates["dry_load_output_under_proof_artifacts"],
        "live_timer_path_loaded": False,
        "live_timer_service_enabled_or_invoked": False,
        "live_supervisor_loads_candidate_hook": live_supervisor_loads_hook_now,
        "supervisor_sha256_before_readback": supervisor_sha_before,
        "supervisor_sha256_after_readback": supervisor_sha_after,
        "live_supervisor_source_unchanged": supervisor_sha_before == supervisor_sha_after,
        "executor_input_hash_equals_baseline": executor_input_hash_equals_baseline,
        "executor_consumes_baseline_only": gates["executor_consumes_baseline_only"],
        "candidate_shadow_hash_differs_from_executor": candidate_shadow_hash_differs_from_executor,
        "candidate_plan_referenced_by_executor": executor_readback.get("candidate_plan_referenced_by_executor"),
        "candidate_artifacts_under_proof_artifacts_only": gates["candidate_artifacts_under_proof_artifacts_only"],
        "ran_supervisor": False,
        "timer_path_invoked": False,
        "remote_execution_performed": False,
        "remote_control_plane_readback_performed": False,
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
        "deployed_hook": False,
        "loaded_hook": False,
        "target_plan_replaced": False,
        "executor_input_changed": False,
        "eligible_for_timer_path_load": False,
        "eligible_for_live_order_submission": False,
        "eligible_for_stage_governance_change": False,
        "proof_root": str(proof_root),
        "gates": gates,
        "blockers": blockers,
        "output_files": {
            "summary": str(output_root / "summary.json"),
            "owner_decision_record": str(output_root / "owner_decision_record.json"),
            "dry_load_manifest": str(proof_root / "dry_load_manifest.json"),
            "dry_load_readback": str(proof_root / "dry_load_readback.json"),
            "control_plane_readback": str(proof_root / "control_plane_readback.json"),
            "report": str(output_root / "p9j_proof_artifacts_dry_load_readback.md"),
        },
    }
    write_json(output_root / "owner_decision_record.json", owner_decision_record)
    write_json(output_root / "summary.json", summary)
    (output_root / "p9j_proof_artifacts_dry_load_readback.md").write_text(
        render_markdown(summary),
        encoding="utf-8",
    )
    return summary, 0 if status == "ready" else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9J Proof-Artifacts Dry-Load Readback",
        "",
        f"`Status: {summary['status']}`",
        "",
        "## Boundary",
        "",
        "This is a proof_artifacts dry-load readback only. It does not load the live timer path.",
        "",
        "```text",
        "dry_load_readback_scope = owner_gated_proof_artifacts_dry_load_readback_only",
        f"proof_artifacts_dry_load_readback_ready = {str(bool(summary['proof_artifacts_dry_load_readback_ready'])).lower()}",
        "dry_load_mode = proof_artifacts_readback_only_not_timer_path",
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
    summary, exit_code = build_phase9j(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
