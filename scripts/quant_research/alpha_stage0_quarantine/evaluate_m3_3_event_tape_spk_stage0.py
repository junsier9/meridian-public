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

from scripts.quant_research import evaluate_v5_h10d_post_pump_short_replacement as v5_spk  # noqa: E402
from enhengclaw.quant_research.features import (  # noqa: E402
    xs_alpha_ontology_v5_h10d_spk_short_replace_mid_v1_score,
    xs_alpha_ontology_v5_score,
)


CONTRACT_VERSION = "m3_3_event_tape_spk_stage0.v1"
DEFAULT_AS_OF = "2026-05-03"
DEFAULT_NEWS_ARTIFACT = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "datasets"
    / "2026-05-01-crypto-news-dataset"
    / "llm_structured_scores_adjudicated_priority_ge_8.parquet"
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Stage 0 M3.3 event tape test: measure whether adjudicated news events explain "
            "SP-K short replacement false positives on the canonical v5 h10d parent."
        )
    )
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--target-horizon-bars", type=int, default=10)
    parser.add_argument("--event-lookback-days", type=int, default=10)
    parser.add_argument("--news-artifact", type=Path, default=DEFAULT_NEWS_ARTIFACT)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--shuffle-count", type=int, default=200)
    parser.add_argument("--random-seed", type=int, default=1337)
    return parser


