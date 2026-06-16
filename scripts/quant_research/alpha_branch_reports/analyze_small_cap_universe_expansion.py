"""SP-K sidecar: universe expansion feasibility review for small-cap pump-short.

Answers two questions:
1. How much true headroom remains beyond the current production-like perp
   universe?
2. If we relax the current filters, does the post_pump_stall event result
   materially change?

Output:
    artifacts/quant_research/factor_reports/<as-of>/small_cap_universe_expansion_review.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]

CARD_CONTRACT_VERSION = "quant_sp_k_universe_expansion_review.v1"
DEFAULT_MAJOR_SUBJECTS = ("BTC", "ETH")


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


def _prepare_frame(features_artifact: Path) -> pd.DataFrame:
    frame = pd.read_csv(features_artifact, compression="gzip")
    for column in (
        "spot_close",
        "return_1",
        "realized_volatility_20",
        "abnormal_range_z_60",
        "quote_volume_expansion",
        "oi_change_5",
        "funding_zscore_20",
        "distance_to_high_5",
    ):
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.sort_values(["subject", "timestamp_ms"]).reset_index(drop=True)
    for horizon in (3, 5, 10):
        frame[f"forward_{horizon}d_log_return"] = frame.groupby("subject", sort=False)["spot_close"].transform(
            lambda close: np.log(close.shift(-horizon) / close)
        )
    return frame


def _post_pump_stall_stats(frame: pd.DataFrame) -> dict:
    frame = frame.copy()
    frame["pump_sigma"] = frame["return_1"] / frame["realized_volatility_20"].replace(0.0, np.nan)
    pump_core = (
        frame["pump_sigma"].gt(2.0)
        & frame["abnormal_range_z_60"].gt(1.0)
        & frame["quote_volume_expansion"].gt(1.5)
    )
    post_pump_stall = (
        pump_core.groupby(frame["subject"], sort=False).shift(1, fill_value=False).astype(bool)
        & frame["return_1"].le(0.015)
        & frame["distance_to_high_5"].ge(-0.05)
        & frame["funding_zscore_20"].gt(0.0)
        & frame["oi_change_5"].gt(0.0)
    )
    cohort = frame["liquidity_bucket"].isin(("mid_liquidity", "tail_liquidity")) & ~frame["subject"].isin(
        DEFAULT_MAJOR_SUBJECTS
    )
    out = {
        "n_subjects_in_mid_tail_ex_majors": int(frame.loc[cohort, "subject"].nunique()),
        "n_rows_in_mid_tail_ex_majors": int(cohort.sum()),
        "n_post_pump_stall_events": int((cohort & post_pump_stall).sum()),
        "horizons": {},
    }
    for horizon in (3, 5, 10):
        returns = pd.to_numeric(
            frame.loc[cohort & post_pump_stall, f"forward_{horizon}d_log_return"], errors="coerce"
        ).dropna()
        out["horizons"][f"h{horizon}d"] = {
            "n_events": int(len(returns)),
            "mean_log_return": float(returns.mean()) if len(returns) else 0.0,
            "median_log_return": float(returns.median()) if len(returns) else 0.0,
            "negative_rate": float((returns < 0).mean()) if len(returns) else 0.0,
        }
    return out


def _latest_snapshot_counts(frame: pd.DataFrame) -> dict:
    latest_date = str(frame["date_utc"].max())
    snapshot = frame[frame["date_utc"] == latest_date].copy()

    def _subject_count(mask: pd.Series) -> int:
        return int(snapshot.loc[mask, "subject"].nunique())

    perp = snapshot["perp_execution_eligible"].fillna(False).astype(bool)
    age = snapshot["listing_age_days_as_of"].fillna(0.0)
    spot_ok = snapshot["spot_close"].fillna(0.0).gt(0.0)
    prod = perp & age.ge(60) & spot_ok

    return {
        "latest_date_utc": latest_date,
        "all_candidates_subjects": int(snapshot["subject"].nunique()),
        "perp_eligible_subjects": _subject_count(perp),
        "perp_eligible_age_ge_60_subjects": _subject_count(perp & age.ge(60)),
        "perp_eligible_age_ge_30_subjects": _subject_count(perp & age.ge(30)),
        "non_perp_subjects": sorted(set(snapshot["subject"]) - set(snapshot.loc[perp, "subject"])),
        "perp_but_age_lt_60_subjects": sorted(snapshot.loc[perp & age.lt(60), "subject"].tolist()),
        "production_like_bucket_counts": {
            str(bucket): int(count)
            for bucket, count in snapshot.loc[prod].groupby("liquidity_bucket")["subject"].nunique().items()
        },
    }


def _local_data_counts() -> dict:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return {"available": False}
    market_root = Path(local_app_data) / "EnhengClaw" / "market_history"
    spot_root = market_root / "coinapi_ohlcv" / "spot"
    deriv_root = market_root / "binance_derivatives"
    return {
        "available": True,
        "spot_symbol_dirs": int(sum(1 for path in spot_root.iterdir() if path.is_dir())) if spot_root.exists() else 0,
        "binance_derivatives_symbol_dirs": int(sum(1 for path in deriv_root.iterdir() if path.is_dir()))
        if deriv_root.exists()
        else 0,
    }


def _load_universe_input_summary(as_of: str) -> dict | None:
    path = ROOT / "artifacts" / "quant_research" / "cycles" / as_of / "quant_universe_input_producer_summary.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        "path": str(path),
        "candidate_count": payload.get("candidate_count"),
        "candidates_with_perp_count": payload.get("candidates_with_perp_count"),
        "excluded_count": payload.get("excluded_count"),
        "top100_complete": payload.get("top100_complete"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SP-K universe expansion feasibility review.")
    parser.add_argument("--as-of", required=True)
    parser.add_argument(
        "--features",
        type=Path,
        default=None,
        help="Optional explicit daily features artifact path. Defaults to latest '*-cross-sectional-daily-1d-features-v1'.",
    )
    parser.add_argument(
        "--features-root",
        type=Path,
        default=ROOT / "artifacts" / "quant_research" / "features",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "artifacts" / "quant_research" / "factor_reports",
    )
    args = parser.parse_args(argv)

    features_artifact = (
        args.features.expanduser().resolve()
        if args.features is not None
        else _discover_latest_daily_features_artifact(args.features_root.expanduser().resolve())
    )
    frame = _prepare_frame(features_artifact)
    latest_counts = _latest_snapshot_counts(frame)

    production_like = (
        frame["perp_execution_eligible"].fillna(False).astype(bool)
        & frame["listing_age_days_as_of"].fillna(0.0).ge(60.0)
        & frame["spot_close"].fillna(0.0).gt(0.0)
    )
    relaxed_perp = (
        frame["perp_execution_eligible"].fillna(False).astype(bool)
        & frame["spot_close"].fillna(0.0).gt(0.0)
    )
    all_candidates = frame["spot_close"].fillna(0.0).gt(0.0)

    event_comparison = {
        "production_like_perp_age_ge_60": _post_pump_stall_stats(frame.loc[production_like].copy()),
        "relaxed_perp_no_age_filter": _post_pump_stall_stats(frame.loc[relaxed_perp].copy()),
        "all_candidates_spot_positive": _post_pump_stall_stats(frame.loc[all_candidates].copy()),
    }

    payload = {
        "contract_version": CARD_CONTRACT_VERSION,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": args.as_of,
        "features_artifact": str(features_artifact),
        "latest_snapshot_counts": latest_counts,
        "local_data_counts": _local_data_counts(),
        "quant_universe_input_producer_summary": _load_universe_input_summary(args.as_of),
        "post_pump_stall_event_comparison": event_comparison,
    }

    out_dir = args.output_dir / args.as_of
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "small_cap_universe_expansion_review.json"
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    print(f"=== Wrote universe expansion review to {out_path}")
    print(
        "=== Headroom snapshot: "
        f"all_candidates={latest_counts['all_candidates_subjects']} "
        f"perp_eligible={latest_counts['perp_eligible_subjects']} "
        f"prod_like={latest_counts['perp_eligible_age_ge_60_subjects']}"
    )
    for label, block in event_comparison.items():
        h5 = block["horizons"]["h5d"]
        print(
            f"  {label:30s} subjects={block['n_subjects_in_mid_tail_ex_majors']:3d} "
            f"events={block['n_post_pump_stall_events']:3d} h5_mean={h5['mean_log_return']:+.4f} "
            f"h5_neg={h5['negative_rate']:.3f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
