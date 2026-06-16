from __future__ import annotations

import argparse
import copy
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
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import enhengclaw.quant_research.binance_canonical_h10d as h10d  # noqa: E402
from enhengclaw.quant_research.binance_canonical_h10d import (  # noqa: E402
    DEFAULT_STORE_ROOT as MODULE_DEFAULT_STORE_ROOT,
    _resolve_funding_root,
    _run_backtest,
    apply_selected_path_gap_symbol_exclusion,
    build_binance_canonical_dataset,
    load_strategy_config,
    prepare_scored_backtest_frame,
)


DEFAULT_INTERVALS = (5, 7, 10, 15, 20, 30)
DEFAULT_HV_BALANCED_CONFIG_PATH = (
    ROOT / "config" / "quant_research" / "binance_pit_top_mid_h10d_pruned3_hv_balanced_soft_budget.json"
)
DEFAULT_OUT_ROOT = ROOT / "artifacts" / "quant_research" / "rebalance_interval_sensitivity_20260518"
DEFAULT_DOC_PATH = (
    ROOT
    / "docs"
    / "quant_research"
    / "03_alpha_branches"
    / "hv_balanced_rebalance_interval_sensitivity_2026_05_18.md"
)
DEFAULT_FROZEN_REPORT = ROOT / "artifacts" / "qr" / "hv_balanced" / "validation_report.json"
DEFAULT_FROZEN_ROW_MEMBERSHIP = ROOT / "artifacts" / "qr" / "hv_balanced" / "universe_membership.csv"
BASELINE_METRIC_KEYS = (
    "net_return",
    "sharpe",
    "max_drawdown",
    "gross_return_before_costs",
    "fee_cost_return",
    "slippage_cost_return",
    "funding_cost_return",
    "turnover",
    "trade_count",
    "rebalance_count",
)
DATASET_REPRODUCTION_KEYS = ("symbol_scan_count", "selected_universe_count", "row_count", "timestamp_count")
ELIGIBILITY_DIAGNOSTIC_COLUMNS = (
    "binance_decision_eligible",
    "binance_pit_data_eligible",
    "binance_pit_top_long_eligible",
    "binance_pit_mid_short_eligible",
    "binance_pit_active_long_eligible",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a dedicated hv_balanced rebalance interval sensitivity sweep. "
            "Alpha scoring, PIT universe logic, eligibility, risk overlay columns, "
            "and execution cost scenario are held fixed; only target_horizon_bars "
            "is swept."
        )
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_HV_BALANCED_CONFIG_PATH)
    parser.add_argument(
        "--store-root",
        type=Path,
        default=None,
        help="Market-history root. Defaults to the frozen hv_balanced report store_root when available.",
    )
    parser.add_argument("--funding-root", type=Path, default=None)
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--intervals", nargs="+", type=int, default=list(DEFAULT_INTERVALS))
    parser.add_argument("--scenario", choices=["base", "stress"], default="base")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUT_ROOT)
    parser.add_argument("--doc-path", type=Path, default=DEFAULT_DOC_PATH)
    parser.add_argument("--baseline-report", type=Path, default=DEFAULT_FROZEN_REPORT)
    parser.add_argument(
        "--frozen-row-membership",
        type=Path,
        default=DEFAULT_FROZEN_ROW_MEMBERSHIP,
        help=(
            "Frozen hv_balanced universe_membership.csv. When present, the runner aligns the "
            "market-history feature rows to these (symbol, timestamp_ms) keys before PIT universe "
            "selection so repaired local market stores cannot add rows outside the frozen control."
        ),
    )
    parser.add_argument(
        "--no-frozen-row-alignment",
        action="store_true",
        help="Disable frozen row-key alignment. Intended only for data drift diagnostics.",
    )
    parser.add_argument("--baseline-tolerance", type=float, default=1e-8)
    parser.add_argument("--max-symbols", type=int, default=None)
    parser.add_argument("--top-n", type=int, default=None)
    parser.add_argument("--start-month", default=None)
    parser.add_argument("--end-month", default=None)
    return parser.parse_args()


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def resolve_repo_path(path: Path) -> Path:
    path = Path(path)
    return path if path.is_absolute() else (ROOT / path).resolve()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe(payload), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if pd.isna(value) if not isinstance(value, (str, bytes, dict, list, tuple)) else False:
        return None
    return value


