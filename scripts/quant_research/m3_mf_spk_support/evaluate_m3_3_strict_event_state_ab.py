from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.quant_research import evaluate_v6_h10d_post_pump_short_replacement as base_eval  # noqa: E402
from scripts.quant_research.alpha_stage0_quarantine import (  # noqa: E402
    evaluate_m3_3_event_state_feature_stage0 as event_features,
    evaluate_m3_3_event_tape_spk_stage0 as event_tape,
)
from enhengclaw.quant_research.hypothesis_batch import _compute_hypothesis_candidate_spec_hash  # noqa: E402


CONTRACT_VERSION = "m3_3_strict_event_state_ab.v1"
DEFAULT_AS_OF = "2026-05-03"
ORIGINAL_ARTIFACTS_ROOT = ROOT / "artifacts" / "quant_research"
BASELINE_MANIFEST_PATH = (
    ROOT
    / "src"
    / "enhengclaw"
    / "quant_research"
    / "cross_sectional_hypothesis_batch_manifest_alpha_ontology_v5_rw_bridge_no_overlay_lsk3_g_v2_h10d.json"
)
BASELINE_CANDIDATE_ID = "xs_alpha_ontology_v5_rw_bridge_no_overlay_lsk3_g_v2_h10d"
CANDIDATE_ID = "xs_alpha_ontology_v5_rw_bridge_no_overlay_m3_3_strict_event_state_q1_noise0_h10d"
MODEL_FAMILY = "xs_alpha_ontology_v5_h10d_rw_bridge_m3_3_strict_event_state_q1_noise0"
ONEOFF_RUNNER_PATH = ROOT / "scripts" / "quant_research" / "run_alpha_ontology_horizon_cycle_oneoff.py"
EVENT_STATE_COLUMNS = [
    "m3_3_event_state_hype_pressure_v1",
    "m3_3_event_state_confirmed_quality_v1",
    "m3_3_event_state_short_quality_v1",
    "m3_3_event_state_noise_ratio_v1",
    "m3_3_strict_event_state_q1_noise0_flag",
]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Formal A/B scaffold for M3.3 strict event-state short-boundary replacement."
    )
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--target-horizon-bars", type=int, default=10)
    parser.add_argument("--event-lookback-days", type=int, default=10)
    parser.add_argument("--news-artifact", type=Path, default=event_tape.DEFAULT_NEWS_ARTIFACT)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--skip-cycle-run", action="store_true")
    parser.add_argument("--force-cycle-run", action="store_true")
    return parser


def _features_artifact_dir(as_of: str) -> Path:
    path = ORIGINAL_ARTIFACTS_ROOT / "features" / f"{as_of}-cross-sectional-daily-1d-features-v1"
    if not path.exists():
        raise FileNotFoundError(f"feature artifact dir not found: {path}")
    return path


def _feature_artifact_dirs(as_of: str) -> list[Path]:
    root = ORIGINAL_ARTIFACTS_ROOT / "features"
    dirs = [
        path
        for path in root.glob(f"{as_of}-cross-sectional-daily-1d*")
        if path.is_dir() and (path / "features.csv.gz").exists()
    ]
    if not dirs:
        return [_features_artifact_dir(as_of)]
    return sorted(dirs, key=lambda path: path.name)


