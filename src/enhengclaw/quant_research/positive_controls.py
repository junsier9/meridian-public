from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from enhengclaw.ops.evidence_contracts import with_evidence_metadata

from .contracts import portable_path, profile_constraints, read_json, write_json
from .lab import (
    _backtest_cross_sectional,
    _backtest_single_asset,
    _chronological_split,
    _single_asset_position_from_score,
)
from .overlap_integrity import (
    evaluate_overlap_integrity,
    infer_interval_ms,
    infer_label_horizon_bars,
    walk_forward_split_with_purge,
)


ROOT = Path(__file__).resolve().parents[3]
POSITIVE_CONTROL_SUMMARY_CONTRACT_VERSION = "quant_positive_control_summary.v1"
POSITIVE_CONTROL_EVIDENCE_FAMILY = "quant_positive_controls"
WEAK_ORACLE_TARGET_CORRELATION = 0.25
MOMENTUM_12_1_LOOKBACK_DAYS = 252
MOMENTUM_12_1_SKIP_DAYS = 21
BENCHMARK_CONSTRAINTS_PROFILE = "balanced"
CONTROL_WALK_FORWARD_TRAIN_DAYS = 120
CONTROL_WALK_FORWARD_VALIDATION_DAYS = 30
CONTROL_WALK_FORWARD_TEST_DAYS = 30
CONTROL_WALK_FORWARD_STEP_DAYS = 30
MIN_SINGLE_ASSET_POSITIVE_CONTROL_WALK_FORWARD_WINDOWS = 3


def write_positive_control_summary(
    *,
    as_of: str,
    artifacts_root: Path,
    repo_root: Path | None = None,
    now_utc: str | None = None,
) -> dict[str, Any]:
    payload = build_positive_control_summary(
        as_of=as_of,
        artifacts_root=artifacts_root,
        repo_root=repo_root,
        now_utc=now_utc,
    )
    resolved_repo_root = (repo_root or ROOT).expanduser().resolve()
    summary_root = _positive_control_root(artifacts_root=artifacts_root, as_of=as_of)
    summary_root.mkdir(parents=True, exist_ok=True)
    json_path = summary_root / "positive_control_summary.json"
    markdown_path = summary_root / "positive_control_summary.md"
    write_json(json_path, payload)
    markdown_path.write_text(_render_positive_control_markdown(payload), encoding="utf-8")
    payload["positive_control_summary_path"] = portable_path(json_path, repo_root=resolved_repo_root)
    payload["positive_control_markdown_path"] = portable_path(markdown_path, repo_root=resolved_repo_root)
    return payload