def interval_config(config: dict[str, Any], interval_days: int) -> dict[str, Any]:
    output = copy.deepcopy(config)
    split = dict(output.get("split_realization") or {})
    split["interval"] = str(split.get("interval") or "1d")
    split["target_horizon_bars"] = int(interval_days)
    output["split_realization"] = split
    return output


def default_store_root_from_baseline(baseline_report: Path) -> Path:
    if baseline_report.exists():
        try:
            report = read_json(baseline_report)
            store_root = (report.get("dataset_manifest") or {}).get("store_root")
            if store_root:
                return Path(str(store_root))
        except (OSError, json.JSONDecodeError):
            pass
    return MODULE_DEFAULT_STORE_ROOT


def install_symbol_partition_compatibility_patch() -> dict[str, Any]:
    original = h10d._symbol_partition_paths

    def compatible_symbol_partition_paths(
        *,
        store_root: Path,
        symbol: str,
        start_month: str | None,
        end_month: str | None,
    ) -> list[Path]:
        symbol_root = Path(store_root) / "data" / h10d.MARKET_TYPE / symbol.upper()
        candidate_roots = [symbol_root / h10d.INTERVAL_1M, symbol_root]
        paths: list[Path] = []
        seen: set[str] = set()
        for root in candidate_roots:
            for path in sorted([*root.glob("*.parquet"), *root.glob("*.csv.gz")]):
                resolved = str(path.resolve())
                if resolved in seen:
                    continue
                month = h10d._partition_month(path)
                if month is None:
                    continue
                if start_month and month < start_month:
                    continue
                if end_month and month > end_month:
                    continue
                seen.add(resolved)
                paths.append(path)
        return sorted(paths)

    h10d._symbol_partition_paths = compatible_symbol_partition_paths
    return {
        "applied": True,
        "scope": "runner_only_monkey_patch",
        "reason": "frozen local store contains both SYMBOL/1m/*.parquet and SYMBOL/*.parquet layouts",
        "original_function": getattr(original, "__name__", str(original)),
    }


def load_frozen_row_keys(path: Path) -> dict[str, set[int]]:
    resolved = resolve_repo_path(path)
    if not resolved.exists():
        return {}
    membership = pd.read_csv(resolved, usecols=["timestamp_ms", "usdm_symbol"])
    if membership.empty:
        return {}
    membership["timestamp_ms"] = pd.to_numeric(membership["timestamp_ms"], errors="coerce")
    membership["usdm_symbol"] = membership["usdm_symbol"].astype(str).str.upper()
    membership = membership.dropna(subset=["timestamp_ms", "usdm_symbol"]).copy()
    membership["timestamp_ms"] = membership["timestamp_ms"].astype("int64")
    row_keys: dict[str, set[int]] = {}
    for symbol, group in membership.groupby("usdm_symbol", sort=True):
        row_keys[str(symbol)] = set(group["timestamp_ms"].astype("int64").tolist())
    return row_keys


