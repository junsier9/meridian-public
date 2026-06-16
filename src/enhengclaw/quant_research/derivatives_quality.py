from __future__ import annotations

from collections import Counter
from statistics import median
from typing import Any

import pandas as pd


INTERVAL_MS = {
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}

DERIVATIVES_FEATURE_SPECS: dict[str, dict[str, Any]] = {
    "funding_zscore_20": {
        "source_field": "funding_rate",
        "lookback_bars": 20,
        "family": "funding",
    },
    "oi_change_5": {
        "source_field": "open_interest",
        "lookback_bars": 5,
        "family": "open_interest",
    },
    "basis_zscore_20": {
        "source_field": "basis_proxy",
        "lookback_bars": 20,
        "family": "basis",
    },
}

DERIVATIVES_FAMILY_COLUMNS: dict[str, tuple[str, ...]] = {
    "funding": ("funding_rate", "funding_sample_count", "funding_zscore_20"),
    "open_interest": ("open_interest", "open_interest_value", "oi_change_5"),
    "basis": ("basis_proxy", "basis_zscore_20", "perp_close", "has_perp"),
}

DERIVATIVES_FAMILY_CANONICAL_FEATURE = {
    "funding": "funding_zscore_20",
    "open_interest": "oi_change_5",
    "basis": "basis_zscore_20",
}


def feature_source_flag_column(feature_name: str) -> str:
    return f"__derivatives_source__{feature_name}"


def feature_ready_flag_column(feature_name: str) -> str:
    return f"__derivatives_ready__{feature_name}"


def build_derivatives_provider_index(sync_summary: dict[str, Any] | None) -> dict[tuple[str, str], dict[str, Any]]:
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for item in list((sync_summary or {}).get("sync_results") or []):
        if not isinstance(item, dict) or str(item.get("status") or "").strip() != "success":
            continue
        symbol = str(item.get("symbol") or "").strip().upper()
        interval = str(item.get("interval") or "").strip()
        if symbol and interval:
            index[(symbol, interval)] = dict(item)
    return index


