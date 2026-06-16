from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

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

from scripts.quant_research import evaluate_v5_h10d_post_pump_short_replacement as v5_spk  # noqa: E402
from enhengclaw.quant_research.features import (  # noqa: E402
    _xs_alpha_ontology_v5_h10d_base_raw_score,
    _xs_alpha_ontology_v6_h10d_spk_short_replacement_score,
    xs_alpha_ontology_v5_score,
)


CONTRACT_VERSION = "mf07_subday_participant_pivot_stage0.v1"
DEFAULT_AS_OF = "2026-05-03"
HOUR_MS = 60 * 60 * 1000


@dataclass(frozen=True)
class VariantSpec:
    label: str
    candidate_veto_column: str | None
    interpretation: str


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sub-day MF-07 participant-pivot diagnostics around SP-K."
    )
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--target-horizon-bars", type=int, default=10)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--market-history-root", type=Path, default=None)
    return parser


def _variant_specs() -> list[VariantSpec]:
    return [
        VariantSpec("spk_raw", None, "Unmodified SP-K replacement on the canonical parent."),
        VariantSpec(
            "spk_confirm_retail_chase_top_fade",
            "mf07_subday_not_retail_chase_top_fade_flag",
            "Allow SP-K replacement only when global accounts add longs while top traders reduce longs.",
        ),
        VariantSpec(
            "spk_veto_retail_chase_top_fade",
            "mf07_subday_retail_chase_top_fade_flag",
            "Block SP-K replacement when global accounts add longs while top traders reduce longs.",
        ),
        VariantSpec(
            "spk_confirm_retail_outpaces_top",
            "mf07_subday_not_retail_outpaces_top_flag",
            "Allow SP-K replacement only when global-account longing outpaces top-trader longing.",
        ),
        VariantSpec(
            "spk_veto_retail_outpaces_top",
            "mf07_subday_retail_outpaces_top_flag",
            "Block SP-K replacement when global-account longing outpaces top-trader longing.",
        ),
        VariantSpec(
            "spk_confirm_top_leads_retail",
            "mf07_subday_not_top_leads_retail_flag",
            "Allow SP-K replacement only when top-trader longing outpaces global accounts.",
        ),
        VariantSpec(
            "spk_veto_top_leads_retail",
            "mf07_subday_top_leads_retail_flag",
            "Block SP-K replacement when top-trader longing outpaces global accounts.",
        ),
        VariantSpec(
            "spk_confirm_fast_retail_chase_top_fade",
            "mf07_subday_not_fast_retail_chase_top_fade_flag",
            "Allow SP-K replacement only when the same top-fade / global-chase pattern appears over 6h.",
        ),
        VariantSpec(
            "spk_veto_fast_retail_chase_top_fade",
            "mf07_subday_fast_retail_chase_top_fade_flag",
            "Block SP-K replacement when the same top-fade / global-chase pattern appears over 6h.",
        ),
        VariantSpec(
            "spk_confirm_any_retail_pivot",
            "mf07_subday_not_any_retail_pivot_flag",
            "Allow SP-K replacement only when any retail-chase participant pivot is active.",
        ),
        VariantSpec(
            "spk_veto_any_retail_pivot",
            "mf07_subday_any_retail_pivot_flag",
            "Block SP-K replacement when any retail-chase participant pivot is active.",
        ),
    ]


def _resolve_market_history_root() -> Path:
    localappdata = os.environ.get("LOCALAPPDATA", "").strip()
    if localappdata:
        return Path(localappdata) / "EnhengClaw" / "market_history"
    return Path.home() / ".local" / "share" / "EnhengClaw" / "market_history"


