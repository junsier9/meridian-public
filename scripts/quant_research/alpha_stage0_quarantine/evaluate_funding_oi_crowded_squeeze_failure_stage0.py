from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.quant_research import evaluate_v6_h10d_post_pump_short_replacement as spk_eval  # noqa: E402


CONTRACT_VERSION = "quant_funding_oi_crowded_squeeze_failure_stage0.v1"
DEFAULT_AS_OF = "2026-05-02"
DEFAULT_HORIZONS = (3, 5, 10)
CROWDING_COLUMNS = [
    "funding_zscore_20",
    "oi_change_5",
    "basis_zscore_20",
    "pump_funding_oi_crowding_score_3d",
    "coinglass_liq_intraday_concentration_24h",
]
PUMP_COLUMNS = [
    "distance_to_high_5",
    "momentum_5",
    "pump_funding_oi_crowding_score_3d",
]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Stage-0 cohort test for Funding + OI crowded squeeze failure. "
            "This is not a promotion runner; it checks whether crowded pump names "
            "have better short-side forward returns than nearby pump cohorts."
        )
    )
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument("--shuffle-iterations", type=int, default=200)
    parser.add_argument("--crowding-quantile", type=float, default=0.75)
    parser.add_argument("--pump-quantile", type=float, default=0.70)
    return parser


