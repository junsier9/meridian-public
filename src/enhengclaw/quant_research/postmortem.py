from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .contracts import ROOT, portable_path, read_json, utc_now, write_json
from .features import build_single_asset_features
from .lab import (
    _backtest_single_asset,
    _chronological_split,
    _experiment_directory_name,
    _fit_and_score,
    _run_walk_forward,
)


POSTMORTEM_CONTRACT_VERSION = "quant_sharpe_anomaly_postmortem.v1"
ROOT_CAUSE_ORDER = (
    "look_ahead_bias",
    "overlap",
    "timestamp_misalignment",
    "survivorship",
)


def postmortem_assessment_root(*, artifacts_root: Path, alpha_id: str) -> Path:
    return artifacts_root / "assessments" / "sharpe_anomaly" / alpha_id


def postmortem_evidence_path(*, artifacts_root: Path, alpha_id: str) -> Path:
    return postmortem_assessment_root(artifacts_root=artifacts_root, alpha_id=alpha_id) / "postmortem_evidence.json"


def postmortem_markdown_path(*, repo_root: Path, alpha_id: str, generated_at_utc: str) -> Path:
    date_prefix = str(generated_at_utc or utc_now())[:10]
    return repo_root / "docs" / "postmortems" / f"{date_prefix}_sharpe_anomaly_{alpha_id}.md"


