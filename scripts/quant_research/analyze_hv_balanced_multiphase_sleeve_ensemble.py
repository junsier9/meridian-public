from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import analyze_hv_balanced_10d_vs_20d_position_attribution as interval_attribution  # noqa: E402
import analyze_hv_balanced_rebalance_interval_sensitivity as interval_sensitivity  # noqa: E402
import analyze_hv_balanced_rebalance_phase_sensitivity as phase_sensitivity  # noqa: E402
from enhengclaw.quant_research.binance_canonical_h10d import _run_backtest  # noqa: E402


PHASES = tuple(range(10))
HORIZON_DAYS = 10
DEFAULT_OUT_ROOT = ROOT / "artifacts" / "quant_research" / "hv_balanced_multiphase_sleeve_ensemble_20260521"
DEFAULT_DOC_PATH = (
    ROOT
    / "docs"
    / "quant_research"
    / "03_alpha_branches"
    / "hv_balanced_multiphase_sleeve_ensemble_2026_05_21.md"
)
RECONCILIATION_TOLERANCE = 1e-10


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a paper-only 10-phase sleeve ensemble diagnostic for frozen hv_balanced. "
            "Each sleeve keeps the original 10d cadence, starts on a different daily phase, "
            "and is weighted equally into one aggregate target book."
        )
    )
    parser.add_argument("--config", type=Path, default=interval_sensitivity.DEFAULT_HV_BALANCED_CONFIG_PATH)
    parser.add_argument("--store-root", type=Path, default=None)
    parser.add_argument("--funding-root", type=Path, default=None)
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--scenario", choices=["base", "stress"], default="base")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUT_ROOT)
    parser.add_argument("--doc-path", type=Path, default=DEFAULT_DOC_PATH)
    parser.add_argument("--baseline-report", type=Path, default=interval_sensitivity.DEFAULT_FROZEN_REPORT)
    parser.add_argument("--frozen-row-membership", type=Path, default=interval_sensitivity.DEFAULT_FROZEN_ROW_MEMBERSHIP)
    parser.add_argument("--no-frozen-row-alignment", action="store_true")
    parser.add_argument("--baseline-tolerance", type=float, default=1e-8)
    parser.add_argument("--max-symbols", type=int, default=None)
    parser.add_argument("--top-n", type=int, default=None)
    parser.add_argument("--start-month", default=None)
    parser.add_argument("--end-month", default=None)
    parser.add_argument("--min-ensemble-net-return", type=float, default=0.0)
    parser.add_argument("--max-ensemble-drawdown", type=float, default=0.20)
    parser.add_argument("--max-aggregate-gross", type=float, default=1.05)
    parser.add_argument(
        "--multiphase-execution-gap-policy",
        choices=["none", "drop_selected_path_gap_symbols_across_phases"],
        default="drop_selected_path_gap_symbols_across_phases",
        help=(
            "Historical validation-only policy for the multi-phase target book. "
            "When enabled, iteratively excludes entire symbols that produce selected fill/exit "
            "execution-path gaps in any 10d phase before constructing aggregate targets."
        ),
    )
    parser.add_argument("--max-gap-policy-iterations", type=int, default=5)
    return parser.parse_args()


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def json_safe(value: Any) -> Any:
    return interval_sensitivity.json_safe(value)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    interval_sensitivity.write_json(path, payload)


def records(frame: pd.DataFrame, *, limit: int | None = None) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    subset = frame.head(limit) if limit is not None else frame
    return json.loads(subset.replace([np.inf, -np.inf], np.nan).to_json(orient="records"))


def performance_summary(returns: pd.Series, *, periods_per_year: int) -> dict[str, float]:
    cleaned = pd.to_numeric(returns, errors="coerce").fillna(0.0).astype("float64")
    if cleaned.empty:
        return {"net_return": 0.0, "sharpe": 0.0, "max_drawdown": 0.0}
    equity = (1.0 + cleaned).cumprod()
    running_max = equity.cummax()
    drawdown = ((running_max - equity) / running_max.replace(0.0, np.nan)).fillna(0.0)
    std = float(cleaned.std(ddof=0))
    sharpe = 0.0 if std <= 0.0 else float(cleaned.mean() / std * math.sqrt(periods_per_year))
    return {
        "net_return": float(equity.iloc[-1] - 1.0),
        "sharpe": sharpe,
        "max_drawdown": float(drawdown.max()),
    }


def reconcile_periods(official: pd.DataFrame, fast: pd.DataFrame, *, phase: int) -> dict[str, Any]:
    if official.empty or fast.empty:
        return {
            "phase_offset_days": int(phase),
            "status": "blocked",
            "reason": "missing_periods",
            "official_period_count": int(len(official)),
            "fast_period_count": int(len(fast)),
        }
    left = official.copy()
    right = fast.copy()
    left["timestamp_ms"] = pd.to_numeric(left["timestamp_ms"], errors="coerce").astype("Int64")
    right["timestamp_ms"] = pd.to_numeric(right["timestamp_ms"], errors="coerce").astype("Int64")
    merged = left.merge(right, on="timestamp_ms", how="outer", suffixes=("_official", "_fast"), indicator=True)
    row: dict[str, Any] = {
        "phase_offset_days": int(phase),
        "status": "passed",
        "official_period_count": int(len(left)),
        "fast_period_count": int(len(right)),
        "merged_period_count": int(len(merged)),
        "timestamp_join_mismatch_count": int((merged["_merge"] != "both").sum()),
        "tolerance": RECONCILIATION_TOLERANCE,
    }
    for metric in (
        "net_period_return",
        "gross_return_before_costs",
        "fee_cost_return",
        "slippage_cost_return",
        "funding_cost_return",
        "turnover",
    ):
        official_series = pd.to_numeric(merged.get(f"{metric}_official"), errors="coerce").fillna(0.0)
        fast_series = pd.to_numeric(merged.get(f"{metric}_fast"), errors="coerce").fillna(0.0)
        delta = fast_series - official_series
        row[f"{metric}_sum_delta_fast_minus_official"] = float(delta.sum())
        row[f"{metric}_max_abs_delta_fast_minus_official"] = float(delta.abs().max()) if not delta.empty else 0.0
    if (
        row["official_period_count"] != row["fast_period_count"]
        or row["timestamp_join_mismatch_count"] > 0
        or row["net_period_return_max_abs_delta_fast_minus_official"] > RECONCILIATION_TOLERANCE
        or row["gross_return_before_costs_max_abs_delta_fast_minus_official"] > RECONCILIATION_TOLERANCE
        or row["funding_cost_return_max_abs_delta_fast_minus_official"] > RECONCILIATION_TOLERANCE
    ):
        row["status"] = "blocked"
    return row


