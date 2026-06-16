from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
QUANT_SCRIPT_DIR = ROOT / "scripts" / "quant_research"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(QUANT_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(QUANT_SCRIPT_DIR))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import analyze_v5_rw_baseline_rebalance_phase_sensitivity as v5_phase  # noqa: E402
import run_dth60_conditional_overlay_ablation as overlay_diag  # noqa: E402
import run_multiphase_factor_drawdown_ablation as factor_ablation  # noqa: E402
import run_portfolio_construction_experiment as portfolio_diag  # noqa: E402

from enhengclaw.quant_research import execution_backtest as execution_bt  # noqa: E402
from enhengclaw.quant_research.execution_backtest import filter_cross_sectional_execution_frame  # noqa: E402
from enhengclaw.quant_research.execution_cost_model import execution_venue_for_constraints  # noqa: E402
from enhengclaw.quant_research.horizon_metrics import SHARPE_METRIC_CONVENTION_VERSION  # noqa: E402
from enhengclaw.quant_research.lab import (  # noqa: E402
    QUANT_ARTIFACTS_ROOT,
    _apply_universe_filter,
    _experiment_directory_name,
    _resolved_execution_cost_models,
)
from enhengclaw.quant_research.overlap_integrity import walk_forward_split_with_purge  # noqa: E402
from enhengclaw.quant_research.split_realization_contract import (  # noqa: E402
    realization_step_bars as split_contract_realization_step_bars,
    resolve_split_realization_contract,
)
from enhengclaw.quant_research.validation_contract import (  # noqa: E402
    execution_capacity_limits,
    validation_contract_reference_capital_usd,
)


CONTRACT_VERSION = "quant_m3_1_options_surface_overlay_ablation.v1"
DEFAULT_AS_OF = "2026-06-13"
BASELINE_LABEL = "v5_rw_bridge_no_overlay_h10d"
EFFECTIVE_BASELINE_LABEL = "v5_rw_bridge_no_overlay_h10d:multiphase_10_sleeve"
BASELINE_EXPERIMENT_ID = "2026-04-29-xs_alpha_ontology_v5_rw_bridge_no_overlay_lsk3_g_v2_h10d"
BASELINE_VARIANT_LABEL = "baseline_no_options_surface_overlay"
CANDIDATE_LABEL = "m3_1_options_surface_top2_context_throttle_v0"
H10D_VALIDATION_CONTRACT_PATH = ROOT / "config" / "quant_research" / "validation_contract_h10d.json"
DEFAULT_OUTPUT_PARENT = ROOT / "artifacts" / "quant_research" / "factor_reports"
DEFAULT_OPTIONS_PANEL = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "options_surface"
    / DEFAULT_AS_OF
    / "tardis_deribit_options_surface_features.csv"
)
DEFAULT_CONTEXT_REPORT = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "factor_reports"
    / DEFAULT_AS_OF
    / "m3_1_options_surface_overlay_context_report_card.json"
)
DEFAULT_ACTIVE_H10D_REGISTRY = ROOT / "config" / "quant_research" / "active_h10d_registry.json"
DEFAULT_PREREG_DOC = (
    ROOT
    / "docs"
    / "quant_research"
    / "03_alpha_branches"
    / "m3_1_options_surface_overlay_preregistration_2026_06_13.md"
)

REQUIRED_OPTION_SUBJECTS = ("BTC", "ETH")
TRIGGER_COLUMNS = ("iv_rv_spread", "iv_term_slope", "dealer_gamma_proxy", "vanna_charm_window")
OBSERVATION_ONLY_COLUMNS = ("iv_25d_skew_residual",)
FROZEN_MULTIPLIER = 0.75
FAIL_OPEN_MULTIPLIER = 1.0
MAX_NON_PATHOLOGICAL_TRIGGER_FRACTION = 0.50


VARIANTS: tuple[dict[str, Any], ...] = (
    {
        "label": BASELINE_VARIANT_LABEL,
        "kind": "baseline",
        "portfolio_target_multiplier": 1.0,
        "description": "No options-surface overlay.",
    },
    {
        "label": CANDIDATE_LABEL,
        "kind": "options_surface_portfolio_throttle",
        "portfolio_target_multiplier": FROZEN_MULTIPLIER,
        "description": "Frozen M3.1 BTC/ETH options-surface top2 context throttle.",
    },
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the preregistered M3.1 options-surface portfolio-throttle A/B "
            "under the current v5_rw 10-sleeve h10d research baseline."
        )
    )
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--baseline-experiment-id", default=BASELINE_EXPERIMENT_ID)
    parser.add_argument("--artifacts-root", type=Path, default=QUANT_ARTIFACTS_ROOT)
    parser.add_argument("--validation-contract", type=Path, default=H10D_VALIDATION_CONTRACT_PATH)
    parser.add_argument("--options-panel", type=Path, default=None)
    parser.add_argument("--context-report", type=Path, default=None)
    parser.add_argument("--active-h10d-registry", type=Path, default=DEFAULT_ACTIVE_H10D_REGISTRY)
    parser.add_argument("--preregistration-doc", type=Path, default=DEFAULT_PREREG_DOC)
    parser.add_argument("--holdout-start", default="2025-10-01")
    parser.add_argument("--exclude-first-context-dates", type=int, default=30)
    parser.add_argument("--output-root", type=Path, default=None)
    return parser.parse_args()


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def json_safe(value: Any) -> Any:
    return factor_ablation.json_safe(value)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    factor_ablation.write_json(path, payload)


def read_json(path: Path) -> dict[str, Any]:
    return dict(json.loads(path.read_text(encoding="utf-8")))


def _sha256_or_none(path: Path | None) -> str | None:
    if path is None or not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_default_options_panel(as_of: str) -> Path:
    if as_of == DEFAULT_AS_OF:
        return DEFAULT_OPTIONS_PANEL
    return ROOT / "artifacts" / "quant_research" / "options_surface" / as_of / "tardis_deribit_options_surface_features.csv"


def _resolve_default_context_report(as_of: str) -> Path:
    if as_of == DEFAULT_AS_OF:
        return DEFAULT_CONTEXT_REPORT
    return (
        ROOT
        / "artifacts"
        / "quant_research"
        / "factor_reports"
        / as_of
        / "m3_1_options_surface_overlay_context_report_card.json"
    )


def _active_manifest_path(context_report: dict[str, Any]) -> Path | None:
    path_raw = dict(context_report.get("inputs") or {}).get("active_manifest_path")
    if not path_raw:
        return None
    return Path(str(path_raw))


