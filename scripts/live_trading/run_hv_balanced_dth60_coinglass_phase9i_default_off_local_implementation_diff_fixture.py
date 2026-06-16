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


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9i_default_off_local_implementation_diff_fixture.v1"
APPROVE_P9I_DECISION = "approve_p9i_default_off_local_implementation_diff_fixture_only"
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_p9i_diff_fixture"
)
PHASE9H_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_coinglass_candidate/"
    "phase9h_timer_hook_implementation_load_proposal"
)
PROJECT_PROFILE = "config/project_governance/project_profile.json"
HOOK_MODULE = "src/enhengclaw/live_trading/dth60_observe_only_shadow_hook.py"
SUPERVISOR_PATH = "src/enhengclaw/live_trading/mainnet_live_supervisor.py"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the P9I default-off local implementation diff fixture. This "
            "writes a fixture-only proposed diff and proves disabled parity plus "
            "enabled shadow-artifact-only behavior. It does not modify the live "
            "supervisor, deploy or load a hook, run the supervisor, invoke the "
            "timer path, mutate executor input, or authorize orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9h-summary", default="")
    parser.add_argument("--hook-module", default=HOOK_MODULE)
    parser.add_argument("--supervisor", default=SUPERVISOR_PATH)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9I_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:approve_enter_p9i_default_off_local_implementation_diff_fixture",
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


def p9h_ready(summary: dict[str, Any], *, current_hook_sha256: str, current_supervisor_sha256: str) -> bool:
    gates = dict(summary.get("gates") or {})
    source_evidence = dict(summary.get("source_evidence") or {})
    source_hook = dict(source_evidence.get("hook_module") or {})
    source_supervisor = dict(source_evidence.get("live_supervisor") or {})
    owner = dict(summary.get("owner_decision") or {})
    required_gates = (
        "owner_decision_p9h_proposal_only",
        "project_stage_boundary_preserved",
        "p9g_timer_hook_review_pack_ready",
        "current_live_supervisor_not_loading_hook",
        "current_hook_hash_matches_p9g_source",
        "proposal_output_under_proof_artifacts",
        "proposal_default_off_required",
        "proposal_timer_load_mode_is_not_live_timer_path",
        "proposal_executor_input_source_baseline_only",
        "proposal_candidate_order_authority_disabled",
        "proposal_artifact_sink_proof_artifacts_only",
        "future_implementation_gate_separate",
        "future_timer_load_gate_separate",
        "future_live_order_gate_separate",
        "no_hook_implementation_in_p9h",
        "no_hook_deployment_in_p9h",
        "no_timer_path_load_in_p9h",
        "no_supervisor_run_in_p9h",
        "no_remote_execution_in_p9h",
        "no_executor_input_mutation_in_p9h",
        "no_target_plan_replacement_in_p9h",
        "no_live_mutation_in_p9h",
        "zero_orders_fills_in_p9h",
    )
    return (
        summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("proposal_scope") == "owner_gated_timer_hook_implementation_load_proposal_only"
        and summary.get("implementation_load_proposal_ready") is True
        and summary.get("eligible_for_owner_implementation_load_review") is True
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
        and summary.get("proposed_timer_load_mode") == "proposal_only_not_loaded"
        and summary.get("live_supervisor_loads_candidate_hook") is False
        and summary.get("implemented_hook") is False
        and summary.get("deployed_hook") is False
        and summary.get("loaded_hook") is False
        and summary.get("ran_supervisor") is False
        and summary.get("timer_path_invoked") is False
        and summary.get("remote_execution_performed") is False
        and summary.get("eligible_for_timer_path_load") is False
        and summary.get("eligible_for_live_order_submission") is False
        and no_live_mutation(summary)
        and zero_orders_fills(summary)
        and owner.get("decision") == "approve_p9h_timer_hook_implementation_load_proposal_only"
        and owner.get("implementation_load_proposal_approved") is True
        and owner.get("timer_hook_implementation_approved") is False
        and owner.get("hook_deployment_approved") is False
        and owner.get("timer_path_load_approved") is False
        and owner.get("live_order_submission_approved") is False
        and source_hook.get("sha256") == current_hook_sha256
        and source_supervisor.get("sha256") == current_supervisor_sha256
        and all(gates.get(key) is True for key in required_gates)
    )


