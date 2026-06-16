"""
v72 gate alignment self-check.

Question: do v6_score's internal dispersion/median-momentum gates align with
the *time-window* holdout regime labels (trend_up_2025h2 / rotation_high_vol_2025q4
/ drawdown_rebound_2026ytd)?

If yes (alignment > 0.5), regime-gated bolt-on (v72) is a valid design.
If no (< 0.3), gating won't transfer and we should pivot to L/H instead.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "src"))

from enhengclaw.quant_research.binance_derivatives import (  # noqa: E402
    load_derivatives_rows,
    resolve_external_derivatives_root,
)


UNIVERSE_PATH = REPO / "artifacts" / "quant_research" / "_quant_inputs" / "pit-liquidity-top100-2026-04-26.quant_universe.json"
HOLDOUT_PATH = REPO / "config" / "quant_research" / "regime_holdout_windows.json"
TARGET_N = 25
INTERVAL = "1d"


def _select_top_universe(target_n: int) -> list[str]:
    payload = json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))
    cands = [c for c in (payload.get("candidates") or []) if c.get("usdm_symbol")]
    cands.sort(key=lambda c: int(c.get("selection_rank") or 9_999))
    return [str(c["usdm_symbol"]) for c in cands[:target_n]]


def _load_perp_close(symbol: str) -> pd.DataFrame:
    rows = load_derivatives_rows(external_root=resolve_external_derivatives_root(), symbol=symbol, interval=INTERVAL)
    if not rows:
        return pd.DataFrame()
    rec = []
    for r in rows:
        try:
            ts = int(r["open_time_ms"])
            close = float(r.get("perp_close", "") or "nan")
        except (TypeError, ValueError, KeyError):
            continue
        rec.append({"open_time_ms": ts, "perp_close": close, "subject": symbol})
    df = pd.DataFrame.from_records(rec).drop_duplicates("open_time_ms").sort_values("open_time_ms").reset_index(drop=True)
    return df


def main() -> int:
    holdout = json.loads(HOLDOUT_PATH.read_text(encoding="utf-8"))
    windows = holdout["windows"]

    symbols = _select_top_universe(TARGET_N)
    frames = []
    for sym in symbols:
        df = _load_perp_close(sym)
        if df.empty:
            continue
        df["momentum_20"] = df["perp_close"] / df["perp_close"].shift(20) - 1.0
        frames.append(df)
    panel = pd.concat(frames, ignore_index=True)
    panel["timestamp"] = pd.to_datetime(panel["open_time_ms"], unit="ms", utc=True)

    daily = panel.dropna(subset=["momentum_20"]).groupby("timestamp", sort=True).agg(
        n=("momentum_20", "size"),
        median_mom=("momentum_20", "median"),
        std_abs_mom=("momentum_20", lambda s: float(np.std(np.abs(s.values)))),
    ).reset_index()
    daily = daily[daily["n"] >= 8].copy()

    median_disp_all = float(daily["std_abs_mom"].median())
    daily["disp_array"] = (daily["std_abs_mom"] / max(median_disp_all * 2.0, 1e-9)).clip(0.0, 1.0)
    daily["scaled_median_mom"] = (daily["median_mom"] / 0.06).clip(-1.0, 1.0)
    daily["med_sign_pos"] = (daily["scaled_median_mom"] > 0).astype(float)
    daily["broad_uniform_signal"] = ((1.0 - daily["disp_array"]) * daily["scaled_median_mom"].abs()).clip(0.0, 1.0)
    daily["trend_up_gate"]  = daily["disp_array"] * daily["med_sign_pos"]
    daily["rotation_gate"]  = daily["disp_array"] * (1.0 - daily["med_sign_pos"])
    daily["drawdown_gate"]  = daily["broad_uniform_signal"]

    rows: list[dict] = []
    for w in windows:
        mask = (daily["timestamp"] >= pd.Timestamp(w["start_utc"])) & (daily["timestamp"] <= pd.Timestamp(w["end_utc"]))
        sub = daily.loc[mask].copy()
        if sub.empty:
            continue
        rows.append({
            "regime_id": w["regime_id"],
            "n_days": int(len(sub)),
            "mean_disp_array": float(sub["disp_array"].mean()),
            "mean_median_mom": float(sub["median_mom"].mean()),
            "mean_med_sign_pos": float(sub["med_sign_pos"].mean()),
            "mean_broad_uniform": float(sub["broad_uniform_signal"].mean()),
            "mean_trend_up_gate": float(sub["trend_up_gate"].mean()),
            "mean_rotation_gate": float(sub["rotation_gate"].mean()),
            "mean_drawdown_gate": float(sub["drawdown_gate"].mean()),
        })

    print(f"\nUniverse: {len(symbols)} symbols, {len(daily)} daily rows total")
    print(f"Median dispersion across all days = {median_disp_all:.5f}\n")
    print(f"  {'regime':<28} {'n':>4} {'disp':>6} {'med_mom':>8} {'medSign':>7} {'bu':>5} {'tu_gate':>7} {'rot_gate':>8} {'dd_gate':>7}")
    for r in rows:
        print(f"  {r['regime_id']:<28} {r['n_days']:>4} {r['mean_disp_array']:>6.3f} {r['mean_median_mom']:>+8.5f} {r['mean_med_sign_pos']:>7.3f} {r['mean_broad_uniform']:>5.3f} {r['mean_trend_up_gate']:>7.3f} {r['mean_rotation_gate']:>8.3f} {r['mean_drawdown_gate']:>7.3f}")
    print()

    expected_winning_gate = {
        "trend_up_2025h2": "trend_up_gate",
        "rotation_high_vol_2025q4": "rotation_gate",
        "drawdown_rebound_2026ytd": "drawdown_gate",
    }
    print("Alignment check (each regime's expected-winning-gate should be its highest gate):")
    pass_count = 0
    for r in rows:
        rid = r["regime_id"]
        gates = {
            "trend_up_gate": r["mean_trend_up_gate"],
            "rotation_gate": r["mean_rotation_gate"],
            "drawdown_gate": r["mean_drawdown_gate"],
        }
        winner = max(gates, key=gates.get)
        expected = expected_winning_gate.get(rid)
        ok = winner == expected
        margin = gates[expected] - max(v for k, v in gates.items() if k != expected) if expected else float("nan")
        status = "PASS" if ok else "FAIL"
        print(f"  {rid:<28} expected={expected:<14} actual_winner={winner:<14} margin={margin:+.3f}  {status}")
        if ok:
            pass_count += 1
    overall_alignment = pass_count / max(len(rows), 1)
    print(f"\n=== Alignment score = {pass_count}/{len(rows)} = {overall_alignment:.2f} ===")
    if overall_alignment >= 0.67:
        print("VERDICT: alignment is sufficient (>= 2/3); v72 regime-gated bolt-on is justified")
    elif overall_alignment >= 0.34:
        print("VERDICT: partial alignment (1/3); v72 should gate by holdout date directly, not by dispersion gate")
    else:
        print("VERDICT: poor alignment; pivot to architectural change (long-short or 1h frequency)")

    out = REPO / "artifacts" / "quant_research" / "v71_exploration" / "v72_gate_alignment.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"median_disp_all": median_disp_all, "regime_summary": rows, "alignment_pass_count": pass_count, "alignment_total": len(rows), "alignment_score": overall_alignment}, indent=2),
        encoding="utf-8",
    )
    print(f"Saved: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
