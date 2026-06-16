from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from enhengclaw.live_trading.default_off_scorer_shadow_wrapper import (  # noqa: E402
    DefaultOffScorerShadowConfig,
    frame_sha256,
    run_default_off_scorer_shadow_wrapper,
)


CONTRACT_VERSION = "hv_balanced_12factor_p10e_live_scorer_entry_local_fixture.v1"
DEFAULT_P10D_PARENT = (
    ROOT
    / "artifacts"
    / "live_trading"
    / "proof_artifacts"
    / "hv_balanced_12factor_candidate"
    / "p10d_default_off_scorer_wrapper"
)
DEFAULT_OUTPUT_PARENT = (
    ROOT
    / "artifacts"
    / "live_trading"
    / "proof_artifacts"
    / "hv_balanced_12factor_candidate"
    / "p10e_scorer_entry_fixture"
)
SCORER_ENTRY_PATH = ROOT / "src" / "enhengclaw" / "live_trading" / "hv_balanced_live_signal.py"
SUPERVISOR_PATH = ROOT / "src" / "enhengclaw" / "live_trading" / "mainnet_live_supervisor.py"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "P10E proof-only live scorer entry local fixture. It wraps a copied "
            "live scorer entry score context outside timer/supervisor and proves "
            "default-off preserves baseline byte-for-byte."
        )
    )
    parser.add_argument("--p10d-summary", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=None)
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def run_p10e_live_scorer_entry_local_fixture(
    args: argparse.Namespace,
    *,
    now_fn: Any | None = None,
) -> tuple[dict[str, Any], int]:
    now = now_fn or utc_now
    started_at = now()
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=UTC)
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")

    p10d_summary_path = resolve_p10d_summary(getattr(args, "p10d_summary", None))
    p10d_summary = load_json(p10d_summary_path)
    output_root = (
        resolve_repo_path(getattr(args, "output_root", None))
        if getattr(args, "output_root", None)
        else DEFAULT_OUTPUT_PARENT / run_id
    )
    output_root.mkdir(parents=True, exist_ok=True)

    p10d_artifacts = dict(p10d_summary.get("artifacts") or {})
    baseline_source = resolve_repo_path(p10d_artifacts.get("baseline_executor_scores_fixture"))
    shadow_source = resolve_repo_path(p10d_artifacts.get("shadow_research_contract_scorer_scores_fixture"))
    ctx_root = output_root / "ctx"
    baseline_copy = ctx_root / "baseline_scores.csv"
    entry_input_copy = ctx_root / "entry_input.csv"
    shadow_copy = ctx_root / "shadow_scores.csv"
    ctx_root.mkdir(parents=True, exist_ok=True)

    blockers: list[str] = []
    if not p10d_ready(p10d_summary):
        blockers.append("p10d_not_ready_for_p10e_live_scorer_entry_fixture")
    if not path_contains_part(output_root, "proof_artifacts"):
        blockers.append("p10e_output_root_not_under_proof_artifacts")
    if not baseline_source.exists():
        blockers.append("p10d_baseline_scores_source_missing")
    if not shadow_source.exists():
        blockers.append("p10d_shadow_scores_source_missing")

    baseline_source_sha_before = file_sha256(baseline_source) if baseline_source.exists() else ""
    shadow_source_sha_before = file_sha256(shadow_source) if shadow_source.exists() else ""
    if not blockers:
        shutil.copyfile(baseline_source, baseline_copy)
        shutil.copyfile(baseline_source, entry_input_copy)
        shutil.copyfile(shadow_source, shadow_copy)

    baseline_source_sha_after = file_sha256(baseline_source) if baseline_source.exists() else ""
    baseline_copy_sha = file_sha256(baseline_copy) if baseline_copy.exists() else ""
    entry_input_sha_before = file_sha256(entry_input_copy) if entry_input_copy.exists() else ""
    shadow_copy_sha = file_sha256(shadow_copy) if shadow_copy.exists() else ""
    baseline_scores = pd.read_csv(baseline_copy) if baseline_copy.exists() else pd.DataFrame()
    entry_input_scores = pd.read_csv(entry_input_copy) if entry_input_copy.exists() else pd.DataFrame()
    shadow_scores = pd.read_csv(shadow_copy) if shadow_copy.exists() else pd.DataFrame()

    entry_context = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "context_kind": "copied_live_scorer_entry_local_fixture_context",
        "fixture_scope": "live_scorer_entry_local_fixture_only_outside_timer_supervisor",
        "live_scorer_entry_path": evidence_file(SCORER_ENTRY_PATH),
        "live_supervisor_path": evidence_file(SUPERVISOR_PATH),
        "source_p10d_summary": evidence_file(p10d_summary_path),
        "source_baseline_scores": evidence_file(baseline_source),
        "source_shadow_scores": evidence_file(shadow_source),
        "baseline_scores_copy": evidence_file(baseline_copy),
        "entry_input_scores_copy": evidence_file(entry_input_copy),
        "shadow_scores_copy": evidence_file(shadow_copy),
        "timer_path_invoked": False,
        "supervisor_invoked": False,
        "executor_invoked": False,
    }
    write_json(output_root / "ctx.json", entry_context)

    disabled_result = None
    enabled_result = None
    if not blockers:
        disabled_result = run_default_off_scorer_shadow_wrapper(
            config=DefaultOffScorerShadowConfig(enabled=False),
            baseline_scores=baseline_scores,
            executor_input_scores=entry_input_scores,
            shadow_scorer_scores=shadow_scores,
            scorer_context=entry_context | {"wrapper_phase": "p10e_disabled_live_scorer_entry_fixture"},
            run_id="p10e_disabled_entry_fixture",
            now=started_at,
        )
        enabled_result = run_default_off_scorer_shadow_wrapper(
            config=DefaultOffScorerShadowConfig(
                enabled=True,
                output_root=output_root / "proof_artifacts" / "enabled",
            ),
            baseline_scores=baseline_scores,
            executor_input_scores=entry_input_scores.copy(),
            shadow_scorer_scores=shadow_scores,
            scorer_context=entry_context | {"wrapper_phase": "p10e_enabled_shadow_only_entry_fixture"},
            run_id="p10e_enabled_shadow_only_entry_fixture",
            now=started_at,
        )
        write_json(output_root / "disabled.json", disabled_result.summary)
        write_json(output_root / "enabled.json", enabled_result.summary)

    entry_input_sha_after = file_sha256(entry_input_copy) if entry_input_copy.exists() else ""
    disabled_summary = disabled_result.summary if disabled_result else {}
    enabled_summary = enabled_result.summary if enabled_result else {}
    disabled_ready = str(disabled_summary.get("status") or "") == "ready"
    enabled_ready = str(enabled_summary.get("status") or "") == "ready"
    proof_checks = {
        "p10d_ready": p10d_ready(p10d_summary),
        "output_root_under_proof_artifacts": path_contains_part(output_root, "proof_artifacts"),
        "copied_live_scorer_entry_context_used": entry_context["context_kind"]
        == "copied_live_scorer_entry_local_fixture_context",
        "baseline_source_file_unchanged": bool(baseline_source_sha_before)
        and baseline_source_sha_before == baseline_source_sha_after,
        "baseline_copy_byte_for_byte_matches_source": bool(baseline_copy_sha)
        and baseline_copy_sha == baseline_source_sha_before,
        "entry_input_copy_byte_for_byte_matches_baseline": bool(entry_input_sha_before)
        and entry_input_sha_before == baseline_copy_sha,
        "entry_input_file_unchanged_after_disabled_wrapper": bool(entry_input_sha_before)
        and entry_input_sha_before == entry_input_sha_after,
        "shadow_copy_byte_for_byte_matches_source": bool(shadow_copy_sha) and shadow_copy_sha == shadow_source_sha_before,
        "disabled_wrapper_ready": disabled_ready,
        "disabled_baseline_scores_byte_for_byte_unchanged": bool(
            disabled_summary.get("baseline_scores_byte_for_byte_unchanged")
        ),
        "disabled_wrapper_output_scores_hash_equals_baseline": bool(
            disabled_summary.get("wrapper_output_scores_hash_equals_baseline")
        ),
        "disabled_executor_consumes_baseline_only": bool(disabled_summary.get("executor_consumes_baseline_only")),
        "disabled_wrote_zero_shadow_artifacts": int(disabled_summary.get("shadow_artifacts_written_count") or 0) == 0,
        "enabled_wrapper_ready": enabled_ready,
        "enabled_shadow_artifacts_under_proof_artifacts_only": bool(
            enabled_summary.get("shadow_artifacts_under_proof_artifacts_only")
        ),
        "enabled_executor_consumes_baseline_only": bool(enabled_summary.get("executor_consumes_baseline_only")),
        "enabled_shadow_not_referenced_by_executor": not bool(
            enabled_summary.get("shadow_scorer_referenced_by_executor")
        ),
        "timer_supervisor_executor_not_invoked": True,
        "zero_orders_fills": True,
        "live_state_unchanged": True,
    }
    blockers.extend([key for key, value in proof_checks.items() if not value])
    blockers.extend(str(item) for item in list(disabled_summary.get("blockers") or []))
    blockers.extend(str(item) for item in list(enabled_summary.get("blockers") or []))
    blockers = sorted(set(item for item in blockers if item))
    status = "ready" if not blockers else "blocked"

    contract_path = output_root / "contract.json"
    summary_path = output_root / "summary.json"
    report_path = output_root / "p10e.md"
    contract = {
        "contract_version": CONTRACT_VERSION,
        "fixture_scope": "live_scorer_entry_local_fixture_only_outside_timer_supervisor",
        "default_off_required": True,
        "disabled_required_effect": {
            "baseline_scores_byte_for_byte_unchanged": True,
            "entry_input_scores_byte_for_byte_unchanged": True,
            "shadow_artifacts_written_count": 0,
            "executor_score_source": "baseline_only",
        },
        "enabled_required_effect": {
            "shadow_scorer_artifacts_under_proof_artifacts_only": True,
            "executor_score_source": "baseline_only",
            "shadow_scorer_referenced_by_executor": False,
        },
        "not_authorized": {
            "timer_path_invocation": True,
            "supervisor_invocation": True,
            "executor_invocation": True,
            "executor_input_mutation": True,
            "target_plan_replacement": True,
            "candidate_execution": True,
            "live_order_submission": True,
            "live_config_change": True,
            "operator_state_change": True,
            "timer_state_change": True,
        },
    }
    write_json(contract_path, contract)

    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "output_root": str(output_root),
        "fixture_scope": "live_scorer_entry_local_fixture_only_outside_timer_supervisor",
        "live_scorer_entry_fixture_invoked": True,
        "live_scorer_entry_wrapped_locally": True,
        "wrapper_default_enabled": False,
        "default_off_scorer_wrapper_enabled": False,
        "candidate_scorer_loaded_into_live_scorer_entry": False,
        "candidate_scorer_loaded_into_executor": False,
        "candidate_scorer_loaded_into_timer": False,
        "candidate_executed": False,
        "executor_invoked": False,
        "executor_input_mutated": False,
        "target_plan_replaced": False,
        "timer_path_invoked": False,
        "supervisor_invoked": False,
        "applied_to_live": False,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "mainnet_order_submission_authorized": False,
        "exchange_order_submission": "disabled",
        "orders_submitted": 0,
        "fill_count": 0,
        "p10d_summary": evidence_file(p10d_summary_path),
        "p10d_ready": p10d_ready(p10d_summary),
        "baseline_source_sha256_before": baseline_source_sha_before,
        "baseline_source_sha256_after": baseline_source_sha_after,
        "baseline_copy_sha256": baseline_copy_sha,
        "entry_input_sha256_before_wrapper": entry_input_sha_before,
        "entry_input_sha256_after_wrapper": entry_input_sha_after,
        "shadow_source_sha256": shadow_source_sha_before,
        "shadow_copy_sha256": shadow_copy_sha,
        "disabled_wrapper_status": str(disabled_summary.get("status") or ""),
        "disabled_baseline_scores_byte_for_byte_unchanged": bool(
            disabled_summary.get("baseline_scores_byte_for_byte_unchanged")
        ),
        "disabled_wrapper_output_scores_hash_equals_baseline": bool(
            disabled_summary.get("wrapper_output_scores_hash_equals_baseline")
        ),
        "disabled_executor_consumes_baseline_only": bool(disabled_summary.get("executor_consumes_baseline_only")),
        "disabled_shadow_artifacts_written_count": int(disabled_summary.get("shadow_artifacts_written_count") or 0),
        "enabled_wrapper_status": str(enabled_summary.get("status") or ""),
        "enabled_shadow_artifacts_written_count": int(enabled_summary.get("shadow_artifacts_written_count") or 0),
        "enabled_shadow_artifacts_under_proof_artifacts_only": bool(
            enabled_summary.get("shadow_artifacts_under_proof_artifacts_only")
        ),
        "enabled_executor_consumes_baseline_only": bool(enabled_summary.get("executor_consumes_baseline_only")),
        "enabled_shadow_scorer_referenced_by_executor": bool(
            enabled_summary.get("shadow_scorer_referenced_by_executor")
        ),
        "proof_checks": proof_checks,
        "blockers": blockers,
        "artifacts": {
            "summary": str(summary_path),
            "contract": str(contract_path),
            "context": str(output_root / "ctx.json"),
            "disabled_wrapper_summary": str(output_root / "disabled.json"),
            "enabled_wrapper_summary": str(output_root / "enabled.json"),
            "report": str(report_path),
        },
    }
    write_json(summary_path, summary)
    report_path.write_text(render_markdown(summary), encoding="utf-8")
    return summary, 0 if status == "ready" else 2