def _to_bool_series(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    return series.astype(str).str.lower().isin({"true", "1", "yes"})


def _explode_news_tape(news: pd.DataFrame, *, lookback_days: int) -> pd.DataFrame:
    required = {
        "currencies",
        "research_effective_at_utc",
        "final_short_veto_flag",
        "final_repricing_type",
        "final_market_impact_direction",
        "final_market_impact_magnitude",
        "final_subject_link_strength",
        "final_is_actionable_event",
        "final_event_type",
        "final_news_kind",
    }
    missing = sorted(required - set(news.columns))
    if missing:
        raise ValueError(f"news artifact missing columns: {missing}")

    frame = news.copy()
    frame["event_day"] = pd.to_datetime(frame["research_effective_at_utc"], utc=True, errors="coerce").dt.floor("D")
    frame = frame.loc[frame["event_day"].notna()].copy()
    frame["currencies"] = frame["currencies"].apply(
        lambda value: list(value) if isinstance(value, (list, tuple, set, np.ndarray)) else [value]
    )
    frame = frame.explode("currencies")
    frame["subject"] = frame["currencies"].astype(str).str.upper().str.strip()
    frame = frame.loc[frame["subject"].ne("") & frame["subject"].ne("NONE")].copy()

    repricing = frame["final_repricing_type"].astype(str).str.lower()
    direction = frame["final_market_impact_direction"].astype(str).str.lower()
    magnitude = pd.to_numeric(frame["final_market_impact_magnitude"], errors="coerce").fillna(0.0)
    link_strength = pd.to_numeric(frame["final_subject_link_strength"], errors="coerce").fillna(0.0)
    actionable = _to_bool_series(frame["final_is_actionable_event"])
    short_veto = _to_bool_series(frame["final_short_veto_flag"])

    frame["event_any_actionable"] = actionable.astype(int)
    frame["event_short_veto"] = short_veto.astype(int)
    frame["event_real_repricing"] = repricing.eq("real_repricing").astype(int)
    frame["event_hype"] = repricing.eq("hype").astype(int)
    frame["event_bullish_repricing"] = (
        repricing.isin(["real_repricing", "mixed"]) & direction.eq("bullish") & (magnitude >= 2.0)
    ).astype(int)
    frame["event_confirmed_short_veto"] = (
        short_veto
        & actionable
        & repricing.isin(["real_repricing", "mixed"])
        & direction.isin(["bullish", "neutral"])
        & (link_strength >= 3.0)
    ).astype(int)

    records: list[pd.DataFrame] = []
    offset_days = range(max(int(lookback_days), 1))
    keep_columns = [
        "subject",
        "event_day",
        "event_any_actionable",
        "event_short_veto",
        "event_real_repricing",
        "event_hype",
        "event_bullish_repricing",
        "event_confirmed_short_veto",
        "final_subject_link_strength",
        "final_market_impact_magnitude",
    ]
    slim = frame[keep_columns].copy()
    for offset in offset_days:
        expanded = slim.copy()
        expanded["date_utc"] = (expanded["event_day"] + pd.to_timedelta(offset, unit="D")).dt.date.astype(str)
        records.append(expanded)
    expanded = pd.concat(records, ignore_index=True)

    grouped = (
        expanded.groupby(["subject", "date_utc"], as_index=False)
        .agg(
            m3_3_event_tape_any_actionable_count_10d=("event_any_actionable", "sum"),
            m3_3_event_tape_short_veto_count_10d=("event_short_veto", "sum"),
            m3_3_event_tape_real_repricing_count_10d=("event_real_repricing", "sum"),
            m3_3_event_tape_hype_count_10d=("event_hype", "sum"),
            m3_3_event_tape_bullish_repricing_count_10d=("event_bullish_repricing", "sum"),
            m3_3_event_tape_confirmed_short_veto_count_10d=("event_confirmed_short_veto", "sum"),
            m3_3_event_tape_max_subject_link_strength_10d=("final_subject_link_strength", "max"),
            m3_3_event_tape_max_market_impact_magnitude_10d=("final_market_impact_magnitude", "max"),
        )
        .copy()
    )
    count_columns = [column for column in grouped.columns if column.endswith("_count_10d")]
    for column in count_columns:
        grouped[column.replace("_count_10d", "_flag_10d")] = (grouped[column] > 0).astype(int)
    return grouped


def _merge_event_tape(risk_frame: pd.DataFrame, tape: pd.DataFrame) -> pd.DataFrame:
    frame = risk_frame.copy()
    if "date_utc" not in frame.columns:
        frame["date_utc"] = pd.to_datetime(frame["timestamp_ms"], unit="ms", utc=True).dt.date.astype(str)
    merged = frame.merge(tape, on=["subject", "date_utc"], how="left")
    event_columns = [column for column in merged.columns if column.startswith("m3_3_event_tape_")]
    for column in event_columns:
        merged[column] = pd.to_numeric(merged[column], errors="coerce").fillna(0.0)
    return merged


def _selection_rows(
    *,
    frame: pd.DataFrame,
    target_horizon_bars: int,
    short_count: int = 3,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    work = frame.copy()
    work["baseline_score"] = xs_alpha_ontology_v5_score(work)
    work["candidate_score"] = xs_alpha_ontology_v5_h10d_spk_short_replace_mid_v1_score(work)
    event_columns = [column for column in work.columns if column.startswith("m3_3_event_tape_")]
    selected_rows: list[dict[str, Any]] = []
    entered_rows: list[dict[str, Any]] = []
    exited_rows: list[dict[str, Any]] = []

    base_columns = [
        "timestamp_ms",
        "date_utc",
        "subject",
        "liquidity_bucket",
        "post_pump_stall_core_score_3d",
        "forward_1d_log_return",
        f"forward_{target_horizon_bars}d_log_return",
    ]
    row_columns = base_columns + event_columns

    for _, group in work.groupby("timestamp_ms", sort=False):
        baseline_ordered = group.sort_values("baseline_score", ascending=False)
        candidate_ordered = group.sort_values("candidate_score", ascending=False)
        baseline_shorts = baseline_ordered.tail(min(short_count, len(baseline_ordered))).copy()
        candidate_shorts = candidate_ordered.tail(min(short_count, len(candidate_ordered))).copy()
        baseline_subjects = set(baseline_shorts["subject"].astype(str))
        candidate_subjects = set(candidate_shorts["subject"].astype(str))

        selected_rows.extend(candidate_shorts[row_columns].to_dict("records"))
        entered = candidate_shorts.loc[~candidate_shorts["subject"].astype(str).isin(baseline_subjects)]
        exited = baseline_shorts.loc[~baseline_shorts["subject"].astype(str).isin(candidate_subjects)]
        entered_rows.extend(entered[row_columns].to_dict("records"))
        exited_rows.extend(exited[row_columns].to_dict("records"))

    return pd.DataFrame(selected_rows), pd.DataFrame(entered_rows), pd.DataFrame(exited_rows)


def _safe_summary(rows: pd.DataFrame, *, flag_column: str, target_horizon_bars: int) -> dict[str, Any]:
    if rows.empty:
        return {"status": "empty"}
    horizon_column = f"forward_{target_horizon_bars}d_log_return"
    work = rows.copy()
    work[flag_column] = pd.to_numeric(work.get(flag_column, 0), errors="coerce").fillna(0.0).gt(0)
    out: dict[str, Any] = {
        "status": "ok",
        "row_count": int(len(work)),
        "subject_count": int(work["subject"].astype(str).nunique()) if "subject" in work.columns else None,
        "flag_column": flag_column,
        "flagged_row_count": int(work[flag_column].sum()),
        "flagged_fraction": float(work[flag_column].mean()),
    }
    for label, subset in [("flagged", work.loc[work[flag_column]]), ("unflagged", work.loc[~work[flag_column]])]:
        next_1d = pd.to_numeric(subset.get("forward_1d_log_return"), errors="coerce").dropna()
        next_h = pd.to_numeric(subset.get(horizon_column), errors="coerce").dropna()
        out[f"{label}_next_1d_mean"] = float(next_1d.mean()) if len(next_1d) else None
        out[f"{label}_next_1d_squeeze_gt_5pct_fraction"] = float((next_1d > 0.05).mean()) if len(next_1d) else None
        out[f"{label}_next_{target_horizon_bars}d_mean"] = float(next_h.mean()) if len(next_h) else None
        out[f"{label}_next_{target_horizon_bars}d_negative_fraction"] = (
            float((next_h < 0).mean()) if len(next_h) else None
        )
    if out[f"flagged_next_{target_horizon_bars}d_mean"] is not None and out[f"unflagged_next_{target_horizon_bars}d_mean"] is not None:
        out[f"flagged_minus_unflagged_next_{target_horizon_bars}d_mean"] = (
            float(out[f"flagged_next_{target_horizon_bars}d_mean"])
            - float(out[f"unflagged_next_{target_horizon_bars}d_mean"])
        )
    else:
        out[f"flagged_minus_unflagged_next_{target_horizon_bars}d_mean"] = None
    if out["flagged_next_1d_squeeze_gt_5pct_fraction"] is not None and out["unflagged_next_1d_squeeze_gt_5pct_fraction"] is not None:
        out["flagged_minus_unflagged_next_1d_squeeze_gt_5pct_fraction"] = (
            float(out["flagged_next_1d_squeeze_gt_5pct_fraction"])
            - float(out["unflagged_next_1d_squeeze_gt_5pct_fraction"])
        )
    else:
        out["flagged_minus_unflagged_next_1d_squeeze_gt_5pct_fraction"] = None
    return out


def _shuffle_diagnostic(
    rows: pd.DataFrame,
    *,
    flag_column: str,
    target_horizon_bars: int,
    shuffle_count: int,
    random_seed: int,
) -> dict[str, Any]:
    if rows.empty or flag_column not in rows.columns:
        return {"status": "empty"}
    observed = _safe_summary(rows, flag_column=flag_column, target_horizon_bars=target_horizon_bars)
    observed_delta = observed.get(f"flagged_minus_unflagged_next_{target_horizon_bars}d_mean")
    if observed_delta is None:
        return {"status": "insufficient_flag_variation", "observed": observed}

    rng = np.random.default_rng(random_seed)
    deltas: list[float] = []
    for _ in range(max(int(shuffle_count), 0)):
        shuffled = rows.copy()
        shuffled[flag_column] = (
            shuffled.groupby("date_utc", group_keys=False)[flag_column]
            .transform(lambda values: rng.permutation(values.to_numpy()))
            .to_numpy()
        )
        summary = _safe_summary(shuffled, flag_column=flag_column, target_horizon_bars=target_horizon_bars)
        delta = summary.get(f"flagged_minus_unflagged_next_{target_horizon_bars}d_mean")
        if delta is not None and np.isfinite(delta):
            deltas.append(float(delta))
    if not deltas:
        return {"status": "no_shuffle_deltas", "observed": observed}
    shuffle = np.asarray(deltas, dtype=float)
    return {
        "status": "ok",
        "observed": observed,
        "shuffle_count": int(len(shuffle)),
        "shuffle_delta_mean": float(shuffle.mean()),
        "shuffle_delta_p05": float(np.quantile(shuffle, 0.05)),
        "shuffle_delta_p95": float(np.quantile(shuffle, 0.95)),
        "observed_above_shuffle_p95": bool(float(observed_delta) > float(np.quantile(shuffle, 0.95))),
        "empirical_p_observed_or_larger": float((shuffle >= float(observed_delta)).mean()),
    }


def _coverage_summary(frame: pd.DataFrame, tape: pd.DataFrame, news: pd.DataFrame) -> dict[str, Any]:
    date_series = pd.to_datetime(frame["date_utc"], utc=True, errors="coerce")
    news_date_series = pd.to_datetime(news["research_effective_at_utc"], utc=True, errors="coerce")
    return {
        "risk_frame_rows": int(len(frame)),
        "risk_frame_subject_count": int(frame["subject"].astype(str).nunique()),
        "risk_frame_date_min": str(date_series.min().date()) if date_series.notna().any() else None,
        "risk_frame_date_max": str(date_series.max().date()) if date_series.notna().any() else None,
        "news_rows": int(len(news)),
        "news_effective_date_min": str(news_date_series.min().date()) if news_date_series.notna().any() else None,
        "news_effective_date_max": str(news_date_series.max().date()) if news_date_series.notna().any() else None,
        "event_tape_rows": int(len(tape)),
        "event_tape_subject_count": int(tape["subject"].astype(str).nunique()) if not tape.empty else 0,
    }


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    output_dir = args.output_dir or (
        ROOT
        / "artifacts"
        / "quant_research"
        / "factor_reports"
        / f"{args.as_of}-m3-3-event-tape-spk-stage0"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    features_artifact = v5_spk.base_eval._features_artifact_path(str(args.as_of))
    risk_frame = v5_spk.base_eval._build_risk_frame(features_artifact, target_horizon_bars=args.target_horizon_bars)
    news = pd.read_parquet(args.news_artifact)
    tape = _explode_news_tape(news, lookback_days=args.event_lookback_days)
    frame = _merge_event_tape(risk_frame, tape)

    selected, entered, exited = _selection_rows(
        frame=frame,
        target_horizon_bars=args.target_horizon_bars,
        short_count=3,
    )
    confirmed_flag = "m3_3_event_tape_confirmed_short_veto_flag_10d"
    short_veto_flag = "m3_3_event_tape_short_veto_flag_10d"
    real_repricing_flag = "m3_3_event_tape_real_repricing_flag_10d"
    hype_flag = "m3_3_event_tape_hype_flag_10d"

    diagnostics = {
        "selected_candidate_shorts_confirmed_event": _shuffle_diagnostic(
            selected,
            flag_column=confirmed_flag,
            target_horizon_bars=args.target_horizon_bars,
            shuffle_count=args.shuffle_count,
            random_seed=args.random_seed,
        ),
        "entered_spk_shorts_confirmed_event": _shuffle_diagnostic(
            entered,
            flag_column=confirmed_flag,
            target_horizon_bars=args.target_horizon_bars,
            shuffle_count=args.shuffle_count,
            random_seed=args.random_seed + 1,
        ),
        "entered_spk_shorts_short_veto_event": _safe_summary(
            entered,
            flag_column=short_veto_flag,
            target_horizon_bars=args.target_horizon_bars,
        ),
        "entered_spk_shorts_real_repricing_event": _safe_summary(
            entered,
            flag_column=real_repricing_flag,
            target_horizon_bars=args.target_horizon_bars,
        ),
        "entered_spk_shorts_hype_event": _safe_summary(
            entered,
            flag_column=hype_flag,
            target_horizon_bars=args.target_horizon_bars,
        ),
        "exited_parent_shorts_confirmed_event": _safe_summary(
            exited,
            flag_column=confirmed_flag,
            target_horizon_bars=args.target_horizon_bars,
        ),
    }

    entered_path = output_dir / "spk_entered_short_event_rows.csv"
    selected_path = output_dir / "spk_selected_short_event_rows.csv"
    tape_path = output_dir / "m3_3_event_tape_symbol_day.csv.gz"
    entered.to_csv(entered_path, index=False)
    selected.to_csv(selected_path, index=False)
    tape.to_csv(tape_path, index=False, compression="gzip")

    payload = {
        "contract_version": CONTRACT_VERSION,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": str(args.as_of),
        "target_horizon_bars": int(args.target_horizon_bars),
        "event_lookback_days": int(args.event_lookback_days),
        "features_artifact": str(features_artifact),
        "news_artifact": str(args.news_artifact),
        "coverage": _coverage_summary(frame, tape, news),
        "row_artifacts": {
            "event_tape_symbol_day": str(tape_path),
            "spk_entered_short_event_rows": str(entered_path),
            "spk_selected_short_event_rows": str(selected_path),
        },
        "selection_counts": {
            "selected_candidate_short_rows": int(len(selected)),
            "entered_spk_short_rows": int(len(entered)),
            "exited_parent_short_rows": int(len(exited)),
            "entered_unique_subjects": int(entered["subject"].astype(str).nunique()) if not entered.empty else 0,
        },
        "diagnostics": diagnostics,
        "interpretation_guardrails": {
            "short_return_sign": "For selected shorts, more negative forward return is better; positive flagged-minus-unflagged h10d mean means event-flagged shorts are worse shorts.",
            "stage0_question": "Does adjudicated event tape explain SP-K short false positives enough to justify a replacement/veto lane on the canonical parent?",
        },
    }
    report_path = output_dir / "m3_3_event_tape_spk_stage0.json"
    report_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(f"=== Wrote M3.3 event tape Stage 0 report to {report_path}")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