def install_frozen_feature_row_alignment_patch(path: Path | None, *, disabled: bool) -> dict[str, Any]:
    if disabled:
        return {"applied": False, "reason": "disabled_by_cli"}
    if path is None:
        return {"applied": False, "reason": "no_frozen_row_membership_path"}
    resolved = resolve_repo_path(path)
    row_keys = load_frozen_row_keys(resolved)
    if not row_keys:
        return {
            "applied": False,
            "reason": "missing_or_empty_frozen_row_membership",
            "path": str(resolved),
        }

    original = h10d.build_symbol_feature_frame

    def frozen_aligned_build_symbol_feature_frame(*args: Any, **kwargs: Any) -> tuple[pd.DataFrame, dict[str, Any]]:
        panel, audit = original(*args, **kwargs)
        symbol = str(kwargs.get("symbol") or audit.get("symbol") or "").upper()
        allowed = row_keys.get(symbol)
        before = int(len(panel))
        if allowed is None or panel.empty or "timestamp_ms" not in panel.columns:
            audit["frozen_row_alignment"] = {
                "applied": False,
                "reason": "symbol_not_in_frozen_membership" if allowed is None else "empty_or_missing_timestamp",
                "before_row_count": before,
                "after_row_count": before,
            }
            return panel, audit
        timestamps = pd.to_numeric(panel["timestamp_ms"], errors="coerce")
        mask = timestamps.isin(allowed)
        aligned = panel.loc[mask].copy()
        after = int(len(aligned))
        audit["feature_row_count_before_frozen_alignment"] = audit.get("feature_row_count")
        audit["feature_row_count"] = after
        audit["frozen_row_alignment"] = {
            "applied": True,
            "path": str(resolved),
            "before_row_count": before,
            "after_row_count": after,
            "dropped_row_count": before - after,
        }
        if before > 0 and after <= 0:
            audit["status"] = "empty_after_frozen_row_alignment"
        return aligned, audit

    h10d.build_symbol_feature_frame = frozen_aligned_build_symbol_feature_frame
    return {
        "applied": True,
        "scope": "runner_only_monkey_patch",
        "path": str(resolved),
        "symbol_count": len(row_keys),
        "row_key_count": sum(len(items) for items in row_keys.values()),
        "original_function": getattr(original, "__name__", str(original)),
    }


def load_fixed_scored_frame(args: argparse.Namespace, *, store_root: Path) -> dict[str, Any]:
    config_path = resolve_repo_path(args.config)
    config = load_strategy_config(config_path)
    config["strategy_label"] = str(config.get("strategy_label") or "hv_balanced")
    strategy_profile = dict(config.get("strategy_profile") or {})
    strategy_profile.setdefault("decision_eligible_column", "binance_decision_eligible")
    config["strategy_profile"] = strategy_profile
    as_of = args.as_of or str(config.get("as_of") or "2026-04-30")
    funding_root = _resolve_funding_root(config=config, funding_root=args.funding_root)
    dataset = build_binance_canonical_dataset(
        store_root=store_root,
        as_of=as_of,
        config=config,
        funding_root=funding_root,
        symbols=None,
        max_symbols=args.max_symbols,
        top_n=args.top_n,
        start_month=args.start_month,
        end_month=args.end_month,
    )
    scored_frame, scoring_audit = prepare_scored_backtest_frame(dataset.panel, config=config)
    blockers: list[dict[str, Any]] = list(dataset.dataset_manifest.get("blockers") or [])
    blockers.extend(scoring_audit.get("blockers") or [])
    execution_gap_policy_audit: dict[str, Any] = {"mode": "none", "applied": False}
    if not scored_frame.empty:
        scored_frame, execution_gap_policy_audit = apply_selected_path_gap_symbol_exclusion(scored_frame, config=config)
    else:
        blockers.append({"code": "empty_scored_backtest_frame"})
    return {
        "config": config,
        "config_path": str(config_path),
        "as_of": as_of,
        "funding_root": str(funding_root),
        "dataset_manifest": dataset.dataset_manifest,
        "gap_audit_summary": dataset.gap_audit.get("summary", {}),
        "feature_manifest": dataset.feature_manifest,
        "scoring_audit": scoring_audit,
        "execution_gap_policy": execution_gap_policy_audit,
        "scored_frame": scored_frame,
        "blockers": blockers,
    }


