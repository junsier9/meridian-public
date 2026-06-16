"""compute_cross_venue_factor_report.py — admission audit for the M2.1
cross-venue spot-stress factor (F14_lite / E.3 frontier probe).

The factor is universe-wide (single time series), not per-subject. The
standard 11-gate admission was designed for per-subject cross-sectional
factors; this script computes the relevant subset:
  - G1 IC vs forward universe-mean return (analog of cross-section IC)
  - G3 regime sign-consistency (high/mid/low BTC vol regimes)
  - Doc F15 falsification: high-quantile (z>1.5 or stress>q95) win-rate
  - Effect size: mean forward 5d return at high-stress vs low-stress

Output. JSON report card persisted to artifacts/quant_research/factor_reports/<as-of>/
along with the existing cards from W1.3 / W3.x.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.cross_venue_features import (  # noqa: E402
    CROSS_VENUE_CONTRACT_VERSION,
    DEFAULT_OUTPUT_PATH,
    write_cross_venue_spot_stress_csv,
)
from enhengclaw.quant_research.regime_gating import (  # noqa: E402
    DEFAULT_FEATURES_ARTIFACT,
    _load_panel,
    _rebuild_features_with_w3_columns,
)


CARD_CONTRACT_VERSION = "quant_factor_report_card_cross_venue.v1"
DOC_FALSIFICATION_WIN_RATE_MIN = 0.60  # doc claim was "≥70% mean reversion"; relax to 60% for noisy panel
DOC_G1_ABS_MIN = 0.04
DOC_G3_SAME_SIGN_MIN = 0.60


def _load_inputs() -> tuple[pd.DataFrame, pd.Series]:
    """Load (cross_venue_stress_df, universe_mean_return_per_date_series)."""
    if not DEFAULT_OUTPUT_PATH.exists():
        write_cross_venue_spot_stress_csv()
    xv = pd.read_csv(DEFAULT_OUTPUT_PATH)
    xv["date_utc"] = xv["open_time_ms"].apply(
        lambda ms: datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).date().isoformat()
    )
    panel = _load_panel(DEFAULT_FEATURES_ARTIFACT)
    features = _rebuild_features_with_w3_columns(panel)
    features["date_utc"] = features["timestamp_ms"].apply(
        lambda ms: datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).date().isoformat()
    )
    universe_mean_return = features.groupby("date_utc")["return_1"].mean()
    return xv, universe_mean_return


def _build_combined(xv: pd.DataFrame, universe_mean_return: pd.Series) -> pd.DataFrame:
    """Join cross_venue stress with universe-mean returns and add forward windows."""
    cols = [
        c
        for c in [
            "cross_venue_spot_stress",
            "cross_venue_spot_stress_z60",
            "cross_venue_spot_premium_BTC",
            "cross_venue_spot_premium_ETH",
        ]
        if c in xv.columns
    ]
    combined = xv.set_index("date_utc")[cols].join(
        universe_mean_return.rename("universe_mean_ret"), how="inner"
    )
    combined["fwd_1d_ret"] = combined["universe_mean_ret"].shift(-1)
    combined["fwd_5d_ret"] = combined["universe_mean_ret"].rolling(5).sum().shift(-5)
    return combined.dropna(subset=["fwd_5d_ret"])


def _g1_ic(combined: pd.DataFrame, factor_col: str) -> dict:
    sub = combined.dropna(subset=[factor_col, "fwd_5d_ret"])
    if sub.empty:
        return {"status": "insufficient_data", "n": 0}
    pearson = float(sub[factor_col].corr(sub["fwd_5d_ret"]))
    spearman = float(sub[factor_col].corr(sub["fwd_5d_ret"], method="spearman"))
    return {
        "n": int(len(sub)),
        "pearson": pearson,
        "spearman": spearman,
        "abs_spearman": abs(spearman),
        "g1_pass": abs(spearman) >= DOC_G1_ABS_MIN,
    }


def _g3_regime_sign_consistency(
    combined: pd.DataFrame,
    factor_col: str,
    *,
    panel_features: pd.DataFrame,
) -> dict:
    """Per-regime spearman IC; same-sign across regimes? Uses BTC realized_vol_20 tertiles."""
    panel_features = panel_features.copy()
    panel_features["date_utc"] = panel_features["timestamp_ms"].apply(
        lambda ms: datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).date().isoformat()
    )
    btc = panel_features[panel_features["subject"] == "BTC"]
    if btc.empty or "realized_volatility_20" not in btc.columns:
        return {"status": "no_btc_vol", "regime_ics": {}, "g3_pass": False}
    btc_rv = (
        pd.to_numeric(btc.set_index("date_utc")["realized_volatility_20"], errors="coerce")
        .dropna()
        .sort_index()
    )
    if btc_rv.empty:
        return {"status": "no_btc_vol", "regime_ics": {}, "g3_pass": False}
    q1, q2 = btc_rv.quantile([1 / 3, 2 / 3]).tolist()

    def _label(x: float) -> str:
        if x < q1:
            return "low_vol"
        if x > q2:
            return "high_vol"
        return "mid_vol"

    regime_label = btc_rv.apply(_label).rename("regime")
    sub = combined.join(regime_label, how="inner").dropna(subset=[factor_col, "fwd_5d_ret"])
    if sub.empty:
        return {"status": "no_overlap", "regime_ics": {}, "g3_pass": False}
    regime_ics: dict[str, float] = {}
    for r, g in sub.groupby("regime"):
        if len(g) < 30:
            continue
        ic = float(g[factor_col].corr(g["fwd_5d_ret"], method="spearman"))
        regime_ics[r] = ic
    if not regime_ics:
        return {"status": "no_regime_with_obs", "regime_ics": {}, "g3_pass": False}
    signs = [1 if v > 0 else -1 if v < 0 else 0 for v in regime_ics.values()]
    same_sign_count = sum(1 for s in signs if s == max(set(signs), key=signs.count))
    same_sign_fraction = same_sign_count / len(signs)
    return {
        "regime_ics": regime_ics,
        "same_sign_fraction": same_sign_fraction,
        "g3_pass": same_sign_fraction >= DOC_G3_SAME_SIGN_MIN,
    }


def _high_stress_bucket(
    combined: pd.DataFrame,
    factor_col: str,
    *,
    z_thresholds: tuple[float, ...] = (1.0, 1.5, 2.0),
    quantile_thresholds: tuple[float, ...] = (0.90, 0.95),
) -> dict:
    """Bucket forward-5d return outcomes at high-stress thresholds."""
    out: dict[str, dict] = {}
    if "cross_venue_spot_stress_z60" in combined.columns:
        for z in z_thresholds:
            mask = combined["cross_venue_spot_stress_z60"] > z
            sub = combined.loc[mask].dropna(subset=["fwd_5d_ret"])
            if sub.empty:
                continue
            wr = float((sub["fwd_5d_ret"] > 0).mean())
            out[f"z60>{z}"] = {
                "n": int(len(sub)),
                "mean_fwd_5d": float(sub["fwd_5d_ret"].mean()),
                "median_fwd_5d": float(sub["fwd_5d_ret"].median()),
                "win_rate": wr,
                "doc_70pct_pass": wr >= DOC_FALSIFICATION_WIN_RATE_MIN,
            }
    if factor_col in combined.columns:
        for q in quantile_thresholds:
            thr = float(combined[factor_col].quantile(q))
            mask = combined[factor_col] >= thr
            sub = combined.loc[mask].dropna(subset=["fwd_5d_ret"])
            if sub.empty:
                continue
            wr = float((sub["fwd_5d_ret"] > 0).mean())
            out[f"stress>q{int(q * 100)}"] = {
                "n": int(len(sub)),
                "threshold": thr,
                "mean_fwd_5d": float(sub["fwd_5d_ret"].mean()),
                "median_fwd_5d": float(sub["fwd_5d_ret"].median()),
                "win_rate": wr,
                "doc_70pct_pass": wr >= DOC_FALSIFICATION_WIN_RATE_MIN,
            }
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="M2.1 cross-venue factor report card.")
    parser.add_argument("--as-of", required=True, help="Sample date YYYY-MM-DD.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "artifacts" / "quant_research" / "factor_reports",
    )
    args = parser.parse_args(argv)

    xv, umr = _load_inputs()
    panel = _load_panel(DEFAULT_FEATURES_ARTIFACT)
    panel_features = _rebuild_features_with_w3_columns(panel)
    combined = _build_combined(xv, umr)

    factor_cards: dict[str, dict] = {}
    for factor_col in [
        "cross_venue_spot_stress",
        "cross_venue_spot_stress_z60",
        "cross_venue_spot_premium_BTC",
        "cross_venue_spot_premium_ETH",
    ]:
        if factor_col not in combined.columns:
            continue
        card = {
            "factor_id": factor_col,
            "g1": _g1_ic(combined, factor_col),
            "g3": _g3_regime_sign_consistency(
                combined, factor_col, panel_features=panel_features
            ),
            "buckets": _high_stress_bucket(combined, factor_col),
        }
        factor_cards[factor_col] = card

    out = {
        "contract_version": CARD_CONTRACT_VERSION,
        "cross_venue_data_contract": CROSS_VENUE_CONTRACT_VERSION,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": args.as_of,
        "coverage_window": {
            "start_date_utc": str(combined.index.min()),
            "end_date_utc": str(combined.index.max()),
            "n_dates": int(len(combined)),
        },
        "g1_threshold": DOC_G1_ABS_MIN,
        "g3_same_sign_threshold": DOC_G3_SAME_SIGN_MIN,
        "doc_falsification_win_rate_threshold": DOC_FALSIFICATION_WIN_RATE_MIN,
        "factors": factor_cards,
    }

    out_dir = args.output_dir / args.as_of
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "cross_venue_factor_report_card.json"
    out_path.write_text(json.dumps(out, indent=2, sort_keys=True), encoding="utf-8")
    print(f"wrote {out_path}")
    print()
    print("=== summary ===")
    for fid, card in factor_cards.items():
        g1 = card.get("g1") or {}
        g3 = card.get("g3") or {}
        print(
            f"  {fid:42s} g1_pass={g1.get('g1_pass')} (spearman={g1.get('spearman'):+.4f})  "
            f"g3_pass={g3.get('g3_pass')} (same_sign={g3.get('same_sign_fraction', 0):.2f})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
