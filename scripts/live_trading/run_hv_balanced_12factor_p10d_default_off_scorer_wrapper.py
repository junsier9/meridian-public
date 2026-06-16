from __future__ import annotations

import argparse
import json
import math
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
    CONTRACT_VERSION as WRAPPER_CONTRACT_VERSION,
    DefaultOffScorerShadowConfig,
    frame_sha256,
    run_default_off_scorer_shadow_wrapper,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9r_research_to_live_parity import (  # noqa: E402
    file_sha256,
)


CONTRACT_VERSION = "hv_balanced_12factor_p10d_default_off_scorer_wrapper.v1"
DEFAULT_P10C_PARENT = (
    ROOT
    / "artifacts"
    / "live_trading"
    / "hv_balanced_12factor_candidate"
    / "p10c_live_snapshot_research_input_parity"
)
DEFAULT_OUTPUT_PARENT = (
    ROOT
    / "artifacts"
    / "live_trading"
    / "proof_artifacts"
    / "hv_balanced_12factor_candidate"
    / "p10d_default_off_scorer_wrapper"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "P10D proof-only wrapper: prove the scorer hook is default-off, "
            "and enabled mode writes only a shadow scorer artifact while executor input stays baseline-only."
        )
    )
    parser.add_argument("--p10c-summary", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=None)
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def run_p10d_default_off_scorer_wrapper(
    args: argparse.Namespace,
    *,
    now_fn: Any | None = None,
) -> tuple[dict[str, Any], int]:
    now = now_fn or utc_now
    started_at = now()
    p10c_summary_path = resolve_p10c_summary(getattr(args, "p10c_summary", None))
    p10c_summary = load_json(p10c_summary_path)
    p10c_artifacts = dict(p10c_summary.get("artifacts") or {})
    scorer_matrix_path = resolve_repo_path(p10c_artifacts.get("research_scorer_input_matrix"))
    scorer_matrix = pd.read_csv(scorer_matrix_path)

    output_root = (
        resolve_repo_path(getattr(args, "output_root", None))
        if getattr(args, "output_root", None)
        else DEFAULT_OUTPUT_PARENT / started_at.strftime("%Y%m%dT%H%M%S%fZ")
    )
    output_root.mkdir(parents=True, exist_ok=True)

    blockers: list[str] = []
    if str(p10c_summary.get("status") or "") != "ready":
        blockers.append("p10c_summary_not_ready")
    if int(p10c_summary.get("mismatch_count") or 0) != 0:
        blockers.append("p10c_factor_parity_mismatch")
    if not bool(p10c_summary.get("factor_order_matches_research_contract")):
        blockers.append("p10c_factor_order_not_bound_to_research_contract")
    if bool(p10c_summary.get("executor_invoked")):
        blockers.append("p10c_executor_invoked")
    if bool(p10c_summary.get("candidate_executed")):
        blockers.append("p10c_candidate_executed")
    if int(p10c_summary.get("orders_submitted") or 0) != 0:
        blockers.append("p10c_orders_submitted_nonzero")
    if int(p10c_summary.get("fills_observed") or 0) != 0:
        blockers.append("p10c_fills_observed_nonzero")
    if not path_contains_part(output_root, "proof_artifacts"):
        blockers.append("p10d_output_root_not_under_proof_artifacts")

    baseline_scores = build_baseline_executor_scores(
        scorer_matrix,
        decision_time_utc=str(p10c_summary.get("p10a_decision_time_utc") or ""),
    )
    shadow_scores = build_shadow_scorer_scores(
        scorer_matrix,
        decision_time_utc=str(p10c_summary.get("p10a_decision_time_utc") or ""),
    )
    baseline_scores_path = output_root / "baseline_executor_scores_fixture.csv"
    shadow_scores_path = output_root / "shadow_research_contract_scorer_scores_fixture.csv"
    write_csv(baseline_scores_path, baseline_scores)
    write_csv(shadow_scores_path, shadow_scores)

    disabled_result = run_default_off_scorer_shadow_wrapper(
        config=DefaultOffScorerShadowConfig(enabled=False),
        baseline_scores=baseline_scores,
        executor_input_scores=baseline_scores.copy(),
        shadow_scorer_scores=shadow_scores,
        scorer_context={
            "p10c_summary_path": str(p10c_summary_path),
            "research_scorer_input_matrix": str(scorer_matrix_path),
            "decision_time_utc": str(p10c_summary.get("p10a_decision_time_utc") or ""),
            "wrapper_phase": "p10d_disabled",
        },
        run_id="p10d_disabled_default_off",
        now=started_at,
    )
    enabled_result = run_default_off_scorer_shadow_wrapper(
        config=DefaultOffScorerShadowConfig(enabled=True, output_root=output_root / "enabled_wrapper"),
        baseline_scores=baseline_scores,
        executor_input_scores=baseline_scores.copy(),
        shadow_scorer_scores=shadow_scores,
        scorer_context={
            "p10c_summary_path": str(p10c_summary_path),
            "research_scorer_input_matrix": str(scorer_matrix_path),
            "decision_time_utc": str(p10c_summary.get("p10a_decision_time_utc") or ""),
            "wrapper_phase": "p10d_enabled_shadow_only",
        },
        run_id="p10d_enabled_shadow_only",
        now=started_at,
    )

    disabled_summary_path = output_root / "disabled_wrapper_summary.json"
    enabled_summary_path = output_root / "enabled_wrapper_summary.json"
    contract_path = output_root / "default_off_scorer_wrapper_contract.json"
    summary_path = output_root / "summary.json"
    write_json(disabled_summary_path, disabled_result.summary)
    write_json(enabled_summary_path, enabled_result.summary)

    wrapper_contract = {
        "contract_version": CONTRACT_VERSION,
        "wrapped_contract_version": WRAPPER_CONTRACT_VERSION,
        "hook_default_enabled": False,
        "disabled_mode_required_effect": {
            "baseline_scores_byte_for_byte_unchanged": True,
            "shadow_artifacts_written_count": 0,
            "executor_score_source": "baseline_only",
        },
        "enabled_mode_required_effect": {
            "shadow_scorer_artifacts_under_proof_artifacts_only": True,
            "executor_score_source": "baseline_only",
            "shadow_scorer_referenced_by_executor": False,
            "candidate_scorer_loaded_into_executor": False,
        },
        "not_authorized": {
            "executor_invocation": True,
            "timer_path_invocation": True,
            "supervisor_invocation": True,
            "live_config_change": True,
            "operator_state_change": True,
            "timer_state_change": True,
            "target_plan_replacement": True,
            "executor_input_mutation": True,
            "candidate_execution": True,
            "live_order_submission": True,
        },
    }
    write_json(contract_path, wrapper_contract)

    disabled_ready = str(disabled_result.summary.get("status") or "") == "ready"
    enabled_ready = str(enabled_result.summary.get("status") or "") == "ready"
    proof_checks = {
        "p10c_snapshot_ready": str(p10c_summary.get("status") or "") == "ready",
        "p10c_factor_parity_clean": int(p10c_summary.get("mismatch_count") or 0) == 0,
        "p10c_no_executor_or_candidate": not bool(p10c_summary.get("executor_invoked"))
        and not bool(p10c_summary.get("candidate_executed")),
        "p10c_zero_orders_fills": int(p10c_summary.get("orders_submitted") or 0) == 0
        and int(p10c_summary.get("fills_observed") or 0) == 0,
        "output_root_under_proof_artifacts": path_contains_part(output_root, "proof_artifacts"),
        "disabled_wrapper_ready": disabled_ready,
        "disabled_hook_baseline_byte_for_byte_unchanged": bool(
            disabled_result.summary.get("baseline_scores_byte_for_byte_unchanged")
        ),
        "disabled_hook_wrote_zero_shadow_artifacts": int(
            disabled_result.summary.get("shadow_artifacts_written_count") or 0
        )
        == 0,
        "enabled_wrapper_ready": enabled_ready,
        "enabled_hook_shadow_artifacts_under_proof_artifacts_only": bool(
            enabled_result.summary.get("shadow_artifacts_under_proof_artifacts_only")
        ),
        "enabled_hook_executor_consumes_baseline_only": bool(
            enabled_result.summary.get("executor_consumes_baseline_only")
        ),
        "enabled_hook_shadow_not_referenced_by_executor": not bool(
            enabled_result.summary.get("shadow_scorer_referenced_by_executor")
        ),
        "enabled_hook_candidate_not_loaded_into_executor": not bool(
            enabled_result.summary.get("candidate_scorer_loaded_into_executor")
        ),
    }
    blockers.extend([key for key, value in proof_checks.items() if not value])
    blockers.extend(str(item) for item in list(disabled_result.summary.get("blockers") or []))
    blockers.extend(str(item) for item in list(enabled_result.summary.get("blockers") or []))
    blockers = sorted(set(item for item in blockers if item))
    status = "ready" if not blockers else "blocked"

    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "generated_at_utc": iso_z(now()),
        "started_at_utc": iso_z(started_at),
        "output_root": str(output_root),
        "applied_to_live": False,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "timer_path_invoked": False,
        "supervisor_invoked": False,
        "executor_invoked": False,
        "executor_input_mutated": False,
        "candidate_executed": False,
        "candidate_scorer_loaded_into_executor": False,
        "candidate_scorer_loaded_into_timer": False,
        "target_plan_replaced": False,
        "mainnet_order_submission_authorized": False,
        "exchange_order_submission": "disabled",
        "orders_submitted": 0,
        "fill_count": 0,
        "p10c_snapshot_ready": str(p10c_summary.get("status") or "") == "ready",
        "p10c_summary_path": str(p10c_summary_path),
        "p10c_summary_sha256": file_sha256(p10c_summary_path),
        "p10c_research_scorer_input_matrix_path": str(scorer_matrix_path),
        "p10c_research_scorer_input_matrix_sha256": file_sha256(scorer_matrix_path),
        "baseline_executor_scores_fixture_sha256": file_sha256(baseline_scores_path),
        "shadow_research_contract_scorer_scores_fixture_sha256": file_sha256(shadow_scores_path),
        "baseline_executor_scores_frame_sha256": frame_sha256(baseline_scores),
        "shadow_research_contract_scorer_scores_frame_sha256": frame_sha256(shadow_scores),
        "disabled_hook_status": str(disabled_result.summary.get("status") or ""),
        "disabled_hook_baseline_byte_for_byte_unchanged": bool(
            disabled_result.summary.get("baseline_scores_byte_for_byte_unchanged")
        ),
        "disabled_hook_shadow_artifacts_written_count": int(
            disabled_result.summary.get("shadow_artifacts_written_count") or 0
        ),
        "enabled_hook_status": str(enabled_result.summary.get("status") or ""),
        "enabled_hook_shadow_artifacts_under_proof_artifacts_only": bool(
            enabled_result.summary.get("shadow_artifacts_under_proof_artifacts_only")
        ),
        "enabled_hook_shadow_artifacts_written_count": int(
            enabled_result.summary.get("shadow_artifacts_written_count") or 0
        ),
        "enabled_hook_executor_consumes_baseline_only": bool(
            enabled_result.summary.get("executor_consumes_baseline_only")
        ),
        "enabled_hook_shadow_scorer_referenced_by_executor": bool(
            enabled_result.summary.get("shadow_scorer_referenced_by_executor")
        ),
        "enabled_hook_wrapper_output_scores_hash_equals_baseline": bool(
            enabled_result.summary.get("wrapper_output_scores_hash_equals_baseline")
        ),
        "proof_checks": proof_checks,
        "blockers": blockers,
        "artifacts": {
            "summary": str(summary_path),
            "default_off_scorer_wrapper_contract": str(contract_path),
            "baseline_executor_scores_fixture": str(baseline_scores_path),
            "shadow_research_contract_scorer_scores_fixture": str(shadow_scores_path),
            "disabled_wrapper_summary": str(disabled_summary_path),
            "enabled_wrapper_summary": str(enabled_summary_path),
        },
    }
    write_json(summary_path, summary)
    return summary, 0 if status == "ready" else 2


