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


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9f_remote_proof_artifacts_wrapper.v1"
APPROVE_P9F_DECISION = "approve_p9f_remote_proof_artifacts_wrapper_only"
APPROVE_P9E_DECISION = "approve_p9e_timer_adjacent_local_fixture_only"
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_coinglass_candidate/"
    "phase9f_remote_proof_artifacts_wrapper"
)
PHASE9E_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_coinglass_candidate/"
    "phase9e_owner_gated_timer_adjacent_fixture"
)
PHASE9B_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_coinglass_candidate/"
    "phase9b_remote_supervisor_artifact_wrapper"
)
HOOK_MODULE = "src/enhengclaw/live_trading/dth60_observe_only_shadow_hook.py"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run P9F as a separate owner-gated remote proof_artifacts wrapper. "
            "It reads retained P9B remote supervisor proof and retained P9E "
            "timer-adjacent fixture proof, then writes a new proof-only P9F "
            "gate. It does not SSH, run the supervisor, touch timers, deploy "
            "the hook, mutate executor input, or authorize orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--phase9e-summary", default="")
    parser.add_argument("--phase9b-summary", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9F_DECISION)
    parser.add_argument("--owner-decision-source", default="user_chat:execute_owner_gated_p9f")
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


def latest_recursive_summary(parent: str) -> Path:
    root = resolve_path(parent)
    matches = [path for path in root.glob("**/summary.json") if path.is_file()]
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


def path_has_marker(path_value: str, marker: str) -> bool:
    return marker.lower() in [part.lower() for part in Path(str(path_value or "")).parts]


def bool_field(payload: dict[str, Any], key: str, expected: bool) -> bool:
    return payload.get(key) is expected


def int_zero(payload: dict[str, Any], key: str) -> bool:
    return int(payload.get(key) or 0) == 0


def phase9e_ready(p9e: dict[str, Any], *, current_hook_sha256: str) -> bool:
    owner_decision = dict(p9e.get("owner_decision") or {})
    source_evidence = dict(p9e.get("source_evidence") or {})
    hook_evidence = dict(source_evidence.get("hook_module") or {})
    return (
        p9e.get("status") == "ready"
        and not p9e.get("blockers")
        and p9e.get("fixture_scope") == "owner_gated_timer_adjacent_local_fixture_only"
        and owner_decision.get("decision") == APPROVE_P9E_DECISION
        and owner_decision.get("decision_effect") == "authorize_p9e_timer_adjacent_local_fixture_only"
        and owner_decision.get("hook_deployment_approved") is False
        and owner_decision.get("timer_path_load_approved") is False
        and owner_decision.get("live_order_submission_approved") is False
        and owner_decision.get("target_plan_replacement_approved") is False
        and owner_decision.get("executor_input_mutation_approved") is False
        and owner_decision.get("live_config_mutation_approved") is False
        and owner_decision.get("operator_state_mutation_approved") is False
        and owner_decision.get("timer_or_service_mutation_approved") is False
        and owner_decision.get("repo_stage_change_approved") is False
        and p9e.get("hook_enabled_inside_fixture") is True
        and p9e.get("default_live_hook_enabled") is False
        and p9e.get("hook_deployment_authorized") is False
        and p9e.get("timer_path_load_authorized") is False
        and p9e.get("live_order_submission_authorized") is False
        and p9e.get("target_plan_replacement_authorized") is False
        and p9e.get("executor_input_mutation_authorized") is False
        and p9e.get("candidate_order_authority") == "disabled"
        and p9e.get("candidate_live_order_submission_authorized") is False
        and p9e.get("execution_target_source") == "baseline_only"
        and p9e.get("candidate_overlay_execution_path") == "excluded"
        and p9e.get("candidate_artifact_sink") == "proof_artifacts_only"
        and p9e.get("executor_consumes_baseline_only") is True
        and p9e.get("candidate_plan_referenced_by_executor") is False
        and p9e.get("candidate_artifacts_under_proof_artifacts_only") is True
        and p9e.get("live_supervisor_loads_candidate_hook") is False
        and p9e.get("ran_supervisor") is False
        and p9e.get("timer_path_invoked") is False
        and int_zero(p9e, "orders_submitted")
        and int_zero(p9e, "fill_count")
        and int_zero(p9e, "fills_observed")
        and p9e.get("mainnet_order_submission_authorized") is False
        and p9e.get("exchange_order_submission") == "disabled"
        and p9e.get("applied_to_live") is False
        and p9e.get("live_config_changed") is False
        and p9e.get("operator_state_changed") is False
        and p9e.get("timer_state_changed") is False
        and p9e.get("wrote_live_hook_config") is False
        and p9e.get("deployed_hook") is False
        and p9e.get("eligible_for_timer_path_load") is False
        and p9e.get("eligible_for_live_order_submission") is False
        and hook_evidence.get("sha256") == current_hook_sha256
    )