def _augment_feature_panel(
    *,
    features_csv_path: Path,
    news_artifact: Path,
    event_lookback_days: int,
) -> dict[str, Any]:
    panel = pd.read_csv(features_csv_path, compression="gzip")
    stale_m3_3_columns = [
        column
        for column in panel.columns
        if column.startswith("m3_3_event_tape_")
        or column.startswith("m3_3_event_state_")
        or column.startswith("m3_3_strict_event_state_")
    ]
    if stale_m3_3_columns:
        panel = panel.drop(columns=stale_m3_3_columns)
    news = pd.read_parquet(news_artifact)
    tape = event_tape._explode_news_tape(news, lookback_days=event_lookback_days)
    augmented = event_tape._merge_event_tape(panel, tape)
    augmented = event_features._add_event_state_features(augmented)
    augmented["m3_3_strict_event_state_q1_noise0_flag"] = (
        pd.to_numeric(augmented["m3_3_event_state_short_quality_v1"], errors="coerce").fillna(0.0).ge(1.0)
        & pd.to_numeric(augmented["m3_3_event_state_noise_ratio_v1"], errors="coerce").fillna(0.0).le(0.0)
        & pd.to_numeric(augmented["m3_3_event_state_hype_pressure_v1"], errors="coerce").fillna(0.0).le(0.0)
    ).astype("int8")
    augmented.to_csv(features_csv_path, index=False, compression="gzip")
    return {
        "row_count": int(len(augmented)),
        "subject_count": int(augmented["subject"].astype(str).nunique()) if "subject" in augmented.columns else None,
        "date_min": str(augmented["date_utc"].min()) if "date_utc" in augmented.columns else None,
        "date_max": str(augmented["date_utc"].max()) if "date_utc" in augmented.columns else None,
        "strict_flag_row_fraction": float(augmented["m3_3_strict_event_state_q1_noise0_flag"].mean()),
        "strict_flag_subject_count": int(
            augmented.loc[augmented["m3_3_strict_event_state_q1_noise0_flag"].gt(0), "subject"].astype(str).nunique()
        )
        if "subject" in augmented.columns
        else None,
    }


def _prepare_augmented_feature_root(
    *,
    as_of: str,
    output_dir: Path,
    news_artifact: Path,
    event_lookback_days: int,
) -> tuple[Path, Path, dict[str, Any]]:
    augmented_root = ORIGINAL_ARTIFACTS_ROOT / f"m3_3_ab_root_{as_of}"
    target_features_root = augmented_root / "features"
    target_features_root.mkdir(parents=True, exist_ok=True)
    augmentation_summaries: dict[str, Any] = {}
    first_features_csv_path: Path | None = None
    for source_dir in _feature_artifact_dirs(as_of):
        target_dir = target_features_root / source_dir.name
        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.copytree(source_dir, target_dir)
    target_dirs = [
        path
        for path in target_features_root.glob(f"{as_of}-cross-sectional-daily-1d*")
        if path.is_dir() and (path / "features.csv.gz").exists() and (path / "feature_manifest.json").exists()
    ]
    for target_dir in sorted(target_dirs, key=lambda path: path.name):
        features_csv_path = target_dir / "features.csv.gz"
        feature_manifest_path = target_dir / "feature_manifest.json"
        augmentation_summaries[target_dir.name] = _augment_feature_panel(
            features_csv_path=features_csv_path,
            news_artifact=news_artifact,
            event_lookback_days=event_lookback_days,
        )
        if first_features_csv_path is None:
            first_features_csv_path = features_csv_path
        manifest = json.loads(feature_manifest_path.read_text(encoding="utf-8"))
        for field in ("available_numeric_columns", "numeric_feature_columns"):
            columns = list(manifest.get(field) or [])
            for column in EVENT_STATE_COLUMNS:
                if column not in columns:
                    columns.append(column)
            manifest[field] = sorted(set(columns))
        feature_manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    source_universe_dir = ORIGINAL_ARTIFACTS_ROOT / "universe" / as_of
    target_universe_dir = augmented_root / "universe" / as_of
    target_universe_dir.parent.mkdir(parents=True, exist_ok=True)
    if target_universe_dir.exists():
        shutil.rmtree(target_universe_dir)
    shutil.copytree(source_universe_dir, target_universe_dir)

    if first_features_csv_path is None:
        raise FileNotFoundError(f"no feature csv copied for {as_of}")
    return augmented_root, first_features_csv_path, {"feature_sets": augmentation_summaries}


