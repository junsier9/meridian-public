from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import statistics
from typing import Any

from .contracts import read_json
from .split_realization_contract import (
    resolve_split_realization_contract,
    split_boundary_contamination_total as contract_split_boundary_contamination_total,
)


ROOT = Path(__file__).resolve().parents[3]
VALIDATION_CONTRACT_PATH = ROOT / "config" / "quant_research" / "validation_contract.json"
REGIME_HOLDOUT_WINDOWS_PATH = ROOT / "config" / "quant_research" / "regime_holdout_windows.json"
VALIDATION_CONTRACT_VERSION = "quant_validation_contract.v10"
VALIDATION_CONTRACT_REQUIRED_SECTIONS = (
    "split_integrity",
    "feature_admission",
    "reproducibility",
    "factor_evidence",
    "walk_forward_assessment",
    "execution_stress",
    "regime_holdout",
)


def load_validation_contract() -> dict[str, Any]:
    return read_json(VALIDATION_CONTRACT_PATH)


def load_regime_holdout_windows() -> list[dict[str, Any]]:
    payload = read_json(REGIME_HOLDOUT_WINDOWS_PATH)
    return [dict(item) for item in payload.get("windows", []) if isinstance(item, dict)]


def required_validation_sections(contract: dict[str, Any] | None = None) -> list[str]:
    payload = contract or load_validation_contract()
    configured = [
        str(item).strip()
        for item in list(payload.get("required_sections") or [])
        if str(item).strip()
    ]
    return configured or list(VALIDATION_CONTRACT_REQUIRED_SECTIONS)


def validation_contract_reference_capital_usd(*, strategy_profile: str, contract: dict[str, Any] | None = None) -> float:
    payload = contract or load_validation_contract()
    execution_stress = dict(payload.get("execution_stress") or {})
    reference_caps = dict(execution_stress.get("reference_capital_usd_by_profile") or {})
    value = reference_caps.get(str(strategy_profile).strip(), 0.0)
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def execution_capacity_limits(contract: dict[str, Any] | None = None) -> dict[str, float]:
    payload = contract or load_validation_contract()
    execution_stress = dict(payload.get("execution_stress") or {})
    max_trade_participation_rate_max = float(execution_stress.get("max_trade_participation_rate_max", 0.005) or 0.005)
    max_inventory_participation_rate_max = float(execution_stress.get("max_inventory_participation_rate_max", 0.02) or 0.02)
    max_participation_rate_max = float(
        execution_stress.get("max_participation_rate_max", max(max_trade_participation_rate_max, max_inventory_participation_rate_max))
        or max(max_trade_participation_rate_max, max_inventory_participation_rate_max)
    )
    return {
        "max_trade_participation_rate_max": max_trade_participation_rate_max,
        "max_inventory_participation_rate_max": max_inventory_participation_rate_max,
        "max_participation_rate_max": max_participation_rate_max,
    }


def validation_contract_threshold(
    *,
    contract: dict[str, Any],
    section: str,
    field_name: str,
    default: Any,
) -> Any:
    value = dict(contract.get(section) or {}).get(field_name, default)
    if isinstance(value, dict) and "value" in value:
        return value["value"]
    return value


def walk_forward_loss_window_fraction(walk_forward: dict[str, Any]) -> float:
    windows = [item for item in list(walk_forward.get("windows") or []) if isinstance(item, dict)]
    if not windows:
        return 0.0
    loss_count = sum(1 for item in windows if float(item.get("sharpe", 0.0) or 0.0) < 0.0)
    return loss_count / len(windows)


