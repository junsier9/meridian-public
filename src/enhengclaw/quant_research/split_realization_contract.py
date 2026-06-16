from __future__ import annotations

from typing import Any

import pandas as pd


SPLIT_REALIZATION_CONTRACT_VERSION = "quant_split_realization_contract.v1"

BAR_INTERVAL_MS_BY_INTERVAL = {
    "1h": 60 * 60 * 1000,
    "4h": 4 * 60 * 60 * 1000,
    "1d": 24 * 60 * 60 * 1000,
}

DEFAULT_CONTRACT_BY_SHAPE = {
    "single_asset": {
        "target_horizon_bars": 6,
        "realization_step_bars": 6,
        "partition_gap_bars": 6,
        "skipped_between_partitions_bars": 5,
    },
    "cross_sectional": {
        "target_horizon_bars": 1,
        "realization_step_bars": 1,
        "partition_gap_bars": 1,
        "skipped_between_partitions_bars": 0,
    },
}


def bar_interval_ms_for_interval(interval: str) -> int:
    normalized = str(interval or "").strip().lower()
    if normalized not in BAR_INTERVAL_MS_BY_INTERVAL:
        raise ValueError(f"unsupported quant interval for split/realization contract: {interval!r}")
    return int(BAR_INTERVAL_MS_BY_INTERVAL[normalized])


def build_split_realization_contract(
    *,
    shape: str,
    interval: str | None = None,
    bar_interval_ms: int | None = None,
    target_horizon_bars: int | None = None,
) -> dict[str, Any]:
    normalized_shape = str(shape or "").strip()
    if normalized_shape not in DEFAULT_CONTRACT_BY_SHAPE:
        raise ValueError(f"unsupported split/realization contract shape: {shape!r}")
    resolved_bar_interval_ms = int(
        bar_interval_ms
        if bar_interval_ms is not None
        else bar_interval_ms_for_interval(str(interval or "").strip())
    )
    template = DEFAULT_CONTRACT_BY_SHAPE[normalized_shape]
    resolved_target_horizon_bars = int(
        target_horizon_bars if target_horizon_bars is not None else template["target_horizon_bars"]
    )
    resolved_realization_step_bars = int(
        resolved_target_horizon_bars if target_horizon_bars is not None else template["realization_step_bars"]
    )
    resolved_partition_gap_bars = int(
        resolved_target_horizon_bars if target_horizon_bars is not None else template["partition_gap_bars"]
    )
    resolved_skipped_between_partitions_bars = int(
        max(resolved_partition_gap_bars - 1, 0)
        if target_horizon_bars is not None
        else template["skipped_between_partitions_bars"]
    )
    return {
        "contract_version": SPLIT_REALIZATION_CONTRACT_VERSION,
        "shape": normalized_shape,
        "target_horizon_bars": resolved_target_horizon_bars,
        "realization_step_bars": resolved_realization_step_bars,
        "bar_interval_ms": resolved_bar_interval_ms,
        "partition_gap_bars": resolved_partition_gap_bars,
        "skipped_between_partitions_bars": resolved_skipped_between_partitions_bars,
        "require_zero_boundary_contamination": True,
        "require_non_overlapping_realization": True,
    }


def resolve_split_realization_contract(
    *,
    contract: dict[str, Any] | None = None,
    shape: str | None = None,
    interval: str | None = None,
    bar_interval_ms: int | None = None,
) -> dict[str, Any]:
    if contract:
        payload = dict(contract)
        normalized_shape = str(payload.get("shape") or shape or "").strip()
        if not normalized_shape:
            raise ValueError("split_realization_contract.shape is required")
        defaults = build_split_realization_contract(
            shape=normalized_shape,
            interval=interval,
            bar_interval_ms=_safe_int(payload.get("bar_interval_ms"), fallback=bar_interval_ms),
        )
        merged = {**defaults, **payload}
        merged["shape"] = normalized_shape
        merged["contract_version"] = str(merged.get("contract_version") or SPLIT_REALIZATION_CONTRACT_VERSION)
        merged["target_horizon_bars"] = _safe_int(merged.get("target_horizon_bars"))
        merged["realization_step_bars"] = _safe_int(merged.get("realization_step_bars"))
        merged["bar_interval_ms"] = _safe_int(merged.get("bar_interval_ms"))
        merged["partition_gap_bars"] = _safe_int(merged.get("partition_gap_bars"))
        merged["skipped_between_partitions_bars"] = _safe_int(merged.get("skipped_between_partitions_bars"))
        merged["require_zero_boundary_contamination"] = bool(merged.get("require_zero_boundary_contamination", True))
        merged["require_non_overlapping_realization"] = bool(merged.get("require_non_overlapping_realization", True))
        return merged
    if shape is None:
        raise ValueError("shape is required when split_realization_contract is not supplied")
    return build_split_realization_contract(
        shape=shape,
        interval=interval,
        bar_interval_ms=bar_interval_ms,
    )


def target_horizon_bars(contract: dict[str, Any]) -> int:
    return _safe_int(dict(contract or {}).get("target_horizon_bars"))


