from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
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

import evaluate_v6_h10d_post_pump_news_veto_ab as news_ab  # noqa: E402
import evaluate_v6_h10d_post_pump_short_replacement as base_eval  # noqa: E402
from enhengclaw.quant_research.features import (  # noqa: E402
    xs_alpha_ontology_v6_h10d_score,
    xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v1_score,
    xs_alpha_ontology_v6_h10d_spk_ss_veto_adjudicated_score,
)
from enhengclaw.quant_research.hypothesis_batch import (  # noqa: E402
    _compute_hypothesis_candidate_spec_hash,
)


CONTRACT_VERSION = "quant_v6_h10d_post_pump_selected_short_exposure_ab.v1"
DEFAULT_AS_OF = base_eval.DEFAULT_AS_OF
DEFAULT_TARGET_HORIZON_BARS = base_eval.DEFAULT_TARGET_HORIZON_BARS
DEFAULT_NEWS_EFFECTIVE_MODE = news_ab.DEFAULT_NEWS_EFFECTIVE_MODE


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "A/B test adjudicated selected-short news veto as do-not-fill or reduced-exposure "
            "on top of the active SP-K short-boundary winner."
        )
    )
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--target-horizon-bars", type=int, default=DEFAULT_TARGET_HORIZON_BARS)
    parser.add_argument(
        "--news-effective-mode",
        choices=("t1", "t0"),
        default=DEFAULT_NEWS_EFFECTIVE_MODE,
    )
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument("--skip-cycle-run", action="store_true")
    return parser


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
            "report_root": news_ab.ORIGINAL_ARTIFACTS_ROOT,
        },
        {
            "label": "replace_mid_v1_no_news",
            "candidate_id": "xs_alpha_ontology_v6_spk_short_replace_mid_v1_h10d",
            "base_mechanism_id": "xs_alpha_ontology_v6_spk_short_replace_mid_v1",
            "model_family": "xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v1",
            "manifest_contract_tag": "alpha_ontology_v6_h10d_spk_short_replace_mid_v1",
            "required_feature_columns_append": ["post_pump_stall_core_score_3d"],
            "description": "Winner SP-K short replacement without any selected-short news action.",
            "report_root": news_ab.ORIGINAL_ARTIFACTS_ROOT,
        },
        {
            "label": "ss_veto_adjudicated",
            "candidate_id": "xs_alpha_ontology_v6_spk_ss_veto_adjudicated_h10d",
            "base_mechanism_id": "xs_alpha_ontology_v6_spk_ss_veto_adjudicated",
            "model_family": "xs_alpha_ontology_v6_h10d_spk_ss_veto_adjudicated",
            "manifest_contract_tag": "alpha_ontology_v6_h10d_spk_ss_veto_adjudicated",
            "required_feature_columns_append": [
                "post_pump_stall_core_score_3d",
                "news_short_veto_adjudicated_flag",
            ],
            "description": "Reference selected-short forced-replacement shape using adjudicated veto labels.",
            "report_root": None,
        },
        {
            "label": "ss_do_not_fill_adjudicated",
            "candidate_id": "xs_alpha_ontology_v6_spk_ss_do_not_fill_adjudicated_h10d",
            "base_mechanism_id": "xs_alpha_ontology_v6_spk_ss_do_not_fill_adjudicated",
            "model_family": "xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v1",
            "manifest_contract_tag": "alpha_ontology_v6_h10d_spk_ss_do_not_fill_adjudicated",
            "required_feature_columns_append": [
                "post_pump_stall_core_score_3d",
                "news_short_veto_adjudicated_flag",
                "news_short_veto_adjudicated_do_not_fill_multiplier",
            ],
            "description": (
                "Keep the SP-K winner's selected shorts, but when adjudicated durable-news veto fires on an "
                "already-selected short, leave that slot unfilled instead of forcing a replacement."
            ),
            "profile_constraints_update": {
                "short_position_weight_multiplier_column": "news_short_veto_adjudicated_do_not_fill_multiplier",
            },
            "report_root": None,
            "exposure_mode": "do_not_fill",
        },
        {
            "label": "ss_reduced_exposure_adjudicated",
            "candidate_id": "xs_alpha_ontology_v6_spk_ss_reduced_exposure_adjudicated_h10d",
            "base_mechanism_id": "xs_alpha_ontology_v6_spk_ss_reduced_exposure_adjudicated",
            "model_family": "xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v1",
            "manifest_contract_tag": "alpha_ontology_v6_h10d_spk_ss_reduced_exposure_adjudicated",
            "required_feature_columns_append": [
                "post_pump_stall_core_score_3d",
                "news_short_veto_adjudicated_flag",
                "news_short_veto_adjudicated_reduced_exposure_multiplier",
            ],
            "description": (
                "Keep the SP-K winner's selected shorts, but cut short weight in half when adjudicated durable-news "
                "veto fires on an already-selected short."
            ),
            "profile_constraints_update": {
                "short_position_weight_multiplier_column": "news_short_veto_adjudicated_reduced_exposure_multiplier",
            },
            "report_root": None,
            "exposure_mode": "reduced_exposure",
        },
    ]


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
    if spec.get("profile_constraints_update"):
        constraints = dict(entry.get("profile_constraints") or {})
        constraints.update(dict(spec["profile_constraints_update"]))
        entry["profile_constraints"] = constraints
    exposure_mode = str(spec.get("exposure_mode") or "").strip()
    if exposure_mode:
        thesis = entry.setdefault("thesis_profile", {})
        thesis["market_mechanism"] = (
            "Keep the SP-K winner `replace_mid_v1_no_news` as the selection engine, but treat adjudicated "
            "durable-news flags on already-selected shorts as a sizing problem instead of a replacement problem."
        )
        thesis["directional_claim"] = (
            "If durable repricing risk mainly means 'do not press this short', then reducing or removing the "
            "flagged short slot should preserve the good boundary names while avoiding the poor forced-replacement "
            "economics seen in the selected-short veto test."
        )
        if exposure_mode == "do_not_fill":
            thesis["factor_formula"] = (
                "stage 1 = `replace_mid_v1_no_news`; stage 2 = if an already-selected short has "
                "`news_short_veto_adjudicated_flag = 1`, set its short position multiplier to `0.0` and do not backfill "
                "the slot."
            )
        else:
            thesis["factor_formula"] = (
                "stage 1 = `replace_mid_v1_no_news`; stage 2 = if an already-selected short has "
                "`news_short_veto_adjudicated_flag = 1`, set its short position multiplier to `0.5` and keep the name "
                "in the basket at reduced exposure."
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
        requires_derivatives_features=bool((entry.get("thesis_profile") or {}).get("requires_derivatives_features")),
        profile_constraints=dict(entry.get("profile_constraints") or {}),
        thesis_profile=dict(entry.get("thesis_profile") or {}),
    )
    return payload