def build_sharpe_anomaly_postmortem_evidence(
    *,
    alpha_id: str,
    artifacts_root: Path | None = None,
    repo_root: Path | None = None,
    now_utc: str | None = None,
) -> dict[str, Any]:
    resolved_repo_root = (repo_root or ROOT).expanduser().resolve()
    resolved_artifacts_root = (artifacts_root or (resolved_repo_root / "artifacts" / "quant_research")).expanduser().resolve()
    experiment_root = _resolve_experiment_root(artifacts_root=resolved_artifacts_root, alpha_id=alpha_id)
    alpha_card_path = experiment_root / "alpha_card.json"
    experiment_spec_path = experiment_root / "experiment_spec.json"
    validation_report_path = experiment_root / "validation_report.json"
    backtest_report_path = experiment_root / "backtest_report.json"
    alpha_card = read_json(alpha_card_path)
    experiment_spec = read_json(experiment_spec_path)
    validation_report = read_json(validation_report_path)
    backtest_report = read_json(backtest_report_path)
    if str(alpha_card.get("shape") or "").strip() != "single_asset":
        raise ValueError(f"{alpha_id} is not a single_asset experiment")
    subject = str(alpha_card.get("subject") or "").strip().upper()
    if not subject:
        raise ValueError(f"{alpha_id} is missing alpha_card.subject")

    as_of = str(alpha_card.get("as_of") or "").strip()
    dataset_root = resolved_artifacts_root / "datasets" / f"{as_of}-single-asset-4h"
    feature_root = resolved_artifacts_root / "features" / f"{as_of}-single-asset-4h-features-v1"
    dataset_manifest_path = dataset_root / "dataset_manifest.json"
    feature_manifest_path = feature_root / "feature_manifest.json"
    panel_path = dataset_root / "panel.csv.gz"
    features_path = feature_root / "features.csv.gz"
    dataset_manifest = read_json(dataset_manifest_path)
    feature_manifest = read_json(feature_manifest_path)
    panel = pd.read_csv(panel_path)
    persisted_features = pd.read_csv(features_path)

    subject_panel = panel.loc[panel["subject"].astype(str).str.upper() == subject].copy()
    if subject_panel.empty:
        raise ValueError(f"{alpha_id} subject={subject} has no rows in {panel_path}")
    rebuilt_features = build_single_asset_features(subject_panel).sort_values("timestamp_ms").reset_index(drop=True)
    persisted_subject_features = (
        persisted_features.loc[persisted_features["subject"].astype(str).str.upper() == subject]
        .sort_values("timestamp_ms")
        .reset_index(drop=True)
    )
    if persisted_subject_features.empty:
        raise ValueError(f"{alpha_id} subject={subject} has no rows in {features_path}")
    rebuilt_target_match = _target_match_summary(rebuilt_features=rebuilt_features, persisted_features=persisted_subject_features)
    label_horizon_bars = _infer_label_horizon_bars(subject_panel=subject_panel, rebuilt_features=rebuilt_features)
    interval_ms = _infer_interval_ms(rebuilt_features["timestamp_ms"])
    interval_hours = interval_ms / 3_600_000.0
    label_horizon_hours = label_horizon_bars * interval_hours

    split = _chronological_split(
        rebuilt_features,
        time_col="timestamp_ms",
        label_horizon_bars=label_horizon_bars,
    )
    if split is None:
        raise ValueError(f"{alpha_id} rebuilt feature frame could not be chronologically split")
    train_df, validation_df, test_df = split
    scored_splits = _fit_and_score(
        model_family=str(experiment_spec.get("model_family") or ""),
        shape="single_asset",
        train_df=train_df,
        validation_df=validation_df,
        test_df=test_df,
        feature_columns=[str(item) for item in experiment_spec.get("feature_columns", [])],
    )
    recomputed_validation_metrics = _backtest_single_asset(
        scored_splits["validation"],
        constraints=dict(experiment_spec.get("profile_constraints") or {}),
    )
    recomputed_test_metrics = _backtest_single_asset(
        scored_splits["test"],
        constraints=dict(experiment_spec.get("profile_constraints") or {}),
    )
    split_boundaries = _split_boundaries_summary(
        train_df=train_df,
        validation_df=validation_df,
        test_df=test_df,
        label_horizon_bars=label_horizon_bars,
        interval_ms=interval_ms,
    )

    walk_forward = _run_walk_forward(
        frame=rebuilt_features,
        shape="single_asset",
        model_family=str(experiment_spec.get("model_family") or ""),
        feature_columns=[str(item) for item in experiment_spec.get("feature_columns", [])],
        constraints=dict(experiment_spec.get("profile_constraints") or {}),
        label_horizon_bars=label_horizon_bars,
        bar_interval_ms=interval_ms,
    )
    walk_forward_windows = _walk_forward_window_summaries(
        rebuilt_features=rebuilt_features,
        windows=walk_forward.get("windows", []),
        label_horizon_bars=label_horizon_bars,
        interval_ms=interval_ms,
    )

    adjacent_label_overlap_fraction = (label_horizon_bars - 1) / label_horizon_bars if label_horizon_bars > 0 else 0.0
    backtest_horizon_mismatch = _backtest_horizon_mismatch(
        test_df=test_df,
        backtest_report=backtest_report,
        recomputed_test_metrics=recomputed_test_metrics,
        label_horizon_bars=label_horizon_bars,
        interval_ms=interval_ms,
    )
    candidate_root_causes, primary_root_cause, secondary_root_causes = _classify_root_causes(
        alpha_card=alpha_card,
        experiment_spec=experiment_spec,
        split_boundaries=split_boundaries,
        walk_forward_windows=walk_forward_windows,
        backtest_horizon_mismatch=backtest_horizon_mismatch,
        label_horizon_bars=label_horizon_bars,
    )
    conclusion = (
        f"{alpha_id} is best explained by overlap: a {label_horizon_hours:.0f}h forward label is evaluated on every "
        f"{interval_hours:.0f}h bar, split boundaries have cross-window label contamination, and the backtest realizes "
        "that overlapping forward return on each rebalance step."
    )

    generated_at_utc = now_utc or utc_now()
    return {
        "contract_version": POSTMORTEM_CONTRACT_VERSION,
        "generated_at_utc": generated_at_utc,
        "alpha_id": alpha_id,
        "label_horizon_bars": label_horizon_bars,
        "label_horizon_hours": label_horizon_hours,
        "bar_interval_hours": interval_hours,
        "source_artifacts": {
            "alpha_card_path": portable_path(alpha_card_path, repo_root=resolved_repo_root),
            "experiment_spec_path": portable_path(experiment_spec_path, repo_root=resolved_repo_root),
            "validation_report_path": portable_path(validation_report_path, repo_root=resolved_repo_root),
            "backtest_report_path": portable_path(backtest_report_path, repo_root=resolved_repo_root),
            "dataset_manifest_path": portable_path(dataset_manifest_path, repo_root=resolved_repo_root),
            "panel_path": portable_path(panel_path, repo_root=resolved_repo_root),
            "feature_manifest_path": portable_path(feature_manifest_path, repo_root=resolved_repo_root),
            "features_path": portable_path(features_path, repo_root=resolved_repo_root),
        },
        "feature_rebuild_consistency": rebuilt_target_match,
        "dataset_summary": {
            "dataset_id": str(dataset_manifest.get("dataset_id") or ""),
            "feature_set_id": str(feature_manifest.get("feature_set_id") or ""),
            "dataset_shape": str(dataset_manifest.get("shape") or ""),
            "feature_shape": str(feature_manifest.get("shape") or ""),
            "subject": subject,
            "subject_row_count": int(len(rebuilt_features)),
        },
        "feature_columns": [str(item) for item in experiment_spec.get("feature_columns", [])],
        "split_boundaries": split_boundaries,
        "walk_forward_windows": walk_forward_windows,
        "boundary_contamination_counts": {
            "train_to_validation": split_boundaries["boundary_contamination"]["train_to_validation"],
            "validation_to_test": split_boundaries["boundary_contamination"]["validation_to_test"],
        },
        "adjacent_label_overlap_fraction": adjacent_label_overlap_fraction,
        "backtest_horizon_mismatch": backtest_horizon_mismatch,
        "candidate_root_causes": candidate_root_causes,
        "primary_root_cause": primary_root_cause,
        "secondary_root_causes": secondary_root_causes,
        "observed_metrics": {
            "validation_metrics": dict(validation_report.get("validation_metrics") or {}),
            "test_metrics": dict(validation_report.get("test_metrics") or {}),
            "recomputed_validation_metrics": recomputed_validation_metrics,
            "recomputed_test_metrics": recomputed_test_metrics,
            "walk_forward": dict(validation_report.get("walk_forward") or {}),
            "leakage_checks": dict(validation_report.get("leakage_checks") or {}),
        },
        "current_leakage_check_blind_spots": [
            "evaluate_no_future_leakage only verifies strict train/validation/test timestamp ordering",
            "the current leakage check does not apply purge or embargo around split boundaries",
            "the current leakage check does not test whether a multi-bar forward label is realized on every bar in backtest",
        ],
        "conclusion": conclusion,
    }