def metric_row(interval_days: int, metrics: dict[str, Any]) -> dict[str, Any]:
    row = {"interval_days": int(interval_days), "scenario": str(metrics.get("execution_cost_model", {}).get("scenario", ""))}
    for key in BASELINE_METRIC_KEYS:
        value = metrics.get(key)
        row[key] = value
    row["evaluation_step_bars"] = metrics.get("evaluation_step_bars")
    row["latency_bars"] = metrics.get("latency_bars")
    row["execution_venue"] = metrics.get("execution_venue")
    row["trade_notional_usd_total"] = metrics.get("trade_notional_usd_total")
    row["max_trade_participation_rate"] = metrics.get("max_trade_participation_rate")
    row["max_inventory_participation_rate"] = metrics.get("max_inventory_participation_rate")
    row["max_participation_rate"] = metrics.get("max_participation_rate")
    row["capacity_breach_count"] = metrics.get("capacity_breach_count")
    row["data_gap_blocker_count"] = len(metrics.get("data_gap_blockers") or [])
    return row


def period_rows(interval_days: int, metrics: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    equity = 1.0
    peak = 1.0
    for offset, period in enumerate(metrics.get("periods") or [], start=1):
        timestamp_ms = int(period["timestamp_ms"])
        net_return = float(period.get("net_period_return", 0.0) or 0.0)
        equity *= 1.0 + net_return
        peak = max(peak, equity)
        drawdown = 0.0 if peak <= 0.0 else (peak - equity) / peak
        date_utc = pd.to_datetime(timestamp_ms, unit="ms", utc=True).date().isoformat()
        row = {
            "interval_days": int(interval_days),
            "period_index": int(offset),
            "timestamp_ms": timestamp_ms,
            "date_utc": date_utc,
            "equity": float(equity),
            "drawdown": float(drawdown),
        }
        for key in (
            "gross_return_before_costs",
            "net_period_return",
            "fee_cost_return",
            "slippage_cost_return",
            "funding_cost_return",
            "borrow_cost_return",
            "trade_notional_usd",
            "turnover",
            "delta_weight",
            "trade_participation_rate",
            "inventory_participation_rate",
            "max_participation_rate",
            "capacity_breach_count",
            "available_quote_volume_usd",
            "portfolio_throttle_multiplier",
            "portfolio_throttle_drawdown",
        ):
            if key in period:
                row[key] = period.get(key)
        row["data_gap_blocker_count"] = len(period.get("data_gap_blockers") or [])
        rows.append(row)
    return rows


def build_paired_mtm(periods: pd.DataFrame, intervals: list[int]) -> pd.DataFrame:
    if periods.empty:
        return pd.DataFrame(columns=["date_utc"])
    dates = sorted(str(item) for item in periods["date_utc"].dropna().unique().tolist())
    wide = pd.DataFrame({"date_utc": dates})
    for interval in intervals:
        group = periods.loc[periods["interval_days"].eq(interval)].copy()
        if group.empty:
            wide[f"equity_h{interval}d"] = 1.0
            wide[f"mtm_return_h{interval}d"] = 0.0
            continue
        curve = (
            group.sort_values(["timestamp_ms", "period_index"])
            .groupby("date_utc", as_index=False)
            .tail(1)[["date_utc", "equity"]]
            .rename(columns={"equity": f"equity_h{interval}d"})
        )
        wide = wide.merge(curve, on="date_utc", how="left")
        equity_col = f"equity_h{interval}d"
        wide[equity_col] = pd.to_numeric(wide[equity_col], errors="coerce").ffill().fillna(1.0)
        prior = wide[equity_col].shift(1).fillna(1.0)
        wide[f"mtm_return_h{interval}d"] = wide[equity_col] / prior.replace(0.0, np.nan) - 1.0
        wide[f"mtm_return_h{interval}d"] = wide[f"mtm_return_h{interval}d"].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    if 10 in intervals and "equity_h10d" in wide.columns:
        for interval in intervals:
            if interval == 10:
                continue
            equity_col = f"equity_h{interval}d"
            if equity_col in wide.columns:
                wide[f"equity_delta_h{interval}d_vs_h10d"] = wide[equity_col] - wide["equity_h10d"]
    return wide


def build_delta_vs_10d(paired_mtm: pd.DataFrame, intervals: list[int]) -> pd.DataFrame:
    if paired_mtm.empty or "equity_h10d" not in paired_mtm.columns:
        return pd.DataFrame(columns=["date_utc"])
    output = paired_mtm[["date_utc", "equity_h10d"]].copy()
    for interval in intervals:
        if interval == 10:
            continue
        equity_col = f"equity_h{interval}d"
        return_col = f"mtm_return_h{interval}d"
        if equity_col not in paired_mtm.columns:
            continue
        output[equity_col] = paired_mtm[equity_col]
        output[f"equity_delta_h{interval}d_vs_h10d"] = paired_mtm[equity_col] - paired_mtm["equity_h10d"]
        if return_col in paired_mtm.columns and "mtm_return_h10d" in paired_mtm.columns:
            output[f"mtm_return_delta_h{interval}d_vs_h10d"] = paired_mtm[return_col] - paired_mtm["mtm_return_h10d"]
    return output


def compare_baseline(
    *,
    ten_day_metrics: dict[str, Any] | None,
    baseline_report_path: Path,
    tolerance: float,
) -> dict[str, Any]:
    if ten_day_metrics is None:
        return {"status": "blocked", "reason": "10d interval missing from sweep"}
    if not baseline_report_path.exists():
        return {"status": "blocked", "reason": f"baseline report not found: {baseline_report_path}"}
    report = read_json(baseline_report_path)
    frozen = dict((report.get("metrics") or {}).get("base") or {})
    comparisons = {}
    mismatches = []
    for key in BASELINE_METRIC_KEYS:
        current = ten_day_metrics.get(key)
        expected = frozen.get(key)
        delta = None
        status = "missing"
        if current is not None and expected is not None:
            delta = float(current) - float(expected)
            status = "match" if abs(delta) <= tolerance else "mismatch"
        comparisons[key] = {
            "current": current,
            "frozen": expected,
            "delta": delta,
            "status": status,
        }
        if status != "match":
            mismatches.append(key)
    return {
        "status": "passed" if not mismatches else "blocked",
        "tolerance": float(tolerance),
        "baseline_report_path": str(baseline_report_path),
        "frozen_strategy_label": report.get("strategy_label"),
        "frozen_status": report.get("status"),
        "comparisons": comparisons,
        "mismatches": mismatches,
    }


def compare_dataset_reproduction(*, current_manifest: dict[str, Any], baseline_report_path: Path) -> dict[str, Any]:
    if not baseline_report_path.exists():
        return {"status": "blocked", "reason": f"baseline report not found: {baseline_report_path}"}
    report = read_json(baseline_report_path)
    frozen_manifest = dict(report.get("dataset_manifest") or {})
    comparisons = {}
    mismatches = []
    for key in DATASET_REPRODUCTION_KEYS:
        current = current_manifest.get(key)
        frozen = frozen_manifest.get(key)
        status = "match" if current == frozen else "mismatch"
        comparisons[key] = {
            "current": current,
            "frozen": frozen,
            "status": status,
        }
        if status != "match":
            mismatches.append(key)
    return {
        "status": "passed" if not mismatches else "blocked",
        "baseline_report_path": str(baseline_report_path),
        "comparisons": comparisons,
        "mismatches": mismatches,
    }


def scored_frame_diagnostics(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {"row_count": 0, "subject_count": 0, "timestamp_count": 0, "eligibility_true_counts": {}}
    diagnostics: dict[str, Any] = {
        "row_count": int(len(frame)),
        "subject_count": int(frame["subject"].nunique()) if "subject" in frame.columns else 0,
        "timestamp_count": int(frame["timestamp_ms"].nunique()) if "timestamp_ms" in frame.columns else 0,
        "eligibility_true_counts": {},
    }
    for column in ELIGIBILITY_DIAGNOSTIC_COLUMNS:
        if column in frame.columns:
            diagnostics["eligibility_true_counts"][column] = int(_truthy_count(frame[column]))
    if "funding_sample_count" in frame.columns:
        funding_samples = pd.to_numeric(frame["funding_sample_count"], errors="coerce").fillna(0.0)
        diagnostics["funding_sample_positive_row_count"] = int(funding_samples.gt(0.0).sum())
        diagnostics["funding_sample_positive_ratio"] = float(funding_samples.gt(0.0).mean())
    if "score" in frame.columns:
        score = pd.to_numeric(frame["score"], errors="coerce").replace([np.inf, -np.inf], np.nan)
        diagnostics["score_nonzero_row_count"] = int(score.fillna(0.0).ne(0.0).sum())
        diagnostics["score_valid_row_count"] = int(score.notna().sum())
    return diagnostics


def _truthy_count(series: pd.Series) -> int:
    if pd.api.types.is_bool_dtype(series):
        return int(series.fillna(False).astype("bool").sum())
    text = series.astype(str).str.strip().str.lower()
    return int(text.isin({"1", "true", "yes", "y"}).sum())


def add_metric_deltas(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    baseline = next((row for row in rows if int(row["interval_days"]) == 10), None)
    if baseline is None:
        return rows
    for row in rows:
        for key in ("net_return", "sharpe", "max_drawdown", "turnover", "trade_count", "rebalance_count"):
            current = row.get(key)
            base = baseline.get(key)
            row[f"{key}_delta_vs_10d"] = None if current is None or base is None else float(current) - float(base)
    return rows


def run_sweep(scored_frame: pd.DataFrame, config: dict[str, Any], intervals: list[int], scenario: str) -> dict[str, Any]:
    metrics_by_interval: dict[int, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    all_period_rows: list[dict[str, Any]] = []
    for interval in intervals:
        run_config = interval_config(config, interval)
        metrics = _run_backtest(scored_frame, config=run_config, scenario=scenario, include_periods=True)
        metrics_by_interval[int(interval)] = metrics
        rows.append(metric_row(int(interval), metrics))
        all_period_rows.extend(period_rows(int(interval), metrics))
    rows = add_metric_deltas(rows)
    metrics_df = pd.DataFrame(rows).sort_values("interval_days").reset_index(drop=True)
    periods_df = pd.DataFrame(all_period_rows).sort_values(["interval_days", "timestamp_ms"]).reset_index(drop=True)
    paired_mtm = build_paired_mtm(periods_df, intervals)
    delta_vs_10d = build_delta_vs_10d(paired_mtm, intervals)
    return {
        "metrics_by_interval": metrics_by_interval,
        "interval_metrics": metrics_df,
        "period_returns_long": periods_df,
        "paired_mtm_curve": paired_mtm,
        "paired_delta_vs_10d": delta_vs_10d,
    }


def dataframe_to_markdown(frame: pd.DataFrame, columns: list[str]) -> str:
    if frame.empty:
        return "_empty_"
    display = frame.loc[:, [column for column in columns if column in frame.columns]].copy()
    for column in display.columns:
        if pd.api.types.is_float_dtype(display[column]):
            display[column] = display[column].map(lambda value: "" if pd.isna(value) else f"{float(value):.6f}")
    headers = list(display.columns)
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for _, row in display.iterrows():
        lines.append("| " + " | ".join(str(row[column]) for column in headers) + " |")
    return "\n".join(lines)


def write_report(
    *,
    doc_path: Path,
    summary: dict[str, Any],
    metrics: pd.DataFrame,
    artifact_paths: dict[str, str],
) -> None:
    baseline = summary.get("baseline_reproduction") or {}
    dataset_reproduction = summary.get("dataset_reproduction") or {}
    diagnostics = summary.get("scored_frame_diagnostics") or {}
    dataset = summary.get("dataset_manifest") or {}
    frozen_row_alignment = summary.get("frozen_row_alignment") or {}
    blockers = summary.get("blockers") or []
    blocker_lines = "\n".join(f"- `{item.get('code', 'blocker')}`: {item}" for item in blockers) or "- none"
    metric_table = dataframe_to_markdown(
        metrics,
        [
            "interval_days",
            "net_return",
            "net_return_delta_vs_10d",
            "sharpe",
            "sharpe_delta_vs_10d",
            "max_drawdown",
            "max_drawdown_delta_vs_10d",
            "turnover",
            "trade_count",
            "rebalance_count",
            "data_gap_blocker_count",
        ],
    )
    lines = [
        "# hv_balanced rebalance interval sensitivity",
        "",
        f"- generated_at_utc: `{summary['generated_at_utc']}`",
        f"- hard_status: `{summary['status']}`",
        f"- scenario: `{summary['scenario']}`",
        f"- fixed_config: `{summary['config_path']}`",
        f"- score_frame_reused_across_intervals: `{summary['score_frame_reused_across_intervals']}`",
        f"- frozen_row_alignment_applied: `{frozen_row_alignment.get('applied')}`",
        f"- selected_universe_count: `{dataset.get('selected_universe_count')}`",
        f"- scored_row_count: `{summary['scored_row_count']}`",
        f"- dataset_reproduction_status: `{dataset_reproduction.get('status')}`",
        f"- baseline_reproduction_status: `{baseline.get('status')}`",
        f"- funding_sample_positive_row_count: `{diagnostics.get('funding_sample_positive_row_count')}`",
        "",
        "## Metric table",
        "",
        metric_table,
        "",
        "## Guardrails",
        "",
        "- Alpha score, feature columns, feature weights, PIT universe policy, PIT eligibility, risk brake columns, reference capital, and execution cost scenario are fixed from the frozen hv_balanced config.",
        "- The only swept field is `split_realization.target_horizon_bars`.",
        "- Paired MTM is aligned on the union of fill dates and forward-filled between rebalance events; it is for curve comparison, not for adding extra trade decisions.",
        "- Promotion use is blocked unless the 10d row reproduces the frozen hv_balanced base metrics within tolerance.",
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
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    doc_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    intervals = sorted(dict.fromkeys(int(item) for item in args.intervals))
    if intervals != list(DEFAULT_INTERVALS):
        raise SystemExit(f"Refusing non-contract intervals: observed={intervals}, required={list(DEFAULT_INTERVALS)}")
    output_root = resolve_repo_path(args.output_root)
    doc_path = resolve_repo_path(args.doc_path)
    baseline_report = resolve_repo_path(args.baseline_report)
    store_root = Path(args.store_root).resolve() if args.store_root else default_store_root_from_baseline(baseline_report)
    partition_path_compatibility = install_symbol_partition_compatibility_patch()
    frozen_row_alignment = install_frozen_feature_row_alignment_patch(
        args.frozen_row_membership,
        disabled=bool(args.no_frozen_row_alignment),
    )
    fixed = load_fixed_scored_frame(args, store_root=store_root)
    config = fixed["config"]
    scored_frame = fixed["scored_frame"]
    sweep = run_sweep(scored_frame, config, intervals, args.scenario) if not scored_frame.empty else {
        "metrics_by_interval": {},
        "interval_metrics": pd.DataFrame(),
        "period_returns_long": pd.DataFrame(),
        "paired_mtm_curve": pd.DataFrame(),
        "paired_delta_vs_10d": pd.DataFrame(),
    }

    metrics_by_interval: dict[int, dict[str, Any]] = sweep["metrics_by_interval"]
    baseline_reproduction = compare_baseline(
        ten_day_metrics=metrics_by_interval.get(10),
        baseline_report_path=baseline_report,
        tolerance=float(args.baseline_tolerance),
    )
    interval_blockers = []
    for interval, metrics in metrics_by_interval.items():
        gaps = list(metrics.get("data_gap_blockers") or [])
        if gaps:
            interval_blockers.append(
                {
                    "code": "interval_execution_data_gap_blockers",
                    "interval_days": int(interval),
                    "data_gap_blocker_count": len(gaps),
                    "sample": gaps[:10],
                }
            )
        if int(metrics.get("rebalance_count", 0) or 0) <= 0:
            interval_blockers.append({"code": "interval_no_rebalances", "interval_days": int(interval)})
        if int(metrics.get("trade_count", 0) or 0) <= 0:
            interval_blockers.append({"code": "interval_no_trades", "interval_days": int(interval)})
    blockers = list(fixed["blockers"]) + interval_blockers
    dataset_reproduction = compare_dataset_reproduction(
        current_manifest=fixed["dataset_manifest"],
        baseline_report_path=baseline_report,
    )
    if dataset_reproduction.get("status") != "passed":
        blockers.append(
            {
                "code": "frozen_dataset_reproduction_failed",
                "detail": dataset_reproduction,
            }
        )
    if baseline_reproduction.get("status") != "passed":
        blockers.append(
            {
                "code": "frozen_10d_baseline_reproduction_failed",
                "detail": baseline_reproduction,
            }
        )
    status = "passed" if not blockers else "blocked"
    artifact_paths = {
        "summary_json": str(output_root / "summary.json"),
        "interval_metrics_csv": str(output_root / "interval_metrics.csv"),
        "period_returns_long_csv": str(output_root / "period_returns_long.csv"),
        "paired_mtm_curve_csv": str(output_root / "paired_mtm_curve.csv"),
        "paired_delta_vs_10d_csv": str(output_root / "paired_delta_vs_10d.csv"),
        "scored_frame_diagnostics_json": str(output_root / "scored_frame_diagnostics.json"),
        "markdown_report": str(doc_path),
    }
    summary = {
        "schema": "hv_balanced_rebalance_interval_sensitivity.v1",
        "generated_at_utc": utc_now_iso(),
        "status": status,
        "scenario": args.scenario,
        "contract_intervals_days": intervals,
        "config_path": fixed["config_path"],
        "as_of": fixed["as_of"],
        "funding_root": fixed["funding_root"],
        "score_frame_reused_across_intervals": True,
        "scored_row_count": int(len(scored_frame)),
        "dataset_manifest": fixed["dataset_manifest"],
        "gap_audit_summary": fixed["gap_audit_summary"],
        "scoring_audit": fixed["scoring_audit"],
        "execution_gap_policy": fixed["execution_gap_policy"],
        "partition_path_compatibility": partition_path_compatibility,
        "frozen_row_alignment": frozen_row_alignment,
        "dataset_reproduction": dataset_reproduction,
        "scored_frame_diagnostics": scored_frame_diagnostics(scored_frame),
        "baseline_reproduction": baseline_reproduction,
        "blockers": blockers,
        "artifact_paths": artifact_paths,
    }

    output_root.mkdir(parents=True, exist_ok=True)
    sweep["interval_metrics"].to_csv(output_root / "interval_metrics.csv", index=False)
    sweep["period_returns_long"].to_csv(output_root / "period_returns_long.csv", index=False)
    sweep["paired_mtm_curve"].to_csv(output_root / "paired_mtm_curve.csv", index=False)
    sweep["paired_delta_vs_10d"].to_csv(output_root / "paired_delta_vs_10d.csv", index=False)
    write_json(output_root / "scored_frame_diagnostics.json", summary["scored_frame_diagnostics"])
    write_json(output_root / "summary.json", summary)
    write_report(doc_path=doc_path, summary=summary, metrics=sweep["interval_metrics"], artifact_paths=artifact_paths)
    print(
        json.dumps(
            {
                "status": status,
                "interval_metrics": json_safe(sweep["interval_metrics"].to_dict(orient="records")),
                "baseline_reproduction": baseline_reproduction,
                "artifact_paths": artifact_paths,
                "blocker_count": len(blockers),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