def build_owner_decision_record(args: argparse.Namespace, started_at: datetime) -> dict[str, Any]:
    approved = str(args.owner_decision) == APPROVE_P9I_DECISION
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9i_owner_decision.v1",
        "owner": str(args.owner),
        "decision": str(args.owner_decision),
        "decision_source": str(args.owner_decision_source),
        "recorded_at_utc": iso_z(started_at),
        "decision_effect": (
            "authorize_p9i_default_off_local_implementation_diff_fixture_only"
            if approved
            else "none"
        ),
        "local_implementation_diff_fixture_approved": approved,
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


def fixture_plan_payload(kind: str) -> dict[str, Any]:
    if kind == "candidate":
        return {
            "plan_kind": "candidate_shadow_only",
            "positions": [
                {"symbol": "ETHUSDT", "target_weight": 0.08},
                {"symbol": "SOLUSDT", "target_weight": 0.04},
            ],
            "risk": {"max_gross": 0.3, "mode": "plan_only"},
        }
    return {
        "plan_kind": "baseline_executor_input",
        "positions": [
            {"symbol": "BTCUSDT", "target_weight": 0.08},
            {"symbol": "BNBUSDT", "target_weight": 0.04},
        ],
        "risk": {"max_gross": 0.3, "mode": "plan_only"},
    }


def build_diff_fixture(
    *,
    run_id: str,
    supervisor_path: Path,
    supervisor_sha256_before: str,
    hook_module_path: Path,
    hook_module_sha256: str,
) -> tuple[dict[str, Any], str]:
    diff_contract = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9i_diff_fixture_contract.v1",
        "run_id": run_id,
        "fixture_scope": "local_implementation_diff_fixture_only",
        "target_file": str(supervisor_path),
        "target_file_sha256_before_fixture": supervisor_sha256_before,
        "hook_module": {"path": str(hook_module_path), "sha256": hook_module_sha256},
        "diff_applied_to_live_supervisor": False,
        "default_off_required": True,
        "default_live_hook_enabled": False,
        "candidate_order_authority": "disabled",
        "candidate_live_order_submission_authorized": False,
        "execution_target_source": "baseline_only",
        "candidate_artifact_sink": "proof_artifacts_only",
        "proposed_insertion_point": "after_baseline_target_plan_materialized_before_executor_input_handoff",
        "proposed_behavior": [
            "freeze_read_only_supervisor_context",
            "run_candidate_hook_only_when_explicit_default_off_config_is_enabled_in_future_gate",
            "write_candidate_shadow_artifacts_under_proof_artifacts",
            "assert_executor_input_hash_equals_baseline_target_plan_hash",
            "never_pass_candidate_plan_to_delta_executor",
        ],
    }
    diff_text = "\n".join(
        [
            "# P9I fixture-only proposed diff - not applied",
            f"# target: {supervisor_path}",
            f"# target_sha256_before: {supervisor_sha256_before}",
            "--- src/enhengclaw/live_trading/mainnet_live_supervisor.py",
            "+++ <p9i_fixture>/mainnet_live_supervisor_with_default_off_shadow_hook.py",
            "@@ after baseline target plan materialization, before executor input handoff @@",
            "+# P9I proposal only: default-off observe-only shadow hook.",
            "+candidate_shadow_hook:",
            "+  enabled: false",
            "+  mode: observe_only",
            "+  artifact_sink: proof_artifacts_only",
            "+  candidate_order_authority: disabled",
            "+  candidate_live_order_submission_authorized: false",
            "+  execution_target_source: baseline_only",
            "+  candidate_overlay_execution_path: excluded",
            "+# Future implementation must preserve:",
            "+# executor_input_plan_sha256 == baseline_target_plan_sha256",
            "+# candidate_plan_referenced_by_executor == false",
            "+# orders_submitted == 0",
            "",
        ]
    )
    return diff_contract, diff_text