def summarize_dataset_derivatives_quality(
    *,
    panel: pd.DataFrame,
    interval: str,
    provider_index: dict[tuple[str, str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    working = panel.copy()
    perp_mask = _perp_mask(working)
    working = working.loc[perp_mask].copy()
    provider_records = _provider_records_for_frame(working, interval=interval, provider_index=provider_index)
    funding_mask = _field_mask(working, "funding_rate")
    open_interest_mask = _field_mask(working, "open_interest")
    return {
        "interval": interval,
        "subject_count_with_perp": int(working["subject"].nunique()) if not working.empty else 0,
        "subject_count_with_funding_rows": _subject_count_for_mask(working, funding_mask),
        "subject_count_with_open_interest_rows": _subject_count_for_mask(working, open_interest_mask),
        "row_fraction_with_funding_rate": _fraction(funding_mask),
        "row_fraction_with_open_interest": _fraction(open_interest_mask),
        "funding_coverage_days": _provider_coverage_distribution(provider_records, family="funding"),
        "open_interest_coverage_days": _provider_coverage_distribution(provider_records, family="open_interest"),
        "funding_minus_open_interest_gap_days": _provider_gap_distribution(provider_records),
        "warning_counts": _warning_counts(provider_records),
        "warning_examples": _warning_examples(provider_records),
        "provider_window": {
            "funding_coverage_days": _provider_coverage_distribution(provider_records, family="funding"),
            "open_interest_coverage_days": _provider_coverage_distribution(provider_records, family="open_interest"),
            "funding_minus_open_interest_gap_days": _provider_gap_distribution(provider_records),
        },
        "research_ready_window": {
            "row_fraction_with_funding_rate": _fraction(funding_mask),
            "row_fraction_with_open_interest": _fraction(open_interest_mask),
            "funding_row_coverage_days": _coverage_distribution_from_mask(
                working,
                mask=funding_mask,
                interval=interval,
            ),
            "open_interest_row_coverage_days": _coverage_distribution_from_mask(
                working,
                mask=open_interest_mask,
                interval=interval,
            ),
        },
    }


def summarize_feature_derivatives_quality(
    *,
    quality_frame: pd.DataFrame,
    interval: str,
    provider_index: dict[tuple[str, str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    provider_records = _provider_records_for_frame(quality_frame, interval=interval, provider_index=provider_index)
    features: dict[str, Any] = {}
    for feature_name, spec in DERIVATIVES_FEATURE_SPECS.items():
        source_mask = _bool_mask(quality_frame, feature_source_flag_column(feature_name))
        ready_mask = _bool_mask(quality_frame, feature_ready_flag_column(feature_name))
        features[feature_name] = {
            "source_field": str(spec["source_field"]),
            "lookback_bars": int(spec["lookback_bars"]),
            "row_source_fraction": _fraction(source_mask),
            "row_ready_fraction": _fraction(ready_mask),
            "subject_ready_count": _subject_count_for_mask(quality_frame, ready_mask),
            "ready_coverage_days": _coverage_distribution_from_mask(
                quality_frame,
                mask=ready_mask,
                interval=interval,
            ),
            "provider_coverage_days": _provider_coverage_distribution(
                provider_records,
                family=str(spec["family"]),
            ),
            "warning_counts": _warning_counts(provider_records, family=str(spec["family"])),
        }
    return {
        "interval": interval,
        "tracked_feature_columns": list(DERIVATIVES_FEATURE_SPECS),
        "features": features,
        "funding_minus_open_interest_gap_days": _coverage_gap_distribution_from_masks(
            quality_frame,
            left_mask=_bool_mask(quality_frame, feature_ready_flag_column("funding_zscore_20")),
            right_mask=_bool_mask(quality_frame, feature_ready_flag_column("oi_change_5")),
            interval=interval,
        ),
    }


def summarize_strategy_derivatives_quality(
    *,
    feature_frame: pd.DataFrame,
    quality_frame: pd.DataFrame | None,
    feature_columns: list[str],
    derivatives_feature_quality: dict[str, Any] | None = None,
    train_df: pd.DataFrame | None = None,
    validation_df: pd.DataFrame | None = None,
    test_df: pd.DataFrame | None = None,
    required_families: list[str] | None = None,
    split_ready_row_fraction_thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    quality = _align_quality_frame_to_feature_frame(
        feature_frame=feature_frame,
        quality_frame=quality_frame,
    )
    used_derivatives_feature_columns = [
        column
        for column in feature_columns
        if any(column in columns for columns in DERIVATIVES_FAMILY_COLUMNS.values())
    ]
    total_subject_count = int(feature_frame["subject"].nunique()) if not feature_frame.empty else 0
    split_quality_frames = {
        "train": _quality_frame_for_split(quality, train_df),
        "validation": _quality_frame_for_split(quality, validation_df),
        "test": _quality_frame_for_split(quality, test_df),
    }
    family_payloads: dict[str, dict[str, Any]] = {}
    for family in ("funding", "open_interest", "basis"):
        used_columns = [column for column in used_derivatives_feature_columns if column in DERIVATIVES_FAMILY_COLUMNS[family]]
        family_payloads[family] = _summarize_strategy_family(
            family=family,
            used_columns=used_columns,
            total_subject_count=total_subject_count,
            full_quality_frame=quality,
            split_quality_frames=split_quality_frames,
            derivatives_feature_quality=derivatives_feature_quality,
            split_ready_row_fraction_thresholds=split_ready_row_fraction_thresholds,
        )
    gap_distribution = _coverage_gap_distribution_from_masks(
        quality,
        left_mask=_family_ready_mask(
            quality,
            family="funding",
            used_columns=family_payloads["funding"]["feature_columns"],
        ),
        right_mask=_family_ready_mask(
            quality,
            family="open_interest",
            used_columns=family_payloads["open_interest"]["feature_columns"],
        ),
        interval=_infer_interval_from_feature_quality(derivatives_feature_quality, feature_frame),
    )
    warning_codes = sorted(
        {
            code
            for family in ("funding", "open_interest")
            for code in family_payloads[family].get("warning_counts", {})
            if str(code).strip()
        }
    )
    uses_derivatives_features = bool(used_derivatives_feature_columns)
    subject_panel_readiness = _subject_panel_readiness(
        feature_frame=feature_frame,
        family_payloads=family_payloads,
        required_families=required_families,
    )
    status = "not_applicable"
    if uses_derivatives_features:
        status = "warning" if warning_codes or (gap_distribution.get("median") or 0.0) > 0.0 else "ok"
    return {
        "status": status,
        "uses_derivatives_features": uses_derivatives_features,
        "used_derivatives_feature_columns": used_derivatives_feature_columns,
        "funding_family": family_payloads["funding"],
        "open_interest_family": family_payloads["open_interest"],
        "basis_family": family_payloads["basis"],
        "funding_minus_open_interest_gap_days": gap_distribution,
        "warning_codes": warning_codes,
        "subject_panel_readiness": subject_panel_readiness,
    }


def aggregate_strategy_derivatives_quality(experiments: list[dict[str, Any]]) -> dict[str, Any]:
    funding_train_values: list[float] = []
    open_interest_train_values: list[float] = []
    gap_medians: list[float] = []
    warning_examples: list[dict[str, Any]] = []
    using_count = 0
    oi_provider_cap_count = 0
    for experiment in experiments:
        if not isinstance(experiment, dict):
            continue
        quality = dict(experiment.get("derivatives_strategy_quality") or {})
        if not quality.get("uses_derivatives_features"):
            continue
        using_count += 1
        funding_family = dict(quality.get("funding_family") or {})
        open_interest_family = dict(quality.get("open_interest_family") or {})
        funding_train = funding_family.get("train_ready_row_fraction")
        open_interest_train = open_interest_family.get("train_ready_row_fraction")
        if funding_train is not None:
            funding_train_values.append(float(funding_train))
        if open_interest_train is not None:
            open_interest_train_values.append(float(open_interest_train))
        gap_distribution = dict(quality.get("funding_minus_open_interest_gap_days") or {})
        if gap_distribution.get("median") is not None:
            gap_medians.append(float(gap_distribution["median"]))
        open_interest_warnings = dict(open_interest_family.get("warning_counts") or {})
        if int(open_interest_warnings.get("open_interest_provider_latest_window_cap", 0) or 0) > 0:
            oi_provider_cap_count += 1
        warning_codes = list(quality.get("warning_codes") or [])
        if warning_codes:
            warning_examples.append(
                {
                    "experiment_id": str(experiment.get("experiment_id") or ""),
                    "strategy_id": str(experiment.get("strategy_id") or ""),
                    "warning_codes": warning_codes,
                }
            )
    return {
        "experiment_count_using_derivatives_features": using_count,
        "experiment_count_with_open_interest_provider_cap_exposure": oi_provider_cap_count,
        "funding_train_ready_row_fraction": _distribution_summary(funding_train_values),
        "open_interest_train_ready_row_fraction": _distribution_summary(open_interest_train_values),
        "funding_minus_open_interest_gap_days": _distribution_summary(gap_medians),
        "warning_examples": warning_examples[:10],
    }


def feature_derivatives_quality_highlights(feature_sets: list[dict[str, Any]]) -> dict[str, Any]:
    highlights: dict[str, Any] = {}
    for feature_set in feature_sets:
        feature_set_id = str(feature_set.get("feature_set_id") or "")
        quality = dict(feature_set.get("derivatives_feature_quality") or {})
        features = dict(quality.get("features") or {})
        if not feature_set_id:
            continue
        highlights[feature_set_id] = {
            "interval": quality.get("interval"),
            "funding_zscore_20": _feature_highlight(features.get("funding_zscore_20")),
            "oi_change_5": _feature_highlight(features.get("oi_change_5")),
            "basis_zscore_20": _feature_highlight(features.get("basis_zscore_20")),
            "funding_minus_open_interest_gap_days": dict(quality.get("funding_minus_open_interest_gap_days") or {}),
        }
    return highlights


def _feature_highlight(feature_quality: Any) -> dict[str, Any]:
    payload = dict(feature_quality or {})
    return {
        "row_source_fraction": payload.get("row_source_fraction"),
        "row_ready_fraction": payload.get("row_ready_fraction"),
        "subject_ready_count": payload.get("subject_ready_count"),
        "ready_coverage_days": dict(payload.get("ready_coverage_days") or {}),
        "warning_counts": dict(payload.get("warning_counts") or {}),
    }


def _summarize_strategy_family(
    *,
    family: str,
    used_columns: list[str],
    total_subject_count: int,
    full_quality_frame: pd.DataFrame,
    split_quality_frames: dict[str, pd.DataFrame],
    derivatives_feature_quality: dict[str, Any] | None,
    split_ready_row_fraction_thresholds: dict[str, float] | None,
) -> dict[str, Any]:
    canonical_feature = DERIVATIVES_FAMILY_CANONICAL_FEATURE[family]
    ready_mask = _family_ready_mask(full_quality_frame, family=family, used_columns=used_columns)
    feature_details = dict((derivatives_feature_quality or {}).get("features") or {})
    provider_coverage_days = dict(feature_details.get(canonical_feature, {}).get("provider_coverage_days") or {})
    warning_counts = dict(feature_details.get(canonical_feature, {}).get("warning_counts") or {})
    split_subject_readiness = {
        split_name: _split_subject_readiness(
            frame=split_quality_frames[split_name],
            family=family,
            used_columns=used_columns,
            ready_row_fraction_min=float((split_ready_row_fraction_thresholds or {}).get(split_name) or 0.0),
        )
        for split_name in ("train", "validation", "test")
    }
    return {
        "used": bool(used_columns),
        "feature_columns": used_columns,
        "train_ready_row_fraction": _fraction(
            _family_ready_mask(split_quality_frames["train"], family=family, used_columns=used_columns)
        ),
        "validation_ready_row_fraction": _fraction(
            _family_ready_mask(split_quality_frames["validation"], family=family, used_columns=used_columns)
        ),
        "test_ready_row_fraction": _fraction(
            _family_ready_mask(split_quality_frames["test"], family=family, used_columns=used_columns)
        ),
        "ready_subject_fraction": (
            _subject_count_for_mask(full_quality_frame, ready_mask) / total_subject_count
            if total_subject_count and used_columns
            else None
        ),
        "ready_coverage_days": _coverage_distribution_from_mask(
            full_quality_frame,
            mask=ready_mask,
            interval=_infer_interval_from_feature_quality(derivatives_feature_quality, full_quality_frame),
        ),
        "provider_coverage_days": provider_coverage_days,
        "warning_counts": warning_counts,
        "train_ready_subject_count": int(split_subject_readiness["train"]["ready_subject_count"]),
        "validation_ready_subject_count": int(split_subject_readiness["validation"]["ready_subject_count"]),
        "test_ready_subject_count": int(split_subject_readiness["test"]["ready_subject_count"]),
        "train_ready_subject_fraction": split_subject_readiness["train"]["ready_subject_fraction"],
        "validation_ready_subject_fraction": split_subject_readiness["validation"]["ready_subject_fraction"],
        "test_ready_subject_fraction": split_subject_readiness["test"]["ready_subject_fraction"],
        "train_ready_subjects": list(split_subject_readiness["train"]["ready_subjects"]),
        "validation_ready_subjects": list(split_subject_readiness["validation"]["ready_subjects"]),
        "test_ready_subjects": list(split_subject_readiness["test"]["ready_subjects"]),
    }


def _subject_panel_readiness(
    *,
    feature_frame: pd.DataFrame,
    family_payloads: dict[str, dict[str, Any]],
    required_families: list[str] | None,
) -> dict[str, Any]:
    all_subjects = sorted(
        {
            str(subject).strip()
            for subject in list(feature_frame.get("subject", []))
            if str(subject).strip()
        }
    )
    active_families = [
        family_name
        for family_name in list(required_families or []) or list(family_payloads)
        if dict(family_payloads.get(family_name) or {}).get("used")
    ]
    if not active_families:
        return {
            "required_families": list(required_families or []),
            "active_families": [],
            "eligible_subject_count": len(all_subjects),
            "eligible_subject_fraction": 1.0 if all_subjects else None,
            "eligible_subjects": all_subjects,
            "excluded_subject_count": 0,
            "excluded_subjects": [],
            "late_start_subjects": [],
            "split_ready_subject_count": {
                split_name: len(all_subjects)
                for split_name in ("train", "validation", "test")
            },
            "split_ready_subject_fraction": {
                split_name: (1.0 if all_subjects else None)
                for split_name in ("train", "validation", "test")
            },
            "split_ready_subjects": {
                split_name: list(all_subjects)
                for split_name in ("train", "validation", "test")
            },
        }
    split_ready_subjects: dict[str, list[str]] = {}
    for split_name in ("train", "validation", "test"):
        family_sets = [
            set(dict(family_payloads[family_name]).get(f"{split_name}_ready_subjects") or [])
            for family_name in active_families
        ]
        ready_set = set.intersection(*family_sets) if family_sets else set(all_subjects)
        split_ready_subjects[split_name] = sorted(str(subject) for subject in ready_set if str(subject).strip())
    eligible_subjects = sorted(
        set(all_subjects)
        & set(split_ready_subjects["train"])
        & set(split_ready_subjects["validation"])
        & set(split_ready_subjects["test"])
    )
    excluded_subjects = sorted(set(all_subjects) - set(eligible_subjects))
    late_start_subjects = sorted(
        set(excluded_subjects)
        & ((set(split_ready_subjects["validation"]) | set(split_ready_subjects["test"])) - set(split_ready_subjects["train"]))
    )
    return {
        "required_families": list(required_families or []),
        "active_families": active_families,
        "eligible_subject_count": len(eligible_subjects),
        "eligible_subject_fraction": (
            len(eligible_subjects) / len(all_subjects)
            if all_subjects
            else None
        ),
        "eligible_subjects": eligible_subjects,
        "excluded_subject_count": len(excluded_subjects),
        "excluded_subjects": excluded_subjects,
        "late_start_subjects": late_start_subjects,
        "split_ready_subject_count": {
            split_name: len(split_ready_subjects[split_name])
            for split_name in ("train", "validation", "test")
        },
        "split_ready_subject_fraction": {
            split_name: (
                len(split_ready_subjects[split_name]) / len(all_subjects)
                if all_subjects
                else None
            )
            for split_name in ("train", "validation", "test")
        },
        "split_ready_subjects": split_ready_subjects,
    }


def _split_subject_readiness(
    *,
    frame: pd.DataFrame,
    family: str,
    used_columns: list[str],
    ready_row_fraction_min: float,
) -> dict[str, Any]:
    if frame.empty or "subject" not in frame.columns:
        return {
            "subject_count": 0,
            "ready_subject_count": 0,
            "ready_subject_fraction": None,
            "ready_subjects": [],
        }
    ready_mask = _family_ready_mask(frame, family=family, used_columns=used_columns)
    subject_count = int(frame["subject"].nunique())
    ready_subjects: list[str] = []
    for subject, subject_frame in frame.assign(__family_ready=ready_mask).groupby("subject", sort=True):
        ready_fraction = _fraction(subject_frame["__family_ready"])
        if ready_fraction is not None and float(ready_fraction) >= float(ready_row_fraction_min):
            ready_subjects.append(str(subject))
    return {
        "subject_count": subject_count,
        "ready_subject_count": len(ready_subjects),
        "ready_subject_fraction": (
            len(ready_subjects) / subject_count
            if subject_count > 0
            else None
        ),
        "ready_subjects": ready_subjects,
    }


def _family_ready_mask(frame: pd.DataFrame, *, family: str, used_columns: list[str]) -> pd.Series:
    if frame.empty or not used_columns:
        return pd.Series(False, index=frame.index, dtype="bool")
    canonical_feature = DERIVATIVES_FAMILY_CANONICAL_FEATURE[family]
    if canonical_feature in used_columns:
        return _bool_mask(frame, feature_ready_flag_column(canonical_feature))
    if family == "funding":
        return _bool_mask(frame, feature_source_flag_column("funding_zscore_20"))
    if family == "open_interest":
        return _bool_mask(frame, feature_source_flag_column("oi_change_5"))
    return _bool_mask(frame, feature_source_flag_column("basis_zscore_20"))


def _quality_frame_for_split(quality_frame: pd.DataFrame, split_df: pd.DataFrame | None) -> pd.DataFrame:
    if quality_frame.empty or split_df is None or split_df.empty:
        return pd.DataFrame(columns=list(quality_frame.columns))
    merge_keys = [column for column in ("subject", "timestamp_ms") if column in quality_frame.columns and column in split_df.columns]
    if len(merge_keys) != 2:
        return pd.DataFrame(columns=list(quality_frame.columns))
    return split_df[merge_keys].merge(quality_frame, on=merge_keys, how="left")


def _align_quality_frame_to_feature_frame(
    *,
    feature_frame: pd.DataFrame,
    quality_frame: pd.DataFrame | None,
) -> pd.DataFrame:
    if not isinstance(quality_frame, pd.DataFrame) or quality_frame.empty:
        return pd.DataFrame()
    if feature_frame.empty:
        return pd.DataFrame(columns=list(quality_frame.columns))
    merge_keys = [
        column
        for column in ("subject", "timestamp_ms")
        if column in feature_frame.columns and column in quality_frame.columns
    ]
    if len(merge_keys) != 2:
        return quality_frame.copy()
    return (
        feature_frame[merge_keys]
        .drop_duplicates()
        .merge(quality_frame, on=merge_keys, how="left")
        .sort_values(merge_keys)
        .reset_index(drop=True)
    )


def _provider_records_for_frame(
    frame: pd.DataFrame,
    *,
    interval: str,
    provider_index: dict[tuple[str, str], dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    if provider_index is None or frame.empty or "usdm_symbol" not in frame.columns:
        return []
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    symbols = sorted(
        {
            normalized
            for normalized in (_normalize_symbol(item) for item in frame["usdm_symbol"].tolist())
            if normalized
        }
    )
    for symbol in symbols:
        if not symbol:
            continue
        key = (symbol, interval)
        if key in seen:
            continue
        seen.add(key)
        if key in provider_index:
            records.append(dict(provider_index[key]))
    return records


def _provider_coverage_distribution(provider_records: list[dict[str, Any]], *, family: str) -> dict[str, Any]:
    if family == "basis":
        return _distribution_summary([])
    field_name = "funding_rate" if family == "funding" else "open_interest"
    values: list[float] = []
    for record in provider_records:
        field_coverage = dict(record.get("field_coverage") or {})
        coverage = dict(field_coverage.get(field_name) or {})
        if coverage.get("coverage_days") is not None:
            values.append(float(coverage["coverage_days"]))
    return _distribution_summary(values)


def _provider_gap_distribution(provider_records: list[dict[str, Any]]) -> dict[str, Any]:
    values: list[float] = []
    for record in provider_records:
        field_coverage = dict(record.get("field_coverage") or {})
        funding = dict(field_coverage.get("funding_rate") or {})
        open_interest = dict(field_coverage.get("open_interest") or {})
        if funding.get("coverage_days") is None or open_interest.get("coverage_days") is None:
            continue
        values.append(float(funding["coverage_days"]) - float(open_interest["coverage_days"]))
    return _distribution_summary(values)


def _warning_counts(provider_records: list[dict[str, Any]], family: str | None = None) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for record in provider_records:
        codes = list((record.get("coverage_validation") or {}).get("warning_codes") or [])
        for code in codes:
            normalized = str(code or "").strip()
            if not normalized:
                continue
            if family == "funding" and not normalized.startswith("funding_rate_"):
                continue
            if family == "open_interest" and not normalized.startswith("open_interest_"):
                continue
            if family == "basis":
                continue
            counter[normalized] += 1
    return dict(sorted(counter.items()))


def _warning_examples(provider_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    for record in provider_records:
        codes = [str(code) for code in list((record.get("coverage_validation") or {}).get("warning_codes") or []) if str(code).strip()]
        if not codes:
            continue
        examples.append(
            {
                "symbol": str(record.get("symbol") or ""),
                "interval": str(record.get("interval") or ""),
                "warning_codes": codes,
            }
        )
    return examples[:10]


def _perp_mask(frame: pd.DataFrame) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype="bool")
    if "has_perp" in frame.columns:
        return frame["has_perp"].astype("bool")
    if "usdm_symbol" not in frame.columns:
        return pd.Series(False, index=frame.index, dtype="bool")
    return frame["usdm_symbol"].map(lambda value: bool(_normalize_symbol(value))).astype("bool")


def _field_mask(frame: pd.DataFrame, column: str) -> pd.Series:
    if frame.empty or column not in frame.columns:
        return pd.Series(False, index=frame.index, dtype="bool")
    series = frame[column]
    if column == "open_interest":
        series = series.replace(0, pd.NA)
    return series.notna().astype("bool")


def _bool_mask(frame: pd.DataFrame, column: str) -> pd.Series:
    if frame.empty or column not in frame.columns:
        return pd.Series(False, index=frame.index, dtype="bool")
    return frame[column].fillna(False).astype("bool")


def _subject_count_for_mask(frame: pd.DataFrame, mask: pd.Series) -> int:
    if frame.empty or "subject" not in frame.columns or mask.empty:
        return 0
    return int(frame.loc[mask, "subject"].nunique())


def _coverage_distribution_from_mask(frame: pd.DataFrame, *, mask: pd.Series, interval: str) -> dict[str, Any]:
    if frame.empty or mask.empty or "subject" not in frame.columns or "timestamp_ms" not in frame.columns:
        return _distribution_summary([])
    values: list[float] = []
    interval_ms = INTERVAL_MS.get(str(interval), 0)
    for _, group in frame.loc[mask].groupby("subject", sort=True):
        timestamps = [int(item) for item in group["timestamp_ms"].tolist()]
        if timestamps and interval_ms > 0:
            values.append(((max(timestamps) - min(timestamps)) + interval_ms) / 86_400_000.0)
    return _distribution_summary(values)


def _coverage_gap_distribution_from_masks(
    frame: pd.DataFrame,
    *,
    left_mask: pd.Series,
    right_mask: pd.Series,
    interval: str,
) -> dict[str, Any]:
    if frame.empty or left_mask.empty or right_mask.empty:
        return _distribution_summary([])
    left_values = _coverage_days_by_subject(frame, mask=left_mask, interval=interval)
    right_values = _coverage_days_by_subject(frame, mask=right_mask, interval=interval)
    values = [
        float(left_values[subject]) - float(right_values[subject])
        for subject in sorted(set(left_values) & set(right_values))
    ]
    return _distribution_summary(values)


def _coverage_days_by_subject(frame: pd.DataFrame, *, mask: pd.Series, interval: str) -> dict[str, float]:
    if frame.empty or mask.empty or "subject" not in frame.columns or "timestamp_ms" not in frame.columns:
        return {}
    interval_ms = INTERVAL_MS.get(str(interval), 0)
    if interval_ms <= 0:
        return {}
    values: dict[str, float] = {}
    for subject, group in frame.loc[mask].groupby("subject", sort=True):
        timestamps = [int(item) for item in group["timestamp_ms"].tolist()]
        if timestamps:
            values[str(subject)] = ((max(timestamps) - min(timestamps)) + interval_ms) / 86_400_000.0
    return values


def _distribution_summary(values: list[float]) -> dict[str, Any]:
    if not values:
        return {
            "count": 0,
            "min": None,
            "median": None,
            "max": None,
        }
    return {
        "count": len(values),
        "min": min(values),
        "median": median(values),
        "max": max(values),
    }


def _fraction(mask: pd.Series) -> float | None:
    if mask.empty:
        return None
    return float(mask.fillna(False).astype("bool").sum() / len(mask))


def _normalize_symbol(value: Any) -> str | None:
    normalized = str(value or "").strip().upper()
    if normalized in {"", "0", "NONE", "NAN"}:
        return None
    return normalized


def _infer_interval_from_feature_quality(
    feature_quality: dict[str, Any] | None,
    feature_frame: pd.DataFrame,
) -> str:
    interval = str((feature_quality or {}).get("interval") or "").strip()
    if interval:
        return interval
    if "date_utc" in feature_frame.columns:
        return "1d"
    return "4h"
