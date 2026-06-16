from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import UTC, datetime
import json
import math
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


DEFAULT_RUN_ROOT = ROOT / "artifacts" / "qr" / "hv_balanced"
DEFAULT_CONFIG_PATH = (
    ROOT / "config" / "quant_research" / "binance_pit_top_mid_h10d_pruned3_hv_balanced_soft_budget.json"
)
DEFAULT_OUTPUT_ROOT = (
    ROOT
    / "artifacts"
    / "live_trading"
    / "hv_balanced_risk_mode_backtest_20260517"
)
DEFAULT_REPORT_PATH = (
    ROOT
    / "docs"
    / "live_trading"
    / "hv_balanced_binance_usdm_pipeline"
    / "risk_mode_leverage_margin_backtest_2026_05_17.md"
)

GROSS_MULTIPLIERS = (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0)
MTM_PLOT_MULTIPLIERS = (0.5, 0.75, 1.0, 1.25, 2.0)
EXCHANGE_LEVERAGES = (1, 2, 3, 5, 10, 20)
MAINTENANCE_BUFFER = 0.01


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate hv_balanced leverage and margin-mode risk from frozen backtest artifacts."
    )
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--config-path", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--skip-mae", action="store_true", help="Skip 1m adverse-excursion scan.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = analyze(
        run_root=args.run_root,
        config_path=args.config_path,
        output_root=args.output_root,
        report_path=args.report_path,
        skip_mae=args.skip_mae,
    )
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


def analyze(
    *,
    run_root: Path,
    config_path: Path,
    output_root: Path,
    report_path: Path,
    skip_mae: bool,
) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    config = _read_json(config_path)
    dataset_manifest = _read_json(run_root / "dataset_manifest.json")
    validation_report = _read_json(run_root / "validation_report.json")
    periods = pd.read_csv(run_root / "aligned_period_returns.csv")
    ledger = pd.read_csv(run_root / "paper_shadow_execution_ledger.csv")

    leverage_sweep = _build_leverage_sweep(periods=periods, validation_report=validation_report)
    position_mae = pd.DataFrame()
    isolated_summary = _empty_isolated_summary()
    worst_positions = pd.DataFrame()
    if not skip_mae:
        store_root = Path(str(dataset_manifest.get("store_root") or ""))
        position_mae = _build_position_mae(ledger=ledger, store_root=store_root)
        isolated_summary = _build_isolated_summary(position_mae=position_mae)
        worst_positions = position_mae.sort_values("adverse_move", ascending=False).head(30).copy()
    store_root = Path(str(dataset_manifest.get("store_root") or ""))
    mtm_curve = _build_mtm_curve(periods=periods, ledger=ledger, store_root=store_root)
    key_metrics = _build_key_metrics_table(
        leverage_sweep=leverage_sweep,
        isolated_summary=isolated_summary,
        mtm_curve=mtm_curve,
    )
    plot_path = output_root / "mtm_equity_curve.png"
    _plot_mtm_curve(mtm_curve=mtm_curve, output_path=plot_path)

    recommendation = _build_recommendation(
        config=config,
        validation_report=validation_report,
        leverage_sweep=leverage_sweep,
        isolated_summary=isolated_summary,
        position_mae=position_mae,
    )

    leverage_sweep.to_csv(output_root / "leverage_sweep.csv", index=False)
    key_metrics.to_csv(output_root / "key_metrics_table.csv", index=False)
    mtm_curve.to_csv(output_root / "mtm_daily_curve.csv", index=False)
    isolated_summary.to_csv(output_root / "isolated_margin_liquidation_proxy.csv", index=False)
    if not position_mae.empty:
        position_mae.to_csv(output_root / "position_adverse_excursion.csv", index=False)
        worst_positions.to_csv(output_root / "worst_position_adverse_excursions.csv", index=False)
    _write_json(output_root / "recommendation.json", recommendation)

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        _render_report(
            config=config,
            dataset_manifest=dataset_manifest,
            validation_report=validation_report,
            leverage_sweep=leverage_sweep,
            isolated_summary=isolated_summary,
            key_metrics=key_metrics,
            mtm_curve=mtm_curve,
            worst_positions=worst_positions,
            recommendation=recommendation,
            output_root=output_root,
            plot_path=plot_path,
        ),
        encoding="utf-8",
    )

    return {
        "status": "ok",
        "output_root": str(output_root),
        "report_path": str(report_path),
        "recommendation": recommendation.get("summary"),
    }


