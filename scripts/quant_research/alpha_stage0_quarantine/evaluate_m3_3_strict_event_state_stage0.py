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

from scripts.quant_research.alpha_stage0_quarantine import (  # noqa: E402
    evaluate_m3_3_event_state_feature_stage0 as feature_stage0,
    evaluate_m3_3_event_tape_spk_stage0 as event_stage0,
)
from enhengclaw.quant_research.features import xs_alpha_ontology_v5_score  # noqa: E402


CONTRACT_VERSION = "m3_3_strict_event_state_stage0.v1"
DEFAULT_AS_OF = "2026-05-03"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Strict M3.3 event-state short-boundary selector diagnostics."
    )
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--target-horizon-bars", type=int, default=10)
    parser.add_argument("--event-lookback-days", type=int, default=10)
    parser.add_argument("--news-artifact", type=Path, default=event_stage0.DEFAULT_NEWS_ARTIFACT)
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser


def _load_frame(
    *,
    as_of: str,
    target_horizon_bars: int,
    event_lookback_days: int,
    news_artifact: Path,
    delay_days: int,
) -> pd.DataFrame:
    return feature_stage0._load_event_frame(
        as_of=as_of,
        target_horizon_bars=target_horizon_bars,
        event_lookback_days=event_lookback_days,
        news_artifact=news_artifact,
        delay_days=delay_days,
    )


def _eligible_mask(
    frame: pd.DataFrame,
    *,
    min_quality: float,
    max_noise_ratio: float,
    require_no_hype: bool,
) -> pd.Series:
    quality = pd.to_numeric(frame["m3_3_event_state_short_quality_v1"], errors="coerce").fillna(0.0)
    noise = pd.to_numeric(frame["m3_3_event_state_noise_ratio_v1"], errors="coerce").fillna(0.0)
    hype = pd.to_numeric(frame["m3_3_event_state_hype_pressure_v1"], errors="coerce").fillna(0.0)
    mask = quality.ge(float(min_quality)) & noise.le(float(max_noise_ratio))
    if require_no_hype:
        mask &= hype.le(0.0)
    return mask