def _assert_context_report_gate(context_report: dict[str, Any]) -> None:
    decision = dict(context_report.get("decision") or {})
    blockers: list[str] = []
    if not bool(decision.get("overlay_context_research_allowed")):
        blockers.append("overlay_context_research_allowed_not_true")
    if bool(decision.get("manifest_mutation_authorized")):
        blockers.append("manifest_mutation_authorized_true")
    if bool(decision.get("v1_admission_policy_mutation_authorized")):
        blockers.append("v1_admission_policy_mutation_authorized_true")
    if bool(decision.get("live_or_timer_overlay_activation_authorized")):
        blockers.append("live_or_timer_overlay_activation_authorized_true")
    if blockers:
        raise RuntimeError(f"context report does not authorize report-only ablation: {blockers}")


def _date_from_ms(timestamp_ms: int | float) -> str:
    return pd.to_datetime(int(timestamp_ms), unit="ms", utc=True).date().isoformat()


def _date_series_from_timestamp_ms(series: pd.Series) -> pd.Series:
    return pd.to_datetime(pd.to_numeric(series, errors="coerce"), unit="ms", utc=True).dt.date.astype(str)


def _normalise_subject(value: Any) -> str:
    text = str(value or "").strip().upper()
    for suffix in ("USDT", "USD", "-PERP", "PERP"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
    return text


def _bool_series(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False).astype(bool)
    return series.astype(str).str.strip().str.lower().isin({"true", "1", "yes", "y"})


def _safe_quantile(series: pd.Series, quantile: float) -> float | None:
    cleaned = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if cleaned.empty:
        return None
    value = float(cleaned.quantile(float(quantile)))
    return value if math.isfinite(value) else None


def build_top2_options_context(options_panel: pd.DataFrame) -> pd.DataFrame:
    required = {"subject", "decision_date_utc", *TRIGGER_COLUMNS, *OBSERVATION_ONLY_COLUMNS}
    missing = sorted(required - set(options_panel.columns))
    if missing:
        raise RuntimeError(f"options panel missing required columns: {missing}")

    working = options_panel.copy()
    working["subject"] = working["subject"].map(_normalise_subject)
    working = working.loc[working["subject"].isin(REQUIRED_OPTION_SUBJECTS)].copy()
    working["decision_date_utc"] = pd.to_datetime(working["decision_date_utc"], utc=True, errors="coerce").dt.date.astype(str)
    ready_column = "m3_1_options_surface_panel_ready"
    if ready_column in working.columns:
        working["row_ready"] = _bool_series(working[ready_column])
    else:
        working["row_ready"] = working[list(TRIGGER_COLUMNS)].apply(pd.to_numeric, errors="coerce").notna().all(axis=1)
    for column in (*TRIGGER_COLUMNS, *OBSERVATION_ONLY_COLUMNS):
        working[column] = pd.to_numeric(working[column], errors="coerce")

    rows: list[dict[str, Any]] = []
    for decision_date, group in working.sort_values(["decision_date_utc", "subject"]).groupby("decision_date_utc"):
        subject_rows = group.drop_duplicates("subject", keep="last").set_index("subject")
        required_present = [subject in subject_rows.index for subject in REQUIRED_OPTION_SUBJECTS]
        ready_subjects = [
            bool(subject_rows.loc[subject, "row_ready"]) if subject in subject_rows.index else False
            for subject in REQUIRED_OPTION_SUBJECTS
        ]
        required_values = subject_rows.reindex(REQUIRED_OPTION_SUBJECTS)
        trigger_ready = bool(required_values[list(TRIGGER_COLUMNS)].notna().to_numpy().all())
        context_ready = bool(all(required_present) and all(ready_subjects) and trigger_ready)
        rows.append(
            {
                "decision_date_utc": str(decision_date),
                "subject_count": int(subject_rows.shape[0]),
                "required_subject_count": int(sum(required_present)),
                "ready_required_subject_count": int(sum(ready_subjects)),
                "context_ready": context_ready,
                "top2_iv_rv_spread_median": _nan_to_none(required_values["iv_rv_spread"].median()),
                "top2_iv_term_slope_min": _nan_to_none(required_values["iv_term_slope"].min()),
                "top2_abs_dealer_gamma_max": _nan_to_none(required_values["dealer_gamma_proxy"].abs().max()),
                "top2_vanna_charm_max": _nan_to_none(required_values["vanna_charm_window"].max()),
                "top2_iv_25d_skew_residual_median_observation_only": _nan_to_none(
                    required_values["iv_25d_skew_residual"].median()
                ),
            }
        )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values("decision_date_utc").reset_index(drop=True)


def _nan_to_none(value: Any) -> float | None:
    try:
        resolved = float(value)
    except (TypeError, ValueError):
        return None
    return resolved if math.isfinite(resolved) else None


def train_thresholds_for_window(train_df: pd.DataFrame, context: pd.DataFrame) -> dict[str, Any]:
    if context.empty:
        return {
            "status": "no_options_context",
            "train_context_day_count": 0,
            "iv_rv_spread_q90": None,
            "iv_term_slope_q10": None,
            "abs_dealer_gamma_q90": None,
            "vanna_charm_q90": None,
        }
    train_dates = set(_date_series_from_timestamp_ms(train_df["timestamp_ms"]).dropna().tolist())
    train_context = context.loc[context["decision_date_utc"].isin(train_dates)].copy()
    ready = train_context.loc[train_context["context_ready"].fillna(False).astype(bool)].copy()
    thresholds = {
        "status": "ok" if not ready.empty else "no_ready_train_context",
        "train_context_day_count": int(train_context.shape[0]),
        "train_ready_context_day_count": int(ready.shape[0]),
        "train_context_date_start": str(train_context["decision_date_utc"].min()) if not train_context.empty else None,
        "train_context_date_end": str(train_context["decision_date_utc"].max()) if not train_context.empty else None,
        "train_ready_context_date_start": str(ready["decision_date_utc"].min()) if not ready.empty else None,
        "train_ready_context_date_end": str(ready["decision_date_utc"].max()) if not ready.empty else None,
        "iv_rv_spread_q90": _safe_quantile(ready["top2_iv_rv_spread_median"], 0.90),
        "iv_term_slope_q10": _safe_quantile(ready["top2_iv_term_slope_min"], 0.10),
        "abs_dealer_gamma_q90": _safe_quantile(ready["top2_abs_dealer_gamma_max"], 0.90),
        "vanna_charm_q90": _safe_quantile(ready["top2_vanna_charm_max"], 0.90),
    }
    required = ("iv_rv_spread_q90", "iv_term_slope_q10", "abs_dealer_gamma_q90", "vanna_charm_q90")
    if thresholds["status"] == "ok" and any(thresholds[key] is None for key in required):
        thresholds["status"] = "incomplete_train_thresholds"
    return thresholds


def options_overlay_lookup(
    *,
    decision_timestamp_ms: int,
    context_by_date: dict[str, dict[str, Any]],
    thresholds: dict[str, Any],
    variant_label: str,
) -> dict[str, Any]:
    decision_date = _date_from_ms(decision_timestamp_ms)
    base = {
        "decision_timestamp_ms": int(decision_timestamp_ms),
        "decision_date_utc": decision_date,
        "options_context_available": False,
        "options_context_ready": False,
        "options_overlay_triggered": False,
        "vol_stress_trigger": False,
        "gamma_expiry_trigger": False,
        "portfolio_target_multiplier": FAIL_OPEN_MULTIPLIER,
        "overlay_reason": "baseline_or_fail_open",
    }
    if variant_label == BASELINE_VARIANT_LABEL:
        base["overlay_reason"] = "baseline"
        return base
    if thresholds.get("status") != "ok":
        base["overlay_reason"] = f"fail_open_{thresholds.get('status')}"
        return base
    row = context_by_date.get(decision_date)
    if not row:
        base["overlay_reason"] = "fail_open_missing_options_context"
        return base
    base["options_context_available"] = True
    base["options_context_ready"] = bool(row.get("context_ready"))
    if not base["options_context_ready"]:
        base["overlay_reason"] = "fail_open_options_context_not_ready"
        return base

    iv_rv = _float_or_none(row.get("top2_iv_rv_spread_median"))
    term = _float_or_none(row.get("top2_iv_term_slope_min"))
    gamma = _float_or_none(row.get("top2_abs_dealer_gamma_max"))
    vanna = _float_or_none(row.get("top2_vanna_charm_max"))
    if any(value is None for value in (iv_rv, term, gamma, vanna)):
        base["overlay_reason"] = "fail_open_options_context_incomplete"
        return base

    vol_stress = bool(iv_rv >= float(thresholds["iv_rv_spread_q90"]) and term <= float(thresholds["iv_term_slope_q10"]))
    gamma_expiry = bool(
        gamma >= float(thresholds["abs_dealer_gamma_q90"])
        and vanna >= float(thresholds["vanna_charm_q90"])
    )
    triggered = vol_stress or gamma_expiry
    base.update(
        {
            "vol_stress_trigger": vol_stress,
            "gamma_expiry_trigger": gamma_expiry,
            "options_overlay_triggered": triggered,
            "portfolio_target_multiplier": FROZEN_MULTIPLIER if triggered else FAIL_OPEN_MULTIPLIER,
            "overlay_reason": "triggered" if triggered else "ready_not_triggered",
        }
    )
    return base


def _float_or_none(value: Any) -> float | None:
    try:
        resolved = float(value)
    except (TypeError, ValueError):
        return None
    return resolved if math.isfinite(resolved) else None


def backtest_cross_sectional_with_options_overlay(
    *,
    frame: pd.DataFrame,
    constraints: dict[str, Any],
    split_realization_contract: dict[str, Any],
    execution_cost_model: dict[str, Any],
    reference_capital_usd: float | None,
    capacity_limits: dict[str, float] | None,
    overlay_lookup: Callable[[int], dict[str, Any]],
    include_periods: bool = False,
) -> dict[str, Any]:
    execution_venue = execution_venue_for_constraints(constraints)
    execution_frame = filter_cross_sectional_execution_frame(frame=frame, constraints=constraints)
    if execution_frame.empty:
        return execution_bt._empty_metrics(
            execution_cost_model=execution_cost_model,
            execution_venue=execution_venue,
        )
    ordered = execution_frame.sort_values(["timestamp_ms", "subject"]).copy()
    evaluation_step_bars = max(split_contract_realization_step_bars(split_realization_contract), 1)
    timestamps = sorted(int(item) for item in ordered["timestamp_ms"].drop_duplicates().tolist())
    decision_timestamp_indices = list(range(0, len(timestamps), evaluation_step_bars))
    previous_weights: dict[str, float] = {}
    periods: list[dict[str, Any]] = []
    trade_count = 0
    data_gap_blockers: set[str] = set()
    latency_bars = int(execution_cost_model["latency_bars"])
    grouped = {timestamp: group.copy() for timestamp, group in ordered.groupby("timestamp_ms")}

    for decision_offset, timestamp_offset in enumerate(decision_timestamp_indices):
        fill_offset = timestamp_offset + latency_bars
        if fill_offset >= len(timestamps):
            break
        decision_timestamp = int(timestamps[timestamp_offset])
        fill_group = grouped[timestamps[fill_offset]]
        next_fill_offset = execution_bt._next_fill_offset(
            timestamp_count=len(timestamps),
            decision_timestamp_indices=decision_timestamp_indices,
            decision_offset=decision_offset,
            latency_bars=latency_bars,
        )
        exit_timestamp = timestamps[next_fill_offset] if next_fill_offset is not None else timestamps[-1]
        hold_slice = ordered.loc[
            (ordered["timestamp_ms"] >= int(fill_group["timestamp_ms"].iloc[0]))
            & (ordered["timestamp_ms"] < int(exit_timestamp))
        ].copy()
        overlay_state = overlay_lookup(decision_timestamp)
        multiplier = float(overlay_state.get("portfolio_target_multiplier", 1.0) or 1.0)
        external_multiplier = multiplier if multiplier < 1.0 else None
        previous_weights, period = execution_bt._cross_sectional_period(
            decision_group=grouped[decision_timestamp],
            fill_group=fill_group,
            exit_group=grouped[exit_timestamp],
            hold_slice=hold_slice,
            previous_weights=previous_weights,
            constraints=constraints,
            execution_venue=execution_venue,
            execution_cost_model=execution_cost_model,
            reference_capital_usd=reference_capital_usd,
            capacity_limits=capacity_limits,
            external_throttle_multiplier=external_multiplier,
        )
        period.update(
            {
                "decision_timestamp_ms": decision_timestamp,
                "decision_date_utc": _date_from_ms(decision_timestamp),
                "portfolio_target_multiplier": multiplier,
                "options_overlay_triggered": int(bool(overlay_state.get("options_overlay_triggered"))),
                "vol_stress_trigger": int(bool(overlay_state.get("vol_stress_trigger"))),
                "gamma_expiry_trigger": int(bool(overlay_state.get("gamma_expiry_trigger"))),
                "options_context_available": int(bool(overlay_state.get("options_context_available"))),
                "options_context_ready": int(bool(overlay_state.get("options_context_ready"))),
                "options_overlay_reason": str(overlay_state.get("overlay_reason") or ""),
            }
        )
        if float(period["turnover"]) > 0.0:
            trade_count += 1
        data_gap_blockers.update(str(item) for item in list(period.get("data_gap_blockers") or []))
        periods.append(period)

    return execution_bt._aggregate_periods(
        periods=periods,
        periods_per_year=execution_bt._periods_per_year(
            bar_interval_ms=int(split_realization_contract["bar_interval_ms"]),
            evaluation_step_bars=evaluation_step_bars,
        ),
        trade_count=trade_count,
        rebalance_count=len(periods),
        evaluation_step_bars=evaluation_step_bars,
        execution_cost_model=execution_cost_model,
        execution_venue=execution_venue,
        data_gap_blockers=sorted(data_gap_blockers),
        include_periods=include_periods,
    )


def period_frame_from_metrics(*, label: str, phase: int, window_index: int, metrics: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for period in list(metrics.get("periods") or []):
        timestamp_ms = int(period["timestamp_ms"])
        row = {
            "candidate_label": label,
            "window_index": int(window_index),
            "phase_offset_days": int(phase),
            "timestamp_ms": timestamp_ms,
            "timestamp_utc": pd.to_datetime(timestamp_ms, unit="ms", utc=True).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "decision_timestamp_ms": int(period.get("decision_timestamp_ms", timestamp_ms)),
            "decision_date_utc": str(period.get("decision_date_utc") or _date_from_ms(timestamp_ms)),
        }
        for column in (
            "net_period_return",
            "gross_return_before_costs",
            "fee_cost_return",
            "slippage_cost_return",
            "funding_cost_return",
            "borrow_cost_return",
            "turnover",
            "trade_notional_usd",
            "trade_participation_rate",
            "inventory_participation_rate",
            "max_participation_rate",
            "available_quote_volume_usd",
            "portfolio_target_multiplier",
        ):
            row[column] = float(period.get(column, 0.0) or 0.0)
        for column in (
            "options_overlay_triggered",
            "vol_stress_trigger",
            "gamma_expiry_trigger",
            "options_context_available",
            "options_context_ready",
        ):
            row[column] = int(period.get(column, 0) or 0)
        row["options_overlay_reason"] = str(period.get("options_overlay_reason") or "")
        row["capacity_breach_count"] = int(period.get("capacity_breach_count", 0) or 0)
        rows.append(row)
    frame = pd.DataFrame.from_records(rows)
    if frame.empty:
        return frame
    return frame.sort_values(["timestamp_ms", "phase_offset_days"]).reset_index(drop=True)


def _period_overlay_stats(metrics: dict[str, Any]) -> dict[str, Any]:
    periods = list(metrics.get("periods") or [])
    if not periods:
        return {
            "overlay_decision_count": 0,
            "overlay_triggered_decision_count": 0,
            "overlay_triggered_decision_fraction": 0.0,
            "context_available_decision_count": 0,
            "context_ready_decision_count": 0,
            "vol_stress_trigger_count": 0,
            "gamma_expiry_trigger_count": 0,
            "average_portfolio_target_multiplier": 1.0,
        }
    trigger = [int(item.get("options_overlay_triggered", 0) or 0) for item in periods]
    available = [int(item.get("options_context_available", 0) or 0) for item in periods]
    ready = [int(item.get("options_context_ready", 0) or 0) for item in periods]
    vol = [int(item.get("vol_stress_trigger", 0) or 0) for item in periods]
    gamma = [int(item.get("gamma_expiry_trigger", 0) or 0) for item in periods]
    multipliers = [float(item.get("portfolio_target_multiplier", 1.0) or 1.0) for item in periods]
    return {
        "overlay_decision_count": int(len(periods)),
        "overlay_triggered_decision_count": int(sum(trigger)),
        "overlay_triggered_decision_fraction": float(sum(trigger) / len(periods)),
        "context_available_decision_count": int(sum(available)),
        "context_ready_decision_count": int(sum(ready)),
        "vol_stress_trigger_count": int(sum(vol)),
        "gamma_expiry_trigger_count": int(sum(gamma)),
        "average_portfolio_target_multiplier": float(np.mean(multipliers)),
    }


def _slice_periods(periods: pd.DataFrame, *, slice_name: str, holdout_start: str, first_context_exclusion_end: str | None) -> pd.DataFrame:
    if periods.empty:
        return periods.copy()
    timestamps = pd.to_datetime(periods["timestamp_ms"], unit="ms", utc=True)
    if slice_name == "full_oos":
        return periods.copy()
    if slice_name == "untouched_holdout":
        return periods.loc[timestamps.ge(pd.Timestamp(holdout_start, tz="UTC"))].copy()
    if slice_name == "exclude_first_context_dates":
        if not first_context_exclusion_end:
            return periods.iloc[0:0].copy()
        return periods.loc[timestamps.dt.date.astype(str).gt(first_context_exclusion_end)].copy()
    raise ValueError(f"unknown slice: {slice_name}")


def _metrics_for_slice(periods: pd.DataFrame, *, split_contract: dict[str, Any]) -> dict[str, Any]:
    metrics = overlay_diag.full_metrics(periods, split_contract=split_contract)
    return {
        "period_count": int(metrics.get("period_count", 0)),
        "cumulative_return": float(metrics.get("cumulative_return", 0.0) or 0.0),
        "h10d_equivalent_sharpe": float(metrics.get("h10d_equivalent_sharpe", 0.0) or 0.0),
        "observed_frequency_sharpe_deprecated": float(metrics.get("observed_frequency_sharpe_deprecated", 0.0) or 0.0),
        "max_drawdown": float(metrics.get("max_drawdown", 0.0) or 0.0),
        "turnover_total": float(metrics.get("turnover_total", 0.0) or 0.0),
        "max_trade_participation_rate": float(metrics.get("max_trade_participation_rate", 0.0) or 0.0),
        "max_inventory_participation_rate": float(metrics.get("max_inventory_participation_rate", 0.0) or 0.0),
        "capacity_breach_count": int(metrics.get("capacity_breach_count", 0) or 0),
    }


def build_summary(
    *,
    periods_by_label: dict[str, pd.DataFrame],
    window_rows: pd.DataFrame,
    split_contract: dict[str, Any],
    holdout_start: str,
    first_context_exclusion_end: str | None,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    definitions_by_label = {str(item["label"]): dict(item) for item in VARIANTS}
    for label, definition in definitions_by_label.items():
        periods = periods_by_label.get(label, pd.DataFrame())
        window_subset = window_rows.loc[window_rows["label"].eq(label)].copy() if not window_rows.empty else pd.DataFrame()
        overlay_count = int(pd.to_numeric(window_subset.get("overlay_decision_count"), errors="coerce").fillna(0).sum()) if not window_subset.empty else 0
        triggered_count = int(pd.to_numeric(window_subset.get("overlay_triggered_decision_count"), errors="coerce").fillna(0).sum()) if not window_subset.empty else 0
        full = _metrics_for_slice(
            _slice_periods(periods, slice_name="full_oos", holdout_start=holdout_start, first_context_exclusion_end=first_context_exclusion_end),
            split_contract=split_contract,
        )
        holdout = _metrics_for_slice(
            _slice_periods(periods, slice_name="untouched_holdout", holdout_start=holdout_start, first_context_exclusion_end=first_context_exclusion_end),
            split_contract=split_contract,
        )
        ex_first = _metrics_for_slice(
            _slice_periods(periods, slice_name="exclude_first_context_dates", holdout_start=holdout_start, first_context_exclusion_end=first_context_exclusion_end),
            split_contract=split_contract,
        )
        rows.append(
            {
                "label": label,
                "kind": str(definition["kind"]),
                "portfolio_target_multiplier_when_triggered": float(definition["portfolio_target_multiplier"]),
                "full_oos_period_count": full["period_count"],
                "full_oos_cumulative_return": full["cumulative_return"],
                "full_oos_h10d_equivalent_sharpe": full["h10d_equivalent_sharpe"],
                "full_oos_observed_frequency_sharpe_deprecated": full["observed_frequency_sharpe_deprecated"],
                "full_oos_max_drawdown": full["max_drawdown"],
                "full_oos_turnover_total": full["turnover_total"],
                "full_oos_max_trade_participation_rate": full["max_trade_participation_rate"],
                "full_oos_max_inventory_participation_rate": full["max_inventory_participation_rate"],
                "full_oos_capacity_breach_count": full["capacity_breach_count"],
                "holdout_start": holdout_start,
                "holdout_period_count": holdout["period_count"],
                "holdout_cumulative_return": holdout["cumulative_return"],
                "holdout_h10d_equivalent_sharpe": holdout["h10d_equivalent_sharpe"],
                "holdout_max_drawdown": holdout["max_drawdown"],
                "holdout_capacity_breach_count": holdout["capacity_breach_count"],
                "exclude_first_context_dates_end": first_context_exclusion_end,
                "exclude_first_context_period_count": ex_first["period_count"],
                "exclude_first_context_cumulative_return": ex_first["cumulative_return"],
                "exclude_first_context_h10d_equivalent_sharpe": ex_first["h10d_equivalent_sharpe"],
                "exclude_first_context_max_drawdown": ex_first["max_drawdown"],
                "overlay_decision_count": overlay_count,
                "overlay_triggered_decision_count": triggered_count,
                "overlay_triggered_decision_fraction": float(triggered_count / overlay_count) if overlay_count else 0.0,
                "context_available_decision_count": int(pd.to_numeric(window_subset.get("context_available_decision_count"), errors="coerce").fillna(0).sum()) if not window_subset.empty else 0,
                "context_ready_decision_count": int(pd.to_numeric(window_subset.get("context_ready_decision_count"), errors="coerce").fillna(0).sum()) if not window_subset.empty else 0,
                "vol_stress_trigger_count": int(pd.to_numeric(window_subset.get("vol_stress_trigger_count"), errors="coerce").fillna(0).sum()) if not window_subset.empty else 0,
                "gamma_expiry_trigger_count": int(pd.to_numeric(window_subset.get("gamma_expiry_trigger_count"), errors="coerce").fillna(0).sum()) if not window_subset.empty else 0,
            }
        )
    summary = pd.DataFrame(rows)
    baseline = summary.loc[summary["label"].eq(BASELINE_VARIANT_LABEL)].iloc[0]
    for column in (
        "full_oos_cumulative_return",
        "full_oos_h10d_equivalent_sharpe",
        "full_oos_max_drawdown",
        "holdout_cumulative_return",
        "holdout_h10d_equivalent_sharpe",
        "holdout_max_drawdown",
        "exclude_first_context_cumulative_return",
        "exclude_first_context_h10d_equivalent_sharpe",
        "exclude_first_context_max_drawdown",
    ):
        summary[f"delta_{column}_vs_baseline"] = pd.to_numeric(summary[column], errors="coerce") - float(baseline[column])
    return summary


def research_gate(summary: pd.DataFrame) -> dict[str, Any]:
    candidate = summary.loc[summary["label"].eq(CANDIDATE_LABEL)]
    baseline = summary.loc[summary["label"].eq(BASELINE_VARIANT_LABEL)]
    if candidate.empty or baseline.empty:
        return {"research_watch_state_allowed": False, "blockers": ["missing_baseline_or_candidate_row"]}
    row = candidate.iloc[0]
    blockers: list[str] = []
    if float(row["delta_full_oos_cumulative_return_vs_baseline"]) < -1e-12:
        blockers.append("full_oos_cumulative_return_worse_than_baseline")
    if float(row["delta_full_oos_h10d_equivalent_sharpe_vs_baseline"]) < -1e-12:
        blockers.append("full_oos_h10d_equivalent_sharpe_worse_than_baseline")
    if float(row["delta_full_oos_max_drawdown_vs_baseline"]) > 1e-12:
        blockers.append("full_oos_max_drawdown_worse_than_baseline")
    if float(row["delta_holdout_cumulative_return_vs_baseline"]) < -1e-12:
        blockers.append("holdout_cumulative_return_worse_than_baseline")
    if int(row["full_oos_capacity_breach_count"]) != 0:
        blockers.append("capacity_breach_count_nonzero")
    trigger_fraction = float(row["overlay_triggered_decision_fraction"])
    if int(row["overlay_triggered_decision_count"]) <= 0:
        blockers.append("trigger_rate_zero")
    if trigger_fraction > MAX_NON_PATHOLOGICAL_TRIGGER_FRACTION:
        blockers.append("trigger_rate_pathologically_frequent")
    if int(row["exclude_first_context_period_count"]) <= 0:
        blockers.append("exclude_first_30_context_dates_slice_empty")
    else:
        if float(row["delta_exclude_first_context_cumulative_return_vs_baseline"]) < -1e-12:
            blockers.append("exclude_first_30_context_dates_cumulative_return_worse_than_baseline")
        if float(row["delta_exclude_first_context_h10d_equivalent_sharpe_vs_baseline"]) < -1e-12:
            blockers.append("exclude_first_30_context_dates_h10d_sharpe_worse_than_baseline")
    return {
        "research_watch_state_allowed": not blockers,
        "blockers": blockers,
        "trigger_fraction": trigger_fraction,
        "max_non_pathological_trigger_fraction": MAX_NON_PATHOLOGICAL_TRIGGER_FRACTION,
    }


def render_markdown(path: Path, payload: dict[str, Any], summary: pd.DataFrame) -> None:
    candidate = summary.loc[summary["label"].eq(CANDIDATE_LABEL)].iloc[0].to_dict()
    baseline = summary.loc[summary["label"].eq(BASELINE_VARIANT_LABEL)].iloc[0].to_dict()
    lines = [
        "# M3.1 Options Surface Overlay Ablation",
        "",
        f"- Generated at UTC: `{payload['generated_at_utc']}`",
        f"- Contract: `{CONTRACT_VERSION}`",
        f"- Effective research baseline: `{payload['effective_research_baseline']}`",
        f"- Candidate: `{CANDIDATE_LABEL}`",
        f"- Research watch allowed: `{payload['decision']['research_watch_state_allowed']}`",
        f"- Blockers: `{payload['decision']['blockers']}`",
        "",
        "## Boundary",
        "",
        "- Report-only h10d overlay ablation.",
        "- No active registry, active manifest, v1 feature-admission, live, timer, or remote-runner mutation.",
        "- The overlay applies only a portfolio target multiplier after existing top/bottom selection.",
        "- F56 is reported as observation-only context and is not used in triggers.",
        "",
        "## Frozen Rule",
        "",
        "| trigger | train threshold | test condition |",
        "| --- | --- | --- |",
        "| vol_stress | q90 top2 IV-RV, q10 top2 term slope | IV-RV >= q90 and term slope <= q10 |",
        "| gamma_expiry | q90 top2 abs dealer gamma, q90 top2 vanna/charm | abs gamma >= q90 and vanna/charm >= q90 |",
        "",
        "When either trigger fires, `portfolio_target_multiplier = 0.75`; otherwise or missing context, `1.0`.",
        "",
        "## A/B Summary",
        "",
        "| label | full ret | full Sharpe | full DD | holdout ret | trigger frac | breaches |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in (baseline, candidate):
        lines.append(
            "| `{label}` | {ret:.6f} | {sharpe:.6f} | {dd:.6f} | {holdout:.6f} | {trigger:.6f} | {breaches} |".format(
                label=row["label"],
                ret=float(row["full_oos_cumulative_return"]),
                sharpe=float(row["full_oos_h10d_equivalent_sharpe"]),
                dd=float(row["full_oos_max_drawdown"]),
                holdout=float(row["holdout_cumulative_return"]),
                trigger=float(row["overlay_triggered_decision_fraction"]),
                breaches=int(row["full_oos_capacity_breach_count"]),
            )
        )
    lines.extend(
        [
            "",
            "## Candidate Deltas",
            "",
            f"- full OOS return delta: `{candidate['delta_full_oos_cumulative_return_vs_baseline']}`",
            f"- full OOS h10d-equivalent Sharpe delta: `{candidate['delta_full_oos_h10d_equivalent_sharpe_vs_baseline']}`",
            f"- full OOS max-drawdown delta: `{candidate['delta_full_oos_max_drawdown_vs_baseline']}`",
            f"- holdout return delta: `{candidate['delta_holdout_cumulative_return_vs_baseline']}`",
            f"- exclude-first-context return delta: `{candidate['delta_exclude_first_context_cumulative_return_vs_baseline']}`",
            "",
            "## Artifacts",
            "",
        ]
    )
    for key, value in sorted(dict(payload.get("artifacts") or {}).items()):
        lines.append(f"- {key}: `{value}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    as_of = str(args.as_of)
    options_panel_path = Path(args.options_panel or _resolve_default_options_panel(as_of)).resolve()
    context_report_path = Path(args.context_report or _resolve_default_context_report(as_of)).resolve()
    output_root = Path(args.output_root or (DEFAULT_OUTPUT_PARENT / as_of / "m3_1_options_surface_overlay_ablation")).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    context_report = read_json(context_report_path)
    _assert_context_report_gate(context_report)
    active_manifest_path = _active_manifest_path(context_report)
    mutation_before = {
        "active_h10d_registry_sha256_before": _sha256_or_none(Path(args.active_h10d_registry)),
        "active_manifest_sha256_before": _sha256_or_none(active_manifest_path),
    }

    options_panel = pd.read_csv(options_panel_path, low_memory=False)
    options_context = build_top2_options_context(options_panel)
    options_context_csv = output_root / "options_top2_context_daily.csv"
    options_context.to_csv(options_context_csv, index=False)
    context_dates = options_context.loc[options_context["context_ready"].fillna(False).astype(bool), "decision_date_utc"].tolist()
    first_context_exclusion_end = None
    if len(context_dates) >= int(args.exclude_first_context_dates) and int(args.exclude_first_context_dates) > 0:
        first_context_exclusion_end = str(context_dates[int(args.exclude_first_context_dates) - 1])
    context_by_date = {
        str(row["decision_date_utc"]): dict(row)
        for row in options_context.to_dict(orient="records")
    }

    experiment_root = Path(args.artifacts_root).resolve() / "experiments" / _experiment_directory_name(
        str(args.baseline_experiment_id)
    )
    spec = dict(portfolio_diag.read_json(experiment_root / "experiment_spec.json"))
    feature_manifest = dict(portfolio_diag.read_json(portfolio_diag._resolve(Path(str(spec["feature_manifest_path"])))))
    feature_path = portfolio_diag._resolve(Path(str(feature_manifest["features_path"])))
    validation_contract = dict(portfolio_diag.read_json(portfolio_diag._resolve(args.validation_contract)))
    base_execution_cost_model, _ = _resolved_execution_cost_models()
    reference_capital_usd = validation_contract_reference_capital_usd(
        strategy_profile=str(spec.get("strategy_profile") or ""),
        contract=validation_contract,
    )
    capacity_limits = execution_capacity_limits(validation_contract)
    split_contract = resolve_split_realization_contract(
        contract=dict(spec["split_realization_contract"]),
        shape="cross_sectional",
    )
    constraints = dict(spec.get("profile_constraints") or {})
    constraints["strategy_profile"] = str(spec.get("strategy_profile") or "")
    inventory_cap = float(capacity_limits["max_inventory_participation_rate_max"])
    trade_cap = float(capacity_limits["max_trade_participation_rate_max"])

    raw_frame = pd.read_csv(feature_path, low_memory=False)
    frame = _apply_universe_filter(raw_frame, universe_filter=spec.get("universe_filter"))
    frame = filter_cross_sectional_execution_frame(frame=frame, constraints=constraints)
    if frame.empty:
        raise RuntimeError("no execution-eligible rows")
    feature_columns = list(spec.get("feature_columns") or [])
    missing_features = [column for column in feature_columns if column not in frame.columns]
    if missing_features:
        raise RuntimeError(f"missing feature columns: {missing_features}")
    daily_ic_by_factor = v5_phase.build_daily_ic_by_factor(frame, feature_columns=feature_columns)

    phase_periods_by_label: dict[str, list[pd.DataFrame]] = {str(item["label"]): [] for item in VARIANTS}
    all_aggregate_period_frames: list[pd.DataFrame] = []
    window_rows: list[dict[str, Any]] = []
    threshold_rows: list[dict[str, Any]] = []

    for phase in portfolio_diag.MULTIPHASE_PHASES:
        phase_data, phase_audit = portfolio_diag._phase_frame(frame, phase_offset_days=phase)
        if phase_data.empty:
            continue
        phase_time_index = pd.to_datetime(phase_data["timestamp_ms"], unit="ms", utc=True)
        current_anchor = phase_time_index.min() + timedelta(days=120)
        final_anchor = phase_time_index.max() - timedelta(days=30)
        window_index = 0
        while current_anchor <= final_anchor:
            current_window_index = window_index
            window_index += 1
            train_end = current_anchor - timedelta(days=30)
            validation_end = current_anchor
            test_end = current_anchor + timedelta(days=30)
            train_df, validation_df, test_df = walk_forward_split_with_purge(
                frame=phase_data,
                time_col="timestamp_ms",
                train_end=train_end,
                validation_end=validation_end,
                test_end=test_end,
                split_realization_contract=split_contract,
            )
            current_anchor += timedelta(days=30)
            if train_df.empty or validation_df.empty or test_df.empty:
                continue

            train_end_ms = int(pd.to_numeric(train_df["timestamp_ms"], errors="coerce").max())
            weights = v5_phase.weights_for_train_end(
                daily_ic_by_factor=daily_ic_by_factor,
                train_end_ms=train_end_ms,
            )
            scored_test = v5_phase.score_frame(test_df, factor_weights=weights)
            thresholds = train_thresholds_for_window(train_df, options_context)
            threshold_rows.append(
                {
                    "window_index": int(current_window_index),
                    "phase_offset_days": int(phase),
                    "train_end_utc": train_end.isoformat().replace("+00:00", "Z"),
                    "validation_end_utc": validation_end.isoformat().replace("+00:00", "Z"),
                    **thresholds,
                }
            )
            test_times = pd.to_datetime(test_df["timestamp_ms"], unit="ms", utc=True)
            for definition in VARIANTS:
                label = str(definition["label"])
                metrics = backtest_cross_sectional_with_options_overlay(
                    frame=scored_test,
                    constraints=constraints,
                    split_realization_contract=split_contract,
                    execution_cost_model=base_execution_cost_model,
                    reference_capital_usd=reference_capital_usd,
                    capacity_limits=capacity_limits,
                    overlay_lookup=lambda ts, label=label, thresholds=thresholds: options_overlay_lookup(
                        decision_timestamp_ms=int(ts),
                        context_by_date=context_by_date,
                        thresholds=thresholds,
                        variant_label=label,
                    ),
                    include_periods=True,
                )
                phase_periods = period_frame_from_metrics(
                    label=label,
                    phase=phase,
                    window_index=current_window_index,
                    metrics=metrics,
                )
                if not phase_periods.empty:
                    phase_periods_by_label[label].append(phase_periods)
                window_rows.append(
                    {
                        "label": label,
                        "kind": str(definition["kind"]),
                        "window_index": int(current_window_index),
                        "phase_offset_days": int(phase),
                        "phase_start_date_utc": phase_audit.get("start_date_utc"),
                        "train_end_utc": train_end.isoformat().replace("+00:00", "Z"),
                        "validation_end_utc": validation_end.isoformat().replace("+00:00", "Z"),
                        "test_start_utc": test_times.min().isoformat().replace("+00:00", "Z"),
                        "test_end_utc": test_times.max().isoformat().replace("+00:00", "Z"),
                        "net_return": float(metrics.get("net_return", 0.0) or 0.0),
                        "max_drawdown": float(metrics.get("max_drawdown", 0.0) or 0.0),
                        "turnover": float(metrics.get("turnover", 0.0) or 0.0),
                        "period_count": int(len(metrics.get("periods") or [])),
                        **_period_overlay_stats(metrics),
                    }
                )

    periods_by_label: dict[str, pd.DataFrame] = {}
    for definition in VARIANTS:
        label = str(definition["label"])
        periods = factor_ablation.aggregate_variant_periods(
            label=label,
            sleeve_periods=phase_periods_by_label[label],
            trade_participation_cap=trade_cap,
            inventory_participation_cap=inventory_cap,
        )
        periods_by_label[label] = periods
        if not periods.empty:
            all_aggregate_period_frames.append(periods.assign(overlay_kind=str(definition["kind"])))

    window_rows_frame = pd.DataFrame(window_rows)
    summary = build_summary(
        periods_by_label=periods_by_label,
        window_rows=window_rows_frame,
        split_contract=split_contract,
        holdout_start=str(args.holdout_start),
        first_context_exclusion_end=first_context_exclusion_end,
    )
    gate = research_gate(summary)

    summary_csv = output_root / "overlay_ablation_summary.csv"
    period_returns_csv = output_root / "overlay_period_returns_long.csv"
    windows_csv = output_root / "overlay_windows.csv"
    thresholds_csv = output_root / "overlay_train_thresholds.csv"
    definitions_json = output_root / "overlay_definitions.json"
    summary.to_csv(summary_csv, index=False)
    if all_aggregate_period_frames:
        pd.concat(all_aggregate_period_frames, ignore_index=True).to_csv(period_returns_csv, index=False)
    else:
        pd.DataFrame().to_csv(period_returns_csv, index=False)
    window_rows_frame.to_csv(windows_csv, index=False)
    pd.DataFrame(threshold_rows).to_csv(thresholds_csv, index=False)
    write_json(
        definitions_json,
        {
            "contract_version": CONTRACT_VERSION,
            "variants": list(VARIANTS),
            "frozen_rule": {
                "required_subjects": list(REQUIRED_OPTION_SUBJECTS),
                "trigger_columns": list(TRIGGER_COLUMNS),
                "observation_only_columns": list(OBSERVATION_ONLY_COLUMNS),
                "portfolio_target_multiplier_when_triggered": FROZEN_MULTIPLIER,
                "missing_context_multiplier": FAIL_OPEN_MULTIPLIER,
                "train_thresholds": {
                    "iv_rv_spread_q90": "q90(top2_iv_rv_spread_median)",
                    "iv_term_slope_q10": "q10(top2_iv_term_slope_min)",
                    "abs_dealer_gamma_q90": "q90(top2_abs_dealer_gamma_max)",
                    "vanna_charm_q90": "q90(top2_vanna_charm_max)",
                },
            },
        },
    )

    mutation_after = {
        "active_h10d_registry_sha256_after": _sha256_or_none(Path(args.active_h10d_registry)),
        "active_manifest_sha256_after": _sha256_or_none(active_manifest_path),
    }
    non_mutation_audit = {
        **mutation_before,
        **mutation_after,
        "active_h10d_registry_unchanged": mutation_before["active_h10d_registry_sha256_before"]
        == mutation_after["active_h10d_registry_sha256_after"],
        "active_manifest_unchanged": mutation_before["active_manifest_sha256_before"]
        == mutation_after["active_manifest_sha256_after"],
    }

    baseline = summary.loc[summary["label"].eq(BASELINE_VARIANT_LABEL)].iloc[0].to_dict()
    candidate = summary.loc[summary["label"].eq(CANDIDATE_LABEL)].iloc[0].to_dict()
    payload = {
        "contract_version": CONTRACT_VERSION,
        "status": "computed",
        "generated_at_utc": utc_now_iso(),
        "as_of": as_of,
        "score_parent_label": BASELINE_LABEL,
        "effective_research_baseline": EFFECTIVE_BASELINE_LABEL,
        "baseline_experiment_id": str(args.baseline_experiment_id),
        "baseline_variant_label": BASELINE_VARIANT_LABEL,
        "candidate_label": CANDIDATE_LABEL,
        "inputs": {
            "options_panel_path": str(options_panel_path),
            "context_report_path": str(context_report_path),
            "preregistration_doc_path": str(Path(args.preregistration_doc).resolve()),
            "feature_path": str(feature_path),
            "experiment_root": str(experiment_root),
            "validation_contract": str(Path(args.validation_contract).resolve()),
            "active_h10d_registry": str(Path(args.active_h10d_registry).resolve()),
            "active_manifest_path": str(active_manifest_path) if active_manifest_path else None,
        },
        "context_report_decision": dict(context_report.get("decision") or {}),
        "construction": {
            "target_engine": "multiphase_equal_sleeve",
            "phase_offsets_days": list(portfolio_diag.MULTIPHASE_PHASES),
            "sleeve_weight": portfolio_diag.MULTIPHASE_SLEEVE_WEIGHT,
            "rebalance_step_bars": int(split_contract["realization_step_bars"]),
            "target_horizon_bars": int(split_contract["target_horizon_bars"]),
            "overlay_application": "portfolio_target_multiplier_after_top_bottom_selection_before_turnover_scaling",
        },
        "sharpe_metric_convention": {
            "version": SHARPE_METRIC_CONVENTION_VERSION,
            "headline_field": "full_oos_h10d_equivalent_sharpe",
            "deprecated_field": "full_oos_observed_frequency_sharpe_deprecated",
            "rule": "annualize overlapping h10d booking returns by max(target_horizon_bars, realization_step_bars), not by observed daily aggregate count",
        },
        "options_context": {
            "context_row_count": int(options_context.shape[0]),
            "context_ready_day_count": int(options_context["context_ready"].fillna(False).astype(bool).sum())
            if not options_context.empty
            else 0,
            "context_date_start": str(options_context["decision_date_utc"].min()) if not options_context.empty else None,
            "context_date_end": str(options_context["decision_date_utc"].max()) if not options_context.empty else None,
            "exclude_first_context_dates": int(args.exclude_first_context_dates),
            "exclude_first_context_dates_end": first_context_exclusion_end,
        },
        "diagnostics": {
            "execution_eligible_row_count": int(len(frame)),
            "execution_eligible_subject_count": int(frame["subject"].nunique()),
            "window_count": int(len(window_rows)),
            "threshold_window_count": int(len(threshold_rows)),
            "baseline_full_oos_cumulative_return": float(baseline["full_oos_cumulative_return"]),
            "candidate_full_oos_cumulative_return": float(candidate["full_oos_cumulative_return"]),
            "candidate_triggered_decision_count": int(candidate["overlay_triggered_decision_count"]),
            "candidate_triggered_decision_fraction": float(candidate["overlay_triggered_decision_fraction"]),
        },
        "decision": {
            **gate,
            "report_only": True,
            "active_manifest_mutation_authorized": False,
            "v1_admission_policy_mutation_authorized": False,
            "live_or_timer_overlay_activation_authorized": False,
            "score_layer_admission_allowed": False,
        },
        "non_mutation_audit": non_mutation_audit,
        "summary_rows": json_safe(summary.to_dict(orient="records")),
        "artifacts": {
            "summary_json": str(output_root / "summary.json"),
            "summary_md": str(output_root / "summary.md"),
            "overlay_ablation_summary_csv": str(summary_csv),
            "overlay_period_returns_long_csv": str(period_returns_csv),
            "overlay_windows_csv": str(windows_csv),
            "overlay_train_thresholds_csv": str(thresholds_csv),
            "options_top2_context_daily_csv": str(options_context_csv),
            "overlay_definitions_json": str(definitions_json),
        },
    }
    write_json(output_root / "summary.json", payload)
    render_markdown(output_root / "summary.md", payload, summary)
    print(
        json.dumps(
            json_safe(
                {
                    "status": "computed",
                    "research_watch_state_allowed": gate["research_watch_state_allowed"],
                    "blockers": gate["blockers"],
                    "summary_json": str(output_root / "summary.json"),
                }
            ),
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