def _timestamp_zscore(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
    values = pd.to_numeric(frame[column], errors="coerce")
    grouped = values.groupby(frame["timestamp_ms"])
    mean = grouped.transform("mean")
    std = grouped.transform("std").replace(0, np.nan)
    return ((values - mean) / std).replace([np.inf, -np.inf], np.nan).fillna(0.0)


def _timestamp_percentile(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
    values = pd.to_numeric(frame[column], errors="coerce")
    return (
        values.groupby(frame["timestamp_ms"])
        .rank(method="average", pct=True)
        .replace([np.inf, -np.inf], np.nan)
        .fillna(0.0)
    )


def _feature_presence(frame: pd.DataFrame, columns: list[str]) -> dict[str, Any]:
    return {
        col: {
            "present": col in frame.columns,
            "non_null_fraction": float(pd.to_numeric(frame[col], errors="coerce").notna().mean())
            if col in frame.columns and len(frame)
            else 0.0,
        }
        for col in columns
    }


def _add_forward_returns(frame: pd.DataFrame, horizons: tuple[int, ...]) -> pd.DataFrame:
    out = frame.sort_values(["subject", "timestamp_ms"]).copy()
    close = pd.to_numeric(out["spot_close"], errors="coerce")
    for horizon in horizons:
        out[f"forward_{horizon}d_log_return"] = close.groupby(out["subject"], sort=False).transform(
            lambda series: np.log(series.shift(-horizon) / series)
        )
    return out


def _prepare_frame(as_of: str) -> pd.DataFrame:
    frame = spk_eval._build_risk_frame(  # noqa: SLF001 - reuse repo-native diagnostic helper.
        spk_eval._features_artifact_path(as_of),  # noqa: SLF001
        target_horizon_bars=10,
    )
    frame = _add_forward_returns(frame, DEFAULT_HORIZONS)
    crowding_score = pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
    for column in CROWDING_COLUMNS:
        crowding_score = crowding_score + _timestamp_zscore(frame, column)
    frame["funding_oi_crowded_squeeze_score_v1"] = crowding_score / float(len(CROWDING_COLUMNS))

    pump_score = pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
    for column in PUMP_COLUMNS:
        pump_score = pump_score + _timestamp_zscore(frame, column)
    frame["pump_context_score_v1"] = pump_score / float(len(PUMP_COLUMNS))

    frame["pump_context_pct"] = (
        frame["pump_context_score_v1"]
        .groupby(frame["timestamp_ms"])
        .rank(method="average", pct=True)
        .fillna(0.0)
    )
    frame["crowding_pct"] = (
        frame["funding_oi_crowded_squeeze_score_v1"]
        .groupby(frame["timestamp_ms"])
        .rank(method="average", pct=True)
        .fillna(0.0)
    )
    return frame


def _cohort_metrics(
    frame: pd.DataFrame,
    *,
    pump_quantile: float,
    crowding_quantile: float,
) -> dict[str, Any]:
    pump = frame.loc[frame["pump_context_pct"] >= pump_quantile].copy()
    crowded = pump.loc[pump["crowding_pct"] >= crowding_quantile].copy()
    control = pump.loc[pump["crowding_pct"] < crowding_quantile].copy()
    payload: dict[str, Any] = {
        "pump_row_count": int(len(pump)),
        "crowded_row_count": int(len(crowded)),
        "control_row_count": int(len(control)),
        "timestamp_count": int(pump["timestamp_ms"].nunique()) if len(pump) else 0,
        "subject_count": int(pump["subject"].nunique()) if len(pump) else 0,
        "horizons": {},
    }
    for horizon in DEFAULT_HORIZONS:
        col = f"forward_{horizon}d_log_return"
        crowded_forward = pd.to_numeric(crowded[col], errors="coerce").dropna()
        control_forward = pd.to_numeric(control[col], errors="coerce").dropna()
        crowded_short = -crowded_forward
        control_short = -control_forward
        uplift = float(crowded_short.mean() - control_short.mean()) if len(crowded_short) and len(control_short) else 0.0
        payload["horizons"][f"h{horizon}d"] = {
            "crowded_short_return_mean": float(crowded_short.mean()) if len(crowded_short) else 0.0,
            "control_short_return_mean": float(control_short.mean()) if len(control_short) else 0.0,
            "short_return_uplift": uplift,
            "crowded_short_win_fraction": float((crowded_short > 0).mean()) if len(crowded_short) else 0.0,
            "control_short_win_fraction": float((control_short > 0).mean()) if len(control_short) else 0.0,
            "crowded_observation_count": int(len(crowded_short)),
            "control_observation_count": int(len(control_short)),
        }
    return payload


def _same_day_shuffle(
    frame: pd.DataFrame,
    *,
    pump_quantile: float,
    crowding_quantile: float,
    iterations: int,
) -> dict[str, Any]:
    rng = np.random.default_rng(1729)
    observed = _cohort_metrics(
        frame,
        pump_quantile=pump_quantile,
        crowding_quantile=crowding_quantile,
    )
    observed_h10 = float(observed["horizons"]["h10d"]["short_return_uplift"])
    shuffled: list[float] = []
    base = frame.copy()
    for _ in range(iterations):
        shuffled_frame = base.copy()
        shuffled_frame["crowding_pct"] = (
            shuffled_frame.groupby("timestamp_ms")["crowding_pct"]
            .transform(lambda values: rng.permutation(values.to_numpy()))
            .astype("float64")
        )
        metrics = _cohort_metrics(
            shuffled_frame,
            pump_quantile=pump_quantile,
            crowding_quantile=crowding_quantile,
        )
        shuffled.append(float(metrics["horizons"]["h10d"]["short_return_uplift"]))
    shuffled_arr = np.array(shuffled, dtype="float64")
    return {
        "iterations": int(iterations),
        "observed_h10d_short_uplift": observed_h10,
        "shuffle_mean_h10d_short_uplift": float(np.nanmean(shuffled_arr)) if len(shuffled_arr) else 0.0,
        "shuffle_p95_h10d_short_uplift": float(np.nanpercentile(shuffled_arr, 95)) if len(shuffled_arr) else 0.0,
        "observed_quantile": float((shuffled_arr <= observed_h10).mean()) if len(shuffled_arr) else 0.0,
        "passed": bool(observed_h10 > 0 and (shuffled_arr <= observed_h10).mean() >= 0.90)
        if len(shuffled_arr)
        else False,
    }


def _verdict(metrics: dict[str, Any], shuffle: dict[str, Any]) -> dict[str, Any]:
    h10 = metrics["horizons"]["h10d"]
    h5 = metrics["horizons"]["h5d"]
    checks = {
        "h10d_short_uplift_positive": float(h10["short_return_uplift"]) > 0,
        "h5d_short_uplift_positive": float(h5["short_return_uplift"]) > 0,
        "h10d_short_win_fraction_ge_control": float(h10["crowded_short_win_fraction"])
        >= float(h10["control_short_win_fraction"]),
        "same_day_shuffle_h10d_passed": bool(shuffle["passed"]),
        "not_extreme_sample_only": int(metrics["crowded_row_count"]) >= 100,
    }
    passed = sum(1 for value in checks.values() if value)
    if passed >= 4:
        label = "stage0_keep"
    elif passed >= 3:
        label = "stage0_watch"
    else:
        label = "stage0_reject"
    return {"label": label, "passed_check_count": passed, "total_check_count": len(checks), "checks": checks}


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    as_of = str(args.as_of)
    report_dir = ROOT / "artifacts" / "quant_research" / "factor_reports" / as_of
    report_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_path or (report_dir / "funding_oi_crowded_squeeze_failure_stage0.json")
    frame = _prepare_frame(as_of)
    metrics = _cohort_metrics(
        frame,
        pump_quantile=float(args.pump_quantile),
        crowding_quantile=float(args.crowding_quantile),
    )
    shuffle = _same_day_shuffle(
        frame,
        pump_quantile=float(args.pump_quantile),
        crowding_quantile=float(args.crowding_quantile),
        iterations=int(args.shuffle_iterations),
    )
    payload = {
        "artifact_family": "quant_funding_oi_crowded_squeeze_failure_stage0",
        "contract_version": CONTRACT_VERSION,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": as_of,
        "features_artifact": str(spk_eval._features_artifact_path(as_of)),  # noqa: SLF001
        "hypothesis": "High funding + rising OI + weak/crowded post-pump context predicts later crowded-long liquidation.",
        "pump_quantile": float(args.pump_quantile),
        "crowding_quantile": float(args.crowding_quantile),
        "crowding_columns": CROWDING_COLUMNS,
        "pump_columns": PUMP_COLUMNS,
        "feature_presence": _feature_presence(frame, CROWDING_COLUMNS + PUMP_COLUMNS),
        "cohort_metrics": metrics,
        "same_day_feature_shuffle": shuffle,
        "verdict": _verdict(metrics, shuffle),
    }
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
