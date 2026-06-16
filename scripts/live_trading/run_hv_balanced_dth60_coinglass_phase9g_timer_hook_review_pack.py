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


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9g_timer_hook_review_pack.v1"
APPROVE_P9G_DECISION = "approve_p9g_timer_hook_review_pack_only"
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_coinglass_candidate/"
    "phase9g_timer_hook_review_pack"
)
PHASE9D_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_coinglass_candidate/"
    "phase9d_default_off_observe_only_hook"
)
PHASE9E_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_coinglass_candidate/"
    "phase9e_owner_gated_timer_adjacent_fixture"
)
PHASE9F_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_coinglass_candidate/"
    "phase9f_remote_proof_artifacts_wrapper"
)
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
            "Build a separate owner-gated P9G timer-hook review pack. This "
            "reads retained P9D/P9E/P9F/P9R evidence and current source files, "
            "then writes a proof-only review packet. It does not deploy the "
            "hook, load the timer path, run the supervisor, mutate executor "
            "input, or authorize orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9d-summary", default="")
    parser.add_argument("--phase9e-summary", default="")
    parser.add_argument("--phase9f-summary", default="")
    parser.add_argument("--phase9r-summary", default="")
    parser.add_argument("--hook-module", default=HOOK_MODULE)
    parser.add_argument("--supervisor", default=SUPERVISOR_PATH)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9G_DECISION)
    parser.add_argument("--owner-decision-source", default="user_chat:execute_owner_gated_p9g_timer_hook_review_pack")
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


def no_order(payload: dict[str, Any]) -> bool:
    return (
        int_zero(payload, "orders_submitted")
        and int_zero(payload, "fill_count")
        and int_zero(payload, "fills_observed")
        and payload.get("mainnet_order_submission_authorized") is False
        and payload.get("exchange_order_submission") == "disabled"
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
        and summary.get("candidate_scorer_mode") == "research_h10d_contract"
        and summary.get("candidate_scorer_mode_scope") == "proof_harness_only"
        and summary.get("candidate_scorer_loaded_into_live_wrapper") is False
        and summary.get("candidate_scorer_loaded_into_timer") is False
        and summary.get("candidate_scorer_loaded_into_executor") is False
        and row_parity_zero(summary)
        and int(target.get("mismatch_count") or 0) == 0
        and int(slices.get("mismatch_count") or 0) == 0
        and retained.get("status") == "ready"
        and int_zero(summary, "orders_submitted")
        and int_zero(summary, "fills_observed")
        and summary.get("applied_to_live") is False
        and summary.get("live_config_changed") is False
        and summary.get("operator_state_changed") is False
        and summary.get("live_supervisor_timer_loaded_candidate_overlay") is False
    )


def p9d_ready(summary: dict[str, Any], *, current_hook_sha256: str) -> bool:
    hook = dict(summary.get("hook_module") or {})
    return (
        summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("implementation_scope") == "default_off_observe_only_hook_contract_only"
        and summary.get("p9c_owner_decision_approved") is True
        and summary.get("default_off_hook_enabled") is False
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
        and summary.get("disabled_hook_baseline_output_unchanged") is True
        and int(summary.get("disabled_hook_candidate_artifacts_written_count") or 0) == 0
        and summary.get("enabled_fixture_execution_target_unchanged") is True
        and summary.get("enabled_fixture_candidate_artifacts_under_proof_artifacts_only") is True
        and summary.get("candidate_plan_referenced_by_executor") is False
        and summary.get("live_supervisor_loads_candidate_hook") is False
        and no_order(summary)
        and no_live_mutation(summary)
        and summary.get("ran_supervisor") is False
        and summary.get("timer_path_invoked") is False
        and summary.get("deployed_hook") is False
        and summary.get("eligible_for_timer_path_load") is False
        and summary.get("eligible_for_live_order_submission") is False
        and hook.get("sha256") == current_hook_sha256
    )


def p9e_ready(summary: dict[str, Any], *, current_hook_sha256: str) -> bool:
    owner = dict(summary.get("owner_decision") or {})
    hook = dict(dict(summary.get("source_evidence") or {}).get("hook_module") or {})
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
        and no_order(summary)
        and no_live_mutation(summary)
        and summary.get("deployed_hook") is False
        and summary.get("eligible_for_timer_path_load") is False
        and summary.get("eligible_for_live_order_submission") is False
        and hook.get("sha256") == current_hook_sha256
    )


