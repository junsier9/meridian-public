"""compute_cross_venue_funding_factor_report.py — admission audit for the
M2.2 cross-venue funding dispersion factor (F14 lite probe).

Loads OKX funding 8h history (synced via OKX_API to LOCALAPPDATA/EnhengClaw/
okx_funding/), aligns with Binance funding from existing 4h derivatives store,
aggregates both to daily mean per (subject, date), and runs G1+G3+G6
admission on the cross-venue dispersion derivatives.

Limitation. OKX's public funding-rate-history endpoint returns only the
latest ~3 months (~270 obs at 8h grain). After daily aggregation, ~90
overlap days. Sample size is too small for definitive admission; this
script reports the audit as a PROBE quality result.

Output. JSON report card persisted to artifacts/quant_research/factor_reports/
<as-of>/cross_venue_funding_factor_report_card.json.
"""

from __future__ import annotations

import argparse
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
from enhengclaw.quant_research.regime_gating import (  # noqa: E402
    DEFAULT_FEATURES_ARTIFACT,
    _load_panel,
    _rebuild_features_with_w3_columns,
)


CARD_CONTRACT_VERSION = "quant_factor_report_card_cross_venue_funding.v1"
G1_ABS_MIN = 0.04
G3_SAME_SIGN_MIN = 0.60
G6_ABS_MIN = 0.02

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

OKX_FUNDING_ROOT = (
    Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share")))
    / "EnhengClaw"
    / "okx_funding"
)
BINANCE_DERIV_ROOT = (
    Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share")))
    / "EnhengClaw"
    / "market_history"
    / "binance_derivatives"
)


def _load_okx_funding_panel() -> pd.DataFrame:
    """Load OKX 8h funding from CSV cache → daily-mean per subject."""
    rows: list[pd.DataFrame] = []
    for csv_path in sorted(OKX_FUNDING_ROOT.glob("*_funding_8h.csv")):
        sym = csv_path.stem.replace("_funding_8h", "")
        df = pd.read_csv(csv_path)
        df["fundingRate"] = pd.to_numeric(df["fundingRate"], errors="coerce")
        df["fundingTime"] = pd.to_numeric(df["fundingTime"], errors="coerce").astype("Int64")
        df["date_utc"] = df["fundingTime"].apply(
            lambda ms: datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).date().isoformat()
        )
        daily = (
            df.groupby("date_utc")["fundingRate"]
            .mean()
            .reset_index()
            .rename(columns={"fundingRate": "okx_funding"})
        )
        daily["subject"] = sym
        rows.append(daily)
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True)


def _load_binance_funding_panel(subjects: list[str]) -> pd.DataFrame:
    """Load Binance funding from 4h derivatives → daily-mean per subject."""
    import glob
    rows: list[pd.DataFrame] = []
    for sym in subjects:
        paths = sorted(glob.glob(str(BINANCE_DERIV_ROOT / f"{sym}USDT" / "4h" / "*.csv.gz")))
        if not paths:
            continue
        df = pd.concat([pd.read_csv(p, compression="gzip") for p in paths], ignore_index=True)
        df["date_utc"] = df["open_time_ms"].apply(
            lambda ms: datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).date().isoformat()
        )
        daily = (
            df.groupby("date_utc")["funding_rate"]
            .mean()
            .reset_index()
            .rename(columns={"funding_rate": "binance_funding"})
        )
        daily["subject"] = sym
        rows.append(daily)
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True)


def build_cross_venue_funding_panel() -> pd.DataFrame:
    okx = _load_okx_funding_panel()
    if okx.empty:
        raise RuntimeError(
            f"no OKX funding data at {OKX_FUNDING_ROOT}. Run the M2.2 sync first."
        )
    subjects = sorted(okx["subject"].unique().tolist())
    binance = _load_binance_funding_panel(subjects)
    if binance.empty:
        raise RuntimeError("no Binance derivatives data")
    merged = binance.merge(okx, on=["subject", "date_utc"], how="inner")
    merged["cross_venue_funding_abs_diff"] = (
        merged["binance_funding"] - merged["okx_funding"]
    ).abs()
    merged["cross_venue_funding_signed_diff"] = merged["binance_funding"] - merged["okx_funding"]
    return merged


