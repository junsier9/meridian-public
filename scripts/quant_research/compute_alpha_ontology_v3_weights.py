"""compute_alpha_ontology_v3_weights.py — derive Bayesian-IR-shrunk weights
for the 11 lsk3 score factors (W3.6).

Method.
  1. Load the latest committed cross-sectional features panel.
  2. Use the FIRST 60% of unique timestamps as the in-sample weight-estimation
     window (the remaining 40% is held back so cycle walk-forward windows that
     start later are at least partially OOS for these weights).
  3. For each factor, compute the per-timestamp Spearman rank IC of the factor
     against `target_forward_return` (the cycle's canonical 5d forward return).
  4. Apply Bayesian shrinkage with prior IC=0 in t-stat units:
       t_obs       = ic_mean * sqrt(n_ts) / ic_std
       posterior   = ic_mean * (t_obs**2 / (t_obs**2 + tau_t**2))
     where tau_t = 2.0 (factors with |t| < 2 get heavily shrunk toward 0).
  5. Scale posterior IC to a weight using the v91 ratio |w|/|IC| ≈ 3.25 (so
     magnitudes are comparable to the hand-tuned weights).

Output.
  Writes config/quant_research/alpha_ontology_v3_weights.json with:
    - contract_version
    - in_sample_window {start_ts_ms, end_ts_ms, fraction, n_unique_ts}
    - hyperparameters {tau_t, ic_to_weight_scale}
    - factors[]: {column, hand_tuned_weight (lsk3), ic_mean, ic_std, n_ts,
      t_stat, shrunk_ic, weight (Bayesian)}

Determinism.
  This script is deterministic given the input panel and the unchanged
  hyperparameters. The output JSON is checked in alongside features.py so
  xs_alpha_ontology_v3_score reads from the file, not from a runtime
  computation. Re-running this script regenerates the JSON; any change to
  hyperparameters or panel must be recorded in threshold_provenance.md.
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
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.feature_admission_v2 import per_timestamp_rank_ic  # noqa: E402
from enhengclaw.quant_research.regime_gating import (  # noqa: E402
    DEFAULT_FEATURES_ARTIFACT,
    _load_panel,
    _rebuild_features_with_w3_columns,
)


# Identical to xs_alpha_ontology_v1_score's 11 factors and signs. Magnitudes
# are reference only (the v3 weights override them).
LSK3_FACTORS_HAND_TUNED: list[tuple[str, float]] = [
    ("intraday_realized_vol_4h_to_1d_smooth_60",     -0.20),
    ("realized_volatility_5",                        -0.10),
    ("distance_to_high_60",                          +0.18),
    ("distance_to_high_5",                           +0.15),
    ("coinglass_top_trader_long_pct_smooth_5",       -0.07),
    ("liquidity_stress_qv_iv",                       -0.10),
    ("momentum_decay_5_20",                          -0.06),
    ("coinglass_taker_imb_intraday_dispersion_24h",  +0.05),
    ("quality_funding_oi",                           -0.05),
    ("downside_upside_vol_ratio_30",                 +0.10),
    ("funding_basis_residual_implied_repo_30",       +0.07),
]

V3_WEIGHTS_CONTRACT_VERSION = "quant_alpha_ontology_v3_weights.v1"
DEFAULT_TAU_T = 2.0
DEFAULT_IC_TO_WEIGHT_SCALE = 3.25
DEFAULT_IN_SAMPLE_FRACTION = 0.60


def compute_v3_weights(
    *,
    features_artifact: Path | None = None,
    in_sample_fraction: float = DEFAULT_IN_SAMPLE_FRACTION,
    tau_t: float = DEFAULT_TAU_T,
    ic_to_weight_scale: float = DEFAULT_IC_TO_WEIGHT_SCALE,
) -> dict:
    artifact = features_artifact or DEFAULT_FEATURES_ARTIFACT
    panel = _load_panel(artifact)
    features = _rebuild_features_with_w3_columns(panel)

    ts_unique = sorted(features["timestamp_ms"].unique())
    cutoff_idx = max(1, int(len(ts_unique) * in_sample_fraction))
    cutoff_ts = ts_unique[cutoff_idx - 1]
    in_sample = features[features["timestamp_ms"] <= cutoff_ts].copy()

    target = pd.to_numeric(in_sample["target_forward_return"], errors="coerce")

    factor_records: list[dict] = []
    for col, hand_w in LSK3_FACTORS_HAND_TUNED:
        if col not in in_sample.columns:
            factor_records.append(
                {
                    "column": col,
                    "hand_tuned_weight": hand_w,
                    "status": "missing_column",
                    "weight": 0.0,
                }
            )
            continue
        factor = pd.to_numeric(in_sample[col], errors="coerce")
        ic_series = per_timestamp_rank_ic(factor, target, in_sample["timestamp_ms"]).dropna()
        n_ts = int(len(ic_series))
        ic_mean = float(ic_series.mean()) if n_ts > 0 else 0.0
        ic_std = float(ic_series.std()) if n_ts > 1 else 0.0
        if ic_std <= 0.0 or n_ts < 30:
            t_stat = 0.0
            shrunk_ic = 0.0
            status = "insufficient_signal"
        else:
            t_stat = ic_mean * (n_ts ** 0.5) / ic_std
            shrunk_ic = ic_mean * (t_stat ** 2) / (t_stat ** 2 + tau_t ** 2)
            status = "ok"
        weight = round(shrunk_ic * ic_to_weight_scale, 6)
        factor_records.append(
            {
                "column": col,
                "hand_tuned_weight": hand_w,
                "ic_mean": ic_mean,
                "ic_std": ic_std,
                "n_ts": n_ts,
                "t_stat": t_stat,
                "shrunk_ic": shrunk_ic,
                "weight": weight,
                "status": status,
            }
        )

    out = {
        "contract_version": V3_WEIGHTS_CONTRACT_VERSION,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "features_artifact": str(artifact),
        "in_sample_window": {
            "start_ts_ms": int(ts_unique[0]),
            "end_ts_ms": int(cutoff_ts),
            "fraction_of_panel": in_sample_fraction,
            "n_unique_ts_in_sample": cutoff_idx,
            "n_unique_ts_total": len(ts_unique),
            "start_date_utc": datetime.fromtimestamp(
                int(ts_unique[0]) / 1000, tz=timezone.utc
            ).date().isoformat(),
            "end_date_utc": datetime.fromtimestamp(
                int(cutoff_ts) / 1000, tz=timezone.utc
            ).date().isoformat(),
        },
        "hyperparameters": {
            "tau_t": tau_t,
            "ic_to_weight_scale": ic_to_weight_scale,
        },
        "factors": factor_records,
        "summary": {
            "sum_abs_hand_tuned": float(
                sum(abs(r.get("hand_tuned_weight", 0.0)) for r in factor_records)
            ),
            "sum_abs_v3": float(sum(abs(r.get("weight", 0.0)) for r in factor_records)),
            "sign_match_count": int(
                sum(
                    1
                    for r in factor_records
                    if r.get("status") == "ok"
                    and (r.get("hand_tuned_weight", 0.0) * r.get("weight", 0.0)) > 0.0
                )
            ),
        },
    }
    return out


def _cli() -> int:
    parser = argparse.ArgumentParser(description="Compute alpha_ontology_v3 Bayesian-IR weights.")
    parser.add_argument("--features-artifact", type=Path, default=None)
    parser.add_argument("--in-sample-fraction", type=float, default=DEFAULT_IN_SAMPLE_FRACTION)
    parser.add_argument("--tau-t", type=float, default=DEFAULT_TAU_T)
    parser.add_argument("--ic-to-weight-scale", type=float, default=DEFAULT_IC_TO_WEIGHT_SCALE)
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "config" / "quant_research" / "alpha_ontology_v3_weights.json",
    )
    parser.add_argument("--print-only", action="store_true")
    args = parser.parse_args()

    payload = compute_v3_weights(
        features_artifact=args.features_artifact,
        in_sample_fraction=args.in_sample_fraction,
        tau_t=args.tau_t,
        ic_to_weight_scale=args.ic_to_weight_scale,
    )
    text = json.dumps(payload, indent=2, sort_keys=True)
    if args.print_only:
        print(text)
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text + "\n", encoding="utf-8")
    print(f"wrote {args.out}")
    print(f"sum |hand_tuned| = {payload['summary']['sum_abs_hand_tuned']:.3f}")
    print(f"sum |v3|         = {payload['summary']['sum_abs_v3']:.3f}")
    print(f"sign matches     = {payload['summary']['sign_match_count']} / {len(payload['factors'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