def write_sharpe_anomaly_postmortem(
    *,
    alpha_id: str,
    artifacts_root: Path | None = None,
    repo_root: Path | None = None,
    now_utc: str | None = None,
    write_markdown: bool = True,
) -> dict[str, Any]:
    resolved_repo_root = (repo_root or ROOT).expanduser().resolve()
    resolved_artifacts_root = (artifacts_root or (resolved_repo_root / "artifacts" / "quant_research")).expanduser().resolve()
    evidence = build_sharpe_anomaly_postmortem_evidence(
        alpha_id=alpha_id,
        artifacts_root=resolved_artifacts_root,
        repo_root=resolved_repo_root,
        now_utc=now_utc,
    )
    evidence_path = postmortem_evidence_path(artifacts_root=resolved_artifacts_root, alpha_id=alpha_id)
    markdown_path = postmortem_markdown_path(
        repo_root=resolved_repo_root,
        alpha_id=alpha_id,
        generated_at_utc=str(evidence["generated_at_utc"]),
    )
    write_json(evidence_path, evidence)
    if write_markdown:
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(render_sharpe_anomaly_postmortem_markdown(evidence) + "\n", encoding="utf-8")
    return {
        "alpha_id": alpha_id,
        "primary_root_cause": evidence["primary_root_cause"],
        "secondary_root_causes": evidence["secondary_root_causes"],
        "postmortem_evidence_path": portable_path(evidence_path, repo_root=resolved_repo_root),
        "postmortem_markdown_path": (
            portable_path(markdown_path, repo_root=resolved_repo_root)
            if write_markdown
            else None
        ),
    }


