from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import evaluate_v6_h10d_post_pump_short_replacement as base_eval  # noqa: E402
from enhengclaw.quant_research.features import (  # noqa: E402
    _timestamp_zscore,
    _xs_alpha_ontology_v6_h10d_base_raw_score,
    xs_alpha_ontology_v6_h10d_score,
    xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v1_news_veto_adjudicated_score,
    xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v1_news_veto_mini_score,
    xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v1_score,
)
from enhengclaw.quant_research.hypothesis_batch import (  # noqa: E402
    _compute_hypothesis_candidate_spec_hash,
)


CONTRACT_VERSION = "quant_v6_h10d_post_pump_news_veto_ab.v1"
DEFAULT_AS_OF = base_eval.DEFAULT_AS_OF
DEFAULT_TARGET_HORIZON_BARS = base_eval.DEFAULT_TARGET_HORIZON_BARS
DEFAULT_NEWS_EFFECTIVE_MODE = "t1"
ORIGINAL_ARTIFACTS_ROOT = ROOT / "artifacts" / "quant_research"
DATASET_ROOT = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "datasets"
    / "2026-05-01-crypto-news-dataset"
)
MINI_LABELS_PATH = DATASET_ROOT / "llm_structured_scores.parquet"
ADJUDICATED_LABELS_PATH = DATASET_ROOT / "llm_structured_scores_adjudicated_priority_ge_8.parquet"
ONEOFF_RUNNER_PATH = ROOT / "scripts" / "quant_research" / "run_alpha_ontology_horizon_cycle_oneoff.py"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="A/B test mini vs adjudicated news veto on SP-K short replacement."
    )
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--target-horizon-bars", type=int, default=DEFAULT_TARGET_HORIZON_BARS)
    parser.add_argument(
        "--news-effective-mode",
        choices=("t1", "t0"),
        default=DEFAULT_NEWS_EFFECTIVE_MODE,
        help="t1 = conservative next-day effective time via research_effective_at_utc; t0 = exploratory same-day effective time via newsDatetime_utc/newsDatetime.",
    )
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument("--skip-cycle-run", action="store_true")
    return parser


def _features_artifact_dir(as_of: str) -> Path:
    path = ORIGINAL_ARTIFACTS_ROOT / "features" / f"{as_of}-cross-sectional-daily-1d-features-v1"
    if not path.exists():
        raise FileNotFoundError(f"feature artifact dir not found: {path}")
    return path