def _build_candidate_manifest(*, baseline_manifest: dict[str, Any]) -> dict[str, Any]:
    payload = json.loads(json.dumps(baseline_manifest))
    payload["contract_version"] = "quant_cross_sectional_hypothesis_batch_manifest.m3_3_strict_event_state_q1_noise0_h10d"
    payload["lifecycle"] = "experimental"
    payload["experimental_marker_set_at"] = datetime.now().date().isoformat()
    payload["experimental_reason"] = (
        "M3.3 strict event-state A/B: preserve canonical v5_rw_bridge_no_overlay_h10d, "
        "then replace only short-boundary names when adjudicated event state is high-quality, no-hype, and zero-noise."
    )
    lineage = payload.setdefault("lineage", {})
    lineage["predecessor_baseline"] = BASELINE_MANIFEST_PATH.name
    lineage["sub_path"] = "M3.3_event_tape"
    lineage["method"] = (
        "Event-state short-boundary replacement on canonical v5_rw_bridge_no_overlay_h10d. "
        "No SP-K dependence; event tape is converted into PIT-safe daily state columns."
    )

    entry = payload["entries"][0]
    entry["candidate_id"] = CANDIDATE_ID
    entry["base_mechanism_id"] = "xs_alpha_ontology_v5_rw_bridge_no_overlay_m3_3_strict_event_state_q1_noise0"
    entry["model_family"] = MODEL_FAMILY
    entry["include_required_feature_columns_in_selection"] = True
    feature_groups = list(entry.get("feature_groups") or [])
    if "events" not in feature_groups:
        feature_groups.append("events")
    entry["feature_groups"] = feature_groups
    required = list(entry.get("required_feature_columns") or [])
    for column in EVENT_STATE_COLUMNS:
        if column not in required:
            required.append(column)
    entry["required_feature_columns"] = required
    thesis = entry.setdefault("thesis_profile", {})
    thesis["thesis_id"] = CANDIDATE_ID
    thesis["thesis_family"] = f"hypothesis_{CANDIDATE_ID}"
    thesis["market_mechanism"] = (
        "Confirmed or real repricing events are not short candidates by themselves. "
        "They become useful only after filtering out hype/noise: if the event tape says a boundary name has durable "
        "short-quality evidence without chatter contamination, it can replace a weaker current short."
    )
    thesis["directional_claim"] = (
        "Compared with the canonical parent, the strict event-state rule should improve short-leg realized returns "
        "without changing the long book or broad score surface."
    )
    thesis["factor_formula"] = (
        "parent = train-only v5_rw_bridge_no_overlay_h10d raw score; shorts start from parent bottom-3. "
        "Within parent bottom-8, eligible = short_quality_v1 >= 1.0 and noise_ratio_v1 <= 0 and hype_pressure_v1 <= 0. "
        "Eligible names are ordered by short_quality desc then parent score asc and may replace current shorts."
    )
    thesis["required_feature_columns"] = required
    entry["spec_hash"] = _compute_hypothesis_candidate_spec_hash(
        candidate_id=str(entry["candidate_id"]),
        base_mechanism_id=str(entry["base_mechanism_id"]),
        horizon_id=str(entry["horizon_id"]),
        target_horizon_bars=int(entry["target_horizon_bars"]),
        label_contract_id=str(entry.get("label_contract_id") or ""),
        shape=str(entry["shape"]),
        dataset_profile=str(entry["dataset_profile"]),
        strategy_profile=str(entry["strategy_profile"]),
        universe_filter=dict(entry.get("universe_filter") or {}),
        model_family=str(entry["model_family"]),
        feature_groups=list(entry.get("feature_groups") or []),
        required_feature_columns=list(entry.get("required_feature_columns") or []),
        requires_derivatives_features=bool(thesis.get("requires_derivatives_features")),
        profile_constraints=dict(entry.get("profile_constraints") or {}),
        thesis_profile=dict(thesis),
    )
    return payload


def _run_candidate_cycle(
    *,
    as_of: str,
    target_horizon_bars: int,
    manifest_path: Path,
    artifacts_root: Path,
    news_artifact: Path,
    event_lookback_days: int,
) -> None:
    command = [
        sys.executable,
        str(ONEOFF_RUNNER_PATH),
        "--as-of",
        as_of,
        "--manifest",
        str(manifest_path),
        "--target-horizon-bars",
        str(target_horizon_bars),
        "--artifacts-root",
        str(artifacts_root),
    ]
    env = {
        **dict(os.environ),
        "ENHENGCLAW_M3_3_EVENT_STATE_NEWS_ARTIFACT": str(news_artifact),
        "ENHENGCLAW_M3_3_EVENT_LOOKBACK_DAYS": str(int(event_lookback_days)),
    }
    subprocess.run(command, cwd=str(ROOT), check=True, env=env)


