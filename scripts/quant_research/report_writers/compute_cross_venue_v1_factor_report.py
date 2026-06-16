"""compute_cross_venue_v1_factor_report.py — per-asset cross-venue dispersion
admission audit (M2.1 v1).

v1 differs from v0 (compute_cross_venue_factor_report.py) by treating the
cross-venue dispersion as a CROSS-SECTIONAL per-asset factor instead of a
universe-wide gauge. Runs the standard 11-gate subset on it:
  - G1: per-timestamp Spearman rank IC vs `target_forward_return`
  - G3: regime sign-consistency across BTC vol tertiles
  - G6: residual IC after orthogonalizing against v91 9-factor and lsk3
        11-factor baselines

The factor pool is the panel from cross_venue_features.compute_cross_venue_panel
(top 30 universe × 4 venues × 1d, 2024-04 → 2026-04). Output JSON card lands
under artifacts/quant_research/factor_reports/<as-of>/.
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
    DEFAULT_PANEL_OUTPUT_PATH,
    compute_cross_venue_panel,
    write_cross_venue_panel_csv,
)
from enhengclaw.quant_research.feature_admission_v2 import (  # noqa: E402
    build_regime_by_ts,
    orthogonalize,
    per_timestamp_rank_ic,
)
from enhengclaw.quant_research.regime_gating import (  # noqa: E402
    DEFAULT_FEATURES_ARTIFACT,
    _load_panel,
    _rebuild_features_with_w3_columns,
)


CARD_CONTRACT_VERSION = "quant_factor_report_card_cross_venue.v1"
G1_ABS_MIN = 0.04
G3_SAME_SIGN_MIN = 0.60
G6_ABS_MIN = 0.02

V91_BASELINE_FACTORS: tuple[str, ...] = (
    "intraday_realized_vol_4h_to_1d_smooth_60",
    "realized_volatility_5",
    "distance_to_high_60",
    "distance_to_high_5",
    "coinglass_top_trader_long_pct_smooth_5",
    "liquidity_stress_qv_iv",
    "momentum_decay_5_20",
    "coinglass_taker_imb_intraday_dispersion_24h",
    "quality_funding_oi",
)
LSK3_BASELINE_FACTORS: tuple[str, ...] = V91_BASELINE_FACTORS + (
    "downside_upside_vol_ratio_30",
    "funding_basis_residual_implied_repo_30",
)


def _build_merged() -> pd.DataFrame:
    if not DEFAULT_PANEL_OUTPUT_PATH.exists():
        write_cross_venue_panel_csv()
    xv = pd.read_csv(DEFAULT_PANEL_OUTPUT_PATH)
    xv = xv[
        [
            "subject",
            "date_utc",
            "n_venues",
            "cross_venue_spot_dispersion",
            "cross_venue_spot_max_minus_min_over_mean",
            "cross_venue_spot_binance_premium",
        ]
    ]
    panel = _load_panel(DEFAULT_FEATURES_ARTIFACT)
    features = _rebuild_features_with_w3_columns(panel)
    features["date_utc"] = features["timestamp_ms"].apply(
        lambda ms: datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).date().isoformat()
    )
    return features.merge(xv, on=["subject", "date_utc"], how="left")


def _g1_ic(merged: pd.DataFrame, factor_col: str) -> dict:
    factor = pd.to_numeric(merged[factor_col], errors="coerce")
    target = pd.to_numeric(merged["target_forward_return"], errors="coerce")
    ic = per_timestamp_rank_ic(factor, target, merged["timestamp_ms"]).dropna()
    n = int(len(ic))
    if n < 30:
        return {"status": "insufficient_data", "n": n}
    mean = float(ic.mean())
    std = float(ic.std())
    t = float(mean * (n ** 0.5) / std) if std > 0 else 0.0
    return {
        "n_ts": n,
        "ic_mean": mean,
        "ic_std": std,
        "t_stat": t,
        "abs_ic_mean": abs(mean),
        "g1_pass": abs(mean) >= G1_ABS_MIN,
    }


def _g3_regime(merged: pd.DataFrame, factor_col: str, features: pd.DataFrame) -> dict:
    factor = pd.to_numeric(merged[factor_col], errors="coerce")
    target = pd.to_numeric(merged["target_forward_return"], errors="coerce")
    ic = per_timestamp_rank_ic(factor, target, merged["timestamp_ms"]).dropna()
    regime_label = build_regime_by_ts(features)
    regime_aligned = regime_label.reindex(ic.index)
    df = pd.DataFrame({"ic": ic, "regime": regime_aligned}).dropna()
    regime_ic: dict[str, float] = {}
    regime_n: dict[str, int] = {}
    for r, g in df.groupby("regime"):
        if len(g) < 30:
            continue
        regime_ic[str(r)] = float(g["ic"].mean())
        regime_n[str(r)] = int(len(g))
    if not regime_ic:
        return {"status": "no_regime_with_obs", "g3_pass": False}
    signs = [1 if v > 0 else -1 if v < 0 else 0 for v in regime_ic.values()]
    same_sign = max(signs.count(1), signs.count(-1)) / len(signs)
    return {
        "regime_ic": regime_ic,
        "regime_n": regime_n,
        "same_sign_fraction": float(same_sign),
        "g3_pass": same_sign >= G3_SAME_SIGN_MIN,
    }


def _g6_residual(merged: pd.DataFrame, factor_col: str, baseline_columns: tuple[str, ...]) -> dict:
    factor = pd.to_numeric(merged[factor_col], errors="coerce")
    target = pd.to_numeric(merged["target_forward_return"], errors="coerce")
    baseline = merged[list(baseline_columns)].apply(pd.to_numeric, errors="coerce")
    residual = orthogonalize(factor, baseline)
    ic = per_timestamp_rank_ic(residual, target, merged["timestamp_ms"]).dropna()
    n = int(len(ic))
    if n < 30:
        return {"status": "insufficient_data", "n": n, "g6_pass": False}
    mean = float(ic.mean())
    std = float(ic.std())
    t = float(mean * (n ** 0.5) / std) if std > 0 else 0.0
    return {
        "n_ts": n,
        "residual_ic_mean": mean,
        "residual_ic_std": std,
        "residual_t_stat": t,
        "abs_residual_ic": abs(mean),
        "g6_pass": abs(mean) >= G6_ABS_MIN,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="M2.1 v1 per-asset cross-venue factor report card.")
    parser.add_argument("--as-of", required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "artifacts" / "quant_research" / "factor_reports",
    )
    args = parser.parse_args(argv)

    merged = _build_merged()
    panel = _load_panel(DEFAULT_FEATURES_ARTIFACT)
    features = _rebuild_features_with_w3_columns(panel)

    factor_cols = (
        "cross_venue_spot_dispersion",
        "cross_venue_spot_max_minus_min_over_mean",
        "cross_venue_spot_binance_premium",
    )

    cards: dict[str, dict] = {}
    for col in factor_cols:
        if col not in merged.columns:
            continue
        cards[col] = {
            "factor_id": col,
            "g1": _g1_ic(merged, col),
            "g3": _g3_regime(merged, col, features),
            "g6_vs_v91": _g6_residual(merged, col, V91_BASELINE_FACTORS),
            "g6_vs_lsk3": _g6_residual(merged, col, LSK3_BASELINE_FACTORS),
        }

    out = {
        "contract_version": CARD_CONTRACT_VERSION,
        "cross_venue_data_contract": CROSS_VENUE_CONTRACT_VERSION,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": args.as_of,
        "thresholds": {
            "g1_abs_min": G1_ABS_MIN,
            "g3_same_sign_min": G3_SAME_SIGN_MIN,
            "g6_abs_min": G6_ABS_MIN,
        },
        "baselines": {
            "v91_9_factor": list(V91_BASELINE_FACTORS),
            "lsk3_11_factor": list(LSK3_BASELINE_FACTORS),
        },
        "factors": cards,
    }

    out_dir = args.output_dir / args.as_of
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "cross_venue_v1_factor_report_card.json"
    out_path.write_text(json.dumps(out, indent=2, sort_keys=True), encoding="utf-8")
    print(f"wrote {out_path}")
    print()
    print("=== summary ===")
    for fid, card in cards.items():
        g1 = card["g1"]
        g3 = card["g3"]
        g6_v91 = card["g6_vs_v91"]
        g6_lsk3 = card["g6_vs_lsk3"]
        print(
            f"  {fid:48s}  G1 ic={g1.get('ic_mean'):+.4f} t={g1.get('t_stat'):+.2f} pass={g1.get('g1_pass')}  "
            f"G3 same={g3.get('same_sign_fraction', 0):.2f} pass={g3.get('g3_pass')}  "
            f"G6_v91 ic={g6_v91.get('residual_ic_mean', 0):+.4f} pass={g6_v91.get('g6_pass')}  "
            f"G6_lsk3 ic={g6_lsk3.get('residual_ic_mean', 0):+.4f} pass={g6_lsk3.get('g6_pass')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
