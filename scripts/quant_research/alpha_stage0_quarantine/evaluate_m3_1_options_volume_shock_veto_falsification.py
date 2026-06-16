from __future__ import annotations

import argparse
import json
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

warnings.filterwarnings(
    "ignore",
    category=FutureWarning,
    message="Downcasting object dtype arrays on .fillna",
)

from scripts.quant_research.alpha_stage0_quarantine import audit_m3_1_options_regime_stage0 as stage0  # noqa: E402


CONTRACT_VERSION = "m3_1_options_volume_shock_veto_falsification.v1"
DEFAULT_AS_OF = "2026-05-03"
DEFAULT_FLAG_COLUMN = "r8_high_option_volume_shock_flag"
DEFAULT_PANEL_PATH = ROOT / "artifacts" / "quant_research" / "coinglass" / "options_regime_panel_1d.csv.gz"
DEFAULT_OUTPUT_DIR = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "factor_reports"
    / "2026-05-09-m3-1-options-volume-shock-veto-falsification"
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "R-8b strict falsification for the quarantined M3.1 options-volume "
            "short-veto market gate."
        )
    )
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--target-horizon-bars", type=int, default=10)
    parser.add_argument("--panel-path", type=Path, default=DEFAULT_PANEL_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--flag-column", default=DEFAULT_FLAG_COLUMN)
    parser.add_argument("--iterations", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20260509)
    parser.add_argument("--min-edge", type=float, default=0.005)
    parser.add_argument("--min-active-date-count", type=int, default=30)
    parser.add_argument("--min-active-date-fraction", type=float, default=0.05)
    parser.add_argument("--max-active-date-fraction", type=float, default=0.40)
    parser.add_argument("--delay-retention-threshold", type=float, default=0.50)
    parser.add_argument("--holdout-positive-fraction", type=float, default=0.70)
    parser.add_argument("--bucket-min-active-dates", type=int, default=10)
    parser.add_argument("--bucket-min-inactive-dates", type=int, default=10)
    return parser


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_options_panel(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"options regime panel not found: {path}")
    panel = pd.read_csv(path)
    if "date_utc" not in panel.columns:
        raise ValueError(f"options regime panel missing date_utc: {path}")
    panel = panel.copy()
    panel["date_utc"] = pd.to_datetime(panel["date_utc"], utc=True, errors="coerce").dt.normalize()
    return panel.dropna(subset=["date_utc"]).sort_values("date_utc").reset_index(drop=True)


def _as_bool(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    text = series.astype(str).str.strip().str.lower()
    return text.isin({"true", "1", "yes", "y"})


def _load_aligned_short_rows(
    *,
    as_of: str,
    target_horizon_bars: int,
    panel_path: Path,
    flag_column: str,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    parent_short_rows, parent_meta = stage0._load_parent_short_rows(
        as_of=as_of,
        target_horizon_bars=target_horizon_bars,
    )
    panel = _read_options_panel(panel_path)
    if flag_column not in panel.columns:
        raise ValueError(f"options regime panel missing flag column: {flag_column}")

    parent_short_rows = parent_short_rows.copy()
    parent_short_rows["date_utc"] = pd.to_datetime(
        parent_short_rows["date_utc"],
        utc=True,
        errors="coerce",
    ).dt.normalize()
    keep = [
        "date_utc",
        flag_column,
        "r8_max_option_volume_z90",
        "btc_option_volume_usd_total",
        "eth_option_volume_usd_total",
        "btc_option_vs_futures_oi_ratio",
        "eth_option_vs_futures_oi_ratio",
    ]
    keep = [column for column in keep if column in panel.columns]
    aligned = parent_short_rows.merge(panel[keep], on="date_utc", how="left")
    aligned[flag_column] = _as_bool(aligned[flag_column])
    horizon_col = f"forward_{target_horizon_bars}d_log_return"
    aligned = aligned.dropna(subset=["date_utc", horizon_col]).copy()
    meta = {
        "parent": parent_meta,
        "panel_path": str(panel_path),
        "panel_rows": int(len(panel)),
        "panel_first_date": str(panel["date_utc"].min().date()) if len(panel) else None,
        "panel_last_date": str(panel["date_utc"].max().date()) if len(panel) else None,
        "aligned_rows": int(len(aligned)),
        "aligned_dates": int(aligned["date_utc"].nunique()),
        "flag_column": flag_column,
    }
    return aligned, panel, meta


def _date_level(
    rows: pd.DataFrame,
    *,
    flag_column: str,
    target_horizon_bars: int,
) -> pd.DataFrame:
    horizon_col = f"forward_{target_horizon_bars}d_log_return"
    if rows.empty:
        return pd.DataFrame(columns=["date_utc", horizon_col, "forward_1d_log_return", flag_column])
    local = rows.dropna(subset=[horizon_col]).copy()
    local[flag_column] = _as_bool(local[flag_column])
    agg = {horizon_col: "mean", flag_column: "max"}
    if "forward_1d_log_return" in local.columns:
        agg["forward_1d_log_return"] = "mean"
    out = local.groupby("date_utc", as_index=False).agg(agg).sort_values("date_utc").reset_index(drop=True)
    out[flag_column] = _as_bool(out[flag_column])
    return out


def _edge_summary(
    date_level: pd.DataFrame,
    *,
    flag_column: str,
    target_horizon_bars: int,
) -> dict[str, Any]:
    horizon_col = f"forward_{target_horizon_bars}d_log_return"
    if date_level.empty or flag_column not in date_level.columns or horizon_col not in date_level.columns:
        return {
            "date_count": 0,
            "active_date_count": 0,
            "inactive_date_count": 0,
            "active_date_fraction": 0.0,
            "veto_short_edge_active_minus_inactive": None,
        }
    flag = _as_bool(date_level[flag_column])
    active = date_level.loc[flag]
    inactive = date_level.loc[~flag]
    active_mean = stage0._safe_mean(active, horizon_col)
    inactive_mean = stage0._safe_mean(inactive, horizon_col)
    edge = None if active_mean is None or inactive_mean is None else float(active_mean - inactive_mean)
    return {
        "date_count": int(len(date_level)),
        "active_date_count": int(len(active)),
        "inactive_date_count": int(len(inactive)),
        "active_date_fraction": float(flag.mean()) if len(flag) else 0.0,
        "active_next_h_mean": active_mean,
        "inactive_next_h_mean": inactive_mean,
        "veto_short_edge_active_minus_inactive": edge,
    }


def _passes_edge_contract(
    summary: dict[str, Any],
    *,
    min_edge: float,
    min_active_date_count: int,
    min_active_date_fraction: float,
    max_active_date_fraction: float,
) -> bool:
    edge = summary.get("veto_short_edge_active_minus_inactive")
    return bool(
        edge is not None
        and float(edge) >= float(min_edge)
        and int(summary.get("active_date_count") or 0) >= int(min_active_date_count)
        and float(summary.get("active_date_fraction") or 0.0) >= float(min_active_date_fraction)
        and float(summary.get("active_date_fraction") or 0.0) <= float(max_active_date_fraction)
    )


def _delayed_activation_test(
    date_level: pd.DataFrame,
    *,
    flag_column: str,
    target_horizon_bars: int,
    observed_edge: float,
    min_edge: float,
    min_active_date_count: int,
    min_active_date_fraction: float,
    max_active_date_fraction: float,
    delay_retention_threshold: float,
) -> dict[str, Any]:
    delayed = date_level.copy()
    delayed[flag_column] = _as_bool(delayed[flag_column]).shift(1).fillna(False).astype(bool)
    summary = _edge_summary(delayed, flag_column=flag_column, target_horizon_bars=target_horizon_bars)
    edge = summary.get("veto_short_edge_active_minus_inactive")
    retention = None if edge is None or observed_edge <= 0 else float(edge / observed_edge)
    passed = bool(
        _passes_edge_contract(
            summary,
            min_edge=min_edge,
            min_active_date_count=min_active_date_count,
            min_active_date_fraction=min_active_date_fraction,
            max_active_date_fraction=max_active_date_fraction,
        )
        and retention is not None
        and retention >= delay_retention_threshold
    )
    return {
        "passed": passed,
        "retention_vs_observed": retention,
        "retention_threshold": float(delay_retention_threshold),
        **summary,
    }


def _contiguous_split_test(
    date_level: pd.DataFrame,
    *,
    flag_column: str,
    target_horizon_bars: int,
    min_edge: float,
    min_active_date_count: int,
) -> dict[str, Any]:
    dates = np.asarray(sorted(date_level["date_utc"].unique()))
    eras = np.array_split(dates, 3)
    rows: list[dict[str, Any]] = []
    for idx, era_dates in enumerate(eras):
        local = date_level[date_level["date_utc"].isin(set(era_dates))]
        summary = _edge_summary(local, flag_column=flag_column, target_horizon_bars=target_horizon_bars)
        summary["era_index"] = int(idx)
        rows.append(summary)
    eligible = [row for row in rows if int(row.get("active_date_count") or 0) >= int(min_active_date_count)]
    edge_values = [
        float(row["veto_short_edge_active_minus_inactive"])
        for row in eligible
        if row.get("veto_short_edge_active_minus_inactive") is not None
    ]
    return {
        "passed": bool(len(eligible) == 3 and all(edge >= float(min_edge) for edge in edge_values)),
        "eligible_era_count": int(len(eligible)),
        "min_edge": float(min(edge_values)) if edge_values else None,
        "by_era": rows,
    }


def _symbol_holdout_test(
    rows: pd.DataFrame,
    *,
    flag_column: str,
    target_horizon_bars: int,
    min_edge: float,
    positive_fraction_threshold: float,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for subject in sorted(rows["subject"].astype(str).unique()):
        held = rows[rows["subject"].astype(str).ne(subject)].copy()
        summary = _edge_summary(
            _date_level(held, flag_column=flag_column, target_horizon_bars=target_horizon_bars),
            flag_column=flag_column,
            target_horizon_bars=target_horizon_bars,
        )
        results.append({"held_out_subject": subject, **summary})
    edges = [
        float(row["veto_short_edge_active_minus_inactive"])
        for row in results
        if row.get("veto_short_edge_active_minus_inactive") is not None
    ]
    if not edges:
        return {"passed": False, "reason": "no_valid_holdout_edges", "by_subject": results}
    values = np.asarray(edges, dtype="float64")
    positive_fraction = float(np.mean(values >= float(min_edge)))
    return {
        "passed": bool(float(values.min()) > 0.0 and positive_fraction >= float(positive_fraction_threshold)),
        "positive_fraction_at_min_edge": positive_fraction,
        "positive_fraction_threshold": float(positive_fraction_threshold),
        "min_edge": float(values.min()),
        "median_edge": float(np.median(values)),
        "by_subject": results,
    }


def _liquidity_bucket_test(
    rows: pd.DataFrame,
    *,
    flag_column: str,
    target_horizon_bars: int,
    min_edge: float,
    min_active_dates: int,
    min_inactive_dates: int,
) -> dict[str, Any]:
    bucket_rows: list[dict[str, Any]] = []
    for bucket in sorted(rows.get("liquidity_bucket", pd.Series(dtype=str)).dropna().astype(str).unique()):
        local_rows = rows[rows["liquidity_bucket"].astype(str).eq(bucket)]
        summary = _edge_summary(
            _date_level(local_rows, flag_column=flag_column, target_horizon_bars=target_horizon_bars),
            flag_column=flag_column,
            target_horizon_bars=target_horizon_bars,
        )
        eligible = (
            int(summary.get("active_date_count") or 0) >= int(min_active_dates)
            and int(summary.get("inactive_date_count") or 0) >= int(min_inactive_dates)
        )
        edge = summary.get("veto_short_edge_active_minus_inactive")
        bucket_rows.append(
            {
                "liquidity_bucket": bucket,
                "eligible": bool(eligible),
                "subject_count": int(local_rows["subject"].astype(str).nunique()) if "subject" in local_rows else None,
                **summary,
                "bucket_passed": bool(eligible and edge is not None and float(edge) >= float(min_edge)),
            }
        )
    eligible_rows = [row for row in bucket_rows if row["eligible"]]
    edge_values = [
        float(row["veto_short_edge_active_minus_inactive"])
        for row in eligible_rows
        if row.get("veto_short_edge_active_minus_inactive") is not None
    ]
    return {
        "passed": bool(len(eligible_rows) >= 2 and all(row["bucket_passed"] for row in eligible_rows)),
        "eligible_bucket_count": int(len(eligible_rows)),
        "positive_eligible_bucket_count": int(sum(row["bucket_passed"] for row in eligible_rows)),
        "min_eligible_bucket_edge": float(min(edge_values)) if edge_values else None,
        "by_bucket": bucket_rows,
    }


def _random_control(
    date_level: pd.DataFrame,
    *,
    flag_column: str,
    target_horizon_bars: int,
    observed_edge: float,
    iterations: int,
    seed: int,
    mode: str,
) -> dict[str, Any]:
    horizon_col = f"forward_{target_horizon_bars}d_log_return"
    rng = np.random.default_rng(seed)
    flags = _as_bool(date_level[flag_column]).to_numpy(dtype=bool)
    returns = pd.to_numeric(date_level[horizon_col], errors="coerce").to_numpy(dtype="float64")
    valid = np.isfinite(returns)
    flags = flags[valid]
    returns = returns[valid]
    if len(returns) == 0 or flags.sum() == 0 or (~flags).sum() == 0:
        return {"passed": False, "reason": "empty_or_degenerate_control", "iterations": int(iterations)}

    values: list[float] = []
    for _ in range(max(int(iterations), 1)):
        if mode == "active_date_time_shuffle":
            shuffled_flags = rng.permutation(flags)
            shuffled_returns = returns
        elif mode == "return_date_shuffle":
            shuffled_flags = flags
            shuffled_returns = rng.permutation(returns)
        else:
            raise ValueError(f"unknown random control mode: {mode}")
        if shuffled_flags.sum() == 0 or (~shuffled_flags).sum() == 0:
            continue
        values.append(float(shuffled_returns[shuffled_flags].mean() - shuffled_returns[~shuffled_flags].mean()))
    if not values:
        return {"passed": False, "reason": "no_valid_random_edges", "iterations": int(iterations)}
    arr = np.asarray(values, dtype="float64")
    q95 = float(np.quantile(arr, 0.95))
    p_value = float((np.sum(arr >= float(observed_edge)) + 1.0) / (len(arr) + 1.0))
    return {
        "passed": bool(float(observed_edge) > q95 and p_value <= 0.05),
        "iterations": int(len(arr)),
        "random_mean_edge": float(arr.mean()),
        "random_q95_edge": q95,
        "empirical_p_value_random_ge_observed": p_value,
    }


def _evaluate(
    rows: pd.DataFrame,
    *,
    flag_column: str,
    target_horizon_bars: int,
    iterations: int,
    seed: int,
    min_edge: float,
    min_active_date_count: int,
    min_active_date_fraction: float,
    max_active_date_fraction: float,
    delay_retention_threshold: float,
    holdout_positive_fraction: float,
    bucket_min_active_dates: int,
    bucket_min_inactive_dates: int,
) -> dict[str, Any]:
    dates = _date_level(rows, flag_column=flag_column, target_horizon_bars=target_horizon_bars)
    observed = _edge_summary(dates, flag_column=flag_column, target_horizon_bars=target_horizon_bars)
    observed_edge = observed.get("veto_short_edge_active_minus_inactive")
    if observed_edge is None:
        return {
            "status": "failed",
            "credible_incremental_edge": False,
            "blocker_codes": ["observed_edge_missing"],
            "observed": observed,
            "tests": {},
        }

    observed_pass = _passes_edge_contract(
        observed,
        min_edge=min_edge,
        min_active_date_count=min_active_date_count,
        min_active_date_fraction=min_active_date_fraction,
        max_active_date_fraction=max_active_date_fraction,
    )
    tests = {
        "observed_stage0_contract": {
            "passed": observed_pass,
            "min_edge": float(min_edge),
            "min_active_date_count": int(min_active_date_count),
            "min_active_date_fraction": float(min_active_date_fraction),
            "max_active_date_fraction": float(max_active_date_fraction),
            **observed,
        },
        "delayed_activation": _delayed_activation_test(
            dates,
            flag_column=flag_column,
            target_horizon_bars=target_horizon_bars,
            observed_edge=float(observed_edge),
            min_edge=min_edge,
            min_active_date_count=min_active_date_count,
            min_active_date_fraction=min_active_date_fraction,
            max_active_date_fraction=max_active_date_fraction,
            delay_retention_threshold=delay_retention_threshold,
        ),
        "contiguous_era_split": _contiguous_split_test(
            dates,
            flag_column=flag_column,
            target_horizon_bars=target_horizon_bars,
            min_edge=min_edge,
            min_active_date_count=min_active_date_count,
        ),
        "symbol_holdout": _symbol_holdout_test(
            rows,
            flag_column=flag_column,
            target_horizon_bars=target_horizon_bars,
            min_edge=min_edge,
            positive_fraction_threshold=holdout_positive_fraction,
        ),
        "liquidity_bucket_consistency": _liquidity_bucket_test(
            rows,
            flag_column=flag_column,
            target_horizon_bars=target_horizon_bars,
            min_edge=min_edge,
            min_active_dates=bucket_min_active_dates,
            min_inactive_dates=bucket_min_inactive_dates,
        ),
        "active_date_time_shuffle": _random_control(
            dates,
            flag_column=flag_column,
            target_horizon_bars=target_horizon_bars,
            observed_edge=float(observed_edge),
            iterations=iterations,
            seed=seed + 101,
            mode="active_date_time_shuffle",
        ),
        "return_date_shuffle": _random_control(
            dates,
            flag_column=flag_column,
            target_horizon_bars=target_horizon_bars,
            observed_edge=float(observed_edge),
            iterations=iterations,
            seed=seed + 202,
            mode="return_date_shuffle",
        ),
    }
    blocker_codes = [name + "_failed" for name, payload in tests.items() if not bool(payload.get("passed"))]
    return {
        "status": "cleared" if not blocker_codes else "failed",
        "credible_incremental_edge": not blocker_codes,
        "blocker_codes": blocker_codes,
        "observed": observed,
        "tests": tests,
    }


def _decision(result: dict[str, Any], *, label: str = DEFAULT_FLAG_COLUMN) -> dict[str, Any]:
    cleared = result.get("status") == "cleared"
    blockers = list(result.get("blocker_codes") or [])
    if cleared:
        next_action = (
            "R-8b cleared strict falsification; implement a separate parent-level "
            "short-exposure throttle simulator before any manifest decision."
        )
    else:
        next_action = (
            "Fail closed; keep the options volume-shock veto as quarantined "
            "mechanism evidence, not a parent overlay or manifest A/B."
        )
    return {
        "status": "cleared" if cleared else "failed",
        "alpha_rerun_allowed": bool(cleared),
        "manifest_ab_allowed": False,
        "strict_cleared_variants": [str(label)] if cleared else [],
        "blocker_codes": blockers,
        "next_action": next_action,
    }


def _json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if pd.isna(value):
        return None
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def run(args: argparse.Namespace) -> dict[str, Any]:
    rows, panel, input_meta = _load_aligned_short_rows(
        as_of=str(args.as_of),
        target_horizon_bars=int(args.target_horizon_bars),
        panel_path=Path(args.panel_path),
        flag_column=str(args.flag_column),
    )
    result = _evaluate(
        rows,
        flag_column=str(args.flag_column),
        target_horizon_bars=int(args.target_horizon_bars),
        iterations=max(int(args.iterations), 1),
        seed=int(args.seed),
        min_edge=float(args.min_edge),
        min_active_date_count=int(args.min_active_date_count),
        min_active_date_fraction=float(args.min_active_date_fraction),
        max_active_date_fraction=float(args.max_active_date_fraction),
        delay_retention_threshold=float(args.delay_retention_threshold),
        holdout_positive_fraction=float(args.holdout_positive_fraction),
        bucket_min_active_dates=int(args.bucket_min_active_dates),
        bucket_min_inactive_dates=int(args.bucket_min_inactive_dates),
    )
    report = {
        "contract_version": CONTRACT_VERSION,
        "generated_at_utc": _now_utc(),
        "as_of": str(args.as_of),
        "canonical_parent": "v5_rw_bridge_no_overlay_h10d",
        "target_horizon_bars": int(args.target_horizon_bars),
        "candidate": {
            "label": str(args.flag_column),
            "source": "CoinGlass aggregate BTC/ETH option volume z90 market gate",
            "landing_shape": "short-exposure veto/throttle when active",
            "promotion_boundary": (
                "market-level exposure gate only; not a cross-sectional rank factor and "
                "not a manifest A/B without a separate parent-throttle simulator"
            ),
        },
        "input_meta": {
            **input_meta,
            "panel_flag_fraction": (
                float(_as_bool(panel[str(args.flag_column)]).mean()) if str(args.flag_column) in panel.columns else None
            ),
        },
        "thresholds": {
            "iterations": max(int(args.iterations), 1),
            "seed": int(args.seed),
            "min_edge": float(args.min_edge),
            "min_active_date_count": int(args.min_active_date_count),
            "min_active_date_fraction": float(args.min_active_date_fraction),
            "max_active_date_fraction": float(args.max_active_date_fraction),
            "delay_retention_threshold": float(args.delay_retention_threshold),
            "holdout_positive_fraction": float(args.holdout_positive_fraction),
            "bucket_min_active_dates": int(args.bucket_min_active_dates),
            "bucket_min_inactive_dates": int(args.bucket_min_inactive_dates),
        },
        "strict_falsification": {str(args.flag_column): result},
        "decision": _decision(result, label=str(args.flag_column)),
    }
    return report


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report = run(args)
    output_path = output_dir / "m3_1_options_volume_shock_veto_falsification.json"
    output_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, default=_json_default),
        encoding="utf-8",
    )
    result = report["strict_falsification"][str(args.flag_column)]
    compact = {
        "report_path": str(output_path),
        "decision": report["decision"],
        "observed": result.get("observed"),
        "tests": {
            name: {
                "passed": payload.get("passed"),
                "edge": payload.get("veto_short_edge_active_minus_inactive")
                or payload.get("min_edge")
                or payload.get("min_eligible_bucket_edge"),
                "p_value": payload.get("empirical_p_value_random_ge_observed"),
            }
            for name, payload in result.get("tests", {}).items()
        },
    }
    print(json.dumps(compact, indent=2, sort_keys=True, default=_json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