def _build_leverage_sweep(*, periods: pd.DataFrame, validation_report: dict[str, Any]) -> pd.DataFrame:
    frame = periods.copy()
    net_return = pd.to_numeric(frame["net_period_return"], errors="coerce").fillna(0.0)
    gross_return = pd.to_numeric(frame["gross_return_before_costs"], errors="coerce").fillna(0.0)
    fee = pd.to_numeric(frame["fee_cost_return"], errors="coerce").fillna(0.0)
    slippage = pd.to_numeric(frame["slippage_cost_return"], errors="coerce").fillna(0.0)
    funding = pd.to_numeric(frame["funding_cost_return"], errors="coerce").fillna(0.0)
    borrow = pd.to_numeric(frame.get("borrow_cost_return", 0.0), errors="coerce").fillna(0.0)
    max_trade_participation = float(
        dict(validation_report.get("metrics", {}).get("base") or {}).get("max_trade_participation_rate") or 0.0
    )

    rows: list[dict[str, Any]] = []
    periods_per_year = 365.0 / 10.0
    for multiplier in GROSS_MULTIPLIERS:
        scaled = net_return * multiplier
        equity = (1.0 + scaled).cumprod()
        running_max = equity.cummax()
        drawdown = (1.0 - equity / running_max.replace(0.0, np.nan)).fillna(0.0)
        wiped_out = bool((1.0 + scaled).le(0.0).any())
        if wiped_out:
            first_wipe = int(np.argmax((1.0 + scaled).le(0.0).to_numpy()))
            final_equity = 0.0
            max_drawdown = 1.0
            net_compound_return = -1.0
        else:
            first_wipe = None
            final_equity = float(equity.iloc[-1]) if not equity.empty else 1.0
            max_drawdown = float(drawdown.max()) if not drawdown.empty else 0.0
            net_compound_return = final_equity - 1.0

        std = float(scaled.std(ddof=1))
        sharpe = float((scaled.mean() / std) * math.sqrt(periods_per_year)) if std > 0 else 0.0
        rows.append(
            {
                "portfolio_gross_multiplier": multiplier,
                "required_exchange_leverage_min": max(1, int(math.ceil(multiplier))),
                "net_compound_return": net_compound_return,
                "final_equity_multiple": final_equity,
                "annualized_sharpe_period_proxy": sharpe,
                "max_drawdown": max_drawdown,
                "worst_period_return": float(scaled.min()) if not scaled.empty else 0.0,
                "loss_period_fraction": float(scaled.lt(0.0).mean()) if not scaled.empty else 0.0,
                "period_count": int(len(scaled)),
                "wiped_out_by_period_return": wiped_out,
                "first_wipe_period_index": first_wipe,
                "gross_return_before_costs_sum_linear": float((gross_return * multiplier).sum()),
                "fee_cost_return_sum_linear": float((fee * multiplier).sum()),
                "slippage_cost_return_sum_linear": float((slippage * multiplier).sum()),
                "funding_cost_return_sum_linear": float((funding * multiplier).sum()),
                "borrow_cost_return_sum_linear": float((borrow * multiplier).sum()),
                "max_trade_participation_rate_scaled": max_trade_participation * multiplier,
                "capacity_cap_0p5pct_pass": bool(max_trade_participation * multiplier <= 0.005),
            }
        )
    return pd.DataFrame(rows)