def _variant_specs() -> list[dict[str, Any]]:
    return [
        {
            "label": "baseline_v6_h10d",
            "candidate_id": base_eval.BASELINE_CANDIDATE_ID,
            "base_mechanism_id": "xs_alpha_ontology_v6_lsk3_g_v2",
            "model_family": "xs_alpha_ontology_v6_h10d",
            "manifest_path": base_eval.BASELINE_MANIFEST_PATH,
            "manifest_contract_tag": "alpha_ontology_v6_lsk3_g_v2_h10d",
            "required_feature_columns_append": [],
            "description": "Active alternative baseline: v6_h10d core-20 perp strategy.",
            "report_root": ORIGINAL_ARTIFACTS_ROOT,
        },
        {
            "label": "replace_mid_v1_no_news",
            "candidate_id": "xs_alpha_ontology_v6_spk_short_replace_mid_v1_h10d",
            "base_mechanism_id": "xs_alpha_ontology_v6_spk_short_replace_mid_v1",
            "model_family": "xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v1",
            "manifest_contract_tag": "alpha_ontology_v6_h10d_spk_short_replace_mid_v1",
            "required_feature_columns_append": ["post_pump_stall_core_score_3d"],
            "description": (
                "SP-K short replacement control without any news veto. Keep v6_h10d unchanged except "
                "for one marginal short-slot replacement from the bottom-6 pool."
            ),
            "report_root": ORIGINAL_ARTIFACTS_ROOT,
        },
        {
            "label": "replace_mid_v1_news_veto_mini",
            "candidate_id": "xs_alpha_ontology_v6_spk_short_replace_mid_v1_news_veto_mini_h10d",
            "base_mechanism_id": "xs_alpha_ontology_v6_spk_short_replace_mid_v1_news_veto_mini",
            "model_family": "xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v1_news_veto_mini",
            "manifest_contract_tag": "alpha_ontology_v6_h10d_spk_short_replace_mid_v1_news_veto_mini",
            "required_feature_columns_append": [
                "post_pump_stall_core_score_3d",
                "news_short_veto_mini_flag",
            ],
            "description": (
                "SP-K short replacement with mini-model news veto: a post-pump-stall candidate may not replace "
                "into the short book if research-effective news says the move is more durable than hype."
            ),
            "report_root": None,
            "news_veto_label": "mini",
        },
        {
            "label": "replace_mid_v1_news_veto_adjudicated",
            "candidate_id": "xs_alpha_ontology_v6_spk_short_replace_mid_v1_news_veto_adjudicated_h10d",
            "base_mechanism_id": "xs_alpha_ontology_v6_spk_short_replace_mid_v1_news_veto_adjudicated",
            "model_family": "xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v1_news_veto_adjudicated",
            "manifest_contract_tag": "alpha_ontology_v6_h10d_spk_short_replace_mid_v1_news_veto_adjudicated",
            "required_feature_columns_append": [
                "post_pump_stall_core_score_3d",
                "news_short_veto_adjudicated_flag",
            ],
            "description": (
                "SP-K short replacement with adjudicated news veto: same replacement rule, but use the "
                "strong-model-reviewed boundary labels where mini was most likely to over-veto."
            ),
            "report_root": None,
            "news_veto_label": "adjudicated",
        },
    ]


def _normalize_subjects(value: Any) -> list[str]:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return []
    if isinstance(value, np.ndarray):
        items = value.tolist()
    elif isinstance(value, (list, tuple, set)):
        items = list(value)
    elif isinstance(value, str):
        items = [part.strip() for part in value.split(",")]
    else:
        items = [str(value)]
    out: list[str] = []
    for item in items:
        token = str(item or "").strip().upper()
        if token and token not in {"NAN", "NONE", "NULL"}:
            out.append(token)
    return sorted(set(out))


def _parse_utc_date(value: Any) -> date | None:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    ts = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(ts):
        return None
    return ts.date()


def _bounded_decay_days(value: Any) -> int:
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return 1
    return max(1, min(int(number), 30))


def _build_news_veto_daily_flags(
    *,
    scored: pd.DataFrame,
    veto_column: str,
    horizon_column: str,
    effective_time_column: str,
    start_date: date,
    end_date: date,
    output_column: str,
) -> pd.DataFrame:
    required = {"currencies", effective_time_column, veto_column, horizon_column}
    missing = [column for column in required if column not in scored.columns]
    if missing:
        raise KeyError(f"news label frame missing required columns: {missing}")

    flagged = scored.loc[scored[veto_column].fillna(False).astype(bool)].copy()
    if flagged.empty:
        return pd.DataFrame(columns=["subject", "date_utc", output_column])

    rows: list[dict[str, Any]] = []
    for row in flagged.itertuples(index=False):
        subjects = _normalize_subjects(getattr(row, "currencies"))
        effective_date = _parse_utc_date(getattr(row, effective_time_column))
        if not subjects or effective_date is None:
            continue
        active_start = max(start_date, effective_date)
        active_end = min(
            end_date,
            effective_date + timedelta(days=_bounded_decay_days(getattr(row, horizon_column)) - 1),
        )
        if active_end < active_start:
            continue
        dates = pd.date_range(active_start.isoformat(), active_end.isoformat(), freq="D")
        for subject in subjects:
            for active_date in dates:
                rows.append(
                    {
                        "subject": subject,
                        "date_utc": active_date.date().isoformat(),
                        output_column: 1,
                    }
                )
    if not rows:
        return pd.DataFrame(columns=["subject", "date_utc", output_column])
    daily = pd.DataFrame(rows)
    daily = (
        daily.groupby(["subject", "date_utc"], as_index=False)[output_column]
        .max()
        .sort_values(["date_utc", "subject"])
        .reset_index(drop=True)
    )
    return daily