def sharpe_anomaly_details(
    *,
    validation_metrics: dict[str, Any],
    test_metrics: dict[str, Any],
    walk_forward: dict[str, Any],
    threshold: float,
) -> dict[str, float | str] | None:
    candidates: list[tuple[str, float]] = [
        ("validation_metrics.sharpe", float(validation_metrics.get("sharpe", 0.0) or 0.0)),
        ("test_metrics.sharpe", float(test_metrics.get("sharpe", 0.0) or 0.0)),
        ("walk_forward.median_oos_sharpe", float(walk_forward.get("median_oos_sharpe", 0.0) or 0.0)),
    ]
    for index, item in enumerate(list(walk_forward.get("windows") or [])):
        if not isinstance(item, dict):
            continue
        candidates.append((f"walk_forward.windows[{index}].sharpe", float(item.get("sharpe", 0.0) or 0.0)))
        candidates.append((f"walk_forward.windows[{index}].stress_sharpe", float(item.get("stress_sharpe", 0.0) or 0.0)))
    triggered = [(metric_name, metric_value) for metric_name, metric_value in candidates if metric_value > threshold]
    if not triggered:
        return None
    metric_name, metric_value = max(triggered, key=lambda item: item[1])
    return {"metric": metric_name, "value": metric_value}


def build_split_integrity_section(
    *,
    split_realization_contract: dict[str, Any] | None = None,
    label_horizon_bars: int | None = None,
    bar_interval_ms: int | None = None,
    overlap_integrity: dict[str, Any],
    leakage_checks: dict[str, Any],
    walk_forward_boundary_contamination_total: int = 0,
) -> dict[str, Any]:
    resolved_contract = resolve_split_realization_contract(
        contract=split_realization_contract,
        shape="single_asset" if _safe_int(label_horizon_bars) > 1 else "cross_sectional",
        bar_interval_ms=bar_interval_ms,
        interval="4h" if _safe_int(label_horizon_bars) > 1 else "1d",
    )
    horizon = int(resolved_contract["target_horizon_bars"])
    interval_ms = int(resolved_contract["bar_interval_ms"])
    purge_gap_bars = int(resolved_contract["partition_gap_bars"])
    overlap_payload = dict(overlap_integrity or {})
    overlap_payload.setdefault("label_horizon_bars", horizon)
    overlap_payload.setdefault("bar_interval_ms", interval_ms)
    overlap_payload.setdefault("purge_gap_bars", purge_gap_bars)
    overlap_payload.setdefault(
        "split_boundary_contamination_counts",
        {
            "train_to_validation": {"contaminated_row_count": 0, "next_partition_start_ms": None, "samples": []},
            "validation_to_test": {"contaminated_row_count": 0, "next_partition_start_ms": None, "samples": []},
        },
    )
    backtest_realization_mismatch = dict(
        overlap_payload.get("backtest_realization_mismatch")
        or overlap_payload.get("backtest_horizon_mismatch")
        or {}
    )
    if not backtest_realization_mismatch:
        backtest_realization_mismatch = {
            "detected": False,
            "label_horizon_bars": horizon,
            "realization_step_bars": int(resolved_contract["realization_step_bars"]),
            "evaluation_step_bars": int(resolved_contract["realization_step_bars"]),
            "prediction_count": 0,
            "rebalance_count": 0,
        }
    overlap_payload["backtest_horizon_mismatch"] = dict(backtest_realization_mismatch)
    overlap_payload["backtest_realization_mismatch"] = dict(backtest_realization_mismatch)
    split_boundary_contamination_total = contract_split_boundary_contamination_total(
        counts=overlap_payload.get("split_boundary_contamination_counts")
    )
    resolved_leakage_checks = dict(leakage_checks or {})
    resolved_leakage_checks.setdefault("passed", True)
    walk_forward_total = _safe_int(walk_forward_boundary_contamination_total)
    passed = (
        bool(overlap_payload.get("passed"))
        and bool(resolved_leakage_checks.get("passed"))
        and split_boundary_contamination_total == 0
        and walk_forward_total == 0
        and not bool(backtest_realization_mismatch.get("detected"))
    )
    return {
        "label_horizon_bars": horizon,
        "bar_interval_ms": interval_ms,
        "purge_gap_bars": purge_gap_bars,
        "split_realization_contract": resolved_contract,
        "split_boundary_contamination_total": split_boundary_contamination_total,
        "walk_forward_boundary_contamination_total": walk_forward_total,
        "backtest_realization_mismatch": dict(backtest_realization_mismatch),
        "overlap_integrity": overlap_payload,
        "leakage_checks": resolved_leakage_checks,
        "passed": passed,
    }