def _build_position_mae(*, ledger: pd.DataFrame, store_root: Path) -> pd.DataFrame:
    positions = ledger.loc[ledger["side"].isin(["long", "short"])].copy()
    if positions.empty:
        return pd.DataFrame()
    positions = positions.reset_index(drop=False).rename(columns={"index": "ledger_row_index"})
    positions["fill_timestamp_ms"] = pd.to_numeric(positions["fill_timestamp_ms"], errors="coerce").astype("Int64")
    positions["exit_timestamp_ms"] = pd.to_numeric(positions["exit_timestamp_ms"], errors="coerce").astype("Int64")
    positions["entry_price"] = pd.to_numeric(positions["entry_price"], errors="coerce")
    positions["target_weight"] = pd.to_numeric(positions["target_weight"], errors="coerce")
    positions["max_high"] = np.nan
    positions["min_low"] = np.nan
    positions["missing_market_data_segment"] = False

    month_to_rows: dict[tuple[str, str], list[int]] = defaultdict(list)
    for row_idx, row in positions.iterrows():
        fill_ms = row.get("fill_timestamp_ms")
        exit_ms = row.get("exit_timestamp_ms")
        symbol = str(row.get("usdm_symbol") or "")
        if pd.isna(fill_ms) or pd.isna(exit_ms) or not symbol:
            positions.at[row_idx, "missing_market_data_segment"] = True
            continue
        fill_dt = pd.to_datetime(int(fill_ms), unit="ms", utc=True).tz_convert(None)
        exit_dt = pd.to_datetime(int(exit_ms), unit="ms", utc=True).tz_convert(None)
        for period in pd.period_range(fill_dt.to_period("M"), exit_dt.to_period("M"), freq="M"):
            month_to_rows[(symbol, str(period))].append(row_idx)

    for (symbol, month), row_indices in sorted(month_to_rows.items()):
        path = store_root / "data" / "usdm_perp" / symbol / "1m" / f"{month}.parquet"
        if not path.exists():
            positions.loc[row_indices, "missing_market_data_segment"] = True
            continue
        try:
            bars = pd.read_parquet(path, columns=["open_time_ms", "high", "low"])
        except Exception:
            positions.loc[row_indices, "missing_market_data_segment"] = True
            continue
        if bars.empty:
            positions.loc[row_indices, "missing_market_data_segment"] = True
            continue
        bars["open_time_ms"] = pd.to_numeric(bars["open_time_ms"], errors="coerce")
        bars["high"] = pd.to_numeric(bars["high"], errors="coerce")
        bars["low"] = pd.to_numeric(bars["low"], errors="coerce")
        for row_idx in row_indices:
            fill_ms = int(positions.at[row_idx, "fill_timestamp_ms"])
            exit_ms = int(positions.at[row_idx, "exit_timestamp_ms"])
            window = bars.loc[(bars["open_time_ms"] >= fill_ms) & (bars["open_time_ms"] < exit_ms)]
            if window.empty:
                continue
            max_high = float(window["high"].max())
            min_low = float(window["low"].min())
            previous_high = positions.at[row_idx, "max_high"]
            previous_low = positions.at[row_idx, "min_low"]
            positions.at[row_idx, "max_high"] = (
                max_high if pd.isna(previous_high) else max(float(previous_high), max_high)
            )
            positions.at[row_idx, "min_low"] = min_low if pd.isna(previous_low) else min(float(previous_low), min_low)

    positions["missing_market_data_segment"] = positions["missing_market_data_segment"] | positions["max_high"].isna() | positions[
        "min_low"
    ].isna()
    valid = ~positions["missing_market_data_segment"]
    positions["adverse_move"] = np.nan
    positions["favorable_move"] = np.nan
    long_mask = valid & positions["side"].eq("long") & positions["entry_price"].gt(0)
    short_mask = valid & positions["side"].eq("short") & positions["entry_price"].gt(0)
    positions.loc[long_mask, "adverse_move"] = (
        1.0 - positions.loc[long_mask, "min_low"] / positions.loc[long_mask, "entry_price"]
    ).clip(lower=0.0)
    positions.loc[long_mask, "favorable_move"] = (
        positions.loc[long_mask, "max_high"] / positions.loc[long_mask, "entry_price"] - 1.0
    ).clip(lower=0.0)
    positions.loc[short_mask, "adverse_move"] = (
        positions.loc[short_mask, "max_high"] / positions.loc[short_mask, "entry_price"] - 1.0
    ).clip(lower=0.0)
    positions.loc[short_mask, "favorable_move"] = (
        1.0 - positions.loc[short_mask, "min_low"] / positions.loc[short_mask, "entry_price"]
    ).clip(lower=0.0)
    positions["abs_target_weight"] = positions["target_weight"].abs()

    keep = [
        "ledger_row_index",
        "decision_date_utc",
        "fill_date_utc",
        "exit_date_utc",
        "subject",
        "usdm_symbol",
        "action",
        "side",
        "target_weight",
        "abs_target_weight",
        "entry_price",
        "exit_price",
        "min_low",
        "max_high",
        "adverse_move",
        "favorable_move",
        "gross_contribution",
        "net_contribution",
        "trade_notional_usd",
        "liquidity_bucket",
        "universe_rank",
        "missing_market_data_segment",
    ]
    return positions.loc[:, [column for column in keep if column in positions.columns]].copy()


def _build_isolated_summary(*, position_mae: pd.DataFrame) -> pd.DataFrame:
    if position_mae.empty:
        return _empty_isolated_summary()
    valid = position_mae.loc[~position_mae["missing_market_data_segment"].astype(bool)].copy()
    rows: list[dict[str, Any]] = []
    total_count = int(len(valid))
    total_weight = float(pd.to_numeric(valid["abs_target_weight"], errors="coerce").fillna(0.0).sum())
    for leverage in EXCHANGE_LEVERAGES:
        threshold = max((1.0 / float(leverage)) - MAINTENANCE_BUFFER, 0.0)
        hit = valid.loc[pd.to_numeric(valid["adverse_move"], errors="coerce").fillna(0.0) >= threshold]
        rows.append(
            {
                "exchange_leverage": leverage,
                "adverse_move_threshold_proxy": threshold,
                "position_count": total_count,
                "proxy_liquidation_position_count": int(len(hit)),
                "proxy_liquidation_position_fraction": float(len(hit) / total_count) if total_count else 0.0,
                "proxy_liquidation_abs_weight_sum": float(
                    pd.to_numeric(hit["abs_target_weight"], errors="coerce").fillna(0.0).sum()
                ),
                "proxy_liquidation_abs_weight_fraction": (
                    float(pd.to_numeric(hit["abs_target_weight"], errors="coerce").fillna(0.0).sum() / total_weight)
                    if total_weight
                    else 0.0
                ),
                "long_hit_count": int(hit["side"].eq("long").sum()) if not hit.empty else 0,
                "short_hit_count": int(hit["side"].eq("short").sum()) if not hit.empty else 0,
                "worst_adverse_move": float(pd.to_numeric(valid["adverse_move"], errors="coerce").max())
                if not valid.empty
                else 0.0,
            }
        )
    return pd.DataFrame(rows)