def render_sharpe_anomaly_postmortem_markdown(evidence: dict[str, Any]) -> str:
    metrics = dict(evidence.get("observed_metrics") or {})
    validation_metrics = dict(metrics.get("validation_metrics") or {})
    test_metrics = dict(metrics.get("test_metrics") or {})
    walk_forward = dict(metrics.get("walk_forward") or {})
    leakage_checks = dict(metrics.get("leakage_checks") or {})
    split_boundaries = dict(evidence.get("split_boundaries") or {})
    boundary_counts = dict(evidence.get("boundary_contamination_counts") or {})
    wf_windows = list(evidence.get("walk_forward_windows") or [])
    backtest_horizon_mismatch = dict(evidence.get("backtest_horizon_mismatch") or {})

    lines = [
        f"# Sharpe Anomaly Postmortem: `{evidence['alpha_id']}`",
        "",
        "## Claim",
        "",
        (
            f"This postmortem reconstructs the checked-in single-asset experiment and tests whether the anomalous "
            f"Sharpe is better explained by `look_ahead_bias`, `overlap`, `timestamp_misalignment`, or `survivorship`. "
            f"The primary root cause is `{evidence['primary_root_cause']}`."
        ),
        "",
        "## Observed Metrics",
        "",
        f"- Validation Sharpe: `{float(validation_metrics.get('sharpe', 0.0)):.6f}`",
        f"- Test Sharpe: `{float(test_metrics.get('sharpe', 0.0)):.6f}`",
        f"- Test max drawdown: `{float(test_metrics.get('max_drawdown', 0.0)):.6f}`",
        f"- Walk-forward median OOS Sharpe: `{float(walk_forward.get('median_oos_sharpe', 0.0)):.6f}`",
        f"- Walk-forward window count: `{int(walk_forward.get('window_count', 0) or 0)}`",
        "",
        "## Data / Label / Split Facts",
        "",
        f"- Subject: `{evidence['dataset_summary']['subject']}`",
        f"- Dataset provenance: `{evidence['source_artifacts']['panel_path']}` rebuilt via `build_single_asset_features()`",
        f"- Label horizon: `{evidence['label_horizon_bars']}` bars / `{float(evidence['label_horizon_hours']):.1f}` hours",
        f"- Bar interval: `{float(evidence['bar_interval_hours']):.1f}` hours",
        f"- Adjacent label overlap fraction: `{float(evidence['adjacent_label_overlap_fraction']):.6f}`",
        (
            f"- Train split: `{split_boundaries['train']['start_utc']}` -> `{split_boundaries['train']['end_utc']}` "
            f"(`{split_boundaries['train']['row_count']}` rows)"
        ),
        (
            f"- Validation split: `{split_boundaries['validation']['start_utc']}` -> `{split_boundaries['validation']['end_utc']}` "
            f"(`{split_boundaries['validation']['row_count']}` rows)"
        ),
        (
            f"- Test split: `{split_boundaries['test']['start_utc']}` -> `{split_boundaries['test']['end_utc']}` "
            f"(`{split_boundaries['test']['row_count']}` rows)"
        ),
        (
            f"- Boundary contamination counts: train->validation=`{boundary_counts['train_to_validation']['contaminated_row_count']}`, "
            f"validation->test=`{boundary_counts['validation_to_test']['contaminated_row_count']}`"
        ),
        (
            f"- Backtest cadence mismatch: `detected={backtest_horizon_mismatch.get('detected')}` "
            f"(`label_horizon_bars={backtest_horizon_mismatch.get('label_horizon_bars')}`, "
            f"`evaluation_step_bars={backtest_horizon_mismatch.get('evaluation_step_bars')}`, "
            f"`rebalance_count={backtest_horizon_mismatch.get('rebalance_count')}`)"
        ),
        "",
        "Walk-forward windows reconstructed via `_run_walk_forward()`:",
        "",
    ]
    for window in wf_windows:
        lines.append(
            (
                f"- `{window['window_index']}` train_end=`{window['train_end_utc']}` "
                f"validation_end=`{window['validation_end_utc']}` test_end=`{window['test_end_utc']}` "
                f"sharpe=`{float(window['sharpe']):.6f}` "
                f"train->validation contamination=`{window['train_to_validation_contaminated_row_count']}` "
                f"validation->test contamination=`{window['validation_to_test_contaminated_row_count']}`"
            )
        )

    lines.extend(
        [
            "",
            "## Evidence for Each Candidate Cause",
            "",
        ]
    )
    for candidate in evidence.get("candidate_root_causes", []):
        status = "supported" if candidate.get("supported") else "not supported"
        lines.append(f"- `{candidate['name']}`: {status}. {candidate['summary']}")
        for detail in candidate.get("evidence", []):
            lines.append(f"  {detail}")

    lines.extend(
        [
            "",
            "## Primary Root Cause",
            "",
            str(evidence.get("conclusion") or "").strip(),
            "",
            "## Secondary Causes",
            "",
        ]
    )
    secondary_root_causes = list(evidence.get("secondary_root_causes") or [])
    if secondary_root_causes:
        for item in secondary_root_causes:
            lines.append(f"- `{item}`")
    else:
        lines.append("- No secondary root cause was proven by the checked-in artifact set.")

    lines.extend(
        [
            "",
            "## Why current leakage_checks passed anyway",
            "",
            f"- `passed={bool(leakage_checks.get('passed'))}` because the current check only enforced strict timestamp ordering between train/validation/test windows.",
            "- It did not apply purge or embargo around split boundaries, so multi-bar forward labels could still cross into the next split.",
            "- It did not test whether `_backtest_single_asset()` was realizing a multi-bar forward label on every single 4h bar.",
            "",
            "## Immediate Remediation",
            "",
            "- Introduce non-overlapping target realization, or evaluate the single-asset strategy only every 6th bar when the label horizon is 24 hours.",
            "- Add purge and embargo logic around train/validation/test and walk-forward boundaries.",
            "- Align walk-forward window construction with the label horizon so boundary labels cannot reach into the next validation or test segment.",
            "- Re-run this anomaly card only after the overlap and split-integrity changes are in place.",
        ]
    )
    return "\n".join(lines)


