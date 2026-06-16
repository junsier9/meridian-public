"""SP-K Stage 0: small-cap post-pump short event study.

Goal:
    Validate whether anomalous upside pump events in altcoin perps are followed
    by negative forward returns over 3 / 5 / 10 days, especially in mid / tail
    liquidity cohorts.

This is the Stage 0 mechanism test described in
docs/quant_research/03_alpha_branches/small_cap_post_pump_short_proposal.md:

1. detect pump events
2. test stricter event variants (OI crowding / funding crowding / post-pump stall)
3. evaluate raw and subject-abnormal forward returns by liquidity cohort

Current scope:
    - daily cross-sectional features artifact only
    - event definitions K1 / K2-style plus a K6-style post-pump stall
    - outputs JSON summary + long event-row CSV for follow-on factorization
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


CARD_CONTRACT_VERSION = "quant_sp_k_post_pump_event_study.v1"
DEFAULT_HORIZONS = (3, 5, 10)
DEFAULT_MAJOR_SUBJECTS = ("BTC", "ETH")
DEFAULT_MIN_LISTING_AGE_DAYS = 60

# Baseline pump event thresholds.
PUMP_SIGMA_THRESHOLD = 2.0
PUMP_RANGE_Z_THRESHOLD = 1.0
PUMP_QV_EXPANSION_THRESHOLD = 1.5

# Crowding refinement thresholds.
OI_CHANGE_MIN = 0.05
FUNDING_Z_MIN = 0.5

# Post-pump stall refinement thresholds.
STALL_RETURN_MAX = 0.015
STALL_DISTANCE_TO_HIGH_5_MIN = -0.05
STALL_FUNDING_Z_MIN = 0.0
STALL_OI_CHANGE_MIN = 0.0


def _discover_latest_daily_features_artifact(features_root: Path) -> Path:
    """Resolve the latest *daily* v1 cross-sectional features artifact."""
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


def _t_stat(values: pd.Series) -> float:
    series = pd.to_numeric(values, errors="coerce").dropna()
    if len(series) < 2:
        return 0.0
    std = float(series.std())
    if std <= 0:
        return 0.0
    return float(series.mean() * np.sqrt(len(series)) / std)


def _require_columns(frame: pd.DataFrame, required: Iterable[str]) -> None:
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise RuntimeError(f"required columns missing from features artifact: {missing}")


def _prepare_panel(
    features_artifact: Path,
    *,
    min_listing_age_days: int,
    horizons: Iterable[int],
) -> pd.DataFrame:
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
        "range_position_20",
    )
    for column in numeric_columns:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")

    eligible = frame["perp_execution_eligible"].fillna(False).astype(bool)
    if min_listing_age_days > 0:
        eligible &= frame["listing_age_days_as_of"].fillna(0).ge(min_listing_age_days)
    eligible &= frame["spot_close"].fillna(0).gt(0)
    frame = frame.loc[eligible].copy()
    frame = frame.sort_values(["subject", "timestamp_ms"]).reset_index(drop=True)

    frame["pump_return_sigma"] = frame["return_1"] / frame["realized_volatility_20"].replace(0.0, np.nan)
    frame["market_wide_non_confirmation"] = frame.groupby("timestamp_ms")["return_1"].transform("mean")

    for horizon in horizons:
        frame[f"forward_{horizon}d_log_return"] = frame.groupby("subject")["spot_close"].transform(
            lambda close: np.log(close.shift(-horizon) / close)
        )
    return frame


def _build_event_masks(frame: pd.DataFrame) -> dict[str, pd.Series]:
    pump_core = (
        (frame["pump_return_sigma"] > PUMP_SIGMA_THRESHOLD)
        & (frame["abnormal_range_z_60"] > PUMP_RANGE_Z_THRESHOLD)
        & (frame["quote_volume_expansion"] > PUMP_QV_EXPANSION_THRESHOLD)
    )
    pump_oi_crowded = pump_core & (frame["oi_change_5"] > OI_CHANGE_MIN)
    pump_funding_oi_crowded = pump_oi_crowded & (frame["funding_zscore_20"] > FUNDING_Z_MIN)

    pump_core_yesterday = pump_core.groupby(frame["subject"]).shift(1, fill_value=False).astype(bool)
    post_pump_stall = (
        pump_core_yesterday
        & (frame["return_1"] <= STALL_RETURN_MAX)
        & (frame["distance_to_high_5"] >= STALL_DISTANCE_TO_HIGH_5_MIN)
        & (frame["funding_zscore_20"] > STALL_FUNDING_Z_MIN)
        & (frame["oi_change_5"] > STALL_OI_CHANGE_MIN)
    )

    return {
        "pump_core": pump_core.fillna(False),
        "pump_oi_crowded": pump_oi_crowded.fillna(False),
        "pump_funding_oi_crowded": pump_funding_oi_crowded.fillna(False),
        "post_pump_stall": post_pump_stall.fillna(False),
    }


def _build_cohort_masks(frame: pd.DataFrame, *, major_subjects: tuple[str, ...]) -> dict[str, pd.Series]:
    ex_majors = ~frame["subject"].isin(major_subjects)
    mid = frame["liquidity_bucket"].eq("mid_liquidity")
    tail = frame["liquidity_bucket"].eq("tail_liquidity")
    top = frame["liquidity_bucket"].eq("top_liquidity")
    return {
        "all_eligible": pd.Series(True, index=frame.index),
        "ex_majors": ex_majors,
        "mid_liquidity": mid,
        "tail_liquidity": tail,
        "mid_tail_liquidity": mid | tail,
        "mid_tail_ex_majors": (mid | tail) & ex_majors,
        "top_liquidity_ex_majors": top & ex_majors,
    }


def _event_stats_for_horizon(
    frame: pd.DataFrame,
    *,
    event_mask: pd.Series,
    cohort_mask: pd.Series,
    horizon: int,
) -> dict:
    forward_column = f"forward_{horizon}d_log_return"
    eligible = cohort_mask & frame[forward_column].notna()
    events = eligible & event_mask
    if int(events.sum()) == 0:
        return {"status": "no_events", "n_events": 0}

    event_rows = frame.loc[events, ["subject", "timestamp_ms", forward_column]].copy()
    raw_returns = pd.to_numeric(event_rows[forward_column], errors="coerce").dropna()
    if raw_returns.empty:
        return {"status": "no_forward_returns", "n_events": int(events.sum())}

    non_events = eligible & ~event_mask
    subject_baseline = (
        frame.loc[non_events, ["subject", forward_column]]
        .dropna(subset=[forward_column])
        .groupby("subject")[forward_column]
        .mean()
    )
    event_rows["subject_baseline"] = event_rows["subject"].map(subject_baseline)
    event_rows["subject_abnormal"] = event_rows[forward_column] - event_rows["subject_baseline"]
    abnormal = pd.to_numeric(event_rows["subject_abnormal"], errors="coerce").dropna()

    date_means = (
        frame.loc[eligible, ["timestamp_ms", forward_column]]
        .dropna(subset=[forward_column])
        .groupby("timestamp_ms")[forward_column]
        .mean()
    )
    event_rows["same_day_cohort_mean"] = event_rows["timestamp_ms"].map(date_means)
    event_rows["same_day_excess"] = event_rows[forward_column] - event_rows["same_day_cohort_mean"]
    same_day_excess = pd.to_numeric(event_rows["same_day_excess"], errors="coerce").dropna()

    subject_event_counts = (
        frame.loc[events, "subject"].value_counts().head(10).to_dict()
    )

    return {
        "status": "ok",
        "n_events": int(raw_returns.shape[0]),
        "n_subjects": int(frame.loc[events, "subject"].nunique()),
        "event_rate_within_cohort": float(raw_returns.shape[0] / max(int(eligible.sum()), 1)),
        "raw_forward_return": {
            "mean": float(raw_returns.mean()),
            "median": float(raw_returns.median()),
            "std": float(raw_returns.std()) if len(raw_returns) > 1 else 0.0,
            "t_stat": _t_stat(raw_returns),
            "negative_rate": float((raw_returns < 0).mean()),
            "p10": float(raw_returns.quantile(0.10)),
            "p90": float(raw_returns.quantile(0.90)),
        },
        "subject_abnormal_return": {
            "n_events_with_baseline": int(abnormal.shape[0]),
            "mean": float(abnormal.mean()) if len(abnormal) else 0.0,
            "median": float(abnormal.median()) if len(abnormal) else 0.0,
            "t_stat": _t_stat(abnormal),
            "negative_rate": float((abnormal < 0).mean()) if len(abnormal) else 0.0,
        },
        "same_day_cohort_excess_return": {
            "n_events_with_baseline": int(same_day_excess.shape[0]),
            "mean": float(same_day_excess.mean()) if len(same_day_excess) else 0.0,
            "median": float(same_day_excess.median()) if len(same_day_excess) else 0.0,
            "t_stat": _t_stat(same_day_excess),
            "negative_rate": float((same_day_excess < 0).mean()) if len(same_day_excess) else 0.0,
        },
        "top_subject_event_counts": {str(k): int(v) for k, v in subject_event_counts.items()},
    }


def _build_summary(
    frame: pd.DataFrame,
    *,
    event_masks: dict[str, pd.Series],
    cohort_masks: dict[str, pd.Series],
    horizons: Iterable[int],
) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for rule_name, event_mask in event_masks.items():
        out[rule_name] = {
            "total_event_rows": int(event_mask.sum()),
            "cohorts": {},
        }
        for cohort_name, cohort_mask in cohort_masks.items():
            cohort_summary: dict[str, dict] = {}
            for horizon in horizons:
                cohort_summary[f"h{horizon}d"] = _event_stats_for_horizon(
                    frame,
                    event_mask=event_mask,
                    cohort_mask=cohort_mask,
                    horizon=horizon,
                )
            out[rule_name]["cohorts"][cohort_name] = cohort_summary
    return out


def _build_event_rows_export(
    frame: pd.DataFrame,
    *,
    event_masks: dict[str, pd.Series],
) -> pd.DataFrame:
    export_columns = [
        "date_utc",
        "timestamp_ms",
        "subject",
        "liquidity_bucket",
        "return_1",
        "pump_return_sigma",
        "abnormal_range_z_60",
        "quote_volume_expansion",
        "oi_change_5",
        "funding_zscore_20",
        "distance_to_high_5",
        "market_wide_non_confirmation",
        "forward_3d_log_return",
        "forward_5d_log_return",
        "forward_10d_log_return",
    ]
    rows: list[pd.DataFrame] = []
    for rule_name, mask in event_masks.items():
        event_rows = frame.loc[mask, export_columns].copy()
        if event_rows.empty:
            continue
        event_rows.insert(0, "event_rule", rule_name)
        rows.append(event_rows)
    if not rows:
        return pd.DataFrame(columns=["event_rule", *export_columns])
    return pd.concat(rows, ignore_index=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SP-K Stage 0 small-cap post-pump event study.")
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
        help="Root searched when --features is omitted.",
    )
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

    features_artifact = (
        args.features.expanduser().resolve()
        if args.features is not None
        else _discover_latest_daily_features_artifact(args.features_root.expanduser().resolve())
    )
    horizons = list(DEFAULT_HORIZONS)

    print(f"=== SP-K Stage 0: loading daily features from {features_artifact}")
    panel = _prepare_panel(
        features_artifact,
        min_listing_age_days=args.min_listing_age_days,
        horizons=horizons,
    )
    print(f"  panel rows after eligibility filter: {len(panel)}")
    print(f"  subjects: {panel['subject'].nunique()}")
    print(f"  date range: {panel['date_utc'].min()} -> {panel['date_utc'].max()}")
    print()

    event_masks = _build_event_masks(panel)
    cohort_masks = _build_cohort_masks(panel, major_subjects=DEFAULT_MAJOR_SUBJECTS)
    summary = _build_summary(
        panel,
        event_masks=event_masks,
        cohort_masks=cohort_masks,
        horizons=horizons,
    )

    print("=== Event counts by rule ===")
    for rule_name, mask in event_masks.items():
        print(f"  {rule_name:24s} {int(mask.sum()):5d}")
    print()

    print("=== Key Stage 0 readout (mid/tail ex majors) ===")
    for rule_name in summary:
        cohort = summary[rule_name]["cohorts"]["mid_tail_ex_majors"]
        line = [f"{rule_name:24s}"]
        for horizon in horizons:
            block = cohort[f"h{horizon}d"]
            if block.get("status") != "ok":
                line.append(f"h{horizon}=NA")
                continue
            raw = block["raw_forward_return"]
            line.append(
                f"h{horizon}: n={block['n_events']} mean={raw['mean']:+.4f} neg={raw['negative_rate']:.3f}"
            )
        print("  " + "  ".join(line))

    out_dir = args.output_dir / args.as_of
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "small_cap_post_pump_event_study.json"
    events_path = out_dir / "small_cap_post_pump_event_rows.csv"

    out = {
        "contract_version": CARD_CONTRACT_VERSION,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": args.as_of,
        "features_artifact": str(features_artifact),
        "major_subjects": list(DEFAULT_MAJOR_SUBJECTS),
        "thresholds": {
            "min_listing_age_days": args.min_listing_age_days,
            "pump_sigma_threshold": PUMP_SIGMA_THRESHOLD,
            "pump_range_z_threshold": PUMP_RANGE_Z_THRESHOLD,
            "pump_quote_volume_expansion_threshold": PUMP_QV_EXPANSION_THRESHOLD,
            "oi_change_min": OI_CHANGE_MIN,
            "funding_z_min": FUNDING_Z_MIN,
            "stall_return_max": STALL_RETURN_MAX,
            "stall_distance_to_high_5_min": STALL_DISTANCE_TO_HIGH_5_MIN,
            "stall_funding_z_min": STALL_FUNDING_Z_MIN,
            "stall_oi_change_min": STALL_OI_CHANGE_MIN,
        },
        "event_rule_definitions": {
            "pump_core": (
                "return_1 > 2.0 * realized_volatility_20 AND abnormal_range_z_60 > 1.0 "
                "AND quote_volume_expansion > 1.5"
            ),
            "pump_oi_crowded": "pump_core AND oi_change_5 > 0.05",
            "pump_funding_oi_crowded": "pump_oi_crowded AND funding_zscore_20 > 0.5",
            "post_pump_stall": (
                "yesterday pump_core AND today return_1 <= 0.015 AND distance_to_high_5 >= -0.05 "
                "AND funding_zscore_20 > 0 AND oi_change_5 > 0"
            ),
        },
        "cohorts": list(cohort_masks.keys()),
        "horizons_days": horizons,
        "summary": summary,
    }
    summary_path.write_text(json.dumps(out, indent=2, sort_keys=True), encoding="utf-8")

    event_rows = _build_event_rows_export(panel, event_masks=event_masks)
    event_rows.to_csv(events_path, index=False)

    print()
    print(f"=== Wrote summary to {summary_path}")
    print(f"=== Wrote event rows to {events_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
