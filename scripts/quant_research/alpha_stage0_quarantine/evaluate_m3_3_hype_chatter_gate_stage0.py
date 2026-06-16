from __future__ import annotations

import argparse
import json
import sys
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
from scripts.quant_research.alpha_stage0_quarantine import (  # noqa: E402
    evaluate_m3_3_event_tape_spk_stage0 as event_stage0,
)
from enhengclaw.quant_research.features import (  # noqa: E402
    _xs_alpha_ontology_v5_h10d_base_raw_score,
    _xs_alpha_ontology_v6_h10d_spk_short_replacement_score,
    xs_alpha_ontology_v5_h10d_spk_short_replace_mid_v1_score,
    xs_alpha_ontology_v5_score,
)


CONTRACT_VERSION = "m3_3_hype_chatter_gate_stage0.v1"
DEFAULT_AS_OF = "2026-05-03"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Stage 0 M3.3 hype-chatter gate test on SP-K boundary shorts. This is diagnostic evidence only; "
            "it does not create or promote a canonical manifest."
        )
    )
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--target-horizon-bars", type=int, default=10)
    parser.add_argument("--event-lookback-days", type=int, default=10)
    parser.add_argument("--news-artifact", type=Path, default=event_stage0.DEFAULT_NEWS_ARTIFACT)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument(
        "--shuffle-count",
        type=int,
        default=0,
        help="Optional expensive symbol-shuffle count. Default 0 keeps the Stage 0 run interactive.",
    )
    parser.add_argument("--random-seed", type=int, default=20260503)
    return parser


def _spk_hype_candidate_veto_score(frame: pd.DataFrame) -> pd.Series:
    return _xs_alpha_ontology_v6_h10d_spk_short_replacement_score(
        frame,
        base_raw_score_fn=_xs_alpha_ontology_v5_h10d_base_raw_score,
        replacement_pool_size=6,
        signal_threshold=0.0,
        max_replacements_per_timestamp=1,
        candidate_veto_column="m3_3_event_tape_hype_flag_10d",
    )


def _spk_hype_selected_short_veto_score(frame: pd.DataFrame) -> pd.Series:
    return _xs_alpha_ontology_v6_h10d_spk_short_replacement_score(
        frame,
        base_raw_score_fn=_xs_alpha_ontology_v5_h10d_base_raw_score,
        replacement_pool_size=6,
        signal_threshold=0.0,
        max_replacements_per_timestamp=1,
        candidate_veto_column="m3_3_event_tape_hype_flag_10d",
        selected_short_veto_column="m3_3_event_tape_hype_flag_10d",
        selected_short_veto_pool_size=10,
        max_selected_short_veto_replacements=1,
    )


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
    return event_stage0._merge_event_tape(risk_frame, tape)


def _short_basket_rows(
    frame: pd.DataFrame,
    *,
    scorer: Callable[[pd.DataFrame], pd.Series],
    label: str,
    target_horizon_bars: int,
    short_count: int = 3,
) -> pd.DataFrame:
    work = frame.copy()
    work["score"] = scorer(work)
    rows: list[dict[str, Any]] = []
    event_columns = [column for column in work.columns if column.startswith("m3_3_event_tape_")]
    base_columns = [
        "timestamp_ms",
        "date_utc",
        "subject",
        "liquidity_bucket",
        "post_pump_stall_core_score_3d",
        "forward_1d_log_return",
        f"forward_{target_horizon_bars}d_log_return",
    ]
    keep_columns = base_columns + event_columns
    for _, group in work.groupby("timestamp_ms", sort=False):
        shorts = group.sort_values("score", ascending=False).tail(min(short_count, len(group))).copy()
        rows.extend(shorts[keep_columns].assign(variant=label).to_dict("records"))
    return pd.DataFrame(rows)


