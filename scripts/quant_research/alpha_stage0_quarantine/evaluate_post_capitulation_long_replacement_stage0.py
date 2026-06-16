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
from enhengclaw.quant_research.features import xs_alpha_ontology_v5_score  # noqa: E402


CONTRACT_VERSION = "quant_post_capitulation_long_replacement_stage0.v1"
DEFAULT_AS_OF = "2026-05-02"
DEFAULT_HORIZONS = (3, 5, 10)
REQUIRED_COLUMNS = [
    "liq_cascade_recency_score_5d",
    "liq_cascade_signed_intensity_24h",
    "coinglass_liq_intraday_concentration_24h",
    "ob_bid_replenishment_ratio_1d",
    "coinglass_orderbook_imb_persistence_24h",
]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Stage-0 diagnostic for post-capitulation long replacement. "
            "The candidate only changes the parent long boundary: top-3 longs "
            "can be replaced from the top-6 pool when liquidation release and "
            "bid-replenishment evidence are both favorable."
        )
    )
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--target-horizon-bars", type=int, default=10)
    parser.add_argument("--replacement-pool-size", type=int, default=6)
    parser.add_argument("--signal-quantile", type=float, default=0.75)
    parser.add_argument("--output-path", type=Path, default=None)
    return parser


def _timestamp_zscore(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
    values = pd.to_numeric(frame[column], errors="coerce")
    grouped = values.groupby(frame["timestamp_ms"])
    mean = grouped.transform("mean")
    std = grouped.transform("std").replace(0.0, np.nan)
    return ((values - mean) / std).replace([np.inf, -np.inf], np.nan).fillna(0.0)


def _add_forward_returns(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.sort_values(["subject", "timestamp_ms"]).copy()
    close = pd.to_numeric(out["spot_close"], errors="coerce")
    for horizon in DEFAULT_HORIZONS:
        out[f"forward_{horizon}d_log_return"] = close.groupby(out["subject"], sort=False).transform(
            lambda series: np.log(series.shift(-horizon) / series)
        )
    return out


def _add_rebound_signal(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    z_cascade = _timestamp_zscore(out, "liq_cascade_recency_score_5d")
    z_signed = _timestamp_zscore(out, "liq_cascade_signed_intensity_24h")
    z_conc = _timestamp_zscore(out, "coinglass_liq_intraday_concentration_24h")
    z_bid_replenish = _timestamp_zscore(out, "ob_bid_replenishment_ratio_1d")
    z_obi = _timestamp_zscore(out, "coinglass_orderbook_imb_persistence_24h")
    # Positive means forced selling recently occurred and the book is no longer
    # starved of bid support. Keep this as a Stage-0 rank signal, not a score factor.
    out["post_capitulation_rebound_score_v1"] = (
        0.35 * z_cascade
        + 0.15 * z_signed
        + 0.15 * z_conc
        + 0.25 * z_bid_replenish
        + 0.10 * z_obi
    ).astype("float64")
    out["post_capitulation_rebound_pct_v1"] = (
        out["post_capitulation_rebound_score_v1"]
        .groupby(out["timestamp_ms"])
        .rank(method="average", pct=True)
        .fillna(0.0)
    )
    return out


def _build_stage0_frame(as_of: str, *, target_horizon_bars: int) -> pd.DataFrame:
    features_path = spk_eval._features_artifact_path(as_of)  # noqa: SLF001
    frame = spk_eval._build_risk_frame(  # noqa: SLF001
        features_path,
        target_horizon_bars=target_horizon_bars,
    )
    raw = pd.read_csv(features_path, compression="gzip")
    merge_keys = [key for key in ["subject", "timestamp_ms"] if key in raw.columns and key in frame.columns]
    passthrough_columns = [
        column
        for column in REQUIRED_COLUMNS
        if column in raw.columns and column not in frame.columns
    ]
    if merge_keys and passthrough_columns:
        frame = frame.merge(
            raw[merge_keys + passthrough_columns],
            on=merge_keys,
            how="left",
            validate="one_to_one",
        )
    return frame


def _feature_presence(frame: pd.DataFrame) -> dict[str, Any]:
    return {
        col: {
            "present": col in frame.columns,
            "non_null_fraction": float(pd.to_numeric(frame[col], errors="coerce").notna().mean())
            if col in frame.columns and len(frame)
            else 0.0,
        }
        for col in REQUIRED_COLUMNS
    }


def _long_replacement_score(
    frame: pd.DataFrame,
    *,
    base_scorer,
    replacement_pool_size: int,
    signal_quantile: float,
) -> pd.Series:
    if frame.empty or "timestamp_ms" not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
    prepared = _add_rebound_signal(frame)
    base_score = base_scorer(prepared).astype("float64")
    adjusted = base_score.copy()
    top_k = 3
    pool_size = max(int(replacement_pool_size), top_k + 1)
    epsilon = 1e-6
    for _, idx in prepared.groupby("timestamp_ms", sort=False).groups.items():
        ts_index = pd.Index(idx)
        group = pd.DataFrame(
            {
                "base_score": base_score.loc[ts_index],
                "signal": prepared.loc[ts_index, "post_capitulation_rebound_score_v1"],
                "signal_pct": prepared.loc[ts_index, "post_capitulation_rebound_pct_v1"],
            },
            index=ts_index,
        )
        if group.empty or len(group) <= top_k:
            continue
        ordered = group.sort_values("base_score", ascending=False).copy()
        current_longs = ordered.head(min(top_k, len(ordered))).copy()
        pool = ordered.head(min(pool_size, len(ordered))).copy()
        eligible = pool.loc[
            (~pool.index.isin(current_longs.index))
            & (pool["signal_pct"] >= float(signal_quantile))
        ].copy()
        if eligible.empty:
            continue
        ejectable = current_longs.loc[current_longs["signal_pct"] < float(signal_quantile)].copy()
        if ejectable.empty:
            continue
        eligible.sort_values(["signal", "base_score"], ascending=[False, False], inplace=True)
        ejectable.sort_values(["base_score", "signal"], ascending=[True, True], inplace=True)
        replace_idx = eligible.index[0]
        eject_idx = ejectable.index[0]
        eject_score = float(adjusted.loc[eject_idx])
        adjusted.loc[replace_idx] = eject_score + epsilon
    return adjusted.astype("float64")


def _selection_change_diagnostic(
    frame: pd.DataFrame,
    *,
    baseline_scorer,
    candidate_scorer,
    target_horizon_bars: int,
) -> dict[str, Any]:
    filtered = _add_rebound_signal(frame)
    filtered["baseline_score"] = baseline_scorer(filtered)
    filtered["candidate_score"] = candidate_scorer(filtered)
    entered_rows: list[dict[str, Any]] = []
    exited_rows: list[dict[str, Any]] = []
    total_timestamps = 0
    changed_timestamps = 0
    overlap: list[float] = []
    for _, group in filtered.groupby("timestamp_ms"):
        total_timestamps += 1
        baseline_longs = group.sort_values("baseline_score", ascending=False).head(min(3, len(group))).copy()
        candidate_longs = group.sort_values("candidate_score", ascending=False).head(min(3, len(group))).copy()
        baseline_subjects = set(baseline_longs["subject"].astype(str))
        candidate_subjects = set(candidate_longs["subject"].astype(str))
        overlap.append(len(baseline_subjects & candidate_subjects) / 3.0)
        if baseline_subjects == candidate_subjects:
            continue
        changed_timestamps += 1
        entered = candidate_longs.loc[~candidate_longs["subject"].astype(str).isin(baseline_subjects)].copy()
        exited = baseline_longs.loc[~baseline_longs["subject"].astype(str).isin(candidate_subjects)].copy()
        for _, row in entered.iterrows():
            entered_rows.append(_row_summary(row, target_horizon_bars))
        for _, row in exited.iterrows():
            exited_rows.append(_row_summary(row, target_horizon_bars))
    entered_df = pd.DataFrame(entered_rows)
    exited_df = pd.DataFrame(exited_rows)
    return {
        "status": "ok",
        "timestamp_count": int(total_timestamps),
        "timestamps_with_long_changes": int(changed_timestamps),
        "timestamps_with_long_changes_fraction": float(changed_timestamps / max(total_timestamps, 1)),
        "total_replacements": int(len(entered_df)),
        "replacement_position_fraction": float(len(entered_df) / max(total_timestamps * 3, 1)),
        "average_long_overlap_fraction": float(np.mean(overlap)) if overlap else 1.0,
        "entered_long_count": int(len(entered_df)),
        "exited_long_count": int(len(exited_df)),
        "entered_mean_rebound_score": _safe_mean(entered_df, "post_capitulation_rebound_score_v1"),
        "exited_mean_rebound_score": _safe_mean(exited_df, "post_capitulation_rebound_score_v1"),
        "entered_mean_rebound_pct": _safe_mean(entered_df, "post_capitulation_rebound_pct_v1"),
        "exited_mean_rebound_pct": _safe_mean(exited_df, "post_capitulation_rebound_pct_v1"),
        "entered_next_1d_mean": _safe_mean(entered_df, "forward_1d_log_return"),
        "exited_next_1d_mean": _safe_mean(exited_df, "forward_1d_log_return"),
        f"entered_next_{target_horizon_bars}d_mean": _safe_mean(
            entered_df,
            f"forward_{target_horizon_bars}d_log_return",
        ),
        f"exited_next_{target_horizon_bars}d_mean": _safe_mean(
            exited_df,
            f"forward_{target_horizon_bars}d_log_return",
        ),
        f"entered_next_{target_horizon_bars}d_hit_fraction": _safe_frac(
            entered_df,
            lambda df: pd.to_numeric(df[f"forward_{target_horizon_bars}d_log_return"], errors="coerce").fillna(0.0) > 0,
        ),
        f"exited_next_{target_horizon_bars}d_hit_fraction": _safe_frac(
            exited_df,
            lambda df: pd.to_numeric(df[f"forward_{target_horizon_bars}d_log_return"], errors="coerce").fillna(0.0) > 0,
        ),
    }


def _row_summary(row: pd.Series, target_horizon_bars: int) -> dict[str, Any]:
    return {
        "subject": str(row.get("subject") or ""),
        "liquidity_bucket": str(row.get("liquidity_bucket") or ""),
        "post_capitulation_rebound_score_v1": _float_or_nan(row.get("post_capitulation_rebound_score_v1")),
        "post_capitulation_rebound_pct_v1": _float_or_nan(row.get("post_capitulation_rebound_pct_v1")),
        "forward_1d_log_return": _float_or_nan(row.get("forward_1d_log_return")),
        f"forward_{target_horizon_bars}d_log_return": _float_or_nan(
            row.get(f"forward_{target_horizon_bars}d_log_return")
        ),
    }


def _float_or_nan(value: Any) -> float:
    numeric = pd.to_numeric(value, errors="coerce")
    return float(numeric) if pd.notna(numeric) else np.nan


def _safe_mean(df: pd.DataFrame, column: str) -> float | None:
    if df.empty or column not in df.columns:
        return None
    values = pd.to_numeric(df[column], errors="coerce").dropna()
    return float(values.mean()) if len(values) else None


def _safe_frac(df: pd.DataFrame, predicate) -> float | None:
    if df.empty:
        return None
    return float(predicate(df).mean())


def _long_basket_summary(
    frame: pd.DataFrame,
    *,
    scorer,
    target_horizon_bars: int,
) -> dict[str, Any]:
    scored = _add_rebound_signal(frame)
    scored["score"] = scorer(scored)
    rows: list[dict[str, Any]] = []
    for _, group in scored.groupby("timestamp_ms"):
        longs = group.sort_values("score", ascending=False).head(min(3, len(group))).copy()
        rows.extend(longs.to_dict("records"))
    basket = pd.DataFrame(rows)
    if basket.empty:
        return {"status": "empty"}
    h_col = f"forward_{target_horizon_bars}d_log_return"
    fwd = pd.to_numeric(basket[h_col], errors="coerce").dropna()
    rebound_pct = pd.to_numeric(basket["post_capitulation_rebound_pct_v1"], errors="coerce").dropna()
    return {
        "status": "ok",
        "n_long_rows": int(len(basket)),
        "next_horizon_mean": float(fwd.mean()) if len(fwd) else 0.0,
        "next_horizon_hit_fraction": float((fwd > 0).mean()) if len(fwd) else 0.0,
        "rebound_pct_mean": float(rebound_pct.mean()) if len(rebound_pct) else 0.0,
        "rebound_pct_ge_signal_quantile_fraction": float((rebound_pct >= 0.75).mean()) if len(rebound_pct) else 0.0,
    }


def _verdict(selection: dict[str, Any], basket_parent: dict[str, Any], basket_candidate: dict[str, Any]) -> dict[str, Any]:
    entered = selection.get("entered_next_10d_mean")
    exited = selection.get("exited_next_10d_mean")
    checks = {
        "has_replacements": int(selection.get("total_replacements") or 0) >= 50,
        "entered_long_h10d_positive": entered is not None and float(entered) > 0,
        "entered_beats_exited_h10d": entered is not None and exited is not None and float(entered) > float(exited),
        "entered_hit_beats_exited_h10d": (
            selection.get("entered_next_10d_hit_fraction") is not None
            and selection.get("exited_next_10d_hit_fraction") is not None
            and float(selection["entered_next_10d_hit_fraction"]) >= float(selection["exited_next_10d_hit_fraction"])
        ),
        "candidate_basket_mean_beats_parent": float(basket_candidate.get("next_horizon_mean") or 0.0)
        > float(basket_parent.get("next_horizon_mean") or 0.0),
        "candidate_basket_hit_beats_parent": float(basket_candidate.get("next_horizon_hit_fraction") or 0.0)
        >= float(basket_parent.get("next_horizon_hit_fraction") or 0.0),
    }
    passed = sum(1 for value in checks.values() if value)
    if passed >= 5 and checks["entered_beats_exited_h10d"]:
        label = "stage0_keep_for_manifest"
    elif passed >= 3:
        label = "stage0_watch"
    else:
        label = "stage0_reject"
    return {"label": label, "passed_check_count": passed, "total_check_count": len(checks), "checks": checks}


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    as_of = str(args.as_of)
    target_horizon_bars = int(args.target_horizon_bars)
    report_dir = ROOT / "artifacts" / "quant_research" / "factor_reports" / as_of
    report_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_path or (report_dir / "post_capitulation_long_replacement_stage0.json")

    frame = _build_stage0_frame(as_of, target_horizon_bars=target_horizon_bars)
    frame = _add_forward_returns(frame)
    frame = _add_rebound_signal(frame)

    def candidate_scorer(local_frame: pd.DataFrame) -> pd.Series:
        return _long_replacement_score(
            local_frame,
            base_scorer=xs_alpha_ontology_v5_score,
            replacement_pool_size=int(args.replacement_pool_size),
            signal_quantile=float(args.signal_quantile),
        )

    selection = _selection_change_diagnostic(
        frame,
        baseline_scorer=xs_alpha_ontology_v5_score,
        candidate_scorer=candidate_scorer,
        target_horizon_bars=target_horizon_bars,
    )
    basket_parent = _long_basket_summary(
        frame,
        scorer=xs_alpha_ontology_v5_score,
        target_horizon_bars=target_horizon_bars,
    )
    basket_candidate = _long_basket_summary(
        frame,
        scorer=candidate_scorer,
        target_horizon_bars=target_horizon_bars,
    )
    payload = {
        "artifact_family": "quant_post_capitulation_long_replacement_stage0",
        "contract_version": CONTRACT_VERSION,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": as_of,
        "target_horizon_bars": target_horizon_bars,
        "replacement_pool_size": int(args.replacement_pool_size),
        "signal_quantile": float(args.signal_quantile),
        "features_artifact": str(spk_eval._features_artifact_path(as_of)),  # noqa: SLF001
        "required_columns": REQUIRED_COLUMNS,
        "feature_presence": _feature_presence(frame),
        "selection_change": selection,
        "long_basket_summary": {
            "parent": basket_parent,
            "post_capitulation_replacement": basket_candidate,
        },
        "verdict": _verdict(selection, basket_parent, basket_candidate),
    }
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