def build_positive_control_summary(
    *,
    as_of: str,
    artifacts_root: Path,
    repo_root: Path | None = None,
    now_utc: str | None = None,
) -> dict[str, Any]:
    resolved_artifacts_root = artifacts_root.expanduser().resolve()
    resolved_repo_root = (repo_root or ROOT).expanduser().resolve()
    generated_at_utc = now_utc or datetime.now(UTC).isoformat().replace("+00:00", "Z")
    single_asset_feature_set = _load_feature_set(artifacts_root=resolved_artifacts_root, as_of=as_of, shape="single_asset")
    cross_sectional_feature_set = _load_feature_set(artifacts_root=resolved_artifacts_root, as_of=as_of, shape="cross_sectional")

    control_cases: list[dict[str, Any]] = []
    for subject in sorted(single_asset_feature_set["dataframe"]["subject"].dropna().astype(str).unique()):
        subject_frame = (
            single_asset_feature_set["dataframe"]
            .loc[single_asset_feature_set["dataframe"]["subject"] == subject]
            .copy()
            .sort_values("timestamp_ms")
            .reset_index(drop=True)
        )
        control_cases.append(
            _execute_control_case(
                as_of=as_of,
                shape="single_asset",
                control_kind="strong_oracle",
                frame=subject_frame,
                dataset_id=single_asset_feature_set["dataset_id"],
                feature_set_id=single_asset_feature_set["feature_set_id"],
                subject=subject,
                expected_future_dependency=True,
            )
        )
        control_cases.append(
            _execute_control_case(
                as_of=as_of,
                shape="single_asset",
                control_kind="weak_oracle",
                frame=subject_frame,
                dataset_id=single_asset_feature_set["dataset_id"],
                feature_set_id=single_asset_feature_set["feature_set_id"],
                subject=subject,
                expected_future_dependency=True,
            )
        )

    control_cases.append(
        _execute_control_case(
            as_of=as_of,
            shape="cross_sectional",
            control_kind="strong_oracle",
            frame=cross_sectional_feature_set["dataframe"].copy(),
            dataset_id=cross_sectional_feature_set["dataset_id"],
            feature_set_id=cross_sectional_feature_set["feature_set_id"],
            subject=None,
            expected_future_dependency=True,
        )
    )
    control_cases.append(
        _execute_control_case(
            as_of=as_of,
            shape="cross_sectional",
            control_kind="weak_oracle",
            frame=cross_sectional_feature_set["dataframe"].copy(),
            dataset_id=cross_sectional_feature_set["dataset_id"],
            feature_set_id=cross_sectional_feature_set["feature_set_id"],
            subject=None,
            expected_future_dependency=True,
        )
    )
    control_cases.append(
        _execute_control_case(
            as_of=as_of,
            shape="cross_sectional",
            control_kind="momentum_12_1",
            frame=cross_sectional_feature_set["dataframe"].copy(),
            dataset_id=cross_sectional_feature_set["dataset_id"],
            feature_set_id=cross_sectional_feature_set["feature_set_id"],
            subject=None,
            expected_future_dependency=False,
        )
    )

    real_lane_reference = _build_real_lane_reference(
        artifacts_root=resolved_artifacts_root,
        as_of=as_of,
        repo_root=resolved_repo_root,
    )
    pipeline_health, pipeline_health_rationale = _pipeline_health(control_cases)
    lane_interpretation = _lane_interpretation(
        pipeline_health=pipeline_health,
        real_lane_reference=real_lane_reference,
        control_cases=control_cases,
    )
    coverage_telemetry = _control_case_coverage_telemetry(control_cases)
    subject_count_by_shape = {
        "single_asset": int(single_asset_feature_set["dataframe"]["subject"].nunique()),
        "cross_sectional": int(cross_sectional_feature_set["dataframe"]["subject"].nunique()),
    }
    payload = with_evidence_metadata(
        {
            "generated_at_utc": generated_at_utc,
            "as_of": as_of,
            "dataset_ids": {
                "single_asset": single_asset_feature_set["dataset_id"],
                "cross_sectional": cross_sectional_feature_set["dataset_id"],
            },
            "feature_set_ids": {
                "single_asset": single_asset_feature_set["feature_set_id"],
                "cross_sectional": cross_sectional_feature_set["feature_set_id"],
            },
            "benchmark_constraints_profile": BENCHMARK_CONSTRAINTS_PROFILE,
            "subject_count_by_shape": subject_count_by_shape,
            "control_cases": control_cases,
            "coverage_telemetry": coverage_telemetry,
            "pipeline_health": pipeline_health,
            "pipeline_health_rationale": pipeline_health_rationale,
            "lane_interpretation": lane_interpretation,
            "real_lane_reference": real_lane_reference,
        },
        evidence_family=POSITIVE_CONTROL_EVIDENCE_FAMILY,
        contract_version=POSITIVE_CONTROL_SUMMARY_CONTRACT_VERSION,
        repo_root=resolved_repo_root,
        require_source_commit_sha=True,
    )
    return payload


def strong_oracle_score(frame: pd.DataFrame) -> pd.Series:
    return frame["target_forward_return"].astype("float64")


def weak_oracle_score(
    frame: pd.DataFrame,
    *,
    seed: int,
    target_correlation: float = WEAK_ORACLE_TARGET_CORRELATION,
) -> pd.Series:
    signal = frame["target_forward_return"].fillna(0.0).astype("float64")
    if signal.empty:
        return signal
    if target_correlation <= 0.0 or target_correlation >= 1.0:
        raise ValueError("target_correlation must be between 0 and 1")
    sigma_signal = float(signal.std(ddof=0))
    if sigma_signal == 0.0:
        return signal
    sigma_noise = sigma_signal * math.sqrt((1.0 / (target_correlation**2)) - 1.0)
    rng = np.random.default_rng(seed)
    noise = rng.normal(loc=0.0, scale=sigma_noise, size=len(signal))
    return pd.Series(signal.to_numpy() + noise, index=frame.index, dtype="float64")


def momentum_12_1_score(frame: pd.DataFrame) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype="float64")
    scored_frames: list[pd.DataFrame] = []
    for _, group in frame.groupby("subject", sort=True):
        ordered = group.sort_values("timestamp_ms").copy()
        close = ordered["spot_close"].replace(0.0, np.nan)
        ordered["score"] = close.pct_change(MOMENTUM_12_1_LOOKBACK_DAYS) - close.pct_change(MOMENTUM_12_1_SKIP_DAYS)
        scored_frames.append(ordered)
    scored = pd.concat(scored_frames, ignore_index=False).sort_values(["timestamp_ms", "subject"])
    return scored["score"].astype("float64")


def has_momentum_12_1_history(frame: pd.DataFrame) -> bool:
    if frame.empty or "subject" not in frame.columns:
        return False
    minimum_rows = MOMENTUM_12_1_LOOKBACK_DAYS + 1
    counts = frame.groupby("subject", sort=False)["timestamp_ms"].count()
    return bool(not counts.empty and counts.min() >= minimum_rows)


