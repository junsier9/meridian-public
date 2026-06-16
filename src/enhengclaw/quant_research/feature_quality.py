from __future__ import annotations

from typing import Any, Iterable

import pandas as pd

from .derivatives_quality import (
    DERIVATIVES_FEATURE_SPECS,
    feature_ready_flag_column as derivatives_feature_ready_flag_column,
    feature_source_flag_column as derivatives_feature_source_flag_column,
)


FEATURE_SOURCE_FLAG_PREFIX = "__feature_source__"
FEATURE_READY_FLAG_PREFIX = "__feature_ready__"
FEATURE_QUALITY_BASE_COLUMNS = (
    "subject",
    "timestamp_ms",
    "liquidity_bucket",
    "usdm_symbol",
)


def feature_source_flag_column(feature_name: str) -> str:
    return f"{FEATURE_SOURCE_FLAG_PREFIX}{feature_name}"


def feature_ready_flag_column(feature_name: str) -> str:
    return f"{FEATURE_READY_FLAG_PREFIX}{feature_name}"


def build_feature_quality_frame(
    *,
    feature_frame: pd.DataFrame,
    tracked_feature_columns: Iterable[str],
    derivatives_quality_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    base_columns = [
        column
        for column in FEATURE_QUALITY_BASE_COLUMNS
        if column in feature_frame.columns
    ]
    quality_frame = feature_frame[base_columns].copy()
    tracked_columns = _normalized_columns(tracked_feature_columns)
    if not tracked_columns:
        return quality_frame
    legacy_derivatives = (
        derivatives_quality_frame.reset_index(drop=True).copy()
        if derivatives_quality_frame is not None
        else pd.DataFrame(index=feature_frame.index)
    )
    stablecoin_ready_mask = _ready_proxy_mask(
        feature_frame,
        proxy_column="stablecoin_flow_signal_ready",
        threshold=0.0,
    )
    m3_2_ready_mask = _ready_proxy_mask(
        feature_frame,
        proxy_column="m3_2_panel_ready",
        threshold=0.5,
    )
    quality_columns: dict[str, pd.Series] = {}
    for column in tracked_columns:
        source_mask, ready_mask = _source_ready_masks(
            feature_frame=feature_frame,
            feature_name=column,
            legacy_derivatives=legacy_derivatives,
            stablecoin_ready_mask=stablecoin_ready_mask,
            m3_2_ready_mask=m3_2_ready_mask,
        )
        quality_columns[feature_source_flag_column(column)] = source_mask.astype("bool")
        quality_columns[feature_ready_flag_column(column)] = ready_mask.astype("bool")
    if quality_columns:
        quality_frame = pd.concat(
            [quality_frame, pd.DataFrame(quality_columns, index=feature_frame.index)],
            axis=1,
        ).copy()
    return quality_frame


def summarize_feature_quality(
    *,
    feature_quality_frame: pd.DataFrame,
    tracked_feature_columns: Iterable[str],
) -> dict[str, Any]:
    tracked_columns = _normalized_columns(tracked_feature_columns)
    features: dict[str, Any] = {}
    for column in tracked_columns:
        source_mask = _bool_mask(feature_quality_frame, feature_source_flag_column(column))
        ready_mask = _bool_mask(feature_quality_frame, feature_ready_flag_column(column))
        features[column] = {
            "row_source_fraction": _fraction(source_mask),
            "row_ready_fraction": _fraction(ready_mask),
            "source_subject_count": _subject_count_for_mask(feature_quality_frame, source_mask),
            "ready_subject_count": _subject_count_for_mask(feature_quality_frame, ready_mask),
        }
    return {
        "tracked_feature_columns": tracked_columns,
        "features": features,
    }


def select_feature_quality(
    *,
    feature_quality_summary: dict[str, Any] | None,
    selected_feature_columns: Iterable[str],
) -> dict[str, Any]:
    summary = dict(feature_quality_summary or {})
    features = dict(summary.get("features") or {})
    selected = _normalized_columns(selected_feature_columns)
    return {
        "tracked_feature_columns": selected,
        "features": {
            column: dict(features.get(column) or {})
            for column in selected
        },
    }


def _source_ready_masks(
    *,
    feature_frame: pd.DataFrame,
    feature_name: str,
    legacy_derivatives: pd.DataFrame,
    stablecoin_ready_mask: pd.Series,
    m3_2_ready_mask: pd.Series,
) -> tuple[pd.Series, pd.Series]:
    if feature_name in DERIVATIVES_FEATURE_SPECS:
        source_column = derivatives_feature_source_flag_column(feature_name)
        ready_column = derivatives_feature_ready_flag_column(feature_name)
        if source_column in legacy_derivatives.columns and ready_column in legacy_derivatives.columns:
            return (
                _bool_series(legacy_derivatives[source_column], index=feature_frame.index),
                _bool_series(legacy_derivatives[ready_column], index=feature_frame.index),
            )
    values = pd.to_numeric(
        feature_frame.get(feature_name, pd.Series(index=feature_frame.index, dtype="float64")),
        errors="coerce",
    )
    source_mask = values.notna()
    ready_mask = source_mask.copy()
    if feature_name != "stablecoin_flow_signal_ready" and feature_name.startswith("stablecoin_"):
        source_mask = source_mask & stablecoin_ready_mask
        ready_mask = source_mask.copy()
    elif feature_name != "m3_2_panel_ready" and feature_name.startswith("m3_2_"):
        source_mask = source_mask & m3_2_ready_mask
        ready_mask = source_mask.copy()
    elif feature_name == "capitulation_amplification_event":
        source_mask = _all_sources_present(
            feature_frame,
            ["realized_volatility_20", "quote_volume_expansion", "return_1"],
        )
        ready_mask = source_mask.copy()
    elif feature_name == "flow_persistence_against_price_20":
        source_mask = _all_sources_present(
            feature_frame,
            ["coinglass_taker_imbalance_5d_sum", "return_1"],
        )
        ready_mask = source_mask.copy()
    return source_mask.astype("bool"), ready_mask.astype("bool")


def _all_sources_present(frame: pd.DataFrame, columns: list[str]) -> pd.Series:
    if not columns:
        return pd.Series(False, index=frame.index, dtype="bool")
    masks = [
        pd.to_numeric(frame.get(column, pd.Series(index=frame.index, dtype="float64")), errors="coerce").notna()
        for column in columns
    ]
    combined = masks[0].astype("bool")
    for mask in masks[1:]:
        combined = combined & mask.astype("bool")
    return combined.astype("bool")


def _ready_proxy_mask(
    feature_frame: pd.DataFrame,
    *,
    proxy_column: str,
    threshold: float,
) -> pd.Series:
    if proxy_column not in feature_frame.columns:
        return pd.Series(False, index=feature_frame.index, dtype="bool")
    values = pd.to_numeric(feature_frame[proxy_column], errors="coerce")
    return (values > threshold).fillna(False).astype("bool")


def _normalized_columns(columns: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for raw_column in columns:
        column = str(raw_column).strip()
        if not column or column in seen:
            continue
        seen.add(column)
        normalized.append(column)
    return sorted(normalized)


def _bool_series(values: Any, *, index: pd.Index) -> pd.Series:
    return pd.Series(values, index=index, dtype="bool").fillna(False).astype("bool")


def _bool_mask(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(False, index=frame.index, dtype="bool")
    return _bool_series(frame[column], index=frame.index)


def _fraction(mask: pd.Series) -> float | None:
    if mask.empty:
        return None
    return float(mask.astype("float64").mean())


def _subject_count_for_mask(frame: pd.DataFrame, mask: pd.Series) -> int | None:
    if frame.empty or "subject" not in frame.columns:
        return None
    active = frame.loc[mask.astype("bool"), "subject"].dropna().astype(str)
    return int(active.nunique())
