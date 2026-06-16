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
from scripts.quant_research.alpha_stage0_quarantine import (  # noqa: E402
    evaluate_m3_3_event_tape_spk_stage0 as event_stage0,
)
from enhengclaw.quant_research.features import xs_alpha_ontology_v5_score  # noqa: E402


CONTRACT_VERSION = "m3_3_event_state_feature_stage0.v1"
DEFAULT_AS_OF = "2026-05-03"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Parent-independent M3.3 event-state feature diagnostics on the canonical v5 short boundary."
    )
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--target-horizon-bars", type=int, default=10)
    parser.add_argument("--event-lookback-days", type=int, default=10)
    parser.add_argument("--news-artifact", type=Path, default=event_stage0.DEFAULT_NEWS_ARTIFACT)
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser


def _load_event_frame(
    *,
    as_of: str,
    target_horizon_bars: int,
    event_lookback_days: int,
    news_artifact: Path,
    delay_days: int = 0,
) -> pd.DataFrame:
    features_artifact = v5_spk.base_eval._features_artifact_path(as_of)
    risk_frame = v5_spk.base_eval._build_risk_frame(features_artifact, target_horizon_bars=target_horizon_bars)
    news = pd.read_parquet(news_artifact)
    tape = event_stage0._explode_news_tape(news, lookback_days=event_lookback_days)
    if delay_days:
        tape = tape.copy()
        tape["date_utc"] = (
            pd.to_datetime(tape["date_utc"], utc=True, errors="coerce")
            + pd.to_timedelta(int(delay_days), unit="D")
        ).dt.date.astype(str)
    frame = event_stage0._merge_event_tape(risk_frame, tape)
    return _add_event_state_features(frame)