def _weighted_short_risk_diagnostic(
    *,
    frame: pd.DataFrame,
    scorer,
    short_count: int,
    target_horizon_bars: int,
    short_multiplier_column: str | None = None,
) -> dict[str, Any]:
    filtered = frame.copy()
    if filtered.empty:
        return {"status": "empty"}
    filtered["score"] = scorer(filtered)
    rows: list[dict[str, Any]] = []
    timestamp_exposure: list[float] = []
    for _, group in filtered.groupby("timestamp_ms", sort=False):
        shorts = group.sort_values("score", ascending=True).head(min(short_count, len(group))).copy()
        if shorts.empty:
            continue
        if short_multiplier_column and short_multiplier_column in shorts.columns:
            multipliers = pd.to_numeric(shorts[short_multiplier_column], errors="coerce").fillna(1.0).clip(lower=0.0, upper=1.0)
        else:
            multipliers = pd.Series(1.0, index=shorts.index, dtype="float64")
        timestamp_exposure.append(float(multipliers.sum()) / float(max(short_count, 1)))
        for idx, row in shorts.iterrows():
            multiplier = float(pd.to_numeric(multipliers.loc[idx], errors="coerce"))
            next_1d = pd.to_numeric(row.get("forward_1d_log_return"), errors="coerce")
            next_h = pd.to_numeric(row.get(f"forward_{target_horizon_bars}d_log_return"), errors="coerce")
            funding = pd.to_numeric(row.get("funding_rate"), errors="coerce")
            rows.append(
                {
                    "subject": str(row.get("subject") or ""),
                    "liquidity_bucket": str(row.get("liquidity_bucket") or ""),
                    "short_weight_multiplier": multiplier,
                    "news_flag": int(pd.to_numeric(row.get("news_short_veto_adjudicated_flag"), errors="coerce") or 0),
                    "funding_rate": float(funding) if pd.notna(funding) else np.nan,
                    "forward_1d_log_return": float(next_1d) if pd.notna(next_1d) else np.nan,
                    f"forward_{target_horizon_bars}d_log_return": float(next_h) if pd.notna(next_h) else np.nan,
                    "post_pump_stall_core_score_3d": float(
                        pd.to_numeric(row.get("post_pump_stall_core_score_3d"), errors="coerce")
                    )
                    if pd.notna(pd.to_numeric(row.get("post_pump_stall_core_score_3d"), errors="coerce"))
                    else np.nan,
                }
            )
    basket = pd.DataFrame(rows)
    if basket.empty:
        return {"status": "no_rows"}
    weights = pd.to_numeric(basket["short_weight_multiplier"], errors="coerce").fillna(0.0).clip(lower=0.0)

    def _weighted_mean(series: pd.Series) -> float | None:
        values = pd.to_numeric(series, errors="coerce")
        mask = values.notna() & weights.gt(0.0)
        if not bool(mask.any()):
            return None
        return float(np.average(values.loc[mask], weights=weights.loc[mask]))

    def _weighted_fraction(predicate: pd.Series) -> float | None:
        mask = predicate.notna() & weights.gt(0.0)
        if not bool(mask.any()):
            return None
        return float(np.average(predicate.loc[mask].astype("float64"), weights=weights.loc[mask]))

    next_1d = pd.to_numeric(basket["forward_1d_log_return"], errors="coerce")
    next_h = pd.to_numeric(basket[f"forward_{target_horizon_bars}d_log_return"], errors="coerce")
    funding = pd.to_numeric(basket["funding_rate"], errors="coerce")
    bucket = basket["liquidity_bucket"].astype(str)
    factor = pd.to_numeric(basket["post_pump_stall_core_score_3d"], errors="coerce")
    return {
        "status": "ok",
        "n_selected_short_rows": int(len(basket)),
        "effective_short_notional_fraction": float(np.mean(timestamp_exposure)) if timestamp_exposure else 0.0,
        "muted_selected_short_fraction": float((weights < 1.0).mean()) if len(weights) else 0.0,
        "fully_removed_selected_short_fraction": float((weights <= 0.0).mean()) if len(weights) else 0.0,
        "selected_short_news_flag_fraction": float((basket["news_flag"] > 0).mean()) if len(basket) else 0.0,
        "shorts_receive_funding_fraction": _weighted_fraction((funding > 0).astype("float64")),
        "shorts_pay_funding_fraction": _weighted_fraction((funding < 0).astype("float64")),
        "mean_funding_rate": _weighted_mean(funding),
        "next_1d_adverse_move_mean": _weighted_mean(next_1d),
        "next_1d_squeeze_gt_5pct_fraction": _weighted_fraction((next_1d > 0.05).astype("float64")),
        "next_1d_squeeze_gt_10pct_fraction": _weighted_fraction((next_1d > 0.10).astype("float64")),
        f"next_{target_horizon_bars}d_mean": _weighted_mean(next_h),
        f"next_{target_horizon_bars}d_negative_fraction": _weighted_fraction((next_h < 0).astype("float64")),
        "mid_liquidity_short_fraction": _weighted_fraction(bucket.eq("mid_liquidity").astype("float64")),
        "top_liquidity_short_fraction": _weighted_fraction(bucket.eq("top_liquidity").astype("float64")),
        "overlay_active_short_fraction": _weighted_fraction((factor < 0).astype("float64")),
        "mean_post_pump_stall_core_score_3d": _weighted_mean(factor),
    }


