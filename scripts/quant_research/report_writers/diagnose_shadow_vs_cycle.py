"""Diagnose why shadow OOS metrics diverge from actual cycle metrics.

Compares per-window numbers from the v83 cycle's fast_reject + walk-forward
artifacts against what the shadow OOS replay would predict for the SAME
decision dates, using the SAME score function and the SAME top-3 long-only
construction.

The diagnostic now checks the post-fix gap:
  (1) Shadow replay uses the execution-aligned path close[t+1]->close[t+1+h].
  (2) Cycle-emulated replay uses the same sparse decision grid on the same windows.
  (3) Any remaining gap is therefore dominated by execution costs, filtering,
      and turnover handling rather than label anchoring.

Reads the most recent v83 cycle artifacts and walks each test window.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd


EXECUTION_ALIGNED_FORWARD_RETURN_COLUMN = "target_execution_forward_return"


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _ts_zscore(values: pd.Series, timestamps: pd.Series) -> pd.Series:
    g = pd.DataFrame({"v": values.values, "t": timestamps.values}, index=values.index)
    mu = g.groupby("t")["v"].transform("mean")
    sd = g.groupby("t")["v"].transform("std").replace(0, np.nan)
    return ((g["v"] - mu) / sd).fillna(0.0)


def _ts_pct_rank(values: pd.Series, timestamps: pd.Series) -> pd.Series:
    g = pd.DataFrame({"v": values.values, "t": timestamps.values}, index=values.index)
    return g.groupby("t")["v"].rank(method="average", pct=True).fillna(0.5)


def v83_score(frame: pd.DataFrame) -> pd.Series:
    rv = frame["realized_volatility_20"]
    iv = frame["intraday_realized_vol_4h_to_1d"]
    dh = frame["distance_to_high_20"]
    tt = frame["coinglass_top_trader_long_pct"]
    ts = frame["timestamp_ms"]
    z_rv = _ts_zscore(rv, ts)
    z_iv = _ts_zscore(iv, ts)
    z_dh = _ts_zscore(dh, ts)
    tt_filled = tt.fillna(tt.median() if tt.notna().any() else 50.0)
    z_tt = _ts_zscore(tt_filled, ts)
    raw = (-0.30 * z_rv) + (-0.25 * z_iv) + (0.25 * z_dh) + (-0.20 * z_tt)
    centered = _ts_pct_rank(raw, ts) - 0.5
    return np.tanh(centered * 1.80).astype("float64")


def _ensure_execution_aligned_forward_return(
    panel: pd.DataFrame,
    *,
    target_horizon_bars: int,
) -> pd.DataFrame:
    if EXECUTION_ALIGNED_FORWARD_RETURN_COLUMN in panel.columns:
        return panel
    ordered = panel.sort_values(["subject", "timestamp_ms"]).copy()
    close = pd.to_numeric(ordered["spot_close"], errors="coerce")
    grouped_subjects = ordered["subject"].astype(str)
    execution_entry_close = close.groupby(grouped_subjects).shift(-1)
    execution_exit_close = close.groupby(grouped_subjects).shift(-(int(target_horizon_bars) + 1))
    ordered[EXECUTION_ALIGNED_FORWARD_RETURN_COLUMN] = execution_exit_close / execution_entry_close - 1.0
    return ordered.sort_index()


def main() -> int:
    fast_reject_path = ROOT / "artifacts" / "quant_research" / "hypothesis_batches" / "2026-04-26" / "families" / "xs_minimal_v3_h5d" / "fast_reject_report.json"
    if not fast_reject_path.exists():
        print(f"missing v83 fast_reject_report at {fast_reject_path}")
        return 1
    fr = json.loads(fast_reject_path.read_text(encoding="utf-8"))
    wf_lite = fr.get("walk_forward_assessment_lite", {})
    print("=== v83 cycle fast_reject_report (current) ===")
    print(f"  walk_forward median sharpe : {wf_lite.get('median_oos_sharpe')}")
    print(f"  walk_forward window_count  : {wf_lite.get('window_count')}")
    print(f"  walk_forward loss_fraction : {wf_lite.get('loss_window_fraction')}")
    rh = fr.get("regime_holdout_lite", {})
    print(f"  regime worst sharpe        : {rh.get('worst_regime_median_oos_sharpe')}")

    val_report_path = ROOT / "artifacts" / "quant_research" / "experiments" / "2026-04-26-xs_minimal_v3_h5d" / "validation_report.json"
    if not val_report_path.exists():
        print(f"\n(no v83 strict validation_report at {val_report_path}; cycle may not have produced strict)")
    else:
        vr = json.loads(val_report_path.read_text(encoding="utf-8"))
        wf = vr.get("walk_forward", {})
        windows = list(wf.get("windows") or [])
        print(f"\n=== v83 strict walk_forward windows ({len(windows)} windows) ===")
        sharpes = [float(w.get("sharpe", 0.0) or 0.0) for w in windows]
        net_returns = [float(w.get("net_return", 0.0) or 0.0) for w in windows]
        gross_returns = [float(w.get("gross_return_before_costs", 0.0) or 0.0) for w in windows]
        fee_costs = [float(w.get("fee_cost_return", 0.0) or 0.0) for w in windows]
        slippage_costs = [float(w.get("slippage_cost_return", 0.0) or 0.0) for w in windows]
        turnovers = [float(w.get("turnover", 0.0) or 0.0) for w in windows]
        print(f"  sharpe   : median={np.median(sharpes):+.3f}  mean={np.mean(sharpes):+.3f}  min={np.min(sharpes):+.3f}  max={np.max(sharpes):+.3f}")
        print(f"  net_ret  : median={np.median(net_returns):+.4f}  mean={np.mean(net_returns):+.4f}")
        print(f"  gross_ret: median={np.median(gross_returns):+.4f}  mean={np.mean(gross_returns):+.4f}")
        print(f"  fees     : mean={np.mean(fee_costs):+.4f}  sum={np.sum(fee_costs):+.4f}")
        print(f"  slippage : mean={np.mean(slippage_costs):+.4f}  sum={np.sum(slippage_costs):+.4f}")
        print(f"  turnover : mean={np.mean(turnovers):.4f}  sum={np.sum(turnovers):.4f}")
        cost_drag = np.mean([f + s for f, s in zip(fee_costs, slippage_costs)])
        print(f"  per-window cost drag (fees+slippage) avg: {cost_drag:+.4f}")

    panel_path = ROOT / "artifacts" / "quant_research" / "features" / "2026-04-26-cross-sectional-daily-1d-h5d-features-v83" / "features.csv.gz"
    panel = pd.read_csv(panel_path)
    panel["timestamp_ms"] = panel["timestamp_ms"].astype("int64")
    panel["date_utc"] = pd.to_datetime(panel["timestamp_ms"], unit="ms", utc=True)
    panel = _ensure_execution_aligned_forward_return(panel, target_horizon_bars=5)

    needed = [
        "realized_volatility_20",
        "intraday_realized_vol_4h_to_1d",
        "distance_to_high_20",
        "coinglass_top_trader_long_pct",
        "subject",
        EXECUTION_ALIGNED_FORWARD_RETURN_COLUMN,
        "spot_close",
    ]
    panel = panel.dropna(subset=needed).copy()
    panel = panel[panel["selection_rank"] <= 20].copy()
    panel = panel[panel["liquidity_bucket"].isin(["top_liquidity", "mid_liquidity"])].copy()
    panel["score"] = v83_score(panel)

    timestamps_sorted = sorted(int(t) for t in panel["timestamp_ms"].drop_duplicates())
    panel_min = pd.Timestamp(timestamps_sorted[0], unit="ms", tz="UTC")
    panel_max = pd.Timestamp(timestamps_sorted[-1], unit="ms", tz="UTC")

    by_ts = {
        ts: g.set_index("subject")[["score", EXECUTION_ALIGNED_FORWARD_RETURN_COLUMN, "spot_close"]]
        for ts, g in panel.groupby("timestamp_ms")
    }

    start_anchor = panel_min + pd.Timedelta(days=120)
    final_anchor = panel_max - pd.Timedelta(days=30)
    anchor = start_anchor
    rows = []
    while anchor <= final_anchor:
        test_start = anchor
        test_end = anchor + pd.Timedelta(days=30)
        ts_in_window = [t for t in timestamps_sorted if test_start <= pd.Timestamp(t, unit="ms", tz="UTC") < test_end]
        if len(ts_in_window) < 10:
            anchor = anchor + pd.Timedelta(days=30)
            continue
        decision_ts_list = ts_in_window[::5]
        shadow_returns_aligned = []
        cycle_emul_returns = []
        turnovers = []
        prev_subjects = set()
        for di, ts in enumerate(decision_ts_list):
            cs = by_ts.get(ts)
            if cs is None or cs.empty:
                continue
            top3 = cs.sort_values("score", ascending=False).head(3)
            top3_subjects = set(top3.index)
            shadow_returns_aligned.append(float(top3[EXECUTION_ALIGNED_FORWARD_RETURN_COLUMN].mean()))
            fill_offset = ts_in_window.index(ts) + 1
            exit_offset = ts_in_window.index(decision_ts_list[di + 1]) + 1 if di + 1 < len(decision_ts_list) else None
            if fill_offset < len(ts_in_window) and exit_offset is not None and exit_offset < len(ts_in_window):
                fill_ts = ts_in_window[fill_offset]
                exit_ts = ts_in_window[exit_offset]
                fill_g = by_ts.get(fill_ts)
                exit_g = by_ts.get(exit_ts)
                if fill_g is not None and exit_g is not None:
                    rets = []
                    for subj in top3_subjects:
                        if subj in fill_g.index and subj in exit_g.index:
                            ep = float(fill_g.loc[subj, "spot_close"])
                            xp = float(exit_g.loc[subj, "spot_close"])
                            if ep > 0 and xp > 0:
                                rets.append(xp / ep - 1.0)
                    cycle_emul_returns.append(float(np.mean(rets)) if rets else 0.0)
            turnover = len(top3_subjects.symmetric_difference(prev_subjects)) / 3.0 if prev_subjects else 1.0
            turnovers.append(turnover)
            prev_subjects = top3_subjects
        if len(shadow_returns_aligned) >= 2:
            shadow_arr = np.array(shadow_returns_aligned)
            shadow_mean = float(shadow_arr.mean())
            shadow_std = float(shadow_arr.std())
            shadow_sharpe = float(shadow_mean / shadow_std * np.sqrt(73.05)) if shadow_std > 0 else None
            if cycle_emul_returns and len(cycle_emul_returns) >= 2:
                emul_arr = np.array(cycle_emul_returns)
                emul_mean = float(emul_arr.mean())
                emul_std = float(emul_arr.std())
                emul_sharpe = float(emul_mean / emul_std * np.sqrt(73.05)) if emul_std > 0 else None
            else:
                emul_mean = emul_std = emul_sharpe = None
            rows.append({
                "test_start": test_start.isoformat(),
                "shadow_aligned_sharpe": shadow_sharpe,
                "shadow_aligned_mean": shadow_mean,
                "cycle_emul_sharpe": emul_sharpe,
                "cycle_emul_mean": emul_mean,
                "decisions": len(shadow_returns_aligned),
                "avg_turnover": float(np.mean(turnovers)),
            })
        anchor = anchor + pd.Timedelta(days=30)

    df = pd.DataFrame(rows)
    print(
        "\n=== Diagnostic: shadow (execution-aligned close[t+1]->close[t+6]) "
        f"vs cycle-emulated price-path on same windows ({len(df)} windows) ==="
    )
    if not df.empty:
        print(
            f"  shadow_align : median sharpe={df['shadow_aligned_sharpe'].median():+.3f}  "
            f"mean sharpe={df['shadow_aligned_sharpe'].mean():+.3f}"
        )
        ces = df["cycle_emul_sharpe"].dropna()
        if len(ces):
            print(f"  cycle_emul   : median sharpe={ces.median():+.3f}  mean sharpe={ces.mean():+.3f}")
        print(
            f"  delta sharpe : median(emul - aligned) = "
            f"{(df['cycle_emul_sharpe'] - df['shadow_aligned_sharpe']).median():+.3f}"
        )
        print(f"  per-window mean return:")
        print(f"    shadow_align : {df['shadow_aligned_mean'].mean():+.5f}")
        print(f"    cycle_emul   : {df['cycle_emul_mean'].mean():+.5f}")
        print(f"  avg turnover per decision: {df['avg_turnover'].mean():.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