def p9f_ready(summary: dict[str, Any], *, current_hook_sha256: str) -> bool:
    owner = dict(summary.get("owner_decision") or {})
    hook = dict(dict(summary.get("source_evidence") or {}).get("hook_module") or {})
    return (
        summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("wrapper_scope") == "owner_gated_remote_proof_artifacts_wrapper_only"
        and owner.get("decision") == "approve_p9f_remote_proof_artifacts_wrapper_only"
        and owner.get("remote_proof_artifacts_wrapper_approved") is True
        and owner.get("remote_execution_approved") is False
        and owner.get("hook_deployment_approved") is False
        and owner.get("timer_path_load_approved") is False
        and owner.get("live_order_submission_approved") is False
        and summary.get("p9e_ready") is True
        and summary.get("p9b_remote_wrapper_ready") is True
        and summary.get("remote_execution_performed") is False
        and summary.get("remote_proof_artifacts_semantics") is True
        and summary.get("uses_retained_remote_supervisor_artifacts") is True
        and summary.get("wrapper_output_under_proof_artifacts") is True
        and summary.get("executor_consumes_baseline_only") is True
        and summary.get("executor_input_plan_hash_equals_baseline") is True
        and summary.get("candidate_plan_referenced_by_executor") is False
        and summary.get("candidate_shadow_plan_generated") is False
        and summary.get("live_supervisor_loads_candidate_hook") is False
        and summary.get("ran_supervisor") is False
        and summary.get("timer_path_invoked") is False
        and summary.get("remote_control_plane_unchanged") is True
        and no_order(summary)
        and no_live_mutation(summary)
        and summary.get("deployed_hook") is False
        and summary.get("eligible_for_timer_path_load") is False
        and summary.get("eligible_for_live_order_submission") is False
        and hook.get("sha256") == current_hook_sha256
    )


