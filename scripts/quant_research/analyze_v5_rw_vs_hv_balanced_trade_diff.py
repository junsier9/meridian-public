from __future__ import annotations

import json
import math
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from enhengclaw.quant_research import lab as qlab  # noqa: E402
from enhengclaw.quant_research.derivatives_quality import (  # noqa: E402
    DERIVATIVES_FEATURE_SPECS,
    feature_ready_flag_column as derivatives_feature_ready_flag_column,
    feature_source_flag_column as derivatives_feature_source_flag_column,
    summarize_feature_derivatives_quality,
)
from enhengclaw.quant_research.execution_backtest import (  # noqa: E402
    _cross_sectional_target_weights,
    _funding_cost_return,
    _next_fill_offset,
    _price_path_return,
    _scale_cross_sectional_turnover,
    filter_cross_sectional_execution_frame,
)
from enhengclaw.quant_research.feature_quality import (  # noqa: E402
    build_feature_quality_frame,
    summarize_feature_quality,
)
from enhengclaw.quant_research.fixed_set_comparison import performance_summary  # noqa: E402
from enhengclaw.quant_research.split_realization_contract import (  # noqa: E402
    realization_step_bars as split_contract_realization_step_bars,
)


OUT = ROOT / "artifacts" / "quant_research" / "h10d_v5_rw_vs_hv_balanced_20260518"
DOC = ROOT / "docs" / "quant_research" / "03_alpha_branches" / "v5_rw_vs_hv_balanced_trade_diff_2026_05_18.md"
PERIODS_PER_YEAR_H10D = 36
MATCH_TOLERANCE_MS = 5 * 86_400_000


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _iso_ms(ms: int) -> str:
    return pd.to_datetime(int(ms), unit="ms", utc=True).isoformat().replace("+00:00", "Z")


def _utc_date(ms: int) -> str:
    return pd.to_datetime(int(ms), unit="ms", utc=True).strftime("%Y-%m-%d")


def _perf(returns: pd.Series) -> dict[str, float]:
    return performance_summary(
        pd.to_numeric(returns, errors="coerce").fillna(0.0),
        periods_per_year=PERIODS_PER_YEAR_H10D,
    )


def _build_derivatives_quality_frame(frame: pd.DataFrame) -> pd.DataFrame:
    base_columns = [
        column
        for column in ("subject", "timestamp_ms", "liquidity_bucket", "usdm_symbol")
        if column in frame.columns
    ]
    quality = frame[base_columns].copy()
    for feature_name, spec in DERIVATIVES_FEATURE_SPECS.items():
        source_field = str(spec["source_field"])
        source_values = pd.to_numeric(
            frame.get(source_field, pd.Series(index=frame.index, dtype="float64")),
            errors="coerce",
        )
        if source_field == "open_interest":
            source_values = source_values.replace(0, pd.NA)
        feature_values = pd.to_numeric(
            frame.get(feature_name, pd.Series(index=frame.index, dtype="float64")),
            errors="coerce",
        )
        quality[derivatives_feature_source_flag_column(feature_name)] = source_values.notna().astype("bool")
        quality[derivatives_feature_ready_flag_column(feature_name)] = feature_values.notna().astype("bool")
    return quality


def _load_v5_context() -> dict:
    registry = _read_json(ROOT / "config" / "quant_research" / "active_h10d_registry.json")
    alpha_path = ROOT / registry["canonical_parent"]["alpha_card_path"]
    alpha = _read_json(alpha_path)
    experiment_root = alpha_path.parent
    spec = _read_json(experiment_root / "experiment_spec.json")
    feature_manifest_path = ROOT / str(alpha["feature_manifest_path"])
    feature_manifest = _read_json(feature_manifest_path)
    return {
        "registry": registry,
        "alpha_path": alpha_path,
        "alpha": alpha,
        "experiment_root": experiment_root,
        "spec": spec,
        "feature_manifest_path": feature_manifest_path,
        "feature_manifest": feature_manifest,
        "features_path": feature_manifest_path.parent / "features.csv.gz",
        "fixed_returns_path": experiment_root / "fixed_set_aligned_period_returns.csv",
    }