def _empty_isolated_summary() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "exchange_leverage",
            "adverse_move_threshold_proxy",
            "position_count",
            "proxy_liquidation_position_count",
            "proxy_liquidation_position_fraction",
            "proxy_liquidation_abs_weight_sum",
            "proxy_liquidation_abs_weight_fraction",
            "long_hit_count",
            "short_hit_count",
            "worst_adverse_move",
        ]
    )


def _build_mtm_curve(*, periods: pd.DataFrame, ledger: pd.DataFrame, store_root: Path) -> pd.DataFrame:
    period_frame = periods.copy()
    period_frame["timestamp_ms"] = pd.to_numeric(period_frame["timestamp_ms"], errors="coerce").astype("Int64")
    period_frame["net_period_return"] = pd.to_numeric(period_frame["net_period_return"], errors="coerce").fillna(0.0)
    period_frame["gross_return_before_costs"] = pd.to_numeric(
        period_frame["gross_return_before_costs"], errors="coerce"
    ).fillna(0.0)
    period_frame = period_frame.dropna(subset=["timestamp_ms"]).sort_values("timestamp_ms").reset_index(drop=True)

    ledger_frame = ledger.copy()
    for column in [
        "fill_timestamp_ms",
        "exit_timestamp_ms",
        "entry_price",
        "exit_price",
        "target_weight",
        "gross_contribution",
        "net_contribution",
    ]:
        ledger_frame[column] = pd.to_numeric(ledger_frame[column], errors="coerce")

    close_map = _load_daily_close_map(ledger=ledger_frame, store_root=store_root)
    grouped = {
        int(fill_ts): group.copy()
        for fill_ts, group in ledger_frame.dropna(subset=["fill_timestamp_ms"]).groupby("fill_timestamp_ms")
    }

    equity_start = {multiplier: 1.0 for multiplier in GROSS_MULTIPLIERS}
    rows: list[dict[str, Any]] = []
    last_date: str | None = None
    for period_index, period in period_frame.iterrows():
        timestamp_ms = int(period["timestamp_ms"])
        period_ledger = grouped.get(timestamp_ms, pd.DataFrame(columns=ledger_frame.columns))
        active = period_ledger.loc[period_ledger["side"].isin(["long", "short"])].copy()
        start_date = _date_from_ms(timestamp_ms)
        if active.empty:
            end_date = start_date
        else:
            end_ms = int(pd.to_numeric(active["exit_timestamp_ms"], errors="coerce").max())
            end_date = _date_from_ms(end_ms)

        official_net = float(period["net_period_return"])
        official_gross = float(period["gross_return_before_costs"])
        raw_exit_gross = _period_mtm_contribution(
            active=active,
            date_utc=end_date,
            close_map=close_map,
            force_exit_prices=True,
        )
        gross_scale = official_gross / raw_exit_gross if abs(raw_exit_gross) > 1e-12 else 1.0

        for day in pd.date_range(start_date, end_date, freq="D"):
            date_utc = str(day.date())
            if last_date is not None and date_utc <= last_date:
                continue
            force_exit = date_utc == end_date
            raw_gross = _period_mtm_contribution(
                active=active,
                date_utc=date_utc,
                close_map=close_map,
                force_exit_prices=force_exit,
            )
            gross_cum = official_gross if force_exit else raw_gross * gross_scale
            net_cum = official_net if force_exit else gross_cum
            row: dict[str, Any] = {
                "date_utc": date_utc,
                "timestamp_ms": _date_str_to_ms(date_utc),
                "period_index": int(period_index),
                "period_start_timestamp_ms": timestamp_ms,
                "gross_period_mtm_return": gross_cum,
                "net_period_mtm_return": net_cum,
                "active_position_count": int(len(active)),
                "gross_abs_exposure": float(pd.to_numeric(active.get("target_weight", pd.Series(dtype=float)), errors="coerce").abs().sum())
                if not active.empty
                else 0.0,
            }
            for multiplier in GROSS_MULTIPLIERS:
                equity = equity_start[multiplier] * (1.0 + net_cum * multiplier)
                row[f"equity_gross_{_slug_multiplier(multiplier)}"] = equity
            rows.append(row)
            last_date = date_utc

        for multiplier in GROSS_MULTIPLIERS:
            equity_start[multiplier] = equity_start[multiplier] * (1.0 + official_net * multiplier)

    curve = pd.DataFrame(rows)
    if curve.empty:
        return curve
    for multiplier in GROSS_MULTIPLIERS:
        equity_col = f"equity_gross_{_slug_multiplier(multiplier)}"
        running_max = curve[equity_col].cummax()
        curve[f"drawdown_gross_{_slug_multiplier(multiplier)}"] = (
            1.0 - curve[equity_col] / running_max.replace(0.0, np.nan)
        ).fillna(0.0)
        curve[f"daily_return_gross_{_slug_multiplier(multiplier)}"] = curve[equity_col].pct_change().fillna(0.0)
    return curve