def _augment_feature_panel_with_news_veto(
    *,
    features_csv_path: Path,
    news_effective_mode: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    panel = pd.read_csv(features_csv_path, compression="gzip")
    if panel.empty:
        raise ValueError("feature panel is empty")
    start_date = pd.to_datetime(panel["date_utc"], utc=True).min().date()
    end_date = pd.to_datetime(panel["date_utc"], utc=True).max().date()

    mini = pd.read_parquet(MINI_LABELS_PATH)
    adjudicated = pd.read_parquet(ADJUDICATED_LABELS_PATH)
    if news_effective_mode == "t0":
        mini_effective_time_column = "newsDatetime_utc"
        adjudicated_effective_time_column = "newsDatetime_utc"
    elif news_effective_mode == "t1":
        mini_effective_time_column = "research_effective_at_utc"
        adjudicated_effective_time_column = "research_effective_at_utc"
    else:
        raise ValueError(f"unsupported news_effective_mode: {news_effective_mode}")

    mini_daily = _build_news_veto_daily_flags(
        scored=mini,
        veto_column="short_veto_flag",
        horizon_column="decay_horizon_days",
        effective_time_column=mini_effective_time_column,
        start_date=start_date,
        end_date=end_date,
        output_column="news_short_veto_mini_flag",
    )
    adjudicated_daily = _build_news_veto_daily_flags(
        scored=adjudicated,
        veto_column="final_short_veto_flag",
        horizon_column="final_decay_horizon_days",
        effective_time_column=adjudicated_effective_time_column,
        start_date=start_date,
        end_date=end_date,
        output_column="news_short_veto_adjudicated_flag",
    )

    augmented = panel.merge(mini_daily, on=["subject", "date_utc"], how="left")
    augmented = augmented.merge(adjudicated_daily, on=["subject", "date_utc"], how="left")
    for column in ["news_short_veto_mini_flag", "news_short_veto_adjudicated_flag"]:
        augmented[column] = pd.to_numeric(augmented[column], errors="coerce").fillna(0).astype("int8")
    adjudicated_flag = pd.to_numeric(
        augmented["news_short_veto_adjudicated_flag"],
        errors="coerce",
    ).fillna(0).astype("int8")
    augmented["news_short_veto_adjudicated_do_not_fill_multiplier"] = (
        1.0 - adjudicated_flag.astype("float64")
    ).clip(lower=0.0, upper=1.0)
    augmented["news_short_veto_adjudicated_reduced_exposure_multiplier"] = np.where(
        adjudicated_flag.to_numpy(dtype="int8") > 0,
        0.5,
        1.0,
    ).astype("float64")

    summary = {
        "news_effective_mode": news_effective_mode,
        "mini_effective_time_column": mini_effective_time_column,
        "adjudicated_effective_time_column": adjudicated_effective_time_column,
        "panel_row_count": int(len(augmented)),
        "panel_subject_count": int(augmented["subject"].astype(str).nunique()),
        "panel_date_count": int(augmented["date_utc"].astype(str).nunique()),
        "mini_daily_flag_rows": int(len(mini_daily)),
        "mini_flag_subject_count": int(mini_daily["subject"].astype(str).nunique()) if not mini_daily.empty else 0,
        "adjudicated_daily_flag_rows": int(len(adjudicated_daily)),
        "adjudicated_flag_subject_count": (
            int(adjudicated_daily["subject"].astype(str).nunique()) if not adjudicated_daily.empty else 0
        ),
        "mini_flag_panel_fraction": float(augmented["news_short_veto_mini_flag"].mean()),
        "adjudicated_flag_panel_fraction": float(augmented["news_short_veto_adjudicated_flag"].mean()),
        "mini_flag_active_timestamps": int(
            augmented.loc[augmented["news_short_veto_mini_flag"] > 0, "timestamp_ms"].nunique()
        ),
        "adjudicated_flag_active_timestamps": int(
            augmented.loc[augmented["news_short_veto_adjudicated_flag"] > 0, "timestamp_ms"].nunique()
        ),
    }
    return augmented, summary


def _prepare_augmented_feature_root(
    *,
    as_of: str,
    report_dir: Path,
    news_effective_mode: str,
) -> tuple[Path, Path, dict[str, Any]]:
    source_dir = _features_artifact_dir(as_of)
    feature_set_id = source_dir.name
    augmented_root = report_dir / ("nva_t0" if news_effective_mode == "t0" else "nva")
    target_dir = augmented_root / "features" / feature_set_id
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    if target_dir.exists():
        shutil.rmtree(target_dir)
    shutil.copytree(source_dir, target_dir)
    source_universe_dir = ORIGINAL_ARTIFACTS_ROOT / "universe" / as_of
    target_universe_dir = augmented_root / "universe" / as_of
    target_universe_dir.parent.mkdir(parents=True, exist_ok=True)
    if target_universe_dir.exists():
        shutil.rmtree(target_universe_dir)
    shutil.copytree(source_universe_dir, target_universe_dir)

    features_csv_path = target_dir / "features.csv.gz"
    feature_manifest_path = target_dir / "feature_manifest.json"
    augmented_panel, summary = _augment_feature_panel_with_news_veto(
        features_csv_path=features_csv_path,
        news_effective_mode=news_effective_mode,
    )
    augmented_panel.to_csv(features_csv_path, index=False, compression="gzip")

    manifest = json.loads(feature_manifest_path.read_text(encoding="utf-8"))
    for field in ("available_numeric_columns", "numeric_feature_columns"):
        columns = list(manifest.get(field) or [])
        for column in (
            "news_short_veto_mini_flag",
            "news_short_veto_adjudicated_flag",
            "news_short_veto_adjudicated_do_not_fill_multiplier",
            "news_short_veto_adjudicated_reduced_exposure_multiplier",
        ):
            if column not in columns:
                columns.append(column)
        manifest[field] = sorted(set(columns))
    feature_manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return augmented_root, features_csv_path, summary


def _validation_report_path(*, artifacts_root: Path, as_of: str, candidate_id: str) -> Path:
    return artifacts_root / "experiments" / f"{as_of}-{candidate_id}" / "validation_report.json"


def _fast_reject_report_path(*, artifacts_root: Path, as_of: str, candidate_id: str) -> Path:
    return artifacts_root / "hypothesis_batches" / as_of / "families" / candidate_id / "fast_reject_report.json"


def _run_candidate_cycle(
    *,
    as_of: str,
    target_horizon_bars: int,
    manifest_path: Path,
    artifacts_root: Path,
) -> None:
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = manifest_payload.get("entries") or []
    candidate_id = str((entries[0] if entries else {}).get("candidate_id") or "")
    if candidate_id:
        (artifacts_root / "hypothesis_batches" / as_of / "families" / candidate_id).mkdir(
            parents=True,
            exist_ok=True,
        )
        (artifacts_root / "experiments" / f"{as_of}-{candidate_id}").mkdir(
            parents=True,
            exist_ok=True,
        )
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
    subprocess.run(command, cwd=str(ROOT), check=True)


def _build_manifest_payload(*, baseline_manifest: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    payload = base_eval._build_candidate_manifest_payload(baseline_manifest=baseline_manifest, spec=spec)
    entry = payload["entries"][0]
    feature_groups = [str(item).strip() for item in list(entry.get("feature_groups") or []) if str(item).strip()]
    required_columns = [
        str(item).strip() for item in list(entry.get("required_feature_columns") or []) if str(item).strip()
    ]
    if any(column.startswith("news_short_veto_") for column in required_columns) and "events" not in set(feature_groups):
        feature_groups.append("events")
        entry["feature_groups"] = feature_groups
    thesis = entry.setdefault("thesis_profile", {})
    veto_label = str(spec.get("news_veto_label") or "")
    if veto_label:
        thesis["market_mechanism"] = (
            "Attach SP-K as a short-slot replacement rule to v6_h10d, then veto only the incoming "
            f"replacement candidate when the {veto_label} news label says the pump is more likely to be "
            "durable repricing than hype."
        )
        thesis["directional_claim"] = (
            "Compared with the no-news SP-K rule, the news-veto version should avoid shorting fewer "
            "durable repricing events, reduce adverse short squeezes, and improve or preserve walk-forward "
            "Sharpe on the active parent strategy."
        )
        thesis["factor_formula"] = (
            "baseline = v6_h10d_raw; longs unchanged; shorts start from baseline bottom-3. "
            "Allow one mid-liquidity post_pump_stall candidate from the bottom-6 pool to replace a weaker "
            f"current short only if its `{veto_label}` news-veto flag is not active on that date."
        )
    entry["thesis_profile"] = thesis
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


def _load_variant_metrics(*, as_of: str, candidate_id: str, artifacts_root: Path) -> tuple[dict[str, Any], dict[str, str]]:
    validation_path = _validation_report_path(
        artifacts_root=artifacts_root,
        as_of=as_of,
        candidate_id=candidate_id,
    )
    fast_reject_path = _fast_reject_report_path(
        artifacts_root=artifacts_root,
        as_of=as_of,
        candidate_id=candidate_id,
    )
    prefer_fast_reject = (
        fast_reject_path.exists()
        and (
            not validation_path.exists()
            or fast_reject_path.stat().st_mtime >= validation_path.stat().st_mtime
        )
    )
    if prefer_fast_reject:
        metrics = base_eval._extract_fast_reject_metrics(base_eval._load_json(fast_reject_path))
    elif validation_path.exists():
        metrics = base_eval._extract_validation_metrics(base_eval._load_json(validation_path))
    elif fast_reject_path.exists():
        metrics = base_eval._extract_fast_reject_metrics(base_eval._load_json(fast_reject_path))
    else:
        metrics = {"status": "missing_cycle_reports"}
    paths = {
        "validation_report": str(validation_path),
        "fast_reject_report": str(fast_reject_path),
    }
    return metrics, paths


def _news_veto_boundary_diff_summary(frame: pd.DataFrame) -> dict[str, Any]:
    filtered = frame.copy()
    if filtered.empty:
        return {"status": "empty"}
    mini_flag = pd.to_numeric(filtered.get("news_short_veto_mini_flag"), errors="coerce").fillna(0).astype(int)
    adjudicated_flag = (
        pd.to_numeric(filtered.get("news_short_veto_adjudicated_flag"), errors="coerce").fillna(0).astype(int)
    )
    filtered["mini_flag"] = mini_flag
    filtered["adjudicated_flag"] = adjudicated_flag
    filtered["flag_diff"] = mini_flag != adjudicated_flag
    filtered["raw_score"] = _xs_alpha_ontology_v6_h10d_base_raw_score(filtered).astype("float64")
    filtered["factor_z"] = _timestamp_zscore(
        pd.to_numeric(filtered.get("post_pump_stall_core_score_3d"), errors="coerce").fillna(0.0),
        filtered["timestamp_ms"],
    ).astype("float64")

    eligible_diff_rows = 0
    eligible_diff_timestamps = 0
    for _, group in filtered.groupby("timestamp_ms", sort=False):
        ordered = group.sort_values("raw_score", ascending=False).copy()
        baseline_shorts = ordered.tail(min(3, len(ordered))).copy()
        pool = ordered.tail(min(6, len(ordered))).copy()
        eligible = pool.loc[
            (~pool.index.isin(baseline_shorts.index))
            & pool["liquidity_bucket"].astype(str).eq("mid_liquidity")
            & (pool["factor_z"] <= 0.0)
        ].copy()
        diff_eligible = eligible.loc[eligible["flag_diff"]].copy()
        if diff_eligible.empty:
            continue
        eligible_diff_timestamps += 1
        eligible_diff_rows += int(len(diff_eligible))

    diff_rows = filtered.loc[filtered["flag_diff"]].copy()
    return {
        "status": "ok",
        "filtered_row_count": int(len(filtered)),
        "flag_diff_rows": int(len(diff_rows)),
        "flag_diff_subject_count": int(diff_rows["subject"].astype(str).nunique()) if not diff_rows.empty else 0,
        "flag_diff_timestamp_count": int(diff_rows["timestamp_ms"].nunique()) if not diff_rows.empty else 0,
        "eligible_pool_flag_diff_rows": int(eligible_diff_rows),
        "eligible_pool_flag_diff_timestamp_count": int(eligible_diff_timestamps),
    }


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    as_of = str(args.as_of)
    news_effective_mode = str(args.news_effective_mode)
    report_dir = ROOT / "artifacts" / "quant_research" / "factor_reports" / as_of
    report_dir.mkdir(parents=True, exist_ok=True)
    default_report_name = (
        "v6_h10d_post_pump_news_veto_ab_diagnostic_t0.json"
        if news_effective_mode == "t0"
        else "v6_h10d_post_pump_news_veto_ab_diagnostic.json"
    )
    output_path = args.output_path or (report_dir / default_report_name)
    manifest_dir = report_dir / "generated_manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)

    augmented_artifacts_root, augmented_features_csv, news_summary = _prepare_augmented_feature_root(
        as_of=as_of,
        report_dir=report_dir,
        news_effective_mode=news_effective_mode,
    )
    baseline_manifest = base_eval._load_json(base_eval.BASELINE_MANIFEST_PATH)
    specs = _variant_specs()

    variant_metrics: dict[str, dict[str, Any]] = {}
    report_paths: dict[str, dict[str, str]] = {}
    generated_manifests: dict[str, str] = {}

    for spec in specs:
        label = str(spec["label"])
        if label == "baseline_v6_h10d":
            manifest_path = Path(spec["manifest_path"])
        else:
            manifest_payload = _build_manifest_payload(baseline_manifest=baseline_manifest, spec=spec)
            manifest_path = manifest_dir / f"{spec['candidate_id']}.json"
            manifest_path.write_text(json.dumps(manifest_payload, indent=2, ensure_ascii=False), encoding="utf-8")
        generated_manifests[label] = str(manifest_path)

        artifacts_root = Path(spec["report_root"]) if spec.get("report_root") else augmented_artifacts_root
        report_paths[label] = {
            "artifacts_root": str(artifacts_root),
        }
        need_run = (
            label not in {"baseline_v6_h10d", "replace_mid_v1_no_news"}
            and not _validation_report_path(
                artifacts_root=artifacts_root,
                as_of=as_of,
                candidate_id=str(spec["candidate_id"]),
            ).exists()
            and not _fast_reject_report_path(
                artifacts_root=artifacts_root,
                as_of=as_of,
                candidate_id=str(spec["candidate_id"]),
            ).exists()
        )
        if not args.skip_cycle_run and need_run:
            _run_candidate_cycle(
                as_of=as_of,
                target_horizon_bars=args.target_horizon_bars,
                manifest_path=manifest_path,
                artifacts_root=artifacts_root,
            )
        metrics, paths = _load_variant_metrics(
            as_of=as_of,
            candidate_id=str(spec["candidate_id"]),
            artifacts_root=artifacts_root,
        )
        variant_metrics[label] = metrics
        report_paths[label].update(paths)

    baseline_metrics = variant_metrics.get("baseline_v6_h10d", {})
    no_news_metrics = variant_metrics.get("replace_mid_v1_no_news", {})
    comparisons_vs_baseline: dict[str, Any] = {}
    comparisons_vs_no_news: dict[str, Any] = {}
    for spec in specs:
        label = str(spec["label"])
        if label != "baseline_v6_h10d":
            comparisons_vs_baseline[label] = base_eval._compare_metric_dicts(
                baseline=baseline_metrics,
                candidate=variant_metrics.get(label, {}),
            )
        if label not in {"baseline_v6_h10d", "replace_mid_v1_no_news"}:
            comparisons_vs_no_news[label] = base_eval._compare_metric_dicts(
                baseline=no_news_metrics,
                candidate=variant_metrics.get(label, {}),
            )

    risk_frame = base_eval._build_risk_frame(
        augmented_features_csv,
        target_horizon_bars=args.target_horizon_bars,
    )
    scorer_map = {
        "baseline_v6_h10d": xs_alpha_ontology_v6_h10d_score,
        "replace_mid_v1_no_news": xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v1_score,
        "replace_mid_v1_news_veto_mini": xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v1_news_veto_mini_score,
        "replace_mid_v1_news_veto_adjudicated": (
            xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v1_news_veto_adjudicated_score
        ),
    }

    risk_diagnostics: dict[str, Any] = {}
    selection_vs_baseline: dict[str, Any] = {}
    selection_vs_no_news: dict[str, Any] = {}
    for label, scorer in scorer_map.items():
        risk_diagnostics[f"{label}_bottom3"] = base_eval._short_risk_diagnostic(
            frame=risk_frame,
            scorer=scorer,
            short_count=3,
            target_horizon_bars=args.target_horizon_bars,
        )
        if label != "baseline_v6_h10d":
            selection_vs_baseline[label] = base_eval._selection_change_diagnostic(
                frame=risk_frame,
                baseline_scorer=scorer_map["baseline_v6_h10d"],
                candidate_scorer=scorer,
                long_count=3,
                short_count=3,
                target_horizon_bars=args.target_horizon_bars,
            )
        if label not in {"baseline_v6_h10d", "replace_mid_v1_no_news"}:
            selection_vs_no_news[label] = base_eval._selection_change_diagnostic(
                frame=risk_frame,
                baseline_scorer=scorer_map["replace_mid_v1_no_news"],
                candidate_scorer=scorer,
                long_count=3,
                short_count=3,
                target_horizon_bars=args.target_horizon_bars,
            )
    boundary_diff_summary = _news_veto_boundary_diff_summary(risk_frame)

    payload = {
        "contract_version": CONTRACT_VERSION,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": as_of,
        "news_effective_mode": news_effective_mode,
        "target_horizon_bars": int(args.target_horizon_bars),
        "augmented_artifacts_root": str(augmented_artifacts_root),
        "augmented_features_artifact": str(augmented_features_csv),
        "baseline_manifest_path": str(base_eval.BASELINE_MANIFEST_PATH),
        "generated_manifests": generated_manifests,
        "cycle_report_paths": report_paths,
        "variant_metrics": variant_metrics,
        "comparisons_vs_baseline": comparisons_vs_baseline,
        "comparisons_vs_no_news": comparisons_vs_no_news,
        "selection_change_vs_baseline": selection_vs_baseline,
        "selection_change_vs_no_news": selection_vs_no_news,
        "short_cost_and_squeeze_risk": risk_diagnostics,
        "news_veto_panel_summary": news_summary,
        "news_veto_boundary_diff_summary": boundary_diff_summary,
    }
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(f"=== Wrote diagnostic to {output_path}")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