def run_phase_bundle(
    *,
    phase: int,
    scored_frame: pd.DataFrame,
    run_config: dict[str, Any],
    scenario: str,
    sleeve_weight: float,
) -> dict[str, Any]:
    phase_frame, phase_audit = phase_sensitivity.phase_frame(scored_frame, phase_offset_days=phase)
    metrics = _run_backtest(phase_frame, config=run_config, scenario=scenario, include_periods=True)
    fast = interval_attribution.build_fast_interval_attribution(phase_frame, config=run_config, scenario=scenario)
    official_periods = pd.DataFrame(metrics.get("periods") or [])
    fast_periods = fast["periods"].copy()
    reconciliation = reconcile_periods(official_periods, fast_periods, phase=phase)
    positions = fast["positions"].copy()
    ledger = fast["ledger"].copy()
    for frame in (positions, ledger, fast_periods):
        if not frame.empty:
            frame["phase_offset_days"] = int(phase)
            frame["sleeve_weight"] = float(sleeve_weight)
    if not positions.empty:
        positions["sleeve_weighted_weight"] = pd.to_numeric(positions["weight"], errors="coerce").fillna(0.0) * float(sleeve_weight)
        for column in ("gross_contribution", "funding_cost_return", "net_before_trade_cost_contribution"):
            positions[f"sleeve_weighted_{column}"] = pd.to_numeric(positions[column], errors="coerce").fillna(0.0) * float(sleeve_weight)
    if not ledger.empty:
        for column in (
            "gross_contribution",
            "fee_cost_return",
            "slippage_cost_return",
            "funding_cost_return",
            "borrow_cost_return",
            "net_contribution",
            "net_before_trade_cost_contribution",
            "target_notional_usd",
            "delta_notional_usd",
            "trade_notional_usd",
        ):
            if column in ledger.columns:
                ledger[f"sleeve_weighted_{column}"] = pd.to_numeric(ledger[column], errors="coerce").fillna(0.0) * float(sleeve_weight)
    if not fast_periods.empty:
        for column in (
            "net_period_return",
            "gross_return_before_costs",
            "fee_cost_return",
            "slippage_cost_return",
            "funding_cost_return",
            "borrow_cost_return",
            "turnover",
            "trade_notional_usd",
        ):
            if column in fast_periods.columns:
                fast_periods[f"sleeve_weighted_{column}"] = pd.to_numeric(fast_periods[column], errors="coerce").fillna(0.0) * float(sleeve_weight)
    return {
        "phase": int(phase),
        "phase_audit": phase_audit,
        "metrics": metrics,
        "positions": positions,
        "ledger": ledger,
        "periods": fast_periods,
        "reconciliation": reconciliation,
        "fast_summary": fast["summary"],
        "ledger_summary": fast["ledger_summary"],
    }