def _change_rows(
    frame: pd.DataFrame,
    *,
    base_scorer: Callable[[pd.DataFrame], pd.Series],
    candidate_scorer: Callable[[pd.DataFrame], pd.Series],
    target_horizon_bars: int,
    short_count: int = 3,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    work = frame.copy()
    work["base_score"] = base_scorer(work)
    work["candidate_score"] = candidate_scorer(work)
    event_columns = [column for column in work.columns if column.startswith("m3_3_event_tape_")]
    keep_columns = [
        "timestamp_ms",
        "date_utc",
        "subject",
        "liquidity_bucket",
        "post_pump_stall_core_score_3d",
        "forward_1d_log_return",
        f"forward_{target_horizon_bars}d_log_return",
    ] + event_columns
    entered_rows: list[dict[str, Any]] = []
    exited_rows: list[dict[str, Any]] = []
    for _, group in work.groupby("timestamp_ms", sort=False):
        base_shorts = group.sort_values("base_score", ascending=False).tail(min(short_count, len(group))).copy()
        candidate_shorts = group.sort_values("candidate_score", ascending=False).tail(min(short_count, len(group))).copy()
        base_subjects = set(base_shorts["subject"].astype(str))
        candidate_subjects = set(candidate_shorts["subject"].astype(str))
        entered_rows.extend(candidate_shorts.loc[~candidate_shorts["subject"].astype(str).isin(base_subjects), keep_columns].to_dict("records"))
        exited_rows.extend(base_shorts.loc[~base_shorts["subject"].astype(str).isin(candidate_subjects), keep_columns].to_dict("records"))
    return pd.DataFrame(entered_rows), pd.DataFrame(exited_rows)


def _summarize_rows(rows: pd.DataFrame, *, target_horizon_bars: int) -> dict[str, Any]:
    if rows.empty:
        return {"status": "empty", "row_count": 0}
    horizon_column = f"forward_{target_horizon_bars}d_log_return"
    next_1d = pd.to_numeric(rows["forward_1d_log_return"], errors="coerce").dropna()
    next_h = pd.to_numeric(rows[horizon_column], errors="coerce").dropna()
    hype = pd.to_numeric(rows.get("m3_3_event_tape_hype_flag_10d", 0), errors="coerce").fillna(0).gt(0)
    confirmed = pd.to_numeric(rows.get("m3_3_event_tape_confirmed_short_veto_flag_10d", 0), errors="coerce").fillna(0).gt(0)
    return {
        "status": "ok",
        "row_count": int(len(rows)),
        "subject_count": int(rows["subject"].astype(str).nunique()) if "subject" in rows.columns else None,
        "hype_fraction": float(hype.mean()) if len(rows) else None,
        "confirmed_event_fraction": float(confirmed.mean()) if len(rows) else None,
        "next_1d_mean": float(next_1d.mean()) if len(next_1d) else None,
        "next_1d_squeeze_gt_5pct_fraction": float((next_1d > 0.05).mean()) if len(next_1d) else None,
        f"next_{target_horizon_bars}d_mean": float(next_h.mean()) if len(next_h) else None,
        f"next_{target_horizon_bars}d_negative_fraction": float((next_h < 0).mean()) if len(next_h) else None,
    }


def _compare_summaries(
    *,
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    target_horizon_bars: int,
) -> dict[str, Any]:
    fields = [
        "next_1d_squeeze_gt_5pct_fraction",
        f"next_{target_horizon_bars}d_mean",
        f"next_{target_horizon_bars}d_negative_fraction",
        "hype_fraction",
    ]
    out: dict[str, Any] = {}
    for field in fields:
        if baseline.get(field) is not None and candidate.get(field) is not None:
            out[f"delta_{field}"] = float(candidate[field]) - float(baseline[field])
    return out


def _evaluate_variants(frame: pd.DataFrame, *, target_horizon_bars: int) -> dict[str, Any]:
    scorer_map: dict[str, Callable[[pd.DataFrame], pd.Series]] = {
        "parent_v5": xs_alpha_ontology_v5_score,
        "spk_no_news": xs_alpha_ontology_v5_h10d_spk_short_replace_mid_v1_score,
        "spk_hype_candidate_veto": _spk_hype_candidate_veto_score,
        "spk_hype_candidate_plus_selected_veto": _spk_hype_selected_short_veto_score,
    }
    basket_rows: dict[str, pd.DataFrame] = {
        label: _short_basket_rows(frame, scorer=scorer, label=label, target_horizon_bars=target_horizon_bars)
        for label, scorer in scorer_map.items()
    }
    summaries = {label: _summarize_rows(rows, target_horizon_bars=target_horizon_bars) for label, rows in basket_rows.items()}
    comparisons = {
        f"{label}_vs_spk_no_news": _compare_summaries(
            baseline=summaries["spk_no_news"],
            candidate=summaries[label],
            target_horizon_bars=target_horizon_bars,
        )
        for label in ["spk_hype_candidate_veto", "spk_hype_candidate_plus_selected_veto"]
    }
    replacement_summaries: dict[str, Any] = {}
    for label in ["spk_hype_candidate_veto", "spk_hype_candidate_plus_selected_veto"]:
        entered, exited = _change_rows(
            frame,
            base_scorer=scorer_map["spk_no_news"],
            candidate_scorer=scorer_map[label],
            target_horizon_bars=target_horizon_bars,
        )
        replacement_summaries[f"{label}_vs_spk_no_news"] = {
            "entered": _summarize_rows(entered, target_horizon_bars=target_horizon_bars),
            "exited": _summarize_rows(exited, target_horizon_bars=target_horizon_bars),
            "entered_minus_exited": _compare_summaries(
                baseline=_summarize_rows(exited, target_horizon_bars=target_horizon_bars),
                candidate=_summarize_rows(entered, target_horizon_bars=target_horizon_bars),
                target_horizon_bars=target_horizon_bars,
            ),
        }
    return {
        "basket_summaries": summaries,
        "basket_comparisons": comparisons,
        "replacement_summaries": replacement_summaries,
    }


def _symbol_shuffle_diagnostic(
    frame: pd.DataFrame,
    *,
    target_horizon_bars: int,
    shuffle_count: int,
    random_seed: int,
) -> dict[str, Any]:
    if int(shuffle_count) <= 0:
        return {"status": "skipped", "reason": "shuffle_count_le_0"}
    rng = np.random.default_rng(random_seed)
    observed = _evaluate_variants(frame, target_horizon_bars=target_horizon_bars)
    observed_delta = observed["basket_comparisons"]["spk_hype_candidate_veto_vs_spk_no_news"].get(
        f"delta_next_{target_horizon_bars}d_mean"
    )
    if observed_delta is None:
        return {"status": "missing_observed_delta", "observed": observed}

    deltas: list[float] = []
    for _ in range(max(int(shuffle_count), 0)):
        shuffled = frame.copy()
        flag = "m3_3_event_tape_hype_flag_10d"
        shuffled[flag] = (
            shuffled.groupby("date_utc", group_keys=False)[flag]
            .transform(lambda values: rng.permutation(values.to_numpy()))
            .to_numpy()
        )
        summary = _evaluate_variants(shuffled, target_horizon_bars=target_horizon_bars)
        delta = summary["basket_comparisons"]["spk_hype_candidate_veto_vs_spk_no_news"].get(
            f"delta_next_{target_horizon_bars}d_mean"
        )
        if delta is not None and np.isfinite(delta):
            deltas.append(float(delta))
    if not deltas:
        return {"status": "no_shuffle_deltas", "observed": observed}
    arr = np.asarray(deltas, dtype=float)
    return {
        "status": "ok",
        "observed_delta_next_h_mean": float(observed_delta),
        "shuffle_count": int(len(arr)),
        "shuffle_delta_mean": float(arr.mean()),
        "shuffle_delta_p05": float(np.quantile(arr, 0.05)),
        "shuffle_delta_p95": float(np.quantile(arr, 0.95)),
        "observed_below_shuffle_p05": bool(float(observed_delta) < float(np.quantile(arr, 0.05))),
        "empirical_p_observed_or_smaller": float((arr <= float(observed_delta)).mean()),
    }


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    output_dir = args.output_dir or (
        ROOT
        / "artifacts"
        / "quant_research"
        / "factor_reports"
        / f"{args.as_of}-m3-3-hype-chatter-gate-stage0"
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
    evaluation = _evaluate_variants(frame, target_horizon_bars=int(args.target_horizon_bars))
    delayed_evaluation = _evaluate_variants(delayed_frame, target_horizon_bars=int(args.target_horizon_bars))
    shuffle = _symbol_shuffle_diagnostic(
        frame,
        target_horizon_bars=int(args.target_horizon_bars),
        shuffle_count=int(args.shuffle_count),
        random_seed=int(args.random_seed),
    )

    entered, exited = _change_rows(
        frame,
        base_scorer=xs_alpha_ontology_v5_h10d_spk_short_replace_mid_v1_score,
        candidate_scorer=_spk_hype_candidate_veto_score,
        target_horizon_bars=int(args.target_horizon_bars),
    )
    entered_path = output_dir / "hype_candidate_veto_entered_vs_spk.csv"
    exited_path = output_dir / "hype_candidate_veto_exited_vs_spk.csv"
    entered.to_csv(entered_path, index=False)
    exited.to_csv(exited_path, index=False)

    payload = {
        "contract_version": CONTRACT_VERSION,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": str(args.as_of),
        "target_horizon_bars": int(args.target_horizon_bars),
        "event_lookback_days": int(args.event_lookback_days),
        "news_artifact": str(args.news_artifact),
        "status_scope": "diagnostic_only_quarantine_respect",
        "row_artifacts": {
            "hype_candidate_veto_entered_vs_spk": str(entered_path),
            "hype_candidate_veto_exited_vs_spk": str(exited_path),
        },
        "evaluation": evaluation,
        "delay_plus_1d_evaluation": delayed_evaluation,
        "symbol_shuffle_diagnostic": shuffle,
        "decision_rules": {
            "short_return_sign": "For short baskets, more negative forward return is better.",
            "candidate_veto_promote_to_full_ab_if": [
                "basket next_h_mean improves versus spk_no_news",
                "changed entered rows are better shorts than exited rows",
                "effect remains directionally negative under +1d delay",
                "observed improvement beats symbol-shuffle lower tail",
            ],
        },
    }
    report_path = output_dir / "m3_3_hype_chatter_gate_stage0.json"
    report_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(f"=== Wrote M3.3 hype-chatter gate Stage 0 report to {report_path}")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