def phase9b_ready(p9b: dict[str, Any]) -> bool:
    control = dict(p9b.get("control_plane") or {})
    gates = dict(p9b.get("gates") or {})
    return (
        p9b.get("status") == "ready"
        and not p9b.get("blockers")
        and p9b.get("executor_consumes_baseline_only") is True
        and p9b.get("executor_input_plan_hash_equals_baseline") is True
        and p9b.get("candidate_plan_referenced_by_executor") is False
        and p9b.get("candidate_shadow_plan_generated") is False
        and p9b.get("candidate_order_authority") == "disabled"
        and p9b.get("candidate_live_order_submission_authorized") is False
        and p9b.get("execution_target_source") == "baseline_only"
        and p9b.get("candidate_artifact_sink") == "proof_artifacts_only"
        and p9b.get("wrapper_output_under_proof_artifacts") is True
        and p9b.get("ran_supervisor") is False
        and p9b.get("timer_path_invoked") is False
        and p9b.get("read_only_supervisor_artifacts") is True
        and int_zero(p9b, "candidate_orders_submitted")
        and int_zero(p9b, "candidate_fill_count")
        and int_zero(p9b, "orders_submitted")
        and int_zero(p9b, "fill_count")
        and p9b.get("mainnet_order_submission_authorized") is False
        and p9b.get("applied_to_live") is False
        and p9b.get("live_config_changed") is False
        and p9b.get("operator_state_changed") is False
        and p9b.get("timer_state_changed") is False
        and p9b.get("exchange_order_submission") == "disabled"
        and p9b.get("eligible_for_live_order_submission") is False
        and control.get("checked") is True
        and control.get("unchanged") is True
        and gates.get("executor_input_plan_hash_equals_baseline") is True
        and gates.get("candidate_plan_not_referenced_by_executor") is True
        and gates.get("wrapper_output_under_proof_artifacts") is True
        and gates.get("control_plane_unchanged") is True
    )