def realization_step_bars(contract: dict[str, Any]) -> int:
    return _safe_int(dict(contract or {}).get("realization_step_bars"))


def partition_gap_bars(contract: dict[str, Any]) -> int:
    return _safe_int(dict(contract or {}).get("partition_gap_bars"))


def skipped_between_partitions_bars(contract: dict[str, Any]) -> int:
    return _safe_int(dict(contract or {}).get("skipped_between_partitions_bars"))


def expected_rebalance_count(
    *,
    frame: pd.DataFrame,
    contract: dict[str, Any],
    time_col: str = "timestamp_ms",
) -> int:
    if frame.empty:
        return 0
    step = max(realization_step_bars(contract), 1)
    unique_times = frame[time_col].drop_duplicates().tolist()
    return int(len(unique_times[::step]))


def split_boundary_contamination_counts(
    *,
    train_df: pd.DataFrame,
    validation_df: pd.DataFrame,
    test_df: pd.DataFrame,
    contract: dict[str, Any],
    time_col: str = "timestamp_ms",
) -> dict[str, Any]:
    resolved_contract = resolve_split_realization_contract(contract=contract)
    bar_interval_ms = _safe_int(resolved_contract.get("bar_interval_ms"))
    horizon_bars = target_horizon_bars(resolved_contract)
    train_to_validation = _partition_contamination_summary(
        frame=train_df,
        next_partition_start_ms=int(validation_df[time_col].min()),
        target_horizon_bars=horizon_bars,
        bar_interval_ms=bar_interval_ms,
        time_col=time_col,
    )
    validation_to_test = _partition_contamination_summary(
        frame=validation_df,
        next_partition_start_ms=int(test_df[time_col].min()),
        target_horizon_bars=horizon_bars,
        bar_interval_ms=bar_interval_ms,
        time_col=time_col,
    )
    return {
        "train_to_validation": train_to_validation,
        "validation_to_test": validation_to_test,
    }


def split_boundary_contamination_total(*, counts: dict[str, Any] | None) -> int:
    payload = dict(counts or {})
    return int(dict(payload.get("train_to_validation") or {}).get("contaminated_row_count", 0) or 0) + int(
        dict(payload.get("validation_to_test") or {}).get("contaminated_row_count", 0) or 0
    )


def backtest_realization_mismatch(
    *,
    contract: dict[str, Any],
    evaluation_step_bars: int,
    prediction_count: int,
    rebalance_count: int,
) -> dict[str, Any]:
    resolved_contract = resolve_split_realization_contract(contract=contract)
    expected_step = realization_step_bars(resolved_contract)
    return {
        "detected": int(evaluation_step_bars) != int(expected_step),
        "label_horizon_bars": target_horizon_bars(resolved_contract),
        "realization_step_bars": expected_step,
        "evaluation_step_bars": int(evaluation_step_bars),
        "prediction_count": int(prediction_count),
        "rebalance_count": int(rebalance_count),
    }


def build_overlap_integrity_view(
    *,
    train_df: pd.DataFrame,
    validation_df: pd.DataFrame,
    test_df: pd.DataFrame,
    contract: dict[str, Any],
    evaluation_step_bars: int,
    prediction_count: int,
    rebalance_count: int,
    time_col: str = "timestamp_ms",
) -> dict[str, Any]:
    resolved_contract = resolve_split_realization_contract(contract=contract)
    counts = split_boundary_contamination_counts(
        train_df=train_df,
        validation_df=validation_df,
        test_df=test_df,
        contract=resolved_contract,
        time_col=time_col,
    )
    total = split_boundary_contamination_total(counts=counts)
    mismatch = backtest_realization_mismatch(
        contract=resolved_contract,
        evaluation_step_bars=evaluation_step_bars,
        prediction_count=prediction_count,
        rebalance_count=rebalance_count,
    )
    return {
        "label_horizon_bars": target_horizon_bars(resolved_contract),
        "bar_interval_ms": _safe_int(resolved_contract.get("bar_interval_ms")),
        "purge_gap_bars": partition_gap_bars(resolved_contract),
        "split_boundary_contamination_counts": counts,
        "label_split_overlap": total,
        "backtest_horizon_mismatch": mismatch,
        "passed": total == 0 and not bool(mismatch["detected"]),
    }


def _partition_contamination_summary(
    *,
    frame: pd.DataFrame,
    next_partition_start_ms: int,
    target_horizon_bars: int,
    bar_interval_ms: int,
    time_col: str,
) -> dict[str, Any]:
    contaminated = frame.loc[
        (frame[time_col] + (int(target_horizon_bars) * int(bar_interval_ms))) > int(next_partition_start_ms)
    ].sort_values(time_col)
    samples = [
        {
            "timestamp_ms": int(row[time_col]),
            "label_window_end_ms": int(row[time_col] + (int(target_horizon_bars) * int(bar_interval_ms))),
        }
        for _, row in contaminated.head(6).iterrows()
    ]
    return {
        "contaminated_row_count": int(len(contaminated)),
        "next_partition_start_ms": int(next_partition_start_ms),
        "samples": samples,
    }


def _safe_int(value: Any, fallback: int | None = None) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        if fallback is None:
            raise
        return int(fallback)