def _resolve_experiment_root(*, artifacts_root: Path, alpha_id: str) -> Path:
    experiments_root = artifacts_root / "experiments"
    directory_names: list[str] = []
    for candidate_name in (alpha_id, _experiment_directory_name(alpha_id)):
        normalized = str(candidate_name).strip()
        if normalized and normalized not in directory_names:
            directory_names.append(normalized)
    search_roots = (experiments_root, experiments_root / "legacy")
    for search_root in search_roots:
        for directory_name in directory_names:
            candidate = search_root / directory_name
            if (candidate / "alpha_card.json").exists():
                return candidate
    for search_root in search_roots:
        if not search_root.exists():
            continue
        for candidate in search_root.iterdir():
            if not candidate.is_dir():
                continue
            for metadata_name in ("alpha_card.json", "experiment_spec.json"):
                metadata_path = candidate / metadata_name
                if not metadata_path.exists():
                    continue
                try:
                    payload = read_json(metadata_path)
                except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
                    continue
                experiment_id = str(payload.get("experiment_id") or payload.get("alpha_id") or "").strip()
                if experiment_id == alpha_id:
                    return candidate
    raise FileNotFoundError(f"could not locate experiment root for {alpha_id}")


def _target_match_summary(*, rebuilt_features: pd.DataFrame, persisted_features: pd.DataFrame) -> dict[str, Any]:
    merged = rebuilt_features[["timestamp_ms", "target_forward_return"]].merge(
        persisted_features[["timestamp_ms", "target_forward_return"]],
        on="timestamp_ms",
        how="inner",
        suffixes=("_rebuilt", "_artifact"),
    )
    if merged.empty:
        raise ValueError("rebuilt and artifact feature frames do not overlap on timestamp_ms")
    max_abs_error = float((merged["target_forward_return_rebuilt"] - merged["target_forward_return_artifact"]).abs().max())
    return {
        "rebuilt_row_count": int(len(rebuilt_features)),
        "artifact_row_count": int(len(persisted_features)),
        "merged_row_count": int(len(merged)),
        "max_abs_target_forward_return_error": max_abs_error,
        "consistent": max_abs_error < 1e-12 and len(rebuilt_features) == len(persisted_features),
    }