def build_walk_forward_assessment(
    *,
    walk_forward: dict[str, Any],
    contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = contract or load_validation_contract()
    window_count = int(walk_forward.get("window_count", 0) or 0)
    median_oos_sharpe = float(walk_forward.get("median_oos_sharpe", 0.0) or 0.0)
    loss_window_fraction = float(walk_forward_loss_window_fraction(walk_forward))
    passed = (
        window_count >= int(validation_contract_threshold(contract=payload, section="walk_forward_assessment", field_name="window_count_min", default=10))
        and median_oos_sharpe >= float(validation_contract_threshold(contract=payload, section="walk_forward_assessment", field_name="median_oos_sharpe_min", default=0.8))
        and loss_window_fraction <= float(validation_contract_threshold(contract=payload, section="walk_forward_assessment", field_name="loss_window_fraction_max", default=0.2))
    )
    return {
        "window_count": window_count,
        "median_oos_sharpe": median_oos_sharpe,
        "loss_window_fraction": loss_window_fraction,
        "passed": passed,
    }


def build_execution_stress_section(
    *,
    strategy_profile: str,
    stress_test_metrics: dict[str, Any],
    walk_forward: dict[str, Any],
    execution_cost_model: dict[str, Any] | None = None,
    contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = contract or load_validation_contract()
    execution_stress = dict(payload.get("execution_stress") or {})
    windows = [item for item in list(walk_forward.get("windows") or []) if isinstance(item, dict)]
    stress_sharpes = [float(item.get("stress_sharpe", 0.0) or 0.0) for item in windows]
    trade_participation_candidates = [float(stress_test_metrics.get("max_trade_participation_rate", 0.0) or 0.0)]
    trade_participation_candidates.extend(float(item.get("stress_max_trade_participation_rate", 0.0) or 0.0) for item in windows)
    inventory_participation_candidates = [float(stress_test_metrics.get("max_inventory_participation_rate", 0.0) or 0.0)]
    inventory_participation_candidates.extend(float(item.get("stress_max_inventory_participation_rate", 0.0) or 0.0) for item in windows)
    participation_candidates = [float(stress_test_metrics.get("max_participation_rate", 0.0) or 0.0)]
    participation_candidates.extend(float(item.get("stress_max_participation_rate", 0.0) or 0.0) for item in windows)
    walk_forward_median_oos_sharpe = statistics.median(stress_sharpes) if stress_sharpes else 0.0
    max_trade_participation_rate = max(trade_participation_candidates) if trade_participation_candidates else 0.0
    max_inventory_participation_rate = max(inventory_participation_candidates) if inventory_participation_candidates else 0.0
    max_participation_rate = max(participation_candidates) if participation_candidates else 0.0
    capacity_breach_count = int(stress_test_metrics.get("capacity_breach_count", 0) or 0)
    capacity_breach_count += sum(int(item.get("stress_capacity_breach_count", 0) or 0) for item in windows)
    capacity_limits = execution_capacity_limits(payload)
    passed = (
        float(stress_test_metrics.get("net_return", 0.0) or 0.0)
        > float(execution_stress.get("test_net_return_min_exclusive", 0.0) or 0.0)
        and float(walk_forward_median_oos_sharpe)
        > float(execution_stress.get("walk_forward_median_oos_sharpe_min_exclusive", 0.0) or 0.0)
        and float(max_trade_participation_rate)
        <= float(capacity_limits["max_trade_participation_rate_max"])
        and float(max_inventory_participation_rate)
        <= float(capacity_limits["max_inventory_participation_rate_max"])
        and float(max_participation_rate)
        <= float(capacity_limits["max_participation_rate_max"])
        and capacity_breach_count == 0
    )
    return {
        "scenario": str((execution_cost_model or {}).get("scenario") or stress_test_metrics.get("scenario") or "stress"),
        "execution_cost_model": dict(execution_cost_model or stress_test_metrics.get("execution_cost_model") or {}),
        "latency_bars": int((execution_cost_model or {}).get("latency_bars") or stress_test_metrics.get("latency_bars", 0) or 0),
        "strategy_profile": str(strategy_profile).strip(),
        "reference_capital_usd": validation_contract_reference_capital_usd(
            strategy_profile=strategy_profile,
            contract=payload,
        ),
        "test_metrics": dict(stress_test_metrics or {}),
        "walk_forward_window_count": len(stress_sharpes),
        "walk_forward_median_oos_sharpe": float(walk_forward_median_oos_sharpe),
        "max_trade_participation_rate": float(max_trade_participation_rate),
        "max_inventory_participation_rate": float(max_inventory_participation_rate),
        "max_participation_rate": float(max_participation_rate),
        "capacity_breach_count": int(capacity_breach_count),
        "passed": passed,
    }


def build_regime_holdout_section(
    *,
    walk_forward: dict[str, Any],
    contract: dict[str, Any] | None = None,
    regime_windows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload = contract or load_validation_contract()
    configured_regimes = regime_windows or load_regime_holdout_windows()
    windows = [item for item in list(walk_forward.get("windows") or []) if isinstance(item, dict)]
    regimes: list[dict[str, Any]] = []
    positive_count = 0
    worst_regime_median = None
    covered_regime_count = 0
    for regime in configured_regimes:
        regime_id = str(regime.get("regime_id") or "").strip()
        start_utc = _parse_utc(str(regime.get("start_utc") or ""))
        end_utc = _parse_utc(str(regime.get("end_utc") or ""))
        matching = [
            item
            for item in windows
            if _window_overlaps_regime(
                window_start_utc=str(item.get("test_start_utc") or item.get("validation_end_utc") or ""),
                window_end_utc=str(item.get("test_end_utc") or ""),
                regime_start_utc=start_utc,
                regime_end_utc=end_utc,
            )
        ]
        sharpes = [float(item.get("sharpe", 0.0) or 0.0) for item in matching]
        median_oos_sharpe = statistics.median(sharpes) if sharpes else None
        is_positive = median_oos_sharpe is not None and median_oos_sharpe > 0.0
        if matching:
            covered_regime_count += 1
            if is_positive:
                positive_count += 1
            if median_oos_sharpe is not None and (worst_regime_median is None or median_oos_sharpe < worst_regime_median):
                worst_regime_median = median_oos_sharpe
        regimes.append(
            {
                "regime_id": regime_id,
                "start_utc": regime.get("start_utc"),
                "end_utc": regime.get("end_utc"),
                "window_count": len(matching),
                "median_oos_sharpe": median_oos_sharpe,
                "positive": is_positive,
            }
        )
    positive_regime_fraction = (positive_count / len(configured_regimes)) if configured_regimes else 0.0
    passed = (
        covered_regime_count >= int(validation_contract_threshold(contract=payload, section="regime_holdout", field_name="regime_coverage_min", default=3))
        and positive_regime_fraction >= float(validation_contract_threshold(contract=payload, section="regime_holdout", field_name="positive_regime_fraction_min", default=0.67))
        and float(worst_regime_median or -1.0)
        >= float(validation_contract_threshold(contract=payload, section="regime_holdout", field_name="worst_regime_median_oos_sharpe_min", default=-0.25))
    )
    return {
        "regimes": regimes,
        "covered_regime_count": covered_regime_count,
        "positive_regime_fraction": positive_regime_fraction,
        "worst_regime_median_oos_sharpe": worst_regime_median,
        "passed": passed,
    }


def evaluate_validation_contract(
    *,
    validation_metrics: dict[str, Any],
    test_metrics: dict[str, Any],
    walk_forward: dict[str, Any],
    split_integrity: dict[str, Any] | None,
    feature_admission: dict[str, Any] | None,
    reproducibility: dict[str, Any] | None,
    factor_evidence: dict[str, Any] | None,
    walk_forward_assessment: dict[str, Any] | None,
    execution_stress: dict[str, Any] | None,
    regime_holdout: dict[str, Any] | None,
    contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = contract or load_validation_contract()
    required_sections = required_validation_sections(payload)
    section_payloads = {
        "split_integrity": dict(split_integrity or {}),
        "feature_admission": dict(feature_admission or {}),
        "reproducibility": dict(reproducibility or {}),
        "factor_evidence": dict(factor_evidence or {}),
        "walk_forward_assessment": dict(walk_forward_assessment or {}),
        "execution_stress": dict(execution_stress or {}),
        "regime_holdout": dict(regime_holdout or {}),
    }
    required_sections_present = [
        name
        for name in required_sections
        if bool(section_payloads.get(name))
    ]
    blockers: list[dict[str, Any]] = []
    missing_sections = [name for name in required_sections if name not in required_sections_present]
    for section_name in missing_sections:
        blockers.append(
            {
                "code": "validation_contract_section_missing",
                "message": f"{section_name} is required by {VALIDATION_CONTRACT_VERSION}",
                "scope": section_name,
            }
        )

    split_section = section_payloads["split_integrity"]
    split_contract = dict(split_section.get("split_realization_contract") or {})
    split_boundary_total = _safe_int(split_section.get("split_boundary_contamination_total"))
    walk_forward_boundary_total = _safe_int(split_section.get("walk_forward_boundary_contamination_total"))
    backtest_realization_mismatch = dict(
        split_section.get("backtest_realization_mismatch")
        or split_section.get("backtest_horizon_mismatch")
        or {}
    )
    split_thresholds = dict(payload.get("split_integrity") or {})
    split_checks = [
        ("split_integrity.overlap_integrity.passed", bool(dict(split_section.get("overlap_integrity") or {}).get("passed"))),
        ("split_integrity.leakage_checks.passed", bool(dict(split_section.get("leakage_checks") or {}).get("passed"))),
        (
            "split_integrity.split_realization_contract",
            bool(split_contract) if bool(split_thresholds.get("require_split_realization_contract", True)) else True,
        ),
        ("split_integrity.label_horizon_bars", _safe_int(split_section.get("label_horizon_bars")) > 0),
        ("split_integrity.bar_interval_ms", _safe_int(split_section.get("bar_interval_ms")) > 0),
        ("split_integrity.purge_gap_bars", _safe_int(split_section.get("purge_gap_bars")) > 0),
        (
            "split_integrity.split_boundary_contamination_total",
            split_boundary_total
            <= _safe_int(split_thresholds.get("split_boundary_contamination_total_max"), fallback=0),
        ),
        (
            "split_integrity.walk_forward_boundary_contamination_total",
            walk_forward_boundary_total
            <= _safe_int(split_thresholds.get("walk_forward_boundary_contamination_total_max"), fallback=0),
        ),
        (
            "split_integrity.backtest_realization_mismatch.detected",
            not bool(backtest_realization_mismatch.get("detected")),
        ),
        ("split_integrity.passed", bool(split_section.get("passed"))),
    ]
    for field_name, passed in split_checks:
        if not passed:
            blockers.append(
                {
                    "code": "split_realization_contract_failed",
                    "message": f"{field_name} did not satisfy the validation contract",
                    "scope": "split_integrity",
                }
            )

    feature_section = section_payloads["feature_admission"]
    feature_policy = dict(feature_section.get("feature_admission_policy") or {})
    feature_selected = [
        str(item).strip()
        for item in list(feature_section.get("selected_feature_columns") or [])
        if str(item).strip()
    ]
    feature_admission_thresholds = dict(payload.get("feature_admission") or {})
    feature_checks = [
        (
            "feature_admission.feature_admission_policy",
            bool(feature_policy) if bool(feature_admission_thresholds.get("require_feature_admission_policy", True)) else True,
        ),
        (
            "feature_admission.selected_feature_columns",
            bool(feature_selected) if bool(feature_admission_thresholds.get("require_non_empty_selected_feature_columns", True)) else True,
        ),
        (
            "feature_admission.banned_proxy_columns_present",
            not bool(feature_section.get("banned_proxy_columns_present"))
            if not bool(feature_admission_thresholds.get("allow_banned_proxy_columns_in_selected", False))
            else True,
        ),
        (
            "feature_admission.unknown_numeric_columns_present",
            not bool(feature_section.get("unknown_numeric_columns_present"))
            if not bool(feature_admission_thresholds.get("allow_unknown_numeric_columns_in_selected", False))
            else True,
        ),
        (
            "feature_admission.selected_feature_columns_outside_manifest",
            not bool(feature_section.get("selected_feature_columns_outside_manifest"))
            if bool(feature_admission_thresholds.get("require_selected_feature_columns_subset_of_numeric_feature_columns", True))
            else True,
        ),
        ("feature_admission.passed", bool(feature_section.get("passed"))),
    ]
    for field_name, passed in feature_checks:
        if not passed:
            blockers.append(
                {
                    "code": "feature_admission_failed",
                    "message": f"{field_name} did not satisfy the validation contract",
                    "scope": "feature_admission",
                }
            )

    reproducibility_section = section_payloads["reproducibility"]
    reproducibility_checks = [
        ("reproducibility.source_commit_sha", bool(str(reproducibility_section.get("source_commit_sha") or "").strip())),
        ("reproducibility.dataset_fingerprint", bool(str(reproducibility_section.get("dataset_fingerprint") or "").strip())),
        ("reproducibility.feature_hash", bool(str(reproducibility_section.get("feature_hash") or "").strip())),
        ("reproducibility.dataset_manifest_path", bool(str(reproducibility_section.get("dataset_manifest_path") or "").strip())),
        ("reproducibility.feature_manifest_path", bool(str(reproducibility_section.get("feature_manifest_path") or "").strip())),
        ("reproducibility.passed", bool(reproducibility_section.get("passed"))),
    ]
    for field_name, passed in reproducibility_checks:
        if not passed:
            blockers.append(
                {
                    "code": "reproducibility_contract_failed",
                    "message": f"{field_name} did not satisfy the validation contract",
                    "scope": "reproducibility",
                }
            )

    factor_section = section_payloads["factor_evidence"]
    factor_thresholds = dict(payload.get("factor_evidence") or {})
    regime_split_results = [
        dict(item)
        for item in list(factor_section.get("regime_split_results") or [])
        if isinstance(item, dict)
    ]
    positive_regime_count = sum(1 for item in regime_split_results if bool(item.get("positive")))
    # W2-B (validation_contract v8 -> v9): denominator is sum-of-POSITIVE-quarters
    # only (not sum-of-all). See lab.py _build_factor_evidence_section comment.
    # Both sites updated together; cap raised from 0.50 to 0.65 in v9 contract.
    positive_edge_contributions = [
        float(item.get("top_minus_bottom_return", 0.0) or 0.0)
        for item in regime_split_results
        if float(item.get("top_minus_bottom_return", 0.0) or 0.0) > 0.0
    ]
    cumulative_positive_edge = sum(positive_edge_contributions)
    max_positive_contribution = max(positive_edge_contributions, default=0.0)
    concentration_ratio = (
        max_positive_contribution / cumulative_positive_edge
        if cumulative_positive_edge > 0.0
        else (1.0 if max_positive_contribution > 0.0 else 0.0)
    )
    factor_checks = [
        (
            "factor_evidence.rank_ic_mean",
            abs(float(factor_section.get("rank_ic_mean", 0.0) or 0.0))
            >= float(factor_thresholds.get("rank_ic_mean_abs_min", 0.01) or 0.01),
        ),
        (
            "factor_evidence.rank_ic_positive_rate",
            float(factor_section.get("rank_ic_positive_rate", 0.0) or 0.0)
            >= float(factor_thresholds.get("rank_ic_positive_rate_min", 0.52) or 0.52),
        ),
        (
            "factor_evidence.top_minus_bottom_return",
            float(factor_section.get("top_minus_bottom_return", 0.0) or 0.0)
            > float(factor_thresholds.get("top_minus_bottom_return_min_exclusive", 0.0) or 0.0),
        ),
        ("factor_evidence.monotonicity_passed", bool(factor_section.get("monotonicity_passed"))),
        (
            "factor_evidence.decay_curve",
            bool(dict(factor_section.get("decay_curve") or {}))
            and float(dict(factor_section.get("decay_curve") or {}).get("intended_horizon_return", 0.0) or 0.0) > 0.0,
        ),
        (
            "factor_evidence.max_trade_participation_rate",
            float(factor_section.get("max_trade_participation_rate", 0.0) or 0.0)
            <= float(factor_thresholds.get("max_trade_participation_rate_max", 0.005) or 0.005),
        ),
        (
            "factor_evidence.max_inventory_participation_rate",
            float(factor_section.get("max_inventory_participation_rate", 0.0) or 0.0)
            <= float(factor_thresholds.get("max_inventory_participation_rate_max", 0.02) or 0.02),
        ),
        (
            "factor_evidence.regime_split_results.positive_regime_count",
            positive_regime_count >= int(factor_thresholds.get("positive_quarter_count_min", 2) or 2),
        ),
        (
            "factor_evidence.regime_split_results.max_positive_contribution_ratio",
            concentration_ratio
            <= float(factor_thresholds.get("max_single_quarter_edge_contribution_ratio_max", 0.5) or 0.5),
        ),
        ("factor_evidence.passed", bool(factor_section.get("passed"))),
    ]
    for field_name, passed in factor_checks:
        if not passed:
            blockers.append(
                {
                    "code": "factor_evidence_failed",
                    "message": f"{field_name} did not satisfy the validation contract",
                    "scope": "factor_evidence",
                }
            )

    sharpe_anomaly = sharpe_anomaly_details(
        validation_metrics=validation_metrics,
        test_metrics=test_metrics,
        walk_forward=walk_forward,
        threshold=float(payload.get("sharpe_anomaly_quarantine_threshold", 5.0) or 5.0),
    )
    if sharpe_anomaly is not None:
        blockers.append(
            {
                "code": "sharpe_anomaly_detected",
                "message": (
                    f"{sharpe_anomaly['metric']}={float(sharpe_anomaly['value']):.3f} exceeds quarantine threshold "
                    f"{float(payload.get('sharpe_anomaly_quarantine_threshold', 5.0) or 5.0):.3f}"
                ),
                "scope": "validation_contract",
            }
        )

    if missing_sections:
        status = "incomplete"
    elif any(
        blocker["code"] in {
            "split_realization_contract_failed",
            "feature_admission_failed",
            "reproducibility_contract_failed",
            "factor_evidence_failed",
        }
        for blocker in blockers
    ):
        status = "failed"
    elif any(blocker["code"] == "sharpe_anomaly_detected" for blocker in blockers):
        status = "falsification_required"
    else:
        failing_sections = [
            section_name
            for section_name in ("walk_forward_assessment", "execution_stress", "regime_holdout")
            if section_payloads[section_name] and not bool(section_payloads[section_name].get("passed"))
        ]
        for section_name in failing_sections:
            blocker_code = "validation_contract_threshold_failed"
            if section_name == "execution_stress":
                execution_stress_section = section_payloads["execution_stress"]
                if (
                    int(execution_stress_section.get("capacity_breach_count", 0) or 0) > 0
                    or float(execution_stress_section.get("max_trade_participation_rate", 0.0) or 0.0)
                    > execution_capacity_limits(payload)["max_trade_participation_rate_max"]
                    or float(execution_stress_section.get("max_inventory_participation_rate", 0.0) or 0.0)
                    > execution_capacity_limits(payload)["max_inventory_participation_rate_max"]
                    or float(execution_stress_section.get("max_participation_rate", 0.0) or 0.0)
                    > execution_capacity_limits(payload)["max_participation_rate_max"]
                ):
                    blocker_code = "execution_capacity_failed"
            blockers.append(
                {
                    "code": blocker_code,
                    "message": f"{section_name} did not meet the validation contract threshold",
                    "scope": section_name,
                }
            )
        status = "passed" if not failing_sections else "failed"

    return {
        "contract_version": str(payload.get("contract_version") or VALIDATION_CONTRACT_VERSION),
        "status": status,
        "required_sections_present": required_sections_present,
        "blockers": blockers,
        "summary": {
            "split_integrity_passed": bool(split_section.get("passed")),
            "feature_admission_passed": bool(feature_section.get("passed")),
            "reproducibility_passed": bool(reproducibility_section.get("passed")),
            "selected_feature_columns_count": len(feature_selected),
            "split_boundary_contamination_total": split_boundary_total,
            "walk_forward_boundary_contamination_total": walk_forward_boundary_total,
            "backtest_realization_mismatch_detected": bool(backtest_realization_mismatch.get("detected")),
            "walk_forward_assessment_passed": bool(section_payloads["walk_forward_assessment"].get("passed")),
            "execution_stress_passed": bool(section_payloads["execution_stress"].get("passed")),
            "regime_holdout_passed": bool(section_payloads["regime_holdout"].get("passed")),
            "walk_forward_median_oos_sharpe": float(walk_forward.get("median_oos_sharpe", 0.0) or 0.0),
            "execution_stress_max_trade_participation_rate": float(section_payloads["execution_stress"].get("max_trade_participation_rate", 0.0) or 0.0),
            "execution_stress_max_inventory_participation_rate": float(section_payloads["execution_stress"].get("max_inventory_participation_rate", 0.0) or 0.0),
            "execution_stress_max_participation_rate": float(section_payloads["execution_stress"].get("max_participation_rate", 0.0) or 0.0),
            "regime_coverage_count": int(section_payloads["regime_holdout"].get("covered_regime_count", 0) or 0),
        },
    }


def validation_contract_blocker_codes(validation_contract: dict[str, Any] | None) -> list[str]:
    payload = dict(validation_contract or {})
    return [
        str(item.get("code") or "").strip()
        for item in list(payload.get("blockers") or [])
        if isinstance(item, dict) and str(item.get("code") or "").strip()
    ]


def validation_contract_missing_sections(payload: dict[str, Any]) -> list[str]:
    required_sections = required_validation_sections()
    return [
        section_name
        for section_name in required_sections
        if not isinstance(payload.get(section_name), dict) or not payload.get(section_name)
    ]


def _window_overlaps_regime(
    *,
    window_start_utc: str,
    window_end_utc: str,
    regime_start_utc: datetime,
    regime_end_utc: datetime,
) -> bool:
    if not window_start_utc or not window_end_utc:
        return False
    start = _parse_utc(window_start_utc)
    end = _parse_utc(window_end_utc)
    return start <= regime_end_utc and end >= regime_start_utc


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(fallback)
