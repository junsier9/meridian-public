from __future__ import annotations

import argparse
import hashlib
import json
import shutil
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


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9e_owner_gated_timer_adjacent_fixture.v1"
APPROVE_P9E_DECISION = "approve_p9e_timer_adjacent_local_fixture_only"
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_coinglass_candidate/"
    "phase9e_owner_gated_timer_adjacent_fixture"
)
PHASE9D_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_coinglass_candidate/"
    "phase9d_default_off_observe_only_hook"
)
HOOK_MODULE = "src/enhengclaw/live_trading/dth60_observe_only_shadow_hook.py"
SUPERVISOR_PATH = "src/enhengclaw/live_trading/mainnet_live_supervisor.py"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the P9E owner-gated timer-adjacent local fixture. The fixture "
            "copies supervisor context and runs the observe-only hook against "
            "the copy only; it never invokes the live supervisor timer path, "
            "deploys hook config, mutates executor input, or authorizes orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--phase9d-summary", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9E_DECISION)
    parser.add_argument("--owner-decision-source", default="user_chat:execute_owner_gated_p9e")
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


def path_under(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def source_path_from_evidence(evidence: dict[str, Any], key: str) -> Path:
    item = dict(evidence.get(key) or {})
    return resolve_path(str(item.get("path") or ""))


def phase9d_ready(p9d: dict[str, Any], *, current_hook_sha256: str) -> bool:
    hook = dict(p9d.get("hook_module") or {})
    return (
        p9d.get("status") == "ready"
        and not p9d.get("blockers")
        and p9d.get("implementation_scope") == "default_off_observe_only_hook_contract_only"
        and p9d.get("p9c_owner_decision_approved") is True
        and p9d.get("default_off_hook_enabled") is False
        and p9d.get("hook_deployment_authorized") is False
        and p9d.get("timer_path_load_authorized") is False
        and p9d.get("live_order_submission_authorized") is False
        and p9d.get("target_plan_replacement_authorized") is False
        and p9d.get("executor_input_mutation_authorized") is False
        and p9d.get("disabled_hook_baseline_output_unchanged") is True
        and int(p9d.get("disabled_hook_candidate_artifacts_written_count") or 0) == 0
        and p9d.get("enabled_fixture_execution_target_unchanged") is True
        and p9d.get("enabled_fixture_candidate_artifacts_under_proof_artifacts_only") is True
        and p9d.get("candidate_plan_referenced_by_executor") is False
        and p9d.get("live_supervisor_loads_candidate_hook") is False
        and p9d.get("eligible_for_timer_path_load") is False
        and p9d.get("eligible_for_live_order_submission") is False
        and p9d.get("deployed_hook") is False
        and hook.get("sha256") == current_hook_sha256
    )


def build_phase9e(
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
    output_root.mkdir(parents=True, exist_ok=True)

    paths = {
        "phase9d": (
            resolve_path(args.phase9d_summary)
            if str(getattr(args, "phase9d_summary", "") or "").strip()
            else latest_match(PHASE9D_PARENT, "*/summary.json")
        ),
        "hook_module": resolve_path(HOOK_MODULE),
        "supervisor": resolve_path(SUPERVISOR_PATH),
    }
    p9d = load_optional(paths["phase9d"])
    current_hook_sha = file_sha256(paths["hook_module"]) if paths["hook_module"].exists() else ""
    supervisor_text = paths["supervisor"].read_text(encoding="utf-8") if paths["supervisor"].exists() else ""
    live_supervisor_loads_candidate_hook = "dth60_observe_only_shadow_hook" in supervisor_text
    source_evidence = dict(p9d.get("source_evidence") or {})
    baseline_source = source_path_from_evidence(source_evidence, "baseline_source")
    candidate_source = source_path_from_evidence(source_evidence, "candidate_source")
    target_plan_diff = source_path_from_evidence(source_evidence, "target_plan_diff")
    shared_input_context = source_path_from_evidence(source_evidence, "shared_input_context")

    owner_decision_record = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9e_owner_decision.v1",
        "owner": str(args.owner),
        "decision": str(args.owner_decision),
        "decision_source": str(args.owner_decision_source),
        "recorded_at_utc": iso_z(started_at),
        "decision_effect": (
            "authorize_p9e_timer_adjacent_local_fixture_only"
            if str(args.owner_decision) == APPROVE_P9E_DECISION
            else "none"
        ),
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

    blockers: list[str] = []
    if str(args.owner_decision) != APPROVE_P9E_DECISION:
        blockers.append("owner_decision_not_p9e_timer_adjacent_fixture_only")
    if not phase9d_ready(p9d, current_hook_sha256=current_hook_sha):
        blockers.append("phase9d_not_ready_for_p9e")
    if live_supervisor_loads_candidate_hook:
        blockers.append("live_supervisor_already_loads_candidate_hook")
    if not baseline_source.exists():
        blockers.append("baseline_source_missing")
    if not candidate_source.exists():
        blockers.append("candidate_source_missing")

    timer_context_root = output_root / "copied_timer_context"
    baseline_copy = timer_context_root / "baseline_target_plan.json"
    executor_copy = timer_context_root / "executor_input" / "target_plan.json"
    candidate_copy = timer_context_root / "candidate_shadow_source.json"
    if not blockers:
        baseline_copy.parent.mkdir(parents=True, exist_ok=True)
        executor_copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(baseline_source, baseline_copy)
        shutil.copyfile(baseline_source, executor_copy)
        shutil.copyfile(candidate_source, candidate_copy)
        if target_plan_diff.exists():
            proof_diff = output_root / "proof_artifacts" / "p9e" / run_id / "shadow_hook" / "paired_plan_diff.csv"
            proof_diff.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(target_plan_diff, proof_diff)

    timer_context_snapshot = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "context_kind": "copied_timer_adjacent_fixture_context",
        "live_supervisor_invoked": False,
        "timer_path_invoked": False,
        "source_phase9d": evidence_file(paths["phase9d"]),
        "source_baseline_plan": evidence_file(baseline_source),
        "source_candidate_plan": evidence_file(candidate_source),
        "source_target_plan_diff": evidence_file(target_plan_diff),
        "source_shared_input_context": evidence_file(shared_input_context),
        "baseline_target_plan_copy": evidence_file(baseline_copy),
        "executor_input_plan_copy": evidence_file(executor_copy),
        "candidate_shadow_source_copy": evidence_file(candidate_copy),
    }
    write_json(output_root / "copied_timer_context_snapshot.json", timer_context_snapshot)

    hook_summary: dict[str, Any] = {}
    if not blockers:
        hook_summary = run_observe_only_shadow_hook(
            config=ObserveOnlyShadowHookConfig(
                enabled=True,
                output_root=output_root / "proof_artifacts" / "p9e" / run_id,
            ),
            baseline_target_plan_path=baseline_copy,
            executor_input_plan_path=executor_copy,
            candidate_shadow_plan_path=candidate_copy,
            supervisor_context=timer_context_snapshot,
            run_id=f"{run_id}-timer-adjacent-fixture",
            now=started_at,
        )
        write_json(output_root / "timer_adjacent_hook_summary.json", hook_summary)

    executor_before_hash = file_sha256(executor_copy) if executor_copy.exists() else ""
    executor_after_hash = str(hook_summary.get("executor_input_plan_sha256_after_hook") or executor_before_hash)
    baseline_hash = file_sha256(baseline_copy) if baseline_copy.exists() else ""
    candidate_artifact_paths = [Path(path) for path in list(hook_summary.get("candidate_artifact_paths") or [])]
    fixture_gates = {
        "owner_decision_p9e_fixture_only": str(args.owner_decision) == APPROVE_P9E_DECISION,
        "phase9d_ready": phase9d_ready(p9d, current_hook_sha256=current_hook_sha),
        "hook_module_hash_matches_p9d": current_hook_sha == dict(p9d.get("hook_module") or {}).get("sha256"),
        "copied_timer_context_used": timer_context_snapshot["context_kind"] == "copied_timer_adjacent_fixture_context",
        "live_supervisor_not_invoked": True,
        "timer_path_not_invoked": True,
        "live_supervisor_not_loading_candidate_hook": not live_supervisor_loads_candidate_hook,
        "hook_enabled_only_inside_fixture": hook_summary.get("hook_enabled") is True,
        "executor_input_hash_equals_baseline_before_hook": executor_before_hash == baseline_hash and bool(baseline_hash),
        "executor_input_hash_equals_baseline_after_hook": executor_after_hash == baseline_hash and bool(baseline_hash),
        "executor_consumes_baseline_only": hook_summary.get("executor_consumes_baseline_only") is True,
        "candidate_artifacts_under_proof_artifacts_only": hook_summary.get("candidate_artifacts_under_proof_artifacts_only") is True,
        "candidate_plan_not_referenced_by_executor": hook_summary.get("candidate_plan_referenced_by_executor") is False,
        "candidate_artifacts_under_output_proof_root": bool(candidate_artifact_paths)
        and all(path_under(path, output_root / "proof_artifacts") for path in candidate_artifact_paths),
        "zero_orders_fills": int(hook_summary.get("orders_submitted") or 0) == 0
        and int(hook_summary.get("fill_count") or 0) == 0,
        "live_config_not_changed": True,
        "operator_state_not_changed": True,
        "timer_state_not_changed": True,
        "hook_not_deployed": True,
    }
    blockers.extend(key for key, value in fixture_gates.items() if not value)
    blockers = sorted(set(blockers))
    status = "ready" if not blockers else "blocked"

    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "owner_decision": owner_decision_record,
        "fixture_scope": "owner_gated_timer_adjacent_local_fixture_only",
        "source_evidence": {
            "phase9d_summary": evidence_file(paths["phase9d"]),
            "hook_module": evidence_file(paths["hook_module"]),
            "live_supervisor": evidence_file(paths["supervisor"]),
            "baseline_source": evidence_file(baseline_source),
            "candidate_source": evidence_file(candidate_source),
            "target_plan_diff": evidence_file(target_plan_diff),
            "shared_input_context": evidence_file(shared_input_context),
        },
        "copied_timer_context_snapshot": timer_context_snapshot,
        "hook_summary": hook_summary,
        "hook_enabled_inside_fixture": hook_summary.get("hook_enabled") is True,
        "default_live_hook_enabled": False,
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
        "executor_input_plan_sha256_before_hook": executor_before_hash,
        "executor_input_plan_sha256_after_hook": executor_after_hash,
        "baseline_target_plan_sha256": baseline_hash,
        "candidate_shadow_plan_sha256": hook_summary.get("candidate_shadow_plan_sha256", ""),
        "executor_consumes_baseline_only": hook_summary.get("executor_consumes_baseline_only") is True,
        "candidate_plan_referenced_by_executor": hook_summary.get("candidate_plan_referenced_by_executor"),
        "candidate_artifacts_under_proof_artifacts_only": hook_summary.get("candidate_artifacts_under_proof_artifacts_only"),
        "live_supervisor_loads_candidate_hook": live_supervisor_loads_candidate_hook,
        "ran_supervisor": False,
        "timer_path_invoked": False,
        "orders_submitted": 0,
        "fill_count": 0,
        "fills_observed": 0,
        "mainnet_order_submission_authorized": False,
        "exchange_order_submission": "disabled",
        "applied_to_live": False,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "wrote_live_hook_config": False,
        "deployed_hook": False,
        "eligible_for_timer_path_load": False,
        "eligible_for_live_order_submission": False,
        "next_step_if_approved_later": "owner_gated_P9F_remote_proof_artifacts_wrapper_or_timer_hook_review",
        "fixture_gates": fixture_gates,
        "blockers": blockers,
        "output_files": {
            "summary": str(output_root / "summary.json"),
            "owner_decision_record": str(output_root / "owner_decision_record.json"),
            "copied_timer_context_snapshot": str(output_root / "copied_timer_context_snapshot.json"),
            "timer_adjacent_hook_summary": str(output_root / "timer_adjacent_hook_summary.json"),
            "report": str(output_root / "p9e_owner_gated_timer_adjacent_fixture.md"),
        },
    }
    write_json(output_root / "summary.json", summary)
    (output_root / "p9e_owner_gated_timer_adjacent_fixture.md").write_text(render_markdown(summary), encoding="utf-8")
    return summary, 0 if status == "ready" else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9E Owner-Gated Timer-Adjacent Fixture",
        "",
        f"`Status: {summary['status']}`",
        "",
        "## Boundary",
        "",
        "This is a copied-context timer-adjacent local fixture. It does not invoke the live supervisor timer path.",
        "",
        "```text",
        "fixture_scope = owner_gated_timer_adjacent_local_fixture_only",
        f"hook_enabled_inside_fixture = {str(summary['hook_enabled_inside_fixture']).lower()}",
        "default_live_hook_enabled = false",
        "hook_deployment_authorized = false",
        "timer_path_load_authorized = false",
        "live_order_submission_authorized = false",
        "target_plan_replacement_authorized = false",
        "executor_input_mutation_authorized = false",
        "execution_target_source = baseline_only",
        "orders_submitted = 0",
        "fill_count = 0",
        "```",
        "",
        "## Gates",
        "",
        "```text",
    ]
    for key, value in dict(summary.get("fixture_gates") or {}).items():
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
    summary, exit_code = build_phase9e(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
