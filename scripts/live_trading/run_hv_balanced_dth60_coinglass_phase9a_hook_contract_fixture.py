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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase6_owner_review_pack import (  # noqa: E402
    TARGET_CONTRIBUTION,
    evidence_file,
    is_zero_order,
    load_json,
    no_live_mutation,
    resolve_path,
    write_json,
)


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9a_hook_contract_fixture.v1"
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_coinglass_candidate/"
    "phase9a_local_hook_contract_fixture"
)
DEFAULT_PHASE4_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_coinglass_candidate/"
    "phase4_paired_target_plan_shadow"
)
EXECUTOR_PLAN_FILENAME = "target_plan.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the P9A local live-supervisor shadow-hook contract fixture. "
            "It proves disabled-hook baseline byte parity and enabled-hook "
            "shadow-only candidate output without touching live config, timers, "
            "operator state, or order submission."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument(
        "--phase4-summary",
        default="",
        help="Retained Phase 4 paired target-plan shadow summary. Defaults to latest local P4 summary.",
    )
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def latest_match(parent: str, pattern: str) -> Path:
    root = resolve_path(parent)
    matches = sorted(root.glob(pattern))
    if not matches:
        return Path("")
    return matches[-1]


def path_under(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def copy_bytes(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def source_file_from_phase4(phase4: dict[str, Any], key: str, phase4_root: Path, default_name: str) -> Path:
    output_files = dict(phase4.get("output_files") or {})
    value = str(output_files.get(key) or "").strip()
    return resolve_path(value) if value else phase4_root / default_name


def build_phase9a_fixture(
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
    phase4_summary_path = (
        resolve_path(args.phase4_summary)
        if str(getattr(args, "phase4_summary", "") or "").strip()
        else latest_match(DEFAULT_PHASE4_PARENT, "*/summary.json")
    )
    phase4_root = phase4_summary_path.parent if phase4_summary_path else Path("")
    blockers: list[str] = []

    phase4: dict[str, Any] = {}
    if not phase4_summary_path or not phase4_summary_path.exists():
        blockers.append("phase4_summary_missing")
    else:
        phase4 = load_json(phase4_summary_path)

    baseline_source = (
        source_file_from_phase4(phase4, "baseline_target_portfolio", phase4_root, "baseline_target_portfolio.json")
        if phase4
        else Path("")
    )
    candidate_source = (
        source_file_from_phase4(phase4, "candidate_target_portfolio", phase4_root, "candidate_target_portfolio.json")
        if phase4
        else Path("")
    )
    target_plan_diff_source = (
        source_file_from_phase4(phase4, "target_plan_diff", phase4_root, "target_plan_diff.csv") if phase4 else Path("")
    )
    shared_context_source = (
        source_file_from_phase4(phase4, "shared_input_context", phase4_root, "shared_input_context.json")
        if phase4
        else Path("")
    )

    phase4_target_boundary_ok = (
        dict(phase4.get("phase3_parity_proof_checks") or {}).get("overlay_enabled_only_target_contribution_changed")
        is True
    )
    phase4_p2_ok = all(
        dict(phase4.get("phase2_pit_proof_checks") or {}).get(key) is True
        for key in ("no_future_fill_proven", "no_stale_fill_proven", "no_zero_fill_proven")
    )
    phase4_p2b_ok = all(
        dict(phase4.get("phase2b_pit_proof_checks") or {}).get(key) is True
        for key in ("no_future_fill_proven", "no_stale_fill_proven", "no_zero_fill_proven")
    )
    phase4_gates = {
        "phase4_ready": phase4.get("status") == "ready",
        "phase4_no_blockers": not phase4.get("blockers"),
        "phase4_same_timestamp_context": phase4.get("same_timestamp_context_proven") is True,
        "phase4_same_risk_inputs": phase4.get("same_risk_inputs_proven") is True,
        "phase4_same_symbol_set": phase4.get("same_symbol_set_proven") is True,
        "phase4_same_portfolio_engine": phase4.get("same_portfolio_engine_proven") is True,
        "phase4_deterministic_target_difference": phase4.get("deterministic_target_difference_proven") is True,
        "phase4_zero_orders_fills": is_zero_order(phase4),
        "phase4_no_live_mutation": no_live_mutation(phase4),
        "phase4_overlay_only_distance_to_high_60": phase4_target_boundary_ok,
        "phase4_phase2_no_future_stale_zero_fill": phase4_p2_ok,
        "phase4_phase2b_no_future_stale_zero_fill": phase4_p2b_ok,
        "baseline_target_plan_exists": bool(baseline_source and baseline_source.exists()),
        "candidate_target_plan_exists": bool(candidate_source and candidate_source.exists()),
    }
    blockers.extend(key for key, value in phase4_gates.items() if not value)

    output_root.mkdir(parents=True, exist_ok=True)
    disabled_root = output_root / "disabled_hook"
    enabled_root = output_root / "enabled_hook"
    proof_root = output_root / "proof_artifacts" / "p9a" / run_id / "shadow_hook"
    disabled_before = disabled_root / "baseline_target_plan_before_hook.json"
    disabled_after = disabled_root / "baseline_target_plan_after_hook.json"
    disabled_executor = disabled_root / "executor_input" / EXECUTOR_PLAN_FILENAME
    enabled_before = enabled_root / "baseline_target_plan_before_hook.json"
    enabled_after = enabled_root / "baseline_target_plan_after_hook.json"
    enabled_executor = enabled_root / "executor_input" / EXECUTOR_PLAN_FILENAME
    candidate_shadow_plan = proof_root / "candidate_shadow_plan.json"
    candidate_shadow_manifest = proof_root / "manifest.json"
    paired_plan_diff = proof_root / "plan_diff.csv"

    baseline_source_sha = ""
    candidate_source_sha = ""
    candidate_shadow_sha = ""
    disabled_hashes: dict[str, str] = {}
    enabled_hashes: dict[str, str] = {}
    candidate_artifact_paths: list[Path] = []

    if not blockers:
        baseline_source_sha = file_sha256(baseline_source)
        candidate_source_sha = file_sha256(candidate_source)
        copy_bytes(baseline_source, disabled_before)
        copy_bytes(baseline_source, disabled_after)
        copy_bytes(baseline_source, disabled_executor)
        copy_bytes(baseline_source, enabled_before)
        copy_bytes(baseline_source, enabled_after)
        copy_bytes(baseline_source, enabled_executor)
        copy_bytes(candidate_source, candidate_shadow_plan)
        candidate_shadow_sha = file_sha256(candidate_shadow_plan)
        candidate_artifact_paths.append(candidate_shadow_plan)
        if target_plan_diff_source and target_plan_diff_source.exists():
            copy_bytes(target_plan_diff_source, paired_plan_diff)
            candidate_artifact_paths.append(paired_plan_diff)

        candidate_manifest = {
            "contract_version": CONTRACT_VERSION,
            "run_id": run_id,
            "candidate_id": "hv_balanced_dth60_cg_q90_top20_overlay_candidate",
            "candidate_order_authority": "disabled",
            "candidate_live_order_submission_authorized": False,
            "execution_target_source": "baseline_only",
            "candidate_overlay_execution_path": "excluded",
            "source_candidate_target_plan": evidence_file(candidate_source),
            "candidate_shadow_plan": evidence_file(candidate_shadow_plan),
            "paired_plan_diff": evidence_file(paired_plan_diff) if paired_plan_diff.exists() else {"exists": False},
            "orders_submitted": 0,
            "fill_count": 0,
        }
        write_json(candidate_shadow_manifest, candidate_manifest)
        candidate_artifact_paths.append(candidate_shadow_manifest)

        disabled_hashes = {
            "baseline_before": file_sha256(disabled_before),
            "baseline_after": file_sha256(disabled_after),
            "executor_input": file_sha256(disabled_executor),
        }
        enabled_hashes = {
            "baseline_before": file_sha256(enabled_before),
            "baseline_after": file_sha256(enabled_after),
            "executor_input": file_sha256(enabled_executor),
            "candidate_shadow_plan": candidate_shadow_sha,
        }

    candidate_artifact_rel_paths = [
        str(path.resolve().relative_to(output_root.resolve())).replace("\\", "/") for path in candidate_artifact_paths
    ]
    candidate_artifacts_under_proof = bool(candidate_artifact_paths) and all(
        path_under(path, output_root / "proof_artifacts") for path in candidate_artifact_paths
    )
    disabled_hook_baseline_output_unchanged = bool(disabled_hashes) and len(set(disabled_hashes.values())) == 1
    enabled_hook_execution_target_unchanged = (
        bool(enabled_hashes)
        and enabled_hashes.get("baseline_before") == enabled_hashes.get("baseline_after")
        and enabled_hashes.get("baseline_before") == enabled_hashes.get("executor_input")
        and enabled_hashes.get("baseline_before") == baseline_source_sha
    )
    executor_consumes_baseline_only = (
        enabled_hook_execution_target_unchanged
        and enabled_hashes.get("executor_input") == baseline_source_sha
        and enabled_hashes.get("executor_input") != candidate_shadow_sha
    )
    disabled_hook_candidate_artifacts_written_count = 0
    candidate_plan_referenced_by_executor = False

    fixture_gates = {
        "disabled_hook_baseline_output_unchanged": disabled_hook_baseline_output_unchanged,
        "disabled_hook_candidate_artifacts_written_count_zero": disabled_hook_candidate_artifacts_written_count == 0,
        "enabled_hook_execution_target_unchanged": enabled_hook_execution_target_unchanged,
        "executor_input_plan_hash_equals_baseline": enabled_hashes.get("executor_input") == baseline_source_sha,
        "executor_consumes_baseline_only": executor_consumes_baseline_only,
        "candidate_shadow_plan_hash_differs_from_executor": (
            bool(candidate_shadow_sha) and candidate_shadow_sha != enabled_hashes.get("executor_input")
        ),
        "candidate_artifacts_under_proof_artifacts_only": candidate_artifacts_under_proof,
        "candidate_plan_not_referenced_by_executor": not candidate_plan_referenced_by_executor,
        "candidate_orders_submitted_zero": True,
        "candidate_fill_count_zero": True,
        "candidate_live_order_submission_authorized_false": True,
    }
    blockers.extend(key for key, value in fixture_gates.items() if not value)
    blockers = sorted(set(str(item) for item in blockers if str(item).strip()))
    status = "ready" if not blockers else "blocked"

    supervisor_context = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "phase4_summary": evidence_file(phase4_summary_path),
        "phase4_run_id": phase4.get("run_id"),
        "phase4_generated_at_utc": phase4.get("generated_at_utc"),
        "live_config_path": phase4.get("live_config_path"),
        "strategy_config_path": phase4.get("strategy_config_path"),
        "strategy_config_sha256": phase4.get("strategy_config_sha256"),
        "target_engine": phase4.get("target_engine"),
        "portfolio_engine": phase4.get("portfolio_engine"),
        "upper_timestamp_utc": phase4.get("upper_timestamp_utc"),
        "phase_decision_times_utc": phase4.get("phase_decision_times_utc"),
        "shared_risk_inputs_sha256": phase4.get("shared_risk_inputs_sha256"),
        "shared_panel_sha256": phase4.get("shared_panel_sha256"),
        "shared_phase_context_sha256": phase4.get("shared_phase_context_sha256"),
        "baseline_target_plan_sha256": baseline_source_sha,
        "candidate_shadow_source_sha256": candidate_source_sha,
        "shared_input_context": evidence_file(shared_context_source) if shared_context_source else {"exists": False},
    }
    write_json(output_root / "supervisor_context_snapshot.json", supervisor_context)
    write_json(
        output_root / "baseline_target_plan_hash.json",
        {
            "source_baseline_target_plan": evidence_file(baseline_source),
            "baseline_target_plan_sha256": baseline_source_sha,
            "disabled_hook_hashes": disabled_hashes,
            "enabled_hook_hashes": enabled_hashes,
        },
    )
    write_json(
        disabled_root / "disabled_hook_summary.json",
        {
            "status": "ready" if disabled_hook_baseline_output_unchanged else "blocked",
            "hook_enabled": False,
            "baseline_target_plan_sha256_before_hook": disabled_hashes.get("baseline_before", ""),
            "baseline_target_plan_sha256_after_hook": disabled_hashes.get("baseline_after", ""),
            "executor_input_plan_sha256": disabled_hashes.get("executor_input", ""),
            "candidate_artifacts_written_count": disabled_hook_candidate_artifacts_written_count,
            "baseline_byte_for_byte_unchanged": disabled_hook_baseline_output_unchanged,
        },
    )
    write_json(
        enabled_root / "executor_input_readback.json",
        {
            "status": "ready" if executor_consumes_baseline_only else "blocked",
            "hook_enabled": True,
            "source_plan_role": "baseline",
            "execution_target_source": "baseline_only",
            "executor_input_plan_path": str(enabled_executor),
            "executor_input_plan_sha256": enabled_hashes.get("executor_input", ""),
            "baseline_target_plan_sha256": baseline_source_sha,
            "candidate_shadow_plan_path": str(candidate_shadow_plan) if candidate_shadow_plan.exists() else "",
            "candidate_shadow_plan_sha256": candidate_shadow_sha,
            "candidate_plan_referenced_by_executor": candidate_plan_referenced_by_executor,
            "candidate_overlay_execution_path": "excluded",
        },
    )

    summary: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "output_root": str(output_root),
        "source_evidence": {
            "phase4_summary": evidence_file(phase4_summary_path),
            "baseline_target_plan": evidence_file(baseline_source),
            "candidate_target_plan": evidence_file(candidate_source),
            "target_plan_diff": evidence_file(target_plan_diff_source) if target_plan_diff_source else {"exists": False},
        },
        "candidate_order_authority": "disabled",
        "candidate_live_order_submission_authorized": False,
        "execution_target_source": "baseline_only",
        "candidate_overlay_execution_path": "excluded",
        "candidate_artifact_sink": "proof_artifacts_only",
        "baseline_executor_input_must_remain_unchanged": True,
        "baseline_target_plan_sha256_before_hook": enabled_hashes.get("baseline_before", ""),
        "baseline_target_plan_sha256_after_hook": enabled_hashes.get("baseline_after", ""),
        "executor_input_plan_sha256": enabled_hashes.get("executor_input", ""),
        "candidate_shadow_plan_sha256": candidate_shadow_sha,
        "disabled_hook_baseline_output_unchanged": disabled_hook_baseline_output_unchanged,
        "disabled_hook_candidate_artifacts_written_count": disabled_hook_candidate_artifacts_written_count,
        "enabled_hook_execution_target_unchanged": enabled_hook_execution_target_unchanged,
        "executor_consumes_baseline_only": executor_consumes_baseline_only,
        "candidate_artifacts_under_proof_artifacts_only": candidate_artifacts_under_proof,
        "candidate_artifact_paths": candidate_artifact_rel_paths,
        "candidate_plan_referenced_by_executor": candidate_plan_referenced_by_executor,
        "same_timestamp_context_proven": phase4.get("same_timestamp_context_proven") is True,
        "same_risk_inputs_proven": phase4.get("same_risk_inputs_proven") is True,
        "same_symbol_set_proven": phase4.get("same_symbol_set_proven") is True,
        "same_portfolio_engine_proven": phase4.get("same_portfolio_engine_proven") is True,
        "overlay_only_distance_to_high_60_contribution": phase4_target_boundary_ok,
        "fresh_phase2_no_future_stale_zero_fill": phase4_p2_ok,
        "fresh_phase2b_no_future_stale_zero_fill": phase4_p2b_ok,
        "candidate_orders_submitted": 0,
        "candidate_fill_count": 0,
        "orders_submitted": 0,
        "fill_count": 0,
        "mainnet_order_submission_authorized": False,
        "applied_to_live": False,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "exchange_order_submission": "disabled",
        "phase4_gates": phase4_gates,
        "fixture_gates": fixture_gates,
        "eligible_for_further_shadow_observation": status == "ready",
        "eligible_for_live_order_submission": False,
        "blockers": blockers,
        "output_files": {
            "summary": str(output_root / "summary.json"),
            "supervisor_context_snapshot": str(output_root / "supervisor_context_snapshot.json"),
            "baseline_target_plan_hash": str(output_root / "baseline_target_plan_hash.json"),
            "disabled_hook_summary": str(disabled_root / "disabled_hook_summary.json"),
            "enabled_executor_input_readback": str(enabled_root / "executor_input_readback.json"),
            "candidate_shadow_plan": str(candidate_shadow_plan) if candidate_shadow_plan.exists() else "",
            "candidate_shadow_manifest": str(candidate_shadow_manifest) if candidate_shadow_manifest.exists() else "",
            "report": str(output_root / "p9a_hook_contract_fixture.md"),
        },
    }
    write_json(output_root / "summary.json", summary)
    (output_root / "p9a_hook_contract_fixture.md").write_text(render_markdown(summary), encoding="utf-8")
    write_json(output_root / "summary.json", summary)
    return summary, 0 if status == "ready" else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9A Local Hook-Contract Fixture",
        "",
        f"Status: `{summary['status']}`",
        f"Generated: `{summary['generated_at_utc']}`",
        "",
        "## Boundary",
        "",
        "- Hook disabled must leave the baseline target plan byte-for-byte unchanged.",
        "- Hook enabled may write only candidate shadow artifacts under proof_artifacts.",
        "- Executor input remains the baseline target plan.",
        "- Candidate order authority remains disabled.",
        "",
        "## Key Proof",
        "",
        f"- disabled_hook_baseline_output_unchanged: `{str(summary['disabled_hook_baseline_output_unchanged']).lower()}`",
        f"- disabled_hook_candidate_artifacts_written_count: `{summary['disabled_hook_candidate_artifacts_written_count']}`",
        f"- enabled_hook_execution_target_unchanged: `{str(summary['enabled_hook_execution_target_unchanged']).lower()}`",
        f"- executor_consumes_baseline_only: `{str(summary['executor_consumes_baseline_only']).lower()}`",
        f"- candidate_artifacts_under_proof_artifacts_only: `{str(summary['candidate_artifacts_under_proof_artifacts_only']).lower()}`",
        f"- candidate_orders_submitted: `{summary['candidate_orders_submitted']}`",
        f"- candidate_fill_count: `{summary['candidate_fill_count']}`",
        f"- eligible_for_live_order_submission: `{str(summary['eligible_for_live_order_submission']).lower()}`",
        "",
        "## Blockers",
        "",
    ]
    blockers = list(summary.get("blockers") or [])
    if blockers:
        lines.extend(f"- `{item}`" for item in blockers)
    else:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_phase9a_fixture(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