def build_phase9i(
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
    proof_root = output_root / "proof_artifacts" / "p9i" / run_id
    fixture_root = output_root / "fixture_workspace"
    proof_root.mkdir(parents=True, exist_ok=True)
    fixture_root.mkdir(parents=True, exist_ok=True)

    paths = {
        "project_profile": resolve_path(args.project_profile),
        "phase9h": (
            resolve_path(args.phase9h_summary)
            if str(getattr(args, "phase9h_summary", "") or "").strip()
            else latest_match(PHASE9H_PARENT, "*/summary.json")
        ),
        "hook_module": resolve_path(args.hook_module),
        "supervisor": resolve_path(args.supervisor),
    }
    project_profile = load_optional(paths["project_profile"])
    p9h = load_optional(paths["phase9h"])
    current_hook_sha = file_sha256(paths["hook_module"]) if paths["hook_module"].exists() else ""
    supervisor_sha_before = file_sha256(paths["supervisor"]) if paths["supervisor"].exists() else ""
    supervisor_text = paths["supervisor"].read_text(encoding="utf-8") if paths["supervisor"].exists() else ""
    live_supervisor_loads_hook_now = "dth60_observe_only_shadow_hook" in supervisor_text

    owner_decision_record = build_owner_decision_record(args, started_at)

    baseline_plan = fixture_root / "baseline_target_plan.json"
    executor_input_plan = fixture_root / "executor_input" / "target_plan.json"
    candidate_shadow_source = fixture_root / "candidate_shadow_source.json"
    write_json(baseline_plan, fixture_plan_payload("baseline"))
    write_json(executor_input_plan, fixture_plan_payload("baseline"))
    write_json(candidate_shadow_source, fixture_plan_payload("candidate"))

    diff_contract, diff_text = build_diff_fixture(
        run_id=run_id,
        supervisor_path=paths["supervisor"],
        supervisor_sha256_before=supervisor_sha_before,
        hook_module_path=paths["hook_module"],
        hook_module_sha256=current_hook_sha,
    )
    write_json(proof_root / "implementation_diff_fixture.json", diff_contract)
    (proof_root / "proposed_supervisor_hook_diff.patch").write_text(diff_text, encoding="utf-8")

    supervisor_context = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "context_kind": "p9i_local_implementation_diff_fixture_context",
        "generated_at_utc": iso_z(started_at),
        "phase9h_summary": evidence_file(paths["phase9h"]),
        "project_profile": evidence_file(paths["project_profile"]),
        "baseline_target_plan": evidence_file(baseline_plan),
        "executor_input_plan": evidence_file(executor_input_plan),
        "candidate_shadow_source": evidence_file(candidate_shadow_source),
        "implementation_diff_fixture": evidence_file(proof_root / "implementation_diff_fixture.json"),
        "proposed_supervisor_hook_diff": evidence_file(proof_root / "proposed_supervisor_hook_diff.patch"),
    }
    write_json(proof_root / "supervisor_context_snapshot.json", supervisor_context)

    disabled_summary = run_observe_only_shadow_hook(
        config=ObserveOnlyShadowHookConfig(enabled=False),
        baseline_target_plan_path=baseline_plan,
        executor_input_plan_path=executor_input_plan,
        candidate_shadow_plan_path=candidate_shadow_source,
        supervisor_context=supervisor_context,
        run_id=f"{run_id}-disabled",
        now=started_at,
    )
    enabled_summary = run_observe_only_shadow_hook(
        config=ObserveOnlyShadowHookConfig(
            enabled=True,
            output_root=proof_root,
        ),
        baseline_target_plan_path=baseline_plan,
        executor_input_plan_path=executor_input_plan,
        candidate_shadow_plan_path=candidate_shadow_source,
        supervisor_context=supervisor_context,
        run_id=f"{run_id}-enabled",
        now=started_at,
    )
    write_json(proof_root / "disabled_hook_summary.json", disabled_summary)
    write_json(proof_root / "enabled_hook_summary.json", enabled_summary)

    supervisor_sha_after = file_sha256(paths["supervisor"]) if paths["supervisor"].exists() else ""
    candidate_artifact_paths = [Path(path) for path in list(enabled_summary.get("candidate_artifact_paths") or [])]
    gates = {
        "owner_decision_p9i_fixture_only": str(args.owner_decision) == APPROVE_P9I_DECISION,
        "project_stage_boundary_preserved": project_profile.get("current_stage") == "stage_1_research_readiness_only",
        "p9h_proposal_ready": p9h_ready(
            p9h,
            current_hook_sha256=current_hook_sha,
            current_supervisor_sha256=supervisor_sha_before,
        ),
        "current_live_supervisor_not_loading_hook": not live_supervisor_loads_hook_now,
        "current_hook_hash_matches_p9h_source": (
            dict(dict(p9h.get("source_evidence") or {}).get("hook_module") or {}).get("sha256")
            == current_hook_sha
        ),
        "current_supervisor_hash_matches_p9h_source": (
            dict(dict(p9h.get("source_evidence") or {}).get("live_supervisor") or {}).get("sha256")
            == supervisor_sha_before
        ),
        "implementation_diff_fixture_written": (proof_root / "implementation_diff_fixture.json").exists(),
        "proposed_diff_patch_written": (proof_root / "proposed_supervisor_hook_diff.patch").exists(),
        "implementation_diff_fixture_not_applied_to_live_supervisor": supervisor_sha_before == supervisor_sha_after,
        "diff_fixture_default_off": diff_contract.get("default_live_hook_enabled") is False,
        "diff_fixture_order_authority_disabled": diff_contract.get("candidate_order_authority") == "disabled",
        "diff_fixture_executor_source_baseline_only": diff_contract.get("execution_target_source") == "baseline_only",
        "disabled_hook_ready": disabled_summary.get("status") == "ready",
        "disabled_hook_baseline_byte_for_byte_unchanged": (
            disabled_summary.get("baseline_target_plan_byte_for_byte_unchanged") is True
            and disabled_summary.get("executor_input_plan_hash_unchanged") is True
        ),
        "disabled_hook_writes_zero_candidate_artifacts": int(
            disabled_summary.get("candidate_artifacts_written_count") or 0
        )
        == 0,
        "enabled_hook_ready": enabled_summary.get("status") == "ready",
        "enabled_hook_writes_shadow_artifact_only": (
            int(enabled_summary.get("candidate_artifacts_written_count") or 0) > 0
            and enabled_summary.get("candidate_artifacts_under_proof_artifacts_only") is True
            and enabled_summary.get("candidate_plan_referenced_by_executor") is False
        ),
        "executor_input_hash_equals_baseline_target_hash": (
            enabled_summary.get("executor_input_plan_sha256_after_hook")
            == enabled_summary.get("baseline_target_plan_sha256_after_hook")
            and bool(enabled_summary.get("baseline_target_plan_sha256_after_hook"))
        ),
        "candidate_artifacts_under_output_proof_root": bool(candidate_artifact_paths)
        and all(path_under(path, proof_root) for path in candidate_artifact_paths),
        "candidate_order_authority_disabled": enabled_summary.get("candidate_order_authority") == "disabled",
        "candidate_live_order_submission_authorized_false": (
            enabled_summary.get("candidate_live_order_submission_authorized") is False
        ),
        "no_timer_path_load_in_p9i": True,
        "no_supervisor_run_in_p9i": True,
        "no_remote_execution_in_p9i": True,
        "no_executor_input_mutation_in_p9i": (
            enabled_summary.get("executor_input_plan_hash_unchanged") is True
        ),
        "no_target_plan_replacement_in_p9i": (
            enabled_summary.get("baseline_target_plan_byte_for_byte_unchanged") is True
        ),
        "no_live_mutation_in_p9i": True,
        "zero_orders_fills_in_p9i": (
            int(enabled_summary.get("orders_submitted") or 0) == 0
            and int(enabled_summary.get("fill_count") or 0) == 0
        ),
    }
    blockers = [key for key, value in gates.items() if not value]
    status = "ready" if not blockers else "blocked"

    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "fixture_scope": "owner_gated_default_off_local_implementation_diff_fixture_only",
        "owner_decision": owner_decision_record,
        "source_evidence": {
            "project_profile": evidence_file(paths["project_profile"]),
            "phase9h_summary": evidence_file(paths["phase9h"]),
            "hook_module": evidence_file(paths["hook_module"]),
            "live_supervisor": evidence_file(paths["supervisor"]),
        },
        "implementation_diff_fixture_ready": status == "ready",
        "eligible_for_owner_p9j_dry_load_review": status == "ready",
        "eligible_for_timer_hook_implementation": False,
        "timer_hook_implementation_authorized": False,
        "local_implementation_diff_fixture_authorized": str(args.owner_decision) == APPROVE_P9I_DECISION,
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
        "default_live_hook_enabled": False,
        "live_supervisor_loads_candidate_hook": live_supervisor_loads_hook_now,
        "implemented_hook_in_fixture": True,
        "implemented_hook_in_live_supervisor": False,
        "implementation_diff_fixture_applied_to_live_supervisor": False,
        "supervisor_sha256_before_fixture": supervisor_sha_before,
        "supervisor_sha256_after_fixture": supervisor_sha_after,
        "disabled_hook_summary": disabled_summary,
        "enabled_hook_summary": enabled_summary,
        "disabled_hook_baseline_byte_for_byte_unchanged": gates[
            "disabled_hook_baseline_byte_for_byte_unchanged"
        ],
        "disabled_hook_candidate_artifacts_written_count": int(
            disabled_summary.get("candidate_artifacts_written_count") or 0
        ),
        "enabled_hook_writes_shadow_artifact_only": gates["enabled_hook_writes_shadow_artifact_only"],
        "executor_input_hash_equals_baseline_target_hash": gates[
            "executor_input_hash_equals_baseline_target_hash"
        ],
        "candidate_artifacts_under_proof_artifacts_only": (
            enabled_summary.get("candidate_artifacts_under_proof_artifacts_only") is True
        ),
        "candidate_artifacts_under_output_proof_root": gates["candidate_artifacts_under_output_proof_root"],
        "candidate_plan_referenced_by_executor": enabled_summary.get("candidate_plan_referenced_by_executor"),
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
            "implementation_diff_fixture": str(proof_root / "implementation_diff_fixture.json"),
            "proposed_supervisor_hook_diff": str(proof_root / "proposed_supervisor_hook_diff.patch"),
            "disabled_hook_summary": str(proof_root / "disabled_hook_summary.json"),
            "enabled_hook_summary": str(proof_root / "enabled_hook_summary.json"),
            "report": str(output_root / "p9i_default_off_local_implementation_diff_fixture.md"),
        },
    }
    write_json(output_root / "owner_decision_record.json", owner_decision_record)
    write_json(output_root / "summary.json", summary)
    (output_root / "p9i_default_off_local_implementation_diff_fixture.md").write_text(
        render_markdown(summary),
        encoding="utf-8",
    )
    return summary, 0 if status == "ready" else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9I Default-Off Local Implementation Diff Fixture",
        "",
        f"`Status: {summary['status']}`",
        "",
        "## Boundary",
        "",
        "This is a local implementation diff fixture only. It does not modify the live supervisor.",
        "",
        "```text",
        "fixture_scope = owner_gated_default_off_local_implementation_diff_fixture_only",
        f"implementation_diff_fixture_ready = {str(bool(summary['implementation_diff_fixture_ready'])).lower()}",
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
    summary, exit_code = build_phase9i(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