def _short_exposure_change_diagnostic(
    *,
    frame: pd.DataFrame,
    baseline_scorer,
    candidate_scorer,
    short_count: int,
    target_horizon_bars: int,
    candidate_multiplier_column: str | None,
) -> dict[str, Any]:
    filtered = frame.copy()
    if filtered.empty:
        return {"status": "empty"}
    filtered["baseline_score"] = baseline_scorer(filtered)
    filtered["candidate_score"] = candidate_scorer(filtered)
    total_timestamps = 0
    exposure_change_timestamps = 0
    total_removed_short_slots = 0.0
    muted_rows: list[dict[str, Any]] = []
    changed_subjects_timestamps = 0
    for _, group in filtered.groupby("timestamp_ms", sort=False):
        total_timestamps += 1
        baseline_ordered = group.sort_values("baseline_score", ascending=False).copy()
        candidate_ordered = group.sort_values("candidate_score", ascending=False).copy()
        baseline_shorts = baseline_ordered.tail(min(short_count, len(baseline_ordered))).copy()
        candidate_shorts = candidate_ordered.tail(min(short_count, len(candidate_ordered))).copy()
        baseline_subjects = set(baseline_shorts["subject"].astype(str))
        candidate_subjects = set(candidate_shorts["subject"].astype(str))
        if baseline_subjects != candidate_subjects:
            changed_subjects_timestamps += 1
        if candidate_multiplier_column and candidate_multiplier_column in candidate_shorts.columns:
            multipliers = pd.to_numeric(
                candidate_shorts[candidate_multiplier_column],
                errors="coerce",
            ).fillna(1.0).clip(lower=0.0, upper=1.0)
        else:
            multipliers = pd.Series(1.0, index=candidate_shorts.index, dtype="float64")
        removed_slots = float((1.0 - multipliers).clip(lower=0.0, upper=1.0).sum())
        if removed_slots <= 0.0:
            continue
        exposure_change_timestamps += 1
        total_removed_short_slots += removed_slots
        for idx, row in candidate_shorts.iterrows():
            multiplier = float(pd.to_numeric(multipliers.loc[idx], errors="coerce"))
            if multiplier >= 1.0:
                continue
            next_h = pd.to_numeric(row.get(f"forward_{target_horizon_bars}d_log_return"), errors="coerce")
            next_1d = pd.to_numeric(row.get("forward_1d_log_return"), errors="coerce")
            muted_rows.append(
                {
                    "subject": str(row.get("subject") or ""),
                    "liquidity_bucket": str(row.get("liquidity_bucket") or ""),
                    "multiplier": multiplier,
                    "news_flag": int(pd.to_numeric(row.get("news_short_veto_adjudicated_flag"), errors="coerce") or 0),
                    f"forward_{target_horizon_bars}d_log_return": float(next_h) if pd.notna(next_h) else np.nan,
                    "forward_1d_log_return": float(next_1d) if pd.notna(next_1d) else np.nan,
                }
            )
    muted = pd.DataFrame(muted_rows)
    next_h = (
        pd.to_numeric(muted[f"forward_{target_horizon_bars}d_log_return"], errors="coerce").dropna()
        if not muted.empty
        else pd.Series(dtype="float64")
    )
    next_1d = (
        pd.to_numeric(muted["forward_1d_log_return"], errors="coerce").dropna()
        if not muted.empty
        else pd.Series(dtype="float64")
    )
    return {
        "status": "ok",
        "timestamp_count": int(total_timestamps),
        "timestamps_with_short_exposure_changes": int(exposure_change_timestamps),
        "timestamps_with_short_exposure_changes_fraction": float(exposure_change_timestamps / max(total_timestamps, 1)),
        "timestamps_with_subject_set_changes": int(changed_subjects_timestamps),
        "timestamps_with_subject_set_changes_fraction": float(changed_subjects_timestamps / max(total_timestamps, 1)),
        "removed_short_slot_equivalents": float(total_removed_short_slots),
        "mean_removed_short_slots_per_timestamp": float(total_removed_short_slots / max(total_timestamps, 1)),
        "muted_selected_short_rows": int(len(muted)),
        "muted_selected_short_subject_count": int(muted["subject"].astype(str).nunique()) if not muted.empty else 0,
        f"muted_selected_short_next_{target_horizon_bars}d_mean": float(next_h.mean()) if len(next_h) else None,
        "muted_selected_short_next_1d_mean": float(next_1d.mean()) if len(next_1d) else None,
        "muted_selected_short_next_1d_squeeze_gt_5pct_fraction": float((next_1d > 0.05).mean()) if len(next_1d) else None,
    }


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    as_of = str(args.as_of)
    news_effective_mode = str(args.news_effective_mode)
    report_dir = ROOT / "artifacts" / "quant_research" / "factor_reports" / as_of
    report_dir.mkdir(parents=True, exist_ok=True)
    default_report_name = (
        "v6_h10d_post_pump_selected_short_exposure_ab_diagnostic_t0.json"
        if news_effective_mode == "t0"
        else "v6_h10d_post_pump_selected_short_exposure_ab_diagnostic.json"
    )
    output_path = args.output_path or (report_dir / default_report_name)
    manifest_dir = report_dir / "generated_manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)

    augmented_artifacts_root, augmented_features_csv, news_summary = news_ab._prepare_augmented_feature_root(
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
        report_paths[label] = {"artifacts_root": str(artifacts_root)}
        need_run = (
            label not in {"baseline_v6_h10d", "replace_mid_v1_no_news"}
            and not news_ab._validation_report_path(
                artifacts_root=artifacts_root,
                as_of=as_of,
                candidate_id=str(spec["candidate_id"]),
            ).exists()
            and not news_ab._fast_reject_report_path(
                artifacts_root=artifacts_root,
                as_of=as_of,
                candidate_id=str(spec["candidate_id"]),
            ).exists()
        )
        if not args.skip_cycle_run and need_run:
            news_ab._run_candidate_cycle(
                as_of=as_of,
                target_horizon_bars=args.target_horizon_bars,
                manifest_path=manifest_path,
                artifacts_root=artifacts_root,
            )
        metrics, paths = news_ab._load_variant_metrics(
            as_of=as_of,
            candidate_id=str(spec["candidate_id"]),
            artifacts_root=artifacts_root,
        )
        variant_metrics[label] = metrics
        report_paths[label].update(paths)

    baseline_metrics = variant_metrics.get("baseline_v6_h10d", {})
    no_news_metrics = variant_metrics.get("replace_mid_v1_no_news", {})
    forced_replacement_metrics = variant_metrics.get("ss_veto_adjudicated", {})
    comparisons_vs_baseline: dict[str, Any] = {}
    comparisons_vs_no_news: dict[str, Any] = {}
    comparisons_vs_forced_replacement: dict[str, Any] = {}
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
        if label not in {"baseline_v6_h10d", "replace_mid_v1_no_news", "ss_veto_adjudicated"}:
            comparisons_vs_forced_replacement[label] = base_eval._compare_metric_dicts(
                baseline=forced_replacement_metrics,
                candidate=variant_metrics.get(label, {}),
            )

    risk_frame = base_eval._build_risk_frame(
        augmented_features_csv,
        target_horizon_bars=args.target_horizon_bars,
    )
    scorer_map = {
        "baseline_v6_h10d": xs_alpha_ontology_v6_h10d_score,
        "replace_mid_v1_no_news": xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v1_score,
        "ss_veto_adjudicated": xs_alpha_ontology_v6_h10d_spk_ss_veto_adjudicated_score,
        "ss_do_not_fill_adjudicated": xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v1_score,
        "ss_reduced_exposure_adjudicated": xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v1_score,
    }
    multiplier_column_map = {
        "baseline_v6_h10d": None,
        "replace_mid_v1_no_news": None,
        "ss_veto_adjudicated": None,
        "ss_do_not_fill_adjudicated": "news_short_veto_adjudicated_do_not_fill_multiplier",
        "ss_reduced_exposure_adjudicated": "news_short_veto_adjudicated_reduced_exposure_multiplier",
    }
    risk_diagnostics: dict[str, Any] = {}
    exposure_change_vs_no_news: dict[str, Any] = {}
    for label, scorer in scorer_map.items():
        risk_diagnostics[f"{label}_bottom3"] = _weighted_short_risk_diagnostic(
            frame=risk_frame,
            scorer=scorer,
            short_count=3,
            target_horizon_bars=args.target_horizon_bars,
            short_multiplier_column=multiplier_column_map.get(label),
        )
        if label not in {"baseline_v6_h10d", "replace_mid_v1_no_news", "ss_veto_adjudicated"}:
            exposure_change_vs_no_news[label] = _short_exposure_change_diagnostic(
                frame=risk_frame,
                baseline_scorer=scorer_map["replace_mid_v1_no_news"],
                candidate_scorer=scorer,
                short_count=3,
                target_horizon_bars=args.target_horizon_bars,
                candidate_multiplier_column=multiplier_column_map.get(label),
            )

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
        "comparisons_vs_forced_replacement": comparisons_vs_forced_replacement,
        "weighted_short_cost_and_squeeze_risk": risk_diagnostics,
        "short_exposure_change_vs_no_news": exposure_change_vs_no_news,
        "news_veto_panel_summary": news_summary,
    }
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(f"=== Wrote diagnostic to {output_path}")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