def _load_v5_fixed_set_frame(context: dict) -> tuple[pd.DataFrame, dict, dict]:
    spec = dict(context["spec"])
    feature_manifest = dict(context["feature_manifest"])
    features_path = Path(context["features_path"])
    feature_manifest_path = Path(context["feature_manifest_path"])
    alpha = dict(context["alpha"])

    frame = pd.read_csv(features_path, compression="gzip")
    derivatives_quality_frame = _build_derivatives_quality_frame(frame)
    derivatives_feature_quality = summarize_feature_derivatives_quality(
        quality_frame=derivatives_quality_frame,
        interval="1d",
    )
    numeric_feature_columns = list(feature_manifest.get("numeric_feature_columns") or [])
    feature_quality_frame = build_feature_quality_frame(
        feature_frame=frame,
        tracked_feature_columns=numeric_feature_columns,
        derivatives_quality_frame=derivatives_quality_frame,
    )
    summarize_feature_quality(
        feature_quality_frame=feature_quality_frame,
        tracked_feature_columns=numeric_feature_columns,
    )

    constraints = qlab._fixed_set_constraints(
        experiment_spec=spec,
        overlay_context={
            "features_path": str(features_path),
            "feature_manifest_path": str(feature_manifest_path),
            "universe_snapshot_path": str(ROOT / str(alpha.get("universe_snapshot_path") or "")),
        },
        profile_constraints_override={},
    )
    filtered = qlab._apply_universe_filter(frame, universe_filter=dict(spec.get("universe_filter") or {}))
    filtered = filter_cross_sectional_execution_frame(frame=filtered, constraints=constraints)
    resolved_contract = qlab.resolve_split_realization_contract(
        contract=dict(spec.get("split_realization_contract") or {}),
        shape=str(spec.get("shape") or "cross_sectional"),
        bar_interval_ms=qlab.infer_interval_ms(filtered["timestamp_ms"]) if not filtered.empty else None,
    )
    split = qlab._chronological_split(
        filtered,
        time_col="timestamp_ms",
        split_realization_contract=resolved_contract,
    )
    if split is None:
        raise RuntimeError("v5 fixed-set frame could not be split")
    strategy_entry = qlab._fixed_set_strategy_entry_for_comparison(spec)
    filtered, _filtered_quality, filtered_split, _derivatives_strategy_quality = (
        qlab._filter_cross_sectional_subject_panel_for_derivatives_readiness(
            frame=filtered,
            derivatives_quality_frame=derivatives_quality_frame,
            feature_columns=list(spec.get("feature_columns") or []),
            derivatives_feature_quality=derivatives_feature_quality,
            strategy_entry=strategy_entry,
            split=split,
            split_realization_contract=resolved_contract,
            data_readiness_contract=qlab.load_data_readiness_contract(),
        )
    )
    if filtered_split is None:
        raise RuntimeError("v5 readiness filter removed the split")
    return filtered, constraints, resolved_contract


def _period_frame_from_walk_forward(walk_forward: dict) -> pd.DataFrame:
    rows: list[dict] = []
    for window_index, window in enumerate(list(walk_forward.get("windows") or [])):
        for period in list(window.get("periods") or []):
            row = dict(period)
            row["window_index"] = int(window_index)
            row["timestamp_utc"] = _iso_ms(int(row["timestamp_ms"]))
            rows.append(row)
    return pd.DataFrame(rows).sort_values(["timestamp_ms", "window_index"]).reset_index(drop=True)


def _raw_to_actual_weights(
    *,
    decision_group: pd.DataFrame,
    constraints: dict,
    previous_weights: dict[str, float],
) -> tuple[dict[str, float], dict[str, float]]:
    raw_target = _cross_sectional_target_weights(
        decision_group=decision_group,
        constraints=constraints,
        previous_weights=previous_weights,
    )
    short_multiplier_column = str(constraints.get("short_position_weight_multiplier_column") or "").strip()
    if short_multiplier_column and raw_target and short_multiplier_column in decision_group.columns:
        multiplier_series = (
            pd.to_numeric(decision_group[short_multiplier_column], errors="coerce")
            .fillna(1.0)
            .clip(lower=0.0, upper=1.0)
        )
        multiplier_by_subject = {
            str(subject): float(multiplier)
            for subject, multiplier in zip(decision_group["subject"], multiplier_series)
        }
        adjusted: dict[str, float] = {}
        for subject, weight in raw_target.items():
            resolved = float(weight)
            if resolved < 0.0:
                resolved *= float(multiplier_by_subject.get(str(subject), 1.0))
            if abs(resolved) > 1e-12:
                adjusted[str(subject)] = resolved
        raw_target = adjusted
    actual = _scale_cross_sectional_turnover(
        raw_target_weights=raw_target,
        previous_weights=previous_weights,
        max_turnover_per_rebalance=float(constraints.get("max_turnover_per_rebalance", math.inf) or math.inf),
        turnover_mode=str(
            constraints.get("pair_turnover_mode")
            or constraints.get("turnover_mode")
            or ""
        ).strip().lower() or None,
    )
    return raw_target, actual


