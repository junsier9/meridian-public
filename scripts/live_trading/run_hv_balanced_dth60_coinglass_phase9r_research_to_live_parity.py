from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
QUANT_SCRIPT_DIR = ROOT / "scripts" / "quant_research"
H10D_SCRIPT_DIR = QUANT_SCRIPT_DIR / "h10d_current_diagnostics"
for path in (ROOT, SRC, QUANT_SCRIPT_DIR, H10D_SCRIPT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import analyze_v5_rw_baseline_rebalance_phase_sensitivity as v5_phase  # noqa: E402
import run_dth60_frozen_q90_top20_forward_validation as frozen_forward  # noqa: E402
import run_dth60_overlay_robustness_validation as robust  # noqa: E402
import run_multiphase_factor_drawdown_ablation as factor_ablation  # noqa: E402
import run_portfolio_construction_experiment as portfolio_diag  # noqa: E402

from enhengclaw.quant_research.execution_backtest import (  # noqa: E402
    _cross_sectional_target_weights,
    _scale_cross_sectional_turnover,
    backtest_cross_sectional,
    filter_cross_sectional_execution_frame,
)
from enhengclaw.quant_research.horizon_metrics import SHARPE_METRIC_CONVENTION_VERSION  # noqa: E402
from enhengclaw.quant_research.lab import (  # noqa: E402
    QUANT_ARTIFACTS_ROOT,
    _apply_universe_filter,
    _experiment_directory_name,
    _resolved_execution_cost_models,
)
from enhengclaw.quant_research.overlap_integrity import walk_forward_split_with_purge  # noqa: E402
from enhengclaw.quant_research.split_realization_contract import (  # noqa: E402
    realization_step_bars as split_contract_realization_step_bars,
    resolve_split_realization_contract,
)
from enhengclaw.quant_research.validation_contract import (  # noqa: E402
    execution_capacity_limits,
    validation_contract_reference_capital_usd,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase3_parity import (  # noqa: E402
    COINGLASS_FACTOR,
    OVERLAY_MULTIPLIER_COLUMN,
    OVERLAY_TRIGGER_COLUMN,
    TARGET_FACTOR,
    compute_candidate_score_layer,
    contribution_column_name,
)


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9r_research_to_live_parity.v2"
FROZEN_LABEL = frozen_forward.FROZEN_LABEL
BASELINE_VARIANT_LABEL = frozen_forward.BASELINE_VARIANT_LABEL
ACTIVE_H10D_REGISTRY_PATH = ROOT / "config" / "quant_research" / "active_h10d_registry.json"
DEFAULT_OUTPUT_PARENT = (
    ROOT
    / "artifacts"
    / "live_trading"
    / "hv_balanced_dth60_coinglass_candidate"
    / "phase9r_research_to_live_parity"
)
DEFAULT_RETAINED_FORWARD_ROOT = frozen_forward.DEFAULT_OUTPUT_ROOT
DEFAULT_TOLERANCE = 1e-10
SCORER_MODE_RESEARCH_CONTRACT = "research_h10d_contract"
SCORER_MODE_LIVE_CANONICAL = "live_canonical"
SLICE_NAMES = (
    "full_oos",
    "episode",
    "no_episode_full",
    "selection_ex_episode_pre_holdout",
    "untouched_holdout",
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Replay the frozen dth60 hybrid research forward-validation windows through "
            "the current live candidate wrapper. This is proof-artifact only: no timer, "
            "executor, operator state, order, or fill path is touched."
        )
    )
    parser.add_argument("--episode-start", default="2024-10-31")
    parser.add_argument("--episode-end", default="2024-11-25")
    parser.add_argument("--holdout-start", default="2025-10-01")
    parser.add_argument("--baseline-experiment-id", default=frozen_forward.BASELINE_EXPERIMENT_ID)
    parser.add_argument("--artifacts-root", type=Path, default=QUANT_ARTIFACTS_ROOT)
    parser.add_argument("--validation-contract", type=Path, default=frozen_forward.H10D_VALIDATION_CONTRACT_PATH)
    parser.add_argument("--active-h10d-registry", type=Path, default=ACTIVE_H10D_REGISTRY_PATH)
    parser.add_argument("--research-parent-manifest", type=Path, default=None)
    parser.add_argument("--retained-forward-root", type=Path, default=DEFAULT_RETAINED_FORWARD_ROOT)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--max-windows", type=int, default=0)
    parser.add_argument("--row-sample-limit", type=int, default=200)
    parser.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE)
    parser.add_argument(
        "--candidate-scorer-mode",
        choices=[SCORER_MODE_RESEARCH_CONTRACT, SCORER_MODE_LIVE_CANONICAL],
        default=SCORER_MODE_RESEARCH_CONTRACT,
        help=(
            "Proof-only scorer contract used by the P9R harness. "
            "research_h10d_contract is required before P9C; live_canonical is diagnostic only."
        ),
    )
    parser.add_argument("--skip-retained-artifact-compare", action="store_true")
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe(payload), indent=2, sort_keys=True), encoding="utf-8")


