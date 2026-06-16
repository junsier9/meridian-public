"""compute_liquidation_cascade_factor_report.py — SP-A admission + doc §E.12
falsification audit.

Two tests:

1. Doc E.12 falsification (per-subject time-series mechanism):
   For each subject, identify cascade events (1h liq_to_oi z > 2.5). Compute
   abnormal forward 24h / 5d return at event-time vs the subject's matched
   non-event sample mean. Pool across subjects, run t-test. Doc says
   t-stat < 2.5σ → REJECT mechanism.

2. Standard cross-sectional admission (G1, G3, G6 vs lsk3 baseline):
   Per (subject, date) cascade features merged into the cross-sectional
   panel. Spearman rank IC vs `target_forward_return` (5d).

Output: artifacts/quant_research/factor_reports/<as-of>/liq_cascade_factor_report_card.json
"""

from __future__ import annotations

import argparse
import glob
import json
import os
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

from enhengclaw.quant_research.feature_admission_v2 import (  # noqa: E402
    build_regime_by_ts,
    orthogonalize,
    per_timestamp_rank_ic,
)
from enhengclaw.quant_research.intraday_liquidation_features import (  # noqa: E402
    DEFAULT_OUTPUT_PATH,
    DEFAULT_TOP30_SUBJECTS,
    _load_subject_1h_liq_oi,
    write_liquidation_cascade_panel_csv,
)
from enhengclaw.quant_research.regime_gating import (  # noqa: E402
    DEFAULT_FEATURES_ARTIFACT,
    _load_panel,
    _rebuild_features_with_w3_columns,
)


CARD_CONTRACT_VERSION = "quant_factor_report_card_liq_cascade.v1"
G1_ABS_MIN = 0.04
G3_SAME_SIGN_MIN = 0.60
G6_ABS_MIN = 0.02
DOC_E12_T_STAT_THRESHOLD = 2.5  # doc §E.12 falsification

LSK3_BASELINE = (
    "intraday_realized_vol_4h_to_1d_smooth_60",
    "realized_volatility_5",
    "distance_to_high_60",
    "distance_to_high_5",
    "coinglass_top_trader_long_pct_smooth_5",
    "liquidity_stress_qv_iv",
    "momentum_decay_5_20",
    "coinglass_taker_imb_intraday_dispersion_24h",
    "quality_funding_oi",
    "downside_upside_vol_ratio_30",
    "funding_basis_residual_implied_repo_30",
)