def _audit(merged_features: pd.DataFrame, factor_col: str, panel_features: pd.DataFrame) -> dict:
    factor = pd.to_numeric(merged_features[factor_col], errors="coerce")
    target = pd.to_numeric(merged_features["target_forward_return"], errors="coerce")
    ts = merged_features["timestamp_ms"]
    ic = per_timestamp_rank_ic(factor, target, ts).dropna()
    n = int(len(ic))
    if n < 30:
        return {"factor_id": factor_col, "n_ts": n, "status": "insufficient_sample"}
    mean = float(ic.mean())
    std = float(ic.std())
    t = float(mean * (n ** 0.5) / std) if std > 0 else 0.0

    regime_label = build_regime_by_ts(panel_features)
    aligned = regime_label.reindex(ic.index)
    df = pd.DataFrame({"ic": ic, "regime": aligned}).dropna()
    regime_ic = {
        str(r): float(g["ic"].mean()) for r, g in df.groupby("regime") if len(g) >= 15
    }
    if regime_ic:
        signs = [1 if v > 0 else -1 if v < 0 else 0 for v in regime_ic.values()]
        same_sign = max(signs.count(1), signs.count(-1)) / len(signs)
    else:
        same_sign = 0.0

    baseline = merged_features[list(LSK3_BASELINE)].apply(pd.to_numeric, errors="coerce")
    residual = orthogonalize(factor, baseline)
    rs = per_timestamp_rank_ic(residual, target, ts).dropna()
    rm = float(rs.mean()) if len(rs) > 0 else 0.0
    rstd = float(rs.std()) if len(rs) > 1 else 0.0
    rt = float(rm * (len(rs) ** 0.5) / rstd) if rstd > 0 else 0.0

    return {
        "factor_id": factor_col,
        "n_ts": n,
        "g1": {"ic_mean": mean, "ic_std": std, "t_stat": t, "abs_pass": abs(mean) >= G1_ABS_MIN},
        "g3": {
            "regime_ic": regime_ic,
            "same_sign_fraction": same_sign,
            "pass": same_sign >= G3_SAME_SIGN_MIN,
        },
        "g6_vs_lsk3": {
            "residual_ic": rm,
            "residual_std": rstd,
            "t_stat": rt,
            "abs_pass": abs(rm) >= G6_ABS_MIN,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="M2.2 cross-venue funding factor report card.")
    parser.add_argument("--as-of", required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "artifacts" / "quant_research" / "factor_reports",
    )
    args = parser.parse_args(argv)

    cv_panel = build_cross_venue_funding_panel()
    panel = _load_panel(DEFAULT_FEATURES_ARTIFACT)
    panel_features = _rebuild_features_with_w3_columns(panel)
    panel_features["date_utc"] = panel_features["timestamp_ms"].apply(
        lambda ms: datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).date().isoformat()
    )
    merged = panel_features.merge(
        cv_panel[
            [
                "subject",
                "date_utc",
                "binance_funding",
                "okx_funding",
                "cross_venue_funding_abs_diff",
                "cross_venue_funding_signed_diff",
            ]
        ],
        on=["subject", "date_utc"],
        how="left",
    )

    cards: dict[str, dict] = {}
    for col in (
        "cross_venue_funding_abs_diff",
        "cross_venue_funding_signed_diff",
    ):
        cards[col] = _audit(merged, col, panel_features)

    out = {
        "contract_version": CARD_CONTRACT_VERSION,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": args.as_of,
        "thresholds": {
            "g1_abs_min": G1_ABS_MIN,
            "g3_same_sign_min": G3_SAME_SIGN_MIN,
            "g6_abs_min": G6_ABS_MIN,
        },
        "lsk3_baseline": list(LSK3_BASELINE),
        "data_source": {
            "okx_funding_root": str(OKX_FUNDING_ROOT),
            "n_okx_subjects": int(cv_panel["subject"].nunique()),
            "n_overlap_rows": int(len(cv_panel)),
            "date_range": {
                "start": str(cv_panel["date_utc"].min()),
                "end": str(cv_panel["date_utc"].max()),
            },
        },
        "factors": cards,
        "probe_quality_disclosure": (
            "OKX public funding-rate-history endpoint returns ~3 months of data "
            "(~270 8h obs per symbol → ~90 daily obs after aggregation). With this "
            "small sample, t-statistics are noisy; admission verdicts should be "
            "treated as PROBE quality, not strict admission. Re-audit when longer "
            "OKX history is available (paid endpoint or alternative venue)."
        ),
    }

    out_dir = args.output_dir / args.as_of
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "cross_venue_funding_factor_report_card.json"
    out_path.write_text(json.dumps(out, indent=2, sort_keys=True), encoding="utf-8")
    print(f"wrote {out_path}")
    print()
    for fid, card in cards.items():
        if "status" in card:
            print(f"  {fid}: {card['status']}")
            continue
        g1 = card["g1"]
        g3 = card["g3"]
        g6 = card["g6_vs_lsk3"]
        print(
            f"  {fid:35s}  G1 ic={g1['ic_mean']:+.4f} t={g1['t_stat']:+.2f} (n={card['n_ts']})  "
            f"G3 same={g3['same_sign_fraction']:.2f} pass={g3['pass']}  "
            f"G6 resid_ic={g6['residual_ic']:+.4f} t={g6['t_stat']:+.2f} pass={g6['abs_pass']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