def _validation_report_path(*, artifacts_root: Path, as_of: str, candidate_id: str) -> Path:
    return artifacts_root / "experiments" / f"{as_of}-{candidate_id}" / "validation_report.json"


def _fast_reject_report_path(*, artifacts_root: Path, as_of: str, candidate_id: str) -> Path:
    return artifacts_root / "hypothesis_batches" / as_of / "families" / candidate_id / "fast_reject_report.json"


def _strict_candidate_list_path(*, artifacts_root: Path, as_of: str) -> Path:
    return artifacts_root / "hypothesis_batches" / as_of / "strict_candidate_list.json"


def _resolve_report_path(path_text: str | None) -> Path | None:
    if not path_text:
        return None
    path = Path(path_text)
    if path.is_absolute():
        return path
    return ROOT / path


def _load_strict_status(*, artifacts_root: Path, as_of: str, candidate_id: str) -> dict[str, Any]:
    strict_list_path = _strict_candidate_list_path(artifacts_root=artifacts_root, as_of=as_of)
    payload: dict[str, Any] = {
        "strict_candidate_list_path": str(strict_list_path),
        "strict_candidate_list_found": strict_list_path.exists(),
    }
    if not strict_list_path.exists():
        return payload

    strict_list = base_eval._load_json(strict_list_path)
    payload["strict_candidate_count"] = strict_list.get("strict_candidate_count")
    payload["strict_survivor_count"] = strict_list.get("strict_survivor_count")
    candidates = list(strict_list.get("strict_candidates") or [])
    candidate = next((item for item in candidates if item.get("candidate_id") == candidate_id), None)
    payload["candidate_found"] = candidate is not None
    if candidate is None:
        return payload

    for key in (
        "strict_validation_passed",
        "validation_contract_status",
        "credible_research_evidence",
        "falsification_status",
        "statistical_falsification_status",
    ):
        payload[key] = candidate.get(key)

    validation_path = _resolve_report_path(candidate.get("validation_report_path"))
    strict_result_path = _resolve_report_path(candidate.get("strict_result_path"))
    fast_reject_path = _resolve_report_path(candidate.get("fast_reject_report_path"))
    payload["validation_report_path"] = str(validation_path) if validation_path is not None else None
    payload["strict_result_path"] = str(strict_result_path) if strict_result_path is not None else None
    payload["fast_reject_report_path"] = str(fast_reject_path) if fast_reject_path is not None else None

    if strict_result_path is not None and strict_result_path.exists():
        strict_result = base_eval._load_json(strict_result_path)
        payload["experiment_status"] = strict_result.get("experiment_status")
        payload["strict_result_found"] = True
    else:
        payload["strict_result_found"] = False
    return payload