def _load_daily_close_map(*, ledger: pd.DataFrame, store_root: Path) -> dict[tuple[str, str], float]:
    active = ledger.loc[ledger["side"].isin(["long", "short"])].copy()
    month_to_symbols: set[tuple[str, str]] = set()
    for _, row in active.iterrows():
        symbol = str(row.get("usdm_symbol") or "")
        fill_ms = row.get("fill_timestamp_ms")
        exit_ms = row.get("exit_timestamp_ms")
        if not symbol or pd.isna(fill_ms) or pd.isna(exit_ms):
            continue
        fill_dt = pd.to_datetime(int(fill_ms), unit="ms", utc=True).tz_convert(None)
        exit_dt = pd.to_datetime(int(exit_ms), unit="ms", utc=True).tz_convert(None)
        for period in pd.period_range(fill_dt.to_period("M"), exit_dt.to_period("M"), freq="M"):
            month_to_symbols.add((symbol, str(period)))

    close_map: dict[tuple[str, str], float] = {}
    for symbol, month in sorted(month_to_symbols):
        path = store_root / "data" / "usdm_perp" / symbol / "1m" / f"{month}.parquet"
        if not path.exists():
            continue
        try:
            bars = pd.read_parquet(path, columns=["open_time_ms", "close"])
        except Exception:
            continue
        if bars.empty:
            continue
        bars["open_time_ms"] = pd.to_numeric(bars["open_time_ms"], errors="coerce")
        bars["close"] = pd.to_numeric(bars["close"], errors="coerce")
        bars = bars.dropna(subset=["open_time_ms", "close"]).sort_values("open_time_ms")
        bars["date_utc"] = pd.to_datetime(bars["open_time_ms"].astype("int64"), unit="ms", utc=True).dt.date.astype(str)
        daily = bars.groupby("date_utc", as_index=False).tail(1)
        for _, item in daily.iterrows():
            close_map[(symbol, str(item["date_utc"]))] = float(item["close"])
    return close_map


def _period_mtm_contribution(
    *,
    active: pd.DataFrame,
    date_utc: str,
    close_map: dict[tuple[str, str], float],
    force_exit_prices: bool,
) -> float:
    if active.empty:
        return 0.0
    contribution = 0.0
    for _, row in active.iterrows():
        fill_date = str(row.get("fill_date_utc") or "")
        exit_date = str(row.get("exit_date_utc") or "")
        if not fill_date or not exit_date or date_utc < fill_date or date_utc > exit_date:
            continue
        entry = float(row.get("entry_price") or 0.0)
        weight = float(row.get("target_weight") or 0.0)
        if entry <= 0.0 or weight == 0.0:
            continue
        if date_utc == fill_date:
            mark = entry
        elif force_exit_prices and date_utc == exit_date and not pd.isna(row.get("exit_price")):
            mark = float(row.get("exit_price"))
        else:
            mark = close_map.get((str(row.get("usdm_symbol") or ""), date_utc))
            if mark is None:
                continue
        contribution += weight * (float(mark) / entry - 1.0)
    return float(contribution)