def doc_e12_falsification(subjects: list[str]) -> dict:
    """Pool cascade events across subjects; t-test post-event vs non-event
    forward 24h log return. Per-subject log-returns computed from the 1h
    perp_close (read alongside coinglass + derivatives in the cascade panel
    builder).
    """
    abnormal_returns_pool: list[float] = []
    sample_means: list[tuple[str, int, float, float]] = []
    n_events_total = 0

    for symbol in subjects:
        bars = _load_subject_1h_liq_oi(symbol)
        if bars.empty:
            continue
        # We need perp_close for return computation; reload binance_derivatives 1h
        import os as _os
        from enhengclaw.quant_research.intraday_liquidation_features import _resolve_market_history_root
        root = _resolve_market_history_root()
        dv_paths = sorted(glob.glob(str(root / "binance_derivatives" / f"{symbol}USDT" / "1h" / "*.csv.gz")))
        if not dv_paths:
            continue
        dv = pd.concat([pd.read_csv(p, compression="gzip") for p in dv_paths], ignore_index=True)
        dv = dv[["open_time_ms", "perp_close"]].sort_values("open_time_ms").drop_duplicates("open_time_ms")
        merged = bars.merge(dv, on="open_time_ms", how="inner").reset_index(drop=True)
        if len(merged) < 1000:
            continue
        # Build z-score
        merged["liq_total"] = merged["long_liquidation_usd"].fillna(0.0) + merged["short_liquidation_usd"].fillna(0.0)
        merged["liq_to_oi"] = merged["liq_total"] / merged["open_interest_value"].replace(0.0, np.nan)
        rolling_mean = merged["liq_to_oi"].rolling(720, min_periods=180).mean()
        rolling_std = merged["liq_to_oi"].rolling(720, min_periods=180).std()
        merged["liq_z"] = (merged["liq_to_oi"] - rolling_mean) / rolling_std.replace(0.0, np.nan)
        # 24h forward log return
        merged["fwd_24h_log_ret"] = (
            np.log(merged["perp_close"].shift(-24) / merged["perp_close"])
        )
        # Cascade events
        events = merged[merged["liq_z"] > DOC_E12_T_STAT_THRESHOLD].dropna(subset=["fwd_24h_log_ret"])
        non_events = merged[(merged["liq_z"] <= DOC_E12_T_STAT_THRESHOLD)].dropna(subset=["fwd_24h_log_ret"])
        if len(events) < 5 or len(non_events) < 100:
            continue
        # Abnormal return per event = event fwd_24h - subject's non-event mean
        baseline = float(non_events["fwd_24h_log_ret"].mean())
        for ar in events["fwd_24h_log_ret"]:
            abnormal_returns_pool.append(float(ar) - baseline)
        sample_means.append((symbol, len(events), baseline, float(events["fwd_24h_log_ret"].mean())))
        n_events_total += len(events)

    if not abnormal_returns_pool:
        return {"status": "no_events", "n_events": 0}

    arr = np.asarray(abnormal_returns_pool)
    mean_ar = float(arr.mean())
    std_ar = float(arr.std())
    t_stat = float(mean_ar * np.sqrt(len(arr)) / std_ar) if std_ar > 0 else 0.0
    return {
        "status": "ok",
        "n_events": int(n_events_total),
        "n_subjects_with_events": int(len(sample_means)),
        "mean_abnormal_24h_log_return": mean_ar,
        "std_abnormal_24h_log_return": std_ar,
        "t_stat": t_stat,
        "doc_threshold_2_5_sigma": DOC_E12_T_STAT_THRESHOLD,
        "doc_e12_passes": abs(t_stat) >= DOC_E12_T_STAT_THRESHOLD,
    }