def _strict_boundary_rows(
    frame: pd.DataFrame,
    *,
    min_quality: float,
    max_noise_ratio: float,
    require_no_hype: bool,
    target_horizon_bars: int,
    pool_size: int = 8,
    short_count: int = 3,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    work = frame.copy()
    work["parent_score"] = xs_alpha_ontology_v5_score(work)
    work["strict_eligible"] = _eligible_mask(
        work,
        min_quality=min_quality,
        max_noise_ratio=max_noise_ratio,
        require_no_hype=require_no_hype,
    )
    keep = [
        "timestamp_ms",
        "date_utc",
        "subject",
        "liquidity_bucket",
        "parent_score",
        "strict_eligible",
        "m3_3_event_state_hype_pressure_v1",
        "m3_3_event_state_confirmed_quality_v1",
        "m3_3_event_state_short_quality_v1",
        "m3_3_event_state_noise_ratio_v1",
        "forward_1d_log_return",
        f"forward_{target_horizon_bars}d_log_return",
    ]
    parent_rows: list[dict[str, Any]] = []
    selected_rows: list[dict[str, Any]] = []
    entered_rows: list[dict[str, Any]] = []
    exited_rows: list[dict[str, Any]] = []
    changed_timestamps = 0
    eligible_timestamps = 0
    total_timestamps = 0
    for _, group in work.groupby("timestamp_ms", sort=False):
        total_timestamps += 1
        ordered = group.sort_values("parent_score", ascending=False).copy()
        if len(ordered) <= short_count:
            continue
        parent_shorts = ordered.tail(min(short_count, len(ordered))).copy()
        tail_pool = ordered.tail(min(pool_size, len(ordered))).copy()
        eligible_pool = tail_pool.loc[tail_pool["strict_eligible"]].copy()
        if not eligible_pool.empty:
            eligible_timestamps += 1
        selected = parent_shorts.copy()
        if not eligible_pool.empty:
            candidate_order = eligible_pool.sort_values(
                ["m3_3_event_state_short_quality_v1", "parent_score"],
                ascending=[False, True],
            ).copy()
            selected = pd.concat([candidate_order, parent_shorts], axis=0)
            selected = selected.loc[~selected["subject"].astype(str).duplicated(keep="first")].head(short_count)
        parent_subjects = set(parent_shorts["subject"].astype(str))
        selected_subjects = set(selected["subject"].astype(str))
        if parent_subjects != selected_subjects:
            changed_timestamps += 1
        parent_rows.extend(parent_shorts[keep].to_dict("records"))
        selected_rows.extend(selected[keep].to_dict("records"))
        entered_rows.extend(selected.loc[~selected["subject"].astype(str).isin(parent_subjects), keep].to_dict("records"))
        exited_rows.extend(parent_shorts.loc[~parent_shorts["subject"].astype(str).isin(selected_subjects), keep].to_dict("records"))
    parent = pd.DataFrame(parent_rows)
    selected = pd.DataFrame(selected_rows)
    entered = pd.DataFrame(entered_rows)
    exited = pd.DataFrame(exited_rows)
    meta = pd.DataFrame(
        [
            {
                "timestamp_count": total_timestamps,
                "eligible_timestamp_count": eligible_timestamps,
                "changed_timestamp_count": changed_timestamps,
                "eligible_timestamp_fraction": eligible_timestamps / max(total_timestamps, 1),
                "changed_timestamp_fraction": changed_timestamps / max(total_timestamps, 1),
            }
        ]
    )
    return parent, selected, entered, exited, meta


def _summarize(rows: pd.DataFrame, *, target_horizon_bars: int) -> dict[str, Any]:
    if rows.empty:
        return {"status": "empty", "row_count": 0}
    hcol = f"forward_{target_horizon_bars}d_log_return"
    h = pd.to_numeric(rows[hcol], errors="coerce").dropna()
    d1 = pd.to_numeric(rows["forward_1d_log_return"], errors="coerce").dropna()
    q = pd.to_numeric(rows["m3_3_event_state_short_quality_v1"], errors="coerce").fillna(0.0)
    noise = pd.to_numeric(rows["m3_3_event_state_noise_ratio_v1"], errors="coerce").fillna(0.0)
    hype = pd.to_numeric(rows["m3_3_event_state_hype_pressure_v1"], errors="coerce").fillna(0.0)
    eligible = rows["strict_eligible"].fillna(False).astype(bool) if "strict_eligible" in rows.columns else pd.Series(False, index=rows.index)
    return {
        "status": "ok",
        "row_count": int(len(rows)),
        "subject_count": int(rows["subject"].astype(str).nunique()) if "subject" in rows.columns else None,
        "eligible_fraction": float(eligible.mean()) if len(eligible) else None,
        "mean_event_short_quality": float(q.mean()) if len(q) else None,
        "mean_noise_ratio": float(noise.mean()) if len(noise) else None,
        "hype_active_fraction": float((hype > 0).mean()) if len(hype) else None,
        "next_1d_mean": float(d1.mean()) if len(d1) else None,
        "next_1d_squeeze_gt_5pct_fraction": float((d1 > 0.05).mean()) if len(d1) else None,
        f"next_{target_horizon_bars}d_mean": float(h.mean()) if len(h) else None,
        f"next_{target_horizon_bars}d_negative_fraction": float((h < 0).mean()) if len(h) else None,
    }


def _compare(*, candidate: dict[str, Any], baseline: dict[str, Any], target_horizon_bars: int) -> dict[str, Any]:
    fields = [
        "eligible_fraction",
        "mean_event_short_quality",
        "mean_noise_ratio",
        "hype_active_fraction",
        "next_1d_squeeze_gt_5pct_fraction",
        f"next_{target_horizon_bars}d_mean",
        f"next_{target_horizon_bars}d_negative_fraction",
    ]
    out: dict[str, Any] = {}
    for field in fields:
        if candidate.get(field) is not None and baseline.get(field) is not None:
            out[f"delta_{field}"] = float(candidate[field]) - float(baseline[field])
    return out


def _evaluate_variant(
    frame: pd.DataFrame,
    *,
    label: str,
    min_quality: float,
    max_noise_ratio: float,
    require_no_hype: bool,
    target_horizon_bars: int,
) -> dict[str, Any]:
    parent, selected, entered, exited, meta = _strict_boundary_rows(
        frame,
        min_quality=min_quality,
        max_noise_ratio=max_noise_ratio,
        require_no_hype=require_no_hype,
        target_horizon_bars=target_horizon_bars,
    )
    parent_summary = _summarize(parent, target_horizon_bars=target_horizon_bars)
    selected_summary = _summarize(selected, target_horizon_bars=target_horizon_bars)
    entered_summary = _summarize(entered, target_horizon_bars=target_horizon_bars)
    exited_summary = _summarize(exited, target_horizon_bars=target_horizon_bars)
    return {
        "label": label,
        "thresholds": {
            "min_quality": float(min_quality),
            "max_noise_ratio": float(max_noise_ratio),
            "require_no_hype": bool(require_no_hype),
        },
        "timestamp_activity": meta.iloc[0].to_dict(),
        "parent_short_summary": parent_summary,
        "selected_summary": selected_summary,
        "selected_vs_parent": _compare(
            candidate=selected_summary,
            baseline=parent_summary,
            target_horizon_bars=target_horizon_bars,
        ),
        "entered": entered_summary,
        "exited": exited_summary,
        "entered_minus_exited": _compare(
            candidate=entered_summary,
            baseline=exited_summary,
            target_horizon_bars=target_horizon_bars,
        ),
        "rows": {
            "parent": parent,
            "selected": selected,
            "entered": entered,
            "exited": exited,
        },
    }


def _strip_rows(payload: dict[str, Any]) -> dict[str, Any]:
    out = dict(payload)
    out.pop("rows", None)
    return out


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    output_dir = args.output_dir or (
        ROOT
        / "artifacts"
        / "quant_research"
        / "factor_reports"
        / f"{args.as_of}-m3-3-strict-event-state-stage0"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    frame = _load_frame(
        as_of=str(args.as_of),
        target_horizon_bars=int(args.target_horizon_bars),
        event_lookback_days=int(args.event_lookback_days),
        news_artifact=Path(args.news_artifact),
        delay_days=0,
    )
    delayed = _load_frame(
        as_of=str(args.as_of),
        target_horizon_bars=int(args.target_horizon_bars),
        event_lookback_days=int(args.event_lookback_days),
        news_artifact=Path(args.news_artifact),
        delay_days=1,
    )
    specs = [
        ("strict_q1_noise0", 1.0, 0.0, True),
        ("strict_q05_noise0", 0.5, 0.0, True),
        ("strict_q1_noise05", 1.0, 0.5, False),
    ]
    evaluations = {
        label: _evaluate_variant(
            frame,
            label=label,
            min_quality=min_quality,
            max_noise_ratio=max_noise,
            require_no_hype=require_no_hype,
            target_horizon_bars=int(args.target_horizon_bars),
        )
        for label, min_quality, max_noise, require_no_hype in specs
    }
    delayed_evaluations = {
        label: _evaluate_variant(
            delayed,
            label=label,
            min_quality=min_quality,
            max_noise_ratio=max_noise,
            require_no_hype=require_no_hype,
            target_horizon_bars=int(args.target_horizon_bars),
        )
        for label, min_quality, max_noise, require_no_hype in specs
    }
    row_artifacts: dict[str, dict[str, str]] = {}
    for label, payload in evaluations.items():
        row_artifacts[label] = {}
        for row_name in ["selected", "entered", "exited"]:
            path = output_dir / f"{label}_{row_name}.csv"
            payload["rows"][row_name].to_csv(path, index=False)
            row_artifacts[label][row_name] = str(path)
    report = {
        "contract_version": CONTRACT_VERSION,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": str(args.as_of),
        "target_horizon_bars": int(args.target_horizon_bars),
        "event_lookback_days": int(args.event_lookback_days),
        "news_artifact": str(args.news_artifact),
        "row_artifacts": row_artifacts,
        "evaluation": {label: _strip_rows(payload) for label, payload in evaluations.items()},
        "delay_plus_1d_evaluation": {label: _strip_rows(payload) for label, payload in delayed_evaluations.items()},
        "decision_rules": {
            "short_return_sign": "For selected shorts, more negative forward return is better.",
            "promote_to_manifest_candidate_if": [
                "selected basket improves parent h10d mean by at least 5 bps",
                "entered rows are negative-return shorts",
                "entered-minus-exited h10d delta is negative",
                "direction survives +1d event delay",
                "timestamp activity is not too sparse",
            ],
        },
    }
    report_path = output_dir / "m3_3_strict_event_state_stage0.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"=== Wrote M3.3 strict event-state Stage 0 report to {report_path}")
    summary = {
        label: {
            "selected_vs_parent_next_h_mean_delta": payload["selected_vs_parent"].get(
                f"delta_next_{int(args.target_horizon_bars)}d_mean"
            ),
            "entered_next_h_mean": payload["entered"].get(f"next_{int(args.target_horizon_bars)}d_mean"),
            "entered_minus_exited_next_h_mean_delta": payload["entered_minus_exited"].get(
                f"delta_next_{int(args.target_horizon_bars)}d_mean"
            ),
            "changed_timestamp_fraction": payload["timestamp_activity"].get("changed_timestamp_fraction"),
        }
        for label, payload in report["evaluation"].items()
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