def apply_multiphase_execution_gap_policy(
    scored_frame: pd.DataFrame,
    *,
    run_config: dict[str, Any],
    scenario: str,
    mode: str,
    max_iterations: int,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    mode = str(mode or "none").strip().lower()
    if scored_frame.empty or mode == "none":
        return scored_frame.copy(), {
            "mode": mode or "none",
            "applied": False,
            "row_count_before": int(len(scored_frame)),
            "row_count_after": int(len(scored_frame)),
            "residual_data_gap_blockers": [],
            "status": "not_applied",
        }
    if mode != "drop_selected_path_gap_symbols_across_phases":
        raise ValueError(f"Unsupported multiphase execution gap policy: {mode}")
    working = scored_frame.copy()
    excluded_subjects: list[str] = []
    iterations: list[dict[str, Any]] = []
    max_iterations = max(int(max_iterations or 1), 1)
    for iteration in range(1, max_iterations + 1):
        phase_gaps = collect_phase_execution_data_gaps(working, run_config=run_config, scenario=scenario)
        gap_subjects = sorted(set(subjects_from_gap_blockers(phase_gaps["all_data_gap_blockers"])) - set(excluded_subjects))
        iterations.append(
            {
                "iteration": int(iteration),
                "row_count_before": int(len(working)),
                "phase_gap_summary": phase_gaps["phase_gap_summary"],
                "data_gap_blockers": phase_gaps["all_data_gap_blockers"],
                "gap_subjects": gap_subjects,
            }
        )
        if not gap_subjects:
            break
        excluded_subjects.extend(gap_subjects)
        working = working.loc[~working["subject"].astype(str).isin(gap_subjects)].copy()
    residual = collect_phase_execution_data_gaps(working, run_config=run_config, scenario=scenario)
    audit = {
        "mode": "drop_selected_path_gap_symbols_across_phases",
        "applied": True,
        "selection_rule": (
            "exclude an entire symbol from this historical multi-phase target diagnostic if any selected "
            "10d phase lacks the required fill/exit execution row for that symbol"
        ),
        "source_boundary": "historical_execution_path_completeness_only",
        "alpha_source_usage": False,
        "forward_return_label_usage": False,
        "future_execution_path_availability_usage": True,
        "live_transfer_policy": (
            "not live-tradable as-is; live integration must use current exchange symbol filters, "
            "fresh market data, and order-size rules instead of historical future-path exclusion"
        ),
        "max_iterations": int(max_iterations),
        "iteration_count": int(len(iterations)),
        "excluded_subjects": sorted(set(excluded_subjects)),
        "excluded_symbols": [f"{subject}USDT" for subject in sorted(set(excluded_subjects))],
        "row_count_before": int(len(scored_frame)),
        "row_count_after": int(len(working)),
        "dropped_row_count": int(len(scored_frame) - len(working)),
        "residual_data_gap_blockers": residual["all_data_gap_blockers"],
        "residual_phase_gap_summary": residual["phase_gap_summary"],
        "status": "ok" if not residual["all_data_gap_blockers"] else "residual_gap_blockers",
        "iterations": iterations,
    }
    return working.reset_index(drop=True), audit


def collect_phase_execution_data_gaps(
    scored_frame: pd.DataFrame,
    *,
    run_config: dict[str, Any],
    scenario: str,
) -> dict[str, Any]:
    all_gaps: list[str] = []
    phase_rows: list[dict[str, Any]] = []
    for phase in PHASES:
        phase_scored, phase_audit = phase_sensitivity.phase_frame(scored_frame, phase_offset_days=phase)
        if phase_scored.empty:
            phase_rows.append(
                {
                    "phase_offset_days": int(phase),
                    "phase_status": str(phase_audit.get("status")),
                    "data_gap_blocker_count": 0,
                    "data_gap_blockers": [],
                }
            )
            continue
        metrics = _run_backtest(phase_scored, config=run_config, scenario=scenario, include_periods=False)
        gaps = sorted(str(item) for item in list(metrics.get("data_gap_blockers") or []))
        all_gaps.extend(gaps)
        phase_rows.append(
            {
                "phase_offset_days": int(phase),
                "phase_status": str(phase_audit.get("status")),
                "rebalance_count": int(metrics.get("rebalance_count", 0) or 0),
                "trade_count": int(metrics.get("trade_count", 0) or 0),
                "data_gap_blocker_count": int(len(gaps)),
                "data_gap_blockers": gaps,
            }
        )
    return {
        "phase_gap_summary": phase_rows,
        "all_data_gap_blockers": sorted(set(all_gaps)),
    }


def subjects_from_gap_blockers(blockers: list[str]) -> list[str]:
    subjects: list[str] = []
    for item in blockers:
        text = str(item or "")
        if ": missing " not in text:
            continue
        subject = text.split(":", 1)[0].strip()
        if subject:
            subjects.append(subject)
    return subjects


def build_ensemble_period_returns(periods: pd.DataFrame) -> pd.DataFrame:
    if periods.empty:
        return pd.DataFrame()
    working = periods.copy()
    working["timestamp_ms"] = pd.to_numeric(working["timestamp_ms"], errors="coerce")
    working = working.dropna(subset=["timestamp_ms"]).copy()
    working["timestamp_ms"] = working["timestamp_ms"].astype("int64")
    for column in (
        "net_period_return",
        "gross_return_before_costs",
        "fee_cost_return",
        "slippage_cost_return",
        "funding_cost_return",
        "borrow_cost_return",
        "turnover",
        "trade_notional_usd",
    ):
        if column in working.columns:
            working[f"sleeve_weighted_{column}"] = pd.to_numeric(
                working.get(f"sleeve_weighted_{column}", working[column] * working["sleeve_weight"]),
                errors="coerce",
            ).fillna(0.0)
        elif f"sleeve_weighted_{column}" not in working.columns:
            working[f"sleeve_weighted_{column}"] = 0.0
    grouped = (
        working.groupby("timestamp_ms", sort=True)
        .agg(
            active_sleeve_period_count=("phase_offset_days", "nunique"),
            contributing_period_count=("phase_offset_days", "count"),
            ensemble_net_return=("sleeve_weighted_net_period_return", "sum"),
            ensemble_gross_return_before_costs=("sleeve_weighted_gross_return_before_costs", "sum"),
            ensemble_fee_cost_return=("sleeve_weighted_fee_cost_return", "sum"),
            ensemble_slippage_cost_return=("sleeve_weighted_slippage_cost_return", "sum"),
            ensemble_funding_cost_return=("sleeve_weighted_funding_cost_return", "sum"),
            ensemble_borrow_cost_return=("sleeve_weighted_borrow_cost_return", "sum"),
            ensemble_turnover=("sleeve_weighted_turnover", "sum"),
            ensemble_trade_notional_usd=("sleeve_weighted_trade_notional_usd", "sum"),
        )
        .reset_index()
    )
    grouped["date_utc"] = pd.to_datetime(grouped["timestamp_ms"], unit="ms", utc=True).dt.date.astype(str)
    equity = []
    drawdown = []
    current = 1.0
    peak = 1.0
    for value in pd.to_numeric(grouped["ensemble_net_return"], errors="coerce").fillna(0.0):
        current *= 1.0 + float(value)
        peak = max(peak, current)
        equity.append(current)
        drawdown.append(0.0 if peak <= 0.0 else (peak - current) / peak)
    grouped["ensemble_equity"] = equity
    grouped["ensemble_drawdown"] = drawdown
    return grouped


def build_aggregate_targets_by_event(positions: pd.DataFrame, event_timestamps: list[int]) -> tuple[pd.DataFrame, pd.DataFrame]:
    if positions.empty or not event_timestamps:
        return pd.DataFrame(), pd.DataFrame()
    pos = positions.copy()
    pos["fill_timestamp_ms"] = pd.to_numeric(pos["fill_timestamp_ms"], errors="coerce")
    pos["exit_timestamp_ms"] = pd.to_numeric(pos["exit_timestamp_ms"], errors="coerce")
    pos["sleeve_weighted_weight"] = pd.to_numeric(pos["sleeve_weighted_weight"], errors="coerce").fillna(0.0)
    pos = pos.dropna(subset=["fill_timestamp_ms", "exit_timestamp_ms"]).copy()
    pos["fill_timestamp_ms"] = pos["fill_timestamp_ms"].astype("int64")
    pos["exit_timestamp_ms"] = pos["exit_timestamp_ms"].astype("int64")
    target_rows: list[dict[str, Any]] = []
    total_rows: list[dict[str, Any]] = []
    previous_weights: dict[str, float] = {}
    for timestamp in sorted(int(item) for item in event_timestamps):
        active = pos.loc[
            (pos["fill_timestamp_ms"] <= timestamp)
            & (pos["exit_timestamp_ms"] > timestamp)
            & pos["sleeve_weighted_weight"].abs().gt(1e-12)
        ].copy()
        if active.empty:
            current_weights: dict[str, float] = {}
            totals = {
                "timestamp_ms": timestamp,
                "date_utc": pd.to_datetime(timestamp, unit="ms", utc=True).date().isoformat(),
                "aggregate_position_count": 0,
                "aggregate_gross_weight": 0.0,
                "aggregate_long_gross_weight": 0.0,
                "aggregate_short_gross_weight": 0.0,
                "aggregate_net_weight": 0.0,
                "max_abs_symbol_weight": 0.0,
                "aggregate_target_turnover_vs_previous_event": sum(abs(value) for value in previous_weights.values()),
                "active_sleeve_count": 0,
            }
        else:
            grouped = (
                active.groupby("subject", sort=True)
                .agg(
                    aggregate_weight=("sleeve_weighted_weight", "sum"),
                    active_sleeve_count=("phase_offset_days", "nunique"),
                    contributing_row_count=("phase_offset_days", "count"),
                    usdm_symbol=("usdm_symbol", "last"),
                    phases=("phase_offset_days", lambda values: ",".join(str(int(item)) for item in sorted(set(values)))),
                )
                .reset_index()
            )
            grouped = grouped.loc[pd.to_numeric(grouped["aggregate_weight"], errors="coerce").abs().gt(1e-12)].copy()
            current_weights = {
                str(row["subject"]): float(row["aggregate_weight"])
                for _, row in grouped.iterrows()
            }
            for _, row in grouped.iterrows():
                aggregate_weight = float(row["aggregate_weight"])
                target_rows.append(
                    {
                        "timestamp_ms": timestamp,
                        "date_utc": pd.to_datetime(timestamp, unit="ms", utc=True).date().isoformat(),
                        "subject": str(row["subject"]),
                        "usdm_symbol": str(row["usdm_symbol"]),
                        "aggregate_weight": aggregate_weight,
                        "side": "long" if aggregate_weight > 0.0 else "short",
                        "active_sleeve_count": int(row["active_sleeve_count"]),
                        "contributing_row_count": int(row["contributing_row_count"]),
                        "phases": str(row["phases"]),
                    }
                )
            union = sorted(set(previous_weights) | set(current_weights))
            turnover = sum(abs(float(current_weights.get(subject, 0.0)) - float(previous_weights.get(subject, 0.0))) for subject in union)
            weights = pd.Series(list(current_weights.values()), dtype="float64")
            totals = {
                "timestamp_ms": timestamp,
                "date_utc": pd.to_datetime(timestamp, unit="ms", utc=True).date().isoformat(),
                "aggregate_position_count": int(len(weights)),
                "aggregate_gross_weight": float(weights.abs().sum()),
                "aggregate_long_gross_weight": float(weights.clip(lower=0.0).sum()),
                "aggregate_short_gross_weight": float((-weights.clip(upper=0.0)).sum()),
                "aggregate_net_weight": float(weights.sum()),
                "max_abs_symbol_weight": float(weights.abs().max()) if not weights.empty else 0.0,
                "aggregate_target_turnover_vs_previous_event": float(turnover),
                "active_sleeve_count": int(active["phase_offset_days"].nunique()),
            }
        total_rows.append(totals)
        previous_weights = current_weights
    return pd.DataFrame(target_rows), pd.DataFrame(total_rows)


def build_true_daily_mtm(
    *,
    scored_frame: pd.DataFrame,
    positions: pd.DataFrame,
    ledger: pd.DataFrame,
) -> dict[str, Any]:
    if scored_frame.empty or positions.empty:
        empty = pd.DataFrame()
        return {
            "position_ledger": empty,
            "daily_returns": empty,
            "metrics": performance_summary(pd.Series(dtype="float64"), periods_per_year=365),
            "blockers": ["empty_scored_frame_or_positions"],
        }
    price_columns = ["timestamp_ms", "subject", "usdm_symbol", "perp_close"]
    optional_columns = ["funding_rate", "funding_sample_count"]
    missing = [column for column in price_columns if column not in scored_frame.columns]
    if missing:
        empty = pd.DataFrame()
        return {
            "position_ledger": empty,
            "daily_returns": empty,
            "metrics": performance_summary(pd.Series(dtype="float64"), periods_per_year=365),
            "blockers": [f"daily_mtm_missing_scored_columns:{','.join(missing)}"],
        }
    price_frame = scored_frame[[*price_columns, *[column for column in optional_columns if column in scored_frame.columns]]].copy()
    price_frame["timestamp_ms"] = pd.to_numeric(price_frame["timestamp_ms"], errors="coerce")
    price_frame["perp_close"] = pd.to_numeric(price_frame["perp_close"], errors="coerce")
    price_frame = price_frame.dropna(subset=["timestamp_ms", "subject", "perp_close"]).copy()
    price_frame["timestamp_ms"] = price_frame["timestamp_ms"].astype("int64")
    if "funding_rate" not in price_frame.columns:
        price_frame["funding_rate"] = 0.0
    if "funding_sample_count" not in price_frame.columns:
        price_frame["funding_sample_count"] = 0.0
    price_frame["funding_rate"] = pd.to_numeric(price_frame["funding_rate"], errors="coerce").fillna(0.0)
    price_frame["funding_sample_count"] = pd.to_numeric(price_frame["funding_sample_count"], errors="coerce").fillna(0.0)
    price_frame = price_frame.sort_values(["subject", "timestamp_ms"]).reset_index(drop=True)
    price_frame["previous_perp_close"] = price_frame.groupby("subject", sort=False)["perp_close"].shift(1)
    by_subject = {str(subject): group.copy() for subject, group in price_frame.groupby("subject", sort=False)}

    records: list[dict[str, Any]] = []
    blockers: set[str] = set()
    required_position_columns = {
        "subject",
        "usdm_symbol",
        "phase_offset_days",
        "fill_timestamp_ms",
        "exit_timestamp_ms",
        "entry_price",
        "sleeve_weighted_weight",
    }
    missing_position = sorted(required_position_columns - set(positions.columns))
    if missing_position:
        blockers.add(f"daily_mtm_missing_position_columns:{','.join(missing_position)}")
    else:
        for _, position in positions.iterrows():
            subject = str(position.get("subject") or "")
            subject_prices = by_subject.get(subject)
            if subject_prices is None or subject_prices.empty:
                blockers.add(f"{subject}:daily_mtm_missing_price_rows")
                continue
            fill_ts = int(float(position.get("fill_timestamp_ms") or 0))
            exit_ts = int(float(position.get("exit_timestamp_ms") or 0))
            entry_price = float(position.get("entry_price") or 0.0)
            weight = float(position.get("sleeve_weighted_weight") or 0.0)
            if exit_ts <= fill_ts or entry_price <= 0.0 or abs(weight) <= 1e-12:
                continue
            active = subject_prices.loc[
                (subject_prices["timestamp_ms"] >= fill_ts)
                & (subject_prices["timestamp_ms"] <= exit_ts)
            ].copy()
            if active.empty:
                blockers.add(f"{subject}:daily_mtm_empty_active_slice")
                continue
            for _, row in active.iterrows():
                ts = int(row["timestamp_ms"])
                price_contribution = 0.0
                if ts > fill_ts:
                    previous_close = float(row.get("previous_perp_close") or 0.0)
                    current_close = float(row.get("perp_close") or 0.0)
                    if previous_close <= 0.0 or current_close <= 0.0:
                        blockers.add(f"{subject}:daily_mtm_missing_price_path:{ts}")
                    else:
                        price_contribution = float(weight * ((current_close - previous_close) / entry_price))
                funding_cost_return = 0.0
                if ts < exit_ts:
                    funding_cost_return = float(
                        weight
                        * float(row.get("funding_rate") or 0.0)
                        * float(row.get("funding_sample_count") or 0.0)
                    )
                if abs(price_contribution) <= 1e-18 and abs(funding_cost_return) <= 1e-18:
                    continue
                records.append(
                    {
                        "timestamp_ms": ts,
                        "date_utc": pd.to_datetime(ts, unit="ms", utc=True).date().isoformat(),
                        "phase_offset_days": int(position.get("phase_offset_days") or 0),
                        "subject": subject,
                        "usdm_symbol": str(position.get("usdm_symbol") or f"{subject}USDT"),
                        "side": str(position.get("side") or ""),
                        "sleeve_weight": float(position.get("sleeve_weight") or 0.0),
                        "sleeve_weighted_weight": float(weight),
                        "fill_timestamp_ms": fill_ts,
                        "exit_timestamp_ms": exit_ts,
                        "entry_price": float(entry_price),
                        "perp_close": float(row.get("perp_close") or 0.0),
                        "previous_perp_close": float(row.get("previous_perp_close") or 0.0),
                        "price_mtm_return": float(price_contribution),
                        "funding_cost_return": float(funding_cost_return),
                        "net_mtm_before_trade_cost_return": float(price_contribution - funding_cost_return),
                    }
                )
    position_ledger = pd.DataFrame(records)
    if position_ledger.empty:
        daily = pd.DataFrame()
    else:
        daily = (
            position_ledger.groupby("timestamp_ms", sort=True)
            .agg(
                date_utc=("date_utc", "last"),
                active_position_day_count=("subject", "count"),
                active_symbol_count=("subject", "nunique"),
                active_sleeve_count=("phase_offset_days", "nunique"),
                gross_return_before_costs=("price_mtm_return", "sum"),
                funding_cost_return=("funding_cost_return", "sum"),
                net_before_trade_cost_return=("net_mtm_before_trade_cost_return", "sum"),
            )
            .reset_index()
        )
    trade_costs = build_daily_trade_costs(ledger)
    if daily.empty:
        daily = trade_costs.copy()
    elif not trade_costs.empty:
        daily = daily.merge(trade_costs, on=["timestamp_ms", "date_utc"], how="outer")
    if not daily.empty:
        for column in (
            "active_position_day_count",
            "active_symbol_count",
            "active_sleeve_count",
            "gross_return_before_costs",
            "funding_cost_return",
            "net_before_trade_cost_return",
            "fee_cost_return",
            "slippage_cost_return",
            "borrow_cost_return",
            "trade_notional_usd",
        ):
            if column not in daily.columns:
                daily[column] = 0.0
            daily[column] = pd.to_numeric(daily[column], errors="coerce").fillna(0.0)
        daily["net_daily_return"] = (
            daily["gross_return_before_costs"]
            - daily["funding_cost_return"]
            - daily["fee_cost_return"]
            - daily["slippage_cost_return"]
            - daily["borrow_cost_return"]
        )
        daily = daily.sort_values("timestamp_ms").reset_index(drop=True)
        equity = (1.0 + daily["net_daily_return"]).cumprod()
        daily["daily_mtm_equity"] = equity
        daily["daily_mtm_drawdown"] = ((equity.cummax() - equity) / equity.cummax().replace(0.0, np.nan)).fillna(0.0)
    metrics = performance_summary(daily["net_daily_return"] if not daily.empty else pd.Series(dtype="float64"), periods_per_year=365)
    if not daily.empty:
        metrics.update(
            {
                "daily_row_count": int(len(daily)),
                "gross_return_before_costs_sum": float(daily["gross_return_before_costs"].sum()),
                "funding_cost_return_sum": float(daily["funding_cost_return"].sum()),
                "fee_cost_return_sum": float(daily["fee_cost_return"].sum()),
                "slippage_cost_return_sum": float(daily["slippage_cost_return"].sum()),
                "borrow_cost_return_sum": float(daily["borrow_cost_return"].sum()),
                "trade_notional_usd_sum": float(daily["trade_notional_usd"].sum()),
            }
        )
    return {
        "position_ledger": position_ledger,
        "daily_returns": daily,
        "metrics": metrics,
        "blockers": sorted(blockers),
    }


def build_daily_trade_costs(ledger: pd.DataFrame) -> pd.DataFrame:
    if ledger.empty or "fill_timestamp_ms" not in ledger.columns:
        return pd.DataFrame()
    working = ledger.copy()
    working["timestamp_ms"] = pd.to_numeric(working["fill_timestamp_ms"], errors="coerce")
    working = working.dropna(subset=["timestamp_ms"]).copy()
    working["timestamp_ms"] = working["timestamp_ms"].astype("int64")
    working["date_utc"] = pd.to_datetime(working["timestamp_ms"], unit="ms", utc=True).dt.date.astype(str)
    for column in ("fee_cost_return", "slippage_cost_return", "borrow_cost_return", "trade_notional_usd"):
        weighted = f"sleeve_weighted_{column}"
        source = weighted if weighted in working.columns else column
        if source not in working.columns:
            working[column] = 0.0
        else:
            working[column] = pd.to_numeric(working[source], errors="coerce").fillna(0.0)
    return (
        working.groupby(["timestamp_ms", "date_utc"], sort=True)
        .agg(
            fee_cost_return=("fee_cost_return", "sum"),
            slippage_cost_return=("slippage_cost_return", "sum"),
            borrow_cost_return=("borrow_cost_return", "sum"),
            trade_notional_usd=("trade_notional_usd", "sum"),
        )
        .reset_index()
    )


def phase_metrics_frame(bundles: dict[int, dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    phase0_net = float(bundles[0]["metrics"].get("net_return", 0.0) or 0.0) if 0 in bundles else 0.0
    for phase, bundle in sorted(bundles.items()):
        metrics = bundle["metrics"]
        row = {
            "label": f"phase{phase}",
            "phase_offset_days": int(phase),
            "net_return": float(metrics.get("net_return", 0.0) or 0.0),
            "sharpe": float(metrics.get("sharpe", 0.0) or 0.0),
            "max_drawdown": float(metrics.get("max_drawdown", 0.0) or 0.0),
            "turnover": float(metrics.get("turnover", 0.0) or 0.0),
            "trade_count": int(metrics.get("trade_count", 0) or 0),
            "rebalance_count": int(metrics.get("rebalance_count", 0) or 0),
            "data_gap_blocker_count": int(len(metrics.get("data_gap_blockers") or [])),
        }
        row["net_return_ratio_vs_phase0"] = row["net_return"] / phase0_net if abs(phase0_net) > 1e-12 else None
        rows.append(row)
    return pd.DataFrame(rows)


def ensemble_metric_frame(*, phase_metrics: pd.DataFrame, ensemble_metrics: dict[str, float], target_totals: pd.DataFrame) -> pd.DataFrame:
    rows = [
        {
            "label": "single_phase0",
            "net_return": float(phase_metrics.loc[phase_metrics["phase_offset_days"].eq(0), "net_return"].iloc[0]),
            "sharpe": float(phase_metrics.loc[phase_metrics["phase_offset_days"].eq(0), "sharpe"].iloc[0]),
            "max_drawdown": float(phase_metrics.loc[phase_metrics["phase_offset_days"].eq(0), "max_drawdown"].iloc[0]),
            "max_aggregate_gross_weight": 1.0,
        },
        {
            "label": "single_phase7_weak",
            "net_return": float(phase_metrics.loc[phase_metrics["phase_offset_days"].eq(7), "net_return"].iloc[0]),
            "sharpe": float(phase_metrics.loc[phase_metrics["phase_offset_days"].eq(7), "sharpe"].iloc[0]),
            "max_drawdown": float(phase_metrics.loc[phase_metrics["phase_offset_days"].eq(7), "max_drawdown"].iloc[0]),
            "max_aggregate_gross_weight": 1.0,
        },
        {
            "label": "equal_weight_10_phase_sleeves",
            "net_return": float(ensemble_metrics["net_return"]),
            "sharpe": float(ensemble_metrics["sharpe"]),
            "max_drawdown": float(ensemble_metrics["max_drawdown"]),
            "max_aggregate_gross_weight": float(pd.to_numeric(target_totals.get("aggregate_gross_weight"), errors="coerce").max()) if not target_totals.empty else 0.0,
        },
    ]
    return pd.DataFrame(rows)


def evaluate_gate(
    *,
    args: argparse.Namespace,
    reconciliations: pd.DataFrame,
    ensemble_metrics: dict[str, float],
    daily_mtm: dict[str, Any],
    target_totals: pd.DataFrame,
    blockers: list[dict[str, Any]],
) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    if not reconciliations.empty and not bool(reconciliations["status"].astype(str).eq("passed").all()):
        failures.append({"code": "phase_fast_reconciliation_failed"})
    max_gross = float(pd.to_numeric(target_totals.get("aggregate_gross_weight"), errors="coerce").max()) if not target_totals.empty else 0.0
    if float(ensemble_metrics.get("net_return", 0.0) or 0.0) <= float(args.min_ensemble_net_return):
        failures.append({"code": "ensemble_net_return_below_threshold", "threshold": float(args.min_ensemble_net_return), "observed": ensemble_metrics.get("net_return")})
    if float(ensemble_metrics.get("max_drawdown", 0.0) or 0.0) > float(args.max_ensemble_drawdown):
        failures.append({"code": "ensemble_drawdown_above_threshold", "threshold": float(args.max_ensemble_drawdown), "observed": ensemble_metrics.get("max_drawdown")})
    if max_gross > float(args.max_aggregate_gross):
        failures.append({"code": "aggregate_gross_above_threshold", "threshold": float(args.max_aggregate_gross), "observed": max_gross})
    daily_blockers = list(daily_mtm.get("blockers") or [])
    if daily_blockers:
        failures.append({"code": "true_daily_mtm_blocked", "blockers": daily_blockers[:10]})
    if blockers:
        failures.append({"code": "upstream_blockers_present", "count": len(blockers)})
    return {
        "status": "passed" if not failures else "blocked",
        "failures": failures,
        "thresholds": {
            "min_ensemble_net_return": float(args.min_ensemble_net_return),
            "max_ensemble_drawdown": float(args.max_ensemble_drawdown),
            "max_aggregate_gross": float(args.max_aggregate_gross),
        },
        "observed": {
            "ensemble_net_return": float(ensemble_metrics.get("net_return", 0.0) or 0.0),
            "ensemble_sharpe_daily_booking_approx": float(ensemble_metrics.get("sharpe", 0.0) or 0.0),
            "ensemble_max_drawdown": float(ensemble_metrics.get("max_drawdown", 0.0) or 0.0),
            "true_daily_mtm_net_return": float(dict(daily_mtm.get("metrics") or {}).get("net_return", 0.0) or 0.0),
            "true_daily_mtm_sharpe": float(dict(daily_mtm.get("metrics") or {}).get("sharpe", 0.0) or 0.0),
            "true_daily_mtm_max_drawdown": float(dict(daily_mtm.get("metrics") or {}).get("max_drawdown", 0.0) or 0.0),
            "max_aggregate_gross_weight": max_gross,
        },
    }


def render_table(frame: pd.DataFrame, columns: list[str], *, max_rows: int = 20) -> str:
    return interval_sensitivity.dataframe_to_markdown(frame.head(max_rows), columns)


def write_report(
    *,
    doc_path: Path,
    summary: dict[str, Any],
    phase_metrics: pd.DataFrame,
    ensemble_metrics_frame: pd.DataFrame,
    target_totals: pd.DataFrame,
    daily_mtm_returns: pd.DataFrame,
    reconciliations: pd.DataFrame,
    artifact_paths: dict[str, str],
) -> None:
    gate = dict(summary.get("gate") or {})
    blockers = list(summary.get("blockers") or [])
    policy = dict(summary.get("multiphase_execution_gap_policy") or {})
    blocker_lines = "\n".join(f"- `{item.get('code', 'blocker')}`: {item}" for item in blockers) or "- none"
    failure_lines = "\n".join(f"- `{item.get('code', 'failure')}`: {item}" for item in gate.get("failures") or []) or "- none"
    target_tail = target_totals.sort_values("timestamp_ms").tail(12) if not target_totals.empty else pd.DataFrame()
    daily_tail = daily_mtm_returns.sort_values("timestamp_ms").tail(12) if not daily_mtm_returns.empty else pd.DataFrame()
    lines = [
        "# hv_balanced multi-phase sleeve ensemble diagnostic",
        "",
        f"- generated_at_utc: `{summary['generated_at_utc']}`",
        f"- status: `{summary['status']}`",
        f"- gate_status: `{gate.get('status')}`",
        f"- scenario: `{summary['scenario']}`",
        f"- config_path: `{summary['config_path']}`",
        f"- phases: `{summary['phases']}`",
        f"- sleeve_weight: `{summary['sleeve_weight']}`",
        f"- raw_scored_row_count: `{summary.get('raw_scored_row_count')}`",
        f"- eligible_scored_row_count: `{summary.get('scored_row_count')}`",
        f"- multiphase_execution_gap_policy_status: `{policy.get('status')}`",
        f"- multiphase_excluded_symbols: `{policy.get('excluded_symbols', [])}`",
        f"- ensemble_net_return: `{summary['ensemble_metrics'].get('net_return')}`",
        f"- ensemble_sharpe_daily_booking_approx: `{summary['ensemble_metrics'].get('sharpe')}`",
        f"- ensemble_max_drawdown: `{summary['ensemble_metrics'].get('max_drawdown')}`",
        f"- true_daily_mtm_net_return: `{summary['true_daily_mtm_metrics'].get('net_return')}`",
        f"- true_daily_mtm_sharpe: `{summary['true_daily_mtm_metrics'].get('sharpe')}`",
        f"- true_daily_mtm_max_drawdown: `{summary['true_daily_mtm_metrics'].get('max_drawdown')}`",
        f"- max_aggregate_gross_weight: `{summary['target_book_summary'].get('max_aggregate_gross_weight')}`",
        f"- max_event_target_turnover: `{summary['target_book_summary'].get('max_event_target_turnover')}`",
        "",
        "## Decision",
        "",
        "- This is a paper-only diagnostic target construction; it does not alter the live supervisor and does not touch Binance APIs.",
        "- The equal-weight 10-sleeve design is the preferred repair path for phase instability because it removes dependence on a single arbitrary 10d start date instead of selecting a historically lucky phase.",
        "- The historical multi-phase target book now applies an explicit execution-path eligible-universe rule before target aggregation; this is a validation policy, not live authorization.",
        "- Promotion path is still gated: executable paper shadow first, then no-order live target comparison, then live supervisor integration only after explicit approval.",
        "",
        "## Execution-Path Eligibility Policy",
        "",
        f"- mode: `{policy.get('mode')}`",
        f"- status: `{policy.get('status')}`",
        f"- excluded_symbols: `{policy.get('excluded_symbols', [])}`",
        f"- residual_data_gap_blockers: `{len(policy.get('residual_data_gap_blockers') or [])}`",
        f"- future_execution_path_availability_usage: `{policy.get('future_execution_path_availability_usage')}`",
        f"- live_transfer_policy: `{policy.get('live_transfer_policy')}`",
        "",
        "## Metrics",
        "",
        render_table(
            ensemble_metrics_frame,
            ["label", "net_return", "sharpe", "max_drawdown", "max_aggregate_gross_weight"],
        ),
        "",
        "## True Daily MTM",
        "",
        "- This section marks every active sleeve position from its fill price through each daily close, then books fee/slippage on fill dates.",
        "- It is the stricter paper-ledger check for the headline Sharpe; event-booked metrics remain a phase-robustness diagnostic.",
        "",
        render_table(
            daily_tail,
            [
                "date_utc",
                "active_position_day_count",
                "active_symbol_count",
                "active_sleeve_count",
                "gross_return_before_costs",
                "funding_cost_return",
                "fee_cost_return",
                "slippage_cost_return",
                "net_daily_return",
                "daily_mtm_equity",
                "daily_mtm_drawdown",
            ],
            max_rows=12,
        ),
        "",
        "## Phase Metrics",
        "",
        render_table(
            phase_metrics,
            [
                "phase_offset_days",
                "net_return",
                "net_return_ratio_vs_phase0",
                "sharpe",
                "max_drawdown",
                "turnover",
                "trade_count",
                "rebalance_count",
                "data_gap_blocker_count",
            ],
            max_rows=12,
        ),
        "",
        "## Recent Aggregate Target Book",
        "",
        render_table(
            target_tail,
            [
                "date_utc",
                "aggregate_position_count",
                "aggregate_gross_weight",
                "aggregate_long_gross_weight",
                "aggregate_short_gross_weight",
                "aggregate_net_weight",
                "max_abs_symbol_weight",
                "aggregate_target_turnover_vs_previous_event",
                "active_sleeve_count",
            ],
            max_rows=12,
        ),
        "",
        "## Reconciliation",
        "",
        render_table(
            reconciliations,
            [
                "phase_offset_days",
                "status",
                "official_period_count",
                "fast_period_count",
                "timestamp_join_mismatch_count",
                "net_period_return_max_abs_delta_fast_minus_official",
                "gross_return_before_costs_max_abs_delta_fast_minus_official",
                "funding_cost_return_max_abs_delta_fast_minus_official",
            ],
            max_rows=12,
        ),
        "",
        "## Gate Failures",
        "",
        failure_lines,
        "",
        "## Blockers",
        "",
        blocker_lines,
        "",
        "## Artifacts",
        "",
    ]
    for key, value in artifact_paths.items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(
        [
            "",
            "## Method Notes",
            "",
            "- Each sleeve runs the original frozen `hv_balanced` 10d policy with one different daily start offset.",
            "- Per-sleeve returns, costs, funding, and targets are scaled by `1/10`; aggregate targets are summed across active sleeves.",
            "- Return metrics are daily-booking approximations over sleeve rebalance events, matching the phase sensitivity diagnostic style.",
            "- True daily MTM metrics use the daily close-to-close mark path of each fixed-quantity sleeve holding and book trade costs on fill dates.",
            "- This runner is intentionally offline and should be treated as a candidate repair artifact, not as live authorization.",
        ]
    )
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    doc_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    output_root = interval_sensitivity.resolve_repo_path(args.output_root)
    doc_path = interval_sensitivity.resolve_repo_path(args.doc_path)
    baseline_report = interval_sensitivity.resolve_repo_path(args.baseline_report)
    store_root = Path(args.store_root).resolve() if args.store_root else interval_sensitivity.default_store_root_from_baseline(baseline_report)
    partition_path_compatibility = interval_sensitivity.install_symbol_partition_compatibility_patch()
    frozen_row_alignment = interval_sensitivity.install_frozen_feature_row_alignment_patch(
        args.frozen_row_membership,
        disabled=bool(args.no_frozen_row_alignment),
    )
    fixed = interval_sensitivity.load_fixed_scored_frame(args, store_root=store_root)
    scored_frame = fixed["scored_frame"]
    base_config = fixed["config"]
    run_config = interval_sensitivity.interval_config(base_config, HORIZON_DAYS)
    if scored_frame.empty:
        raise RuntimeError("scored_frame is empty; cannot build multi-phase ensemble")
    raw_scored_frame = scored_frame.copy()
    raw_phase0_metrics = _run_backtest(raw_scored_frame, config=run_config, scenario=args.scenario, include_periods=True)
    baseline_reproduction = interval_sensitivity.compare_baseline(
        ten_day_metrics=raw_phase0_metrics,
        baseline_report_path=baseline_report,
        tolerance=float(args.baseline_tolerance),
    )
    scored_frame, multiphase_execution_gap_policy = apply_multiphase_execution_gap_policy(
        raw_scored_frame,
        run_config=run_config,
        scenario=args.scenario,
        mode=str(args.multiphase_execution_gap_policy),
        max_iterations=int(args.max_gap_policy_iterations),
    )
    if scored_frame.empty:
        raise RuntimeError("scored_frame is empty after multi-phase execution gap policy")
    sleeve_weight = 1.0 / float(len(PHASES))
    bundles = {
        phase: run_phase_bundle(
            phase=phase,
            scored_frame=scored_frame,
            run_config=run_config,
            scenario=args.scenario,
            sleeve_weight=sleeve_weight,
        )
        for phase in PHASES
    }
    phase_metrics = phase_metrics_frame(bundles)
    positions = pd.concat([bundle["positions"] for bundle in bundles.values() if not bundle["positions"].empty], ignore_index=True)
    ledger = pd.concat([bundle["ledger"] for bundle in bundles.values() if not bundle["ledger"].empty], ignore_index=True)
    periods = pd.concat([bundle["periods"] for bundle in bundles.values() if not bundle["periods"].empty], ignore_index=True)
    reconciliations = pd.DataFrame([bundle["reconciliation"] for bundle in bundles.values()])
    ensemble_periods = build_ensemble_period_returns(periods)
    ensemble_metrics = performance_summary(ensemble_periods["ensemble_net_return"] if not ensemble_periods.empty else pd.Series(dtype="float64"), periods_per_year=365)
    event_timestamps = sorted(int(item) for item in ensemble_periods["timestamp_ms"].dropna().astype("int64").tolist()) if not ensemble_periods.empty else []
    aggregate_targets, aggregate_target_totals = build_aggregate_targets_by_event(positions, event_timestamps)
    true_daily_mtm = build_true_daily_mtm(scored_frame=scored_frame, positions=positions, ledger=ledger)
    daily_mtm_position_ledger = true_daily_mtm["position_ledger"]
    daily_mtm_returns = true_daily_mtm["daily_returns"]
    daily_mtm_metrics = true_daily_mtm["metrics"]
    ensemble_metrics_table = ensemble_metric_frame(
        phase_metrics=phase_metrics,
        ensemble_metrics=ensemble_metrics,
        target_totals=aggregate_target_totals,
    )

    dataset_reproduction = interval_sensitivity.compare_dataset_reproduction(
        current_manifest=fixed["dataset_manifest"],
        baseline_report_path=baseline_report,
    )
    candidate_phase0_baseline_comparison = interval_sensitivity.compare_baseline(
        ten_day_metrics=bundles[0]["metrics"],
        baseline_report_path=baseline_report,
        tolerance=float(args.baseline_tolerance),
    )
    blockers = list(fixed.get("blockers") or [])
    if dataset_reproduction.get("status") != "passed":
        blockers.append({"code": "frozen_dataset_reproduction_failed", "detail": dataset_reproduction})
    if baseline_reproduction.get("status") != "passed":
        blockers.append({"code": "raw_frozen_phase0_baseline_reproduction_failed", "detail": baseline_reproduction})
    if str(multiphase_execution_gap_policy.get("status")) not in {"ok", "not_applied"}:
        blockers.append(
            {
                "code": "multiphase_execution_gap_policy_failed",
                "detail": {
                    "status": multiphase_execution_gap_policy.get("status"),
                    "residual_data_gap_blockers": multiphase_execution_gap_policy.get("residual_data_gap_blockers"),
                },
            }
        )
    for phase, bundle in bundles.items():
        gaps = list(bundle["metrics"].get("data_gap_blockers") or [])
        if gaps:
            blockers.append(
                {
                    "code": "phase_execution_data_gap_blockers",
                    "phase_offset_days": int(phase),
                    "data_gap_blocker_count": len(gaps),
                    "sample": gaps[:10],
                }
            )
    gate = evaluate_gate(
        args=args,
        reconciliations=reconciliations,
        ensemble_metrics=ensemble_metrics,
        daily_mtm=true_daily_mtm,
        target_totals=aggregate_target_totals,
        blockers=blockers,
    )
    target_book_summary = {
        "event_count": int(len(aggregate_target_totals)),
        "target_row_count": int(len(aggregate_targets)),
        "max_aggregate_gross_weight": float(pd.to_numeric(aggregate_target_totals.get("aggregate_gross_weight"), errors="coerce").max()) if not aggregate_target_totals.empty else 0.0,
        "mean_aggregate_gross_weight": float(pd.to_numeric(aggregate_target_totals.get("aggregate_gross_weight"), errors="coerce").mean()) if not aggregate_target_totals.empty else 0.0,
        "max_abs_symbol_weight": float(pd.to_numeric(aggregate_target_totals.get("max_abs_symbol_weight"), errors="coerce").max()) if not aggregate_target_totals.empty else 0.0,
        "max_event_target_turnover": float(pd.to_numeric(aggregate_target_totals.get("aggregate_target_turnover_vs_previous_event"), errors="coerce").max()) if not aggregate_target_totals.empty else 0.0,
        "mean_event_target_turnover": float(pd.to_numeric(aggregate_target_totals.get("aggregate_target_turnover_vs_previous_event"), errors="coerce").mean()) if not aggregate_target_totals.empty else 0.0,
        "latest_target_date_utc": str(aggregate_target_totals["date_utc"].iloc[-1]) if not aggregate_target_totals.empty else None,
    }
    artifact_paths = {
        "summary_json": str(output_root / "summary.json"),
        "phase_metrics_csv": str(output_root / "phase_metrics.csv"),
        "ensemble_metrics_csv": str(output_root / "ensemble_metrics.csv"),
        "sleeve_period_returns_csv": str(output_root / "sleeve_period_returns.csv"),
        "ensemble_period_returns_csv": str(output_root / "ensemble_period_returns.csv"),
        "sleeve_position_attribution_csv": str(output_root / "sleeve_position_attribution.csv"),
        "sleeve_paper_shadow_ledger_csv": str(output_root / "sleeve_paper_shadow_ledger.csv"),
        "aggregate_targets_by_event_csv": str(output_root / "aggregate_targets_by_event.csv"),
        "aggregate_target_totals_by_event_csv": str(output_root / "aggregate_target_totals_by_event.csv"),
        "phase_fast_reconciliation_csv": str(output_root / "phase_fast_reconciliation.csv"),
        "multiphase_execution_gap_policy_json": str(output_root / "multiphase_execution_gap_policy.json"),
        "true_daily_mtm_position_ledger_csv": str(output_root / "true_daily_mtm_position_ledger.csv"),
        "true_daily_mtm_returns_csv": str(output_root / "true_daily_mtm_returns.csv"),
        "true_daily_mtm_metrics_json": str(output_root / "true_daily_mtm_metrics.json"),
        "markdown_report": str(doc_path),
    }
    summary = {
        "schema": "hv_balanced_multiphase_sleeve_ensemble.v1",
        "generated_at_utc": utc_now_iso(),
        "status": "passed" if gate["status"] == "passed" else "blocked",
        "scenario": args.scenario,
        "config_path": fixed["config_path"],
        "as_of": fixed["as_of"],
        "funding_root": fixed["funding_root"],
        "phases": list(PHASES),
        "horizon_days": HORIZON_DAYS,
        "sleeve_weight": sleeve_weight,
        "raw_scored_row_count": int(len(raw_scored_frame)),
        "scored_row_count": int(len(scored_frame)),
        "dataset_manifest": fixed["dataset_manifest"],
        "dataset_reproduction": dataset_reproduction,
        "raw_baseline_reproduction": baseline_reproduction,
        "candidate_phase0_baseline_comparison": candidate_phase0_baseline_comparison,
        "multiphase_execution_gap_policy": multiphase_execution_gap_policy,
        "partition_path_compatibility": partition_path_compatibility,
        "frozen_row_alignment": frozen_row_alignment,
        "phase_metrics": records(phase_metrics),
        "ensemble_metrics": ensemble_metrics,
        "true_daily_mtm_metrics": daily_mtm_metrics,
        "true_daily_mtm_blockers": list(true_daily_mtm.get("blockers") or []),
        "target_book_summary": target_book_summary,
        "phase_fast_reconciliation": records(reconciliations),
        "gate": gate,
        "blockers": blockers,
        "artifact_paths": artifact_paths,
    }
    output_root.mkdir(parents=True, exist_ok=True)
    phase_metrics.to_csv(output_root / "phase_metrics.csv", index=False)
    ensemble_metrics_table.to_csv(output_root / "ensemble_metrics.csv", index=False)
    periods.to_csv(output_root / "sleeve_period_returns.csv", index=False)
    ensemble_periods.to_csv(output_root / "ensemble_period_returns.csv", index=False)
    positions.to_csv(output_root / "sleeve_position_attribution.csv", index=False)
    ledger.to_csv(output_root / "sleeve_paper_shadow_ledger.csv", index=False)
    aggregate_targets.to_csv(output_root / "aggregate_targets_by_event.csv", index=False)
    aggregate_target_totals.to_csv(output_root / "aggregate_target_totals_by_event.csv", index=False)
    reconciliations.to_csv(output_root / "phase_fast_reconciliation.csv", index=False)
    daily_mtm_position_ledger.to_csv(output_root / "true_daily_mtm_position_ledger.csv", index=False)
    daily_mtm_returns.to_csv(output_root / "true_daily_mtm_returns.csv", index=False)
    write_json(output_root / "true_daily_mtm_metrics.json", json_safe(daily_mtm_metrics))
    write_json(output_root / "multiphase_execution_gap_policy.json", json_safe(multiphase_execution_gap_policy))
    write_json(output_root / "summary.json", json_safe(summary))
    write_report(
        doc_path=doc_path,
        summary=json_safe(summary),
        phase_metrics=phase_metrics,
        ensemble_metrics_frame=ensemble_metrics_table,
        target_totals=aggregate_target_totals,
        daily_mtm_returns=daily_mtm_returns,
        reconciliations=reconciliations,
        artifact_paths=artifact_paths,
    )
    print(
        json.dumps(
            json_safe(
                {
                    "status": summary["status"],
                    "gate": gate,
                    "ensemble_metrics": ensemble_metrics,
                    "true_daily_mtm_metrics": daily_mtm_metrics,
                    "true_daily_mtm_blocker_count": len(true_daily_mtm.get("blockers") or []),
                    "multiphase_execution_gap_policy": {
                        "status": multiphase_execution_gap_policy.get("status"),
                        "excluded_symbols": multiphase_execution_gap_policy.get("excluded_symbols"),
                        "residual_data_gap_blocker_count": len(multiphase_execution_gap_policy.get("residual_data_gap_blockers") or []),
                    },
                    "target_book_summary": target_book_summary,
                    "artifact_paths": artifact_paths,
                    "blocker_count": len(blockers),
                }
            ),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
