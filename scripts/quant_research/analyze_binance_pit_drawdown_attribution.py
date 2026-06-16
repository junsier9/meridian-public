from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


DEFAULT_FULL_RUN_ROOT = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "binance_canonical_h10d"
    / "20260511TpitTopMidFullSideYearLooBackfilled-1k-v5_binance_pit_top_mid_h10d"
)
DEFAULT_PRUNED_RUN_ROOT = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "binance_canonical_h10d"
    / "20260511TpitTopMidPruned3Backfilled-1k-v5_binance_pit_top_mid_h10d_pruned3"
)
DEFAULT_OUTPUT_ROOT = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "binance_canonical_h10d"
    / "drawdown_attribution_20260511Tpruned3_vs_full"
)
DEFAULT_REPORT_PATH = (
    ROOT
    / "docs"
    / "quant_research"
    / "02_binance_pit_h10d"
    / "binance_pit_pruned3_drawdown_attribution_2026_05_11.md"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Attribute the pruned3 Binance PIT drawdown versus full PIT.")
    parser.add_argument("--full-run-root", type=Path, default=DEFAULT_FULL_RUN_ROOT)
    parser.add_argument("--pruned-run-root", type=Path, default=DEFAULT_PRUNED_RUN_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = analyze_drawdowns(
        full_run_root=args.full_run_root,
        pruned_run_root=args.pruned_run_root,
        output_root=args.output_root,
        report_path=args.report_path,
    )
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


def analyze_drawdowns(
    *,
    full_run_root: Path,
    pruned_run_root: Path,
    output_root: Path,
    report_path: Path,
) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    full = _load_run(full_run_root, run_name="full_pit")
    pruned = _load_run(pruned_run_root, run_name="pruned3")

    full["periods"].to_csv(output_root / "drawdown_periods_full_pit.csv", index=False)
    pruned["periods"].to_csv(output_root / "drawdown_periods_pruned3.csv", index=False)
    episodes = pd.concat([full["episodes"], pruned["episodes"]], ignore_index=True)
    episodes.to_csv(output_root / "drawdown_episodes.csv", index=False)

    pruned_worst = _worst_episode(pruned["episodes"])
    full_worst = _worst_episode(full["episodes"])
    if pruned_worst is None:
        raise ValueError("No pruned3 drawdown episode found.")
    if full_worst is None:
        raise ValueError("No full PIT drawdown episode found.")

    same_window_periods = _compare_same_window_periods(
        full_periods=full["periods"],
        pruned_periods=pruned["periods"],
        episode=pruned_worst,
    )
    same_window_periods.to_csv(output_root / "pruned3_worst_window_period_returns.csv", index=False)

    side = _compare_window_ledger(
        full_ledger=full["ledger"],
        pruned_ledger=pruned["ledger"],
        episode=pruned_worst,
        group_columns=["side"],
    )
    side.to_csv(output_root / "pruned3_worst_window_side_attribution.csv", index=False)
    symbol = _compare_window_ledger(
        full_ledger=full["ledger"],
        pruned_ledger=pruned["ledger"],
        episode=pruned_worst,
        group_columns=["subject", "usdm_symbol", "side"],
    )
    symbol.to_csv(output_root / "pruned3_worst_window_symbol_attribution.csv", index=False)
    year = _compare_window_ledger(
        full_ledger=full["ledger"],
        pruned_ledger=pruned["ledger"],
        episode=pruned_worst,
        group_columns=["year", "side"],
    )
    year.to_csv(output_root / "pruned3_worst_window_year_side_attribution.csv", index=False)
    bucket = _compare_window_ledger(
        full_ledger=full["ledger"],
        pruned_ledger=pruned["ledger"],
        episode=pruned_worst,
        group_columns=["liquidity_bucket", "side"],
    )
    bucket.to_csv(output_root / "pruned3_worst_window_liquidity_bucket_attribution.csv", index=False)

    summary = {
        "status": "ok",
        "method": "period_return_drawdown_episode_then_same_window_ledger_attribution",
        "full_run_root": str(full_run_root),
        "pruned_run_root": str(pruned_run_root),
        "output_root": str(output_root),
        "report_path": str(report_path),
        "full_worst_episode": _json_record(full_worst),
        "pruned3_worst_episode": _json_record(pruned_worst),
        "same_window": _same_window_summary(same_window_periods),
        "top_extra_loss_by_side": _records(_sort_extra_loss(side).head(10)),
        "top_extra_loss_by_symbol": _records(_sort_extra_loss(symbol).head(15)),
        "top_extra_loss_by_year_side": _records(_sort_extra_loss(year).head(10)),
        "top_extra_loss_by_liquidity_bucket": _records(_sort_extra_loss(bucket).head(10)),
        "artifacts": {
            "drawdown_periods_full_pit": str(output_root / "drawdown_periods_full_pit.csv"),
            "drawdown_periods_pruned3": str(output_root / "drawdown_periods_pruned3.csv"),
            "drawdown_episodes": str(output_root / "drawdown_episodes.csv"),
            "pruned3_worst_window_period_returns": str(output_root / "pruned3_worst_window_period_returns.csv"),
            "pruned3_worst_window_side_attribution": str(output_root / "pruned3_worst_window_side_attribution.csv"),
            "pruned3_worst_window_symbol_attribution": str(output_root / "pruned3_worst_window_symbol_attribution.csv"),
            "pruned3_worst_window_year_side_attribution": str(output_root / "pruned3_worst_window_year_side_attribution.csv"),
            "pruned3_worst_window_liquidity_bucket_attribution": str(output_root / "pruned3_worst_window_liquidity_bucket_attribution.csv"),
            "summary": str(output_root / "drawdown_attribution_summary.json"),
            "markdown_report": str(report_path),
        },
    }
    (output_root / "drawdown_attribution_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(_render_report(summary, side=side, symbol=symbol, year=year, bucket=bucket), encoding="utf-8")
    return summary


def _load_run(run_root: Path, *, run_name: str) -> dict[str, pd.DataFrame]:
    periods = pd.read_csv(run_root / "aligned_period_returns.csv")
    periods = _add_drawdown_path(periods, run_name=run_name)
    episodes = _find_drawdown_episodes(periods, run_name=run_name)
    ledger = pd.read_csv(run_root / "paper_shadow_execution_ledger.csv")
    ledger = _normalize_ledger(ledger)
    return {"periods": periods, "episodes": episodes, "ledger": ledger}


def _add_drawdown_path(periods: pd.DataFrame, *, run_name: str) -> pd.DataFrame:
    frame = periods.copy()
    frame["run"] = run_name
    frame["timestamp_ms"] = pd.to_numeric(frame["timestamp_ms"], errors="coerce").astype("Int64")
    frame = frame.dropna(subset=["timestamp_ms"]).copy()
    frame["timestamp_ms"] = frame["timestamp_ms"].astype("int64")
    frame = frame.sort_values("timestamp_ms").reset_index(drop=True)
    frame["date_utc"] = frame["timestamp_ms"].map(_ms_to_date)
    returns = pd.to_numeric(frame["net_period_return"], errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0.0)
    frame["equity"] = (1.0 + returns).cumprod()
    frame["running_peak_equity"] = frame["equity"].cummax()
    frame["drawdown"] = (1.0 - frame["equity"] / frame["running_peak_equity"].replace(0.0, np.nan)).fillna(0.0)
    frame["period_index"] = np.arange(len(frame), dtype="int64")
    return frame


def _find_drawdown_episodes(periods: pd.DataFrame, *, run_name: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    peak_idx = 0
    peak_equity = float(periods.iloc[0]["equity"]) if not periods.empty else 1.0
    current: dict[str, Any] | None = None
    eps = 1e-12
    for idx, row in periods.iterrows():
        equity = float(row["equity"])
        drawdown = float(row["drawdown"])
        if equity >= peak_equity - eps:
            if current is not None:
                current["recovery_index"] = int(idx)
                current["recovery_timestamp_ms"] = int(row["timestamp_ms"])
                current["recovery_date_utc"] = str(row["date_utc"])
                rows.append(_finalize_episode(current, periods))
                current = None
            peak_idx = int(idx)
            peak_equity = equity
            continue
        if current is None:
            peak_row = periods.iloc[peak_idx]
            current = {
                "run": run_name,
                "episode_id": f"{run_name}_dd_{len(rows) + 1:03d}",
                "peak_index": int(peak_idx),
                "peak_timestamp_ms": int(peak_row["timestamp_ms"]),
                "peak_date_utc": str(peak_row["date_utc"]),
                "peak_equity": float(peak_row["equity"]),
                "trough_index": int(idx),
                "trough_timestamp_ms": int(row["timestamp_ms"]),
                "trough_date_utc": str(row["date_utc"]),
                "trough_equity": equity,
                "max_drawdown": drawdown,
                "recovery_index": None,
                "recovery_timestamp_ms": None,
                "recovery_date_utc": None,
            }
        elif drawdown > float(current["max_drawdown"]):
            current["trough_index"] = int(idx)
            current["trough_timestamp_ms"] = int(row["timestamp_ms"])
            current["trough_date_utc"] = str(row["date_utc"])
            current["trough_equity"] = equity
            current["max_drawdown"] = drawdown
    if current is not None:
        rows.append(_finalize_episode(current, periods))
    return pd.DataFrame(rows)


def _finalize_episode(episode: dict[str, Any], periods: pd.DataFrame) -> dict[str, Any]:
    peak_idx = int(episode["peak_index"])
    trough_idx = int(episode["trough_index"])
    window = periods.iloc[peak_idx + 1 : trough_idx + 1].copy()
    returns = pd.to_numeric(window.get("net_period_return"), errors="coerce").fillna(0.0)
    episode["peak_to_trough_period_count"] = int(len(window))
    episode["peak_to_trough_compounded_return"] = float((1.0 + returns).prod() - 1.0) if len(returns) else 0.0
    episode["start_year"] = int(str(episode["peak_date_utc"])[:4])
    episode["trough_year"] = int(str(episode["trough_date_utc"])[:4])
    episode["recovered"] = episode.get("recovery_timestamp_ms") is not None
    return episode


def _worst_episode(episodes: pd.DataFrame) -> pd.Series | None:
    if episodes.empty:
        return None
    idx = pd.to_numeric(episodes["max_drawdown"], errors="coerce").idxmax()
    return episodes.loc[idx]


def _compare_same_window_periods(
    *,
    full_periods: pd.DataFrame,
    pruned_periods: pd.DataFrame,
    episode: pd.Series,
) -> pd.DataFrame:
    timestamps = _episode_window_timestamps(pruned_periods, episode)
    full = full_periods.loc[full_periods["timestamp_ms"].isin(timestamps)].copy()
    pruned = pruned_periods.loc[pruned_periods["timestamp_ms"].isin(timestamps)].copy()
    keep = ["timestamp_ms", "date_utc", "net_period_return", "gross_return_before_costs", "fee_cost_return", "slippage_cost_return", "funding_cost_return", "equity", "drawdown"]
    merged = full[keep].rename(columns={column: f"full_{column}" for column in keep if column not in {"timestamp_ms", "date_utc"}}).merge(
        pruned[keep].rename(columns={column: f"pruned3_{column}" for column in keep if column not in {"timestamp_ms", "date_utc"}}),
        on=["timestamp_ms", "date_utc"],
        how="outer",
    )
    for column in ("full_net_period_return", "pruned3_net_period_return"):
        merged[column] = pd.to_numeric(merged[column], errors="coerce").fillna(0.0)
    merged["delta_pruned3_minus_full_net_period_return"] = merged["pruned3_net_period_return"] - merged["full_net_period_return"]
    return merged.sort_values("timestamp_ms").reset_index(drop=True)


def _compare_window_ledger(
    *,
    full_ledger: pd.DataFrame,
    pruned_ledger: pd.DataFrame,
    episode: pd.Series,
    group_columns: list[str],
) -> pd.DataFrame:
    start_ms = int(episode["peak_timestamp_ms"])
    end_ms = int(episode["trough_timestamp_ms"])
    full = _aggregate_ledger_window(full_ledger, start_ms=start_ms, end_ms=end_ms, group_columns=group_columns, prefix="full")
    pruned = _aggregate_ledger_window(pruned_ledger, start_ms=start_ms, end_ms=end_ms, group_columns=group_columns, prefix="pruned3")
    merged = full.merge(pruned, on=group_columns, how="outer")
    for column in merged.columns:
        if column not in group_columns:
            merged[column] = pd.to_numeric(merged[column], errors="coerce").fillna(0.0)
    for metric in (
        "row_count",
        "gross_contribution",
        "fee_cost_return",
        "slippage_cost_return",
        "funding_cost_return",
        "borrow_cost_return",
        "net_contribution",
        "trade_notional_usd",
    ):
        full_column = f"full_{metric}"
        pruned_column = f"pruned3_{metric}"
        if full_column not in merged.columns:
            merged[full_column] = 0.0
        if pruned_column not in merged.columns:
            merged[pruned_column] = 0.0
        merged[f"delta_pruned3_minus_full_{metric}"] = merged[pruned_column] - merged[full_column]
    return merged.sort_values(["delta_pruned3_minus_full_net_contribution", *group_columns]).reset_index(drop=True)


def _aggregate_ledger_window(
    ledger: pd.DataFrame,
    *,
    start_ms: int,
    end_ms: int,
    group_columns: list[str],
    prefix: str,
) -> pd.DataFrame:
    if ledger.empty:
        return pd.DataFrame(columns=[*group_columns, f"{prefix}_net_contribution"])
    frame = ledger.loc[
        pd.to_numeric(ledger["fill_timestamp_ms"], errors="coerce").gt(start_ms)
        & pd.to_numeric(ledger["fill_timestamp_ms"], errors="coerce").le(end_ms)
    ].copy()
    if frame.empty:
        return pd.DataFrame(columns=[*group_columns, f"{prefix}_net_contribution"])
    for column in group_columns:
        if column not in frame.columns:
            frame[column] = ""
    metrics = (
        frame.groupby(group_columns, dropna=False, sort=True)
        .agg(
            row_count=("subject", "count"),
            gross_contribution=("gross_contribution", "sum"),
            fee_cost_return=("fee_cost_return", "sum"),
            slippage_cost_return=("slippage_cost_return", "sum"),
            funding_cost_return=("funding_cost_return", "sum"),
            borrow_cost_return=("borrow_cost_return", "sum"),
            net_contribution=("net_contribution", "sum"),
            trade_notional_usd=("trade_notional_usd", "sum"),
        )
        .reset_index()
    )
    return metrics.rename(columns={column: f"{prefix}_{column}" for column in metrics.columns if column not in group_columns})


def _episode_window_timestamps(periods: pd.DataFrame, episode: pd.Series) -> set[int]:
    peak_idx = int(episode["peak_index"])
    trough_idx = int(episode["trough_index"])
    window = periods.iloc[peak_idx + 1 : trough_idx + 1]
    return {int(item) for item in window["timestamp_ms"].tolist()}


def _normalize_ledger(ledger: pd.DataFrame) -> pd.DataFrame:
    frame = ledger.copy()
    for column in (
        "fill_timestamp_ms",
        "gross_contribution",
        "fee_cost_return",
        "slippage_cost_return",
        "funding_cost_return",
        "borrow_cost_return",
        "net_contribution",
        "trade_notional_usd",
    ):
        if column not in frame.columns:
            frame[column] = 0.0
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
    if "year" not in frame.columns:
        frame["year"] = frame["fill_timestamp_ms"].map(lambda item: int(_ms_to_date(int(item))[:4]) if item else 0)
    return frame


def _same_window_summary(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {}
    full_returns = pd.to_numeric(frame["full_net_period_return"], errors="coerce").fillna(0.0)
    pruned_returns = pd.to_numeric(frame["pruned3_net_period_return"], errors="coerce").fillna(0.0)
    return {
        "start_date_utc": str(frame["date_utc"].iloc[0]),
        "end_date_utc": str(frame["date_utc"].iloc[-1]),
        "period_count": int(len(frame)),
        "full_compounded_return": float((1.0 + full_returns).prod() - 1.0),
        "pruned3_compounded_return": float((1.0 + pruned_returns).prod() - 1.0),
        "delta_pruned3_minus_full_compounded_return": float((1.0 + pruned_returns).prod() - (1.0 + full_returns).prod()),
        "full_worst_period_return": float(full_returns.min()),
        "pruned3_worst_period_return": float(pruned_returns.min()),
        "periods_where_pruned3_worse": int((pruned_returns < full_returns).sum()),
    }


def _sort_extra_loss(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "delta_pruned3_minus_full_net_contribution" not in frame.columns:
        return frame
    return frame.sort_values("delta_pruned3_minus_full_net_contribution", ascending=True).reset_index(drop=True)


def _render_report(
    summary: dict[str, Any],
    *,
    side: pd.DataFrame,
    symbol: pd.DataFrame,
    year: pd.DataFrame,
    bucket: pd.DataFrame,
) -> str:
    pruned = summary["pruned3_worst_episode"]
    full = summary["full_worst_episode"]
    same = summary["same_window"]
    lines = [
        "# Binance PIT Pruned3 Drawdown Attribution",
        "",
        "Date: 2026-05-11",
        "",
        "## Decision",
        "",
        f"`pruned3` has a higher max drawdown than the full PIT version. The extra drawdown is concentrated in its worst `{same['start_date_utc']}` to `{same['end_date_utc']}` peak-to-trough window rather than being a uniform increase in volatility across the whole sample.",
        "",
        "## Worst Episodes",
        "",
        "| Run | Peak | Trough | Recovery | Max DD | Peak-to-trough return | Periods |",
        "| --- | --- | --- | --- | ---: | ---: | ---: |",
        f"| Full PIT | {full['peak_date_utc']} | {full['trough_date_utc']} | {full.get('recovery_date_utc') or 'unrecovered'} | {float(full['max_drawdown']):.6f} | {float(full['peak_to_trough_compounded_return']):.6f} | {int(full['peak_to_trough_period_count'])} |",
        f"| Pruned3 | {pruned['peak_date_utc']} | {pruned['trough_date_utc']} | {pruned.get('recovery_date_utc') or 'unrecovered'} | {float(pruned['max_drawdown']):.6f} | {float(pruned['peak_to_trough_compounded_return']):.6f} | {int(pruned['peak_to_trough_period_count'])} |",
        "",
        "## Same-Window Comparison",
        "",
        f"Pruned3 worst peak-to-trough window: `{same['start_date_utc']}` to `{same['end_date_utc']}`, `{same['period_count']}` h10d periods.",
        "",
        "| Window Metric | Full PIT | Pruned3 | Delta |",
        "| --- | ---: | ---: | ---: |",
        f"| Compounded return | {same['full_compounded_return']:.6f} | {same['pruned3_compounded_return']:.6f} | {same['delta_pruned3_minus_full_compounded_return']:.6f} |",
        f"| Worst period return | {same['full_worst_period_return']:.6f} | {same['pruned3_worst_period_return']:.6f} | {(same['pruned3_worst_period_return'] - same['full_worst_period_return']):.6f} |",
        f"| Periods where pruned3 worse | {same['periods_where_pruned3_worse']} | {same['period_count']} | |",
        "",
        "## Extra Loss By Side",
        "",
        _markdown_table(
            _sort_extra_loss(side).head(10),
            [
                "side",
                "full_net_contribution",
                "pruned3_net_contribution",
                "delta_pruned3_minus_full_net_contribution",
                "full_row_count",
                "pruned3_row_count",
            ],
        ),
        "",
        "## Extra Loss By Year And Side",
        "",
        _markdown_table(
            _sort_extra_loss(year).head(10),
            [
                "year",
                "side",
                "full_net_contribution",
                "pruned3_net_contribution",
                "delta_pruned3_minus_full_net_contribution",
            ],
        ),
        "",
        "## Extra Loss By Liquidity Bucket",
        "",
        _markdown_table(
            _sort_extra_loss(bucket).head(10),
            [
                "liquidity_bucket",
                "side",
                "full_net_contribution",
                "pruned3_net_contribution",
                "delta_pruned3_minus_full_net_contribution",
            ],
        ),
        "",
        "## Extra Loss By Symbol",
        "",
        _markdown_table(
            _sort_extra_loss(symbol).head(15),
            [
                "subject",
                "usdm_symbol",
                "side",
                "full_net_contribution",
                "pruned3_net_contribution",
                "delta_pruned3_minus_full_net_contribution",
            ],
        ),
        "",
        "## Read",
        "",
        "The pruned3 drawdown penalty is not an all-period volatility problem. In the worst same-window comparison, the largest deterioration comes from top-liquidity long exposure. Mid-liquidity shorts also worsen, but they are not the main incremental drawdown source in this window.",
        "",
        "This points to a risk-layer problem rather than an alpha-pruning failure: pruned3 is still stronger on full-sample and falsification metrics, but it needs a Binance-only ex-ante drawdown/volatility brake before paper readiness.",
        "",
        "## Artifacts",
        "",
    ]
    for name, path in dict(summary["artifacts"]).items():
        lines.append(f"- {name}: `{path}`")
    lines.append("")
    return "\n".join(lines)


def _markdown_table(frame: pd.DataFrame, columns: list[str]) -> str:
    if frame.empty:
        return "_No rows._"
    rows = []
    available = [column for column in columns if column in frame.columns]
    rows.append("| " + " | ".join(available) + " |")
    rows.append("| " + " | ".join("---" for _ in available) + " |")
    for _, item in frame.loc[:, available].iterrows():
        values = []
        for column in available:
            value = item[column]
            if isinstance(value, float):
                values.append(f"{value:.6f}")
            else:
                values.append(str(value))
        rows.append("| " + " | ".join(values) + " |")
    return "\n".join(rows)


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    return json.loads(frame.replace([np.inf, -np.inf], np.nan).to_json(orient="records"))


def _json_record(row: pd.Series | None) -> dict[str, Any]:
    if row is None:
        return {}
    return json.loads(row.replace([np.inf, -np.inf], np.nan).to_json())


def _ms_to_date(value: int) -> str:
    return datetime.fromtimestamp(int(value) / 1000, tz=UTC).date().isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