def _load_variant_metrics(*, artifacts_root: Path, as_of: str, candidate_id: str) -> tuple[dict[str, Any], dict[str, str]]:
    strict_status = _load_strict_status(artifacts_root=artifacts_root, as_of=as_of, candidate_id=candidate_id)
    validation_path = _resolve_report_path(strict_status.get("validation_report_path")) or _validation_report_path(
        artifacts_root=artifacts_root,
        as_of=as_of,
        candidate_id=candidate_id,
    )
    fast_reject_path = _fast_reject_report_path(artifacts_root=artifacts_root, as_of=as_of, candidate_id=candidate_id)
    paths = {"validation_report": str(validation_path), "fast_reject_report": str(fast_reject_path)}
    if validation_path.exists():
        metrics = base_eval._extract_validation_metrics(base_eval._load_json(validation_path))
        if metrics.get("report_kind") == "validation" and strict_status.get("validation_contract_status"):
            metrics["strict_validation_passed"] = strict_status.get("strict_validation_passed")
            metrics["validation_contract_status"] = strict_status.get("validation_contract_status")
            metrics["credible_research_evidence"] = strict_status.get("credible_research_evidence")
            metrics["experiment_status"] = strict_status.get("experiment_status")
        if fast_reject_path.exists():
            fast_metrics = base_eval._extract_fast_reject_metrics(base_eval._load_json(fast_reject_path))
            metrics["fast_reject_passed"] = fast_metrics.get("fast_reject_passed")
            metrics["fast_reject_rank_ic_mean"] = fast_metrics.get("rank_ic_mean")
            metrics["fast_reject_validation_sharpe"] = fast_metrics.get("validation_sharpe")
            metrics["fast_reject_test_sharpe"] = fast_metrics.get("test_sharpe")
            metrics["fast_reject_walk_forward_median_oos_sharpe"] = fast_metrics.get(
                "walk_forward_median_oos_sharpe"
            )
        return metrics, paths
    if fast_reject_path.exists():
        return base_eval._extract_fast_reject_metrics(base_eval._load_json(fast_reject_path)), paths
    return {"report_kind": "missing"}, paths


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    as_of = str(args.as_of)
    output_dir = args.output_dir or (
        ROOT / "artifacts" / "quant_research" / "factor_reports" / f"{as_of}-m3-3-strict-event-state-ab"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_dir = output_dir / "generated_manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)

    augmented_root, augmented_features_csv, augmentation_summary = _prepare_augmented_feature_root(
        as_of=as_of,
        output_dir=output_dir,
        news_artifact=Path(args.news_artifact),
        event_lookback_days=int(args.event_lookback_days),
    )
    baseline_manifest = base_eval._load_json(BASELINE_MANIFEST_PATH)
    candidate_manifest = _build_candidate_manifest(baseline_manifest=baseline_manifest)
    candidate_manifest_path = manifest_dir / f"{CANDIDATE_ID}.json"
    candidate_manifest_path.write_text(json.dumps(candidate_manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    need_run = args.force_cycle_run or (
        not _validation_report_path(artifacts_root=augmented_root, as_of=as_of, candidate_id=CANDIDATE_ID).exists()
        and not _fast_reject_report_path(artifacts_root=augmented_root, as_of=as_of, candidate_id=CANDIDATE_ID).exists()
    )
    if not args.skip_cycle_run and need_run:
        _run_candidate_cycle(
            as_of=as_of,
            target_horizon_bars=int(args.target_horizon_bars),
            manifest_path=candidate_manifest_path,
            artifacts_root=augmented_root,
            news_artifact=Path(args.news_artifact),
            event_lookback_days=int(args.event_lookback_days),
        )

    baseline_metrics, baseline_paths = _load_variant_metrics(
        artifacts_root=ORIGINAL_ARTIFACTS_ROOT,
        as_of=as_of,
        candidate_id=BASELINE_CANDIDATE_ID,
    )
    candidate_metrics, candidate_paths = _load_variant_metrics(
        artifacts_root=augmented_root,
        as_of=as_of,
        candidate_id=CANDIDATE_ID,
    )
    comparison = base_eval._compare_metric_dicts(baseline=baseline_metrics, candidate=candidate_metrics)
    payload = {
        "contract_version": CONTRACT_VERSION,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": as_of,
        "target_horizon_bars": int(args.target_horizon_bars),
        "event_lookback_days": int(args.event_lookback_days),
        "news_artifact": str(args.news_artifact),
        "baseline_manifest_path": str(BASELINE_MANIFEST_PATH),
        "candidate_manifest_path": str(candidate_manifest_path),
        "augmented_artifacts_root": str(augmented_root),
        "augmented_features_csv": str(augmented_features_csv),
        "augmentation_summary": augmentation_summary,
        "variant_metrics": {
            "baseline_v5_rw_bridge_no_overlay_h10d": baseline_metrics,
            "m3_3_strict_event_state_q1_noise0": candidate_metrics,
        },
        "comparison_vs_baseline": comparison,
        "cycle_report_paths": {
            "baseline_v5_rw_bridge_no_overlay_h10d": baseline_paths,
            "m3_3_strict_event_state_q1_noise0": candidate_paths,
        },
        "decision_scope": "quarantined_ab_scaffold_only",
    }
    output_path = output_dir / "m3_3_strict_event_state_ab.json"
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(f"=== Wrote M3.3 strict event-state A/B report to {output_path}")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