def build_phase9f(
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
    proof_root = output_root / "proof_artifacts" / "p9f" / run_id
    output_root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    paths = {
        "phase9e": (
            resolve_path(args.phase9e_summary)
            if str(getattr(args, "phase9e_summary", "") or "").strip()
            else latest_match(PHASE9E_PARENT, "*/summary.json")
        ),
        "phase9b": (
            resolve_path(args.phase9b_summary)
            if str(getattr(args, "phase9b_summary", "") or "").strip()
            else latest_recursive_summary(PHASE9B_PARENT)
        ),
        "hook_module": resolve_path(HOOK_MODULE),
    }
    p9e = load_optional(paths["phase9e"])
    p9b = load_optional(paths["phase9b"])
    current_hook_sha = file_sha256(paths["hook_module"]) if paths["hook_module"].exists() else ""

    owner_decision_record = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9f_owner_decision.v1",
        "owner": str(args.owner),
        "decision": str(args.owner_decision),
        "decision_source": str(args.owner_decision_source),
        "recorded_at_utc": iso_z(started_at),
        "decision_effect": (
            "authorize_p9f_remote_proof_artifacts_wrapper_only"
            if str(args.owner_decision) == APPROVE_P9F_DECISION
            else "none"
        ),
        "remote_proof_artifacts_wrapper_approved": str(args.owner_decision) == APPROVE_P9F_DECISION,
        "remote_execution_approved": False,
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
    write_json(output_root / "owner_decision_record.json", owner_decision_record)

    p9e_is_ready = phase9e_ready(p9e, current_hook_sha256=current_hook_sha)
    p9b_is_ready = phase9b_ready(p9b)
    p9f_output_under_proof_artifacts = output_under_proof_artifacts(proof_root)
    p9b_output_root = str(p9b.get("output_root") or "")
    p9b_remote_proof_artifacts_semantics = (
        p9b.get("wrapper_output_under_proof_artifacts") is True
        and path_has_marker(p9b_output_root, "proof_artifacts")
        and p9b.get("read_only_supervisor_artifacts") is True
    )
    owner_approved = str(args.owner_decision) == APPROVE_P9F_DECISION

    gates = {
        "owner_decision_p9f_wrapper_only": owner_approved,
        "phase9e_ready": p9e_is_ready,
        "phase9b_remote_wrapper_ready": p9b_is_ready,
        "hook_module_hash_matches_p9e": dict(dict(p9e.get("source_evidence") or {}).get("hook_module") or {}).get(
            "sha256"
        )
        == current_hook_sha,
        "p9f_output_under_proof_artifacts": p9f_output_under_proof_artifacts,
        "p9b_remote_proof_artifacts_semantics": p9b_remote_proof_artifacts_semantics,
        "p9b_executor_consumes_baseline_only": bool_field(p9b, "executor_consumes_baseline_only", True),
        "p9b_executor_input_plan_hash_equals_baseline": bool_field(
            p9b, "executor_input_plan_hash_equals_baseline", True
        ),
        "p9b_candidate_plan_not_referenced_by_executor": bool_field(
            p9b, "candidate_plan_referenced_by_executor", False
        ),
        "p9b_candidate_shadow_plan_not_generated": bool_field(p9b, "candidate_shadow_plan_generated", False),
        "p9b_ran_supervisor_false": bool_field(p9b, "ran_supervisor", False),
        "p9b_timer_path_not_invoked": bool_field(p9b, "timer_path_invoked", False),
        "p9b_control_plane_unchanged": dict(p9b.get("control_plane") or {}).get("unchanged") is True,
        "p9e_live_supervisor_not_loading_candidate_hook": bool_field(
            p9e, "live_supervisor_loads_candidate_hook", False
        ),
        "p9e_not_eligible_for_timer_path_load": bool_field(p9e, "eligible_for_timer_path_load", False),
        "zero_orders_fills": (
            int_zero(p9e, "orders_submitted")
            and int_zero(p9e, "fill_count")
            and int_zero(p9b, "orders_submitted")
            and int_zero(p9b, "fill_count")
            and int_zero(p9b, "candidate_orders_submitted")
            and int_zero(p9b, "candidate_fill_count")
        ),
        "live_config_not_changed": bool_field(p9e, "live_config_changed", False)
        and bool_field(p9b, "live_config_changed", False),
        "operator_state_not_changed": bool_field(p9e, "operator_state_changed", False)
        and bool_field(p9b, "operator_state_changed", False),
        "timer_state_not_changed": bool_field(p9e, "timer_state_changed", False)
        and bool_field(p9b, "timer_state_changed", False),
        "hook_not_deployed": bool_field(p9e, "deployed_hook", False),
    }
    blockers: list[str] = []
    if not owner_approved:
        blockers.append("owner_decision_not_p9f_remote_proof_artifacts_wrapper_only")
    if not p9e_is_ready:
        blockers.append("phase9e_not_ready_for_p9f")
    if not p9b_is_ready:
        blockers.append("phase9b_not_ready_for_p9f")
    blockers.extend(key for key, value in gates.items() if not value)
    blockers = sorted(set(str(item) for item in blockers if str(item).strip()))
    status = "ready" if not blockers else "blocked"

    remote_manifest = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "status": status,
        "manifest_kind": "retained_remote_proof_artifacts_wrapper_readback",
        "remote_execution_performed": False,
        "uses_retained_remote_supervisor_artifacts": True,
        "source_phase9b_summary": evidence_file(paths["phase9b"]),
        "source_phase9b_run_id": p9b.get("run_id"),
        "source_phase9b_output_root": p9b.get("output_root", ""),
        "source_remote_supervisor_run_id": dict(p9b.get("supervisor") or {}).get("run_id", ""),
        "source_remote_supervisor_status": dict(p9b.get("supervisor") or {}).get("status", ""),
        "source_remote_plan_artifact_root": dict(p9b.get("source_evidence") or {}).get("plan_artifact_root", ""),
        "remote_proof_artifacts_semantics": p9b_remote_proof_artifacts_semantics,
        "read_only_supervisor_artifacts": p9b.get("read_only_supervisor_artifacts") is True,
        "remote_control_plane_unchanged": dict(p9b.get("control_plane") or {}).get("unchanged") is True,
        "remote_ran_supervisor": p9b.get("ran_supervisor") is True,
        "remote_timer_path_invoked": p9b.get("timer_path_invoked") is True,
    }
    write_json(proof_root / "remote_proof_readback_manifest.json", remote_manifest)

    executor_readback = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "status": status,
        "execution_target_source": "baseline_only" if status == "ready" else "not_proven",
        "executor_consumes_baseline_only": p9b.get("executor_consumes_baseline_only") is True,
        "executor_input_plan_hash_equals_baseline": p9b.get("executor_input_plan_hash_equals_baseline") is True,
        "baseline_plan_hash": p9b.get("baseline_plan_hash", ""),
        "executor_source_manifest_plan_hash": p9b.get("executor_source_manifest_plan_hash", ""),
        "executor_input_reference_kind": p9b.get("executor_input_reference_kind", ""),
        "executor_input_reference_plan_root": p9b.get("executor_input_reference_plan_root", ""),
        "candidate_plan_referenced_by_executor": p9b.get("candidate_plan_referenced_by_executor") is True,
        "candidate_shadow_plan_generated": p9b.get("candidate_shadow_plan_generated") is True,
        "candidate_order_authority": "disabled",
        "candidate_live_order_submission_authorized": False,
        "eligible_for_live_order_submission": False,
    }
    write_json(proof_root / "executor_input_readback.json", executor_readback)

    candidate_manifest = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "status": status,
        "candidate_order_authority": "disabled",
        "candidate_live_order_submission_authorized": False,
        "candidate_artifact_sink": "proof_artifacts_only",
        "candidate_overlay_execution_path": "excluded",
        "candidate_shadow_plan_generated_in_p9f": False,
        "candidate_shadow_plan_generated_in_p9b": p9b.get("candidate_shadow_plan_generated") is True,
        "candidate_shadow_plan_sha256_from_p9e_fixture": p9e.get("candidate_shadow_plan_sha256", ""),
        "baseline_target_plan_sha256_from_p9e_fixture": p9e.get("baseline_target_plan_sha256", ""),
        "executor_input_plan_sha256_after_hook_from_p9e_fixture": p9e.get(
            "executor_input_plan_sha256_after_hook", ""
        ),
        "p9e_candidate_plan_referenced_by_executor": p9e.get("candidate_plan_referenced_by_executor") is True,
        "p9b_candidate_plan_referenced_by_executor": p9b.get("candidate_plan_referenced_by_executor") is True,
        "p9f_candidate_plan_referenced_by_executor": False,
        "candidate_artifacts_under_p9f_proof_artifacts": p9f_output_under_proof_artifacts,
    }
    write_json(proof_root / "candidate_readonly_manifest.json", candidate_manifest)

    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "owner_decision": owner_decision_record,
        "wrapper_scope": "owner_gated_remote_proof_artifacts_wrapper_only",
        "source_evidence": {
            "phase9e_summary": evidence_file(paths["phase9e"]),
            "phase9b_summary": evidence_file(paths["phase9b"]),
            "hook_module": evidence_file(paths["hook_module"]),
        },
        "p9e_ready": p9e_is_ready,
        "p9b_remote_wrapper_ready": p9b_is_ready,
        "remote_execution_performed": False,
        "remote_proof_artifacts_semantics": p9b_remote_proof_artifacts_semantics,
        "uses_retained_remote_supervisor_artifacts": True,
        "wrapper_output_under_proof_artifacts": p9f_output_under_proof_artifacts,
        "p9f_proof_root": str(proof_root),
        "candidate_order_authority": "disabled",
        "candidate_live_order_submission_authorized": False,
        "execution_target_source": "baseline_only" if status == "ready" else "not_proven",
        "candidate_overlay_execution_path": "excluded",
        "candidate_artifact_sink": "proof_artifacts_only",
        "candidate_shadow_plan_generated": False,
        "candidate_plan_referenced_by_executor": False if status == "ready" else p9b.get("candidate_plan_referenced_by_executor"),
        "executor_consumes_baseline_only": p9b.get("executor_consumes_baseline_only") is True and status == "ready",
        "executor_input_plan_hash_equals_baseline": p9b.get("executor_input_plan_hash_equals_baseline") is True,
        "baseline_plan_hash": p9b.get("baseline_plan_hash", ""),
        "p9e_baseline_target_plan_sha256": p9e.get("baseline_target_plan_sha256", ""),
        "p9e_executor_input_plan_sha256_after_hook": p9e.get("executor_input_plan_sha256_after_hook", ""),
        "p9e_candidate_shadow_plan_sha256": p9e.get("candidate_shadow_plan_sha256", ""),
        "live_supervisor_loads_candidate_hook": p9e.get("live_supervisor_loads_candidate_hook") is True,
        "ran_supervisor": False,
        "timer_path_invoked": False,
        "read_only_supervisor_artifacts": True,
        "remote_control_plane_unchanged": dict(p9b.get("control_plane") or {}).get("unchanged") is True,
        "hook_deployment_authorized": False,
        "timer_path_load_authorized": False,
        "live_order_submission_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "mainnet_order_submission_authorized": False,
        "orders_submitted": 0,
        "fill_count": 0,
        "fills_observed": 0,
        "candidate_orders_submitted": 0,
        "candidate_fill_count": 0,
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
        "eligible_for_timer_hook_review_pack_discussion": bool(status == "ready"),
        "gates": gates,
        "blockers": blockers,
        "output_files": {
            "summary": str(output_root / "summary.json"),
            "owner_decision_record": str(output_root / "owner_decision_record.json"),
            "remote_proof_readback_manifest": str(proof_root / "remote_proof_readback_manifest.json"),
            "executor_input_readback": str(proof_root / "executor_input_readback.json"),
            "candidate_readonly_manifest": str(proof_root / "candidate_readonly_manifest.json"),
            "report": str(output_root / "p9f_remote_proof_artifacts_wrapper.md"),
        },
    }
    write_json(output_root / "summary.json", summary)
    (output_root / "p9f_remote_proof_artifacts_wrapper.md").write_text(render_markdown(summary), encoding="utf-8")
    return summary, 0 if status == "ready" else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9F Remote Proof-Artifacts Wrapper",
        "",
        f"`Status: {summary['status']}`",
        "",
        "## Boundary",
        "",
        "P9F is a separate owner-gated remote proof_artifacts wrapper. It reads retained P9B/P9E proof only.",
        "",
        "```text",
        "wrapper_scope = owner_gated_remote_proof_artifacts_wrapper_only",
        "remote_execution_performed = false",
        "uses_retained_remote_supervisor_artifacts = true",
        "candidate_order_authority = disabled",
        "candidate_live_order_submission_authorized = false",
        "execution_target_source = baseline_only",
        "candidate_overlay_execution_path = excluded",
        "candidate_artifact_sink = proof_artifacts_only",
        "timer_path_load_authorized = false",
        "live_order_submission_authorized = false",
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
    summary, exit_code = build_phase9f(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
