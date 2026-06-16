from __future__ import annotations

import hashlib
from typing import Any, Callable

import pandas as pd

from .contracts import utc_now
from .execution_backtest import filter_cross_sectional_execution_frame


RESEARCH_DATASET_MANIFEST_CONTRACT_VERSION = "quant_research_dataset_manifest.v1"
DEFAULT_MINIMUM_EXECUTABLE_HISTORY_DAYS = 180
DEFAULT_MINIMUM_EXECUTABLE_SUBJECT_COVERAGE_RATIO = 0.85
PERP_EXECUTION_CONSTRAINTS = {
    "execution_venue": "perp",
    "spot_only": False,
    "long_only": False,
    "short_allowed": True,
}


def build_research_dataset_manifest_fields(
    *,
    as_of: str,
    dataset_id: str,
    dataset_profile: str,
    primary_interval: str,
    raw_panel: pd.DataFrame,
    minimum_executable_history_days: int = DEFAULT_MINIMUM_EXECUTABLE_HISTORY_DAYS,
    minimum_executable_subject_coverage_ratio: float = DEFAULT_MINIMUM_EXECUTABLE_SUBJECT_COVERAGE_RATIO,
) -> dict[str, Any]:
    subject_count = int(raw_panel["subject"].nunique()) if not raw_panel.empty and "subject" in raw_panel.columns else 0
    executable_metrics = _perp_executable_metrics(
        frame=raw_panel,
        minimum_executable_history_days=minimum_executable_history_days,
        minimum_executable_subject_coverage_ratio=minimum_executable_subject_coverage_ratio,
    )
    funding_coverage = _non_null_coverage(raw_panel, "funding_rate")
    open_interest_coverage = _non_null_coverage(raw_panel, "open_interest")
    required_sidecar_families = _required_sidecar_families(dataset_profile=dataset_profile)
    sidecar_fingerprints = _sidecar_fingerprints(raw_panel)
    missing_required_sidecar_families = [
        family for family in required_sidecar_families if family not in sidecar_fingerprints
    ]
    research_dataset = {
        "contract_version": RESEARCH_DATASET_MANIFEST_CONTRACT_VERSION,
        "generated_at_utc": utc_now(),
        "dataset_id": str(dataset_id),
        "dataset_profile": str(dataset_profile),
        "primary_interval": str(primary_interval),
        "required_sidecar_families": required_sidecar_families,
        "missing_required_sidecar_families": missing_required_sidecar_families,
        "required_sidecar_families_present": not missing_required_sidecar_families,
        "perp_executable_row_coverage": executable_metrics["row_coverage"],
        "perp_executable_subject_coverage": executable_metrics["subject_coverage"],
        "perp_executable_subject_count": executable_metrics["subject_count"],
        "funding_coverage": funding_coverage,
        "open_interest_coverage": open_interest_coverage,
        "sidecar_fingerprints": sidecar_fingerprints,
        "minimum_executable_history_days": int(minimum_executable_history_days),
        "minimum_executable_subject_coverage_ratio": float(minimum_executable_subject_coverage_ratio),
        "minimum_executable_history_subject_coverage": executable_metrics["minimum_history_subject_coverage"],
        "minimum_executable_history_passed": executable_metrics["minimum_history_passed"],
    }
    return {
        "as_of": str(as_of),
        "subject_count": subject_count,
        "research_dataset": research_dataset,
    }


def validate_research_dataset_requirements(
    *,
    research_dataset: dict[str, Any] | None,
) -> list[str]:
    resolved = dict(research_dataset or {})
    blockers: list[str] = []
    if not bool(resolved.get("required_sidecar_families_present")):
        blockers.append("research_dataset_missing_required_sidecar")
    if not bool(resolved.get("minimum_executable_history_passed")):
        blockers.append("research_dataset_minimum_executable_history_failed")
    return blockers


def scope_research_dataset_to_frame(
    *,
    research_dataset: dict[str, Any] | None,
    scoped_frame: pd.DataFrame,
    scope_kind: str = "strategy_universe",
) -> dict[str, Any]:
    resolved = dict(research_dataset or {})
    if not resolved:
        return {}
    minimum_executable_history_days = int(
        resolved.get("minimum_executable_history_days") or DEFAULT_MINIMUM_EXECUTABLE_HISTORY_DAYS
    )
    minimum_executable_subject_coverage_ratio = float(
        resolved.get("minimum_executable_subject_coverage_ratio")
        or DEFAULT_MINIMUM_EXECUTABLE_SUBJECT_COVERAGE_RATIO
    )
    executable_metrics = _perp_executable_metrics(
        frame=scoped_frame,
        minimum_executable_history_days=minimum_executable_history_days,
        minimum_executable_subject_coverage_ratio=minimum_executable_subject_coverage_ratio,
    )
    scoped_subject_count = (
        int(scoped_frame["subject"].nunique())
        if not scoped_frame.empty and "subject" in scoped_frame.columns
        else 0
    )
    scoped = dict(resolved)
    scoped["dataset_scope"] = {
        "contract_version": "quant_research_dataset_scope.v1",
        "scope_kind": str(scope_kind),
        "scope_subject_count": scoped_subject_count,
        "scope_row_count": int(len(scoped_frame)),
        "base_metrics": {
            "perp_executable_row_coverage": resolved.get("perp_executable_row_coverage"),
            "perp_executable_subject_coverage": resolved.get("perp_executable_subject_coverage"),
            "perp_executable_subject_count": resolved.get("perp_executable_subject_count"),
            "funding_coverage": resolved.get("funding_coverage"),
            "open_interest_coverage": resolved.get("open_interest_coverage"),
            "minimum_executable_history_subject_coverage": resolved.get(
                "minimum_executable_history_subject_coverage"
            ),
            "minimum_executable_history_passed": resolved.get("minimum_executable_history_passed"),
        },
    }
    scoped["perp_executable_row_coverage"] = executable_metrics["row_coverage"]
    scoped["perp_executable_subject_coverage"] = executable_metrics["subject_coverage"]
    scoped["perp_executable_subject_count"] = executable_metrics["subject_count"]
    scoped["funding_coverage"] = _non_null_coverage(scoped_frame, "funding_rate")
    scoped["open_interest_coverage"] = _non_null_coverage(scoped_frame, "open_interest")
    scoped["minimum_executable_history_subject_coverage"] = executable_metrics[
        "minimum_history_subject_coverage"
    ]
    scoped["minimum_executable_history_passed"] = executable_metrics["minimum_history_passed"]
    return scoped