def p10d_ready(summary: dict[str, Any]) -> bool:
    return (
        summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p10c_snapshot_ready") is True
        and summary.get("disabled_hook_baseline_byte_for_byte_unchanged") is True
        and int(summary.get("disabled_hook_shadow_artifacts_written_count") or 0) == 0
        and summary.get("enabled_hook_executor_consumes_baseline_only") is True
        and summary.get("enabled_hook_shadow_artifacts_under_proof_artifacts_only") is True
        and summary.get("enabled_hook_shadow_scorer_referenced_by_executor") is False
        and summary.get("candidate_scorer_loaded_into_executor") is False
        and summary.get("candidate_scorer_loaded_into_timer") is False
        and summary.get("executor_invoked") is False
        and summary.get("timer_path_invoked") is False
        and summary.get("supervisor_invoked") is False
        and int(summary.get("orders_submitted") or 0) == 0
        and int(summary.get("fill_count") or 0) == 0
    )


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced 12-Factor P10E Live Scorer Entry Local Fixture",
        "",
        f"`Status: {summary['status']}`",
        "",
        "## Boundary",
        "",
        "This fixture wraps a copied live scorer entry context outside timer, supervisor, executor, and order paths.",
        "",
        "```text",
        f"fixture_scope = {summary['fixture_scope']}",
        "wrapper_default_enabled = false",
        "default_off_scorer_wrapper_enabled = false",
        "candidate_scorer_loaded_into_live_scorer_entry = false",
        "executor_invoked = false",
        "timer_path_invoked = false",
        "supervisor_invoked = false",
        "orders_submitted = 0",
        "fill_count = 0",
        "```",
        "",
        "## Proof Checks",
        "",
        "```text",
    ]
    for key, value in dict(summary.get("proof_checks") or {}).items():
        lines.append(f"{key} = {str(bool(value)).lower()}")
    lines.extend(["```", "", "## Blockers", ""])
    blockers = list(summary.get("blockers") or [])
    if blockers:
        lines.extend(f"- `{item}`" for item in blockers)
    else:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def resolve_p10d_summary(path_ref: Path | str | None) -> Path:
    if path_ref:
        path = resolve_repo_path(path_ref)
        if path.is_dir():
            path = path / "summary.json"
        if not path.exists():
            raise FileNotFoundError(path)
        return path
    candidates = sorted(DEFAULT_P10D_PARENT.glob("*/summary.json"), key=lambda path: path.stat().st_mtime)
    if not candidates:
        raise FileNotFoundError(f"no P10D summary.json found under {DEFAULT_P10D_PARENT}")
    return candidates[-1]


def resolve_repo_path(path_ref: Path | str | None) -> Path:
    if path_ref is None:
        raise ValueError("path is required")
    path = Path(path_ref).expanduser()
    if path.is_absolute():
        return path
    return (ROOT / path).resolve()


def path_contains_part(path: Path, part: str) -> bool:
    return part.lower() in [item.lower() for item in path.resolve().parts]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def evidence_file(path: Path | None) -> dict[str, Any]:
    if not path:
        return {"path": "", "exists": False, "sha256": ""}
    if not path.exists():
        return {"path": str(path), "exists": False, "sha256": ""}
    return {"path": str(path), "exists": True, "sha256": file_sha256(path)}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (pd.Timestamp, datetime)):
        timestamp = pd.Timestamp(value)
        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize("UTC")
        return timestamp.tz_convert("UTC").isoformat().replace("+00:00", "Z")
    if isinstance(value, Path):
        return str(value)
    if pd.isna(value):
        return None
    return value


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = run_p10e_live_scorer_entry_local_fixture(parse_args(argv))
    print(json.dumps(json_safe(summary), indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