def build_phase9g(
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
    proof_root = output_root / "proof_artifacts" / "p9g" / run_id
    proof_root.mkdir(parents=True, exist_ok=True)

    paths = {
        "project_profile": resolve_path(args.project_profile),
        "phase9d": (
            resolve_path(args.phase9d_summary)
            if str(getattr(args, "phase9d_summary", "") or "").strip()
            else latest_match(PHASE9D_PARENT, "*/summary.json")
        ),
        "phase9e": (
            resolve_path(args.phase9e_summary)
            if str(getattr(args, "phase9e_summary", "") or "").strip()
            else latest_match(PHASE9E_PARENT, "*/summary.json")
        ),
        "phase9f": (
            resolve_path(args.phase9f_summary)
            if str(getattr(args, "phase9f_summary", "") or "").strip()
            else latest_match(PHASE9F_PARENT, "*/summary.json")
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
    p9d = load_optional(paths["phase9d"])
    p9e = load_optional(paths["phase9e"])
    p9f = load_optional(paths["phase9f"])
    p9r = load_optional(paths["phase9r"])
    current_hook_sha = file_sha256(paths["hook_module"]) if paths["hook_module"].exists() else ""
    supervisor_text = paths["supervisor"].read_text(encoding="utf-8") if paths["supervisor"].exists() else ""
    live_supervisor_loads_hook_now = "dth60_observe_only_shadow_hook" in supervisor_text

    owner_decision_record = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9g_owner_decision.v1",
        "owner": str(args.owner),
        "decision": str(args.owner_decision),
        "decision_source": str(args.owner_decision_source),
        "recorded_at_utc": iso_z(started_at),
        "decision_effect": (
            "authorize_p9g_timer_hook_review_pack_only"
            if str(args.owner_decision) == APPROVE_P9G_DECISION
            else "none"
        ),
        "timer_hook_review_pack_approved": str(args.owner_decision) == APPROVE_P9G_DECISION,
        "timer_hook_implementation_approved": False,
        "hook_deployment_approved": False,
        "timer_path_load_approved": False,
        "live_order_submission_approved": False,
        "target_plan_replacement_approved": False,
        "executor_input_mutation_approved": False,
        "live_config_mutation_approved": False,
        "operator_state_mutation_approved": False,
        "timer_or_service_mutation_approved": False,
        "repo_stage_change_approved": False,
    }

    gates = {
        "owner_decision_p9g_review_pack_only": str(args.owner_decision) == APPROVE_P9G_DECISION,
        "project_stage_boundary_preserved": project_profile.get("current_stage") == "stage_1_research_readiness_only",
        "p9r_research_to_live_parity_ready": p9r_ready(p9r),
        "p9d_default_off_hook_ready": p9d_ready(p9d, current_hook_sha256=current_hook_sha),
        "p9e_timer_adjacent_fixture_ready": p9e_ready(p9e, current_hook_sha256=current_hook_sha),
        "p9f_remote_proof_wrapper_ready": p9f_ready(p9f, current_hook_sha256=current_hook_sha),
        "current_live_supervisor_not_loading_hook": not live_supervisor_loads_hook_now,
        "hook_module_hash_consistent": (
            dict(p9d.get("hook_module") or {}).get("sha256") == current_hook_sha
            and dict(dict(p9e.get("source_evidence") or {}).get("hook_module") or {}).get("sha256") == current_hook_sha
            and dict(dict(p9f.get("source_evidence") or {}).get("hook_module") or {}).get("sha256") == current_hook_sha
        ),
        "default_live_hook_disabled": (
            p9d.get("default_off_hook_enabled") is False
            and p9e.get("default_live_hook_enabled") is False
        ),
        "executor_baseline_only_all_proofs": (
            p9d.get("enabled_fixture_execution_target_unchanged") is True
            and p9e.get("executor_consumes_baseline_only") is True
            and p9f.get("executor_consumes_baseline_only") is True
        ),
        "candidate_plan_not_referenced_all_proofs": (
            p9d.get("candidate_plan_referenced_by_executor") is False
            and p9e.get("candidate_plan_referenced_by_executor") is False
            and p9f.get("candidate_plan_referenced_by_executor") is False
        ),
        "candidate_artifacts_proof_only_all_proofs": (
            p9d.get("enabled_fixture_candidate_artifacts_under_proof_artifacts_only") is True
            and p9e.get("candidate_artifacts_under_proof_artifacts_only") is True
            and p9f.get("candidate_artifact_sink") == "proof_artifacts_only"
            and output_under_proof_artifacts(proof_root)
        ),
        "no_timer_path_load_all_proofs": (
            p9d.get("timer_path_invoked") is False
            and p9e.get("timer_path_invoked") is False
            and p9f.get("timer_path_invoked") is False
            and p9d.get("eligible_for_timer_path_load") is False
            and p9e.get("eligible_for_timer_path_load") is False
            and p9f.get("eligible_for_timer_path_load") is False
        ),
        "no_live_mutation_all_proofs": (
            no_live_mutation(p9d)
            and no_live_mutation(p9e)
            and no_live_mutation(p9f)
            and p9r.get("applied_to_live") is False
            and p9r.get("live_config_changed") is False
            and p9r.get("operator_state_changed") is False
        ),
        "zero_orders_fills_all_proofs": (
            no_order(p9d)
            and no_order(p9e)
            and no_order(p9f)
            and int_zero(p9r, "orders_submitted")
            and int_zero(p9r, "fills_observed")
        ),
    }
    blockers = [key for key, value in gates.items() if not value]
    status = "ready" if not blockers else "blocked"

    review_packet = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "status": status,
        "review_pack_scope": "owner_gated_timer_hook_review_pack_only",
        "review_question": (
            "Do retained proof artifacts justify a later owner decision on a default-off "
            "timer-adjacent observe-only hook, while preserving baseline-only executor input?"
        ),
        "owner_decision": owner_decision_record,
        "source_summaries": {
            "phase9r": evidence_file(paths["phase9r"]),
            "phase9d": evidence_file(paths["phase9d"]),
            "phase9e": evidence_file(paths["phase9e"]),
            "phase9f": evidence_file(paths["phase9f"]),
        },
        "required_followup_decision_if_any": "separate_owner_gate_for_timer_hook_implementation_or_load",
        "not_authorized_by_this_pack": [
            "timer_hook_implementation",
            "hook_deployment",
            "timer_path_load",
            "target_plan_replacement",
            "executor_input_mutation",
            "live_config_mutation",
            "operator_state_mutation",
            "timer_or_service_mutation",
            "stage_governance_change",
            "live_order_submission",
        ],
        "gates": gates,
        "blockers": blockers,
    }
    write_json(proof_root / "timer_hook_review_packet.json", review_packet)
    write_json(output_root / "owner_decision_record.json", owner_decision_record)

    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "review_pack_scope": "owner_gated_timer_hook_review_pack_only",
        "owner_decision": owner_decision_record,
        "source_evidence": {
            "project_profile": evidence_file(paths["project_profile"]),
            "phase9r_summary": evidence_file(paths["phase9r"]),
            "phase9d_summary": evidence_file(paths["phase9d"]),
            "phase9e_summary": evidence_file(paths["phase9e"]),
            "phase9f_summary": evidence_file(paths["phase9f"]),
            "hook_module": evidence_file(paths["hook_module"]),
            "live_supervisor": evidence_file(paths["supervisor"]),
        },
        "timer_hook_review_pack_ready": status == "ready",
        "eligible_for_owner_timer_hook_review": status == "ready",
        "eligible_for_timer_hook_implementation": False,
        "timer_hook_implementation_authorized": False,
        "hook_deployment_authorized": False,
        "timer_path_load_authorized": False,
        "live_order_submission_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "candidate_order_authority": "disabled",
        "candidate_live_order_submission_authorized": False,
        "execution_target_source": "baseline_only",
        "candidate_overlay_execution_path": "excluded",
        "candidate_artifact_sink": "proof_artifacts_only",
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
        "deployed_hook": False,
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
            "timer_hook_review_packet": str(proof_root / "timer_hook_review_packet.json"),
            "report": str(output_root / "p9g_timer_hook_review_pack.md"),
        },
    }
    write_json(output_root / "summary.json", summary)
    (output_root / "p9g_timer_hook_review_pack.md").write_text(render_markdown(summary), encoding="utf-8")
    return summary, 0 if status == "ready" else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9G Timer-Hook Review Pack",
        "",
        f"`Status: {summary['status']}`",
        "",
        "## Boundary",
        "",
        "This is a separate owner-gated timer-hook review pack only.",
        "",
        "```text",
        "review_pack_scope = owner_gated_timer_hook_review_pack_only",
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
    summary, exit_code = build_phase9g(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