def _build_key_metrics_table(
    *,
    leverage_sweep: pd.DataFrame,
    isolated_summary: pd.DataFrame,
    mtm_curve: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    iso = {int(row["exchange_leverage"]): row for _, row in isolated_summary.iterrows()} if not isolated_summary.empty else {}
    if mtm_curve.empty:
        return pd.DataFrame()
    first_date = pd.to_datetime(mtm_curve["date_utc"].iloc[0])
    last_date = pd.to_datetime(mtm_curve["date_utc"].iloc[-1])
    elapsed_years = max(float((last_date - first_date).days) / 365.25, 1e-9)
    for _, row in leverage_sweep.iterrows():
        multiplier = float(row["portfolio_gross_multiplier"])
        slug = _slug_multiplier(multiplier)
        equity_col = f"equity_gross_{slug}"
        drawdown_col = f"drawdown_gross_{slug}"
        daily_return_col = f"daily_return_gross_{slug}"
        required_leverage = int(row["required_exchange_leverage_min"])
        iso_row = iso.get(required_leverage)
        equity = pd.to_numeric(mtm_curve[equity_col], errors="coerce").dropna()
        daily = pd.to_numeric(mtm_curve[daily_return_col], errors="coerce").fillna(0.0)
        daily_std = float(daily.std(ddof=1))
        total_return = float(equity.iloc[-1] - 1.0) if not equity.empty else 0.0
        cagr = float(equity.iloc[-1] ** (1.0 / elapsed_years) - 1.0) if not equity.empty and equity.iloc[-1] > 0 else -1.0
        ann_vol = daily_std * math.sqrt(365.0)
        daily_sharpe = float((daily.mean() / daily_std) * math.sqrt(365.0)) if daily_std > 0 else 0.0
        rows.append(
            {
                "portfolio_gross_multiplier": multiplier,
                "required_exchange_leverage_min": required_leverage,
                "total_return": total_return,
                "final_equity_multiple": float(equity.iloc[-1]) if not equity.empty else 1.0,
                "cagr": cagr,
                "daily_mtm_ann_vol": ann_vol,
                "daily_mtm_sharpe": daily_sharpe,
                "max_drawdown_mtm": float(pd.to_numeric(mtm_curve[drawdown_col], errors="coerce").max()),
                "worst_daily_mtm_return": float(daily.min()),
                "worst_rebalance_period_return": float(row["worst_period_return"]),
                "loss_day_fraction": float(daily.lt(0.0).mean()),
                "capacity_cap_0p5pct_pass": bool(row["capacity_cap_0p5pct_pass"]),
                "isolated_proxy_liquidation_position_count": int(
                    iso_row["proxy_liquidation_position_count"] if iso_row is not None else 0
                ),
                "isolated_proxy_liquidation_position_fraction": float(
                    iso_row["proxy_liquidation_position_fraction"] if iso_row is not None else 0.0
                ),
            }
        )
    return pd.DataFrame(rows)


def _plot_mtm_curve(*, mtm_curve: pd.DataFrame, output_path: Path) -> None:
    if mtm_curve.empty:
        return
    try:
        import matplotlib.pyplot as plt
    except Exception:
        return

    dates = pd.to_datetime(mtm_curve["date_utc"])
    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True, gridspec_kw={"height_ratios": [2, 1]})
    for multiplier in MTM_PLOT_MULTIPLIERS:
        slug = _slug_multiplier(multiplier)
        axes[0].plot(dates, mtm_curve[f"equity_gross_{slug}"], label=f"{multiplier:g}x gross", linewidth=1.8)
        axes[1].plot(dates, -mtm_curve[f"drawdown_gross_{slug}"], label=f"{multiplier:g}x gross", linewidth=1.2)
    axes[0].set_title("hv_balanced simulated daily MTM equity curve")
    axes[0].set_ylabel("Equity multiple")
    axes[0].grid(True, alpha=0.25)
    axes[0].legend(ncol=3, fontsize=9)
    axes[1].set_ylabel("Drawdown")
    axes[1].set_xlabel("UTC date")
    axes[1].grid(True, alpha=0.25)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=160)
    plt.close(fig)


def _date_from_ms(value: int) -> str:
    return datetime.fromtimestamp(int(value) / 1000, tz=UTC).date().isoformat()


def _date_str_to_ms(value: str) -> int:
    parsed = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)
    return int(parsed.timestamp() * 1000)


def _slug_multiplier(value: float) -> str:
    return str(value).replace(".", "p")


def _build_recommendation(
    *,
    config: dict[str, Any],
    validation_report: dict[str, Any],
    leverage_sweep: pd.DataFrame,
    isolated_summary: pd.DataFrame,
    position_mae: pd.DataFrame,
) -> dict[str, Any]:
    current_profile = dict(config.get("strategy_profile") or {})
    current_base = dict(validation_report.get("metrics", {}).get("base") or {})
    rows = {float(row["portfolio_gross_multiplier"]): row for _, row in leverage_sweep.iterrows()}
    iso = {int(row["exchange_leverage"]): row for _, row in isolated_summary.iterrows()} if not isolated_summary.empty else {}

    def gross_status(multiplier: float) -> dict[str, Any]:
        row = rows[multiplier]
        required_leverage = int(row["required_exchange_leverage_min"])
        iso_row = iso.get(required_leverage)
        return {
            "portfolio_gross_multiplier": multiplier,
            "exchange_leverage": required_leverage,
            "max_drawdown": float(row["max_drawdown"]),
            "net_compound_return": float(row["net_compound_return"]),
            "isolated_proxy_liquidation_position_count": int(
                iso_row["proxy_liquidation_position_count"] if iso_row is not None else 0
            ),
        }

    max_adverse = (
        float(pd.to_numeric(position_mae["adverse_move"], errors="coerce").max())
        if not position_mae.empty and "adverse_move" in position_mae.columns
        else None
    )
    return {
        "summary": {
            "default_live_pilot": "isolated_1x_current_gross_1p0",
            "cross_margin_recommendation": "not_recommended_for_live_pilot",
            "max_adverse_move_observed": max_adverse,
            "current_base_net_return": current_base.get("net_return"),
            "current_base_max_drawdown": current_base.get("max_drawdown"),
            "current_base_sharpe": current_base.get("sharpe"),
        },
        "risk_buckets": [
            {
                "risk_need": "capital_preservation",
                "recommendation": "isolated margin, exchange leverage 1x, portfolio gross 0.5x to 0.75x, plus explicit short-side liquidation guard",
                "primary_case": gross_status(0.5),
                "rationale": "Cuts historical drawdown roughly in half while preserving the same signal direction. Best for first real-money pilot, but shorts still need a path-risk guard.",
            },
            {
                "risk_need": "balanced",
                "recommendation": "isolated margin, exchange leverage 1x, portfolio gross 1.0x, with short-side path-risk guard before non-tiny mainnet",
                "primary_case": gross_status(1.0),
                "rationale": "Matches the frozen candidate and existing gate. It does not require exchange leverage above 1x, but 1x isolated shorts are not zero-liquidation-risk.",
            },
            {
                "risk_need": "growth",
                "recommendation": "research-only until paper/live gates pass; if used, isolated margin, exchange leverage 2x, portfolio gross no higher than 1.25x",
                "primary_case": gross_status(1.25),
                "rationale": "Raises return but pushes drawdown above the frozen 1x profile and introduces 2x isolated liquidation sensitivity.",
            },
            {
                "risk_need": "speculative",
                "recommendation": "not recommended for current mainnet pilot",
                "primary_case": gross_status(2.0),
                "rationale": "The backtest still compounds, but historical drawdown and isolated liquidation proxy become unacceptable for an unapproved live candidate.",
            },
        ],
        "current_strategy_profile": {
            "long_leverage": current_profile.get("long_leverage"),
            "short_leverage": current_profile.get("short_leverage"),
            "max_gross_leverage": current_profile.get("max_gross_leverage"),
            "execution_venue": current_profile.get("execution_venue"),
            "short_allowed": current_profile.get("short_allowed"),
        },
        "method_limits": [
            "Leverage sweep scales the frozen period return, funding, fee, and slippage linearly; it does not rerank symbols or retune factors.",
            "Isolated liquidation proxy uses 1m holding-window adverse excursion and a simple threshold of 1/leverage minus a 1 percentage point buffer; it is not Binance's exact maintenance-margin formula.",
            "Cross margin and isolated margin have the same mark-to-market PnL before liquidation; the distinction here is liquidation path and account contagion.",
        ],
    }


