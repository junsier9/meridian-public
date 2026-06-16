"""SP-K Stage 1: continuous post-pump factor diagnostics.

Builds a small family of continuous post-pump / post-stall factor candidates
from the daily cross-sectional panel, then audits them with the standard
admission-style lenses:

1. G1: full-sample per-timestamp rank IC magnitude
2. G3: regime sign consistency across BTC vol tertiles
3. G6: residual IC versus lsk3 baseline
4. G6+: residual IC versus lsk3 plus liquidation-cascade sibling

The hypothesis is intentionally narrow: these factors are expected to work
primarily in mid / tail ex-major alt perps, not in the full universe.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

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


CARD_CONTRACT_VERSION = "quant_sp_k_post_pump_factor_report.v1"
DEFAULT_MAJOR_SUBJECTS = ("BTC", "ETH")
DEFAULT_MIN_LISTING_AGE_DAYS = 60
DEFAULT_HORIZONS = (5, 10)

G1_ABS_MIN = 0.04
G3_SAME_SIGN_MIN = 0.60
G6_ABS_MIN = 0.02
G3_REGIME_MIN_TS = 15

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


def _discover_latest_daily_features_artifact(features_root: Path) -> Path:
    pattern = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})-cross-sectional-daily-1d-features-v1$")
    candidates: list[tuple[str, Path]] = []
    for child in features_root.iterdir():
        if not child.is_dir():
            continue
        match = pattern.match(child.name)
        if not match:
            continue
        artifact = child / "features.csv.gz"
        if artifact.exists():
            candidates.append((match.group("date"), artifact))
    if not candidates:
        raise FileNotFoundError(
            f"no daily features artifact matching '*-cross-sectional-daily-1d-features-v1' under {features_root}"
        )
    candidates.sort(key=lambda item: item[0])
    return candidates[-1][1]


def _require_columns(frame: pd.DataFrame, required: Iterable[str]) -> None:
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise RuntimeError(f"required columns missing from features artifact: {missing}")


def _t_stat(values: pd.Series) -> float:
    series = pd.to_numeric(values, errors="coerce").dropna()
    if len(series) < 2:
        return 0.0
    std = float(series.std())
    if std <= 0.0:
        return 0.0
    return float(series.mean() * np.sqrt(len(series)) / std)


def _prepare_panel(
    features_artifact: Path,
    *,
    min_listing_age_days: int,
    horizons: Iterable[int],
) -> pd.DataFrame:
    frame = pd.read_csv(features_artifact, compression="gzip")
    required = set(
        [
            "subject",
            "timestamp_ms",
            "date_utc",
            "liquidity_bucket",
            "spot_close",
            "return_1",
            "realized_volatility_20",
            "abnormal_range_z_60",
            "quote_volume_expansion",
            "oi_change_5",
            "funding_zscore_20",
            "distance_to_high_5",
            "perp_execution_eligible",
            "listing_age_days_as_of",
            "target_forward_return",
            "liq_cascade_recency_score_5d",
        ]
        + list(LSK3_BASELINE)
    )
    _require_columns(frame, required)

    numeric_columns = sorted(
        {
            "spot_close",
            "return_1",
            "realized_volatility_20",
            "abnormal_range_z_60",
            "quote_volume_expansion",
            "oi_change_5",
            "funding_zscore_20",
            "distance_to_high_5",
            "listing_age_days_as_of",
            "target_forward_return",
            "liq_cascade_recency_score_5d",
            *LSK3_BASELINE,
        }
    )
    for column in numeric_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    eligible = frame["perp_execution_eligible"].fillna(False).astype(bool)
    eligible &= frame["listing_age_days_as_of"].fillna(0).ge(min_listing_age_days)
    eligible &= frame["spot_close"].fillna(0).gt(0)
    frame = frame.loc[eligible].copy()
    frame = frame.sort_values(["subject", "timestamp_ms"]).reset_index(drop=True)

    frame["pump_return_sigma"] = frame["return_1"] / frame["realized_volatility_20"].replace(0.0, np.nan)
    for horizon in horizons:
        if horizon == 5:
            frame["forward_5d_log_return"] = pd.to_numeric(frame["target_forward_return"], errors="coerce")
        else:
            frame[f"forward_{horizon}d_log_return"] = frame.groupby("subject")["spot_close"].transform(
                lambda close: np.log(close.shift(-horizon) / close)
            )
    return frame


def _build_factor_candidates(frame: pd.DataFrame) -> dict[str, pd.Series]:
    pump_core_intensity = (
        (frame["pump_return_sigma"] - 2.0).clip(lower=0.0)
        * (frame["abnormal_range_z_60"] - 1.0).clip(lower=0.0)
        * (frame["quote_volume_expansion"] - 1.5).clip(lower=0.0)
    )
    pump_core_yesterday = pump_core_intensity.groupby(frame["subject"]).shift(1).fillna(0.0)

    factors = {
        "pump_core_overextension_score": pump_core_intensity,
        "pump_crowding_overextension_score": (
            pump_core_intensity
            * frame["oi_change_5"].clip(lower=0.0)
            * (0.25 + frame["funding_zscore_20"]).clip(lower=0.0)
        ),
        "post_pump_stall_strict_score": (
            pump_core_yesterday
            * (0.015 - frame["return_1"]).clip(lower=0.0)
            * (frame["distance_to_high_5"] + 0.05).clip(lower=0.0)
            * frame["oi_change_5"].clip(lower=0.0)
            * frame["funding_zscore_20"].clip(lower=0.0)
        ),
        "post_pump_stall_soft_score": (
            pump_core_yesterday
            * (0.02 - frame["return_1"]).clip(lower=0.0)
            * (0.05 + frame["distance_to_high_5"]).clip(lower=0.0)
            * (0.02 + frame["oi_change_5"]).clip(lower=0.0)
            * (0.10 + frame["funding_zscore_20"]).clip(lower=0.0)
        ),
    }
    return {name: pd.to_numeric(series, errors="coerce").fillna(0.0) for name, series in factors.items()}


def _build_cohort_masks(frame: pd.DataFrame, *, major_subjects: tuple[str, ...]) -> dict[str, pd.Series]:
    ex_majors = ~frame["subject"].isin(major_subjects)
    mid = frame["liquidity_bucket"].eq("mid_liquidity")
    tail = frame["liquidity_bucket"].eq("tail_liquidity")
    top = frame["liquidity_bucket"].eq("top_liquidity")
    return {
        "all_eligible": pd.Series(True, index=frame.index),
        "mid_tail_ex_majors": (mid | tail) & ex_majors,
        "tail_ex_majors": tail & ex_majors,
        "top_ex_majors": top & ex_majors,
    }


def _audit_factor(
    factor: pd.Series,
    *,
    target: pd.Series,
    ts: pd.Series,
    cohort_mask: pd.Series,
    regime_label: pd.Series,
    baseline_lsk3: pd.DataFrame,
    baseline_lsk3_plus_cascade: pd.DataFrame,
) -> dict:
    factor_sub = pd.to_numeric(factor.where(cohort_mask), errors="coerce")
    target_sub = pd.to_numeric(target.where(cohort_mask), errors="coerce")
    ts_sub = ts.where(cohort_mask)

    ic = per_timestamp_rank_ic(factor_sub, target_sub, ts_sub).dropna()
    nonzero_rows = int((factor_sub.fillna(0.0).abs() > 0.0).sum())
    cohort_rows = int(cohort_mask.sum())
    cohort_subjects = int(pd.Series(cohort_mask.index[cohort_mask]).shape[0])
    if ic.empty:
        return {
            "status": "no_valid_ic",
            "cohort_rows": cohort_rows,
            "nonzero_rows": nonzero_rows,
            "nonzero_row_fraction": float(nonzero_rows / max(cohort_rows, 1)),
            "cohort_subject_rows": cohort_subjects,
        }

    g1_mean = float(ic.mean())
    g1_std = float(ic.std()) if len(ic) > 1 else 0.0
    g1_t = _t_stat(ic)

    aligned_regime = regime_label.reindex(ic.index)
    regime_frame = pd.DataFrame({"ic": ic, "regime": aligned_regime}).dropna()
    regime_ic = {
        str(regime): float(group["ic"].mean())
        for regime, group in regime_frame.groupby("regime")
        if len(group) >= G3_REGIME_MIN_TS
    }
    signs = [1 if value > 0 else -1 if value < 0 else 0 for value in regime_ic.values()]
    same_sign_fraction = (
        max(signs.count(1), signs.count(-1)) / len(signs) if signs else 0.0
    )

    residual_lsk3 = orthogonalize(factor_sub, baseline_lsk3.where(cohort_mask))
    residual_ic_lsk3 = per_timestamp_rank_ic(residual_lsk3, target_sub, ts_sub).dropna()
    residual_lsk3_mean = float(residual_ic_lsk3.mean()) if len(residual_ic_lsk3) else 0.0
    residual_lsk3_t = _t_stat(residual_ic_lsk3)

    residual_lsk3_cascade = orthogonalize(factor_sub, baseline_lsk3_plus_cascade.where(cohort_mask))
    residual_ic_lsk3_cascade = per_timestamp_rank_ic(residual_lsk3_cascade, target_sub, ts_sub).dropna()
    residual_lsk3_cascade_mean = float(residual_ic_lsk3_cascade.mean()) if len(residual_ic_lsk3_cascade) else 0.0
    residual_lsk3_cascade_t = _t_stat(residual_ic_lsk3_cascade)

    return {
        "status": "ok" if len(ic) >= 30 else "thin_sample",
        "cohort_rows": cohort_rows,
        "nonzero_rows": nonzero_rows,
        "nonzero_row_fraction": float(nonzero_rows / max(cohort_rows, 1)),
        "n_ts": int(len(ic)),
        "n_regime_ts_used": int(sum(len(group) for _, group in regime_frame.groupby("regime") if len(group) >= G3_REGIME_MIN_TS)),
        "g1": {
            "ic_mean": g1_mean,
            "ic_std": g1_std,
            "t_stat": g1_t,
            "abs_pass": abs(g1_mean) >= G1_ABS_MIN,
        },
        "g3": {
            "regime_ic": regime_ic,
            "same_sign_fraction": same_sign_fraction,
            "pass": same_sign_fraction >= G3_SAME_SIGN_MIN,
        },
        "g6_vs_lsk3": {
            "residual_ic_mean": residual_lsk3_mean,
            "t_stat": residual_lsk3_t,
            "abs_pass": abs(residual_lsk3_mean) >= G6_ABS_MIN,
        },
        "g6_vs_lsk3_plus_cascade": {
            "residual_ic_mean": residual_lsk3_cascade_mean,
            "t_stat": residual_lsk3_cascade_t,
            "abs_pass": abs(residual_lsk3_cascade_mean) >= G6_ABS_MIN,
        },
        "verdict_vs_lsk3": bool(
            abs(g1_mean) >= G1_ABS_MIN
            and same_sign_fraction >= G3_SAME_SIGN_MIN
            and abs(residual_lsk3_mean) >= G6_ABS_MIN
        ),
        "verdict_vs_lsk3_plus_cascade": bool(
            abs(g1_mean) >= G1_ABS_MIN
            and same_sign_fraction >= G3_SAME_SIGN_MIN
            and abs(residual_lsk3_cascade_mean) >= G6_ABS_MIN
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SP-K post-pump continuous factor report.")
    parser.add_argument("--as-of", required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "artifacts" / "quant_research" / "factor_reports",
    )
    parser.add_argument(
        "--min-listing-age-days",
        type=int,
        default=DEFAULT_MIN_LISTING_AGE_DAYS,
    )
    args = parser.parse_args(argv)

    features_artifact = _discover_latest_daily_features_artifact(
        ROOT / "artifacts" / "quant_research" / "features"
    )
    panel = _prepare_panel(
        features_artifact,
        min_listing_age_days=args.min_listing_age_days,
        horizons=DEFAULT_HORIZONS,
    )
    factors = _build_factor_candidates(panel)
    cohorts = _build_cohort_masks(panel, major_subjects=DEFAULT_MAJOR_SUBJECTS)
    regime_label = build_regime_by_ts(panel)

    baseline_lsk3 = panel[list(LSK3_BASELINE)].apply(pd.to_numeric, errors="coerce")
    baseline_lsk3_plus_cascade = panel[list(LSK3_BASELINE) + ["liq_cascade_recency_score_5d"]].apply(
        pd.to_numeric,
        errors="coerce",
    )
    horizons = {
        "h5d": pd.to_numeric(panel["forward_5d_log_return"], errors="coerce"),
        "h10d": pd.to_numeric(panel["forward_10d_log_return"], errors="coerce"),
    }

    factor_cards: dict[str, dict] = {}
    for factor_name, factor_series in factors.items():
        cohort_cards: dict[str, dict] = {}
        for cohort_name, cohort_mask in cohorts.items():
            horizon_cards: dict[str, dict] = {}
            for horizon_name, target in horizons.items():
                horizon_cards[horizon_name] = _audit_factor(
                    factor_series,
                    target=target,
                    ts=panel["timestamp_ms"],
                    cohort_mask=cohort_mask,
                    regime_label=regime_label,
                    baseline_lsk3=baseline_lsk3,
                    baseline_lsk3_plus_cascade=baseline_lsk3_plus_cascade,
                )
            cohort_cards[cohort_name] = {
                "n_subjects": int(panel.loc[cohort_mask, "subject"].nunique()),
                "horizons": horizon_cards,
            }
        factor_cards[factor_name] = cohort_cards

    out = {
        "contract_version": CARD_CONTRACT_VERSION,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": args.as_of,
        "features_artifact": str(features_artifact),
        "expected_direction": "negative_ic_is_favorable_for_raw_short_score",
        "major_subjects": list(DEFAULT_MAJOR_SUBJECTS),
        "min_listing_age_days": args.min_listing_age_days,
        "thresholds": {
            "g1_abs_min": G1_ABS_MIN,
            "g3_same_sign_min": G3_SAME_SIGN_MIN,
            "g3_regime_min_ts": G3_REGIME_MIN_TS,
            "g6_abs_min": G6_ABS_MIN,
        },
        "lsk3_baseline": list(LSK3_BASELINE),
        "factor_definitions": {
            "pump_core_overextension_score": "same-day pump intensity from sigma-range-volume overextension",
            "pump_crowding_overextension_score": "pump intensity times positive OI and funding crowding",
            "post_pump_stall_strict_score": "yesterday pump intensity times next-day stall, near-high, positive OI, positive funding",
            "post_pump_stall_soft_score": "softer stall version with looser thresholds and crowding offsets",
        },
        "factors": factor_cards,
    }

    out_dir = args.output_dir / args.as_of
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "small_cap_post_pump_factor_report.json"
    out_path.write_text(json.dumps(out, indent=2, sort_keys=True), encoding="utf-8")

    print(f"wrote {out_path}")
    print()
    print("=== primary cohort summary: mid_tail_ex_majors ===")
    for factor_name, cohort_cards in factor_cards.items():
        mid_tail = cohort_cards["mid_tail_ex_majors"]["horizons"]
        h5 = mid_tail["h5d"]
        h10 = mid_tail["h10d"]
        print(
            f"  {factor_name:36s} "
            f"h5 ic={h5.get('g1', {}).get('ic_mean', float('nan')):+.4f} "
            f"g6={h5.get('g6_vs_lsk3', {}).get('residual_ic_mean', float('nan')):+.4f} "
            f"verdict={h5.get('verdict_vs_lsk3')} | "
            f"h10 ic={h10.get('g1', {}).get('ic_mean', float('nan')):+.4f} "
            f"g6={h10.get('g6_vs_lsk3', {}).get('residual_ic_mean', float('nan')):+.4f} "
            f"verdict={h10.get('verdict_vs_lsk3')}"
        )
    print()
    print("=== secondary cohort summary: tail_ex_majors ===")
    for factor_name, cohort_cards in factor_cards.items():
        tail = cohort_cards["tail_ex_majors"]["horizons"]
        h5 = tail["h5d"]
        print(
            f"  {factor_name:36s} "
            f"h5 ic={h5.get('g1', {}).get('ic_mean', float('nan')):+.4f} "
            f"g6={h5.get('g6_vs_lsk3', {}).get('residual_ic_mean', float('nan')):+.4f} "
            f"verdict={h5.get('verdict_vs_lsk3')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
