"""validate_week_2_exit.py — Alpha Ontology W1 / "Week 2 exit criterion".

Per `docs/quant_research/00_roadmap_state/alpha_ontology_and_factor_library.md` §H.1, the Week 2
exit gate is three checks:
    1. v92 cycle completed (deferred — requires `run_quant_research_cycle`).
    2. At least 5 new factors pass admission.
    3. Combined IC ≥ v91 IC + 0.005.

This script verifies criteria #2 and #3 directly from the existing W1.3 factor
report cards (`artifacts/quant_research/factor_reports/<date>/`) and from a
panel-level rank-IC comparison between `xs_minimal_v6_score` (v91 baseline)
and `xs_alpha_ontology_v1_score` (W1.4 expansion).

Criterion #1 is *out of scope* for this script and would need a full
hypothesis_batch cycle (universe freeze, derivatives sync, walk-forward
backtest). The script reports criterion #1 as `out_of_scope` rather than
`pass` or `fail`.

Lookahead disclosure: the v91 + alpha_ontology_v1 weight tables are derived
from full-panel rank IC and contain the in-sample test segment. The combined
IC measured here therefore inherits the same in-sample lookahead. This is the
same shortcut used for v91 hand-tuned weights and is documented in
`xs_alpha_ontology_v1_score`'s docstring; Phase 1d's rolling-IR dynamic
weight schedule is the proper OOS alternative and a separate work item.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.features import (  # noqa: E402
    build_cross_sectional_feature_bundle,
    xs_minimal_v6_score,
    xs_alpha_ontology_v1_score,
)


DEFAULT_PANEL_ARTIFACT = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "features"
    / "2026-04-29-cross-sectional-daily-1d-features-v1"
    / "features.csv.gz"
)
DEFAULT_REPORT_DATE = "2026-04-29"
DEFAULT_OUT_ROOT = ROOT / "artifacts" / "quant_research" / "week_2_exit_validation"
DEFAULT_FACTOR_REPORT_ROOT = ROOT / "artifacts" / "quant_research" / "factor_reports"

UPLIFT_THRESHOLD = 0.005
ADMITTED_FACTORS_THRESHOLD = 5

# Criterion 2 strict gate per the W1.4 admission decision:
G6_RESIDUAL_IC_THRESHOLD = 0.02
G3_REGIME_SAME_SIGN_THRESHOLD = 0.60

PANEL_INPUT_COLUMNS = (
    "subject", "timestamp_ms", "liquidity_bucket", "usdm_symbol",
    "spot_open", "spot_high", "spot_low", "spot_close",
    "spot_volume", "spot_quote_volume", "rolling_median_quote_volume_usd_30d",
    "funding_rate", "basis_proxy", "open_interest", "open_interest_value",
    "intraday_realized_vol_4h_to_1d",
    "coinglass_top_trader_long_pct",
    "coinglass_taker_imbalance_5d_sum",
    "coinglass_taker_imb_intraday_dispersion_24h",
    "coinglass_top_trader_intraday_volatility_24h",
    "coinglass_orderbook_imb_persistence_24h",
    "coinglass_liquidation_imbalance_24h",
    "coinglass_liq_intraday_concentration_24h",
    "coinglass_global_account_long_pct",
)


def per_timestamp_rank_ic(
    factor: pd.Series,
    target: pd.Series,
    timestamps: pd.Series,
) -> pd.Series:
    df = pd.DataFrame({"f": factor, "t": target, "ts": timestamps}).dropna()
    if df.empty:
        return pd.Series(dtype="float64")
    fr = df.groupby("ts")["f"].rank(method="average")
    tr = df.groupby("ts")["t"].rank(method="average")
    fr_mean = fr.groupby(df["ts"]).transform("mean")
    tr_mean = tr.groupby(df["ts"]).transform("mean")
    fr_dev = fr - fr_mean
    tr_dev = tr - tr_mean
    num = (fr_dev * tr_dev).groupby(df["ts"]).sum()
    denom = np.sqrt(
        (fr_dev * fr_dev).groupby(df["ts"]).sum()
        * (tr_dev * tr_dev).groupby(df["ts"]).sum()
    )
    return (num / denom.replace(0.0, np.nan)).rename("ic")


def build_regime_by_ts(features: pd.DataFrame, anchor_subject: str) -> pd.Series:
    btc = features[features["subject"] == anchor_subject]
    if btc.empty or "realized_volatility_20" not in btc.columns:
        available = sorted(features["subject"].dropna().unique().tolist())
        raise RuntimeError(
            f"anchor_subject={anchor_subject!r} not found; available: "
            f"{available[:10]}{'...' if len(available) > 10 else ''}"
        )
    rv = pd.to_numeric(
        btc.set_index("timestamp_ms")["realized_volatility_20"], errors="coerce"
    ).replace(0.0, np.nan).dropna()
    if rv.empty:
        raise RuntimeError("BTC realized_volatility_20 is all NaN")
    q_lo, q_hi = rv.quantile([1.0 / 3, 2.0 / 3]).tolist()

    def _tag(x: float) -> str:
        if pd.isna(x):
            return "unknown"
        if x < q_lo:
            return "low_vol"
        if x > q_hi:
            return "high_vol"
        return "mid_vol"

    return rv.apply(_tag)


def summarise_score_ic(
    score: pd.Series,
    target: pd.Series,
    timestamps: pd.Series,
    regime_by_ts: pd.Series,
    rolling_window: int = 60,
) -> dict:
    ic = per_timestamp_rank_ic(score, target, timestamps).sort_index()
    valid = ic.dropna()
    if valid.empty:
        return {
            "ic_mean": float("nan"),
            "ic_std": float("nan"),
            "ir": float("nan"),
            "pos_day_rate": float("nan"),
            "n_days": 0,
            "rolling_60d_pos_fraction": float("nan"),
            "rolling_60d_max_drop": float("nan"),
            "rolling_60d_max_rise": float("nan"),
            "regime_ic": {},
            "regime_same_sign_fraction": float("nan"),
        }
    ic_mean = float(valid.mean())
    ic_std = float(valid.std())
    ir = ic_mean / ic_std if ic_std and ic_std > 0 else float("nan")
    pos_day_rate = float((valid > 0).mean())

    rolling = valid.rolling(rolling_window).mean().dropna()
    rolling_pos = float((rolling > 0).mean()) if not rolling.empty else float("nan")
    rolling_min = float(rolling.min()) if not rolling.empty else float("nan")
    rolling_max = float(rolling.max()) if not rolling.empty else float("nan")

    aligned = pd.DataFrame(
        {"ic": valid, "regime": regime_by_ts.reindex(valid.index)}
    ).dropna()
    if aligned.empty:
        regime_ic = {}
        regime_same_sign = float("nan")
    else:
        regime_means = aligned.groupby("regime")["ic"].mean()
        regime_ic = {str(k): float(v) for k, v in regime_means.items()}
        if len(regime_means) >= 2:
            overall_sign = np.sign(regime_means.mean())
            regime_same_sign = (
                float((np.sign(regime_means) == overall_sign).mean())
                if overall_sign != 0
                else float("nan")
            )
        else:
            regime_same_sign = float("nan")

    return {
        "ic_mean": ic_mean,
        "ic_std": ic_std,
        "ir": float(ir) if not (isinstance(ir, float) and math.isnan(ir)) else float("nan"),
        "pos_day_rate": pos_day_rate,
        "n_days": int(valid.shape[0]),
        "rolling_60d_pos_fraction": rolling_pos,
        "rolling_60d_max_drop": rolling_min,
        "rolling_60d_max_rise": rolling_max,
        "regime_ic": regime_ic,
        "regime_same_sign_fraction": regime_same_sign,
    }


def assess_criterion_2(
    factor_report_root: Path,
    report_date: str,
) -> dict:
    summary_csv = factor_report_root / report_date / "summary.csv"
    if not summary_csv.exists():
        return {
            "available": False,
            "reason": f"factor report summary not found at {summary_csv}",
            "passed": False,
        }
    df = pd.read_csv(summary_csv)
    w11 = df[df["kind"] != "v91_baseline"].copy()
    w11["g6_pass"] = w11["residual_ic_baseline"].abs() >= G6_RESIDUAL_IC_THRESHOLD
    w11["g3_pass"] = w11["regime_same_sign"] >= G3_REGIME_SAME_SIGN_THRESHOLD
    w11["strict_pass"] = w11["g6_pass"] & w11["g3_pass"]
    strict_passers = w11[w11["strict_pass"]][["factor_id", "column", "kind", "ic_mean", "residual_ic_baseline", "regime_same_sign", "gate_pass_count"]]
    n_strict = int(w11["strict_pass"].sum())
    g6_only = int(w11["g6_pass"].sum())
    g3_only = int(w11["g3_pass"].sum())
    by_pass_count = (
        w11.groupby("gate_pass_count").size().rename("n_factors").to_dict()
    )

    return {
        "available": True,
        "summary_csv": str(summary_csv),
        "n_w11_candidates_total": int(len(w11)),
        "n_strict_pass_g6_and_g3": n_strict,
        "n_g6_pass_only": g6_only,
        "n_g3_pass_only": g3_only,
        "gate_pass_count_histogram": {int(k): int(v) for k, v in by_pass_count.items()},
        "threshold": ADMITTED_FACTORS_THRESHOLD,
        "passed": n_strict >= ADMITTED_FACTORS_THRESHOLD,
        "strict_pass_factors": strict_passers.to_dict(orient="records"),
    }


def _sanitize_for_json(obj):
    if isinstance(obj, dict):
        return {str(k): _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_json(v) for v in obj]
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.floating):
        v = float(obj)
        return None if math.isnan(v) or math.isinf(v) else v
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.ndarray):
        return [_sanitize_for_json(v) for v in obj.tolist()]
    if isinstance(obj, float):
        return None if math.isnan(obj) or math.isinf(obj) else obj
    return obj


def main(argv=None):
    parser = argparse.ArgumentParser(description="Week 2 exit criterion validation per alpha_ontology §H.1")
    parser.add_argument("--panel", default=str(DEFAULT_PANEL_ARTIFACT))
    parser.add_argument("--out-root", default=str(DEFAULT_OUT_ROOT))
    parser.add_argument("--report-date", default=DEFAULT_REPORT_DATE)
    parser.add_argument("--target-shift-bars", type=int, default=5)
    parser.add_argument("--anchor-subject", default="BTC")
    parser.add_argument("--factor-report-root", default=str(DEFAULT_FACTOR_REPORT_ROOT))
    args = parser.parse_args(argv)

    panel_path = Path(args.panel).resolve()
    out_dir = Path(args.out_root).resolve() / args.report_date
    out_dir.mkdir(parents=True, exist_ok=True)
    factor_report_root = Path(args.factor_report_root).resolve()

    print(f"[load] panel: {panel_path}")
    panel_df = pd.read_csv(panel_path, compression="gzip")
    keep = [c for c in PANEL_INPUT_COLUMNS if c in panel_df.columns]
    panel = panel_df[keep].copy()
    print(f"[load] panel shape: {panel.shape}")

    print(f"[features] rebuilding via build_cross_sectional_feature_bundle")
    bundle = build_cross_sectional_feature_bundle(panel, target_shift_bars=args.target_shift_bars)
    features = bundle["dataframe"].sort_values(["timestamp_ms", "subject"]).reset_index(drop=True)
    target_col = bundle["forward_return_column"]
    print(f"[features] features shape: {features.shape}, target_col={target_col}")

    target = pd.to_numeric(features[target_col], errors="coerce")
    timestamps = features["timestamp_ms"]
    period_start = pd.Timestamp(int(timestamps.min()), unit="ms", tz="UTC").strftime("%Y-%m-%d")
    period_end = pd.Timestamp(int(timestamps.max()), unit="ms", tz="UTC").strftime("%Y-%m-%d")
    period_days = int(timestamps.nunique())

    print(f"[regime] BTC realised-vol tertile classifier (anchor={args.anchor_subject})")
    regime_by_ts = build_regime_by_ts(features, args.anchor_subject)

    print(f"[score] computing v91 score (xs_minimal_v6_score)")
    v91_score = xs_minimal_v6_score(features)
    print(f"[score] computing alpha_ontology_v1 score (xs_alpha_ontology_v1_score)")
    ao_score = xs_alpha_ontology_v1_score(features)

    print(f"[ic] summarising per-timestamp rank IC for both scores")
    v91_ic = summarise_score_ic(v91_score, target, timestamps, regime_by_ts)
    ao_ic = summarise_score_ic(ao_score, target, timestamps, regime_by_ts)
    uplift = ao_ic["ic_mean"] - v91_ic["ic_mean"]
    crit3_pass = (not math.isnan(uplift)) and uplift >= UPLIFT_THRESHOLD

    print(f"[criterion-2] reading factor report cards from {factor_report_root}")
    crit2 = assess_criterion_2(factor_report_root, args.report_date)

    crit1 = {
        "available": False,
        "scope": "out_of_scope_for_this_script",
        "reason": (
            "v92/alpha_ontology_v1 cycle requires run_quant_research_cycle "
            "(universe freeze + derivatives sync + walk-forward backtest + "
            "fast_reject_report + validation_report). Cycle invocation is the "
            "operator's responsibility and is documented in the W1.4 provenance "
            "entry. This validator covers criterion #2 (admitted factor count) "
            "and criterion #3 (score-level combined IC uplift) only."
        ),
        "passed": None,
    }

    overall_passed = bool(crit2.get("passed") and crit3_pass)
    overall_status = "PASS" if overall_passed else (
        "PARTIAL" if (crit2.get("passed") or crit3_pass) else "FAIL"
    )

    summary = {
        "report_date": args.report_date,
        "panel_artifact": str(panel_path),
        "features_rows": int(features.shape[0]),
        "period_start": period_start,
        "period_end": period_end,
        "period_days": period_days,
        "anchor_subject": args.anchor_subject,
        "target_horizon_bars": int(args.target_shift_bars),
        "lookahead_disclosure": (
            "v91 and alpha_ontology_v1 score weights are derived from full-panel "
            "rank IC including the test segment; combined IC measured here inherits "
            "that in-sample lookahead. This is the same shortcut documented in "
            "xs_alpha_ontology_v1_score and is the v91-baseline-preserved methodology. "
            "Phase 1d's rolling-IR dynamic weight schedule is the proper OOS variant."
        ),
        "criterion_1_v92_cycle_completed": crit1,
        "criterion_2_at_least_5_factors_pass_admission": crit2,
        "criterion_3_combined_ic_uplift_ge_0_005": {
            "v91_combined_ic": v91_ic,
            "alpha_ontology_v1_combined_ic": ao_ic,
            "uplift": float(uplift) if not math.isnan(uplift) else None,
            "uplift_threshold": UPLIFT_THRESHOLD,
            "passed": crit3_pass,
        },
        "overall_status": overall_status,
        "overall_passed": overall_passed,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }

    json_path = out_dir / "summary.json"
    with json_path.open("w", encoding="utf-8") as fh:
        json.dump(_sanitize_for_json(summary), fh, indent=2)

    txt_path = out_dir / "summary.txt"
    with txt_path.open("w", encoding="utf-8") as fh:
        fh.write(_render_text(summary))

    print(f"[done] wrote summary to {json_path}")
    print(f"[done] human-readable summary at {txt_path}")
    print()
    print(_render_text(summary))


def _render_text(summary: dict) -> str:
    def fmt(v, p=4, sign=False):
        if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
            return "n/a"
        return f"{v:+.{p}f}" if sign else f"{v:.{p}f}"

    def pct(v, p=1):
        if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
            return "n/a"
        return f"{v * 100:.{p}f}%"

    crit2 = summary["criterion_2_at_least_5_factors_pass_admission"]
    crit3 = summary["criterion_3_combined_ic_uplift_ge_0_005"]
    v91 = crit3["v91_combined_ic"]
    ao = crit3["alpha_ontology_v1_combined_ic"]

    lines = [
        f"Week 2 exit verification ({summary['report_date']})",
        f"period: {summary['period_start']} → {summary['period_end']} ({summary['period_days']} days)",
        f"panel: {summary['panel_artifact']}",
        f"features rows: {summary['features_rows']}",
        "",
        f"OVERALL: {summary['overall_status']} (criterion 1 out_of_scope, 2 = {'PASS' if crit2.get('passed') else 'FAIL'}, 3 = {'PASS' if crit3['passed'] else 'FAIL'})",
        "",
        "[criterion 1] v92 cycle completed: out_of_scope (full hypothesis_batch cycle).",
        "",
        f"[criterion 2] >= 5 W1.1 factors pass admission (strict G6 |residual_ic|>=0.02 AND G3 same_sign>=0.60)",
        f"  available factor report cards: {crit2.get('summary_csv', 'n/a')}",
        f"  W1.1 candidates total: {crit2.get('n_w11_candidates_total', 'n/a')}",
        f"  strict pass (G6 AND G3): {crit2.get('n_strict_pass_g6_and_g3', 'n/a')} (threshold {crit2.get('threshold', 'n/a')})",
        f"  G6 pass only:            {crit2.get('n_g6_pass_only', 'n/a')}",
        f"  G3 pass only:            {crit2.get('n_g3_pass_only', 'n/a')}",
        f"  result: {'PASS' if crit2.get('passed') else 'FAIL'}",
        f"  strict pass list: {[f['factor_id'] for f in crit2.get('strict_pass_factors', [])] or 'none'}",
        "",
        f"[criterion 3] combined IC uplift >= {crit3['uplift_threshold']:+.3f}",
        f"  v91 combined IC:                 mean={fmt(v91['ic_mean'], 4, True)}  IR={fmt(v91['ir'], 3, True)}  pos_day_rate={pct(v91['pos_day_rate'])}  rolling60d_pos%={pct(v91['rolling_60d_pos_fraction'])}",
        f"  alpha_ontology_v1 combined IC:   mean={fmt(ao['ic_mean'], 4, True)}  IR={fmt(ao['ir'], 3, True)}  pos_day_rate={pct(ao['pos_day_rate'])}  rolling60d_pos%={pct(ao['rolling_60d_pos_fraction'])}",
        f"  uplift:                          {fmt(crit3['uplift'], 4, True)} (threshold {crit3['uplift_threshold']:+.4f})",
        f"  result: {'PASS' if crit3['passed'] else 'FAIL'}",
        "",
        f"  v91 regime IC: " + "  ".join(f"{k}={fmt(v, 4, True)}" for k, v in v91.get('regime_ic', {}).items()) + f"  same_sign={pct(v91.get('regime_same_sign_fraction'))}",
        f"  ao  regime IC: " + "  ".join(f"{k}={fmt(v, 4, True)}" for k, v in ao.get('regime_ic', {}).items()) + f"  same_sign={pct(ao.get('regime_same_sign_fraction'))}",
        "",
        "Lookahead disclosure: " + summary["lookahead_disclosure"],
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
