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
    CONTRACT_VERSION as HOOK_CONTRACT_VERSION,
    ObserveOnlyShadowHookConfig,
    run_observe_only_shadow_hook,
)


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9d_default_off_observe_only_hook.v1"
APPROVE_P9C_IMPLEMENTATION_DECISION = "approve_p9c_observe_only_hook_implementation"
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_coinglass_candidate/"
    "phase9d_default_off_observe_only_hook"
)
PHASE9C_DECISION_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_coinglass_candidate/"
    "phase9c_owner_decision"
)
PHASE4_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_coinglass_candidate/"
    "phase4_paired_target_plan_shadow"
)
SUPERVISOR_PATH = "src/enhengclaw/live_trading/mainnet_live_supervisor.py"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Implement and prove the P9D default-off observe-only DTH60 hook "
            "contract. This writes local proof artifacts only; it does not "
            "deploy the hook, load timer path, mutate executor input, or "
            "authorize orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--phase9c-owner-decision-summary", default="")
    parser.add_argument("--phase4-summary", default="")
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


def source_file_from_phase4(phase4: dict[str, Any], key: str, phase4_root: Path, default_name: str) -> Path:
    output_files = dict(phase4.get("output_files") or {})
    value = str(output_files.get(key) or "").strip()
    return resolve_path(value) if value else phase4_root / default_name


def p9c_owner_decision_ready(decision: dict[str, Any]) -> bool:
    authorized = dict(decision.get("authorized_scope") or {})
    not_authorized = dict(decision.get("not_authorized") or {})
    scorer = dict(decision.get("scorer_reproduction_assessment") or {})
    return (
        decision.get("status") == "approved"
        and not decision.get("blockers")
        and decision.get("decision") == APPROVE_P9C_IMPLEMENTATION_DECISION
        and decision.get("decision_effect") == "authorize_default_off_observe_only_hook_implementation_only"
        and authorized.get("observe_only_hook_implementation") is True
        and authorized.get("default_off_required") is True
        and authorized.get("proof_artifacts_only_required") is True
        and authorized.get("executor_input_must_remain_baseline_only") is True
        and authorized.get("candidate_order_authority") == "disabled"
        and not_authorized.get("hook_deployment") is True
        and not_authorized.get("timer_path_load") is True
        and not_authorized.get("live_order_submission") is True
        and not_authorized.get("target_plan_replacement") is True
        and not_authorized.get("executor_input_mutation") is True
        and scorer.get("research_baseline_reproduced_in_p9r_harness") is True
        and scorer.get("candidate_scorer_loaded_into_timer") is False
        and scorer.get("candidate_scorer_loaded_into_executor") is False
    )


def phase4_ready(phase4: dict[str, Any]) -> bool:
    p2 = dict(phase4.get("phase2_pit_proof_checks") or {})
    p2b = dict(phase4.get("phase2b_pit_proof_checks") or {})
    p3 = dict(phase4.get("phase3_parity_proof_checks") or {})
    return (
        phase4.get("status") == "ready"
        and not phase4.get("blockers")
        and phase4.get("same_timestamp_context_proven") is True
        and phase4.get("same_risk_inputs_proven") is True
        and phase4.get("same_symbol_set_proven") is True
        and phase4.get("same_portfolio_engine_proven") is True
        and p3.get("overlay_enabled_only_target_contribution_changed") is True
        and all(p2.get(key) is True for key in ("no_future_fill_proven", "no_stale_fill_proven", "no_zero_fill_proven"))
        and all(p2b.get(key) is True for key in ("no_future_fill_proven", "no_stale_fill_proven", "no_zero_fill_proven"))
        and int(phase4.get("orders_submitted") or 0) == 0
        and int(phase4.get("fill_count") or 0) == 0
        and phase4.get("mainnet_order_submission_authorized") is False
        and phase4.get("applied_to_live") is False
        and phase4.get("live_config_changed") is False
        and phase4.get("operator_state_changed") is False
        and phase4.get("timer_state_changed") is False
    )