def _execute_control_case(
    *,
    as_of: str,
    shape: str,
    control_kind: str,
    frame: pd.DataFrame,
    dataset_id: str,
    feature_set_id: str,
    subject: str | None,
    expected_future_dependency: bool,
) -> dict[str, Any]:
    ordered = frame.sort_values(["timestamp_ms", "subject"] if "subject" in frame.columns else ["timestamp_ms"]).reset_index(drop=True)
    control_id = _control_id(as_of=as_of, shape=shape, control_kind=control_kind, subject=subject)
    minimum_walk_forward_windows_required = _minimum_walk_forward_windows_required(
        shape=shape,
        control_kind=control_kind,
    )
    if ordered.empty:
        return _skipped_control_case(
            control_id=control_id,
            shape=shape,
            control_kind=control_kind,
            dataset_id=dataset_id,
            feature_set_id=feature_set_id,
            subject=subject,
            expected_future_dependency=expected_future_dependency,
            skipped_reason="skipped_empty_frame",
            available_walk_forward_window_count=0 if minimum_walk_forward_windows_required is not None else None,
            minimum_walk_forward_windows_required=minimum_walk_forward_windows_required,
        )
    if control_kind == "momentum_12_1" and not has_momentum_12_1_history(ordered):
        return _skipped_control_case(
            control_id=control_id,
            shape=shape,
            control_kind=control_kind,
            dataset_id=dataset_id,
            feature_set_id=feature_set_id,
            subject=subject,
            expected_future_dependency=expected_future_dependency,
            skipped_reason="skipped_insufficient_history",
            available_walk_forward_window_count=0 if minimum_walk_forward_windows_required is not None else None,
            minimum_walk_forward_windows_required=minimum_walk_forward_windows_required,
        )

    if control_kind == "momentum_12_1":
        momentum_scores = momentum_12_1_score(ordered)
        ordered = ordered.loc[momentum_scores.notna()].copy()
        ordered["score"] = momentum_scores.loc[ordered.index]
        ordered.reset_index(drop=True, inplace=True)
        if ordered.empty:
            return _skipped_control_case(
                control_id=control_id,
                shape=shape,
                control_kind=control_kind,
                dataset_id=dataset_id,
                feature_set_id=feature_set_id,
                subject=subject,
                expected_future_dependency=expected_future_dependency,
                skipped_reason="skipped_insufficient_history",
                available_walk_forward_window_count=0 if minimum_walk_forward_windows_required is not None else None,
                minimum_walk_forward_windows_required=minimum_walk_forward_windows_required,
            )

    label_horizon_bars = infer_label_horizon_bars(frame=ordered)
    bar_interval_ms = _infer_bar_interval_ms(ordered)
    split = _chronological_split(ordered, time_col="timestamp_ms", label_horizon_bars=label_horizon_bars)
    if split is None:
        return _skipped_control_case(
            control_id=control_id,
            shape=shape,
            control_kind=control_kind,
            dataset_id=dataset_id,
            feature_set_id=feature_set_id,
            subject=subject,
            expected_future_dependency=expected_future_dependency,
            skipped_reason="skipped_insufficient_history",
            label_horizon_bars=label_horizon_bars,
            bar_interval_ms=bar_interval_ms,
            available_walk_forward_window_count=0 if minimum_walk_forward_windows_required is not None else None,
            minimum_walk_forward_windows_required=minimum_walk_forward_windows_required,
        )
    available_walk_forward_window_count = _count_control_walk_forward_windows(
        frame=ordered,
        label_horizon_bars=label_horizon_bars,
        bar_interval_ms=bar_interval_ms,
    )
    if (
        minimum_walk_forward_windows_required is not None
        and available_walk_forward_window_count < minimum_walk_forward_windows_required
    ):
        return _skipped_control_case(
            control_id=control_id,
            shape=shape,
            control_kind=control_kind,
            dataset_id=dataset_id,
            feature_set_id=feature_set_id,
            subject=subject,
            expected_future_dependency=expected_future_dependency,
            skipped_reason="skipped_insufficient_history",
            label_horizon_bars=label_horizon_bars,
            bar_interval_ms=bar_interval_ms,
            available_walk_forward_window_count=available_walk_forward_window_count,
            minimum_walk_forward_windows_required=minimum_walk_forward_windows_required,
        )
    train_df, validation_df, test_df = split
    scored_train, scored_validation, scored_test = _score_split_partitions(
        control_id=control_id,
        control_kind=control_kind,
        shape=shape,
        train_df=train_df,
        validation_df=validation_df,
        test_df=test_df,
    )
    constraints = profile_constraints(BENCHMARK_CONSTRAINTS_PROFILE)
    constraints["strategy_profile"] = BENCHMARK_CONSTRAINTS_PROFILE
    constraints["execution_venue"] = "spot"
    validation_metrics = _backtest_single_asset(scored_validation, constraints=constraints) if shape == "single_asset" else _backtest_cross_sectional(scored_validation, constraints=constraints)
    test_metrics = _backtest_single_asset(scored_test, constraints=constraints) if shape == "single_asset" else _backtest_cross_sectional(scored_test, constraints=constraints)
    overlap_integrity = evaluate_overlap_integrity(
        train_df=scored_train,
        validation_df=scored_validation,
        test_df=scored_test,
        label_horizon_bars=label_horizon_bars,
        bar_interval_ms=bar_interval_ms,
        evaluation_step_bars=int(test_metrics.get("evaluation_step_bars", 1) or 1),
        prediction_count=int(len(scored_test)),
        rebalance_count=int(test_metrics.get("rebalance_count", 0) or 0),
    )
    walk_forward = _run_control_walk_forward(
        control_id=control_id,
        control_kind=control_kind,
        shape=shape,
        frame=ordered,
        constraints=constraints,
        label_horizon_bars=label_horizon_bars,
        bar_interval_ms=bar_interval_ms,
    )
    raw_positive = bool(
        float(validation_metrics.get("sharpe") or 0.0) > 0.0
        and float(test_metrics.get("sharpe") or 0.0) > 0.0
        and float(walk_forward.get("median_oos_sharpe") or 0.0) > 0.0
    )
    position_diagnostics = _position_diagnostics(
        shape=shape,
        scored_test=scored_test,
        constraints=constraints,
    )
    production_admissibility = (
        "inadmissible_expected_future_dependency"
        if expected_future_dependency
        else "eligible_for_normal_contract_check"
    )
    return {
        "control_id": control_id,
        "shape": shape,
        "subject": subject,
        "control_kind": control_kind,
        "status": "executed",
        "expected_future_dependency": bool(expected_future_dependency),
        "dataset_id": dataset_id,
        "feature_set_id": feature_set_id,
        "benchmark_constraints_profile": BENCHMARK_CONSTRAINTS_PROFILE,
        "label_horizon_bars": int(label_horizon_bars),
        "bar_interval_ms": int(bar_interval_ms),
        "raw_positive": raw_positive,
        "production_admissibility": production_admissibility,
        "validation_metrics": validation_metrics,
        "test_metrics": test_metrics,
        "walk_forward": walk_forward,
        "score_sign_counts": position_diagnostics["score_sign_counts"],
        "position_sign_counts": position_diagnostics["position_sign_counts"],
        "nonzero_position_fraction": position_diagnostics["nonzero_position_fraction"],
        "label_split_overlap": int(overlap_integrity.get("label_split_overlap", 0) or 0),
        "split_boundary_contamination_counts": dict(overlap_integrity.get("split_boundary_contamination_counts") or {}),
        "backtest_horizon_mismatch": dict(overlap_integrity.get("backtest_horizon_mismatch") or {}),
    }