def write_csv(path: Path, rows: Iterable[dict[str, Any]] | pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(rows, pd.DataFrame):
        rows.to_csv(path, index=False)
        return
    materialized = list(rows)
    pd.DataFrame(materialized).to_csv(path, index=False)


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        if not math.isfinite(float(value)):
            return None
        return float(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (pd.Timestamp, datetime)):
        return pd.Timestamp(value).tz_convert("UTC").isoformat().replace("+00:00", "Z")
    if isinstance(value, Path):
        return str(value)
    if pd.isna(value):
        return None
    return value


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_artifact_path(path_ref: str | Path) -> Path:
    path = Path(path_ref)
    if path.exists():
        return path
    if not path.is_absolute():
        candidate = ROOT / path
        if candidate.exists():
            return candidate
        return candidate
    return path


def max_abs_diff(left: pd.Series, right: pd.Series) -> float:
    if len(left) == 0 and len(right) == 0:
        return 0.0
    lnum = pd.to_numeric(left, errors="coerce").fillna(0.0).astype("float64")
    rnum = pd.to_numeric(right, errors="coerce").fillna(0.0).astype("float64")
    return float((lnum - rnum).abs().max()) if len(lnum) else 0.0


def live_trigger_from_research_thresholds(
    frame: pd.DataFrame,
    *,
    shock_quantile: float,
    crowded_top_fraction: float,
    thresholds: dict[str, float],
) -> tuple[pd.Series, pd.Series, pd.DataFrame]:
    tag = robust.q_tag(float(shock_quantile))
    shock_threshold = float(thresholds[f"shock_co_occurrence_index_{tag}"])
    co_jump_threshold = float(thresholds[f"co_jump_count_3d_{tag}"])

    timestamps = pd.to_numeric(frame["timestamp_ms"], errors="coerce").astype("int64")
    shock_by_timestamp = pd.to_numeric(frame["shock_co_occurrence_index"], errors="coerce").groupby(timestamps).first()
    co_jump_by_timestamp = pd.to_numeric(frame["co_jump_count_3d"], errors="coerce").groupby(timestamps).first()
    shock_timestamp_trigger = shock_by_timestamp.ge(shock_threshold) | co_jump_by_timestamp.ge(co_jump_threshold)
    shock_trigger = timestamps.map(shock_timestamp_trigger).fillna(False).astype(bool)

    distance_rank = frame.groupby("timestamp_ms")[TARGET_FACTOR].rank(pct=True, method="average")
    crowded_rank = frame.groupby("timestamp_ms")[COINGLASS_FACTOR].rank(pct=True, method="average")
    crowded_trigger = distance_rank.ge(0.75) & crowded_rank.ge(1.0 - float(crowded_top_fraction))
    trigger = (shock_trigger | crowded_trigger).astype(bool)
    multiplier = pd.Series(np.where(trigger, 0.0, 1.0), index=frame.index, dtype="float64")
    branch_frame = pd.DataFrame(
        {
            "timestamp_ms": timestamps,
            "subject": frame["subject"].astype(str),
            "live_shock_branch_trigger": shock_trigger.astype(bool),
            "live_crowded_branch_trigger": crowded_trigger.astype(bool),
            "live_distance_to_high_60_rank_pct": pd.to_numeric(distance_rank, errors="coerce"),
            "live_coinglass_top_trader_long_pct_smooth_5_rank_pct": pd.to_numeric(crowded_rank, errors="coerce"),
            "live_candidate_overlay_trigger": trigger.astype(bool),
            "live_candidate_overlay_multiplier": multiplier,
        },
        index=frame.index,
    )
    return trigger, multiplier, branch_frame


def expected_target_contribution(
    frame: pd.DataFrame,
    *,
    weights: dict[str, float],
    multiplier: pd.Series,
) -> pd.Series:
    return expected_factor_contribution(
        frame,
        weights=weights,
        factor=TARGET_FACTOR,
        target_factor=TARGET_FACTOR,
        multiplier=multiplier,
    )


def expected_factor_contribution(
    frame: pd.DataFrame,
    *,
    weights: dict[str, float],
    factor: str,
    target_factor: str,
    multiplier: pd.Series,
) -> pd.Series:
    column = str(factor)
    if column not in frame.columns:
        return pd.Series(0.0, index=frame.index, dtype="float64")
    timestamps = frame["timestamp_ms"]
    zscore = v5_phase.lab._timestamp_cross_section_zscore(
        pd.to_numeric(frame[column], errors="coerce"),
        timestamps,
    )
    contribution = zscore * float(weights.get(column, 0.0))
    if column == str(target_factor):
        contribution = contribution * pd.to_numeric(multiplier, errors="coerce")
    return contribution.astype("float64")


def compare_factor_contributions(
    frame: pd.DataFrame,
    live_scored: pd.DataFrame,
    *,
    weights: dict[str, float],
    factor_columns: Iterable[str],
    target_factor: str,
    multiplier: pd.Series,
    window_id: str,
    tolerance: float,
    sample_limit: int,
) -> tuple[dict[str, Any], list[dict[str, Any]], pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    mismatch_frames: list[pd.DataFrame] = []
    stats = {
        "comparison_cell_count": 0,
        "mismatch_count": 0,
        "max_abs_diff": 0.0,
        "factor_count": 0,
    }
    factors = [str(column) for column in factor_columns]
    stats["factor_count"] = int(len(factors))
    for factor in factors:
        expected = expected_factor_contribution(
            frame,
            weights=weights,
            factor=factor,
            target_factor=target_factor,
            multiplier=multiplier,
        )
        contribution_name = contribution_column_name(factor)
        if contribution_name in live_scored.columns:
            actual = pd.to_numeric(live_scored[contribution_name], errors="coerce").fillna(0.0).astype("float64")
        else:
            actual = pd.Series(0.0, index=frame.index, dtype="float64")
        diff = expected - actual
        abs_diff = diff.abs()
        mismatch = abs_diff.gt(float(tolerance))
        row_count = int(len(frame))
        mismatch_count = int(mismatch.sum())
        max_diff = float(abs_diff.max()) if row_count else 0.0
        stats["comparison_cell_count"] += row_count
        stats["mismatch_count"] += mismatch_count
        stats["max_abs_diff"] = max(float(stats["max_abs_diff"]), max_diff)
        rows.append(
            {
                "window_id": str(window_id),
                "factor": factor,
                "weight": float(weights.get(factor, 0.0)),
                "comparison_row_count": row_count,
                "mismatch_count": mismatch_count,
                "max_abs_diff": max_diff,
            }
        )
        if mismatch_count > 0:
            sample = pd.DataFrame(
                {
                    "window_id": str(window_id),
                    "timestamp_ms": pd.to_numeric(frame.loc[mismatch, "timestamp_ms"], errors="coerce")
                    .astype("int64")
                    .to_numpy(),
                    "subject": frame.loc[mismatch, "subject"].astype(str).to_numpy(),
                    "factor": factor,
                    "research_contribution": expected.loc[mismatch].to_numpy(dtype="float64"),
                    "live_contribution": actual.loc[mismatch].to_numpy(dtype="float64"),
                    "abs_diff": abs_diff.loc[mismatch].to_numpy(dtype="float64"),
                }
            ).head(int(sample_limit))
            mismatch_frames.append(sample)
    mismatches = pd.concat(mismatch_frames, ignore_index=True) if mismatch_frames else pd.DataFrame()
    return stats, rows, mismatches


def score_live_candidate_from_research_window(
    frame: pd.DataFrame,
    *,
    weights: dict[str, float],
    trigger: pd.Series,
    multiplier: pd.Series,
    scorer_mode: str = SCORER_MODE_RESEARCH_CONTRACT,
) -> pd.DataFrame:
    live_panel = frame.copy(deep=True)
    live_panel[OVERLAY_TRIGGER_COLUMN] = trigger.astype(bool)
    live_panel[OVERLAY_MULTIPLIER_COLUMN] = pd.to_numeric(multiplier, errors="coerce").astype("float64")
    mode = str(scorer_mode or SCORER_MODE_RESEARCH_CONTRACT).strip()
    if mode == SCORER_MODE_LIVE_CANONICAL:
        return compute_candidate_score_layer(
            live_panel,
            feature_columns=list(weights.keys()),
            feature_weights=dict(weights),
            target_factor=TARGET_FACTOR,
            overlay_enabled=True,
            overlay_multiplier_column=OVERLAY_MULTIPLIER_COLUMN,
        )
    if mode != SCORER_MODE_RESEARCH_CONTRACT:
        raise ValueError(f"unsupported P9R scorer mode: {mode}")
    return compute_research_contract_candidate_score_layer(
        live_panel,
        feature_columns=list(weights.keys()),
        feature_weights=dict(weights),
        target_factor=TARGET_FACTOR,
        overlay_enabled=True,
        overlay_multiplier_column=OVERLAY_MULTIPLIER_COLUMN,
    )


def compute_research_contract_candidate_score_layer(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str],
    feature_weights: dict[str, float],
    target_factor: str,
    overlay_enabled: bool,
    overlay_multiplier_column: str,
) -> pd.DataFrame:
    features = [str(item) for item in feature_columns]
    missing = [column for column in features if column not in frame.columns]
    if missing:
        raise ValueError(f"missing research-contract feature columns: {missing}")
    if target_factor not in features:
        raise ValueError(f"target factor is not in research-contract feature columns: {target_factor}")
    if overlay_enabled and overlay_multiplier_column not in frame.columns:
        raise ValueError(f"missing overlay multiplier column: {overlay_multiplier_column}")
    if "timestamp_ms" not in frame.columns:
        raise ValueError("missing timestamp_ms column")

    output = frame.copy(deep=True)
    timestamps = output["timestamp_ms"]
    overlay_multiplier = (
        pd.to_numeric(output[overlay_multiplier_column], errors="coerce").fillna(1.0).clip(lower=0.0, upper=1.0)
        if overlay_enabled
        else pd.Series(1.0, index=output.index, dtype="float64")
    )
    raw_score = pd.Series(0.0, index=output.index, dtype="float64")
    for column in features:
        values = pd.to_numeric(output[column], errors="coerce")
        if not values.notna().any():
            continue
        zscore = v5_phase.lab._timestamp_cross_section_zscore(values, timestamps)
        contribution = zscore * float(feature_weights.get(column, 0.0))
        if overlay_enabled and column == target_factor:
            contribution = contribution * overlay_multiplier
        contribution_name = contribution_column_name(column)
        output[contribution_name] = contribution.astype("float64")
        raw_score = raw_score + output[contribution_name]
    centered_rank = v5_phase.lab._timestamp_cross_section_percentile_rank(raw_score, timestamps) - 0.5
    output["raw_score"] = raw_score.astype("float64")
    output["score"] = pd.Series(np.tanh(centered_rank * 1.80), index=output.index, dtype="float64")
    return output


def target_weight_trace(
    frame: pd.DataFrame,
    *,
    constraints: dict[str, Any],
    split_contract: dict[str, Any],
    window_id: str,
) -> pd.DataFrame:
    execution_frame = filter_cross_sectional_execution_frame(frame=frame, constraints=constraints)
    if execution_frame.empty:
        return pd.DataFrame(columns=["window_id", "timestamp_ms", "subject", "target_weight"])
    ordered = execution_frame.sort_values(["timestamp_ms", "subject"]).copy()
    timestamps = sorted(pd.to_numeric(ordered["timestamp_ms"], errors="coerce").dropna().astype("int64").unique())
    step = max(split_contract_realization_step_bars(split_contract), 1)
    previous_weights: dict[str, float] = {}
    rows: list[dict[str, Any]] = []
    for timestamp_ms in timestamps[::step]:
        decision_group = ordered.loc[pd.to_numeric(ordered["timestamp_ms"], errors="coerce").astype("int64").eq(timestamp_ms)]
        raw_target_weights = _cross_sectional_target_weights(
            decision_group=decision_group,
            constraints=constraints,
            previous_weights=previous_weights,
        )
        raw_target_weights = apply_research_target_adjustments(
            raw_target_weights=raw_target_weights,
            decision_group=decision_group,
            constraints=constraints,
        )
        actual_weights = _scale_cross_sectional_turnover(
            raw_target_weights=raw_target_weights,
            previous_weights=previous_weights,
            max_turnover_per_rebalance=float(constraints.get("max_turnover_per_rebalance", math.inf) or math.inf),
            turnover_mode=str(constraints.get("pair_turnover_mode") or constraints.get("turnover_mode") or "").strip().lower()
            or None,
        )
        union_subjects = sorted(set(previous_weights) | set(actual_weights))
        for subject in union_subjects:
            rows.append(
                {
                    "window_id": str(window_id),
                    "timestamp_ms": int(timestamp_ms),
                    "subject": str(subject),
                    "target_weight": float(actual_weights.get(subject, 0.0)),
                }
            )
        previous_weights = {str(subject): float(weight) for subject, weight in actual_weights.items()}
    return pd.DataFrame(rows)


def apply_research_target_adjustments(
    *,
    raw_target_weights: dict[str, float],
    decision_group: pd.DataFrame,
    constraints: dict[str, Any],
) -> dict[str, float]:
    adjusted = dict(raw_target_weights)
    short_multiplier_column = str(constraints.get("short_position_weight_multiplier_column") or "").strip()
    if short_multiplier_column and adjusted and not decision_group.empty and short_multiplier_column in decision_group.columns:
        multiplier_series = pd.to_numeric(decision_group[short_multiplier_column], errors="coerce").fillna(1.0).clip(
            lower=0.0,
            upper=1.0,
        )
        multiplier_by_subject = {
            str(subject): float(multiplier)
            for subject, multiplier in zip(decision_group["subject"], multiplier_series)
        }
        adjusted = {
            str(subject): (float(weight) * float(multiplier_by_subject.get(str(subject), 1.0)) if float(weight) < 0.0 else float(weight))
            for subject, weight in adjusted.items()
            if abs(float(weight)) > 1e-12
        }
    overlay_id = str(constraints.get("position_multiplier_overlay_id") or "").strip() or None
    if overlay_id is not None and adjusted and not decision_group.empty:
        from enhengclaw.quant_research.multiplier_overlay import position_multiplier_lookup

        lookup = position_multiplier_lookup(
            overlay_id,
            overlay_context=dict(constraints.get("position_multiplier_overlay_context") or {}),
        )
        if lookup is not None:
            multiplier = float(lookup(int(decision_group["timestamp_ms"].iloc[0])))
            if multiplier < 1.0:
                adjusted = {str(subject): float(weight) * multiplier for subject, weight in adjusted.items()}
    return {str(subject): float(weight) for subject, weight in adjusted.items() if abs(float(weight)) > 1e-12}


def compare_target_weight_traces(
    research_trace: pd.DataFrame,
    live_trace: pd.DataFrame,
    *,
    tolerance: float,
) -> tuple[dict[str, Any], pd.DataFrame]:
    keys = ["window_id", "timestamp_ms", "subject"]
    left = research_trace.rename(columns={"target_weight": "research_target_weight"})
    right = live_trace.rename(columns={"target_weight": "live_target_weight"})
    merged = left.merge(right, on=keys, how="outer")
    for column in ("research_target_weight", "live_target_weight"):
        merged[column] = pd.to_numeric(merged[column], errors="coerce").fillna(0.0)
    merged["target_weight_abs_diff"] = (merged["research_target_weight"] - merged["live_target_weight"]).abs()
    mismatches = merged.loc[merged["target_weight_abs_diff"].gt(float(tolerance))].copy()
    stats = {
        "comparison_row_count": int(len(merged)),
        "mismatch_count": int(len(mismatches)),
        "max_abs_diff": float(merged["target_weight_abs_diff"].max()) if len(merged) else 0.0,
    }
    return stats, mismatches


def compare_metric_frames(
    left: pd.DataFrame,
    right: pd.DataFrame,
    *,
    keys: list[str],
    metrics: list[str],
    tolerance: float,
) -> tuple[dict[str, Any], pd.DataFrame]:
    lcols = keys + metrics
    rcols = keys + metrics
    merged = left[lcols].merge(right[rcols], on=keys, how="outer", suffixes=("_research", "_live"))
    mismatch_mask = pd.Series(False, index=merged.index)
    max_diff = 0.0
    for metric in metrics:
        lcol = f"{metric}_research"
        rcol = f"{metric}_live"
        merged[lcol] = pd.to_numeric(merged[lcol], errors="coerce").fillna(0.0)
        merged[rcol] = pd.to_numeric(merged[rcol], errors="coerce").fillna(0.0)
        diff_col = f"{metric}_abs_diff"
        merged[diff_col] = (merged[lcol] - merged[rcol]).abs()
        if len(merged):
            max_diff = max(max_diff, float(merged[diff_col].max()))
        mismatch_mask = mismatch_mask | merged[diff_col].gt(float(tolerance))
    mismatches = merged.loc[mismatch_mask].copy()
    return {
        "comparison_row_count": int(len(merged)),
        "mismatch_count": int(len(mismatches)),
        "max_abs_diff": float(max_diff),
    }, mismatches


def build_slice_metrics(
    periods: pd.DataFrame,
    *,
    split_contract: dict[str, Any],
    episode_start: str,
    episode_end: str,
    holdout_start: str,
    label: str,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for slice_name in SLICE_NAMES:
        slice_frame = robust.slice_periods(
            periods,
            slice_name=slice_name,
            episode_start=episode_start,
            episode_end=episode_end,
            holdout_start=holdout_start,
        )
        rows.append(
            {
                "label": str(label),
                "slice": slice_name,
                **robust.metrics_for_periods(slice_frame, split_contract=split_contract),
            }
        )
    return pd.DataFrame(rows)


def load_research_scorer_contract(
    *,
    active_h10d_registry_path: Path,
    research_parent_manifest_path: Path | None,
) -> dict[str, Any]:
    registry_path = resolve_artifact_path(active_h10d_registry_path)
    registry = load_json(registry_path)
    canonical_parent = dict(registry.get("canonical_parent") or {})
    effective_baseline = dict(registry.get("effective_research_baseline") or {})
    portfolio_baseline = dict(registry.get("portfolio_construction_baseline") or {})
    manifest_ref = research_parent_manifest_path or canonical_parent.get("manifest_path")
    if manifest_ref is None:
        raise RuntimeError("active h10d registry does not provide canonical_parent.manifest_path")
    manifest_path = resolve_artifact_path(manifest_ref)
    manifest = load_json(manifest_path)
    expected_strategy_id = str(canonical_parent.get("strategy_id") or "")
    entries = [dict(item) for item in list(manifest.get("entries") or [])]
    selected_entry = next(
        (entry for entry in entries if str(entry.get("candidate_id") or "") == expected_strategy_id),
        entries[0] if entries else {},
    )
    thesis_profile = dict(selected_entry.get("thesis_profile") or {})
    required_features = list(
        selected_entry.get("required_feature_columns")
        or thesis_profile.get("required_feature_columns")
        or []
    )
    return {
        "contract_version": "research_h10d_12_factor_scorer_contract.v1",
        "active_h10d_registry_path": str(registry_path),
        "active_h10d_registry_sha256": file_sha256(registry_path),
        "research_parent_manifest_path": str(manifest_path),
        "research_parent_manifest_sha256": file_sha256(manifest_path),
        "canonical_parent_label": str(canonical_parent.get("label") or ""),
        "canonical_parent_strategy_id": expected_strategy_id,
        "effective_research_baseline": str(effective_baseline.get("label") or ""),
        "portfolio_construction_baseline": portfolio_baseline,
        "manifest_contract_version": str(manifest.get("contract_version") or ""),
        "manifest_lifecycle": str(manifest.get("lifecycle") or ""),
        "manifest_promotion_eligibility": str(manifest.get("promotion_eligibility") or ""),
        "selected_entry_candidate_id": str(selected_entry.get("candidate_id") or ""),
        "dataset_profile": str(selected_entry.get("dataset_profile") or thesis_profile.get("dataset_profile") or ""),
        "model_family": str(selected_entry.get("model_family") or ""),
        "target_horizon_bars": int(selected_entry.get("target_horizon_bars") or thesis_profile.get("intended_holding_horizon_bars") or 0),
        "requires_derivatives_features": bool(thesis_profile.get("requires_derivatives_features", False)),
        "required_feature_columns": [str(column) for column in required_features],
        "required_feature_count": int(len(required_features)),
        "factor_formula": str(thesis_profile.get("factor_formula") or ""),
        "profile_constraints": dict(selected_entry.get("profile_constraints") or {}),
        "universe_filter": dict(selected_entry.get("universe_filter") or thesis_profile.get("universe_rule") or {}),
        "overlay_id": (manifest.get("lineage") or {}).get("overlay_id"),
        "spec_hash": str(selected_entry.get("spec_hash") or ""),
    }


def validate_research_scorer_contract(
    *,
    contract: dict[str, Any],
    context: dict[str, Any],
    split_contract: dict[str, Any],
    constraints: dict[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    required = [str(column) for column in list(contract.get("required_feature_columns") or [])]
    active = [str(column) for column in list(context.get("active_factor_columns") or [])]
    frame = context["frame"]
    missing_from_frame = [column for column in required if column not in frame.columns]
    missing_from_active = [column for column in required if column not in active]
    extra_active = [column for column in active if column not in required]
    formula = str(contract.get("factor_formula") or "")
    portfolio_baseline = dict(contract.get("portfolio_construction_baseline") or {})
    expected_phase_offsets = [int(item) for item in list(portfolio_diag.MULTIPHASE_PHASES)]
    registry_phase_offsets = [int(item) for item in list(portfolio_baseline.get("phase_offsets_days") or [])]

    checks = {
        "required_feature_count_is_12": int(len(required)) == 12,
        "active_factor_columns_equal_required_features_in_order": active == required,
        "all_required_features_present_in_panel": not missing_from_frame,
        "all_required_features_active_in_scorer": not missing_from_active and not extra_active,
        "target_horizon_bars_match_manifest": int(split_contract.get("target_horizon_bars") or 0)
        == int(contract.get("target_horizon_bars") or 0),
        "realization_step_bars_is_h10d": int(split_contract.get("realization_step_bars") or 0) == 10,
        "top_bottom_three_long_short_constraints": (
            int(constraints.get("top_long_count") or 0) == 3
            and int(constraints.get("bottom_short_count") or 0) == 3
            and bool(constraints.get("short_allowed")) is True
            and abs(float(constraints.get("long_leverage") or 0.0) - 0.5) <= 1e-12
            and abs(float(constraints.get("short_leverage") or 0.0) - 0.5) <= 1e-12
        ),
        "no_position_multiplier_overlay_in_parent": not constraints.get("position_multiplier_overlay_id")
        and contract.get("overlay_id") is None,
        "train_window_signed_ir_formula_bound": (
            "Spearman IC" in formula
            and "target_execution_forward_return" in formula
            and "abs-sum 1.0" in formula
            and "tanh" in formula
        ),
        "registry_multiphase_10_sleeve_bound": (
            str(portfolio_baseline.get("target_engine") or "") == "multiphase_equal_sleeve"
            and registry_phase_offsets == expected_phase_offsets
            and abs(float(portfolio_baseline.get("sleeve_weight") or 0.0) - float(portfolio_diag.MULTIPHASE_SLEEVE_WEIGHT))
            <= 1e-12
        ),
    }
    for name, passed in checks.items():
        if not bool(passed):
            blockers.append(name)
    return {
        "status": "ready" if not blockers else "blocked",
        "blockers": blockers,
        "checks": checks,
        "required_feature_columns": required,
        "active_factor_columns": active,
        "missing_required_features_from_panel": missing_from_frame,
        "missing_required_features_from_active_scorer": missing_from_active,
        "extra_active_factor_columns": extra_active,
        "panel": {
            "execution_eligible_row_count": int(len(frame)),
            "execution_eligible_subject_count": int(frame["subject"].nunique()) if "subject" in frame.columns else 0,
            "execution_eligible_timestamp_count": int(frame["timestamp_ms"].nunique()) if "timestamp_ms" in frame.columns else 0,
        },
    }


def run_research_to_live_parity(
    args: argparse.Namespace,
    *,
    now_fn=utc_now,
) -> tuple[dict[str, Any], int]:
    started_at = now_fn()
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")
    output_root = Path(args.output_root) if args.output_root is not None else DEFAULT_OUTPUT_PARENT / run_id
    output_root.mkdir(parents=True, exist_ok=True)

    tolerance = float(args.tolerance)
    scorer_mode = str(getattr(args, "candidate_scorer_mode", SCORER_MODE_RESEARCH_CONTRACT) or SCORER_MODE_RESEARCH_CONTRACT)
    blockers: list[str] = []
    retained_forward_root = Path(args.retained_forward_root)
    max_windows = max(int(args.max_windows or 0), 0)
    compare_retained = not bool(args.skip_retained_artifact_compare) and max_windows == 0

    context = build_research_context(args)
    frame = context["frame"]
    split_contract = context["split_contract"]
    constraints = context["constraints"]
    base_execution_cost_model = context["base_execution_cost_model"]
    reference_capital_usd = context["reference_capital_usd"]
    capacity_limits = context["capacity_limits"]
    active_factor_columns = context["active_factor_columns"]
    daily_ic_by_factor = context["daily_ic_by_factor"]
    research_scorer_contract = load_research_scorer_contract(
        active_h10d_registry_path=Path(args.active_h10d_registry),
        research_parent_manifest_path=Path(args.research_parent_manifest) if args.research_parent_manifest else None,
    )
    research_scorer_contract_checks = validate_research_scorer_contract(
        contract=research_scorer_contract,
        context=context,
        split_contract=split_contract,
        constraints=constraints,
    )
    blockers.extend([f"research_scorer_contract_{item}" for item in research_scorer_contract_checks.get("blockers", [])])
    inventory_cap = float(capacity_limits["max_inventory_participation_rate_max"])
    trade_cap = float(capacity_limits["max_trade_participation_rate_max"])
    if bool(constraints.get("drawdown_throttle_enabled", False)):
        blockers.append("target_weight_trace_drawdown_throttle_not_supported")

    definitions = {str(item["label"]): dict(item) for item in frozen_forward.build_definitions()}
    candidate_definition = definitions[FROZEN_LABEL]
    baseline_definition = definitions[BASELINE_VARIANT_LABEL]

    generated_threshold_rows: list[dict[str, Any]] = []
    research_window_rows: list[dict[str, Any]] = []
    live_window_rows: list[dict[str, Any]] = []
    wfo_weight_rows: list[dict[str, Any]] = []
    row_parity_rows: list[dict[str, Any]] = []
    factor_contribution_rows: list[dict[str, Any]] = []
    factor_contribution_mismatch_frames: list[pd.DataFrame] = []
    row_mismatch_rows: list[dict[str, Any]] = []
    target_mismatch_frames: list[pd.DataFrame] = []
    target_sample_frames: list[pd.DataFrame] = []
    phase_candidate_research_periods: list[pd.DataFrame] = []
    phase_candidate_live_periods: list[pd.DataFrame] = []
    phase_baseline_research_periods: list[pd.DataFrame] = []

    row_parity_stats = {
        "row_count": 0,
        "trigger_mismatch_count": 0,
        "multiplier_mismatch_count": 0,
        "target_contribution_mismatch_count": 0,
        "score_mismatch_count": 0,
        "trigger_max_abs_diff": 0.0,
        "multiplier_max_abs_diff": 0.0,
        "target_contribution_max_abs_diff": 0.0,
        "score_max_abs_diff": 0.0,
    }
    factor_contribution_stats = {
        "comparison_cell_count": 0,
        "mismatch_count": 0,
        "max_abs_diff": 0.0,
        "factor_count": int(len(active_factor_columns)),
    }
    wfo_weight_stats = {
        "window_count": 0,
        "factor_count": int(len(active_factor_columns)),
        "row_count": 0,
        "missing_weight_count": 0,
        "max_abs_weight_sum_deviation_from_one": 0.0,
        "min_abs_weight_sum": None,
        "max_abs_weight_sum": None,
    }
    target_weight_stats = {"comparison_row_count": 0, "mismatch_count": 0, "max_abs_diff": 0.0}
    processed_windows = 0

    for phase in portfolio_diag.MULTIPHASE_PHASES:
        phase_data, phase_audit = portfolio_diag._phase_frame(frame, phase_offset_days=phase)
        if phase_data.empty:
            continue
        phase_time_index = pd.to_datetime(phase_data["timestamp_ms"], unit="ms", utc=True)
        current_anchor = phase_time_index.min() + timedelta(days=120)
        final_anchor = phase_time_index.max() - timedelta(days=30)
        while current_anchor <= final_anchor:
            train_end = current_anchor - timedelta(days=30)
            validation_end = current_anchor
            test_end = current_anchor + timedelta(days=30)
            train_df, validation_df, test_df = walk_forward_split_with_purge(
                frame=phase_data,
                time_col="timestamp_ms",
                train_end=train_end,
                validation_end=validation_end,
                test_end=test_end,
                split_realization_contract=split_contract,
            )
            current_anchor += timedelta(days=30)
            if train_df.empty or validation_df.empty or test_df.empty:
                continue
            if max_windows and processed_windows >= max_windows:
                break

            processed_windows += 1
            train_end_ms = int(pd.to_numeric(train_df["timestamp_ms"], errors="coerce").max())
            weights = v5_phase.weights_for_train_end(
                daily_ic_by_factor=daily_ic_by_factor,
                train_end_ms=train_end_ms,
            )
            weights = {str(column): float(weights[column]) for column in active_factor_columns if column in weights}
            thresholds = robust.robustness_thresholds(train_df)
            generated_threshold_rows.append(
                {
                    "phase_offset_days": int(phase),
                    "train_end_utc": train_end.isoformat().replace("+00:00", "Z"),
                    "validation_end_utc": validation_end.isoformat().replace("+00:00", "Z"),
                    **thresholds,
                }
            )

            window_id = "|".join(
                [
                    f"phase={int(phase)}",
                    f"train_end={train_end.isoformat().replace('+00:00', 'Z')}",
                    f"validation_end={validation_end.isoformat().replace('+00:00', 'Z')}",
                ]
            )
            missing_window_weights = [column for column in active_factor_columns if column not in weights]
            abs_weight_sum = float(sum(abs(float(weights.get(column, 0.0))) for column in active_factor_columns))
            wfo_weight_stats["window_count"] += 1
            wfo_weight_stats["row_count"] += int(len(active_factor_columns))
            wfo_weight_stats["missing_weight_count"] += int(len(missing_window_weights))
            wfo_weight_stats["max_abs_weight_sum_deviation_from_one"] = max(
                float(wfo_weight_stats["max_abs_weight_sum_deviation_from_one"]),
                abs(abs_weight_sum - 1.0),
            )
            wfo_weight_stats["min_abs_weight_sum"] = (
                abs_weight_sum
                if wfo_weight_stats["min_abs_weight_sum"] is None
                else min(float(wfo_weight_stats["min_abs_weight_sum"]), abs_weight_sum)
            )
            wfo_weight_stats["max_abs_weight_sum"] = (
                abs_weight_sum
                if wfo_weight_stats["max_abs_weight_sum"] is None
                else max(float(wfo_weight_stats["max_abs_weight_sum"]), abs_weight_sum)
            )
            for factor in active_factor_columns:
                wfo_weight_rows.append(
                    {
                        "window_id": window_id,
                        "phase_offset_days": int(phase),
                        "train_end_utc": train_end.isoformat().replace("+00:00", "Z"),
                        "validation_end_utc": validation_end.isoformat().replace("+00:00", "Z"),
                        "factor": str(factor),
                        "weight": float(weights.get(factor, 0.0)),
                        "abs_weight_sum": abs_weight_sum,
                        "missing_weight": bool(factor not in weights),
                    }
                )
            test_times = pd.to_datetime(test_df["timestamp_ms"], unit="ms", utc=True)
            research_candidate, overlay_stats = robust.score_frame_with_robust_overlay(
                test_df,
                factor_weights=weights,
                variant=candidate_definition,
                thresholds=thresholds,
            )
            research_baseline, _ = robust.score_frame_with_robust_overlay(
                test_df,
                factor_weights=weights,
                variant=baseline_definition,
                thresholds=thresholds,
            )
            live_trigger, live_multiplier, branch_frame = live_trigger_from_research_thresholds(
                test_df,
                shock_quantile=float(candidate_definition["shock_quantile"]),
                crowded_top_fraction=float(candidate_definition["crowded_top_fraction"]),
                thresholds=thresholds,
            )
            research_trigger = research_candidate["dth60_overlay_triggered"].astype(bool)
            research_multiplier = pd.to_numeric(research_candidate["dth60_overlay_multiplier"], errors="coerce")
            live_candidate = score_live_candidate_from_research_window(
                test_df,
                weights=weights,
                trigger=live_trigger,
                multiplier=live_multiplier,
                scorer_mode=scorer_mode,
            )
            expected_contribution = expected_target_contribution(
                test_df,
                weights=weights,
                multiplier=research_multiplier,
            )
            live_contribution = pd.to_numeric(
                live_candidate[contribution_column_name(TARGET_FACTOR)],
                errors="coerce",
            )
            contribution_window_stats, contribution_window_rows, contribution_window_mismatches = (
                compare_factor_contributions(
                    test_df,
                    live_candidate,
                    weights=weights,
                    factor_columns=active_factor_columns,
                    target_factor=TARGET_FACTOR,
                    multiplier=research_multiplier,
                    window_id=window_id,
                    tolerance=tolerance,
                    sample_limit=int(args.row_sample_limit),
                )
            )
            factor_contribution_stats["comparison_cell_count"] += int(
                contribution_window_stats["comparison_cell_count"]
            )
            factor_contribution_stats["mismatch_count"] += int(contribution_window_stats["mismatch_count"])
            factor_contribution_stats["max_abs_diff"] = max(
                float(factor_contribution_stats["max_abs_diff"]),
                float(contribution_window_stats["max_abs_diff"]),
            )
            factor_contribution_rows.extend(contribution_window_rows)
            if not contribution_window_mismatches.empty:
                factor_contribution_mismatch_frames.append(contribution_window_mismatches)

            trigger_diff = research_trigger.astype(int) - live_trigger.astype(int)
            multiplier_diff = research_multiplier - live_multiplier
            contribution_diff = expected_contribution - live_contribution
            score_diff = pd.to_numeric(research_candidate["score"], errors="coerce") - pd.to_numeric(
                live_candidate["score"],
                errors="coerce",
            )
            trigger_mismatch = trigger_diff.ne(0)
            multiplier_mismatch = multiplier_diff.abs().gt(tolerance)
            contribution_mismatch = contribution_diff.abs().gt(tolerance)
            score_mismatch = score_diff.abs().gt(tolerance)
            any_mismatch = trigger_mismatch | multiplier_mismatch | contribution_mismatch | score_mismatch

            row_count = int(len(test_df))
            row_parity_stats["row_count"] += row_count
            row_parity_stats["trigger_mismatch_count"] += int(trigger_mismatch.sum())
            row_parity_stats["multiplier_mismatch_count"] += int(multiplier_mismatch.sum())
            row_parity_stats["target_contribution_mismatch_count"] += int(contribution_mismatch.sum())
            row_parity_stats["score_mismatch_count"] += int(score_mismatch.sum())
            row_parity_stats["trigger_max_abs_diff"] = max(
                row_parity_stats["trigger_max_abs_diff"],
                float(trigger_diff.abs().max()) if row_count else 0.0,
            )
            row_parity_stats["multiplier_max_abs_diff"] = max(
                row_parity_stats["multiplier_max_abs_diff"],
                float(multiplier_diff.abs().max()) if row_count else 0.0,
            )
            row_parity_stats["target_contribution_max_abs_diff"] = max(
                row_parity_stats["target_contribution_max_abs_diff"],
                float(contribution_diff.abs().max()) if row_count else 0.0,
            )
            row_parity_stats["score_max_abs_diff"] = max(
                row_parity_stats["score_max_abs_diff"],
                float(score_diff.abs().max()) if row_count else 0.0,
            )

            window_row_summary = {
                "window_id": window_id,
                "phase_offset_days": int(phase),
                "phase_start_date_utc": phase_audit.get("start_date_utc"),
                "train_end_utc": train_end.isoformat().replace("+00:00", "Z"),
                "validation_end_utc": validation_end.isoformat().replace("+00:00", "Z"),
                "test_start_utc": test_times.min().isoformat().replace("+00:00", "Z"),
                "test_end_utc": test_times.max().isoformat().replace("+00:00", "Z"),
                "test_row_count": row_count,
                "trigger_mismatch_count": int(trigger_mismatch.sum()),
                "multiplier_max_abs_diff": float(multiplier_diff.abs().max()) if row_count else 0.0,
                "target_contribution_max_abs_diff": float(contribution_diff.abs().max()) if row_count else 0.0,
                "score_max_abs_diff": float(score_diff.abs().max()) if row_count else 0.0,
            }
            row_parity_rows.append(window_row_summary)

            if any_mismatch.any():
                mismatch_frame = pd.concat(
                    [
                        test_df.loc[any_mismatch, ["timestamp_ms", "subject"]].reset_index(drop=True),
                        branch_frame.loc[any_mismatch]
                        .drop(columns=["timestamp_ms", "subject"], errors="ignore")
                        .reset_index(drop=True),
                        pd.DataFrame(
                            {
                                "window_id": window_id,
                                "research_trigger": research_trigger.loc[any_mismatch].to_numpy(),
                                "live_trigger": live_trigger.loc[any_mismatch].to_numpy(),
                                "research_multiplier": research_multiplier.loc[any_mismatch].to_numpy(),
                                "live_multiplier": live_multiplier.loc[any_mismatch].to_numpy(),
                                "target_contribution_abs_diff": contribution_diff.loc[any_mismatch].abs().to_numpy(),
                                "score_abs_diff": score_diff.loc[any_mismatch].abs().to_numpy(),
                            }
                        ),
                    ],
                    axis=1,
                )
                row_mismatch_rows.extend(mismatch_frame.head(int(args.row_sample_limit)).to_dict(orient="records"))

            research_metrics = backtest_cross_sectional(
                frame=research_candidate,
                constraints=constraints,
                split_realization_contract=split_contract,
                execution_cost_model=base_execution_cost_model,
                reference_capital_usd=reference_capital_usd,
                capacity_limits=capacity_limits,
                include_periods=True,
            )
            live_metrics = backtest_cross_sectional(
                frame=live_candidate,
                constraints=constraints,
                split_realization_contract=split_contract,
                execution_cost_model=base_execution_cost_model,
                reference_capital_usd=reference_capital_usd,
                capacity_limits=capacity_limits,
                include_periods=True,
            )
            baseline_metrics = backtest_cross_sectional(
                frame=research_baseline,
                constraints=constraints,
                split_realization_contract=split_contract,
                execution_cost_model=base_execution_cost_model,
                reference_capital_usd=reference_capital_usd,
                capacity_limits=capacity_limits,
                include_periods=True,
            )

            research_window_rows.append(
                build_window_metric_row(
                    label=FROZEN_LABEL,
                    kind=str(candidate_definition["kind"]),
                    definition=candidate_definition,
                    phase=int(phase),
                    phase_audit=phase_audit,
                    train_end=train_end,
                    validation_end=validation_end,
                    test_times=test_times,
                    metrics=research_metrics,
                    overlay_stats=overlay_stats,
                )
            )
            live_window_rows.append(
                build_window_metric_row(
                    label=FROZEN_LABEL,
                    kind=str(candidate_definition["kind"]),
                    definition=candidate_definition,
                    phase=int(phase),
                    phase_audit=phase_audit,
                    train_end=train_end,
                    validation_end=validation_end,
                    test_times=test_times,
                    metrics=live_metrics,
                    overlay_stats=overlay_stats,
                )
            )

            research_period_frame = factor_ablation.period_frame_from_metrics(
                label=FROZEN_LABEL,
                phase=phase,
                metrics=research_metrics,
            )
            live_period_frame = factor_ablation.period_frame_from_metrics(
                label=FROZEN_LABEL,
                phase=phase,
                metrics=live_metrics,
            )
            baseline_period_frame = factor_ablation.period_frame_from_metrics(
                label=BASELINE_VARIANT_LABEL,
                phase=phase,
                metrics=baseline_metrics,
            )
            if not research_period_frame.empty:
                phase_candidate_research_periods.append(research_period_frame)
            if not live_period_frame.empty:
                phase_candidate_live_periods.append(live_period_frame)
            if not baseline_period_frame.empty:
                phase_baseline_research_periods.append(baseline_period_frame)

            research_trace = target_weight_trace(
                research_candidate,
                constraints=constraints,
                split_contract=split_contract,
                window_id=window_id,
            )
            live_trace = target_weight_trace(
                live_candidate,
                constraints=constraints,
                split_contract=split_contract,
                window_id=window_id,
            )
            trace_stats, trace_mismatches = compare_target_weight_traces(
                research_trace,
                live_trace,
                tolerance=tolerance,
            )
            target_weight_stats["comparison_row_count"] += int(trace_stats["comparison_row_count"])
            target_weight_stats["mismatch_count"] += int(trace_stats["mismatch_count"])
            target_weight_stats["max_abs_diff"] = max(
                float(target_weight_stats["max_abs_diff"]),
                float(trace_stats["max_abs_diff"]),
            )
            if not trace_mismatches.empty:
                target_mismatch_frames.append(trace_mismatches)
            if len(target_sample_frames) < 5 and not research_trace.empty:
                target_sample_frames.append(
                    research_trace.merge(
                        live_trace,
                        on=["window_id", "timestamp_ms", "subject"],
                        how="outer",
                        suffixes=("_research", "_live"),
                    ).head(40)
                )

        if max_windows and processed_windows >= max_windows:
            break

    research_candidate_periods = factor_ablation.aggregate_variant_periods(
        label=FROZEN_LABEL,
        sleeve_periods=phase_candidate_research_periods,
        trade_participation_cap=trade_cap,
        inventory_participation_cap=inventory_cap,
    )
    live_candidate_periods = factor_ablation.aggregate_variant_periods(
        label=FROZEN_LABEL,
        sleeve_periods=phase_candidate_live_periods,
        trade_participation_cap=trade_cap,
        inventory_participation_cap=inventory_cap,
    )
    baseline_periods = factor_ablation.aggregate_variant_periods(
        label=BASELINE_VARIANT_LABEL,
        sleeve_periods=phase_baseline_research_periods,
        trade_participation_cap=trade_cap,
        inventory_participation_cap=inventory_cap,
    )

    research_slice_metrics = build_slice_metrics(
        research_candidate_periods,
        split_contract=split_contract,
        episode_start=str(args.episode_start),
        episode_end=str(args.episode_end),
        holdout_start=str(args.holdout_start),
        label=FROZEN_LABEL,
    )
    live_slice_metrics = build_slice_metrics(
        live_candidate_periods,
        split_contract=split_contract,
        episode_start=str(args.episode_start),
        episode_end=str(args.episode_end),
        holdout_start=str(args.holdout_start),
        label=FROZEN_LABEL,
    )
    slice_metric_fields = [
        "period_count",
        "cumulative_return",
        "h10d_equivalent_sharpe",
        "max_drawdown",
        "loss_period_fraction",
        "mean_period_return",
        "turnover_total",
        "max_trade_participation_rate",
        "capacity_breach_count",
    ]
    slice_metric_stats, slice_metric_mismatches = compare_metric_frames(
        research_slice_metrics,
        live_slice_metrics,
        keys=["label", "slice"],
        metrics=slice_metric_fields,
        tolerance=tolerance,
    )

    retained_compare = compare_retained_forward_artifacts(
        retained_forward_root=retained_forward_root,
        generated_threshold_rows=pd.DataFrame(generated_threshold_rows),
        generated_window_rows=pd.DataFrame(research_window_rows),
        generated_slice_metrics=build_research_style_slice_summary(
            baseline_periods=baseline_periods,
            candidate_periods=research_candidate_periods,
            split_contract=split_contract,
            episode_start=str(args.episode_start),
            episode_end=str(args.episode_end),
            holdout_start=str(args.holdout_start),
        ),
        tolerance=tolerance,
        enabled=compare_retained,
    )
    blockers.extend(retained_compare.get("blockers", []))

    if processed_windows <= 0:
        blockers.append("no_wfo_windows_processed")
    if int(row_parity_stats["trigger_mismatch_count"]) > 0:
        blockers.append("trigger_mismatch")
    if int(row_parity_stats["multiplier_mismatch_count"]) > 0:
        blockers.append("multiplier_mismatch")
    if int(row_parity_stats["target_contribution_mismatch_count"]) > 0:
        blockers.append("target_contribution_mismatch")
    if int(row_parity_stats["score_mismatch_count"]) > 0:
        blockers.append("score_mismatch")
    if int(factor_contribution_stats["mismatch_count"]) > 0:
        blockers.append("factor_contribution_mismatch")
    if int(wfo_weight_stats["missing_weight_count"]) > 0:
        blockers.append("wfo_weight_missing_factor")
    if float(wfo_weight_stats["max_abs_weight_sum_deviation_from_one"]) > tolerance:
        blockers.append("wfo_weight_abs_sum_not_one")
    if int(target_weight_stats["mismatch_count"]) > 0:
        blockers.append("target_weight_mismatch")
    if int(slice_metric_stats["mismatch_count"]) > 0:
        blockers.append("slice_metric_mismatch")

    blockers = sorted(set(blockers))
    status = "ready" if not blockers else "blocked"
    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "status": status,
        "blockers": blockers,
        "scope": "research_to_live_parity_harness_only",
        "stage_boundary": "stage_1_research_readiness_only",
        "live_supervisor_timer_loaded_candidate_overlay": False,
        "executor_input": "baseline_only_outside_this_harness",
        "orders_submitted": 0,
        "fills_observed": 0,
        "operator_state_changed": False,
        "live_config_changed": False,
        "applied_to_live": False,
        "eligible_next_step": "owner_gated_p9c_review" if status == "ready" else "not_eligible_until_parity_ready",
        "effective_research_baseline": frozen_forward.EFFECTIVE_BASELINE_LABEL,
        "score_parent_label": frozen_forward.BASELINE_LABEL,
        "frozen_candidate_label": FROZEN_LABEL,
        "target_factor": TARGET_FACTOR,
        "target_overlay_semantics": "only distance_to_high_60 contribution is multiplied by 0.0 on candidate trigger rows",
        "candidate_scorer_mode": scorer_mode,
        "candidate_scorer_mode_scope": "proof_harness_only",
        "candidate_scorer_loaded_into_live_wrapper": False,
        "candidate_scorer_loaded_into_timer": False,
        "candidate_scorer_loaded_into_executor": False,
        "baseline_experiment_id": str(args.baseline_experiment_id),
        "feature_path": str(context["feature_path"]),
        "feature_path_sha256": file_sha256(Path(context["feature_path"])),
        "validation_contract_path": str(context["validation_contract_path"]),
        "validation_contract_sha256": file_sha256(Path(context["validation_contract_path"])),
        "retained_forward_root": str(retained_forward_root),
        "retained_artifact_compare_enabled": compare_retained,
        "processed_wfo_window_count": int(processed_windows),
        "max_windows": int(max_windows),
        "tolerance": tolerance,
        "construction": {
            "target_engine": "research_execution_backtest_cross_sectional_target_trace",
            "phase_offsets_days": list(portfolio_diag.MULTIPHASE_PHASES),
            "sleeve_weight": portfolio_diag.MULTIPHASE_SLEEVE_WEIGHT,
            "rebalance_step_bars": int(split_contract["realization_step_bars"]),
            "target_horizon_bars": int(split_contract["target_horizon_bars"]),
            "sharpe_metric_convention_version": SHARPE_METRIC_CONVENTION_VERSION,
        },
        "research_scorer_contract": research_scorer_contract,
        "research_scorer_contract_checks": research_scorer_contract_checks,
        "wfo_window_weight_contract": {
            "weight_estimation": "train-window daily cross-sectional Spearman IC signed-IR, normalized to abs-sum 1.0",
            "weights_source": "v5_phase.weights_for_train_end(daily_ic_by_factor, train_end_ms)",
            "required_factor_columns": list(research_scorer_contract.get("required_feature_columns") or []),
            "stats": wfo_weight_stats,
        },
        "panel_contract": {
            "dataset_profile": research_scorer_contract.get("dataset_profile"),
            "feature_path": str(context["feature_path"]),
            "feature_path_sha256": file_sha256(Path(context["feature_path"])),
            "required_feature_columns": list(research_scorer_contract.get("required_feature_columns") or []),
            "required_feature_count": int(len(research_scorer_contract.get("required_feature_columns") or [])),
            "execution_eligible_row_count": int(len(frame)),
            "execution_eligible_subject_count": int(frame["subject"].nunique()),
            "execution_eligible_timestamp_count": int(frame["timestamp_ms"].nunique()),
            "missing_required_features_from_panel": list(
                research_scorer_contract_checks.get("missing_required_features_from_panel") or []
            ),
        },
        "threshold_contract": {
            "threshold_source": "robust.robustness_thresholds(train_df) per WFO train window",
            "threshold_artifact": str(output_root / "generated_train_thresholds.csv"),
            "retained_threshold_compare": dict(retained_compare.get("threshold_compare") or {}),
        },
        "row_parity": row_parity_stats,
        "factor_contribution_parity": factor_contribution_stats,
        "target_weight_parity": target_weight_stats,
        "slice_metric_parity": slice_metric_stats,
        "slice_metric_contract": {
            "slice_names": list(SLICE_NAMES),
            "metric_fields": list(slice_metric_fields),
            "research_slice_metrics_artifact": str(output_root / "research_slice_metrics.csv"),
            "live_slice_metrics_artifact": str(output_root / "live_slice_metrics.csv"),
        },
        "retained_forward_artifact_compare": retained_compare,
        "diagnostics": {
            "execution_eligible_row_count": int(len(frame)),
            "execution_eligible_subject_count": int(frame["subject"].nunique()),
            "active_factor_columns": list(active_factor_columns),
            "target_factor_weight_abs_sum": float(sum(abs(float(v)) for v in context["last_weights_sample"].values()))
            if context.get("last_weights_sample")
            else None,
        },
        "output_files": {
            "summary": str(output_root / "summary.json"),
            "report": str(output_root / "report.md"),
            "window_row_parity": str(output_root / "window_row_parity.csv"),
            "factor_contribution_parity": str(output_root / "factor_contribution_parity.csv"),
            "factor_contribution_mismatch_sample": str(output_root / "factor_contribution_mismatch_sample.csv"),
            "row_mismatch_sample": str(output_root / "row_mismatch_sample.csv"),
            "target_weight_mismatches": str(output_root / "target_weight_mismatches.csv"),
            "target_weight_sample": str(output_root / "target_weight_sample.csv"),
            "research_window_metrics": str(output_root / "research_window_metrics.csv"),
            "live_window_metrics": str(output_root / "live_window_metrics.csv"),
            "research_slice_metrics": str(output_root / "research_slice_metrics.csv"),
            "live_slice_metrics": str(output_root / "live_slice_metrics.csv"),
            "slice_metric_mismatches": str(output_root / "slice_metric_mismatches.csv"),
            "generated_train_thresholds": str(output_root / "generated_train_thresholds.csv"),
            "wfo_window_factor_weights": str(output_root / "wfo_window_factor_weights.csv"),
            "research_scorer_contract": str(output_root / "research_scorer_contract.json"),
        },
    }

    write_csv(output_root / "window_row_parity.csv", row_parity_rows)
    write_csv(output_root / "factor_contribution_parity.csv", factor_contribution_rows)
    if factor_contribution_mismatch_frames:
        write_csv(
            output_root / "factor_contribution_mismatch_sample.csv",
            pd.concat(factor_contribution_mismatch_frames, ignore_index=True).head(int(args.row_sample_limit)),
        )
    else:
        write_csv(output_root / "factor_contribution_mismatch_sample.csv", [])
    write_csv(output_root / "row_mismatch_sample.csv", row_mismatch_rows[: int(args.row_sample_limit)])
    if target_mismatch_frames:
        write_csv(output_root / "target_weight_mismatches.csv", pd.concat(target_mismatch_frames, ignore_index=True))
    else:
        write_csv(output_root / "target_weight_mismatches.csv", [])
    if target_sample_frames:
        write_csv(output_root / "target_weight_sample.csv", pd.concat(target_sample_frames, ignore_index=True))
    else:
        write_csv(output_root / "target_weight_sample.csv", [])
    write_csv(output_root / "research_window_metrics.csv", research_window_rows)
    write_csv(output_root / "live_window_metrics.csv", live_window_rows)
    write_csv(output_root / "research_slice_metrics.csv", research_slice_metrics)
    write_csv(output_root / "live_slice_metrics.csv", live_slice_metrics)
    write_csv(output_root / "slice_metric_mismatches.csv", slice_metric_mismatches)
    write_csv(output_root / "generated_train_thresholds.csv", generated_threshold_rows)
    write_csv(output_root / "wfo_window_factor_weights.csv", wfo_weight_rows)
    write_json(
        output_root / "research_scorer_contract.json",
        {
            "research_scorer_contract": research_scorer_contract,
            "research_scorer_contract_checks": research_scorer_contract_checks,
            "wfo_window_weight_contract": summary["wfo_window_weight_contract"],
            "panel_contract": summary["panel_contract"],
            "threshold_contract": summary["threshold_contract"],
            "slice_metric_contract": summary["slice_metric_contract"],
        },
    )
    write_json(output_root / "summary.json", summary)
    write_report(output_root / "report.md", summary)
    return summary, 0 if status == "ready" else 2


def build_research_context(args: argparse.Namespace) -> dict[str, Any]:
    experiment_root = Path(args.artifacts_root) / "experiments" / _experiment_directory_name(str(args.baseline_experiment_id))
    spec_path = experiment_root / "spec.json"
    if not spec_path.exists():
        spec_path = experiment_root / "experiment_spec.json"
    validation_contract_path = Path(args.validation_contract)
    spec = load_json(spec_path)
    feature_manifest_path = experiment_root / "feature_manifest.json"
    if not feature_manifest_path.exists():
        feature_manifest_path = resolve_artifact_path(str(spec.get("feature_manifest_path") or ""))
    feature_manifest = load_json(feature_manifest_path)
    feature_path = resolve_artifact_path(str(feature_manifest.get("feature_path") or feature_manifest.get("features_path") or ""))
    validation_contract = load_json(validation_contract_path)
    split_contract = resolve_split_realization_contract(contract=spec.get("split_realization_contract"))
    try:
        execution_cost_models = _resolved_execution_cost_models(validation_contract)
    except TypeError:
        execution_cost_models = _resolved_execution_cost_models()
    strategy_profile = str(spec.get("strategy_profile") or "")
    execution_venue = str(spec.get("execution_venue") or "binance_futures").strip().lower()
    if isinstance(execution_cost_models, tuple):
        base_execution_cost_model = dict(execution_cost_models[0])
    elif execution_venue in execution_cost_models:
        base_execution_cost_model = dict(execution_cost_models[execution_venue])
    else:
        base_execution_cost_model = dict(execution_cost_models)
    try:
        reference_capital_usd = validation_contract_reference_capital_usd(validation_contract)
    except TypeError:
        reference_capital_usd = validation_contract_reference_capital_usd(
            strategy_profile=strategy_profile,
            contract=validation_contract,
        )
    try:
        capacity_limits = execution_capacity_limits(validation_contract)
    except TypeError:
        capacity_limits = execution_capacity_limits(contract=validation_contract)
    constraints = dict(spec.get("profile_constraints") or {})
    constraints["strategy_profile"] = strategy_profile

    raw_frame = pd.read_csv(feature_path, low_memory=False)
    frame = _apply_universe_filter(raw_frame, universe_filter=spec.get("universe_filter"))
    frame = filter_cross_sectional_execution_frame(frame=frame, constraints=constraints)
    if frame.empty:
        raise RuntimeError("no execution-eligible rows")
    feature_columns = list(spec.get("feature_columns") or [])
    missing_features = [column for column in feature_columns if column not in frame.columns]
    if missing_features:
        raise RuntimeError(f"missing feature columns: {missing_features}")
    active_factor_columns = factor_ablation.active_v5_factor_columns(feature_columns)
    if TARGET_FACTOR not in active_factor_columns:
        raise RuntimeError(f"{TARGET_FACTOR} not active in v5 factor map")
    daily_ic_by_factor = v5_phase.build_daily_ic_by_factor(frame, feature_columns=feature_columns)
    sample_weights = v5_phase.weights_for_train_end(
        daily_ic_by_factor=daily_ic_by_factor,
        train_end_ms=int(pd.to_numeric(frame["timestamp_ms"], errors="coerce").min()),
    )
    return {
        "spec_path": spec_path,
        "feature_manifest_path": feature_manifest_path,
        "feature_path": feature_path,
        "validation_contract_path": validation_contract_path,
        "spec": spec,
        "feature_manifest": feature_manifest,
        "validation_contract": validation_contract,
        "split_contract": split_contract,
        "base_execution_cost_model": base_execution_cost_model,
        "reference_capital_usd": reference_capital_usd,
        "capacity_limits": capacity_limits,
        "constraints": constraints,
        "frame": frame,
        "feature_columns": feature_columns,
        "active_factor_columns": active_factor_columns,
        "daily_ic_by_factor": daily_ic_by_factor,
        "last_weights_sample": sample_weights,
    }


def build_window_metric_row(
    *,
    label: str,
    kind: str,
    definition: dict[str, Any],
    phase: int,
    phase_audit: dict[str, Any],
    train_end: datetime,
    validation_end: datetime,
    test_times: pd.Series,
    metrics: dict[str, Any],
    overlay_stats: dict[str, Any],
) -> dict[str, Any]:
    return {
        "label": label,
        "kind": kind,
        "condition": str(definition["condition"]),
        "shock_quantile": definition.get("shock_quantile"),
        "crowded_top_fraction": definition.get("crowded_top_fraction"),
        "target_multiplier": float(definition["target_multiplier"]),
        "phase_offset_days": int(phase),
        "phase_start_date_utc": phase_audit.get("start_date_utc"),
        "train_end_utc": train_end.isoformat().replace("+00:00", "Z"),
        "validation_end_utc": validation_end.isoformat().replace("+00:00", "Z"),
        "test_start_utc": test_times.min().isoformat().replace("+00:00", "Z"),
        "test_end_utc": test_times.max().isoformat().replace("+00:00", "Z"),
        "net_return": float(metrics.get("net_return", 0.0) or 0.0),
        "max_drawdown": float(metrics.get("max_drawdown", 0.0) or 0.0),
        "turnover": float(metrics.get("turnover", 0.0) or 0.0),
        "period_count": int(len(metrics.get("periods") or [])),
        **overlay_stats,
    }


def build_research_style_slice_summary(
    *,
    baseline_periods: pd.DataFrame,
    candidate_periods: pd.DataFrame,
    split_contract: dict[str, Any],
    episode_start: str,
    episode_end: str,
    holdout_start: str,
) -> pd.DataFrame:
    periods_by_label = {
        BASELINE_VARIANT_LABEL: baseline_periods,
        FROZEN_LABEL: candidate_periods,
    }
    return robust.build_slice_summary(
        labels=[BASELINE_VARIANT_LABEL, FROZEN_LABEL],
        periods_by_label=periods_by_label,
        split_contract=split_contract,
        episode_start=episode_start,
        episode_end=episode_end,
        holdout_start=holdout_start,
    )


def compare_retained_forward_artifacts(
    *,
    retained_forward_root: Path,
    generated_threshold_rows: pd.DataFrame,
    generated_window_rows: pd.DataFrame,
    generated_slice_metrics: pd.DataFrame,
    tolerance: float,
    enabled: bool,
) -> dict[str, Any]:
    if not enabled:
        return {"enabled": False, "status": "skipped", "blockers": []}
    blockers: list[str] = []
    retained_summary_path = retained_forward_root / "summary.json"
    retained_threshold_path = retained_forward_root / "forward_train_thresholds.csv"
    retained_window_path = retained_forward_root / "forward_test_windows.csv"
    retained_slice_path = retained_forward_root / "forward_slice_summary.csv"
    required = [retained_summary_path, retained_threshold_path, retained_window_path, retained_slice_path]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        return {
            "enabled": True,
            "status": "blocked",
            "blockers": ["retained_forward_artifacts_missing"],
            "missing": missing,
        }
    retained_summary = load_json(retained_summary_path)
    retained_thresholds = pd.read_csv(retained_threshold_path)
    retained_windows = pd.read_csv(retained_window_path)
    retained_slices = pd.read_csv(retained_slice_path)

    threshold_stats, threshold_mismatches = compare_metric_frames(
        normalize_threshold_rows(retained_thresholds),
        normalize_threshold_rows(generated_threshold_rows),
        keys=["phase_offset_days", "train_end_utc", "validation_end_utc"],
        metrics=[
            "shock_co_occurrence_index_q85",
            "shock_co_occurrence_index_q90",
            "shock_co_occurrence_index_q95",
            "co_jump_count_3d_q85",
            "co_jump_count_3d_q90",
            "co_jump_count_3d_q95",
        ],
        tolerance=tolerance,
    )
    retained_candidate_windows = retained_windows.loc[retained_windows["label"].astype(str).eq(FROZEN_LABEL)].copy()
    window_stats, window_mismatches = compare_metric_frames(
        normalize_window_rows(retained_candidate_windows),
        normalize_window_rows(generated_window_rows),
        keys=["label", "phase_offset_days", "train_end_utc", "validation_end_utc", "test_start_utc", "test_end_utc"],
        metrics=[
            "net_return",
            "max_drawdown",
            "turnover",
            "period_count",
            "overlay_test_row_count",
            "overlay_triggered_row_count",
            "overlay_average_factor_multiplier",
        ],
        tolerance=tolerance,
    )
    retained_candidate_slices = retained_slices.loc[
        retained_slices["label"].astype(str).isin([BASELINE_VARIANT_LABEL, FROZEN_LABEL])
    ].copy()
    slice_stats, slice_mismatches = compare_metric_frames(
        normalize_slice_rows(retained_candidate_slices),
        normalize_slice_rows(generated_slice_metrics),
        keys=["label", "slice"],
        metrics=[
            "period_count",
            "cumulative_return",
            "h10d_equivalent_sharpe",
            "max_drawdown",
            "loss_period_fraction",
            "mean_period_return",
            "turnover_total",
            "max_trade_participation_rate",
            "capacity_breach_count",
            "delta_cumulative_return_vs_baseline",
            "delta_h10d_equivalent_sharpe_vs_baseline",
            "delta_max_drawdown_vs_baseline",
        ],
        tolerance=tolerance,
    )
    if threshold_stats["mismatch_count"] > 0:
        blockers.append("retained_threshold_mismatch")
    if window_stats["mismatch_count"] > 0:
        blockers.append("retained_window_metric_mismatch")
    if slice_stats["mismatch_count"] > 0:
        blockers.append("retained_slice_metric_mismatch")
    if str(retained_summary.get("frozen_candidate_label") or "") != FROZEN_LABEL:
        blockers.append("retained_frozen_label_mismatch")
    if retained_summary.get("status") != "computed":
        blockers.append("retained_summary_status_not_computed")

    return {
        "enabled": True,
        "status": "ready" if not blockers else "blocked",
        "blockers": blockers,
        "retained_summary_path": str(retained_summary_path),
        "retained_summary_sha256": file_sha256(retained_summary_path),
        "threshold_compare": threshold_stats,
        "window_compare": window_stats,
        "slice_compare": slice_stats,
        "threshold_mismatch_sample": threshold_mismatches.head(20).to_dict(orient="records"),
        "window_mismatch_sample": window_mismatches.head(20).to_dict(orient="records"),
        "slice_mismatch_sample": slice_mismatches.head(20).to_dict(orient="records"),
    }


def normalize_threshold_rows(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    output = frame.copy()
    output["phase_offset_days"] = pd.to_numeric(output["phase_offset_days"], errors="coerce").astype("int64")
    for column in ("train_end_utc", "validation_end_utc"):
        output[column] = output[column].astype(str)
    return output.sort_values(["phase_offset_days", "train_end_utc", "validation_end_utc"]).reset_index(drop=True)


def normalize_window_rows(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    output = frame.copy()
    output["phase_offset_days"] = pd.to_numeric(output["phase_offset_days"], errors="coerce").astype("int64")
    for column in ("label", "train_end_utc", "validation_end_utc", "test_start_utc", "test_end_utc"):
        output[column] = output[column].astype(str)
    return output.sort_values(
        ["label", "phase_offset_days", "train_end_utc", "validation_end_utc", "test_start_utc", "test_end_utc"]
    ).reset_index(drop=True)


def normalize_slice_rows(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    output = frame.copy()
    for column in ("label", "slice"):
        output[column] = output[column].astype(str)
    return output.sort_values(["label", "slice"]).reset_index(drop=True)


def write_report(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# P9R Research-To-Live Parity Harness",
        "",
        f"- status: `{summary['status']}`",
        f"- contract_version: `{summary['contract_version']}`",
        f"- frozen_candidate_label: `{summary['frozen_candidate_label']}`",
        f"- effective_research_baseline: `{summary['effective_research_baseline']}`",
        f"- candidate_scorer_mode: `{summary.get('candidate_scorer_mode')}`",
        f"- research_scorer_contract_status: `{summary.get('research_scorer_contract_checks', {}).get('status')}`",
        f"- research_required_feature_count: `{summary.get('research_scorer_contract', {}).get('required_feature_count')}`",
        f"- processed_wfo_window_count: `{summary['processed_wfo_window_count']}`",
        f"- row_parity_mismatches: `{sum(int(summary['row_parity'][k]) for k in ['trigger_mismatch_count', 'multiplier_mismatch_count', 'target_contribution_mismatch_count', 'score_mismatch_count'])}`",
        f"- factor_contribution_mismatch_count: `{summary['factor_contribution_parity']['mismatch_count']}`",
        f"- target_weight_mismatch_count: `{summary['target_weight_parity']['mismatch_count']}`",
        f"- slice_metric_mismatch_count: `{summary['slice_metric_parity']['mismatch_count']}`",
        f"- wfo_weight_rows: `{summary.get('wfo_window_weight_contract', {}).get('stats', {}).get('row_count')}`",
        f"- wfo_weight_max_abs_sum_deviation_from_one: `{summary.get('wfo_window_weight_contract', {}).get('stats', {}).get('max_abs_weight_sum_deviation_from_one')}`",
        f"- retained_artifact_compare_enabled: `{summary['retained_artifact_compare_enabled']}`",
        f"- blockers: `{summary['blockers']}`",
        "",
        "## Non-Live Boundary",
        "",
        "- live_supervisor_timer_loaded_candidate_overlay: `false`",
        "- executor_input: `baseline_only_outside_this_harness`",
        "- orders_submitted: `0`",
        "- fills_observed: `0`",
        "- operator_state_changed: `false`",
        "- live_config_changed: `false`",
        "- candidate_scorer_loaded_into_timer: `false`",
        "- candidate_scorer_loaded_into_executor: `false`",
        "",
        "## Output Files",
        "",
    ]
    for name, value in dict(summary.get("output_files") or {}).items():
        lines.append(f"- {name}: `{value}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    _, exit_code = run_research_to_live_parity(parse_args(argv))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