def _add_event_state_features(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    hype = pd.to_numeric(out.get("m3_3_event_tape_hype_count_10d"), errors="coerce").fillna(0.0)
    confirmed = pd.to_numeric(out.get("m3_3_event_tape_confirmed_short_veto_count_10d"), errors="coerce").fillna(0.0)
    real = pd.to_numeric(out.get("m3_3_event_tape_real_repricing_count_10d"), errors="coerce").fillna(0.0)
    short_veto = pd.to_numeric(out.get("m3_3_event_tape_short_veto_count_10d"), errors="coerce").fillna(0.0)
    any_actionable = pd.to_numeric(out.get("m3_3_event_tape_any_actionable_count_10d"), errors="coerce").fillna(0.0)
    max_link = pd.to_numeric(out.get("m3_3_event_tape_max_subject_link_strength_10d"), errors="coerce").fillna(0.0)
    max_mag = pd.to_numeric(out.get("m3_3_event_tape_max_market_impact_magnitude_10d"), errors="coerce").fillna(0.0)

    out["m3_3_event_state_hype_pressure_v1"] = hype.astype("float64")
    out["m3_3_event_state_confirmed_quality_v1"] = (confirmed + real + short_veto).astype("float64")
    out["m3_3_event_state_short_quality_v1"] = (
        confirmed + 0.5 * real + 0.5 * short_veto + 0.1 * max_link + 0.1 * max_mag - hype
    ).astype("float64")
    out["m3_3_event_state_noise_ratio_v1"] = (
        hype / any_actionable.replace(0.0, np.nan)
    ).replace([np.inf, -np.inf], np.nan).fillna(0.0).astype("float64")
    return out


def _rank_ic_by_timestamp(
    frame: pd.DataFrame,
    *,
    feature_column: str,
    target_horizon_bars: int,
    universe_mask: pd.Series | None = None,
) -> dict[str, Any]:
    horizon_column = f"forward_{target_horizon_bars}d_log_return"
    work = frame.loc[universe_mask.fillna(False)].copy() if universe_mask is not None else frame.copy()
    rows: list[float] = []
    for _, group in work.groupby("timestamp_ms", sort=False):
        feature = pd.to_numeric(group[feature_column], errors="coerce")
        short_payoff = -pd.to_numeric(group[horizon_column], errors="coerce")
        valid = feature.notna() & short_payoff.notna()
        if int(valid.sum()) < 5 or feature.loc[valid].nunique() < 2 or short_payoff.loc[valid].nunique() < 2:
            continue
        corr = feature.loc[valid].rank().corr(short_payoff.loc[valid].rank())
        if pd.notna(corr):
            rows.append(float(corr))
    arr = np.asarray(rows, dtype=float)
    if len(arr) == 0:
        return {"status": "no_valid_windows", "window_count": 0}
    return {
        "status": "ok",
        "window_count": int(len(arr)),
        "rank_ic_mean_vs_short_payoff": float(arr.mean()),
        "rank_ic_median_vs_short_payoff": float(np.median(arr)),
        "rank_ic_positive_rate": float((arr > 0).mean()),
    }


def _short_rows_for_score(
    frame: pd.DataFrame,
    *,
    score_column: str,
    target_horizon_bars: int,
    short_count: int = 3,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    keep = [
        "timestamp_ms",
        "date_utc",
        "subject",
        "liquidity_bucket",
        score_column,
        "m3_3_event_state_hype_pressure_v1",
        "m3_3_event_state_confirmed_quality_v1",
        "m3_3_event_state_short_quality_v1",
        "m3_3_event_state_noise_ratio_v1",
        "forward_1d_log_return",
        f"forward_{target_horizon_bars}d_log_return",
    ]
    keep = list(dict.fromkeys(keep))
    for _, group in frame.groupby("timestamp_ms", sort=False):
        shorts = group.sort_values(score_column, ascending=False).tail(min(short_count, len(group))).copy()
        rows.extend(shorts[keep].to_dict("records"))
    return pd.DataFrame(rows)


def _parent_boundary_replacement_rows(
    frame: pd.DataFrame,
    *,
    event_score_column: str,
    target_horizon_bars: int,
    pool_size: int = 8,
    short_count: int = 3,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    work = frame.copy()
    work["parent_score"] = xs_alpha_ontology_v5_score(work)
    selected_rows: list[dict[str, Any]] = []
    entered_rows: list[dict[str, Any]] = []
    exited_rows: list[dict[str, Any]] = []
    keep = [
        "timestamp_ms",
        "date_utc",
        "subject",
        "liquidity_bucket",
        "parent_score",
        event_score_column,
        "m3_3_event_state_hype_pressure_v1",
        "m3_3_event_state_confirmed_quality_v1",
        "m3_3_event_state_short_quality_v1",
        "m3_3_event_state_noise_ratio_v1",
        "forward_1d_log_return",
        f"forward_{target_horizon_bars}d_log_return",
    ]
    keep = list(dict.fromkeys(keep))
    for _, group in work.groupby("timestamp_ms", sort=False):
        ordered = group.sort_values("parent_score", ascending=False).copy()
        if len(ordered) <= short_count:
            continue
        parent_shorts = ordered.tail(min(short_count, len(ordered))).copy()
        tail_pool = ordered.tail(min(pool_size, len(ordered))).copy()
        event_candidates = tail_pool.sort_values([event_score_column, "parent_score"], ascending=[False, True]).head(
            min(short_count, len(tail_pool))
        )
        selected_rows.extend(event_candidates[keep].to_dict("records"))
        parent_subjects = set(parent_shorts["subject"].astype(str))
        event_subjects = set(event_candidates["subject"].astype(str))
        entered_rows.extend(event_candidates.loc[~event_candidates["subject"].astype(str).isin(parent_subjects), keep].to_dict("records"))
        exited_rows.extend(parent_shorts.loc[~parent_shorts["subject"].astype(str).isin(event_subjects), keep].to_dict("records"))
    return pd.DataFrame(selected_rows), pd.DataFrame(entered_rows), pd.DataFrame(exited_rows)


def _summarize_rows(rows: pd.DataFrame, *, target_horizon_bars: int) -> dict[str, Any]:
    if rows.empty:
        return {"status": "empty", "row_count": 0}
    horizon_column = f"forward_{target_horizon_bars}d_log_return"
    next_1d = pd.to_numeric(rows["forward_1d_log_return"], errors="coerce").dropna()
    next_h = pd.to_numeric(rows[horizon_column], errors="coerce").dropna()
    hype = pd.to_numeric(rows.get("m3_3_event_state_hype_pressure_v1", 0), errors="coerce").fillna(0.0)
    quality = pd.to_numeric(rows.get("m3_3_event_state_short_quality_v1", 0), errors="coerce").fillna(0.0)
    return {
        "status": "ok",
        "row_count": int(len(rows)),
        "subject_count": int(rows["subject"].astype(str).nunique()) if "subject" in rows.columns else None,
        "hype_active_fraction": float((hype > 0).mean()) if len(hype) else None,
        "mean_event_short_quality": float(quality.mean()) if len(quality) else None,
        "next_1d_mean": float(next_1d.mean()) if len(next_1d) else None,
        "next_1d_squeeze_gt_5pct_fraction": float((next_1d > 0.05).mean()) if len(next_1d) else None,
        f"next_{target_horizon_bars}d_mean": float(next_h.mean()) if len(next_h) else None,
        f"next_{target_horizon_bars}d_negative_fraction": float((next_h < 0).mean()) if len(next_h) else None,
    }


def _compare(*, candidate: dict[str, Any], baseline: dict[str, Any], target_horizon_bars: int) -> dict[str, Any]:
    fields = [
        "hype_active_fraction",
        "mean_event_short_quality",
        "next_1d_squeeze_gt_5pct_fraction",
        f"next_{target_horizon_bars}d_mean",
        f"next_{target_horizon_bars}d_negative_fraction",
    ]
    out: dict[str, Any] = {}
    for field in fields:
        if candidate.get(field) is not None and baseline.get(field) is not None:
            out[f"delta_{field}"] = float(candidate[field]) - float(baseline[field])
    return out


def _evaluate(frame: pd.DataFrame, *, target_horizon_bars: int) -> dict[str, Any]:
    work = frame.copy()
    work["parent_score"] = xs_alpha_ontology_v5_score(work)
    parent_short_rows = _short_rows_for_score(work, score_column="parent_score", target_horizon_bars=target_horizon_bars)
    boundary_mask = pd.Series(False, index=work.index)
    for _, group in work.groupby("timestamp_ms", sort=False):
        tail_idx = group.sort_values("parent_score", ascending=False).tail(min(8, len(group))).index
        boundary_mask.loc[tail_idx] = True

    feature_columns = [
        "m3_3_event_state_hype_pressure_v1",
        "m3_3_event_state_confirmed_quality_v1",
        "m3_3_event_state_short_quality_v1",
        "m3_3_event_state_noise_ratio_v1",
    ]
    feature_evidence = {
        column: {
            "all_core": _rank_ic_by_timestamp(work, feature_column=column, target_horizon_bars=target_horizon_bars),
            "parent_bottom8_boundary": _rank_ic_by_timestamp(
                work,
                feature_column=column,
                target_horizon_bars=target_horizon_bars,
                universe_mask=boundary_mask,
            ),
        }
        for column in feature_columns
    }
    selected, entered, exited = _parent_boundary_replacement_rows(
        work,
        event_score_column="m3_3_event_state_short_quality_v1",
        target_horizon_bars=target_horizon_bars,
    )
    parent_summary = _summarize_rows(parent_short_rows, target_horizon_bars=target_horizon_bars)
    event_summary = _summarize_rows(selected, target_horizon_bars=target_horizon_bars)
    entered_summary = _summarize_rows(entered, target_horizon_bars=target_horizon_bars)
    exited_summary = _summarize_rows(exited, target_horizon_bars=target_horizon_bars)
    return {
        "feature_evidence": feature_evidence,
        "parent_short_summary": parent_summary,
        "event_quality_boundary_summary": event_summary,
        "event_quality_vs_parent_short": _compare(
            candidate=event_summary,
            baseline=parent_summary,
            target_horizon_bars=target_horizon_bars,
        ),
        "event_quality_replacements_vs_parent": {
            "entered": entered_summary,
            "exited": exited_summary,
            "entered_minus_exited": _compare(
                candidate=entered_summary,
                baseline=exited_summary,
                target_horizon_bars=target_horizon_bars,
            ),
        },
        "row_counts": {
            "parent_short_rows": int(len(parent_short_rows)),
            "event_quality_selected_rows": int(len(selected)),
            "event_quality_entered_rows": int(len(entered)),
            "event_quality_exited_rows": int(len(exited)),
        },
    }


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    output_dir = args.output_dir or (
        ROOT
        / "artifacts"
        / "quant_research"
        / "factor_reports"
        / f"{args.as_of}-m3-3-event-state-feature-stage0"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    frame = _load_event_frame(
        as_of=str(args.as_of),
        target_horizon_bars=int(args.target_horizon_bars),
        event_lookback_days=int(args.event_lookback_days),
        news_artifact=Path(args.news_artifact),
        delay_days=0,
    )
    delayed_frame = _load_event_frame(
        as_of=str(args.as_of),
        target_horizon_bars=int(args.target_horizon_bars),
        event_lookback_days=int(args.event_lookback_days),
        news_artifact=Path(args.news_artifact),
        delay_days=1,
    )
    evaluation = _evaluate(frame, target_horizon_bars=int(args.target_horizon_bars))
    delayed_evaluation = _evaluate(delayed_frame, target_horizon_bars=int(args.target_horizon_bars))
    selected, entered, exited = _parent_boundary_replacement_rows(
        frame,
        event_score_column="m3_3_event_state_short_quality_v1",
        target_horizon_bars=int(args.target_horizon_bars),
    )
    selected_path = output_dir / "event_quality_boundary_selected_rows.csv"
    entered_path = output_dir / "event_quality_boundary_entered_vs_parent.csv"
    exited_path = output_dir / "event_quality_boundary_exited_vs_parent.csv"
    selected.to_csv(selected_path, index=False)
    entered.to_csv(entered_path, index=False)
    exited.to_csv(exited_path, index=False)
    payload = {
        "contract_version": CONTRACT_VERSION,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": str(args.as_of),
        "target_horizon_bars": int(args.target_horizon_bars),
        "event_lookback_days": int(args.event_lookback_days),
        "news_artifact": str(args.news_artifact),
        "status_scope": "diagnostic_only_parent_independent_event_state",
        "row_artifacts": {
            "event_quality_boundary_selected_rows": str(selected_path),
            "event_quality_boundary_entered_vs_parent": str(entered_path),
            "event_quality_boundary_exited_vs_parent": str(exited_path),
        },
        "evaluation": evaluation,
        "delay_plus_1d_evaluation": delayed_evaluation,
        "decision_rules": {
            "short_return_sign": "For short baskets, more negative forward return is better.",
            "promote_to_manifest_candidate_if": [
                "event_state_short_quality_v1 has positive boundary rank IC versus short payoff",
                "event-quality selected short basket beats parent shorts",
                "entered rows are better shorts than exited rows",
                "direction survives +1d event delay",
            ],
        },
    }
    report_path = output_dir / "m3_3_event_state_feature_stage0.json"
    report_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(f"=== Wrote M3.3 event-state feature Stage 0 report to {report_path}")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