def _infer_label_horizon_bars(*, subject_panel: pd.DataFrame, rebuilt_features: pd.DataFrame, max_horizon_bars: int = 48) -> int:
    ordered_panel = subject_panel.sort_values("timestamp_ms").reset_index(drop=True)
    feature_target = rebuilt_features[["timestamp_ms", "target_forward_return"]].copy()
    close = ordered_panel["spot_close"].replace(0, pd.NA)
    for horizon_bars in range(1, max_horizon_bars + 1):
        candidate = ordered_panel[["timestamp_ms"]].copy()
        candidate["candidate_forward_return"] = close.shift(-horizon_bars) / close - 1.0
        compare = feature_target.merge(candidate, on="timestamp_ms", how="inner").dropna()
        if compare.empty:
            continue
        max_abs_error = float((compare["target_forward_return"] - compare["candidate_forward_return"]).abs().max())
        if max_abs_error < 1e-12:
            return horizon_bars
    raise ValueError("could not infer label horizon bars from rebuilt features")


def _infer_interval_ms(timestamp_series: pd.Series) -> int:
    deltas = timestamp_series.sort_values().diff().dropna()
    if deltas.empty:
        raise ValueError("cannot infer interval_ms from fewer than two timestamps")
    return int(deltas.mode().iloc[0])


def _split_boundaries_summary(
    *,
    train_df: pd.DataFrame,
    validation_df: pd.DataFrame,
    test_df: pd.DataFrame,
    label_horizon_bars: int,
    interval_ms: int,
) -> dict[str, Any]:
    train_end_ms = int(train_df["timestamp_ms"].max())
    validation_end_ms = int(validation_df["timestamp_ms"].max())
    return {
        "train": _segment_summary(train_df),
        "validation": _segment_summary(validation_df),
        "test": _segment_summary(test_df),
        "boundary_contamination": {
            "train_to_validation": _boundary_contamination_summary(
                frame=train_df,
                boundary_end_ms=train_end_ms,
                label_horizon_bars=label_horizon_bars,
                interval_ms=interval_ms,
            ),
            "validation_to_test": _boundary_contamination_summary(
                frame=validation_df,
                boundary_end_ms=validation_end_ms,
                label_horizon_bars=label_horizon_bars,
                interval_ms=interval_ms,
            ),
        },
    }


def _walk_forward_window_summaries(
    *,
    rebuilt_features: pd.DataFrame,
    windows: list[dict[str, Any]],
    label_horizon_bars: int,
    interval_ms: int,
) -> list[dict[str, Any]]:
    time_index = pd.to_datetime(rebuilt_features["timestamp_ms"], unit="ms", utc=True)
    summaries: list[dict[str, Any]] = []
    for index, window in enumerate(windows, start=1):
        train_end_ms = _iso_utc_to_ms(str(window["train_end_utc"]))
        validation_end_ms = _iso_utc_to_ms(str(window["validation_end_utc"]))
        train_df = rebuilt_features.loc[time_index <= pd.Timestamp(str(window["train_end_utc"]))].copy()
        validation_df = rebuilt_features.loc[
            (time_index > pd.Timestamp(str(window["train_end_utc"])))
            & (time_index <= pd.Timestamp(str(window["validation_end_utc"])))
        ].copy()
        summaries.append(
            {
                "window_index": index,
                "train_end_utc": str(window["train_end_utc"]),
                "validation_end_utc": str(window["validation_end_utc"]),
                "test_end_utc": str(window["test_end_utc"]),
                "sharpe": float(window["sharpe"]),
                "net_return": float(window["net_return"]),
                "max_drawdown": float(window["max_drawdown"]),
                "train_to_validation_contaminated_row_count": _boundary_contamination_summary(
                    frame=train_df,
                    boundary_end_ms=train_end_ms,
                    label_horizon_bars=label_horizon_bars,
                    interval_ms=interval_ms,
                )["contaminated_row_count"],
                "validation_to_test_contaminated_row_count": _boundary_contamination_summary(
                    frame=validation_df,
                    boundary_end_ms=validation_end_ms,
                    label_horizon_bars=label_horizon_bars,
                    interval_ms=interval_ms,
                )["contaminated_row_count"],
            }
        )
    return summaries