def build_phase9d(
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
        "phase9c_owner_decision": (
            resolve_path(args.phase9c_owner_decision_summary)
            if str(getattr(args, "phase9c_owner_decision_summary", "") or "").strip()
            else latest_match(PHASE9C_DECISION_PARENT, "*/summary.json")
        ),
        "phase4": (
            resolve_path(args.phase4_summary)
            if str(getattr(args, "phase4_summary", "") or "").strip()
            else latest_match(PHASE4_PARENT, "*/summary.json")
        ),
        "supervisor": resolve_path(SUPERVISOR_PATH),
    }
    owner_decision = load_optional(paths["phase9c_owner_decision"])
    phase4 = load_optional(paths["phase4"])
    phase4_root = paths["phase4"].parent if paths["phase4"] else Path("")
    baseline_source = source_file_from_phase4(phase4, "baseline_target_portfolio", phase4_root, "baseline_target_portfolio.json")
    candidate_source = source_file_from_phase4(phase4, "candidate_target_portfolio", phase4_root, "candidate_target_portfolio.json")
    target_plan_diff = source_file_from_phase4(phase4, "target_plan_diff", phase4_root, "target_plan_diff.csv")
    shared_context = source_file_from_phase4(phase4, "shared_input_context", phase4_root, "shared_input_context.json")

    fixture_root = output_root / "fixture_workspace"
    baseline_fixture = fixture_root / "baseline_target_plan.json"
    executor_fixture = fixture_root / "executor_input" / "target_plan.json"
    blockers: list[str] = []
    if not baseline_source.exists():
        blockers.append("baseline_source_missing")
    if not candidate_source.exists():
        blockers.append("candidate_source_missing")
    if not p9c_owner_decision_ready(owner_decision):
        blockers.append("p9c_owner_decision_not_ready")
    if not phase4_ready(phase4):
        blockers.append("phase4_not_ready")

    if not blockers:
        baseline_fixture.parent.mkdir(parents=True, exist_ok=True)
        executor_fixture.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(baseline_source, baseline_fixture)
        shutil.copyfile(baseline_source, executor_fixture)

    supervisor_context = {
        "phase": "P9D",
        "phase9c_owner_decision": evidence_file(paths["phase9c_owner_decision"]),
        "phase4_summary": evidence_file(paths["phase4"]),
        "phase4_run_id": phase4.get("run_id"),
        "phase4_generated_at_utc": phase4.get("generated_at_utc"),
        "baseline_source": evidence_file(baseline_source),
        "candidate_source": evidence_file(candidate_source),
        "target_plan_diff": evidence_file(target_plan_diff),
        "shared_input_context": evidence_file(shared_context),
    }

    disabled_summary: dict[str, Any] = {}
    enabled_summary: dict[str, Any] = {}
    if not blockers:
        disabled_summary = run_observe_only_shadow_hook(
            config=ObserveOnlyShadowHookConfig(enabled=False),
            baseline_target_plan_path=baseline_fixture,
            executor_input_plan_path=executor_fixture,
            candidate_shadow_plan_path=candidate_source,
            supervisor_context=supervisor_context,
            run_id=f"{run_id}-disabled",
            now=started_at,
        )
        enabled_summary = run_observe_only_shadow_hook(
            config=ObserveOnlyShadowHookConfig(
                enabled=True,
                output_root=output_root / "proof_artifacts" / "p9d" / run_id,
            ),
            baseline_target_plan_path=baseline_fixture,
            executor_input_plan_path=executor_fixture,
            candidate_shadow_plan_path=candidate_source,
            supervisor_context=supervisor_context,
            run_id=f"{run_id}-enabled",
            now=started_at,
        )
        write_json(output_root / "disabled_hook_summary.json", disabled_summary)
        write_json(output_root / "enabled_hook_summary.json", enabled_summary)
        if target_plan_diff.exists():
            proof_diff = output_root / "proof_artifacts" / "p9d" / run_id / "shadow_hook" / "paired_plan_diff.csv"
            proof_diff.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(target_plan_diff, proof_diff)

    supervisor_text = paths["supervisor"].read_text(encoding="utf-8") if paths["supervisor"].exists() else ""
    live_supervisor_loads_candidate_hook = "dth60_observe_only_shadow_hook" in supervisor_text
    default_off_contract = {
        "contract_version": HOOK_CONTRACT_VERSION,
        "enabled": False,
        "mode": "observe_only",
        "artifact_sink": "proof_artifacts_only",
        "candidate_order_authority": "disabled",
        "candidate_live_order_submission_authorized": False,
        "execution_target_source": "baseline_only",
        "candidate_overlay_execution_path": "excluded",
        "default_off_required": True,
        "not_loaded_by_live_supervisor_timer": not live_supervisor_loads_candidate_hook,
    }
    write_json(output_root / "default_off_hook_contract.json", default_off_contract)

    implementation_gates = {
        "p9c_owner_decision_ready": p9c_owner_decision_ready(owner_decision),
        "phase4_ready": phase4_ready(phase4),
        "hook_contract_default_enabled_false": default_off_contract["enabled"] is False,
        "hook_contract_order_authority_disabled": default_off_contract["candidate_order_authority"] == "disabled",
        "hook_contract_proof_artifacts_only": default_off_contract["artifact_sink"] == "proof_artifacts_only",
        "disabled_hook_ready": disabled_summary.get("status") == "ready",
        "disabled_hook_writes_zero_candidate_artifacts": int(disabled_summary.get("candidate_artifacts_written_count") or 0) == 0,
        "disabled_hook_executor_consumes_baseline_only": disabled_summary.get("executor_consumes_baseline_only") is True,
        "enabled_fixture_ready": enabled_summary.get("status") == "ready",
        "enabled_fixture_executor_consumes_baseline_only": enabled_summary.get("executor_consumes_baseline_only") is True,
        "enabled_fixture_candidate_artifacts_under_proof_artifacts": (
            enabled_summary.get("candidate_artifacts_under_proof_artifacts_only") is True
        ),
        "enabled_fixture_candidate_plan_not_referenced_by_executor": (
            enabled_summary.get("candidate_plan_referenced_by_executor") is False
        ),
        "enabled_fixture_zero_orders_fills": (
            int(enabled_summary.get("candidate_orders_submitted") or 0) == 0
            and int(enabled_summary.get("candidate_fill_count") or 0) == 0
        ),
        "live_supervisor_timer_not_loading_candidate_hook": not live_supervisor_loads_candidate_hook,
        "live_config_not_changed": True,
        "operator_state_not_changed": True,
        "timer_state_not_changed": True,
        "hook_not_deployed": True,
    }
    blockers.extend(key for key, value in implementation_gates.items() if not value)
    blockers = sorted(set(blockers))
    status = "ready" if not blockers else "blocked"

    candidate_artifact_paths = [Path(path) for path in list(enabled_summary.get("candidate_artifact_paths") or [])]
    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "implementation_scope": "default_off_observe_only_hook_contract_only",
        "hook_module": evidence_file(resolve_path("src/enhengclaw/live_trading/dth60_observe_only_shadow_hook.py")),
        "source_evidence": supervisor_context,
        "default_off_contract": default_off_contract,
        "p9c_owner_decision_approved": p9c_owner_decision_ready(owner_decision),
        "default_off_hook_enabled": False,
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
        "disabled_hook_summary": disabled_summary,
        "enabled_fixture_summary": enabled_summary,
        "disabled_hook_baseline_output_unchanged": disabled_summary.get("baseline_target_plan_byte_for_byte_unchanged") is True,
        "disabled_hook_candidate_artifacts_written_count": int(
            disabled_summary.get("candidate_artifacts_written_count") or 0
        ),
        "enabled_fixture_execution_target_unchanged": enabled_summary.get("executor_consumes_baseline_only") is True,
        "enabled_fixture_candidate_artifacts_under_proof_artifacts_only": (
            enabled_summary.get("candidate_artifacts_under_proof_artifacts_only") is True
        ),
        "candidate_plan_referenced_by_executor": enabled_summary.get("candidate_plan_referenced_by_executor"),
        "candidate_artifacts_under_output_proof_root": bool(candidate_artifact_paths)
        and all(path_under(path, output_root / "proof_artifacts") for path in candidate_artifact_paths),
        "orders_submitted": 0,
        "fill_count": 0,
        "fills_observed": 0,
        "mainnet_order_submission_authorized": False,
        "exchange_order_submission": "disabled",
        "ran_supervisor": False,
        "timer_path_invoked": False,
        "live_supervisor_loads_candidate_hook": live_supervisor_loads_candidate_hook,
        "applied_to_live": False,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "wrote_live_hook_config": False,
        "deployed_hook": False,
        "eligible_for_timer_path_load": False,
        "eligible_for_live_order_submission": False,
        "next_step_if_approved_later": "owner_gated_P9E_timer_adjacent_local_fixture_or_remote_proof_artifacts_wrapper",
        "implementation_gates": implementation_gates,
        "blockers": blockers,
        "output_files": {
            "summary": str(output_root / "summary.json"),
            "default_off_hook_contract": str(output_root / "default_off_hook_contract.json"),
            "disabled_hook_summary": str(output_root / "disabled_hook_summary.json"),
            "enabled_hook_summary": str(output_root / "enabled_hook_summary.json"),
            "report": str(output_root / "p9d_default_off_observe_only_hook.md"),
        },
    }
    write_json(output_root / "summary.json", summary)
    (output_root / "p9d_default_off_observe_only_hook.md").write_text(render_markdown(summary), encoding="utf-8")
    return summary, 0 if status == "ready" else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9D Default-Off Observe-Only Hook",
        "",
        f"`Status: {summary['status']}`",
        "",
        "## Boundary",
        "",
        "This implements a default-off observe-only hook contract only. It does not deploy the hook or load timer path.",
        "",
        "```text",
        f"default_off_hook_enabled = {str(summary['default_off_hook_enabled']).lower()}",
        "hook_deployment_authorized = false",
        "timer_path_load_authorized = false",
        "live_order_submission_authorized = false",
        "target_plan_replacement_authorized = false",
        "executor_input_mutation_authorized = false",
        "execution_target_source = baseline_only",
        "candidate_artifact_sink = proof_artifacts_only",
        "orders_submitted = 0",
        "fill_count = 0",
        "```",
        "",
        "## Implementation Gates",
        "",
        "```text",
    ]
    for key, value in dict(summary.get("implementation_gates") or {}).items():
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
    summary, exit_code = build_phase9d(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