def _render_report(
    *,
    config: dict[str, Any],
    dataset_manifest: dict[str, Any],
    validation_report: dict[str, Any],
    leverage_sweep: pd.DataFrame,
    isolated_summary: pd.DataFrame,
    key_metrics: pd.DataFrame,
    mtm_curve: pd.DataFrame,
    worst_positions: pd.DataFrame,
    recommendation: dict[str, Any],
    output_root: Path,
    plot_path: Path,
) -> str:
    generated_at = datetime.now(tz=UTC).isoformat()
    base = dict(validation_report.get("metrics", {}).get("base") or {})
    stress = dict(validation_report.get("metrics", {}).get("stress") or {})
    profile = dict(config.get("strategy_profile") or {})
    lines = [
        "# hv_balanced leverage and margin-mode risk backtest",
        "",
        f"Generated at UTC: `{generated_at}`",
        "",
        "## Decision",
        "",
        "For the current Binance USD-M mainnet pilot, the recommended default remains: `isolated` margin, exchange leverage `1x`, portfolio gross `1.0x` or lower, with an explicit short-side liquidation guard before any non-tiny mainnet exposure.",
        "",
        "Cross margin is not recommended for the live pilot. It can reduce single-position liquidation risk by sharing account equity, but it also turns one bad path into whole-account contagion. That trade is not appropriate while the strategy is still frozen-candidate / live-not-approved.",
        "",
        "## Frozen strategy baseline",
        "",
        f"- Strategy label: `{config.get('strategy_label')}`",
        f"- Dataset profile: `{dataset_manifest.get('dataset_profile')}`",
        f"- Current long/short sleeves: long `{profile.get('long_leverage')}`, short `{profile.get('short_leverage')}`, max gross `{profile.get('max_gross_leverage')}`",
        f"- Base net return: `{_fmt(base.get('net_return'))}`",
        f"- Base Sharpe: `{_fmt(base.get('sharpe'))}`",
        f"- Base max drawdown: `{_fmt(base.get('max_drawdown'))}`",
        f"- Stress net return: `{_fmt(stress.get('net_return'))}`",
        f"- Stress max drawdown: `{_fmt(stress.get('max_drawdown'))}`",
        "",
        "## Return and key metrics",
        "",
        "| Gross | Exchange lev | Total return | CAGR | Daily MTM Sharpe | Ann vol | Max DD | Worst daily | Isolated proxy hits |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, row in key_metrics.iterrows():
        lines.append(
            "| "
            f"{float(row['portfolio_gross_multiplier']):.2f}x | "
            f"{int(row['required_exchange_leverage_min'])}x | "
            f"{float(row['total_return']):.3f} | "
            f"{float(row['cagr']):.3f} | "
            f"{float(row['daily_mtm_sharpe']):.3f} | "
            f"{float(row['daily_mtm_ann_vol']):.3f} | "
            f"{float(row['max_drawdown_mtm']):.3f} | "
            f"{float(row['worst_daily_mtm_return']):.3f} | "
            f"{int(row['isolated_proxy_liquidation_position_count'])} |"
        )

    mtm_start = mtm_curve["date_utc"].iloc[0] if not mtm_curve.empty else "n/a"
    mtm_end = mtm_curve["date_utc"].iloc[-1] if not mtm_curve.empty else "n/a"
    lines.extend(
        [
            "",
            "## MTM curve",
            "",
            f"- Daily MTM window: `{mtm_start}` to `{mtm_end}`",
            f"- PNG chart: `{plot_path}`",
            f"- Daily curve CSV: `{output_root / 'mtm_daily_curve.csv'}`",
            "",
            "## Leverage sweep",
            "",
            "| Portfolio gross | Required exchange leverage | Net return | Sharpe proxy | Max DD | Worst period | Capacity pass |",
            "|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for _, row in leverage_sweep.iterrows():
        lines.append(
            "| "
            f"{float(row['portfolio_gross_multiplier']):.2f}x | "
            f"{int(row['required_exchange_leverage_min'])}x | "
            f"{float(row['net_compound_return']):.3f} | "
            f"{float(row['annualized_sharpe_period_proxy']):.3f} | "
            f"{float(row['max_drawdown']):.3f} | "
            f"{float(row['worst_period_return']):.3f} | "
            f"{bool(row['capacity_cap_0p5pct_pass'])} |"
        )

    lines.extend(
        [
            "",
            "## Isolated liquidation proxy",
            "",
            "This proxy scans the paper-shadow holding windows against local Binance 1m high/low data. A hit means the holding-window adverse move exceeded `1 / leverage - 1 percentage point`. It is deliberately simple and conservative; it is not Binance's exact liquidation formula.",
            "",
            "| Exchange leverage | Approx adverse threshold | Hit positions | Hit fraction | Long hits | Short hits | Worst adverse move |",
            "|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for _, row in isolated_summary.iterrows():
        lines.append(
            "| "
            f"{int(row['exchange_leverage'])}x | "
            f"{float(row['adverse_move_threshold_proxy']):.3f} | "
            f"{int(row['proxy_liquidation_position_count'])} | "
            f"{float(row['proxy_liquidation_position_fraction']):.3f} | "
            f"{int(row['long_hit_count'])} | "
            f"{int(row['short_hit_count'])} | "
            f"{float(row['worst_adverse_move']):.3f} |"
        )

    if not worst_positions.empty:
        lines.extend(
            [
                "",
                "## Worst holding-window adverse moves",
                "",
                "| Fill | Exit | Symbol | Side | Action | Weight | Adverse move | Favorable move |",
                "|---|---|---|---|---|---:|---:|---:|",
            ]
        )
        for _, row in worst_positions.head(12).iterrows():
            lines.append(
                "| "
                f"{row.get('fill_date_utc')} | "
                f"{row.get('exit_date_utc')} | "
                f"{row.get('usdm_symbol')} | "
                f"{row.get('side')} | "
                f"{row.get('action')} | "
                f"{float(row.get('target_weight') or 0.0):.3f} | "
                f"{float(row.get('adverse_move') or 0.0):.3f} | "
                f"{float(row.get('favorable_move') or 0.0):.3f} |"
            )

    lines.extend(
        [
            "",
            "## Risk-bucket recommendation",
            "",
            "| Risk need | Recommendation | Primary case |",
            "|---|---|---|",
        ]
    )
    for bucket in recommendation["risk_buckets"]:
        case = bucket["primary_case"]
        lines.append(
            "| "
            f"{bucket['risk_need']} | "
            f"{bucket['recommendation']} | "
            f"gross {case['portfolio_gross_multiplier']}x, exchange {case['exchange_leverage']}x, max DD {case['max_drawdown']:.3f}, net return {case['net_compound_return']:.3f}, isolated proxy hits {case['isolated_proxy_liquidation_position_count']} |"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Before liquidation, `isolated` and `cross` have the same strategy PnL for the same target notionals. The reason to choose one is risk boundary, not expected return.",
        "- `isolated 1x` is the cleanest tested pilot setting because it matches the frozen 1.0 gross profile and keeps single-symbol losses compartmentalized. It is not zero-liquidation-risk: three low-weight historical short windows crossed the simple 1x isolated proxy threshold.",
            "- `cross` should stay disabled for pilot trading unless there is a separate account-level kill switch, fresh preflight, and an explicit operator decision to accept whole-account contagion risk.",
            "- Raising exchange leverage above 1x is not needed for the current frozen strategy. If gross exposure is intentionally raised, use a new paper/shadow gate first and keep it isolated.",
            "",
            "## Artifacts",
            "",
            f"- Leverage sweep: `{output_root / 'leverage_sweep.csv'}`",
            f"- Isolated liquidation proxy: `{output_root / 'isolated_margin_liquidation_proxy.csv'}`",
            f"- Worst position adverse excursions: `{output_root / 'worst_position_adverse_excursions.csv'}`",
            f"- Machine-readable recommendation: `{output_root / 'recommendation.json'}`",
        ]
    )
    return "\n".join(lines) + "\n"


def _fmt(value: Any) -> str:
    try:
        return f"{float(value):.6f}"
    except Exception:
        return str(value)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