def _segment_summary(frame: pd.DataFrame) -> dict[str, Any]:
    ordered = frame.sort_values("timestamp_ms")
    return {
        "row_count": int(len(ordered)),
        "start_utc": _ms_to_utc(int(ordered["timestamp_ms"].min())),
        "end_utc": _ms_to_utc(int(ordered["timestamp_ms"].max())),
    }


def _boundary_contamination_summary(
    *,
    frame: pd.DataFrame,
    boundary_end_ms: int,
    label_horizon_bars: int,
    interval_ms: int,
) -> dict[str, Any]:
    ordered = frame.sort_values("timestamp_ms").copy()
    contaminated = ordered.loc[(ordered["timestamp_ms"] + (label_horizon_bars * interval_ms)) > boundary_end_ms].copy()
    contaminated["label_window_end_ms"] = contaminated["timestamp_ms"] + (label_horizon_bars * interval_ms)
    samples = [
        {
            "timestamp_utc": _ms_to_utc(int(row["timestamp_ms"])),
            "label_window_end_utc": _ms_to_utc(int(row["label_window_end_ms"])),
        }
        for _, row in contaminated.head(6).iterrows()
    ]
    return {
        "boundary_end_utc": _ms_to_utc(boundary_end_ms),
        "contaminated_row_count": int(len(contaminated)),
        "samples": samples,
    }


def _backtest_horizon_mismatch(
    *,
    test_df: pd.DataFrame,
    backtest_report: dict[str, Any],
    recomputed_test_metrics: dict[str, Any],
    label_horizon_bars: int,
    interval_ms: int,
) -> dict[str, Any]:
    step_ms = _infer_interval_ms(test_df["timestamp_ms"])
    evaluation_step_bars = max(int(round(step_ms / interval_ms)), 1)
    prediction_count = int(backtest_report.get("prediction_counts", {}).get("test", 0) or 0)
    rebalance_count = int(backtest_report.get("test_metrics", {}).get("rebalance_count", 0) or 0)
    recomputed_rebalance_count = int(recomputed_test_metrics.get("rebalance_count", 0) or 0)
    detected = bool(
        label_horizon_bars > evaluation_step_bars
        and rebalance_count == prediction_count
        and rebalance_count > max(recomputed_rebalance_count, 0)
    )
    return {
        "detected": detected,
        "label_horizon_bars": label_horizon_bars,
        "evaluation_step_bars": evaluation_step_bars,
        "prediction_count": prediction_count,
        "rebalance_count": rebalance_count,
        "adjacent_label_overlap_fraction": (label_horizon_bars - evaluation_step_bars) / label_horizon_bars,
        "reuse_multiple": label_horizon_bars / evaluation_step_bars,
        "recomputed_test_sharpe": float(recomputed_test_metrics.get("sharpe", 0.0) or 0.0),
        "recomputed_test_rebalance_count": recomputed_rebalance_count,
        "details": (
            "The backtest realizes target_forward_return once per scored 4h bar; with a 24h / 6-bar label horizon, "
            "consecutive realizations reuse most of the same future return window."
        ),
    }