def _load_frame(
    *,
    as_of: str,
    target_horizon_bars: int,
    market_history_root: Path | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    features_artifact = v5_spk.base_eval._features_artifact_path(as_of)
    frame = v5_spk.base_eval._build_risk_frame(
        features_artifact,
        target_horizon_bars=target_horizon_bars,
    )
    frame = frame.copy()
    pivot_panel, pivot_meta = _build_participant_pivot_panel(
        frame[["timestamp_ms", "subject"]].drop_duplicates(),
        market_history_root=market_history_root,
    )
    frame = frame.merge(pivot_panel, on=["timestamp_ms", "subject"], how="left")
    frame, flag_meta = _add_pivot_flags(frame)
    meta = {
        "features_artifact": str(features_artifact),
        "market_history_root": str(market_history_root or _resolve_market_history_root()),
        **pivot_meta,
        **flag_meta,
    }
    return frame, meta


def _load_subject_participant_bars(
    symbol: str,
    *,
    market_history_root: Path | None = None,
) -> pd.DataFrame:
    root = market_history_root or _resolve_market_history_root()
    paths = sorted(
        glob.glob(str(root / "coinglass_extended" / f"{symbol}USDT" / "1h" / "*.csv.gz"))
    )
    if not paths:
        return pd.DataFrame()
    keep = ["open_time_ms", "top_trader_long_pct", "global_account_long_pct"]
    frames: list[pd.DataFrame] = []
    for path in paths:
        chunk = pd.read_csv(path, compression="gzip", usecols=lambda c: c in keep)
        frames.append(chunk)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    out = out[[c for c in keep if c in out.columns]].copy()
    if "open_time_ms" not in out.columns:
        return pd.DataFrame()
    for column in keep:
        if column not in out.columns:
            out[column] = np.nan
    out["open_time_ms"] = pd.to_numeric(out["open_time_ms"], errors="coerce")
    out = out.dropna(subset=["open_time_ms"]).sort_values("open_time_ms")
    out = out.drop_duplicates("open_time_ms").reset_index(drop=True)
    for column in ("top_trader_long_pct", "global_account_long_pct"):
        out[column] = pd.to_numeric(out[column], errors="coerce")
    return out


def _merge_asof_participant_snapshot(
    events: pd.DataFrame,
    bars: pd.DataFrame,
    *,
    offset_ms: int,
    suffix: str,
    max_staleness_ms: int = 3 * HOUR_MS,
) -> pd.DataFrame:
    event_lookup = events[["timestamp_ms"]].drop_duplicates().copy()
    event_lookup["_lookup_ms"] = pd.to_numeric(event_lookup["timestamp_ms"], errors="coerce") - int(
        offset_ms
    )
    event_lookup = event_lookup.sort_values("_lookup_ms")
    bars_lookup = bars.sort_values("open_time_ms").copy()
    merged = pd.merge_asof(
        event_lookup,
        bars_lookup,
        left_on="_lookup_ms",
        right_on="open_time_ms",
        direction="backward",
        allow_exact_matches=True,
    )
    age_ms = merged["_lookup_ms"] - merged["open_time_ms"]
    stale = age_ms.isna() | age_ms.gt(max_staleness_ms)
    for column in ("top_trader_long_pct", "global_account_long_pct"):
        merged.loc[stale, column] = np.nan
    return merged.rename(
        columns={
            "open_time_ms": f"participant_open_time_ms_{suffix}",
            "top_trader_long_pct": f"top_trader_long_pct_{suffix}",
            "global_account_long_pct": f"global_account_long_pct_{suffix}",
        }
    )[
        [
            "timestamp_ms",
            f"participant_open_time_ms_{suffix}",
            f"top_trader_long_pct_{suffix}",
            f"global_account_long_pct_{suffix}",
        ]
    ]


def _subject_participant_pivots(
    events: pd.DataFrame,
    bars: pd.DataFrame,
    *,
    symbol: str,
) -> pd.DataFrame:
    if bars.empty:
        return pd.DataFrame()
    now = _merge_asof_participant_snapshot(events, bars, offset_ms=1, suffix="now")
    h6 = _merge_asof_participant_snapshot(events, bars, offset_ms=6 * HOUR_MS, suffix="h6")
    h24 = _merge_asof_participant_snapshot(events, bars, offset_ms=24 * HOUR_MS, suffix="h24")
    out = now.merge(h6, on="timestamp_ms", how="left").merge(h24, on="timestamp_ms", how="left")
    out["subject"] = symbol
    out["mf07_subday_top_delta_6h"] = out["top_trader_long_pct_now"] - out[
        "top_trader_long_pct_h6"
    ]
    out["mf07_subday_global_delta_6h"] = out["global_account_long_pct_now"] - out[
        "global_account_long_pct_h6"
    ]
    out["mf07_subday_top_delta_24h"] = out["top_trader_long_pct_now"] - out[
        "top_trader_long_pct_h24"
    ]
    out["mf07_subday_global_delta_24h"] = out["global_account_long_pct_now"] - out[
        "global_account_long_pct_h24"
    ]
    out["mf07_subday_retail_minus_top_delta_24h"] = (
        out["mf07_subday_global_delta_24h"] - out["mf07_subday_top_delta_24h"]
    )
    out["mf07_subday_top_minus_retail_delta_24h"] = (
        out["mf07_subday_top_delta_24h"] - out["mf07_subday_global_delta_24h"]
    )
    out["mf07_subday_top_minus_global_level"] = (
        out["top_trader_long_pct_now"] - out["global_account_long_pct_now"]
    )
    keep = [
        "timestamp_ms",
        "subject",
        "mf07_subday_top_delta_6h",
        "mf07_subday_global_delta_6h",
        "mf07_subday_top_delta_24h",
        "mf07_subday_global_delta_24h",
        "mf07_subday_retail_minus_top_delta_24h",
        "mf07_subday_top_minus_retail_delta_24h",
        "mf07_subday_top_minus_global_level",
    ]
    return out[keep]


def _build_participant_pivot_panel(
    event_keys: pd.DataFrame,
    *,
    market_history_root: Path | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    event_keys = event_keys[["timestamp_ms", "subject"]].drop_duplicates().copy()
    event_keys["subject"] = event_keys["subject"].astype(str)
    timestamps = pd.DataFrame({"timestamp_ms": sorted(event_keys["timestamp_ms"].unique())})
    rows: list[pd.DataFrame] = []
    missing_subjects: list[str] = []
    loaded_subjects: list[str] = []
    for symbol in sorted(event_keys["subject"].unique()):
        bars = _load_subject_participant_bars(symbol, market_history_root=market_history_root)
        if bars.empty:
            missing_subjects.append(symbol)
            continue
        loaded_subjects.append(symbol)
        subject_panel = _subject_participant_pivots(timestamps, bars, symbol=symbol)
        if not subject_panel.empty:
            rows.append(subject_panel)
    if rows:
        panel = pd.concat(rows, ignore_index=True)
        panel = event_keys.merge(panel, on=["timestamp_ms", "subject"], how="left")
    else:
        panel = event_keys.copy()
        for column in _pivot_value_columns():
            panel[column] = np.nan
    coverage = float(
        panel[["mf07_subday_top_delta_24h", "mf07_subday_global_delta_24h"]]
        .notna()
        .all(axis=1)
        .mean()
    )
    meta = {
        "pivot_event_key_count": int(len(event_keys)),
        "pivot_panel_row_count": int(len(panel)),
        "pivot_subject_count": int(event_keys["subject"].nunique()),
        "pivot_loaded_subject_count": int(len(loaded_subjects)),
        "pivot_missing_subjects": missing_subjects,
        "pivot_24h_coverage": coverage,
    }
    return panel, meta


def _pivot_value_columns() -> list[str]:
    return [
        "mf07_subday_top_delta_6h",
        "mf07_subday_global_delta_6h",
        "mf07_subday_top_delta_24h",
        "mf07_subday_global_delta_24h",
        "mf07_subday_retail_minus_top_delta_24h",
        "mf07_subday_top_minus_retail_delta_24h",
        "mf07_subday_top_minus_global_level",
    ]


def _quantile(values: pd.Series, q: float) -> float:
    cleaned = pd.to_numeric(values, errors="coerce").dropna()
    if cleaned.empty:
        return float("nan")
    return float(cleaned.quantile(float(q)))


def _positive_threshold(value: float) -> float:
    if not np.isfinite(value):
        return float("nan")
    return float(max(0.0, value))


def _negative_threshold(value: float) -> float:
    if not np.isfinite(value):
        return float("nan")
    return float(min(0.0, value))


def _add_pivot_flags(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    out = frame.copy()
    top_24h = pd.to_numeric(out.get("mf07_subday_top_delta_24h"), errors="coerce")
    global_24h = pd.to_numeric(out.get("mf07_subday_global_delta_24h"), errors="coerce")
    top_6h = pd.to_numeric(out.get("mf07_subday_top_delta_6h"), errors="coerce")
    global_6h = pd.to_numeric(out.get("mf07_subday_global_delta_6h"), errors="coerce")
    retail_gap = pd.to_numeric(out.get("mf07_subday_retail_minus_top_delta_24h"), errors="coerce")
    top_gap = pd.to_numeric(out.get("mf07_subday_top_minus_retail_delta_24h"), errors="coerce")

    global_24h_q75 = _quantile(global_24h, 0.75)
    top_24h_q25 = _quantile(top_24h, 0.25)
    global_6h_q75 = _quantile(global_6h, 0.75)
    top_6h_q25 = _quantile(top_6h, 0.25)
    retail_gap_q90 = _quantile(retail_gap, 0.90)
    top_gap_q90 = _quantile(top_gap, 0.90)

    global_24h_up = _positive_threshold(global_24h_q75)
    top_24h_down = _negative_threshold(top_24h_q25)
    global_6h_up = _positive_threshold(global_6h_q75)
    top_6h_down = _negative_threshold(top_6h_q25)
    retail_gap_hi = _positive_threshold(retail_gap_q90)
    top_gap_hi = _positive_threshold(top_gap_q90)

    out["mf07_subday_retail_chase_top_fade_flag"] = (
        global_24h.ge(global_24h_up) & top_24h.le(top_24h_down)
    ).fillna(False)
    out["mf07_subday_retail_outpaces_top_flag"] = retail_gap.ge(retail_gap_hi).fillna(False)
    out["mf07_subday_top_leads_retail_flag"] = top_gap.ge(top_gap_hi).fillna(False)
    out["mf07_subday_fast_retail_chase_top_fade_flag"] = (
        global_6h.ge(global_6h_up) & top_6h.le(top_6h_down)
    ).fillna(False)
    out["mf07_subday_any_retail_pivot_flag"] = (
        out["mf07_subday_retail_chase_top_fade_flag"]
        | out["mf07_subday_retail_outpaces_top_flag"]
        | out["mf07_subday_fast_retail_chase_top_fade_flag"]
    )

    for column in _pivot_flag_columns():
        out[f"mf07_subday_not_{column.removeprefix('mf07_subday_')}"] = ~out[column]

    meta = {
        "global_delta_24h_q75": global_24h_q75,
        "top_delta_24h_q25": top_24h_q25,
        "global_delta_6h_q75": global_6h_q75,
        "top_delta_6h_q25": top_6h_q25,
        "retail_minus_top_delta_24h_q90": retail_gap_q90,
        "top_minus_retail_delta_24h_q90": top_gap_q90,
        "pivot_24h_coverage_after_merge": float((top_24h.notna() & global_24h.notna()).mean()),
        "pivot_6h_coverage_after_merge": float((top_6h.notna() & global_6h.notna()).mean()),
    }
    for column in _pivot_flag_columns():
        meta[f"{column}_fraction"] = float(out[column].fillna(False).astype(bool).mean())
    return out, meta


def _pivot_flag_columns() -> list[str]:
    return [
        "mf07_subday_retail_chase_top_fade_flag",
        "mf07_subday_retail_outpaces_top_flag",
        "mf07_subday_top_leads_retail_flag",
        "mf07_subday_fast_retail_chase_top_fade_flag",
        "mf07_subday_any_retail_pivot_flag",
    ]


def _spk_scorer(candidate_veto_column: str | None = None) -> Callable[[pd.DataFrame], pd.Series]:
    def _score(frame: pd.DataFrame) -> pd.Series:
        return _xs_alpha_ontology_v6_h10d_spk_short_replacement_score(
            frame,
            base_raw_score_fn=_xs_alpha_ontology_v5_h10d_base_raw_score,
            replacement_pool_size=6,
            signal_threshold=0.0,
            max_replacements_per_timestamp=1,
            candidate_veto_column=candidate_veto_column,
        )

    return _score


def _short_rows(
    frame: pd.DataFrame,
    *,
    score_column: str,
    target_horizon_bars: int,
    short_count: int = 3,
) -> pd.DataFrame:
    keep = [
        "timestamp_ms",
        "date_utc",
        "subject",
        "liquidity_bucket",
        score_column,
        "post_pump_stall_core_score_3d",
        "forward_1d_log_return",
        f"forward_{target_horizon_bars}d_log_return",
        *_pivot_value_columns(),
        *_pivot_flag_columns(),
    ]
    keep = [column for column in keep if column in frame.columns]
    rows: list[dict[str, Any]] = []
    for _, group in frame.groupby("timestamp_ms", sort=False):
        shorts = group.sort_values(score_column, ascending=True).head(min(short_count, len(group)))
        rows.extend(shorts[keep].to_dict("records"))
    return pd.DataFrame(rows)


def _summarize_rows(rows: pd.DataFrame, *, target_horizon_bars: int) -> dict[str, Any]:
    if rows.empty:
        return {"row_count": 0}
    hcol = f"forward_{target_horizon_bars}d_log_return"
    h = pd.to_numeric(rows.get(hcol), errors="coerce").dropna()
    one = pd.to_numeric(rows.get("forward_1d_log_return"), errors="coerce").dropna()
    out = {
        "row_count": int(len(rows)),
        "timestamp_count": int(rows["timestamp_ms"].nunique()) if "timestamp_ms" in rows.columns else None,
        "subject_count": int(rows["subject"].astype(str).nunique()) if "subject" in rows.columns else None,
        "next_1d_mean": float(one.mean()) if len(one) else None,
        "next_1d_squeeze_gt_5pct_fraction": float((one > 0.05).mean()) if len(one) else None,
        f"next_{target_horizon_bars}d_mean": float(h.mean()) if len(h) else None,
        f"next_{target_horizon_bars}d_negative_fraction": float((h < 0.0).mean()) if len(h) else None,
    }
    for column in _pivot_value_columns():
        if column in rows.columns:
            value = pd.to_numeric(rows[column], errors="coerce")
            out[f"{column}_mean"] = float(value.mean()) if value.notna().any() else None
            out[f"{column}_coverage"] = float(value.notna().mean())
    for column in _pivot_flag_columns():
        if column in rows.columns:
            out[f"{column}_fraction"] = float(rows[column].fillna(False).astype(bool).mean())
    return out


def _selection_change(
    frame: pd.DataFrame,
    *,
    baseline_score: str,
    candidate_score: str,
    target_horizon_bars: int,
    short_count: int = 3,
) -> dict[str, Any]:
    hcol = f"forward_{target_horizon_bars}d_log_return"
    entered: list[dict[str, Any]] = []
    exited: list[dict[str, Any]] = []
    changed = 0
    total = 0
    keep = [
        "timestamp_ms",
        "date_utc",
        "subject",
        "liquidity_bucket",
        "post_pump_stall_core_score_3d",
        "forward_1d_log_return",
        hcol,
        *_pivot_value_columns(),
        *_pivot_flag_columns(),
    ]
    keep = [column for column in keep if column in frame.columns]
    for _, group in frame.groupby("timestamp_ms", sort=False):
        total += 1
        baseline = group.sort_values(baseline_score, ascending=True).head(min(short_count, len(group)))
        candidate = group.sort_values(candidate_score, ascending=True).head(min(short_count, len(group)))
        baseline_subjects = set(baseline["subject"].astype(str))
        candidate_subjects = set(candidate["subject"].astype(str))
        if baseline_subjects == candidate_subjects:
            continue
        changed += 1
        entered.extend(candidate.loc[~candidate["subject"].astype(str).isin(baseline_subjects), keep].to_dict("records"))
        exited.extend(baseline.loc[~baseline["subject"].astype(str).isin(candidate_subjects), keep].to_dict("records"))
    entered_summary = _summarize_rows(pd.DataFrame(entered), target_horizon_bars=target_horizon_bars)
    exited_summary = _summarize_rows(pd.DataFrame(exited), target_horizon_bars=target_horizon_bars)
    edge = None
    field = f"next_{target_horizon_bars}d_mean"
    if entered_summary.get(field) is not None and exited_summary.get(field) is not None:
        edge = float(exited_summary[field]) - float(entered_summary[field])
    return {
        "timestamp_count": int(total),
        "changed_timestamp_count": int(changed),
        "changed_timestamp_fraction": float(changed / max(total, 1)),
        "entered": entered_summary,
        "exited": exited_summary,
        f"entered_edge_vs_exited_{target_horizon_bars}d": edge,
    }


def _compare_short_baskets(
    *,
    candidate: dict[str, Any],
    baseline: dict[str, Any],
    target_horizon_bars: int,
) -> dict[str, Any]:
    field = f"next_{target_horizon_bars}d_mean"
    lhs = baseline.get(field)
    rhs = candidate.get(field)
    edge = None if lhs is None or rhs is None else float(lhs) - float(rhs)
    if edge is not None and edge > 0.0005:
        verdict = "stage0_positive"
    elif edge is not None and abs(edge) <= 0.0005:
        verdict = "stage0_at_par"
    else:
        verdict = "stage0_negative"
    return {f"short_basket_edge_vs_baseline_{target_horizon_bars}d": edge, "verdict": verdict}


def _evaluate_variant(
    frame: pd.DataFrame,
    *,
    spec: VariantSpec,
    parent_summary: dict[str, Any],
    spk_raw_summary: dict[str, Any],
    target_horizon_bars: int,
) -> dict[str, Any]:
    work = frame.copy()
    work["candidate_score"] = _spk_scorer(spec.candidate_veto_column)(work)
    summary = _summarize_rows(
        _short_rows(work, score_column="candidate_score", target_horizon_bars=target_horizon_bars),
        target_horizon_bars=target_horizon_bars,
    )
    return {
        "label": spec.label,
        "interpretation": spec.interpretation,
        "candidate_veto_column": spec.candidate_veto_column,
        "short_basket_summary": summary,
        "vs_parent": _compare_short_baskets(
            candidate=summary,
            baseline=parent_summary,
            target_horizon_bars=target_horizon_bars,
        ),
        "vs_spk_raw": _compare_short_baskets(
            candidate=summary,
            baseline=spk_raw_summary,
            target_horizon_bars=target_horizon_bars,
        ),
        "selection_vs_parent": _selection_change(
            work,
            baseline_score="parent_score",
            candidate_score="candidate_score",
            target_horizon_bars=target_horizon_bars,
        ),
        "selection_vs_spk_raw": _selection_change(
            work,
            baseline_score="spk_raw_score",
            candidate_score="candidate_score",
            target_horizon_bars=target_horizon_bars,
        ),
    }


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    output_dir = args.output_dir or (
        ROOT
        / "artifacts"
        / "quant_research"
        / "factor_reports"
        / f"{args.as_of}-mf07-subday-participant-pivot-stage0"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    target_horizon_bars = int(args.target_horizon_bars)
    frame, input_meta = _load_frame(
        as_of=str(args.as_of),
        target_horizon_bars=target_horizon_bars,
        market_history_root=args.market_history_root,
    )
    frame["parent_score"] = xs_alpha_ontology_v5_score(frame)
    frame["spk_raw_score"] = _spk_scorer()(frame)
    parent_summary = _summarize_rows(
        _short_rows(frame, score_column="parent_score", target_horizon_bars=target_horizon_bars),
        target_horizon_bars=target_horizon_bars,
    )
    spk_raw_summary = _summarize_rows(
        _short_rows(frame, score_column="spk_raw_score", target_horizon_bars=target_horizon_bars),
        target_horizon_bars=target_horizon_bars,
    )
    evaluations = {
        spec.label: _evaluate_variant(
            frame,
            spec=spec,
            parent_summary=parent_summary,
            spk_raw_summary=spk_raw_summary,
            target_horizon_bars=target_horizon_bars,
        )
        for spec in _variant_specs()
    }
    report = {
        "contract_version": CONTRACT_VERSION,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": str(args.as_of),
        "target_horizon_bars": target_horizon_bars,
        "canonical_parent": "v5_rw_bridge_no_overlay_h10d",
        "input_meta": input_meta,
        "frame_rows": int(len(frame)),
        "timestamp_count": int(frame["timestamp_ms"].nunique()),
        "subject_count": int(frame["subject"].astype(str).nunique()),
        "parent_short_basket_summary": parent_summary,
        "spk_raw_short_basket_summary": spk_raw_summary,
        "evaluation": evaluations,
    }
    output_path = output_dir / "mf07_subday_participant_pivot_stage0.json"
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    compact: dict[str, dict[str, Any]] = {}
    for label, row in evaluations.items():
        selection = row["selection_vs_spk_raw"]
        compact[label] = {
            "changed_vs_spk_raw": selection["changed_timestamp_fraction"],
            "edge_vs_spk_raw": row["vs_spk_raw"][f"short_basket_edge_vs_baseline_{target_horizon_bars}d"],
            "entered_edge_vs_exited": selection[f"entered_edge_vs_exited_{target_horizon_bars}d"],
            "vs_parent": row["vs_parent"]["verdict"],
            "vs_spk_raw": row["vs_spk_raw"]["verdict"],
        }
    print(f"=== Wrote MF-07 sub-day participant-pivot Stage 0 report to {output_path}")
    print(json.dumps(compact, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