def build_baseline_executor_scores(scorer_matrix: pd.DataFrame, *, decision_time_utc: str) -> pd.DataFrame:
    symbol_subject = normalize_symbol_subject(scorer_matrix)
    output = symbol_subject.copy()
    output["decision_time_utc"] = decision_time_utc
    output["score"] = 0.0
    output["score_source"] = "baseline_executor_fixture"
    return output[["symbol", "subject", "decision_time_utc", "score", "score_source"]].sort_values("symbol").reset_index(
        drop=True
    )


def build_shadow_scorer_scores(scorer_matrix: pd.DataFrame, *, decision_time_utc: str) -> pd.DataFrame:
    matrix = scorer_matrix.copy()
    symbol_subject = normalize_symbol_subject(matrix)
    feature_columns = [column for column in matrix.columns if column not in {"symbol", "subject"}]
    if not feature_columns:
        output = symbol_subject.copy()
        output["shadow_score"] = 0.0
    else:
        values = matrix[feature_columns].apply(pd.to_numeric, errors="coerce")
        output = symbol_subject.copy()
        output["shadow_score"] = values.mean(axis=1)
    output["decision_time_utc"] = decision_time_utc
    output["score_source"] = "research_contract_shadow_scorer_fixture"
    return output[["symbol", "subject", "decision_time_utc", "shadow_score", "score_source"]].sort_values(
        "symbol"
    ).reset_index(drop=True)


def normalize_symbol_subject(frame: pd.DataFrame) -> pd.DataFrame:
    if not {"symbol", "subject"}.issubset(set(frame.columns)):
        raise ValueError("scorer matrix must include symbol and subject columns")
    output = frame.loc[:, ["symbol", "subject"]].copy()
    output["symbol"] = output["symbol"].astype(str).str.upper()
    output["subject"] = output["subject"].astype(str).str.upper()
    return output


def resolve_p10c_summary(path_ref: Path | str | None) -> Path:
    if path_ref:
        path = resolve_repo_path(path_ref)
        if path.is_dir():
            path = path / "summary.json"
        if not path.exists():
            raise FileNotFoundError(path)
        return path
    candidates = sorted(DEFAULT_P10C_PARENT.glob("*/summary.json"), key=lambda path: path.stat().st_mtime)
    if not candidates:
        raise FileNotFoundError(f"no P10C summary.json found under {DEFAULT_P10C_PARENT}")
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


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


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
    summary, exit_code = run_p10d_default_off_scorer_wrapper(parse_args(argv))
    print(json.dumps(json_safe(summary), indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