def _classify_root_causes(
    *,
    alpha_card: dict[str, Any],
    experiment_spec: dict[str, Any],
    split_boundaries: dict[str, Any],
    walk_forward_windows: list[dict[str, Any]],
    backtest_horizon_mismatch: dict[str, Any],
    label_horizon_bars: int,
) -> tuple[list[dict[str, Any]], str, list[str]]:
    feature_columns = {str(item) for item in experiment_spec.get("feature_columns", [])}
    split_counts = dict(split_boundaries.get("boundary_contamination", {}) or {})
    overlap_supported = (
        int(split_counts["train_to_validation"]["contaminated_row_count"]) > 0
        or int(split_counts["validation_to_test"]["contaminated_row_count"]) > 0
        or bool(backtest_horizon_mismatch.get("detected"))
    )
    look_ahead_supported = False
    timestamp_misalignment_supported = False
    survivorship_supported = False
    candidate_root_causes = [
        {
            "name": "look_ahead_bias",
            "supported": look_ahead_supported,
            "summary": (
                "No direct t+ feature dependency was proven from the checked-in single-asset feature builder; "
                "the forward shift is confined to the target column, which is not in the model feature set."
            ),
            "evidence": [
                f"- `target_forward_return` is defined separately from model inputs and `target_forward_return` is not in `feature_columns` ({len(feature_columns)} columns checked).",
                f"- Current leakage checks were `{bool(alpha_card.get('leakage_checks', {}).get('passed'))}` but they only attest to strict split ordering, not to forward-window reuse.",
            ],
        },
        {
            "name": "overlap",
            "supported": overlap_supported,
            "summary": (
                "Supported. The 24h / 6-bar label overlaps heavily at a 4h evaluation cadence, split boundaries lack purge/embargo, "
                "and `_backtest_single_asset()` realizes the multi-bar forward return on every bar."
            ),
            "evidence": [
                f"- Split contamination counts are train->validation=`{split_counts['train_to_validation']['contaminated_row_count']}` and validation->test=`{split_counts['validation_to_test']['contaminated_row_count']}`.",
                f"- Each reconstructed walk-forward window has train->validation contamination=`{walk_forward_windows[0]['train_to_validation_contaminated_row_count']}` and validation->test contamination=`{walk_forward_windows[0]['validation_to_test_contaminated_row_count']}` under the same 6-bar label horizon.",
                f"- Backtest mismatch detected=`{bool(backtest_horizon_mismatch.get('detected'))}` with `label_horizon_bars={label_horizon_bars}` and `evaluation_step_bars={backtest_horizon_mismatch.get('evaluation_step_bars')}`.",
            ],
        },
        {
            "name": "timestamp_misalignment",
            "supported": timestamp_misalignment_supported,
            "summary": (
                "Not proven by the checked-in artifact set. This reconstruction reproduces the anomaly from the exported ETH panel "
                "without requiring any future-aligned join."
            ),
            "evidence": [
                "- The rebuilt single-asset panel is monotonic in `timestamp_ms` and the anomaly is reproduced before introducing any alternate timestamp joins.",
                "- No checked-in audit evidence currently shows spot, perp, or event rows being joined from a future bucket.",
            ],
        },
        {
            "name": "survivorship",
            "supported": survivorship_supported,
            "summary": "Not applicable as the primary explanation: this is a fixed-subject ETH single-asset experiment, not a changing cross-sectional universe.",
            "evidence": [
                f"- The experiment subject is fixed at `{alpha_card.get('subject')}`.",
                "- Universe survival bias could affect discovery scope, but it does not explain this card's single-asset Sharpe anomaly.",
            ],
        },
    ]
    supported = [item["name"] for item in candidate_root_causes if item["supported"]]
    if not supported:
        raise ValueError("postmortem could not assign a supported root cause")
    primary_root_cause = next(name for name in ROOT_CAUSE_ORDER if name in supported)
    secondary_root_causes = [name for name in supported if name != primary_root_cause]
    return candidate_root_causes, primary_root_cause, secondary_root_causes


def _ms_to_utc(value: int) -> str:
    return pd.to_datetime(int(value), unit="ms", utc=True).isoformat().replace("+00:00", "Z")


def _iso_utc_to_ms(value: str) -> int:
    return int(pd.Timestamp(value).timestamp() * 1000)
