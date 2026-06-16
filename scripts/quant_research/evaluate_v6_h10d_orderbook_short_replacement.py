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

import evaluate_v6_h10d_post_pump_short_replacement as base_eval  # noqa: E402
from scripts.quant_research.alpha_branch_reports import (  # noqa: E402
    compute_orderbook_inventory_event_study as mf01_stage0,
)
from enhengclaw.quant_research.features import (  # noqa: E402
    xs_alpha_ontology_v6_h10d_mf01_boundary_fragile_replace_v1_score,
    xs_alpha_ontology_v6_h10d_mf01_combo_replace_v1_score,
    xs_alpha_ontology_v6_h10d_mf01_pump_bid_fail_replace_v1_score,
    xs_alpha_ontology_v6_h10d_score,
    xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v1_score,
)
from enhengclaw.quant_research.hypothesis_batch import (  # noqa: E402
    _compute_hypothesis_candidate_spec_hash,
)


CONTRACT_VERSION = "quant_v6_h10d_orderbook_short_replacement_diagnostic.v1"
DEFAULT_AS_OF = base_eval.DEFAULT_AS_OF
DEFAULT_TARGET_HORIZON_BARS = base_eval.DEFAULT_TARGET_HORIZON_BARS

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate MF-01 orderbook / inventory-transfer short-boundary replacement rules on v6_h10d."
    )
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--target-horizon-bars", type=int, default=DEFAULT_TARGET_HORIZON_BARS)
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
            "signal_column": None,
        },
        {
            "label": "replace_mid_v1_no_news",
            "candidate_id": "xs_alpha_ontology_v6_spk_short_replace_mid_v1_h10d",
            "base_mechanism_id": "xs_alpha_ontology_v6_spk_short_replace_mid_v1",
            "model_family": "xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v1",
            "manifest_contract_tag": "alpha_ontology_v6_h10d_spk_short_replace_mid_v1",
            "required_feature_columns_append": ["post_pump_stall_core_score_3d"],
            "description": "Current winning SP-K short-boundary rule for context.",
            "signal_column": "post_pump_stall_core_score_3d",
        },
        {
            "label": "mf01_boundary_fragile_v1",
            "candidate_id": "xs_alpha_ontology_v6_mf01_boundary_fragile_replace_v1_h10d",
            "base_mechanism_id": "xs_alpha_ontology_v6_mf01_boundary_fragile_replace_v1",
            "model_family": "xs_alpha_ontology_v6_h10d_mf01_boundary_fragile_replace_v1",
            "manifest_contract_tag": "alpha_ontology_v6_h10d_mf01_boundary_fragile_replace_v1",
            "required_feature_columns_append": ["boundary_fragile_orderbook_score"],
            "description": (
                "MF-01 broad boundary-fragility rule: allow a nearby tail candidate to replace the weakest "
                "selected short when daily orderbook state shows weak bid replenishment or persistent ask pressure."
            ),
            "signal_column": "boundary_fragile_orderbook_score",
        },
        {
            "label": "mf01_pump_bid_fail_v1",
            "candidate_id": "xs_alpha_ontology_v6_mf01_pump_bid_fail_replace_v1_h10d",
            "base_mechanism_id": "xs_alpha_ontology_v6_mf01_pump_bid_fail_replace_v1",
            "model_family": "xs_alpha_ontology_v6_h10d_mf01_pump_bid_fail_replace_v1",
            "manifest_contract_tag": "alpha_ontology_v6_h10d_mf01_pump_bid_fail_replace_v1",
            "required_feature_columns_append": ["pump_bid_replenishment_failure_score"],
            "description": (
                "MF-01 sparse high-conviction rule: only replace into same-day pump names whose bid depth fails "
                "to replenish after the move."
            ),
            "signal_column": "pump_bid_replenishment_failure_score",
        },
        {
            "label": "mf01_combo_v1",
            "candidate_id": "xs_alpha_ontology_v6_mf01_combo_replace_v1_h10d",
            "base_mechanism_id": "xs_alpha_ontology_v6_mf01_combo_replace_v1",
            "model_family": "xs_alpha_ontology_v6_h10d_mf01_combo_replace_v1",
            "manifest_contract_tag": "alpha_ontology_v6_h10d_mf01_combo_replace_v1",
            "required_feature_columns_append": ["mf01_short_boundary_combo_score"],
            "description": (
                "MF-01 combo rule: broad boundary fragility plus the sparse pump-failure kicker in one "
                "short-boundary replacement score."
            ),
            "signal_column": "mf01_short_boundary_combo_score",
        },
    ]