def cross_sectional_admission_audit(panel_csv_path: Path) -> dict:
    """Merge cascade panel into the cross-sectional features panel and run
    G1+G3+G6 admission against the canonical lsk3 11-factor baseline.
    """
    cv = pd.read_csv(panel_csv_path)
    cv = cv[
        [
            "subject",
            "date_utc",
            "liq_cascade_max_z_24h",
            "liq_cascade_count_24h_z25",
            "liq_cascade_signed_intensity_24h",
            "liq_cascade_recency_score_5d",
        ]
    ]
    panel = _load_panel(DEFAULT_FEATURES_ARTIFACT)
    features = _rebuild_features_with_w3_columns(panel)
    features["date_utc"] = features["timestamp_ms"].apply(
        lambda ms: datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).date().isoformat()
    )
    merged = features.merge(cv, on=["subject", "date_utc"], how="left")
    target = pd.to_numeric(merged["target_forward_return"], errors="coerce")
    ts = merged["timestamp_ms"]
    baseline = merged[list(LSK3_BASELINE)].apply(pd.to_numeric, errors="coerce")
    regime_label = build_regime_by_ts(features)

    cards: dict[str, dict] = {}
    for col in (
        "liq_cascade_max_z_24h",
        "liq_cascade_count_24h_z25",
        "liq_cascade_signed_intensity_24h",
        "liq_cascade_recency_score_5d",
    ):
        if col not in merged.columns:
            cards[col] = {"status": "missing"}
            continue
        factor = pd.to_numeric(merged[col], errors="coerce").fillna(0.0)
        ic = per_timestamp_rank_ic(factor, target, ts).dropna()
        n = int(len(ic))
        if n < 30:
            cards[col] = {"status": "insufficient", "n": n}
            continue
        m = float(ic.mean())
        s = float(ic.std())
        t = float(m * (n ** 0.5) / s) if s > 0 else 0.0

        aligned = regime_label.reindex(ic.index)
        df_g3 = pd.DataFrame({"ic": ic, "regime": aligned}).dropna()
        regime_ic = {str(r): float(g["ic"].mean()) for r, g in df_g3.groupby("regime") if len(g) >= 30}
        signs = [1 if v > 0 else -1 if v < 0 else 0 for v in regime_ic.values()]
        same_sign = max(signs.count(1), signs.count(-1)) / len(signs) if signs else 0

        residual = orthogonalize(factor, baseline)
        rs = per_timestamp_rank_ic(residual, target, ts).dropna()
        rm = float(rs.mean()) if len(rs) > 0 else 0.0
        rstd = float(rs.std()) if len(rs) > 1 else 0.0
        rt = float(rm * (len(rs) ** 0.5) / rstd) if rstd > 0 else 0.0

        cards[col] = {
            "n_ts": n,
            "g1": {"ic_mean": m, "ic_std": s, "t_stat": t, "abs_pass": abs(m) >= G1_ABS_MIN},
            "g3": {"regime_ic": regime_ic, "same_sign_fraction": same_sign, "pass": same_sign >= G3_SAME_SIGN_MIN},
            "g6_vs_lsk3": {
                "residual_ic_mean": rm,
                "residual_t_stat": rt,
                "abs_pass": abs(rm) >= G6_ABS_MIN,
            },
        }
    return cards


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SP-A liquidation cascade factor report card.")
    parser.add_argument("--as-of", required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "artifacts" / "quant_research" / "factor_reports",
    )
    args = parser.parse_args(argv)

    print("=== SP-A: rebuilding cascade panel ===")
    panel_path = write_liquidation_cascade_panel_csv()
    print(f"  panel at {panel_path}")
    print()

    print("=== Doc §E.12 falsification (per-subject post-event 24h abnormal return) ===")
    e12_result = doc_e12_falsification(list(DEFAULT_TOP30_SUBJECTS))
    print(json.dumps(e12_result, indent=2, sort_keys=True))
    print()

    print("=== Cross-sectional G1+G3+G6 admission audit ===")
    cs_cards = cross_sectional_admission_audit(panel_path)
    for fid, card in cs_cards.items():
        if "status" in card:
            print(f"  {fid}: {card.get('status')}")
            continue
        g1 = card["g1"]
        g3 = card["g3"]
        g6 = card["g6_vs_lsk3"]
        print(
            f"  {fid:42s}  G1 ic={g1['ic_mean']:+.4f} t={g1['t_stat']:+.2f} (n={card['n_ts']})  "
            f"G3 same={g3['same_sign_fraction']:.2f}  "
            f"G6 resid={g6['residual_ic_mean']:+.4f} t={g6['residual_t_stat']:+.2f} pass={g6['abs_pass']}"
        )

    out = {
        "contract_version": CARD_CONTRACT_VERSION,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": args.as_of,
        "thresholds": {
            "g1_abs_min": G1_ABS_MIN,
            "g3_same_sign_min": G3_SAME_SIGN_MIN,
            "g6_abs_min": G6_ABS_MIN,
            "doc_e12_t_stat": DOC_E12_T_STAT_THRESHOLD,
        },
        "doc_e12_falsification": e12_result,
        "cross_sectional_admission": cs_cards,
        "lsk3_baseline": list(LSK3_BASELINE),
    }
    out_dir = args.output_dir / args.as_of
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "liq_cascade_factor_report_card.json"
    out_path.write_text(json.dumps(out, indent=2, sort_keys=True), encoding="utf-8")
    print()
    print(f"=== Done. Card at {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
