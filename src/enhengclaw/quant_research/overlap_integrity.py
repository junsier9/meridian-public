from __future__ import annotations

from datetime import timedelta
from typing import Any

import pandas as pd

from .split_realization_contract import (
    build_overlap_integrity_view,
    build_split_realization_contract,
    partition_gap_bars as contract_partition_gap_bars,
    resolve_split_realization_contract,
)


def infer_interval_ms(timestamp_series: pd.Series) -> int:
    deltas = timestamp_series.sort_values().diff().dropna()
    positive_deltas = deltas.loc[deltas > 0]
    if positive_deltas.empty:
        raise ValueError("cannot infer positive interval_ms from fewer than two distinct timestamps")
    return int(positive_deltas.mode().iloc[0])


def infer_label_horizon_bars(
    *,
    frame: pd.DataFrame,
    price_column: str = "spot_close",
    target_column: str = "target_forward_return",
    max_horizon_bars: int = 48,
) -> int:
    ordered = frame.sort_values("timestamp_ms").reset_index(drop=True)
    group_column = "subject" if "subject" in ordered.columns else None
    close = ordered[price_column].replace(0, pd.NA)
    target = ordered[[target_column]].copy()
    for horizon_bars in range(1, max_horizon_bars + 1):
        if group_column is None:
            candidate = close.shift(-horizon_bars) / close - 1.0
        else:
            candidate = (
                ordered.groupby(group_column, sort=False)[price_column]
                .shift(-horizon_bars)
                .replace(0, pd.NA)
                / close
                - 1.0
            )
        compare = pd.DataFrame(
            {
                "target": target[target_column],
                "candidate": candidate,
            }
        ).dropna()
        if compare.empty:
            continue
        max_abs_error = float((compare["target"] - compare["candidate"]).abs().max())
        if max_abs_error < 1e-12:
            return horizon_bars
    raise ValueError("could not infer label horizon bars from feature frame")


def purge_gap_bars(*, label_horizon_bars: int) -> int:
    return max(int(label_horizon_bars) - 1, 0)


def chronological_split_with_purge(
    frame: pd.DataFrame,
    *,
    time_col: str,
    label_horizon_bars: int | None = None,
    split_realization_contract: dict[str, Any] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame] | None:
    ordered_times = sorted(frame[time_col].drop_duplicates().tolist())
    if len(ordered_times) < 30:
        return None
    train_end_index = max(int(len(ordered_times) * 0.6), 1) - 1
    validation_end_index = max(int(len(ordered_times) * 0.8), train_end_index + 2) - 1
    if validation_end_index >= len(ordered_times):
        return None
    if split_realization_contract:
        resolved_contract = resolve_split_realization_contract(contract=split_realization_contract)
        partition_gap_bars = contract_partition_gap_bars(resolved_contract)
    else:
        partition_gap_bars = max(int(label_horizon_bars or 0), 0)
    validation_start_index = train_end_index + partition_gap_bars
    test_start_index = validation_end_index + partition_gap_bars
    if validation_start_index > validation_end_index or test_start_index >= len(ordered_times):
        return None
    train_cut = ordered_times[train_end_index]
    validation_start = ordered_times[validation_start_index]
    validation_cut = ordered_times[validation_end_index]
    test_start = ordered_times[test_start_index]
    train_df = frame.loc[frame[time_col] <= train_cut].copy()
    validation_df = frame.loc[(frame[time_col] >= validation_start) & (frame[time_col] <= validation_cut)].copy()
    test_df = frame.loc[frame[time_col] >= test_start].copy()
    if train_df.empty or validation_df.empty or test_df.empty:
        return None
    return train_df, validation_df, test_df