def _non_null_coverage(frame: pd.DataFrame, column: str) -> float:
    if frame.empty or column not in frame.columns:
        return 0.0
    series = pd.to_numeric(frame[column], errors="coerce")
    return float(series.notna().mean()) if len(series) else 0.0


def _perp_executable_metrics(
    *,
    frame: pd.DataFrame,
    minimum_executable_history_days: int,
    minimum_executable_subject_coverage_ratio: float,
) -> dict[str, Any]:
    if frame.empty or "subject" not in frame.columns or "timestamp_ms" not in frame.columns:
        return {
            "row_coverage": 0.0,
            "subject_coverage": 0.0,
            "subject_count": 0,
            "minimum_history_subject_coverage": 0.0,
            "minimum_history_passed": False,
        }
    ordered = frame.sort_values(["timestamp_ms", "subject"]).copy()
    executable = filter_cross_sectional_execution_frame(
        frame=ordered,
        constraints=PERP_EXECUTION_CONSTRAINTS,
    )
    total_rows = max(int(len(ordered)), 1)
    total_subjects = max(int(ordered["subject"].nunique()), 1)
    executable_subject_count = int(executable["subject"].nunique()) if not executable.empty else 0
    minimum_history_subject_coverage = 0.0
    if not executable.empty:
        timestamps = pd.to_datetime(executable["timestamp_ms"], unit="ms", utc=True, errors="coerce")
        dated = executable.assign(__decision_date=timestamps.dt.date)
        history_days = dated.groupby("subject")["__decision_date"].nunique()
        subjects_meeting_history = int((history_days >= int(minimum_executable_history_days)).sum())
        minimum_history_subject_coverage = float(subjects_meeting_history / total_subjects)
    return {
        "row_coverage": float(len(executable) / total_rows),
        "subject_coverage": float(executable_subject_count / total_subjects),
        "subject_count": executable_subject_count,
        "minimum_history_subject_coverage": minimum_history_subject_coverage,
        "minimum_history_passed": minimum_history_subject_coverage >= float(minimum_executable_subject_coverage_ratio),
    }


def _required_sidecar_families(*, dataset_profile: str) -> list[str]:
    normalized = str(dataset_profile or "").strip()
    if normalized.startswith("cross_sectional"):
        return ["derivatives_core"]
    return []


def _sidecar_fingerprints(frame: pd.DataFrame) -> dict[str, str]:
    if frame.empty:
        return {}
    fingerprints: dict[str, str] = {}
    for family_name, matcher in _sidecar_family_specs():
        matched_columns = [
            column for column in frame.columns if matcher(str(column))
        ]
        if not matched_columns:
            continue
        fingerprint_frame = frame[["timestamp_ms", "subject", *matched_columns]].copy()
        fingerprints[family_name] = _sha256_dataframe_csv(
            fingerprint_frame.sort_values(["timestamp_ms", "subject"]).reset_index(drop=True)
        )
    return fingerprints


def _sidecar_family_specs() -> list[tuple[str, Callable[[str], bool]]]:
    return [
        (
            "derivatives_core",
            lambda column: column in {
                "funding_rate",
                "open_interest",
                "basis_proxy",
                "mark_price",
                "index_price",
            },
        ),
        (
            "coinglass_oi_provenance",
            lambda column: column in {
                "open_interest_value_native_usd",
                "open_interest_value_provider",
                "open_interest_value_source",
                "open_interest_value_source_interval",
                "open_interest_value_canonical_policy",
                "derived_native_formula_status",
            },
        ),
        (
            "coinglass_extended",
            lambda column: column.startswith("coinglass_"),
        ),
        (
            "intraday_context",
            lambda column: column.startswith("intraday_"),
        ),
        (
            "settlement_cycle",
            lambda column: column.startswith("settlement_cycle_"),
        ),
        (
            "stablecoin_regime",
            lambda column: column.startswith("stablecoin_"),
        ),
        (
            "m3_2_onchain",
            lambda column: column.startswith("m3_2_"),
        ),
        (
            "news_event_tape",
            lambda column: column.startswith("recent_news_") or column.startswith("news_"),
        ),
    ]


def _sha256_dataframe_csv(frame: pd.DataFrame) -> str:
    csv_payload = frame.to_csv(index=False, lineterminator="\n")
    return hashlib.sha256(csv_payload.encode("utf-8")).hexdigest()