def _score_split_partitions(
    *,
    control_id: str,
    control_kind: str,
    shape: str,
    train_df: pd.DataFrame,
    validation_df: pd.DataFrame,
    test_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    train = train_df.copy()
    validation = validation_df.copy()
    test = test_df.copy()
    if control_kind == "strong_oracle":
        train["score"] = strong_oracle_score(train)
        validation["score"] = strong_oracle_score(validation)
        test["score"] = strong_oracle_score(test)
    elif control_kind == "weak_oracle":
        train["score"] = weak_oracle_score(train, seed=_seed_from_identifier(f"{control_id}:train"))
        validation["score"] = weak_oracle_score(validation, seed=_seed_from_identifier(f"{control_id}:validation"))
        test["score"] = weak_oracle_score(test, seed=_seed_from_identifier(f"{control_id}:test"))
    elif control_kind == "momentum_12_1":
        if shape != "cross_sectional":
            raise ValueError("momentum_12_1 is only supported for cross_sectional controls")
        train["score"] = momentum_12_1_score(train).fillna(0.0)
        validation["score"] = momentum_12_1_score(validation).fillna(0.0)
        test["score"] = momentum_12_1_score(test).fillna(0.0)
    else:
        raise ValueError(f"unsupported control_kind: {control_kind}")
    return train, validation, test


def _run_control_walk_forward(
    *,
    control_id: str,
    control_kind: str,
    shape: str,
    frame: pd.DataFrame,
    constraints: dict[str, Any],
    label_horizon_bars: int,
    bar_interval_ms: int,
) -> dict[str, Any]:
    windows: list[dict[str, Any]] = []
    resolved_constraints = dict(constraints)
    resolved_constraints["strategy_profile"] = BENCHMARK_CONSTRAINTS_PROFILE
    resolved_constraints["execution_venue"] = "spot"
    for train_end, validation_end, test_end, train_df, validation_df, test_df in _iter_control_walk_forward_splits(
        frame=frame,
        label_horizon_bars=label_horizon_bars,
        bar_interval_ms=bar_interval_ms,
    ):
        if not train_df.empty and not validation_df.empty and not test_df.empty:
            _, _, scored_test = _score_split_partitions(
                control_id=f"{control_id}:{train_end.isoformat()}",
                control_kind=control_kind,
                shape=shape,
                train_df=train_df,
                validation_df=validation_df,
                test_df=test_df,
            )
            metrics = _backtest_single_asset(scored_test, constraints=resolved_constraints) if shape == "single_asset" else _backtest_cross_sectional(scored_test, constraints=resolved_constraints)
            windows.append(
                {
                    "train_end_utc": train_end.isoformat().replace("+00:00", "Z"),
                    "validation_end_utc": validation_end.isoformat().replace("+00:00", "Z"),
                    "test_end_utc": test_end.isoformat().replace("+00:00", "Z"),
                    "sharpe": metrics["sharpe"],
                    "net_return": metrics["net_return"],
                    "max_drawdown": metrics["max_drawdown"],
                }
            )
    sharpes = [float(item["sharpe"]) for item in windows]
    return {
        "window_count": len(windows),
        "windows": windows,
        "median_oos_sharpe": float(np.median(sharpes)) if sharpes else 0.0,
    }


def _count_control_walk_forward_windows(
    *,
    frame: pd.DataFrame,
    label_horizon_bars: int,
    bar_interval_ms: int,
) -> int:
    return sum(
        1
        for _, _, _, train_df, validation_df, test_df in _iter_control_walk_forward_splits(
            frame=frame,
            label_horizon_bars=label_horizon_bars,
            bar_interval_ms=bar_interval_ms,
        )
        if not train_df.empty and not validation_df.empty and not test_df.empty
    )


def _iter_control_walk_forward_splits(
    *,
    frame: pd.DataFrame,
    label_horizon_bars: int,
    bar_interval_ms: int,
):
    time_index = pd.to_datetime(frame["timestamp_ms"], unit="ms", utc=True)
    if time_index.empty:
        return
    start_anchor = time_index.min() + timedelta(days=CONTROL_WALK_FORWARD_TRAIN_DAYS)
    final_anchor = time_index.max() - timedelta(days=CONTROL_WALK_FORWARD_TEST_DAYS)
    current_anchor = start_anchor
    while current_anchor <= final_anchor:
        train_end = current_anchor - timedelta(days=CONTROL_WALK_FORWARD_VALIDATION_DAYS)
        validation_end = current_anchor
        test_end = current_anchor + timedelta(days=CONTROL_WALK_FORWARD_TEST_DAYS)
        train_df, validation_df, test_df = walk_forward_split_with_purge(
            frame=frame,
            time_col="timestamp_ms",
            train_end=train_end,
            validation_end=validation_end,
            test_end=test_end,
            interval_ms=bar_interval_ms,
            label_horizon_bars=label_horizon_bars,
        )
        yield train_end, validation_end, test_end, train_df, validation_df, test_df
        current_anchor = current_anchor + timedelta(days=CONTROL_WALK_FORWARD_STEP_DAYS)


def _load_feature_set(*, artifacts_root: Path, as_of: str, shape: str) -> dict[str, Any]:
    features_root = artifacts_root / "features"
    for manifest_path in sorted(features_root.glob(f"{as_of}-*features-v1/feature_manifest.json")):
        manifest = read_json(manifest_path)
        if str(manifest.get("shape") or "") != shape:
            continue
        dataframe = pd.read_csv(manifest_path.parent / "features.csv.gz", compression="gzip")
        if "timestamp_ms" in dataframe.columns:
            dataframe["timestamp_ms"] = dataframe["timestamp_ms"].astype("int64")
        return {
            "dataset_id": str(manifest["dataset_id"]),
            "feature_set_id": str(manifest["feature_set_id"]),
            "manifest_path": manifest_path,
            "dataframe": dataframe,
        }
    raise FileNotFoundError(f"no feature manifest found for {as_of=} {shape=}")


def _infer_bar_interval_ms(frame: pd.DataFrame) -> int:
    unique_timestamps = pd.Series(sorted(frame["timestamp_ms"].drop_duplicates().tolist()), dtype="int64")
    return infer_interval_ms(unique_timestamps)


def _build_real_lane_reference(*, artifacts_root: Path, as_of: str, repo_root: Path) -> dict[str, Any]:
    manifests_root = artifacts_root / "governance" / "daily_alpha_manifests"
    global_status_counts: dict[str, int] = {}
    global_experiment_count = 0
    global_pass_count = 0
    for manifest_path in sorted(manifests_root.glob("*.json")):
        manifest = read_json(manifest_path)
        for entry in manifest.get("entries", []):
            alpha_card_path = repo_root / str(entry["alpha_card_path"])
            alpha_card = read_json(alpha_card_path)
            experiment_status = str(alpha_card.get("experiment_status") or "fail")
            global_status_counts[experiment_status] = global_status_counts.get(experiment_status, 0) + 1
            global_experiment_count += 1
            if experiment_status == "pass":
                global_pass_count += 1
    quality_summary_path = artifacts_root / "cycles" / as_of / "research_quality_summary.json"
    quality_summary = read_json(quality_summary_path)
    return {
        "global_canonical_experiment_count": int(global_experiment_count),
        "global_pass_count": int(global_pass_count),
        "global_raw_pass_rate": (global_pass_count / global_experiment_count) if global_experiment_count else 0.0,
        "global_experiment_status_counts": global_status_counts,
        "as_of_canonical_experiment_count": int(quality_summary.get("experiment_count", 0) or 0),
        "as_of_experiment_status_counts": dict(quality_summary.get("experiment_status_counts") or {}),
        "as_of_raw_pass_rate": float(quality_summary.get("raw_pass_rate", 0.0) or 0.0),
        "as_of_audit_cleared_pass_rate": float(quality_summary.get("audit_cleared_pass_rate", 0.0) or 0.0),
        "as_of_cross_sectional_median_oos_sharpe": dict(quality_summary.get("cross_sectional_median_oos_sharpe") or {}),
        "research_quality_summary_path": portable_path(quality_summary_path, repo_root=repo_root),
    }


def _pipeline_health(control_cases: list[dict[str, Any]]) -> tuple[str, str]:
    strong_cases = [case for case in control_cases if case["control_kind"] == "strong_oracle" and case["status"] == "executed"]
    weak_cases = [case for case in control_cases if case["control_kind"] == "weak_oracle" and case["status"] == "executed"]
    strong_skipped_count = sum(
        1 for case in control_cases if case["control_kind"] == "strong_oracle" and str(case.get("status") or "").startswith("skipped")
    )
    weak_skipped_count = sum(
        1 for case in control_cases if case["control_kind"] == "weak_oracle" and str(case.get("status") or "").startswith("skipped")
    )
    coverage_suffix = (
        f" Coverage telemetry: skipped {strong_skipped_count} strong-oracle and {weak_skipped_count} weak-oracle controls."
    )
    if any(not bool(case.get("raw_positive")) for case in strong_cases):
        failed = [case["control_id"] for case in strong_cases if not bool(case.get("raw_positive"))]
        return "broken", f"strong oracle controls failed raw_positive for {', '.join(failed)}.{coverage_suffix}"
    if not strong_cases:
        return (
            "marginal",
            "no strong oracle controls were eligible for execution; positive-control coverage is insufficient to treat the lane as broken or healthy."
            + coverage_suffix,
        )
    weak_positive_count = sum(1 for case in weak_cases if bool(case.get("raw_positive")))
    weak_positive_fraction = (weak_positive_count / len(weak_cases)) if weak_cases else 0.0
    if weak_positive_fraction >= 0.5:
        return (
            "healthy",
            f"all strong oracle controls passed and {weak_positive_count}/{len(weak_cases)} weak oracle controls remained raw_positive."
            + coverage_suffix,
        )
    return (
        "marginal",
        f"all strong oracle controls passed but only {weak_positive_count}/{len(weak_cases)} weak oracle controls remained raw_positive."
        + coverage_suffix,
    )


def _lane_interpretation(
    *,
    pipeline_health: str,
    real_lane_reference: dict[str, Any],
    control_cases: list[dict[str, Any]],
) -> dict[str, Any]:
    momentum_case = next((case for case in control_cases if case["control_kind"] == "momentum_12_1"), None)
    global_total = int(real_lane_reference.get("global_canonical_experiment_count", 0) or 0)
    global_pass = int(real_lane_reference.get("global_pass_count", 0) or 0)
    if pipeline_health == "broken":
        verdict = "current real-lane negatives are not interpretable yet"
        details = (
            f"At least one strong oracle failed, so the current 0/{global_total} checked-in real-lane record cannot yet be treated as a research conclusion. "
            "Repair the scoring or evaluation path before making track-level calls."
        )
    elif pipeline_health == "marginal":
        verdict = "pipeline can see obvious alpha but remains weak-signal fragile"
        details = (
            f"Strong oracle cases passed, but weak oracle transfer remained inconsistent. "
            f"The current 0/{global_total} checked-in real-lane record may still reflect tight thresholds, small samples, or brittle evaluation settings rather than purely dead signal families."
        )
    else:
        verdict = "pipeline can distinguish strong controls from the current negative lanes"
        details = (
            f"Strong oracle cases passed and weak oracle cases cleared the majority threshold. "
            f"With the current checked-in record at {global_pass}/{global_total} real-lane passes, the most likely interpretation is that the current OHLCV and Funding/OI lanes are genuinely weak under the present universe, horizon, and sample window."
        )
    if momentum_case and momentum_case["status"] == "skipped_insufficient_history":
        track_choice = (
            "Momentum 12-1 could not be scored with enough history, so it does not settle the broader track question. "
            "Treat it as a support signal only and widen the universe or data depth before using it as a decisive negative."
        )
    elif momentum_case and bool(momentum_case.get("raw_positive")):
        track_choice = (
            "Momentum 12-1 stayed positive, so the current 0/88 real-lane result points more strongly to lane-specific signal weakness than to universal crypto cross-sectional impossibility."
        )
    else:
        track_choice = (
            "Momentum 12-1 was not positive on the current 3-subject cross-sectional panel, which reinforces that this panel is too narrow to settle the strategic track question by itself. "
            "If pipeline health is healthy, the next leverage point is broader signal families or a less capacity-crowded track rather than more governance tuning."
        )
    return {
        "verdict": verdict,
        "details": details,
        "track_choice_implication": track_choice,
    }


def _render_positive_control_markdown(payload: dict[str, Any]) -> str:
    coverage_telemetry = dict(payload.get("coverage_telemetry") or {})
    single_asset_coverage = dict(coverage_telemetry.get("single_asset") or {})
    single_asset_strong_coverage = dict(single_asset_coverage.get("strong_oracle") or {})
    single_asset_weak_coverage = dict(single_asset_coverage.get("weak_oracle") or {})
    lines = [
        "# Positive Control Summary",
        "",
        "## Controls",
        "",
        f"- As of: `{payload['as_of']}`",
        f"- Benchmark constraints profile: `{payload['benchmark_constraints_profile']}`",
        f"- Single-asset subjects: `{payload['subject_count_by_shape']['single_asset']}`",
        f"- Cross-sectional subjects: `{payload['subject_count_by_shape']['cross_sectional']}`",
        f"- Current checked-in real-lane total: `{payload['real_lane_reference']['global_pass_count']}/{payload['real_lane_reference']['global_canonical_experiment_count']}` passes",
        (
            "- Single-asset strong oracle coverage: "
            f"`executed={single_asset_strong_coverage.get('executed_count', 0)}` "
            f"`skipped={single_asset_strong_coverage.get('skipped_count', 0)}`"
        ),
        (
            "- Single-asset weak oracle coverage: "
            f"`executed={single_asset_weak_coverage.get('executed_count', 0)}` "
            f"`skipped={single_asset_weak_coverage.get('skipped_count', 0)}`"
        ),
        "",
        "## Results Matrix",
        "",
        "| control_id | shape | kind | status | raw_positive | production_admissibility | validation_sharpe | test_sharpe | walk_forward_median_oos_sharpe |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for case in payload["control_cases"]:
        validation_sharpe = _metric_cell(case.get("validation_metrics"), "sharpe")
        test_sharpe = _metric_cell(case.get("test_metrics"), "sharpe")
        walk_forward_median = _walk_forward_cell(case.get("walk_forward"))
        lines.append(
            "| "
            + " | ".join(
                [
                    str(case["control_id"]),
                    str(case["shape"]),
                    str(case["control_kind"]),
                    str(case["status"]),
                    str(case.get("raw_positive")),
                    str(case.get("production_admissibility")),
                    validation_sharpe,
                    test_sharpe,
                    walk_forward_median,
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Pipeline Health Verdict",
            "",
            f"- Pipeline health: `{payload['pipeline_health']}`",
            f"- Rationale: {payload['pipeline_health_rationale']}",
            "",
            "## What 0/88 Means Now",
            "",
            payload["lane_interpretation"]["details"],
            "",
            "## Implication For Track Choice",
            "",
            payload["lane_interpretation"]["track_choice_implication"],
        ]
    )
    return "\n".join(lines)


def _positive_control_root(*, artifacts_root: Path, as_of: str) -> Path:
    return artifacts_root / "assessments" / "positive_controls" / as_of


def _control_id(*, as_of: str, shape: str, control_kind: str, subject: str | None) -> str:
    tokens = [as_of, shape.replace("_", "-")]
    if subject:
        tokens.append(str(subject).lower())
    tokens.append(control_kind.replace("_", "-"))
    return "-".join(tokens)


def _seed_from_identifier(value: str) -> int:
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=False)


def _metric_cell(metrics: dict[str, Any] | None, key: str) -> str:
    if not isinstance(metrics, dict):
        return "NA"
    value = metrics.get(key)
    if value is None:
        return "NA"
    return f"{float(value):.4f}"


def _walk_forward_cell(walk_forward: dict[str, Any] | None) -> str:
    if not isinstance(walk_forward, dict):
        return "NA"
    value = walk_forward.get("median_oos_sharpe")
    if value is None:
        return "NA"
    return f"{float(value):.4f}"


def _skipped_control_case(
    *,
    control_id: str,
    shape: str,
    control_kind: str,
    dataset_id: str,
    feature_set_id: str,
    subject: str | None,
    expected_future_dependency: bool,
    skipped_reason: str,
    label_horizon_bars: int | None = None,
    bar_interval_ms: int | None = None,
    available_walk_forward_window_count: int | None = None,
    minimum_walk_forward_windows_required: int | None = None,
) -> dict[str, Any]:
    return {
        "control_id": control_id,
        "shape": shape,
        "subject": subject,
        "control_kind": control_kind,
        "status": skipped_reason,
        "expected_future_dependency": bool(expected_future_dependency),
        "dataset_id": dataset_id,
        "feature_set_id": feature_set_id,
        "benchmark_constraints_profile": BENCHMARK_CONSTRAINTS_PROFILE,
        "label_horizon_bars": label_horizon_bars,
        "bar_interval_ms": bar_interval_ms,
        "raw_positive": None,
        "production_admissibility": "not_applicable_skipped_insufficient_history",
        "validation_metrics": None,
        "test_metrics": None,
        "walk_forward": {
            "window_count": int(available_walk_forward_window_count or 0),
            "windows": [],
            "median_oos_sharpe": None,
        },
        "available_walk_forward_window_count": available_walk_forward_window_count,
        "minimum_walk_forward_windows_required": minimum_walk_forward_windows_required,
        "score_sign_counts": None,
        "position_sign_counts": None,
        "nonzero_position_fraction": None,
        "label_split_overlap": None,
        "split_boundary_contamination_counts": None,
        "backtest_horizon_mismatch": None,
    }


def _minimum_walk_forward_windows_required(*, shape: str, control_kind: str) -> int | None:
    if shape == "single_asset" and control_kind in {"strong_oracle", "weak_oracle"}:
        return MIN_SINGLE_ASSET_POSITIVE_CONTROL_WALK_FORWARD_WINDOWS
    return None


def _control_case_coverage_telemetry(control_cases: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, int]]]:
    telemetry: dict[str, dict[str, dict[str, int]]] = {}
    for shape in sorted({str(case.get("shape") or "") for case in control_cases if str(case.get("shape") or "")}):
        telemetry[shape] = {}
        shape_cases = [case for case in control_cases if str(case.get("shape") or "") == shape]
        for control_kind in sorted(
            {str(case.get("control_kind") or "") for case in shape_cases if str(case.get("control_kind") or "")}
        ):
            relevant_cases = [case for case in shape_cases if str(case.get("control_kind") or "") == control_kind]
            telemetry[shape][control_kind] = {
                "total_count": len(relevant_cases),
                "executed_count": sum(1 for case in relevant_cases if str(case.get("status") or "") == "executed"),
                "skipped_count": sum(
                    1 for case in relevant_cases if str(case.get("status") or "").startswith("skipped")
                ),
            }
    return telemetry