def walk_forward_split_with_purge(
    *,
    frame: pd.DataFrame,
    time_col: str,
    train_end: pd.Timestamp,
    validation_end: pd.Timestamp,
    test_end: pd.Timestamp,
    interval_ms: int | None = None,
    label_horizon_bars: int | None = None,
    split_realization_contract: dict[str, Any] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if split_realization_contract:
        resolved_contract = resolve_split_realization_contract(contract=split_realization_contract)
        interval_ms = _require_positive_interval_ms(
            interval_ms=int(resolved_contract["bar_interval_ms"]),
            field_name="split_realization_contract.bar_interval_ms",
        )
        partition_gap_bars = contract_partition_gap_bars(resolved_contract)
    else:
        interval_ms = _require_positive_interval_ms(interval_ms=int(interval_ms or 0), field_name="interval_ms")
        partition_gap_bars = max(int(label_horizon_bars or 0), 0)
    time_index = pd.to_datetime(frame[time_col], unit="ms", utc=True)
    start_gap = timedelta(milliseconds=interval_ms * partition_gap_bars)
    validation_start = train_end + start_gap
    test_start = validation_end + start_gap
    train_df = frame.loc[time_index <= train_end].copy()
    validation_df = frame.loc[(time_index >= validation_start) & (time_index <= validation_end)].copy()
    test_df = frame.loc[(time_index >= test_start) & (time_index <= test_end)].copy()
    return train_df, validation_df, test_df


def evaluate_overlap_integrity(
    *,
    train_df: pd.DataFrame,
    validation_df: pd.DataFrame,
    test_df: pd.DataFrame,
    label_horizon_bars: int | None = None,
    bar_interval_ms: int | None = None,
    evaluation_step_bars: int,
    prediction_count: int,
    rebalance_count: int,
    split_realization_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if split_realization_contract:
        resolved_contract = resolve_split_realization_contract(contract=split_realization_contract)
    else:
        resolved_contract = build_split_realization_contract(
            shape="single_asset" if int(label_horizon_bars or 0) > 1 else "cross_sectional",
            bar_interval_ms=_require_positive_interval_ms(
                interval_ms=int(bar_interval_ms or 0),
                field_name="bar_interval_ms",
            ),
        )
        resolved_contract["target_horizon_bars"] = int(label_horizon_bars or resolved_contract["target_horizon_bars"])
        resolved_contract["realization_step_bars"] = int(evaluation_step_bars)
        resolved_contract["partition_gap_bars"] = int(label_horizon_bars or resolved_contract["partition_gap_bars"])
        resolved_contract["skipped_between_partitions_bars"] = max(int(resolved_contract["partition_gap_bars"]) - 1, 0)
    return build_overlap_integrity_view(
        train_df=train_df,
        validation_df=validation_df,
        test_df=test_df,
        contract=resolved_contract,
        evaluation_step_bars=evaluation_step_bars,
        prediction_count=prediction_count,
        rebalance_count=rebalance_count,
        time_col="timestamp_ms",
    )


def _partition_contamination_summary(
    *,
    frame: pd.DataFrame,
    next_partition_start_ms: int,
    label_horizon_bars: int,
    bar_interval_ms: int,
) -> dict[str, Any]:
    contaminated = frame.loc[
        (frame["timestamp_ms"] + (int(label_horizon_bars) * int(bar_interval_ms))) > int(next_partition_start_ms)
    ].sort_values("timestamp_ms")
    samples = [
        {
            "timestamp_ms": int(row["timestamp_ms"]),
            "label_window_end_ms": int(row["timestamp_ms"] + (int(label_horizon_bars) * int(bar_interval_ms))),
        }
        for _, row in contaminated.head(6).iterrows()
    ]
    return {
        "contaminated_row_count": int(len(contaminated)),
        "next_partition_start_ms": int(next_partition_start_ms),
        "samples": samples,
    }


def _require_positive_interval_ms(*, interval_ms: int, field_name: str) -> int:
    normalized = int(interval_ms)
    if normalized <= 0:
        raise ValueError(f"{field_name} must be a positive integer, got {normalized}")
    return normalized