def _reconstruct_v5_positions(context: dict, frame: pd.DataFrame, constraints: dict, contract: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    spec = dict(context["spec"])
    base_execution_cost_model, stress_execution_cost_model = qlab._resolved_execution_cost_models()
    validation_contract = qlab.load_validation_contract()
    reference_capital_usd = qlab.validation_contract_reference_capital_usd(
        strategy_profile=str(spec.get("strategy_profile") or ""),
        contract=validation_contract,
    )
    capacity_limits = qlab.execution_capacity_limits(validation_contract)
    walk_forward = qlab._run_walk_forward(
        frame=frame,
        shape=str(spec.get("shape") or "cross_sectional"),
        model_family=str(spec["model_family"]),
        feature_columns=list(spec.get("feature_columns") or []),
        constraints=constraints,
        split_realization_contract=contract,
        target_column=str(spec.get("target_column") or "target_up"),
        execution_cost_model=base_execution_cost_model,
        stress_execution_cost_model=stress_execution_cost_model,
        reference_capital_usd=reference_capital_usd,
        capacity_limits=capacity_limits,
        validation_contract=validation_contract,
        model_definition=None,
        include_periods=True,
    )
    periods = _period_frame_from_walk_forward(walk_forward)

    positions: list[dict] = []
    time_index = pd.to_datetime(frame["timestamp_ms"], unit="ms", utc=True)
    current_anchor = time_index.min() + timedelta(days=120)
    final_anchor = time_index.max() - timedelta(days=30)
    latency_bars = int(base_execution_cost_model["latency_bars"])
    evaluation_step_bars = split_contract_realization_step_bars(contract)
    window_index = -1
    while current_anchor <= final_anchor:
        train_end = current_anchor - timedelta(days=30)
        validation_end = current_anchor
        test_end = current_anchor + timedelta(days=30)
        train_df, validation_df, test_df = qlab.walk_forward_split_with_purge(
            frame=frame,
            time_col="timestamp_ms",
            train_end=train_end,
            validation_end=validation_end,
            test_end=test_end,
            split_realization_contract=contract,
        )
        if train_df.empty or validation_df.empty or test_df.empty:
            current_anchor += timedelta(days=30)
            continue
        window_index += 1
        scored = qlab._fit_and_score(
            model_family=str(spec["model_family"]),
            shape=str(spec.get("shape") or "cross_sectional"),
            train_df=train_df,
            validation_df=validation_df,
            test_df=test_df,
            feature_columns=list(spec.get("feature_columns") or []),
            target_column=str(spec.get("target_column") or "target_up"),
            model_definition=None,
        )
        ordered = filter_cross_sectional_execution_frame(frame=scored["test"], constraints=constraints)
        ordered = ordered.sort_values(["timestamp_ms", "subject"]).copy()
        timestamps = sorted(int(item) for item in ordered["timestamp_ms"].drop_duplicates().tolist())
        decision_indices = list(range(0, len(timestamps), evaluation_step_bars))
        grouped = {int(timestamp): group.copy() for timestamp, group in ordered.groupby("timestamp_ms")}
        previous_weights: dict[str, float] = {}
        for decision_offset, timestamp_offset in enumerate(decision_indices):
            fill_offset = timestamp_offset + latency_bars
            if fill_offset >= len(timestamps):
                break
            next_fill = _next_fill_offset(
                timestamp_count=len(timestamps),
                decision_timestamp_indices=decision_indices,
                decision_offset=decision_offset,
                latency_bars=latency_bars,
            )
            decision_ts = int(timestamps[timestamp_offset])
            fill_ts = int(timestamps[fill_offset])
            exit_ts = int(timestamps[next_fill]) if next_fill is not None else int(timestamps[-1])
            decision_group = grouped[decision_ts]
            fill_group = grouped[fill_ts]
            exit_group = grouped[exit_ts]
            raw_target, actual = _raw_to_actual_weights(
                decision_group=decision_group,
                constraints=constraints,
                previous_weights=previous_weights,
            )
            ranks = decision_group[["subject", "score"]].copy()
            ranks["score_at_decision"] = pd.to_numeric(ranks["score"], errors="coerce")
            ranks["score_rank_desc"] = ranks["score_at_decision"].rank(ascending=False, method="first")
            score_by_subject = {str(row.subject): float(row.score_at_decision) for row in ranks.itertuples()}
            rank_by_subject = {str(row.subject): int(row.score_rank_desc) for row in ranks.itertuples()}
            liq_by_subject = {
                str(row.subject): str(getattr(row, "liquidity_bucket", ""))
                for row in decision_group.itertuples()
            }
            if "selection_rank" in decision_group.columns:
                universe_rank_by_subject = {
                    str(row.subject): float(getattr(row, "selection_rank"))
                    for row in decision_group.itertuples()
                }
            elif "universe_rank" in decision_group.columns:
                universe_rank_by_subject = {
                    str(row.subject): float(getattr(row, "universe_rank"))
                    for row in decision_group.itertuples()
                }
            else:
                universe_rank_by_subject = {}

            fill_rows = {str(row["subject"]): row for _, row in fill_group.iterrows()}
            exit_rows = {str(row["subject"]): row for _, row in exit_group.iterrows()}
            hold_slice = ordered.loc[
                (ordered["timestamp_ms"] >= fill_ts)
                & (ordered["timestamp_ms"] < exit_ts)
            ].copy()
            funding_rows = {str(subject): group.copy() for subject, group in hold_slice.groupby("subject")}

            for subject, weight in sorted(actual.items()):
                if abs(float(weight)) <= 1e-12:
                    continue
                fill_row = fill_rows.get(str(subject))
                exit_row = exit_rows.get(str(subject))
                data_gap_blockers: set[str] = set()
                gross = np.nan
                if fill_row is not None and exit_row is not None:
                    gross = _price_path_return(
                        entry_row=fill_row,
                        exit_row=exit_row,
                        weight=float(weight),
                        execution_venue="perp",
                        subject=str(subject),
                        data_gap_blockers=data_gap_blockers,
                    )
                funding = _funding_cost_return(
                    hold_slice=funding_rows.get(str(subject), pd.DataFrame()),
                    weight=float(weight),
                    execution_venue="perp",
                )
                previous_weight = float(previous_weights.get(str(subject), 0.0))
                positions.append(
                    {
                        "window_index": int(window_index),
                        "decision_timestamp_ms": decision_ts,
                        "fill_timestamp_ms": fill_ts,
                        "exit_timestamp_ms": exit_ts,
                        "fill_date_utc": _utc_date(fill_ts),
                        "exit_date_utc": _utc_date(exit_ts),
                        "subject": str(subject),
                        "side": "long" if float(weight) > 0 else "short",
                        "weight": float(weight),
                        "previous_weight": previous_weight,
                        "delta_weight": float(weight) - previous_weight,
                        "raw_target_weight": float(raw_target.get(str(subject), 0.0)),
                        "score_at_decision": score_by_subject.get(str(subject), np.nan),
                        "score_rank_desc": rank_by_subject.get(str(subject), np.nan),
                        "liquidity_bucket": liq_by_subject.get(str(subject), ""),
                        "universe_rank": universe_rank_by_subject.get(str(subject), np.nan),
                        "gross_contribution": float(gross) if pd.notna(gross) else np.nan,
                        "funding_cost_return": float(funding) if pd.notna(funding) else np.nan,
                        "net_before_trade_cost_contribution": (
                            float(gross - funding)
                            if pd.notna(gross) and pd.notna(funding)
                            else np.nan
                        ),
                    }
                )
            previous_weights = actual
        current_anchor += timedelta(days=30)

    positions_frame = pd.DataFrame(positions)
    if not positions_frame.empty:
        positions_frame = positions_frame.sort_values(["fill_timestamp_ms", "side", "subject"]).reset_index(drop=True)
    return periods, positions_frame


def _build_paired_returns(context: dict) -> pd.DataFrame:
    v5_fixed = pd.read_csv(context["fixed_returns_path"])
    hv_returns = pd.read_csv(ROOT / "artifacts" / "qr" / "hv_balanced" / "aligned_period_returns.csv")
    v5_returns = v5_fixed[["timestamp_ms", "timestamp_utc", "v5_rw_bridge_no_overlay_h10d"]].rename(
        columns={
            "timestamp_ms": "v5_timestamp_ms",
            "timestamp_utc": "v5_timestamp_utc",
            "v5_rw_bridge_no_overlay_h10d": "v5_return",
        }
    )
    hv_returns = hv_returns[
        [
            "timestamp_ms",
            "net_period_return",
            "gross_return_before_costs",
            "fee_cost_return",
            "slippage_cost_return",
            "funding_cost_return",
            "turnover",
        ]
    ].rename(
        columns={
            "timestamp_ms": "hv_timestamp_ms",
            "net_period_return": "hv_return",
            "gross_return_before_costs": "hv_gross_return_before_costs",
            "fee_cost_return": "hv_fee_cost_return",
            "slippage_cost_return": "hv_slippage_cost_return",
            "funding_cost_return": "hv_funding_cost_return",
            "turnover": "hv_turnover",
        }
    )
    paired = pd.merge_asof(
        v5_returns.sort_values("v5_timestamp_ms"),
        hv_returns.sort_values("hv_timestamp_ms"),
        left_on="v5_timestamp_ms",
        right_on="hv_timestamp_ms",
        direction="nearest",
        tolerance=MATCH_TOLERANCE_MS,
    )
    paired = paired.loc[paired["hv_timestamp_ms"].notna()].copy()
    paired["hv_timestamp_ms"] = paired["hv_timestamp_ms"].astype("int64")
    paired["timestamp_ms"] = paired["v5_timestamp_ms"].astype("int64")
    paired["timestamp_utc"] = paired["v5_timestamp_utc"]
    paired["hv_timestamp_utc"] = paired["hv_timestamp_ms"].apply(_iso_ms)
    paired["match_lag_days"] = (
        (paired["v5_timestamp_ms"].astype("int64") - paired["hv_timestamp_ms"].astype("int64")).abs()
        / 86_400_000.0
    )
    paired = paired.sort_values("v5_timestamp_ms").reset_index(drop=True)
    paired["return_diff_v5_minus_hv"] = paired["v5_return"] - paired["hv_return"]
    paired["v5_equity"] = (1.0 + paired["v5_return"]).cumprod()
    paired["hv_equity"] = (1.0 + paired["hv_return"]).cumprod()
    paired["v5_cum_net_return"] = paired["v5_equity"] - 1.0
    paired["hv_cum_net_return"] = paired["hv_equity"] - 1.0
    paired["cum_return_diff_v5_minus_hv"] = paired["v5_cum_net_return"] - paired["hv_cum_net_return"]
    return paired


def _prepare_position_diffs(paired: pd.DataFrame, v5_positions: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    v5_ts_to_pair = {
        int(row.v5_timestamp_ms): int(row.timestamp_ms)
        for row in paired.itertuples()
    }
    hv_ts_to_pair = {
        int(row.hv_timestamp_ms): int(row.timestamp_ms)
        for row in paired.itertuples()
    }
    v5_common_ts = set(v5_ts_to_pair)
    hv_common_ts = set(hv_ts_to_pair)
    hv_pos = pd.read_csv(ROOT / "artifacts" / "qr" / "hv_balanced" / "position_attribution.csv")
    hv_pos = hv_pos.loc[hv_pos["fill_timestamp_ms"].astype("int64").isin(hv_common_ts)].copy()
    hv_pos["pair_timestamp_ms"] = hv_pos["fill_timestamp_ms"].astype("int64").map(hv_ts_to_pair)
    hv_pos["subject"] = hv_pos["subject"].astype(str)
    hv_pos = hv_pos.rename(
        columns={
            "fill_timestamp_ms": "hv_fill_timestamp_ms",
            "side": "hv_side",
            "weight": "hv_weight",
            "score_at_decision": "hv_score_at_decision",
            "score_rank_desc": "hv_score_rank_desc",
            "gross_contribution": "hv_gross_contribution",
            "funding_cost_return": "hv_funding_cost_return",
            "net_before_trade_cost_contribution": "hv_net_before_trade_cost_contribution",
            "exit_date_utc": "hv_exit_date_utc",
        }
    )
    hv_pos = hv_pos[
        [
            "pair_timestamp_ms",
            "hv_fill_timestamp_ms",
            "subject",
            "hv_side",
            "hv_weight",
            "hv_score_at_decision",
            "hv_score_rank_desc",
            "hv_gross_contribution",
            "hv_funding_cost_return",
            "hv_net_before_trade_cost_contribution",
            "hv_exit_date_utc",
        ]
    ]

    v5_pos = v5_positions.loc[v5_positions["fill_timestamp_ms"].astype("int64").isin(v5_common_ts)].copy()
    v5_pos["pair_timestamp_ms"] = v5_pos["fill_timestamp_ms"].astype("int64").map(v5_ts_to_pair)
    v5_pos["subject"] = v5_pos["subject"].astype(str)
    v5_pos = v5_pos.rename(
        columns={
            "fill_timestamp_ms": "v5_fill_timestamp_ms",
            "side": "v5_side",
            "weight": "v5_weight",
            "score_at_decision": "v5_score_at_decision",
            "score_rank_desc": "v5_score_rank_desc",
            "gross_contribution": "v5_gross_contribution",
            "funding_cost_return": "v5_funding_cost_return",
            "net_before_trade_cost_contribution": "v5_net_before_trade_cost_contribution",
            "exit_date_utc": "v5_exit_date_utc",
        }
    )
    v5_pos = v5_pos[
        [
            "pair_timestamp_ms",
            "v5_fill_timestamp_ms",
            "subject",
            "v5_side",
            "v5_weight",
            "v5_score_at_decision",
            "v5_score_rank_desc",
            "v5_gross_contribution",
            "v5_funding_cost_return",
            "v5_net_before_trade_cost_contribution",
            "v5_exit_date_utc",
        ]
    ]

    pos_diff = v5_pos.merge(hv_pos, on=["pair_timestamp_ms", "subject"], how="outer")
    pos_diff["pair_date_utc"] = pos_diff["pair_timestamp_ms"].apply(_utc_date)
    pos_diff["v5_fill_date_utc"] = pd.to_numeric(pos_diff.get("v5_fill_timestamp_ms"), errors="coerce").map(
        lambda value: "" if pd.isna(value) else _utc_date(int(value))
    )
    pos_diff["hv_fill_date_utc"] = pd.to_numeric(pos_diff.get("hv_fill_timestamp_ms"), errors="coerce").map(
        lambda value: "" if pd.isna(value) else _utc_date(int(value))
    )
    numeric_cols = [
        "v5_weight",
        "hv_weight",
        "v5_net_before_trade_cost_contribution",
        "hv_net_before_trade_cost_contribution",
        "v5_gross_contribution",
        "hv_gross_contribution",
        "v5_funding_cost_return",
        "hv_funding_cost_return",
    ]
    for column in numeric_cols:
        pos_diff[column] = pd.to_numeric(pos_diff[column], errors="coerce").fillna(0.0)
    pos_diff["weight_diff_v5_minus_hv"] = pos_diff["v5_weight"] - pos_diff["hv_weight"]
    pos_diff["net_before_trade_diff_v5_minus_hv"] = (
        pos_diff["v5_net_before_trade_cost_contribution"]
        - pos_diff["hv_net_before_trade_cost_contribution"]
    )
    pos_diff["gross_contribution_diff_v5_minus_hv"] = (
        pos_diff["v5_gross_contribution"] - pos_diff["hv_gross_contribution"]
    )
    pos_diff["funding_cost_diff_v5_minus_hv"] = (
        pos_diff["v5_funding_cost_return"] - pos_diff["hv_funding_cost_return"]
    )

    def classify(row: pd.Series) -> str:
        v5_weight = float(row["v5_weight"])
        hv_weight = float(row["hv_weight"])
        if abs(v5_weight) > 1e-12 and abs(hv_weight) <= 1e-12:
            return "v5_only"
        if abs(hv_weight) > 1e-12 and abs(v5_weight) <= 1e-12:
            return "hv_only"
        if abs(v5_weight) <= 1e-12 and abs(hv_weight) <= 1e-12:
            return "none"
        if v5_weight * hv_weight < 0:
            return "opposite_direction"
        if abs(v5_weight - hv_weight) > 1e-9:
            return "same_direction_weight_shift"
        return "same_weight"

    pos_diff["diff_type"] = pos_diff.apply(classify, axis=1)
    pos_diff = pos_diff.loc[pos_diff["diff_type"] != "same_weight"].sort_values(
        ["pair_timestamp_ms", "diff_type", "subject"]
    ).reset_index(drop=True)

    period_rows = []
    for timestamp_ms, group in pos_diff.groupby("pair_timestamp_ms", sort=True):
        row = paired.loc[paired["timestamp_ms"] == int(timestamp_ms)].iloc[0]
        v5_subjects = set(v5_pos.loc[v5_pos["pair_timestamp_ms"] == int(timestamp_ms), "subject"])
        hv_subjects = set(hv_pos.loc[hv_pos["pair_timestamp_ms"] == int(timestamp_ms), "subject"])
        overlap_count = len(v5_subjects & hv_subjects)
        union_count = len(v5_subjects | hv_subjects)
        period_rows.append(
            {
                "pair_timestamp_ms": int(timestamp_ms),
                "pair_date_utc": _utc_date(int(timestamp_ms)),
                "v5_fill_date_utc": _utc_date(int(row["v5_timestamp_ms"])),
                "hv_fill_date_utc": _utc_date(int(row["hv_timestamp_ms"])),
                "match_lag_days": float(row["match_lag_days"]),
                "v5_return": float(row["v5_return"]),
                "hv_return": float(row["hv_return"]),
                "return_diff_v5_minus_hv": float(row["return_diff_v5_minus_hv"]),
                "v5_position_count": int(len(v5_subjects)),
                "hv_position_count": int(len(hv_subjects)),
                "subject_overlap_count": int(overlap_count),
                "subject_union_count": int(union_count),
                "subject_jaccard": float(overlap_count / union_count) if union_count else 1.0,
                "v5_only_count": int((group["diff_type"] == "v5_only").sum()),
                "hv_only_count": int((group["diff_type"] == "hv_only").sum()),
                "opposite_direction_count": int((group["diff_type"] == "opposite_direction").sum()),
                "same_direction_weight_shift_count": int((group["diff_type"] == "same_direction_weight_shift").sum()),
                "abs_net_before_trade_diff_sum": float(group["net_before_trade_diff_v5_minus_hv"].abs().sum()),
                "net_before_trade_diff_sum": float(group["net_before_trade_diff_v5_minus_hv"].sum()),
            }
        )
    period_summary = pd.DataFrame(period_rows).sort_values("pair_timestamp_ms").reset_index(drop=True)
    return pos_diff, period_summary, v5_pos


def _top_period_details(paired: pd.DataFrame, pos_diff: pd.DataFrame) -> pd.DataFrame:
    top_periods = paired.copy().sort_values("timestamp_ms").reset_index(drop=True)
    rows = []
    for period in top_periods.itertuples():
        timestamp_ms = int(period.timestamp_ms)
        group = pos_diff.loc[pos_diff["pair_timestamp_ms"] == timestamp_ms].copy()
        group["abs_net_diff"] = group["net_before_trade_diff_v5_minus_hv"].abs()
        top_legs = group.sort_values("abs_net_diff", ascending=False).head(8)
        rows.append(
            {
                "pair_date_utc": _utc_date(timestamp_ms),
                "v5_fill_date_utc": _utc_date(int(period.v5_timestamp_ms)),
                "hv_fill_date_utc": _utc_date(int(period.hv_timestamp_ms)),
                "match_lag_days": float(period.match_lag_days),
                "v5_return": float(period.v5_return),
                "hv_return": float(period.hv_return),
                "return_diff_v5_minus_hv": float(period.return_diff_v5_minus_hv),
                "top_leg_diffs": "; ".join(
                    (
                        f"{leg.subject}: {leg.diff_type}, "
                        f"v5_w={leg.v5_weight:.4f}, hv_w={leg.hv_weight:.4f}, "
                        f"netdiff={leg.net_before_trade_diff_v5_minus_hv:.4f}"
                    )
                    for leg in top_legs.itertuples()
                ),
            }
        )
    return pd.DataFrame(rows)


def _markdown_table(df: pd.DataFrame, columns: list[str], float_columns: set[str] | None = None) -> str:
    float_columns = float_columns or set()
    out = df[columns].copy()
    for column in float_columns:
        if column in out.columns:
            out[column] = out[column].map(lambda value: f"{float(value):.6f}")
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for _, row in out.iterrows():
        lines.append("| " + " | ".join(str(row[column]) for column in columns) + " |")
    return "\n".join(lines)


def _write_plot(paired: pd.DataFrame) -> Path:
    plot_path = OUT / "paired_mtm_v5_rw_vs_hv_balanced.png"
    plt.figure(figsize=(12, 6.5))
    plt.plot(
        pd.to_datetime(paired["timestamp_ms"], unit="ms", utc=True),
        paired["v5_equity"],
        label="v5_rw_bridge_no_overlay_h10d",
        linewidth=2.2,
    )
    plt.plot(
        pd.to_datetime(paired["timestamp_ms"], unit="ms", utc=True),
        paired["hv_equity"],
        label="hv_balanced (nearest 10d-cycle match)",
        linewidth=2.2,
    )
    plt.axhline(1.0, color="#666666", linewidth=0.8, alpha=0.5)
    plt.title("Paired MTM: v5_rw_bridge_no_overlay_h10d vs hv_balanced")
    plt.ylabel("Equity curve, start = 1.0")
    plt.xlabel("Fill timestamp")
    plt.grid(True, alpha=0.25)
    plt.legend(loc="best")
    plt.tight_layout()
    plt.savefig(plot_path, dpi=160)
    plt.close()
    return plot_path


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    DOC.parent.mkdir(parents=True, exist_ok=True)
    context = _load_v5_context()
    paired = _build_paired_returns(context)
    paired.to_csv(OUT / "paired_mtm_curve.csv", index=False)

    filtered_frame, v5_constraints, v5_contract = _load_v5_fixed_set_frame(context)
    v5_periods, v5_positions = _reconstruct_v5_positions(
        context,
        frame=filtered_frame,
        constraints=v5_constraints,
        contract=v5_contract,
    )
    v5_periods.to_csv(OUT / "reconstructed_v5_periods.csv", index=False)
    v5_positions.to_csv(OUT / "reconstructed_v5_positions.csv", index=False)

    v5_fixed = pd.read_csv(context["fixed_returns_path"])
    hv_returns = pd.read_csv(ROOT / "artifacts" / "qr" / "hv_balanced" / "aligned_period_returns.csv")
    v5_returns = v5_fixed[["timestamp_ms", "timestamp_utc", "v5_rw_bridge_no_overlay_h10d"]].rename(
        columns={"v5_rw_bridge_no_overlay_h10d": "v5_return"}
    )
    v5_period_components = v5_periods[
        [
            "timestamp_ms",
            "net_period_return",
            "gross_return_before_costs",
            "fee_cost_return",
            "slippage_cost_return",
            "funding_cost_return",
            "turnover",
        ]
    ].rename(
        columns={
            "net_period_return": "v5_reconstructed_return",
            "gross_return_before_costs": "v5_gross_return_before_costs",
            "fee_cost_return": "v5_fee_cost_return",
            "slippage_cost_return": "v5_slippage_cost_return",
            "funding_cost_return": "v5_funding_cost_return",
            "turnover": "v5_turnover",
        }
    )
    parity = v5_returns.merge(
        v5_period_components[["timestamp_ms", "v5_reconstructed_return"]],
        on="timestamp_ms",
        how="left",
    )
    parity["abs_error"] = (parity["v5_return"] - parity["v5_reconstructed_return"]).abs()
    parity.to_csv(OUT / "v5_reconstruction_return_parity.csv", index=False)
    max_parity_error = float(parity["abs_error"].max()) if not parity.empty else math.nan

    paired_components = paired.merge(v5_period_components, on="timestamp_ms", how="left")
    paired_components.to_csv(OUT / "paired_period_component_returns.csv", index=False)

    pos_diff, period_diff_summary, _v5_pos_common = _prepare_position_diffs(paired, v5_positions)
    pos_diff.to_csv(OUT / "position_diffs.csv", index=False)
    period_diff_summary.to_csv(OUT / "period_position_diff_summary.csv", index=False)
    top_period_detail = _top_period_details(paired, pos_diff)
    top_period_detail.to_csv(OUT / "top_period_trade_differences.csv", index=False)

    top_leg_diffs = pos_diff.copy()
    top_leg_diffs["abs_net_before_trade_diff"] = top_leg_diffs["net_before_trade_diff_v5_minus_hv"].abs()
    top_leg_diffs.sort_values("abs_net_before_trade_diff", ascending=False).head(80).to_csv(
        OUT / "top_leg_diffs.csv",
        index=False,
    )

    v5_perf = _perf(paired["v5_return"])
    hv_perf = _perf(paired["hv_return"])
    summary_df = pd.DataFrame(
        [
            {
                "strategy": "v5_rw_bridge_no_overlay_h10d",
                "periods": len(paired),
                "start_utc": paired["timestamp_utc"].iloc[0],
                "end_utc": paired["timestamp_utc"].iloc[-1],
                **v5_perf,
            },
            {
                "strategy": "hv_balanced_nearest_cycle",
                "periods": len(paired),
                "start_utc": paired["timestamp_utc"].iloc[0],
                "end_utc": paired["timestamp_utc"].iloc[-1],
                **hv_perf,
            },
        ]
    )
    summary_df.to_csv(OUT / "paired_summary_metrics.csv", index=False)

    component_pairs = [
        ("gross_return_before_costs", "v5_gross_return_before_costs", "hv_gross_return_before_costs"),
        ("fee_cost_return", "v5_fee_cost_return", "hv_fee_cost_return"),
        ("slippage_cost_return", "v5_slippage_cost_return", "hv_slippage_cost_return"),
        ("funding_cost_return", "v5_funding_cost_return", "hv_funding_cost_return"),
        ("turnover", "v5_turnover", "hv_turnover"),
    ]
    component_summary = []
    for component, v5_column, hv_column in component_pairs:
        v5_sum = float(pd.to_numeric(paired_components[v5_column], errors="coerce").fillna(0.0).sum())
        hv_sum = float(pd.to_numeric(paired_components[hv_column], errors="coerce").fillna(0.0).sum())
        component_summary.append(
            {
                "component": component,
                "v5_sum": v5_sum,
                "hv_sum": hv_sum,
                "diff_v5_minus_hv": v5_sum - hv_sum,
            }
        )
    component_summary_df = pd.DataFrame(component_summary)
    component_summary_df.to_csv(OUT / "component_summary.csv", index=False)

    plot_path = _write_plot(paired)

    full_v5_fixed_perf = _perf(v5_fixed["v5_rw_bridge_no_overlay_h10d"])
    full_hv_perf = _perf(hv_returns["net_period_return"])
    win_count = int((paired["return_diff_v5_minus_hv"] > 0).sum())
    loss_count = int((paired["return_diff_v5_minus_hv"] < 0).sum())
    mean_jaccard = float(period_diff_summary["subject_jaccard"].mean()) if not period_diff_summary.empty else math.nan
    opposite_periods = int((period_diff_summary["opposite_direction_count"] > 0).sum()) if not period_diff_summary.empty else 0
    exact_subject_set_periods = int((period_diff_summary["subject_jaccard"] >= 0.999999).sum()) if not period_diff_summary.empty else 0

    best_dates = top_period_detail.sort_values("return_diff_v5_minus_hv", ascending=False).head(5)
    worst_dates = top_period_detail.sort_values("return_diff_v5_minus_hv", ascending=True).head(5)

    lines = [
        "# v5_rw_bridge_no_overlay_h10d vs hv_balanced Trade Diff",
        "",
        "## Scope",
        "",
        "- Generated at: 2026-05-18",
        f"- v5 source: `{Path(context['fixed_returns_path']).as_posix()}`",
        f"- hv source: `{(ROOT / 'artifacts' / 'qr' / 'hv_balanced' / 'aligned_period_returns.csv').as_posix()}`",
        (
            f"- Comparison mode: nearest 10d-cycle match, `{len(paired)}` v5 fill timestamps "
            f"from `{paired['timestamp_utc'].iloc[0]}` to `{paired['timestamp_utc'].iloc[-1]}`; "
            f"max match lag `{float(paired['match_lag_days'].max()):.1f}` days."
        ),
        f"- v5 position reconstruction max absolute return parity error vs fixed-set file: `{max_parity_error:.12g}`.",
        "",
        "## Paired Metrics",
        "",
        _markdown_table(
            summary_df,
            ["strategy", "periods", "start_utc", "end_utc", "net_return", "sharpe", "max_drawdown"],
            {"net_return", "sharpe", "max_drawdown"},
        ),
        "",
        "## Full Native Windows",
        "",
        (
            f"- v5 native fixed-set full OOS: net `{full_v5_fixed_perf['net_return']:.6f}`, "
            f"Sharpe `{full_v5_fixed_perf['sharpe']:.3f}`, Max DD `{full_v5_fixed_perf['max_drawdown']:.6f}`, "
            f"periods `{len(v5_fixed)}`."
        ),
        (
            f"- hv native frozen full sample: net `{full_hv_perf['net_return']:.6f}`, "
            f"Sharpe `{full_hv_perf['sharpe']:.3f}`, Max DD `{full_hv_perf['max_drawdown']:.6f}`, "
            f"periods `{len(hv_returns)}`."
        ),
        "",
        "## Component Sums On Common Timestamps",
        "",
        _markdown_table(
            component_summary_df,
            ["component", "v5_sum", "hv_sum", "diff_v5_minus_hv"],
            {"v5_sum", "hv_sum", "diff_v5_minus_hv"},
        ),
        "",
        "## Position Difference Summary",
        "",
        f"- Period wins/losses for v5 vs hv: `{win_count}` / `{loss_count}`.",
        (
            f"- Mean subject-set Jaccard overlap: `{mean_jaccard:.3f}`; exact same subject set periods: "
            f"`{exact_subject_set_periods}` / `{len(period_diff_summary)}`."
        ),
        f"- Periods with at least one opposite-direction same-symbol leg: `{opposite_periods}` / `{len(period_diff_summary)}`.",
        f"- All leg-level differences are in `{(OUT / 'position_diffs.csv').as_posix()}`.",
        f"- Largest contribution differences are in `{(OUT / 'top_leg_diffs.csv').as_posix()}`.",
        "",
        "## Top v5 Outperformance Periods",
        "",
        _markdown_table(
            best_dates,
            [
                "pair_date_utc",
                "v5_fill_date_utc",
                "hv_fill_date_utc",
                "match_lag_days",
                "v5_return",
                "hv_return",
                "return_diff_v5_minus_hv",
                "top_leg_diffs",
            ],
            {"v5_return", "hv_return", "return_diff_v5_minus_hv"},
        ),
        "",
        "## Top hv Outperformance Periods",
        "",
        _markdown_table(
            worst_dates,
            [
                "pair_date_utc",
                "v5_fill_date_utc",
                "hv_fill_date_utc",
                "match_lag_days",
                "v5_return",
                "hv_return",
                "return_diff_v5_minus_hv",
                "top_leg_diffs",
            ],
            {"v5_return", "hv_return", "return_diff_v5_minus_hv"},
        ),
        "",
        "## Artifacts",
        "",
    ]
    for name in [
        "paired_mtm_v5_rw_vs_hv_balanced.png",
        "paired_mtm_curve.csv",
        "paired_summary_metrics.csv",
        "paired_period_component_returns.csv",
        "component_summary.csv",
        "reconstructed_v5_positions.csv",
        "v5_reconstruction_return_parity.csv",
        "position_diffs.csv",
        "period_position_diff_summary.csv",
        "top_period_trade_differences.csv",
        "top_leg_diffs.csv",
    ]:
        lines.append(f"- `{(OUT / name).as_posix()}`")
    DOC.write_text("\n".join(lines) + "\n", encoding="utf-8")

    summary = {
        "status": "completed",
        "output_root": str(OUT),
        "report_path": str(DOC),
        "plot_path": str(plot_path),
        "paired_period_count": int(len(paired)),
        "start_utc": str(paired["timestamp_utc"].iloc[0]),
        "end_utc": str(paired["timestamp_utc"].iloc[-1]),
        "v5_overlap": v5_perf,
        "hv_overlap": hv_perf,
        "v5_full_fixed_set": full_v5_fixed_perf,
        "hv_full_native": full_hv_perf,
        "v5_return_parity_max_abs_error": max_parity_error,
        "period_win_count_v5": win_count,
        "period_loss_count_v5": loss_count,
        "mean_subject_jaccard": mean_jaccard,
        "opposite_direction_period_count": opposite_periods,
        "match_mode": "nearest_10d_cycle",
        "max_match_lag_days": float(paired["match_lag_days"].max()) if not paired.empty else None,
        "component_summary": component_summary,
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