def _augment_mf01_signals(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    coverage_ok = out["hourly_bar_count"].fillna(0).ge(mf01_stage0.MIN_HOURLY_BARS_PER_DAY)
    weak_bid_fragility = (
        (-0.50 - pd.to_numeric(out["ob_bid_depth_mean_z30"], errors="coerce")).clip(lower=0.0, upper=4.0)
        + (
            0.95 - pd.to_numeric(out["ob_bid_replenishment_ratio_1d"], errors="coerce")
        ).clip(lower=0.0, upper=0.50)
        / 0.10
    )
    ask_pressure_fragility = (
        (
            pd.to_numeric(out["ob_ask_heavy_share_24h"], errors="coerce") - 0.60
        ).clip(lower=0.0, upper=0.40)
        / 0.10
        + (
            -0.05 - pd.to_numeric(out["ob_imb_mean_24h"], errors="coerce")
        ).clip(lower=0.0, upper=0.30)
        / 0.10
    )
    boundary_flag = (
        coverage_ok
        & (
            (
                pd.to_numeric(out["ob_bid_depth_mean_z30"], errors="coerce").lt(-0.50)
                & pd.to_numeric(out["ob_bid_replenishment_ratio_1d"], errors="coerce").lt(0.95)
            )
            | (
                pd.to_numeric(out["ob_ask_heavy_share_24h"], errors="coerce").gt(0.60)
                & pd.to_numeric(out["ob_imb_mean_24h"], errors="coerce").lt(-0.05)
            )
        )
    )
    pump_core = (
        coverage_ok
        & pd.to_numeric(out["pump_return_sigma"], errors="coerce").gt(mf01_stage0.PUMP_SIGMA_THRESHOLD)
        & pd.to_numeric(out["abnormal_range_z_60"], errors="coerce").gt(mf01_stage0.PUMP_RANGE_Z_THRESHOLD)
        & pd.to_numeric(out["quote_volume_expansion"], errors="coerce").gt(mf01_stage0.PUMP_QV_EXPANSION_THRESHOLD)
    )
    pump_bid_fail = (
        pump_core
        & pd.to_numeric(out["ob_bid_depth_mean_z30"], errors="coerce").lt(-0.50)
        & pd.to_numeric(out["ob_bid_replenishment_ratio_1d"], errors="coerce").lt(0.95)
    )
    out["boundary_fragile_orderbook_flag"] = boundary_flag.astype("bool")
    out["pump_bid_replenishment_failure_flag"] = pump_bid_fail.astype("bool")
    out["boundary_fragile_orderbook_score"] = -(
        weak_bid_fragility.fillna(0.0) + ask_pressure_fragility.fillna(0.0)
    ).where(boundary_flag, 0.0)
    out["pump_bid_replenishment_failure_score"] = -(
        pd.to_numeric(out["pump_exhaustion_recency_score_5d"], errors="coerce").abs().fillna(0.0)
        * (1.0 + weak_bid_fragility.fillna(0.0))
    ).where(pump_bid_fail, 0.0)
    out["mf01_short_boundary_combo_score"] = (
        pd.to_numeric(out["boundary_fragile_orderbook_score"], errors="coerce").fillna(0.0)
        + 0.50 * pd.to_numeric(out["pump_bid_replenishment_failure_score"], errors="coerce").fillna(0.0)
    )
    return out


def _build_risk_frame(*, as_of: str, target_horizon_bars: int) -> tuple[pd.DataFrame, Path]:
    features_artifact = base_eval._features_artifact_path(as_of)
    panel = mf01_stage0._load_daily_panel(
        features_artifact,
        horizons=(target_horizon_bars,),
        min_listing_age_days=0,
    )
    risk_frame = mf01_stage0._build_risk_frame(panel, horizons=(target_horizon_bars,))
    orderbook_panel, _ = mf01_stage0._build_orderbook_state_panel(risk_frame["subject"].astype(str).unique())
    merged = risk_frame.merge(orderbook_panel, on=["subject", "timestamp_ms", "date_utc"], how="left")
    merged = mf01_stage0._attach_baseline_short_boundary(merged)
    merged = _augment_mf01_signals(merged)
    return merged, features_artifact


def _build_candidate_manifest_payload(
    *,
    baseline_manifest: dict[str, Any],
    spec: dict[str, Any],
) -> dict[str, Any]:
    payload = json.loads(json.dumps(baseline_manifest))
    payload["contract_version"] = (
        f"quant_cross_sectional_hypothesis_batch_manifest.{spec['manifest_contract_tag']}"
    )
    payload["lifecycle"] = "experimental"
    payload["experimental_marker_set_at"] = datetime.now().date().isoformat()
    payload["experimental_reason"] = spec["description"]
    lineage = payload.setdefault("lineage", {})
    lineage["predecessor_baseline"] = base_eval.BASELINE_MANIFEST_PATH.name
    lineage["method"] = (
        "MF-01 orderbook / inventory-transfer test on the active v6_h10d strategy. Keep the parent core-20 "
        "universe and long leg unchanged; only allow discrete short-slot replacement near the baseline cutoff "
        "when 1h orderbook state says a nearby tail candidate should be shorted instead."
    )
    lineage["sub_path"] = "MF-01"

    entry = payload["entries"][0]
    entry["candidate_id"] = spec["candidate_id"]
    entry["base_mechanism_id"] = spec["base_mechanism_id"]
    entry["model_family"] = spec["model_family"]
    required = list(entry.get("required_feature_columns") or [])
    for column in list(spec.get("required_feature_columns_append") or []):
        if column not in required:
            required.append(column)
    entry["required_feature_columns"] = required

    thesis = entry.setdefault("thesis_profile", {})
    thesis["thesis_id"] = spec["candidate_id"]
    thesis["thesis_family"] = f"hypothesis_{spec['candidate_id']}"
    thesis["market_mechanism"] = (
        "MF-01 treats orderbook state as a short-boundary selector, not a global factor. The parent strategy "
        "already finds the broad cross-sectional short book; the marginal question is whether a nearby tail "
        "candidate has weaker inventory transfer, thinner replenishment, or more persistent ask pressure than "
        "the weakest selected short."
    )
    thesis["directional_claim"] = (
        "If orderbook fragility is informative, swapping one weak baseline short for a more fragile nearby "
        "candidate should improve short-basket economics without damaging the walk-forward profile of the "
        "active parent."
    )
    thesis["factor_formula"] = (
        "baseline = v6_h10d_raw; longs unchanged; shorts start from baseline bottom-3. Look in the bottom-6 tail "
        "for candidates with strong MF-01 boundary signal, then let one such candidate replace the weakest "
        "currently-selected short."
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


def _short_risk_diagnostic(
    *,
    frame: pd.DataFrame,
    scorer,
    short_count: int,
    target_horizon_bars: int,
    signal_column: str | None,
) -> dict[str, Any]:
    filtered = frame.copy()
    if filtered.empty:
        return {"status": "empty"}
    filtered["score"] = scorer(filtered)
    rows: list[dict[str, float | str]] = []
    for _, group in filtered.groupby("timestamp_ms"):
        ordered = group.sort_values("score", ascending=True).head(min(short_count, len(group))).copy()
        for _, row in ordered.iterrows():
            signal_value = pd.to_numeric(row.get(signal_column), errors="coerce") if signal_column else np.nan
            rows.append(
                {
                    "liquidity_bucket": str(row.get("liquidity_bucket") or ""),
                    "funding_rate": float(pd.to_numeric(row.get("funding_rate"), errors="coerce"))
                    if pd.notna(pd.to_numeric(row.get("funding_rate"), errors="coerce"))
                    else np.nan,
                    "forward_1d_log_return": float(pd.to_numeric(row.get("forward_1d_log_return"), errors="coerce"))
                    if pd.notna(pd.to_numeric(row.get("forward_1d_log_return"), errors="coerce"))
                    else np.nan,
                    f"forward_{target_horizon_bars}d_log_return": float(
                        pd.to_numeric(row.get(f"forward_{target_horizon_bars}d_log_return"), errors="coerce")
                    )
                    if pd.notna(pd.to_numeric(row.get(f"forward_{target_horizon_bars}d_log_return"), errors="coerce"))
                    else np.nan,
                    "signal_value": float(signal_value) if pd.notna(signal_value) else np.nan,
                }
            )
    basket = pd.DataFrame(rows)
    if basket.empty:
        return {"status": "no_rows"}
    funding = pd.to_numeric(basket["funding_rate"], errors="coerce").dropna()
    next_1d = pd.to_numeric(basket["forward_1d_log_return"], errors="coerce").dropna()
    next_h = pd.to_numeric(
        basket[f"forward_{target_horizon_bars}d_log_return"],
        errors="coerce",
    ).dropna()
    signal = pd.to_numeric(basket["signal_value"], errors="coerce").dropna()
    bucket = basket["liquidity_bucket"].astype(str)
    return {
        "status": "ok",
        "n_short_rows": int(len(basket)),
        "shorts_receive_funding_fraction": float((funding > 0).mean()) if len(funding) else 0.0,
        "shorts_pay_funding_fraction": float((funding < 0).mean()) if len(funding) else 0.0,
        "mean_funding_rate": float(funding.mean()) if len(funding) else 0.0,
        "median_funding_rate": float(funding.median()) if len(funding) else 0.0,
        "next_1d_adverse_move_mean": float(next_1d.mean()) if len(next_1d) else 0.0,
        "next_1d_adverse_move_p90": float(next_1d.quantile(0.90)) if len(next_1d) else 0.0,
        "next_1d_squeeze_gt_5pct_fraction": float((next_1d > 0.05).mean()) if len(next_1d) else 0.0,
        "next_1d_squeeze_gt_10pct_fraction": float((next_1d > 0.10).mean()) if len(next_1d) else 0.0,
        f"next_{target_horizon_bars}d_mean": float(next_h.mean()) if len(next_h) else 0.0,
        f"next_{target_horizon_bars}d_negative_fraction": float((next_h < 0).mean()) if len(next_h) else 0.0,
        "mid_liquidity_short_fraction": float(bucket.eq("mid_liquidity").mean()) if len(bucket) else 0.0,
        "top_liquidity_short_fraction": float(bucket.eq("top_liquidity").mean()) if len(bucket) else 0.0,
        "signal_active_short_fraction": float((signal < 0).mean()) if len(signal) else 0.0,
        "mean_signal_value": float(signal.mean()) if len(signal) else 0.0,
    }


def _selection_change_diagnostic(
    *,
    frame: pd.DataFrame,
    baseline_scorer,
    candidate_scorer,
    long_count: int,
    short_count: int,
    target_horizon_bars: int,
    signal_column: str | None,
) -> dict[str, Any]:
    filtered = frame.copy()
    if filtered.empty:
        return {"status": "empty"}
    filtered["baseline_score"] = baseline_scorer(filtered)
    filtered["candidate_score"] = candidate_scorer(filtered)

    timestamps_with_changes = 0
    timestamps_with_long_changes = 0
    total_timestamps = 0
    total_replacements = 0
    overlap_accumulator: list[float] = []
    entered_rows: list[dict[str, Any]] = []
    exited_rows: list[dict[str, Any]] = []

    for _, group in filtered.groupby("timestamp_ms"):
        total_timestamps += 1
        baseline_ordered = group.sort_values("baseline_score", ascending=False).copy()
        candidate_ordered = group.sort_values("candidate_score", ascending=False).copy()
        baseline_longs = baseline_ordered.head(min(long_count, len(baseline_ordered))).copy()
        candidate_longs = candidate_ordered.head(min(long_count, len(candidate_ordered))).copy()
        baseline_shorts = baseline_ordered.tail(min(short_count, len(baseline_ordered))).copy()
        candidate_shorts = candidate_ordered.tail(min(short_count, len(candidate_ordered))).copy()

        baseline_long_subjects = set(baseline_longs["subject"].astype(str))
        candidate_long_subjects = set(candidate_longs["subject"].astype(str))
        baseline_short_subjects = set(baseline_shorts["subject"].astype(str))
        candidate_short_subjects = set(candidate_shorts["subject"].astype(str))

        overlap_accumulator.append(len(baseline_short_subjects & candidate_short_subjects) / float(max(short_count, 1)))
        if baseline_long_subjects != candidate_long_subjects:
            timestamps_with_long_changes += 1
        if baseline_short_subjects == candidate_short_subjects:
            continue

        timestamps_with_changes += 1
        entered = candidate_shorts.loc[~candidate_shorts["subject"].astype(str).isin(baseline_short_subjects)].copy()
        exited = baseline_shorts.loc[~baseline_shorts["subject"].astype(str).isin(candidate_short_subjects)].copy()
        total_replacements += int(len(entered))

        for _, row in entered.iterrows():
            signal_value = pd.to_numeric(row.get(signal_column), errors="coerce") if signal_column else np.nan
            entered_rows.append(
                {
                    "subject": str(row.get("subject") or ""),
                    "liquidity_bucket": str(row.get("liquidity_bucket") or ""),
                    "signal_value": float(signal_value) if pd.notna(signal_value) else np.nan,
                    "forward_1d_log_return": float(pd.to_numeric(row.get("forward_1d_log_return"), errors="coerce"))
                    if pd.notna(pd.to_numeric(row.get("forward_1d_log_return"), errors="coerce"))
                    else np.nan,
                    f"forward_{target_horizon_bars}d_log_return": float(
                        pd.to_numeric(row.get(f"forward_{target_horizon_bars}d_log_return"), errors="coerce")
                    )
                    if pd.notna(pd.to_numeric(row.get(f"forward_{target_horizon_bars}d_log_return"), errors="coerce"))
                    else np.nan,
                }
            )
        for _, row in exited.iterrows():
            signal_value = pd.to_numeric(row.get(signal_column), errors="coerce") if signal_column else np.nan
            exited_rows.append(
                {
                    "subject": str(row.get("subject") or ""),
                    "liquidity_bucket": str(row.get("liquidity_bucket") or ""),
                    "signal_value": float(signal_value) if pd.notna(signal_value) else np.nan,
                    "forward_1d_log_return": float(pd.to_numeric(row.get("forward_1d_log_return"), errors="coerce"))
                    if pd.notna(pd.to_numeric(row.get("forward_1d_log_return"), errors="coerce"))
                    else np.nan,
                    f"forward_{target_horizon_bars}d_log_return": float(
                        pd.to_numeric(row.get(f"forward_{target_horizon_bars}d_log_return"), errors="coerce")
                    )
                    if pd.notna(pd.to_numeric(row.get(f"forward_{target_horizon_bars}d_log_return"), errors="coerce"))
                    else np.nan,
                }
            )

    entered_df = pd.DataFrame(entered_rows)
    exited_df = pd.DataFrame(exited_rows)

    def _safe_mean(df: pd.DataFrame, column: str) -> float | None:
        if df.empty or column not in df.columns:
            return None
        series = pd.to_numeric(df[column], errors="coerce").dropna()
        if series.empty:
            return None
        return float(series.mean())

    def _safe_frac(df: pd.DataFrame, predicate) -> float | None:
        if df.empty:
            return None
        return float(predicate(df).mean())

    return {
        "status": "ok",
        "timestamp_count": int(total_timestamps),
        "timestamps_with_short_changes": int(timestamps_with_changes),
        "timestamps_with_short_changes_fraction": float(timestamps_with_changes / max(total_timestamps, 1)),
        "timestamps_with_long_changes": int(timestamps_with_long_changes),
        "timestamps_with_long_changes_fraction": float(timestamps_with_long_changes / max(total_timestamps, 1)),
        "total_replacements": int(total_replacements),
        "replacement_position_fraction": float(total_replacements / max(total_timestamps * short_count, 1)),
        "average_short_overlap_fraction": float(np.mean(overlap_accumulator)) if overlap_accumulator else 1.0,
        "entered_short_count": int(len(entered_df)),
        "exited_short_count": int(len(exited_df)),
        "entered_mid_liquidity_fraction": _safe_frac(
            entered_df,
            lambda df: df["liquidity_bucket"].astype(str).eq("mid_liquidity"),
        ),
        "exited_mid_liquidity_fraction": _safe_frac(
            exited_df,
            lambda df: df["liquidity_bucket"].astype(str).eq("mid_liquidity"),
        ),
        "entered_mean_signal_value": _safe_mean(entered_df, "signal_value"),
        "exited_mean_signal_value": _safe_mean(exited_df, "signal_value"),
        "entered_signal_active_fraction": _safe_frac(
            entered_df,
            lambda df: pd.to_numeric(df["signal_value"], errors="coerce").fillna(0.0) < 0.0,
        ),
        "exited_signal_active_fraction": _safe_frac(
            exited_df,
            lambda df: pd.to_numeric(df["signal_value"], errors="coerce").fillna(0.0) < 0.0,
        ),
        "entered_next_1d_mean": _safe_mean(entered_df, "forward_1d_log_return"),
        "exited_next_1d_mean": _safe_mean(exited_df, "forward_1d_log_return"),
        f"entered_next_{target_horizon_bars}d_mean": _safe_mean(
            entered_df,
            f"forward_{target_horizon_bars}d_log_return",
        ),
        f"exited_next_{target_horizon_bars}d_mean": _safe_mean(
            exited_df,
            f"forward_{target_horizon_bars}d_log_return",
        ),
        "entered_next_1d_squeeze_gt_5pct_fraction": _safe_frac(
            entered_df,
            lambda df: pd.to_numeric(df["forward_1d_log_return"], errors="coerce").fillna(0.0) > 0.05,
        ),
        "exited_next_1d_squeeze_gt_5pct_fraction": _safe_frac(
            exited_df,
            lambda df: pd.to_numeric(df["forward_1d_log_return"], errors="coerce").fillna(0.0) > 0.05,
        ),
    }


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    as_of = str(args.as_of)
    baseline_manifest = base_eval._load_json(base_eval.BASELINE_MANIFEST_PATH)
    report_dir = ROOT / "artifacts" / "quant_research" / "factor_reports" / as_of
    report_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_path or (report_dir / "v6_h10d_orderbook_short_replacement_diagnostic.json")
    manifest_dir = report_dir / "generated_manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)

    specs = _variant_specs()
    report_paths: dict[str, dict[str, str]] = {}
    variant_metrics: dict[str, dict[str, Any]] = {}
    generated_manifests: dict[str, str] = {}

    for spec in specs:
        label = str(spec["label"])
        if label == "baseline_v6_h10d":
            manifest_path = Path(spec["manifest_path"])
        else:
            manifest_payload = _build_candidate_manifest_payload(
                baseline_manifest=baseline_manifest,
                spec=spec,
            )
            manifest_path = manifest_dir / f"{spec['candidate_id']}.json"
            manifest_path.write_text(json.dumps(manifest_payload, indent=2, ensure_ascii=False), encoding="utf-8")
        generated_manifests[label] = str(manifest_path)

        validation_path = base_eval._validation_report_path(as_of=as_of, candidate_id=str(spec["candidate_id"]))
        fast_reject_path = base_eval._fast_reject_report_path(as_of=as_of, candidate_id=str(spec["candidate_id"]))
        report_paths[label] = {
            "validation_report": str(validation_path),
            "fast_reject_report": str(fast_reject_path),
        }
        need_run = (
            label not in {"baseline_v6_h10d", "replace_mid_v1_no_news"}
            and not validation_path.exists()
            and not fast_reject_path.exists()
        )
        if not args.skip_cycle_run and need_run:
            base_eval._run_candidate_cycle(
                as_of=as_of,
                target_horizon_bars=args.target_horizon_bars,
                manifest_path=manifest_path,
            )

        if validation_path.exists():
            variant_metrics[label] = base_eval._extract_validation_metrics(base_eval._load_json(validation_path))
        elif fast_reject_path.exists():
            variant_metrics[label] = base_eval._extract_fast_reject_metrics(base_eval._load_json(fast_reject_path))
        else:
            variant_metrics[label] = {
                "report_kind": "missing",
                "validation_status": "missing",
            }

    risk_frame, features_artifact = _build_risk_frame(
        as_of=as_of,
        target_horizon_bars=args.target_horizon_bars,
    )

    scorer_map = {
        "baseline_v6_h10d": xs_alpha_ontology_v6_h10d_score,
        "replace_mid_v1_no_news": xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v1_score,
        "mf01_boundary_fragile_v1": xs_alpha_ontology_v6_h10d_mf01_boundary_fragile_replace_v1_score,
        "mf01_pump_bid_fail_v1": xs_alpha_ontology_v6_h10d_mf01_pump_bid_fail_replace_v1_score,
        "mf01_combo_v1": xs_alpha_ontology_v6_h10d_mf01_combo_replace_v1_score,
    }
    signal_columns = {str(spec["label"]): spec.get("signal_column") for spec in specs}

    risk_diagnostics: dict[str, Any] = {}
    for label, scorer in scorer_map.items():
        risk_diagnostics[f"{label}_bottom3"] = _short_risk_diagnostic(
            frame=risk_frame,
            scorer=scorer,
            short_count=3,
            target_horizon_bars=args.target_horizon_bars,
            signal_column=signal_columns.get(label),
        )

    selection_diagnostics: dict[str, Any] = {}
    baseline_scorer = scorer_map["baseline_v6_h10d"]
    for label, scorer in scorer_map.items():
        if label == "baseline_v6_h10d":
            continue
        selection_diagnostics[label] = _selection_change_diagnostic(
            frame=risk_frame,
            baseline_scorer=baseline_scorer,
            candidate_scorer=scorer,
            long_count=3,
            short_count=3,
            target_horizon_bars=args.target_horizon_bars,
            signal_column=signal_columns.get(label),
        )

    metric_deltas_vs_baseline = {
        label: base_eval._compare_metric_dicts(
            baseline=variant_metrics["baseline_v6_h10d"],
            candidate=metrics,
        )
        for label, metrics in variant_metrics.items()
        if label != "baseline_v6_h10d"
    }
    metric_deltas_vs_replace_mid_v1 = {}
    if "replace_mid_v1_no_news" in variant_metrics:
        metric_deltas_vs_replace_mid_v1 = {
            label: base_eval._compare_metric_dicts(
                baseline=variant_metrics["replace_mid_v1_no_news"],
                candidate=metrics,
            )
            for label, metrics in variant_metrics.items()
            if label not in {"baseline_v6_h10d", "replace_mid_v1_no_news"}
        }

    report = {
        "contract_version": CONTRACT_VERSION,
        "as_of": as_of,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "baseline_candidate_id": base_eval.BASELINE_CANDIDATE_ID,
        "features_artifact": str(features_artifact),
        "variants": json.loads(json.dumps(specs, default=str)),
        "generated_manifests": generated_manifests,
        "report_paths": report_paths,
        "variant_metrics": variant_metrics,
        "metric_deltas_vs_baseline": metric_deltas_vs_baseline,
        "metric_deltas_vs_replace_mid_v1_no_news": metric_deltas_vs_replace_mid_v1,
        "risk_diagnostics": risk_diagnostics,
        "selection_diagnostics": selection_diagnostics,
    }
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Wrote {output_path}")
    for label in ("mf01_boundary_fragile_v1", "mf01_pump_bid_fail_v1", "mf01_combo_v1"):
        metrics = variant_metrics.get(label, {})
        delta = metric_deltas_vs_baseline.get(label, {})
        print(
            f"{label}: status={metrics.get('validation_status')} "
            f"walk={metrics.get('walk_forward_median_oos_sharpe')} "
            f"delta_vs_baseline={delta.get('walk_forward_median_delta')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