def _position_diagnostics(
    *,
    shape: str,
    scored_test: pd.DataFrame,
    constraints: dict[str, Any],
) -> dict[str, Any]:
    scores = scored_test.get("score", pd.Series(dtype="float64")).fillna(0.0).astype("float64")
    if scores.empty:
        return {
            "score_sign_counts": {"positive": 0, "negative": 0, "zero": 0},
            "position_sign_counts": {"positive": 0, "negative": 0, "zero": 0},
            "nonzero_position_fraction": 0.0,
        }
    if shape == "single_asset":
        positions = _single_asset_position_from_score(scores, constraints=constraints)
    else:
        positions = pd.Series(np.nan, index=scores.index, dtype="float64")
    return {
        "score_sign_counts": _sign_counts(scores),
        "position_sign_counts": _sign_counts(positions),
        "nonzero_position_fraction": float((positions != 0).mean()) if not positions.empty else 0.0,
    }


def _sign_counts(series: pd.Series) -> dict[str, int]:
    if series.empty:
        return {"positive": 0, "negative": 0, "zero": 0}
    cleaned = series.fillna(0.0).astype("float64")
    return {
        "positive": int((cleaned > 0).sum()),
        "negative": int((cleaned < 0).sum()),
        "zero": int((cleaned == 0).sum()),
    }
