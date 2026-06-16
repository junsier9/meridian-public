"""Audit small-cap universe headroom and compare event outcomes by cohort.

This is the companion to SP-K Stage 0/1. It answers two questions:

1. How much genuine local headroom exists beyond the current 99-name panel?
2. Does broadening the small-cap screen materially improve or dilute the
   post-pump short mechanism?

The output is a compact JSON audit plus console summary.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]

CARD_CONTRACT_VERSION = "quant_sp_k_small_cap_universe_audit.v1"
DEFAULT_MAJOR_SUBJECTS = ("BTC", "ETH")
DEFAULT_MIN_LISTING_AGE_DAYS = 60
DEFAULT_HORIZONS = (3, 5, 10)


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


def _prepare_panel(features_artifact: Path) -> pd.DataFrame:
    frame = pd.read_csv(features_artifact, compression="gzip")
    _require_columns(
        frame,
        (
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
            "usdm_symbol",
        ),
    )
    numeric_columns = (
        "spot_close",
        "return_1",
        "realized_volatility_20",
        "abnormal_range_z_60",
        "quote_volume_expansion",
        "oi_change_5",
        "funding_zscore_20",
        "distance_to_high_5",
        "listing_age_days_as_of",
    )
    for column in numeric_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.sort_values(["subject", "timestamp_ms"]).reset_index(drop=True)
    frame = frame[frame["spot_close"].fillna(0).gt(0)].copy()
    frame["pump_return_sigma"] = frame["return_1"] / frame["realized_volatility_20"].replace(0.0, np.nan)
    for horizon in DEFAULT_HORIZONS:
        frame[f"forward_{horizon}d_log_return"] = frame.groupby("subject")["spot_close"].transform(
            lambda close: np.log(close.shift(-horizon) / close)
        )
    return frame


def _build_event_masks(frame: pd.DataFrame) -> dict[str, pd.Series]:
    pump_core = (
        (frame["pump_return_sigma"] > 2.0)
        & (frame["abnormal_range_z_60"] > 1.0)
        & (frame["quote_volume_expansion"] > 1.5)
    )
    pump_core_yesterday = pump_core.groupby(frame["subject"]).shift(1, fill_value=False).astype(bool)
    post_pump_stall = (
        pump_core_yesterday
        & (frame["return_1"] <= 0.015)
        & (frame["distance_to_high_5"] >= -0.05)
        & (frame["funding_zscore_20"] > 0.0)
        & (frame["oi_change_5"] > 0.0)
    )
    return {
        "pump_core": pump_core.fillna(False),
        "post_pump_stall": post_pump_stall.fillna(False),
    }


def _collect_local_symbol_inventory(feature_subjects: set[str]) -> dict:
    local_appdata = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share")))
    spot_root = local_appdata / "EnhengClaw" / "market_history" / "coinapi_ohlcv" / "spot"
    deriv_root = local_appdata / "EnhengClaw" / "market_history" / "binance_derivatives"

    spot_symbols: set[str] = set()
    if spot_root.exists():
        for path in spot_root.iterdir():
            if not path.is_dir():
                continue
            symbol = path.name[:-4] if path.name.endswith("USDT") else path.name
            spot_symbols.add(symbol)

    deriv_symbols: set[str] = set()
    if deriv_root.exists():
        for path in deriv_root.iterdir():
            if not path.is_dir() or not path.name.endswith("USDT"):
                continue
            symbol = path.name[:-4]
            deriv_symbols.add(symbol)

    return {
        "spot_root": str(spot_root),
        "derivatives_root": str(deriv_root),
        "spot_symbol_count": len(spot_symbols),
        "derivatives_symbol_count": len(deriv_symbols),
        "extra_spot_symbols_not_in_features": sorted(spot_symbols - feature_subjects),
        "extra_derivative_symbols_not_in_features": sorted(deriv_symbols - feature_subjects),
        "feature_subjects_missing_spot": sorted(feature_subjects - spot_symbols),
        "feature_subjects_missing_derivatives": sorted(feature_subjects - deriv_symbols),
    }


def _event_stats(frame: pd.DataFrame, *, event_mask: pd.Series, cohort_mask: pd.Series) -> dict:
    out: dict[str, dict] = {}
    for horizon in DEFAULT_HORIZONS:
        col = f"forward_{horizon}d_log_return"
        eligible = cohort_mask & frame[col].notna()
        events = eligible & event_mask
        values = pd.to_numeric(frame.loc[events, col], errors="coerce").dropna()
        if values.empty:
            out[f"h{horizon}d"] = {"status": "no_events", "n_events": 0}
            continue
        out[f"h{horizon}d"] = {
            "status": "ok",
            "n_events": int(values.shape[0]),
            "mean": float(values.mean()),
            "median": float(values.median()),
            "negative_rate": float((values < 0).mean()),
            "std": float(values.std()) if len(values) > 1 else 0.0,
        }
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit small-cap universe headroom.")
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
    frame = _prepare_panel(features_artifact)
    event_masks = _build_event_masks(frame)

    latest_date = str(frame["date_utc"].max())
    latest = frame[frame["date_utc"] == latest_date].copy()
    latest["perp_execution_eligible"] = latest["perp_execution_eligible"].fillna(False).astype(bool)
    latest["age60"] = latest["listing_age_days_as_of"].fillna(0).ge(args.min_listing_age_days)
    ex_majors = ~frame["subject"].isin(DEFAULT_MAJOR_SUBJECTS)
    mid = frame["liquidity_bucket"].eq("mid_liquidity")
    tail = frame["liquidity_bucket"].eq("tail_liquidity")
    latest_ex_majors = ~latest["subject"].isin(DEFAULT_MAJOR_SUBJECTS)

    cohort_masks = {
        "investable_mid_tail_ex_majors": (
            (mid | tail)
            & ex_majors
            & frame["perp_execution_eligible"].fillna(False).astype(bool)
            & frame["listing_age_days_as_of"].fillna(0).ge(args.min_listing_age_days)
        ),
        "broad_age60_mid_tail_ex_majors": (
            (mid | tail) & ex_majors & frame["listing_age_days_as_of"].fillna(0).ge(args.min_listing_age_days)
        ),
        "investable_tail_ex_majors": (
            tail
            & ex_majors
            & frame["perp_execution_eligible"].fillna(False).astype(bool)
            & frame["listing_age_days_as_of"].fillna(0).ge(args.min_listing_age_days)
        ),
        "broad_age60_tail_ex_majors": (
            tail & ex_majors & frame["listing_age_days_as_of"].fillna(0).ge(args.min_listing_age_days)
        ),
    }

    latest_mid_tail = latest["liquidity_bucket"].isin(["mid_liquidity", "tail_liquidity"]) & latest_ex_majors
    latest_tail = latest["liquidity_bucket"].eq("tail_liquidity") & latest_ex_majors

    feature_subjects = set(frame["subject"].dropna().unique().tolist())
    local_inventory = _collect_local_symbol_inventory(feature_subjects)

    universe_input_summary_path = (
        ROOT / "artifacts" / "quant_research" / "cycles" / args.as_of / "quant_universe_input_producer_summary.json"
    )
    universe_input_summary = None
    if universe_input_summary_path.exists():
        universe_input_summary = json.loads(universe_input_summary_path.read_text(encoding="utf-8"))

    event_comparison: dict[str, dict] = {}
    for event_name, event_mask in event_masks.items():
        event_comparison[event_name] = {}
        for cohort_name, cohort_mask in cohort_masks.items():
            event_comparison[event_name][cohort_name] = {
                "n_subjects": int(frame.loc[cohort_mask, "subject"].nunique()),
                "horizons": _event_stats(frame, event_mask=event_mask, cohort_mask=cohort_mask),
            }

    broad_mid_tail_subjects = set(
        latest.loc[latest_mid_tail & latest["age60"], "subject"].dropna().tolist()
    )
    investable_mid_tail_subjects = set(
        latest.loc[latest_mid_tail & latest["age60"] & latest["perp_execution_eligible"], "subject"].dropna().tolist()
    )

    out = {
        "contract_version": CARD_CONTRACT_VERSION,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": args.as_of,
        "features_artifact": str(features_artifact),
        "latest_panel_date_utc": latest_date,
        "screen_definition": {
            "investable": f"spot_close>0 and perp_execution_eligible and listing_age_days_as_of>={args.min_listing_age_days}",
            "broad_age60": f"spot_close>0 and listing_age_days_as_of>={args.min_listing_age_days}",
        },
        "latest_counts": {
            "feature_subject_count": int(latest["subject"].nunique()),
            "eligible_subject_count": int(latest["perp_execution_eligible"].sum()),
            "age60_subject_count": int(latest["age60"].sum()),
            "eligible_and_age60_subject_count": int((latest["perp_execution_eligible"] & latest["age60"]).sum()),
            "mid_tail_ex_majors_investable_count": int((latest_mid_tail & latest["age60"] & latest["perp_execution_eligible"]).sum()),
            "mid_tail_ex_majors_broad_age60_count": int((latest_mid_tail & latest["age60"]).sum()),
            "tail_ex_majors_investable_count": int((latest_tail & latest["age60"] & latest["perp_execution_eligible"]).sum()),
            "tail_ex_majors_broad_age60_count": int((latest_tail & latest["age60"]).sum()),
        },
        "broadening_delta": {
            "mid_tail_added_subjects_age60": sorted(broad_mid_tail_subjects - investable_mid_tail_subjects),
            "mid_tail_added_subject_count_age60": int(len(broad_mid_tail_subjects - investable_mid_tail_subjects)),
            "noneligible_latest_subjects": sorted(
                latest.loc[~latest["perp_execution_eligible"], "subject"].dropna().tolist()
            ),
            "under_age_threshold_latest_subjects": sorted(
                latest.loc[~latest["age60"], "subject"].dropna().tolist()
            ),
        },
        "local_symbol_inventory": local_inventory,
        "universe_input_summary": universe_input_summary,
        "event_comparison": event_comparison,
    }

    out_dir = args.output_dir / args.as_of
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "small_cap_universe_expansion_audit.json"
    out_path.write_text(json.dumps(out, indent=2, sort_keys=True), encoding="utf-8")

    print(f"wrote {out_path}")
    print()
    print("=== latest headroom ===")
    print(
        "  feature subjects="
        f"{out['latest_counts']['feature_subject_count']}  "
        f"eligible={out['latest_counts']['eligible_subject_count']}  "
        f"mid_tail investable={out['latest_counts']['mid_tail_ex_majors_investable_count']}  "
        f"mid_tail broad_age60={out['latest_counts']['mid_tail_ex_majors_broad_age60_count']}"
    )
    print(
        f"  added mid_tail names when broadening age60 screen: "
        f"{', '.join(out['broadening_delta']['mid_tail_added_subjects_age60']) or 'none'}"
    )
    print(
        f"  extra derivative symbols outside feature panel: "
        f"{', '.join(local_inventory['extra_derivative_symbols_not_in_features']) or 'none'}"
    )
    print()
    print("=== post_pump_stall comparison ===")
    for cohort_name in (
        "investable_mid_tail_ex_majors",
        "broad_age60_mid_tail_ex_majors",
        "investable_tail_ex_majors",
        "broad_age60_tail_ex_majors",
    ):
        card = event_comparison["post_pump_stall"][cohort_name]
        h5 = card["horizons"]["h5d"]
        h10 = card["horizons"]["h10d"]
        print(
            f"  {cohort_name:30s} "
            f"h5 mean={h5.get('mean', float('nan')):+.4f} neg={h5.get('negative_rate', float('nan')):.3f} n={h5.get('n_events', 0)} | "
            f"h10 mean={h10.get('mean', float('nan')):+.4f} neg={h10.get('negative_rate', float('nan')):.3f} n={h10.get('n_events', 0)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
